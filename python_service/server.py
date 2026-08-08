import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pydantic import BaseModel, Field, ValidationError, model_validator

from .playwright_crawler import fetch_product_page
from .deepseek import chat_json
from .doubao import (
    DEFAULT_DOUBAO_FALLBACK_MODEL,
    DEFAULT_DOUBAO_MODEL,
    DoubaoTimeoutError,
    chat_json as doubao_json,
)
from .gemini_kie import chat_json as gemini_kie_json
from .feishu_knowledge import knowledge
from .kie import create_image_task, create_kling_video_task, create_overseas_video_task, query_task
from .tos_upload import mirror_video_to_tos
from .topaz import create_enhancement_task, query_enhancement_task
from .media import render_edit, export_editing_handoff, align_subtitles
from .minimax import generate_music
from .prompts import product_facts_prompt, stage_one_prompt, stage_two_prompt, stage_three_prompt


def _knowledge_trace(role: str) -> dict:
    meta = dict(getattr(knowledge, "last_context_meta", {}) or {})
    meta["role"] = role
    return meta


def _stage_one_doubao_json(prompt: str, system_prompt: str = "", image_urls=None):
    """Use the requested Pro model first, then a bounded Doubao Lite fallback."""
    primary_model = os.getenv("DOUBAO_MODEL", DEFAULT_DOUBAO_MODEL).strip()
    try:
        return doubao_json(
            prompt,
            system_prompt,
            image_urls=image_urls,
        ), primary_model, False
    except DoubaoTimeoutError as primary_error:
        fallback_model = os.getenv(
            "DOUBAO_FALLBACK_MODEL",
            DEFAULT_DOUBAO_FALLBACK_MODEL,
        ).strip()
        fallback_budget = float(os.getenv("DOUBAO_FALLBACK_DEADLINE_SECONDS", "120"))
        fallback_tokens = int(os.getenv("DOUBAO_FALLBACK_MAX_OUTPUT_TOKENS", "5000"))
        print(
            f"[stage-1] {primary_error}; retrying with Doubao fallback "
            f"{fallback_model} ({fallback_budget:g}s budget)..."
        )
        return doubao_json(
            prompt,
            system_prompt,
            image_urls=list(image_urls or [])[:1],
            model_override=fallback_model,
            deadline_seconds=fallback_budget,
            max_output_tokens_override=fallback_tokens,
        ), fallback_model, True


class StageOneRequest(BaseModel):
    product_url: str = ""
    campaign_theme: str = ""
    content_type: str = "真人口播带货"
    language: str = "中文"
    product_images: list = Field(default_factory=list)
    document_text: str = ""
    filter_values: dict = Field(default_factory=dict)
    resolution: str = "480p"

    @model_validator(mode="after")
    def has_source(self):
        if not any([self.product_url.strip(), self.campaign_theme.strip(), self.document_text.strip()]):
            raise ValueError("产品链接、营销主题或产品资料至少填写一项")
        return self


class StageTwoRequest(BaseModel):
    product_brief: dict = Field(default_factory=dict)
    hook: dict | str
    creative_plan: dict = Field(default_factory=dict)
    selected_plan: dict = Field(default_factory=dict)
    selected_mood_board: dict = Field(default_factory=dict)
    selected_plan_id: str = ""
    content_type: str = "真人口播带货"
    language: str = "中文"
    duration: int = 15
    filter_values: dict = Field(default_factory=dict)
    character_description: str = ""
    voice_type: str = "旁白配音"
    director_instruction: str = ""
    resolution: str = "480p"
    template_group_id: str = ""
    content_subtype: str = ""
    product_category: str = ""


class CreativePlan(BaseModel):
    plan_id: str = ""
    title: str = ""
    core_hook: str = ""
    mood_board_id: str = ""
    mood_board: str = ""
    emotion_direction: dict | str = Field(default_factory=dict)
    slogan: str = ""
    opening_method: str = ""
    rhythm_skeleton: str = ""
    visual_codes: list = Field(default_factory=list)
    director_guidance: str = ""
    must_have_elements: list = Field(default_factory=list)
    negative_rules: list = Field(default_factory=list)
    score: int = 0
    template_group_id: str = ""
    content_subtype: str = ""


def _plan_to_hook(plan: dict, index: int = 0) -> dict:
    emotion = plan.get("emotion_direction") or {}
    if isinstance(emotion, dict):
        emotion = emotion.get("primary") or emotion.get("start") or ""
    return {
        "title": plan.get("title") or plan.get("name") or f"创意方案 {index + 1}",
        "hook": plan.get("core_hook") or plan.get("hook") or plan.get("slogan") or "从产品真实差异切入",
        "hook_zh": plan.get("core_hook_zh") or plan.get("hook_zh") or "",
        "category": plan.get("category") or "完整创意方案",
        "description": plan.get("director_guidance") or plan.get("mood_board") or "",
        "emotion": emotion,
        "score": plan.get("score") or 0,
        "plan_id": plan.get("plan_id") or f"plan-{index + 1:02d}",
    }


def _hook_to_display(hook: dict, index: int, plans: list[dict], moods: list[dict]) -> dict:
    """Keep the full Hook pool while attaching a compact, reusable Mood Board summary."""
    plan_id = hook.get("plan_id") or hook.get("creative_plan_id") or ""
    plan = next((item for item in plans if item.get("plan_id") == plan_id), {})
    mood_id = hook.get("mood_board_id") or plan.get("mood_board_id") or ""
    mood = next((item for item in moods if item.get("mood_board_id") == mood_id), {})
    summary = hook.get("mood_board_summary") or hook.get("mood_board_brief") or {}
    if not summary:
        summary = {
            "name": mood.get("name") or plan.get("mood_board") or "",
            "emotion_direction": mood.get("emotion_direction") or plan.get("emotion_direction") or "",
            "palette": mood.get("palette") or [],
            "materials": mood.get("materials") or [],
            "scene": mood.get("scene_grammar") or "",
        }
    if isinstance(summary, str):
        summary = {"name": summary}
    result = dict(hook)
    result.update({
        "hook_id": hook.get("hook_id") or f"hook-{index + 1:02d}",
        "title": hook.get("title") or hook.get("name") or f"Hook {index + 1}",
        "hook": hook.get("hook") or hook.get("core_hook") or hook.get("slogan") or "从产品真实差异切入",
        "description": hook.get("description") or hook.get("reason") or hook.get("hook") or "",
        "category": hook.get("category") or "创意切入",
        "emotion": hook.get("emotion") or hook.get("emotion_direction") or "",
        "score": hook.get("score") or 0,
        "plan_id": plan_id or (plans[0].get("plan_id") if plans else ""),
        "mood_board_id": mood_id,
        "mood_board_summary": summary,
        "template_group_id": hook.get("template_group_id") or plan.get("template_group_id") or "",
        "content_subtype": hook.get("content_subtype") or plan.get("content_subtype") or "",
    })
    return result


TEMPLATE_ROUTES = {
    "真人口播带货": ("真人口播带货", "live-general-v3"),
    "好物推荐": ("好物推荐", "review-general-v3"),
    "品牌叙事TVC": ("品牌叙事TVC", "tvc-brand-v3"),
    "社媒氛围快剪TVC": ("社媒氛围快剪TVC", "tvc-social-fastcut-v3"),
    "产品材质视觉TVC": ("产品材质视觉TVC", "tvc-material-v3"),
}


def _infer_template_route(payload: dict, product_brief=None) -> tuple[str, str]:
    explicit_group = str(payload.get("template_group_id") or "").strip()
    explicit_subtype = str(payload.get("content_subtype") or "").strip()
    if explicit_group:
        return explicit_subtype, explicit_group

    for source in (payload.get("creative_plan"), payload.get("selected_plan"), payload.get("hook")):
        if not isinstance(source, dict):
            continue
        group = str(source.get("template_group_id") or "").strip()
        subtype = str(source.get("content_subtype") or "").strip()
        creative_board = source.get("creative_board") or {}
        if isinstance(creative_board, dict):
            group = group or str(creative_board.get("template_group_id") or "").strip()
            subtype = subtype or str(creative_board.get("content_subtype") or "").strip()
        if group:
            return subtype, group

    content_type = str(payload.get("content_type") or "真人口播带货").strip()
    if content_type != "高端TVC":
        return TEMPLATE_ROUTES.get(content_type, TEMPLATE_ROUTES["真人口播带货"])

    filters = payload.get("filter_values") or {}
    brief = product_brief or payload.get("product_brief") or {}
    text = " ".join(
        str(value)
        for value in (
            payload.get("campaign_theme", ""),
            filters.get("narrative", ""),
            filters.get("visual_lang", ""),
            filters.get("emotion_tone", ""),
            brief.get("summary", "") if isinstance(brief, dict) else "",
        )
    ).lower()
    if any(word in text for word in ("快剪", "氛围", "小红书", "抖音", "夏日", "少女", "穿搭", "梦幻", "社媒", "截图率")):
        return TEMPLATE_ROUTES["社媒氛围快剪TVC"]
    if any(word in text for word in ("材质", "微距", "质地", "工艺", "结构", "包装", "液体", "玻璃", "金属")):
        return TEMPLATE_ROUTES["产品材质视觉TVC"]
    return TEMPLATE_ROUTES["品牌叙事TVC"]


def _product_category(payload: dict, product_brief=None) -> str:
    explicit = str(payload.get("product_category") or "").strip()
    if explicit:
        return explicit
    brief = product_brief or payload.get("product_brief") or {}
    category = str((brief.get("category") or brief.get("category_zh") or "") if isinstance(brief, dict) else "")
    lowered = category.lower()
    if any(word in lowered for word in ("手机", "数码", "phone", "smartphone", "电子")):
        return "手机与数码"
    if any(word in lowered for word in ("美妆", "口红", "护肤", "彩妆", "beauty", "cosmetic")):
        return "美妆个护"
    if any(word in lowered for word in ("服饰", "服装", "穿搭", "配饰", "fashion", "apparel")):
        return "服饰与配饰"
    if any(word in lowered for word in ("食品", "饮料", "零食", "food", "beverage")):
        return "食品饮料"
    return category or "all"


STAGE_ONE_VISUAL_FIELDS = (
    "palette",
    "lighting",
    "materials",
    "scene_grammar",
    "character_state",
    "camera_language",
)


def _unwrap_stage_one_result(data: dict) -> dict:
    """Accept a provider's optional data/output/result wrapper without weakening the contract."""
    result = data if isinstance(data, dict) else {}
    expected_keys = {
        "product_brief", "productBrief", "creative_plans", "creativePlans",
        "mood_boards", "moodBoards", "hooks", "hooks_list", "creative_directions",
    }
    if expected_keys.intersection(result):
        return result
    for key in ("data", "output", "result"):
        candidate = result.get(key)
        if isinstance(candidate, dict) and expected_keys.intersection(candidate):
            return candidate
    return result


def _expand_creative_directions(result: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """Flatten the compact model contract into the existing frontend contract."""
    plans = [item for item in (result.get("creative_plans") or result.get("creativePlans") or []) if isinstance(item, dict)]
    moods = [item for item in (result.get("mood_boards") or result.get("moodBoards") or []) if isinstance(item, dict)]
    hooks = _merge_hook_lists(result)
    directions = [item for item in (result.get("creative_directions") or []) if isinstance(item, dict)]
    if not directions:
        return plans, moods, hooks

    plans, moods, hooks = [], [], []
    for direction_index, direction in enumerate(directions[:3], start=1):
        plan_id = direction.get("plan_id") or f"plan-{direction_index:02d}"
        mood_id = direction.get("mood_board_id") or f"mood-{direction_index:02d}"
        mood = direction.get("mood_board") or {}
        plan = direction.get("creative_plan") or {}
        if isinstance(mood, dict):
            moods.append({**mood, "mood_board_id": mood_id})
        if isinstance(plan, dict):
            plans.append({**plan, "plan_id": plan_id, "mood_board_id": mood_id})
        for hook_index, hook in enumerate(direction.get("hooks") or [], start=1):
            if not isinstance(hook, dict):
                continue
            absolute_index = (direction_index - 1) * 4 + hook_index
            hooks.append({
                **hook,
                "hook_id": hook.get("hook_id") or f"hook-{absolute_index:02d}",
                "plan_id": plan_id,
                "mood_board_id": mood_id,
            })
    return plans, moods, hooks


def _has_visual_value(value) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set)):
        return any(_has_visual_value(item) for item in value)
    if isinstance(value, dict):
        return any(_has_visual_value(item) for item in value.values())
    return value is not None and bool(value)


def _stage_one_missing_fields(data: dict) -> list[str]:
    result = _unwrap_stage_one_result(data)
    product_brief = result.get("product_brief") or result.get("productBrief")
    plans, moods, hooks = _expand_creative_directions(result)
    embedded_plans = [item.get("creative_board") for item in hooks if isinstance(item.get("creative_board"), dict)]
    embedded_moods = [item.get("mood_board") for item in hooks if isinstance(item.get("mood_board"), dict)]
    missing = []
    if not isinstance(product_brief, dict) or not product_brief:
        missing.append("product_brief")
    if not plans and not embedded_plans:
        missing.append("creative_plans")
    if not moods and not embedded_moods:
        missing.append("mood_boards")
    elif not any(any(_has_visual_value(board.get(key)) for key in STAGE_ONE_VISUAL_FIELDS) for board in (moods or embedded_moods)):
        missing.append("mood_boards.visual_fields")
    if len(hooks) < 12:
        missing.append(f"hooks(需要12条，实际{len(hooks)}条)")
    return missing


def _merge_hook_lists(data: dict) -> list[dict]:
    """Merge hooks + hooks_list without collapsing distinct hooks with similar copy."""
    hooks1 = [item for item in (data.get("hooks") or []) if isinstance(item, dict)]
    hooks2 = [item for item in (data.get("hooks_list") or []) if isinstance(item, dict)]
    if not hooks1:
        return hooks2
    if not hooks2:
        return hooks1
    # Normalized responses commonly expose the same list under both keys.
    # Return it once instead of deduplicating by text: two valid Hooks may
    # intentionally share copy while belonging to different plans/moods.
    if hooks1 == hooks2:
        return hooks1
    ids1 = [item.get("hook_id") for item in hooks1]
    ids2 = [item.get("hook_id") for item in hooks2]
    if ids1 and ids1 == ids2:
        return hooks1

    seen_ids = set()
    merged = []
    for hook in hooks1 + hooks2:
        hook_id = str(hook.get("hook_id") or "").strip()
        if hook_id:
            if hook_id in seen_ids:
                continue
            seen_ids.add(hook_id)
            merged.append(hook)
            continue
        merged.append(hook)
    return merged


def _normalize_stage_one(data: dict, payload: dict) -> dict:
    result = _unwrap_stage_one_result(data)
    plans, moods, source_hooks = _expand_creative_directions(result)
    route_subtype, route_group = _infer_template_route(payload, result.get("product_brief") or {})

    if source_hooks and not plans:
        for index, hook in enumerate(source_hooks):
            board = hook.get("creative_board")
            if not isinstance(board, dict):
                continue
            plan_id = hook.get("plan_id") or f"plan-{index + 1:02d}"
            mood_id = hook.get("mood_board_id") or f"mood-{index + 1:02d}"
            plans.append({
                **board,
                "plan_id": plan_id,
                "mood_board_id": mood_id,
                "core_hook": hook.get("core_hook") or hook.get("hook") or "",
                "template_group_id": hook.get("template_group_id") or board.get("template_group_id") or route_group,
                "content_subtype": hook.get("content_subtype") or board.get("content_subtype") or route_subtype,
            })
            hook.setdefault("plan_id", plan_id)
            hook.setdefault("mood_board_id", mood_id)
    if source_hooks and not moods:
        for index, hook in enumerate(source_hooks):
            board = hook.get("mood_board")
            if not isinstance(board, dict):
                continue
            mood_id = hook.get("mood_board_id") or f"mood-{index + 1:02d}"
            moods.append({**board, "mood_board_id": mood_id})
            hook.setdefault("mood_board_id", mood_id)

    for plan in plans:
        plan.setdefault("template_group_id", route_group)
        plan.setdefault("content_subtype", route_subtype)
    for hook in source_hooks:
        hook.setdefault("template_group_id", route_group)
        hook.setdefault("content_subtype", route_subtype)
    # Legacy Hook-only responses are intentionally not promoted into fake Mood Boards.
    # Stage 1 must receive the structured response from the Python service.
    hooks = (
        [_hook_to_display(hook, index, plans, moods) for index, hook in enumerate(source_hooks)]
        if source_hooks
        else [_plan_to_hook(plan, index) for index, plan in enumerate(plans)]
    )
    normalized = dict(result)
    normalized["mood_boards"] = moods[:12]
    normalized["creative_plans"] = plans[:12]
    normalized["recommended_plan_id"] = result.get("recommended_plan_id") or (
        normalized["creative_plans"][0].get("plan_id") if normalized["creative_plans"] else ""
    )
    normalized["hooks"] = hooks[:12]
    normalized["hooks_list"] = hooks[:12]
    return normalized


class StageThreeRequest(BaseModel):
    product_brief: dict = Field(default_factory=dict)
    hook: dict | str = Field(default_factory=dict)
    creative_plan: dict = Field(default_factory=dict)
    selected_plan: dict = Field(default_factory=dict)
    selected_mood_board: dict = Field(default_factory=dict)
    selected_plan_id: str = ""
    script_text: str = ""
    script_segments: list = Field(default_factory=list)
    content_type: str = "真人口播带货"
    duration: int = 15
    filter_values: dict = Field(default_factory=dict)
    product_record_id: str = ""
    language: str = "中文"
    director_instruction: str = ""
    resolution: str = "480p"
    template_group_id: str = ""
    content_subtype: str = ""
    product_category: str = ""


def stage_three(payload: dict) -> dict:
    script_text = payload.get("script_text") or ""
    if not script_text.strip():
        return {"ok": False, "error": "missing_script", "message": "请先生成脚本"}
    brief = payload.get("product_brief") or {}
    product_name = brief.get("product_name") or brief.get("产品名称") or ""
    content_subtype, template_group_id = _infer_template_route(payload, brief)
    product_category = _product_category(payload, brief)
    payload["content_subtype"] = content_subtype
    payload["template_group_id"] = template_group_id
    payload["product_category"] = product_category
    knowledge_context = knowledge.context(
        payload.get("content_type", ""),
        payload.get("filter_values") or {},
        product_name,
        roles=("摄影摄像",),
        top_k=4,
        max_chars=5200,
        content_subtype=content_subtype,
        product_category=product_category,
        template_group_id=template_group_id,
    )

    prompt = stage_three_prompt(payload, knowledge_context)
    sys_prompt = "You ONLY output in English. All visual descriptions must be English." if (payload.get("language") or "") in ("英文","english","en","English") else ""
    data = gemini_kie_json(prompt, sys_prompt)
    storyboard = data.get("storyboard") or []
    source_segments = payload.get("script_segments") or []
    normalized_storyboard = []
    for index, shot in enumerate(storyboard):
        item = dict(shot) if isinstance(shot, dict) else {"visual": str(shot)}
        item.setdefault("shot_id", f"S{index + 1:02d}")
        if source_segments and not item.get("source_segment_id"):
            source_index = min(index, len(source_segments) - 1)
            item["source_segment_id"] = source_segments[source_index].get("segment_id", f"SEG{source_index + 1:02d}") if isinstance(source_segments[source_index], dict) else f"SEG{source_index + 1:02d}"
        # The final video contract is subtitle-free even when a model echoes script fields.
        for key in ("subtitle", "subtitle_zh", "subtitles", "caption", "captions", "on_screen_text", "text_overlay", "text_overlays", "title_card"):
            if key in item:
                item[key] = ""
        item["no_subtitles"] = True
        no_text_rule = "No subtitles, captions, title cards, logos, watermarks, UI, screen text, or rendered words."
        item["video_prompt"] = f"{item.get('video_prompt', '')} {no_text_rule}".strip()
        normalized_storyboard.append(item)
    return {
        "ok": True,
        "storyboard": normalized_storyboard,
        "director_instruction": data.get("director_instruction") or payload.get("director_instruction") or "",
        "no_subtitles": True,
        "video_task_id": payload.get("product_record_id") or "",
        "source": "python",
        "model_provider": "gemini-kie",
        "knowledge_source": (_knowledge_trace("摄影摄像").get("source") or "unknown"),
        "knowledge_role": "摄影摄像",
        "knowledge_triggered": bool(_knowledge_trace("摄影摄像").get("api_attempted")),
        "knowledge_trace": _knowledge_trace("摄影摄像"),
        "template_group_id": template_group_id,
        "content_subtype": content_subtype,
        "product_category": product_category,
    }


def stage_one(payload: dict) -> dict:
    import time as _time
    _t0 = _time.perf_counter()
    source_parts = []
    import re

    def fetch_source():
        if not payload.get("product_url"):
            return {}
        raw = str(payload["product_url"]).strip().replace("\n", "").replace("\r", "")
        # Extract URL from mixed text like "【京东】https://item.jd.com/..."
        match = re.search(r"https?://[^\s]+", raw)
        url = match.group(0) if match else raw
        if url and not url.startswith("http"):
            url = "https://" + url
        return fetch_product_page(url) if url.startswith("http") else {}

    # 产品页面先抓取，再用标题找相关知识
    with ThreadPoolExecutor(max_workers=1) as executor:
        page_future = executor.submit(fetch_source)
        page = page_future.result()

    source_parts += [page.get("title", ""), page.get("description", ""), page.get("text", "")]
    # When crawler is blocked, tell LLM to rely on campaign theme + knowledge base
    if page.get("blocked"):
        block_reason = page.get("block_reason", "反爬拦截")
        if payload.get("campaign_theme"):
            source_parts.insert(0, f"⚠️ 产品页面无法抓取（{block_reason}）。请仅根据营销主题和知识库生成创意方案，不要虚构产品事实。")
        else:
            source_parts.insert(0, f"⚠️ 产品页面无法抓取（{block_reason}），且未提供营销主题。请生成通用创意框架，产品名留空或标注为「待补充」，不要虚构任何具体品牌或产品名。")

    if payload.get("campaign_theme"):
        source_parts.append(f"营销主题：{payload['campaign_theme']}")
    if payload.get("document_text"):
        source_parts.append(payload["document_text"])
    source_text = "\n\n".join(part for part in source_parts if part).strip()

    submitted_images = list(payload.get("product_images") or [])
    product_images = []
    invalid_images = []
    for item in submitted_images:
        image_url = (
            item.get("url") or item.get("image_url") or item.get("public_url")
            if isinstance(item, dict)
            else item
        )
        if isinstance(image_url, str) and image_url.startswith("https://"):
            product_images.append(image_url)
        else:
            invalid_images.append(image_url)
    if invalid_images:
        raise ValueError("产品图片尚未上传为公开 HTTPS URL，已停止生成，避免豆包看不到图片")
    page_image = page.get("image")
    if isinstance(page_image, str) and page_image.startswith("https://") and page_image not in product_images:
        product_images.append(page_image)
    max_image_inputs = max(1, int(os.getenv("DOUBAO_MAX_IMAGE_INPUTS", "2")))
    fact_images = product_images[:1]
    creative_images = product_images[:max_image_inputs]

    # 完整模式的第一层模型只做事实整理；快速模式用输入摘要作为 Wiki 检索线索，
    # 再由一次豆包调用完成结构化输出。两种模式都必须经过广告策划 Wiki。
    fast_mode = os.getenv("STAGE1_FAST_MODE", "1").strip() == "1"
    doubao_models_used = []
    doubao_fallback_used = False
    if fast_mode:
        # These values only help select the relevant Wiki section. Python does
        # not write creative copy or supplement facts in the fast path.
        product_facts = {
            "product_name": page.get("title", ""),
            "category": payload.get("product_category", ""),
            "summary": page.get("description", "") or str(payload.get("document_text") or "")[:800],
            "selling_points": [],
            "campaign_theme": payload.get("campaign_theme", ""),
        }
    else:
        print(f"[stage-1][{_time.perf_counter() - _t0:.1f}s] crawl done, calling Doubao #1 (product facts)...")
        product_facts, facts_model, facts_fallback = _stage_one_doubao_json(
            product_facts_prompt(payload, source_text),
            payload.get("language", "中文"),
            image_urls=fact_images,
        )
        doubao_models_used.append(facts_model)
        doubao_fallback_used = doubao_fallback_used or facts_fallback
        if not isinstance(product_facts, dict) or not product_facts:
            raise ValueError("产品事实整理返回为空，已停止 Stage 1，避免用未核实信息生成创意")
    if fast_mode:
        print(f"[stage-1][{_time.perf_counter() - _t0:.1f}s] fast mode: keeping live Wiki and using one Doubao call...")

    # 只有事实整理完成后，才用产品名、品类和核心场景查询广告策划 Wiki。
    selling_points = product_facts.get("selling_points") or product_facts.get("selling_points_zh") or []
    if isinstance(selling_points, list):
        selling_points = " ".join(str(item) for item in selling_points)
    search_term = " ".join(
        str(value).strip()
        for value in (
            product_facts.get("product_name") or product_facts.get("product_name_zh") or page.get("title", ""),
            product_facts.get("category") or product_facts.get("category_zh") or "",
            product_facts.get("summary") or product_facts.get("summary_zh") or "",
            selling_points,
            payload.get("campaign_theme", ""),
        )
        if str(value).strip()
    )
    content_subtype, template_group_id = _infer_template_route(payload, product_facts)
    product_category = _product_category(payload, product_facts)
    payload["content_subtype"] = content_subtype
    payload["template_group_id"] = template_group_id
    payload["product_category"] = product_category
    knowledge_context = knowledge.context(
        payload.get("content_type", ""),
        payload.get("filter_values") or {},
        search_term,
        roles=("广告策划",),
        top_k=3,
        max_chars=4000,
        content_subtype=content_subtype,
        product_category=product_category,
        template_group_id=template_group_id,
    )
    knowledge_meta = _knowledge_trace("广告策划")
    print(
        f"[stage-1][{_time.perf_counter() - _t0:.1f}s] "
        f"knowledge={knowledge_meta.get('source')} "
        f"wiki_docs={knowledge_meta.get('wiki_document_count', 0)} "
        f"cards={knowledge_meta.get('card_ids') or []} "
        f"images={len(creative_images)}/{len(product_images)}"
    )
    print(f"[stage-1][{_time.perf_counter() - _t0:.1f}s] calling Doubao creative model...")
    # Stage 1 uses Doubao Responses for faster multimodal product understanding.
    # Both factual extraction and creative planning use the same Doubao channel.
    # Stage 2/3 remain on the existing Gemini-KIE path for now.
    creative_prompt = stage_one_prompt(
        payload,
        source_text,
        knowledge_context,
        {} if fast_mode else product_facts,
    )
    data, creative_model, creative_fallback = _stage_one_doubao_json(
        creative_prompt,
        image_urls=creative_images,
    )
    doubao_models_used.append(creative_model)
    doubao_fallback_used = doubao_fallback_used or creative_fallback
    print(f"[stage-1][{_time.perf_counter() - _t0:.1f}s] Doubao creative model done, normalizing...")
    data = _normalize_stage_one(data, payload)
    if fast_mode:
        # The one-pass response's product brief is the factual contract for
        # this latency-sensitive path; it is still produced by Doubao and is
        # never supplemented with invented values in Python.
        product_facts = dict(data.get("product_brief") or {})
    generated_brief = dict(data.get("product_brief") or {})
    for key, value in product_facts.items():
        if value and not generated_brief.get(key):
            generated_brief[key] = value
    data["product_brief"] = generated_brief
    data["product_facts"] = product_facts

    # Retry: if hooks < 12, ask model to fill in the missing ones
    hooks_after_merge = _merge_hook_lists(data)
    if len(hooks_after_merge) < 12 and not fast_mode:
        existing_hooks_json = json.dumps(hooks_after_merge, ensure_ascii=False, indent=2)
        fixup_prompt = (
            f"你上次生成的 hooks 数组只有 {len(hooks_after_merge)} 条，需要恰好 12 条。\n"
            f"请基于以下已有 Hook，补充到恰好 12 条，保持风格、质量和字段结构一致。\n"
            f"已有的 {len(hooks_after_merge)} 条 Hook：\n"
            f"{existing_hooks_json}\n\n"
            f"要求：\n"
            f"1. 保留所有已有 Hook，补充缺失的 hook_id（用 hook-09 到 hook-12 等未使用的 ID）\n"
            f"2. 补充的 Hook 风格和质量必须与已有的一致\n"
            f"3. 按 Mood Board 对应：每个 mood_board_id 应有 4 条 Hook\n\n"
            f"只返回 JSON：{{\"hooks\": [...]}}，hooks 数组必须恰好包含 12 条完整的 Hook 对象。"
        )
        try:
            print(f"[stage-1] retrying: need 12 hooks, got {len(hooks_after_merge)}")
            fixup_data = doubao_json(fixup_prompt)
            fixup_hooks = [item for item in (_merge_hook_lists(fixup_data)) if isinstance(item, dict)]
            if len(fixup_hooks) >= len(hooks_after_merge):
                # Replace hooks in data with fixup result
                data["hooks"] = fixup_hooks
                data["hooks_list"] = fixup_hooks
                data = _normalize_stage_one(data, payload)
                data["product_brief"] = generated_brief
                data["product_facts"] = product_facts
                hooks_after_merge = _merge_hook_lists(data)
                print(f"[stage-1] retry result: {len(hooks_after_merge)} hooks")
        except Exception as retry_error:
            print(f"[stage-1] retry failed: {retry_error}")

    missing = _stage_one_missing_fields(data)
    if missing:
        returned_keys = ", ".join(sorted(_unwrap_stage_one_result(data).keys())) or "无"
        # Soft-fail: if only missing hooks and we have >= 8, proceed with warning
        hooks_only_missing = all(m.startswith("hooks(") for m in missing)
        if hooks_only_missing and len(hooks_after_merge) >= 8:
            print(f"[stage-1] WARNING: only {len(hooks_after_merge)}/12 hooks, proceeding anyway; keys={returned_keys}")
        else:
            message = (
                "模型结构化输出不完整，缺少："
                + "、".join(missing)
                + "。模型返回字段："
                + returned_keys
            )
            print(f"[stage-1] rejected response: missing={missing}; keys={returned_keys}")
            raise ValueError(message)
    plans = data.get("creative_plans") or []
    hooks = data.get("hooks") or []
    print(f"[stage-1][{_time.perf_counter() - _t0:.1f}s] done: {len(plans)} plans, {len(hooks)} hooks, {len(data.get('mood_boards') or [])} moods")
    return {
        "ok": True,
        "product_record_id": f"python-{uuid.uuid4().hex[:16]}",
        "product_main_image_url": (payload.get("product_images") or [page.get("image", "")])[0],
        "product_brief": data.get("product_brief") or {},
        "product_facts": data.get("product_facts") or {},
        "mood_boards": data.get("mood_boards") or [],
        "creative_plans": plans,
        "recommended_plan_id": data.get("recommended_plan_id") or plans[0].get("plan_id", ""),
        "hooks": hooks,
        "hooks_list": hooks,
        "source": "python",
        "model_provider": "doubao-responses",
        "product_facts_provider": "doubao-responses",
        "model_name": doubao_models_used[-1] if doubao_models_used else "",
        "doubao_fallback_used": doubao_fallback_used,
        "image_inputs_received": len(product_images),
        "image_inputs_sent": len(creative_images),
        "image_vision_used": bool(creative_images),
        "knowledge_source": (_knowledge_trace("广告策划").get("source") or "unknown"),
        "knowledge_role": "广告策划",
        "knowledge_triggered": bool(_knowledge_trace("广告策划").get("api_attempted")),
        "knowledge_trace": _knowledge_trace("广告策划"),
        "crawler_blocked": page.get("blocked", False),
        "crawler_block_reason": page.get("block_reason", "") if page.get("blocked") else "",
        "pipeline_trace": {
            "order": [
                "crawler",
                *(["planning_knowledge_wiki", "doubao_responses_fast_stage1_model"] if fast_mode else [
                    "doubao_responses_product_facts_model",
                    "planning_knowledge_wiki",
                    "doubao_responses_creative_model",
                ]),
            ],
            "crawler_completed": bool(page or source_text),
            "product_facts_completed": bool(product_facts),
            "fast_mode": fast_mode,
            "doubao_models_used": doubao_models_used,
            "doubao_fallback_used": doubao_fallback_used,
            "knowledge_trace": _knowledge_trace("广告策划"),
        },
        "template_group_id": template_group_id,
        "content_subtype": content_subtype,
        "product_category": product_category,
    }


def stage_two(payload: dict) -> dict:
    brief = payload.get("product_brief") or {}
    product_name = brief.get("product_name") or brief.get("产品名称") or ""
    content_subtype, template_group_id = _infer_template_route(payload, brief)
    product_category = _product_category(payload, brief)
    payload["content_subtype"] = content_subtype
    payload["template_group_id"] = template_group_id
    payload["product_category"] = product_category
    knowledge_context = knowledge.context(
        payload.get("content_type", ""),
        payload.get("filter_values") or {},
        product_name,
        roles=("编剧导演",),
        top_k=4,
        max_chars=5200,
        content_subtype=content_subtype,
        product_category=product_category,
        template_group_id=template_group_id,
    )
    is_en = (payload.get("language") or "") in ("英文","english","en","English")
    if is_en:
        payload["duration"] = 8  # English always 8s
    prompt = stage_two_prompt(payload, knowledge_context)
    if is_en:
        provider = "deepseek"
        data = chat_json(prompt, payload.get("language",""))  # DeepSeek for English
    else:
        provider = "gemini-kie"
        data = gemini_kie_json(prompt)
    return {
        "ok": True,
        "script_text": data.get("script_text") or "",
        "script_text_zh": data.get("script_text_zh") or "",
        "director_instruction": data.get("director_instruction") or "",
        "script_segments": data.get("script_segments") or data.get("storyboard") or [],
        "source": "python",
        "model_provider": provider,
        "knowledge_source": (_knowledge_trace("编剧导演").get("source") or "unknown"),
        "knowledge_role": "编剧导演",
        "knowledge_triggered": bool(_knowledge_trace("编剧导演").get("api_attempted")),
        "knowledge_trace": _knowledge_trace("编剧导演"),
        "template_group_id": template_group_id,
        "content_subtype": content_subtype,
        "product_category": product_category,
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send(
                200,
                {
                    "ok": True,
                    "service": "adflow-python",
                    "knowledge_reader": "wiki-only-v3",
                    "knowledge_roles": ["广告策划", "编剧导演", "摄影摄像"],
                    "stage1_fast_mode": os.getenv("STAGE1_FAST_MODE", "1").strip() == "1",
                    "doubao_stream": os.getenv("DOUBAO_STREAM", "1").strip() != "0",
                    "doubao_model": os.getenv("DOUBAO_MODEL", DEFAULT_DOUBAO_MODEL),
                    "doubao_fallback_model": os.getenv(
                        "DOUBAO_FALLBACK_MODEL",
                        DEFAULT_DOUBAO_FALLBACK_MODEL,
                    ),
                },
            )
        elif parsed.path == "/knowledge/status":
            force = parse_qs(parsed.query).get("force", ["0"])[0].lower() in ("1", "true", "yes")
            self._send(200, {"ok": True, **knowledge.status(force=force)})
        elif parsed.path == "/knowledge/filters":
            content_type = parse_qs(parsed.query).get("content_type", ["真人口播带货"])[0]
            self._send(200, {"ok": True, **knowledge.filter_schema(content_type)})
        else:
            self._send(404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 40 * 1024 * 1024:
                raise ValueError("请求内容超过 40MB")
            payload = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/stage-1":
                request = StageOneRequest.model_validate(payload)
                result = stage_one(request.model_dump())
            elif self.path == "/stage-2":
                request = StageTwoRequest.model_validate(payload)
                result = stage_two(request.model_dump())
            elif self.path == "/stage-3":
                request = StageThreeRequest.model_validate(payload)
                result = stage_three(request.model_dump())
            elif self.path == "/mirror-video":
                result = mirror_video_to_tos(
                    payload.get("video_url", ""),
                    payload.get("filename", ""),
                )
            elif self.path == "/media/align-subtitles":
                output_dir = Path(os.getenv(
                    "MEDIA_OUTPUT_DIR",
                    Path(__file__).resolve().parents[1] / "frontend" / "generated" / "edits",
                ))
                result = align_subtitles(payload, output_dir)
            elif self.path == "/media/edit":
                output_dir = Path(os.getenv(
                    "MEDIA_OUTPUT_DIR",
                    Path(__file__).resolve().parents[1] / "frontend" / "generated" / "edits",
                ))
                result = render_edit(payload, output_dir)
            elif self.path in ("/media/jianying-package", "/media/chatcut-handoff"):
                output_dir = Path(os.getenv(
                    "MEDIA_OUTPUT_DIR",
                    Path(__file__).resolve().parents[1] / "frontend" / "generated" / "edits",
                ))
                target = "jianying" if self.path.endswith("jianying-package") else "chatcut"
                result = export_editing_handoff(payload, output_dir, target)
            elif self.path == "/providers/kie/character":
                result = create_image_task("character", payload)
            elif self.path == "/providers/kie/storyboard":
                result = create_image_task("storyboard", payload)
            elif self.path == "/providers/kie/overseas-video":
                result = create_overseas_video_task(payload)
            elif self.path == "/providers/kie/kling-video":
                result = create_kling_video_task(payload)
            elif self.path == "/providers/kie/status":
                result = query_task(payload)
            elif self.path == "/providers/topaz/enhance":
                result = create_enhancement_task(payload)
            elif self.path == "/providers/minimax/music":
                result = generate_music(payload)
            elif self.path == "/providers/topaz/status":
                result = query_enhancement_task(payload)
            else:
                self._send(404, {"ok": False, "error": "not_found"})
                return
            self._send(200, result)
        except ValidationError as error:
            self._send(422, {"ok": False, "error": "validation_error", "message": str(error)})
        except Exception as error:
            status = 503 if "API_KEY" in str(error) else 500
            self._send(status, {"ok": False, "error": "service_error", "message": str(error)})

    def log_message(self, message, *args):
        print(f"[python-service] {self.address_string()} {message % args}")


def main():
    host = os.getenv("PYTHON_SERVICE_HOST", "127.0.0.1")
    port = int(os.getenv("PYTHON_SERVICE_PORT", "8787"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Python service ready on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
