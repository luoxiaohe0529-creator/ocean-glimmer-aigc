import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

import httpx
from dotenv import load_dotenv


# 允许知识模块被单独导入时也读取项目 .env；服务入口会重复调用一次，但不会覆盖已存在的环境变量。
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


DEFAULT_FILTERS = {
    "真人口播带货": [
        {"id": "creator_vibe", "label": "达人气质", "options": ["邻家亲和", "专业可信", "知性优雅", "活力元气"]},
        {"id": "speaking_style", "label": "表达方式", "options": ["闺蜜聊天", "专业讲解", "沉稳叙述", "轻松种草"]},
        {"id": "use_scene", "label": "使用场景", "options": ["早晨护肤", "化妆台前", "日常通勤", "睡前护理"]},
    ],
    "好物推荐": [
        {"id": "selling_angle", "label": "推荐切入", "options": ["成分科技", "功效实测", "设计美学", "使用体验"]},
        {"id": "compare_dim", "label": "比较维度", "options": ["竞品对比", "升级前后", "有无对比", "多款横评"]},
        {"id": "visual_style", "label": "展示方式", "options": ["极简白底", "微距特写", "数据图叠层", "生活场景"]},
    ],
    "高端TVC": [
        {"id": "emotion_tone", "label": "情绪基调", "options": ["克制诗意", "温暖治愈", "冷峻高级", "复古怀旧"]},
        {"id": "visual_lang", "label": "视觉语言", "options": ["暖金逆光", "慢镜头", "浅景深", "对称构图"]},
        {"id": "narrative", "label": "叙事结构", "options": ["时间流转", "意象隐喻", "人物独白", "场景切换"]},
    ],
}


@dataclass(frozen=True)
class WikiConfig:
    role: str
    node_token: str
    title_hint: str


# M7v... 是知识库首页；三个子文档是三个阶段的唯一知识来源。
# 运行时不读取、也不依赖飞书多维表格的知识字段。
WIKIS = (
    WikiConfig("广告策划", os.getenv("FEISHU_PLANNING_WIKI_TOKEN", ""), "广告策划知识库"),
    WikiConfig("编剧导演", os.getenv("FEISHU_DIRECTOR_WIKI_TOKEN", ""), "编剧导演知识库"),
    WikiConfig("摄影摄像", os.getenv("FEISHU_CAMERA_WIKI_TOKEN", ""), "摄影摄像知识库"),
)


# 这是 Wiki 暂时不可用时的本地安全契约，不是外部知识源。
# 正常运行时，三份 Wiki 正文会覆盖这些默认契约并进入阶段提示词。
DEFAULT_KNOWLEDGE_CARDS = {
    "广告策划": [
        {
            "card_id": "planning-mood-board-v1",
            "card_type": "mood_board_rule",
            "name": "产品气质到 Mood Board 的映射",
            "tags": "夏天；少女；年轻女性；清凉；海边；旅行；度假；高颜值；通透；松弛",
            "emotion_direction": "先让人感到，再让人理解：视觉降温感 → 出行向往感 → 种草占有欲",
            "mood_board": "从产品颜色、材质、使用场景和目标人群抽取色彩、光线、材质、人物状态、场景底色与镜头语法；产品是视觉主角，场景只负责放大产品气质。",
            "slogan_rule": "Slogan 要把产品差异转译成可感知的生活画面，不写参数，不写空泛口号；优先使用‘把某种生活感带在身边’这类占有心智结构。",
            "creative_plan_rule": "每个创意方案必须完整包含：核心 Hook、Mood Board、情绪方向、Slogan、开篇方式、节奏骨架、视觉密码、导演指导、必备元素、禁止事项。",
            "negative_rules": "避免硬件参数广告；避免纯风景空镜；避免静止产品展示；避免没有人物关系的素材堆砌；不得凭空补写产品事实。",
        },
        {
            "card_id": "planning-creative-pool-v1",
            "card_type": "creative_plan_pool",
            "name": "完整创意方案池输出契约",
            "tags": "创意方案池；核心Hook；Mood Board；情绪方向；Slogan；开篇方式；节奏骨架；视觉密码；导演指导",
            "pool_size": "一次生成 3 个可比较方案，分别承担情绪优先、场景优先、产品差异优先；推荐其中 1 个作为默认方案。",
            "opening_methods": "气泡叙事；水珠叙事；光影叙事；触感叙事；声音叙事；根据产品材质与场景选择，不机械随机。",
            "rhythm_skeletons": "三拍子；极速跳切；碎片化快剪；渐强；以时长、平台和产品气质为依据。",
            "visual_codes": "颜色进化；材质贯穿；光影时序；水、玻璃、织物、金属等可复用材质母题。",
            "director_guidance": "指导 Stage 2 如何把方案转成叙事、人物动作、台词节奏和镜头任务；不直接代替 Stage 2 写完整分镜。",
        },
    ],
    "编剧导演": [
        {
            "card_id": "director-storyboard-v1",
            "card_type": "director_contract",
            "name": "编剧导演阶段知识卡",
            "tags": "脚本；导演；叙事动线；人物动作；口播；字幕；段落节奏",
            "director_role": "把已选创意方案变成可拍摄的完整视频脚本：先确定情绪弧线，再安排人物关系、产品出现节点、口播与字幕，不重写产品事实。",
            "narrative_flow": "开头建立冲突或好奇 → 中段用人物行为证明产品差异 → 后段完成情绪升华与自然行动引导；每个镜头都要推进叙事或完成信息交付。",
            "movement_constraints": "严格遵守方案中的开篇方式、节奏骨架、视觉密码和必备元素；场景作为叙事底色，不写没有人物或产品关系的风景空镜。",
            "output_contract": "返回 script_text 与 script_segments；每段包含时间、画面、运镜意图、对白、字幕、音乐音效和给摄影摄像的 video_prompt。",
            "safety": "不虚构参数、功效、地点背书或竞品事实；不使用用户明确禁止的词与营销话术；品牌名和产品事实只按输入资料使用。",
        },
    ],
    "摄影摄像": [
        {
            "card_id": "camera-generation-v1",
            "card_type": "camera_contract",
            "name": "摄影摄像阶段知识卡",
            "tags": "摄影；运镜；影调；视觉焦点；材质；视频生成；安全策略",
            "camera_role": "把脚本和 Mood Board 翻译成可执行的镜头参数与视频生成提示词，保证产品身份、人物连续性、色彩和材质统一。",
            "shot_rules": "明确景别、主体、动作、光线、材质、构图和运镜；镜头时长服从脚本与平台节奏；特写、中近景、全景有意识跳跃。",
            "visual_focus": "每个镜头只设一个视觉焦点；产品背板、人物动作或关键材质必须写清楚，场景不能抢走产品叙事。",
            "look": "先锁定 Mood Board 的主色、辅助色、光线方向、对比度、景深、质感和时间段，再写具体镜头；不要用空泛的‘高级、唯美’代替可拍摄描述。",
            "generation_prompt": "video_prompt 使用英文，包含主体与动作、环境、光线、色彩、材质、镜头、运动、画幅和连续性约束；禁止出现屏幕、系统界面、其他电子产品或品牌 Logo，除非输入明确允许。",
            "safety": "不生成不真实的产品结构；不拍正面屏幕和 UI；不添加输入中没有的功能与标识；避免手指、文字、Logo、产品颜色在镜头间漂移。",
        },
    ],
}


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "；".join(filter(None, (_text(item) for item in value)))
    if isinstance(value, dict):
        for key in ("text", "name", "value"):
            if key in value:
                return _text(value[key])
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _split_options(value: str) -> list[str]:
    normalized = value.replace("\n", "；").replace("、", "；").replace("|", "；")
    options = []
    for part in normalized.split("；"):
        clean = part.strip(" ，。:：-")
        if 1 < len(clean) <= 28 and clean not in options:
            options.append(clean)
    return options


FILTER_LABEL_ALIASES = {
    "creator_vibe": ("creator_vibe", "达人气质"),
    "speaking_style": ("speaking_style", "表达方式", "说话风格"),
    "use_scene": ("use_scene", "使用场景"),
    "selling_angle": ("selling_angle", "推荐切入"),
    "compare_dim": ("compare_dim", "比较维度"),
    "visual_style": ("visual_style", "展示方式"),
    "emotion_tone": ("emotion_tone", "情绪基调"),
    "visual_lang": ("visual_lang", "视觉语言"),
    "narrative": ("narrative", "叙事结构"),
}


def _wiki_filter_options(rows: list[dict], filter_id: str) -> list[str]:
    """Extract only explicitly labelled option lines from Wiki prose.

    Wiki documents are prose, not Base rows. Do not turn arbitrary sentences
    into filter values; only a known filter label may open an option block.
    """
    aliases = FILTER_LABEL_ALIASES.get(filter_id, ())
    if not aliases:
        return []
    label_pattern = "|".join(re.escape(alias) for alias in aliases)
    label_sequence = rf"(?:{label_pattern})(?:\s+(?:{label_pattern}))*"
    pattern = re.compile(
        rf"^\s*(?:[-*#>\d.、\s]*)?{label_sequence}\s*(?:[:：=])\s*(.*)$",
        re.IGNORECASE,
    )
    options: list[str] = []
    for row in rows:
        text = _text(row.get("knowledge_text"))
        if not text:
            continue
        text = re.sub(r"<[^>]+>", " ", text)
        lines = [line.strip() for line in text.splitlines()]
        for index, line in enumerate(lines):
            match = pattern.match(line)
            if not match:
                continue
            values = [match.group(1)] if match.group(1).strip() else []
            for next_line in lines[index + 1:]:
                if not next_line:
                    if values:
                        break
                    continue
                if re.match(r"^\s*(?:#{1,6}\s*|\d+[.、]\s*|<h\d)", next_line, re.IGNORECASE):
                    break
                if re.match(rf"^\s*(?:[-*#>\d.、\s]*)?{label_sequence}\s*(?:[:：=])", next_line, re.IGNORECASE):
                    break
                if values and not next_line.startswith(("-", "*", "•")):
                    break
                values.append(next_line.lstrip("-*• "))
            for value in values:
                for option in re.split(r"[，,、；;|/]+", value):
                    clean = option.strip(" ，。:：-()（）")
                    if 1 < len(clean) <= 28 and clean not in options:
                        options.append(clean)
    return options[:12]


def _parse_wiki_cards(content: str, config: WikiConfig, node: dict, obj_token: str) -> list[dict]:
    """Split copy-paste-friendly CARD_START blocks into runtime knowledge cards."""
    blocks = re.findall(r"(?ms)^\s*CARD_START\s*$\n?(.*?)^\s*CARD_END\s*$", content)
    if not blocks:
        return [{
            "record_id": f"wiki:{config.node_token}",
            "role": config.role,
            "card_id": f"wiki-{config.role}",
            "wiki_node_token": config.node_token,
            "wiki_obj_token": obj_token,
            "name": node.get("title") or config.title_hint,
            "knowledge_text": content,
        }]

    cards = []
    for index, block in enumerate(blocks, start=1):
        fields = {}
        current_key = ""
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            match = re.match(r"^([A-Za-z][A-Za-z0-9_]*)\s*:\s*(.*)$", line)
            if match:
                current_key = match.group(1)
                fields[current_key] = match.group(2).strip()
            elif current_key:
                fields[current_key] = f"{fields[current_key]} {line}".strip()
        card_id = fields.get("card_id") or f"wiki-{config.role}-{index:02d}"
        cards.append({
            "record_id": f"wiki:{config.node_token}:{card_id}",
            "role": config.role,
            "card_id": card_id,
            "wiki_node_token": config.node_token,
            "wiki_obj_token": obj_token,
            "name": fields.get("name") or card_id,
            "knowledge_text": block.strip(),
            **fields,
        })
    return cards


class FeishuKnowledge:
    def __init__(self):
        self.app_id = os.getenv("FEISHU_APP_ID", "").strip()
        self.app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
        self.base_url = os.getenv("FEISHU_API_BASE_URL", "https://open.feishu.cn/open-apis").rstrip("/")
        self.cache_seconds = int(os.getenv("FEISHU_KNOWLEDGE_CACHE_SECONDS", "300"))
        self._cache: dict[str, list[dict]] = {}
        self._cache_at: dict[str, float] = {}
        self._lock = Lock()
        self.last_context_meta: dict = {}

    @property
    def configured(self) -> bool:
        return self.configured_for()

    def configured_for(self, roles=None) -> bool:
        wiki_configs = self._wiki_configs(roles)
        return bool(
            self.app_id
            and self.app_secret
            and wiki_configs
            and all(config.node_token for config in wiki_configs)
        )

    def source_for(self, roles=None) -> str:
        wiki_configs = self._wiki_configs(roles)
        if self.app_id and self.app_secret and wiki_configs and all(config.node_token for config in wiki_configs):
            return "wiki"
        return "fallback"

    def _tenant_token(self, client: httpx.Client) -> str:
        response = client.post(
            f"{self.base_url}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code", 0) != 0:
            raise RuntimeError(payload.get("msg") or "飞书应用鉴权失败")
        return payload["tenant_access_token"]

    def _wiki_configs(self, roles=None) -> list[WikiConfig]:
        if roles is None:
            return list(WIKIS)
        wanted = set(roles if isinstance(roles, (list, tuple, set)) else [roles])
        return [config for config in WIKIS if config.role in wanted]

    def _wiki_document_text(self, client: httpx.Client, token: str, config: WikiConfig) -> list[dict]:
        node_response = client.get(
            f"{self.base_url}/wiki/v2/spaces/get_node",
            headers={"Authorization": f"Bearer {token}"},
            params={"token": config.node_token},
        )
        node_response.raise_for_status()
        node_payload = node_response.json()
        if node_payload.get("code", 0) != 0:
            raise RuntimeError(f"{config.role} Wiki：{node_payload.get('msg') or '节点读取失败'}")
        node = (node_payload.get("data") or {}).get("node") or {}
        obj_token = node.get("obj_token") or ""
        if not obj_token:
            raise RuntimeError(f"{config.role} Wiki：节点没有可读取的文档对象")

        raw_response = client.get(
            f"{self.base_url}/docx/v1/documents/{obj_token}/raw_content",
            headers={"Authorization": f"Bearer {token}"},
        )
        raw_response.raise_for_status()
        raw_payload = raw_response.json()
        if raw_payload.get("code", 0) != 0:
            raise RuntimeError(f"{config.role} Wiki：正文读取失败：{raw_payload.get('msg') or '未知错误'}")
        content = ((raw_payload.get("data") or {}).get("content") or "").strip()
        if not content:
            raise RuntimeError(f"{config.role} Wiki：正文为空，未将空文档当作知识库命中")
        return _parse_wiki_cards(content, config, node, obj_token)

    def _wiki_records_for(self, roles=None, force=False) -> dict[str, list[dict]]:
        configs = self._wiki_configs(roles)
        if not self.app_id or not self.app_secret or not configs or not all(config.node_token for config in configs):
            return {}
        now = time.time()
        keys = [config.role for config in configs]
        if not force and all(key in self._cache and now - self._cache_at.get(key, 0) < self.cache_seconds for key in keys):
            return {key: self._cache[key] for key in keys}
        with self._lock:
            now = time.time()
            if not force and all(key in self._cache and now - self._cache_at.get(key, 0) < self.cache_seconds for key in keys):
                return {key: self._cache[key] for key in keys}
            with httpx.Client(timeout=20.0) as client:
                token = self._tenant_token(client)
                result = {}
                for config in configs:
                    result[config.role] = self._wiki_document_text(client, token, config)
                    self._cache[config.role] = result[config.role]
                    self._cache_at[config.role] = now
            return result

    def records_for(self, roles=None, force=False) -> dict[str, list[dict]]:
        if not self.configured_for(roles):
            return {}
        return self._wiki_records_for(roles, force=force)

    def status(self, force=False) -> dict:
        """Return a safe, content-free read status for every Wiki role."""
        roles = [config.role for config in WIKIS]
        role_status = {}
        for role in roles:
            configured = self.configured_for((role,))
            item = {
                "configured": configured,
                "read_ok": False,
                "source": "fallback",
                "document_count": 0,
                "card_ids": [],
                "names": [],
                "error": "",
            }
            if not configured:
                item["error"] = "缺少飞书应用凭证或该角色 Wiki Token"
                role_status[role] = item
                continue
            try:
                records = self.records_for((role,), force=force)
                rows = records.get(role, [])
                item.update({
                    "read_ok": bool(rows),
                    "source": "wiki" if rows else "fallback",
                    "document_count": len(rows),
                    "card_ids": [
                        _text(row.get("card_id")) or _text(row.get("record_id"))
                        for row in rows
                        if _text(row.get("card_id")) or _text(row.get("record_id"))
                    ],
                    "names": [_text(row.get("name")) for row in rows if _text(row.get("name"))],
                })
                if not rows:
                    item["error"] = "Wiki 返回空正文"
            except Exception as error:
                item["error"] = str(error)
            role_status[role] = item
        read_ok = all(item["read_ok"] for item in role_status.values()) if role_status else False
        return {
            "reader": "wiki-only-v3",
            "source": "wiki" if read_ok else "partial-or-fallback",
            "read_ok": read_ok,
            "roles": role_status,
        }

    def _default_rows(self, roles=None) -> dict[str, list[dict]]:
        wanted = set(roles if isinstance(roles, (list, tuple, set)) else [roles]) if roles else set(DEFAULT_KNOWLEDGE_CARDS)
        return {
            role: [dict(card, role=role) for card in cards]
            for role, cards in DEFAULT_KNOWLEDGE_CARDS.items()
            if role in wanted
        }

    def filter_schema(self, content_type: str) -> dict:
        defaults = [dict(item) for item in DEFAULT_FILTERS.get(content_type, DEFAULT_FILTERS["真人口播带货"])]
        role_map = {
            "真人口播带货": ("广告策划", "编剧导演"),
            "好物推荐": ("广告策划", "摄影摄像"),
            "高端TVC": ("编剧导演", "摄影摄像"),
        }
        selected_roles = role_map.get(content_type, role_map["真人口播带货"])
        try:
            records = self.records_for(selected_roles)
        except Exception as error:
            source = self.source_for(selected_roles)
            return {
                "source": "fallback" if source == "fallback" else f"{source}+error",
                "configured": self.configured_for(selected_roles),
                "filters": defaults,
                "message": str(error),
            }
        if not records or not any(records.values()):
            source = self.source_for(selected_roles)
            return {
                "source": "fallback" if source == "fallback" else f"{source}+empty",
                "configured": self.configured_for(selected_roles),
                "filters": defaults,
            }
        merged_rows = [row for role_rows in records.values() for row in role_rows]
        for definition in defaults:
            options = _wiki_filter_options(merged_rows, definition["id"])
            if options:
                definition["options"] = options[:12]
            definition["knowledge_field"] = "Wiki正文"
        return {
            "source": self.source_for(selected_roles),
            "configured": True,
            "filters": defaults,
        }

    def context(
        self,
        content_type: str,
        filter_values: dict,
        product_name="",
        roles=None,
        top_k=5,
        max_chars=6500,
        content_subtype="",
        product_category="",
        template_group_id="",
    ) -> str:
        selected_roles = list(roles) if roles else [config.role for config in WIKIS]
        configured = self.configured_for(selected_roles)
        api_attempted = configured
        api_read_ok = False
        api_error = ""
        try:
            records = self.records_for(selected_roles)
            api_read_ok = configured
        except Exception as error:
            records = {}
            api_error = str(error)
        # 默认卡是兜底契约；飞书实际记录只会增加产品/团队特定规则。
        merged = self._default_rows(selected_roles)
        for role, rows in records.items():
            merged.setdefault(role, []).extend(rows)
        if not merged:
            self.last_context_meta = {
                "api_attempted": api_attempted,
                "api_read_ok": api_read_ok,
                "wiki_document_count": 0,
                "source": "empty",
                "fallback_used": False,
                "error": api_error,
                "roles": selected_roles,
                "card_ids": [],
            }
            return ""

        needles = [
            content_type,
            content_subtype,
            product_category,
            template_group_id,
            product_name,
        ] + [_text(value) for value in (filter_values or {}).values()]
        needles = [item.lower() for item in needles if item]
        # Also match by role name so cards for the right role always get some score
        role_names = [role for role in merged.keys()]
        configured_source = self.source_for(selected_roles)
        scored = []
        actual_record_ids = {
            _text(row.get("record_id"))
            for role_rows in records.values()
            for row in role_rows
            if _text(row.get("record_id"))
        }
        for role, rows in merged.items():
            for row in rows:
                searchable = " ".join(_text(value) for value in row.values()).lower()
                score = sum(1 for needle in needles if needle in searchable)
                row_group = _text(row.get("template_group_id")).lower()
                row_type = _text(row.get("content_type")).lower()
                row_subtype = _text(row.get("content_subtype")).lower()
                row_category = _text(row.get("product_category")).lower()
                wanted_group = _text(template_group_id).lower()
                wanted_type = _text(content_type).lower()
                wanted_subtype = _text(content_subtype).lower()
                wanted_category = _text(product_category).lower()
                is_wiki_row = _text(row.get("record_id")) in actual_record_ids
                is_category_patch = _text(row.get("card_type")).lower() == "category_patch"

                # A selected template group is a hard stage-to-stage contract.
                # Other master templates must not leak into the prompt merely
                # because every fetched Wiki card is authoritative.
                if wanted_group and row_group and row_group != wanted_group:
                    continue
                # V3 routing deliberately ignores legacy ungrouped Wiki cards.
                # The only ungrouped cards allowed beside a master template are
                # explicit category patches for the selected product category.
                if wanted_group and is_wiki_row and not row_group and not (
                    is_category_patch and wanted_category and row_category == wanted_category
                ):
                    continue
                if wanted_type and row_type and row_type not in ("all", wanted_type):
                    continue
                if wanted_subtype and row_subtype and row_subtype != wanted_subtype:
                    continue
                if wanted_category and row_category and row_category not in ("all", wanted_category):
                    continue

                if wanted_group and row_group == wanted_group:
                    score += 10000
                if wanted_subtype and row_subtype == wanted_subtype:
                    score += 2000
                if wanted_type and row_type == wanted_type:
                    score += 500
                if wanted_category and row_category == wanted_category:
                    score += 1000
                # Bonus for matching tags (not role names - role is just a label)
                tags = (row.get("tags") or "").lower()
                for needle in needles:
                    if len(needle) >= 2 and needle in tags:
                        score += 1
                # Wiki documents are the authoritative role contract. Always keep
                # the fetched document ahead of built-in cards, even when its prose
                # does not repeat the selected product/filter keywords.
                if configured_source == "wiki" and is_wiki_row:
                    score += 100
                # Only include cards that match actual content (product name, content type, etc.)
                if score == 0:
                    continue
                scored.append((score, role, row))
        scored.sort(key=lambda item: (-item[0], item[1], _text(item[2].get("card_id"))))
        # 筛选器只决定排序，不应让某个已请求的角色完全没有上下文。
        # 每个角色至少保留一张最小知识卡，避免 Stage 2/3 因关键词未命中而退化成通用提示。
        matched_roles = {role for _, role, _ in scored}
        for role in role_names:
            if role in matched_roles or not merged.get(role):
                continue
            # 真实 Wiki 文档优先于内置默认卡，避免“读到了文档但实际喂给模型的是默认卡”。
            fallback_row = (
                records.get(role, [None])[0]
                or next((row for row in merged[role] if row.get("card_type")), merged[role][0])
            )
            scored.append((0, role, fallback_row))
        scored.sort(key=lambda item: (-item[0], item[1], _text(item[2].get("card_id"))))
        blocks = []
        selected_rows = []
        for _, role, row in scored[:top_k]:
            selected_rows.append(row)
            details = [
                f"{key}：{value}"
                for key, value in row.items()
                if key not in ("record_id", "role", "card_id") and value
            ]
            blocks.append(f"【{role}知识卡】" + "；".join(details))
        wiki_document_count = sum(len(rows) for rows in records.values())
        card_ids = [
            _text(row.get("card_id")) or _text(row.get("record_id"))
            for row in selected_rows
            if _text(row.get("card_id")) or _text(row.get("record_id"))
        ]
        source = "wiki" if api_read_ok and wiki_document_count else "fallback"
        self.last_context_meta = {
            "api_attempted": api_attempted,
            "api_read_ok": api_read_ok,
            "wiki_document_count": wiki_document_count,
            "source": source,
            "fallback_used": bool(not api_read_ok or not wiki_document_count),
            "error": api_error,
            "roles": selected_roles,
            "card_ids": card_ids,
            "source_mode": configured_source,
            "source_names": [
                _text(row.get("name"))
                for row in selected_rows
                if _text(row.get("name"))
            ],
            "content_type": content_type,
            "content_subtype": content_subtype,
            "product_category": product_category,
            "template_group_id": template_group_id,
        }
        return "\n".join(blocks)[:max_chars]


knowledge = FeishuKnowledge()
