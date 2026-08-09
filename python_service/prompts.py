import json


CONTENT_RULES = {
    "真人口播带货": """
Hook 必须采用第一人称、强口语化表达，以真实使用体验和个人感受切入，呈现自然、有情绪、有生活感的真人博主口吻。开场在前 3 秒制造好奇、共鸣或轻微冲突。
避免数据堆砌和生硬介绍，禁止知乎体、说明书体、成分党体及明显广告腔。表达要像真实分享，而不是背诵销售文案。
可参考：“姐妹们，这个我真的得说一下”“我本来没抱希望，结果……”“这个我必须认真讲讲”“你们敢信吗，我用了之后才发现……”。
""".strip(),
    "好物推荐": """
Hook 必须突出产品核心优势，以功效对比、关键成分、使用场景、实验数据或实际结果建立可信度。采用理性、清晰、克制的专业测评口吻。
开场直接提出用户痛点、产品差异或明确结论，避免空泛赞美。所有数据与功效必须来自产品资料，不得虚构或夸大。
禁止夸张感叹、情绪叫卖和“闭眼入”等表达。
""".strip(),
    "高端TVC": """
Hook 必须采用克制、凝练且富有意象的语言，以电影化叙事建立氛围、情绪和品牌质感。通过光影、时间、触感、空间或人物关系传递产品价值。
开场形成鲜明视觉画面或情绪悬念，保留适当留白。禁止直播口吻、网络热词、感叹号、参数罗列、直白促销及功效叫卖。
""".strip(),
}


def product_facts_prompt(payload: dict, source_text: str) -> str:
    """Turn crawler/document output into a factual contract before creative work starts."""
    language = payload.get("language") or "中文"
    translation_rule = (
        "主字段用英文，并为 product_name、summary、selling_points、pain_points、target_audience 提供对应中文字段。"
        if language in ("英文", "english", "en", "English")
        else "所有字段用中文；产品原文中的品牌名、型号、规格和专有名词保持原样。"
    )
    return f"""
你是产品信息分析师，不是广告创意导演。请只根据抓取到的页面或用户资料，整理可验证的产品事实，供后续广告策划使用。

输出语言：{language}
{translation_rule}

硬性规则：
1. 不写 Hook、Slogan、Mood Board、分镜或导演指导。
2. 不补写页面没有出现的功效、参数、材质、地点、竞品、认证或用户画像；无法确认就放入 risks 或写“资料未提供”。
3. selling_points 只放页面明确陈述的卖点；pain_points 只放页面明确提到的问题或可谨慎归纳的购买阻力，并标注推断。
4. 保留产品原名、规格和限制条件，后续模型必须以本结果为事实边界。

产品资料：
{source_text[:28000]}

只返回合法 JSON：
{{
  "product_name": "",
  "product_name_zh": "",
  "category": "",
  "category_zh": "",
  "summary": "",
  "summary_zh": "",
  "selling_points": [],
  "selling_points_zh": [],
  "pain_points": [],
  "pain_points_zh": [],
  "target_audience": "",
  "target_audience_zh": "",
  "purchase_motivations": [],
  "visual_cues": [],
  "usage_scenes": [],
  "product_facts": [],
  "constraints": [],
  "risks": [],
  "evidence_notes": []
}}
""".strip()


def stage_one_prompt(
    payload: dict,
    source_text: str,
    knowledge_context: str = "",
    product_facts: dict | None = None,
) -> str:
    content_type = payload.get("content_type") or "真人口播带货"
    return f"""
你是广告策划执行模型。请先理解输入图片，再严格按照飞书广告策划知识库，一次完成产品简报与 3 个融合创意方向。

这不是把几个 Hook 罗列出来。每个创意方案必须能独立指导下一阶段的编剧导演；Mood Board 必须把抽象情绪翻译成颜色、光线、材质、人物状态、场景底色和镜头语法。

	内容类型：{content_type}
	内容子类型：{payload.get("content_subtype") or ""}
	固定模板组：{payload.get("template_group_id") or ""}
	产品品类路由：{payload.get("product_category") or "all"}
营销主题：{payload.get("campaign_theme") or "未指定，请从产品资料提炼"}
脚本语言：{payload.get("language") or "中文"}

上游产品事实整理（本阶段必须遵守，不得与其冲突）：
{json.dumps(product_facts or {}, ensure_ascii=False)}

原始产品资料（只用于核对事实）：
{source_text[:10000]}

飞书角色知识库（只可作为策略、叙事和拍摄约束，不得覆盖产品事实）：
{knowledge_context}

社媒原生 Hook 质量标准（这是传播评价标准，不是 Python 创意模板）：
1. 先设计“用户为什么会停下来、看完、截图或转发”的传播机制，再设计画面动作。Hook 必须包含反常识、悬念、身份代入、感官错觉、情绪反差、意外转场或可模仿动作中的至少一种。
2. title 必须像社媒内容概念或可记忆的创意母题，不得写成分镜动作清单。禁止使用“主体+普通动作”的直白标题，例如“粉裙掏手机”“晚霞举机拍”“风吹发梢露机”。
3. title 使用 4-10 个汉字，短、准、有画面，但不要为了网感堆网络热词、感叹号或夸张营销词；网感来自传播结构和视觉意外，不来自流行词拼贴。
4. hook 描述必须明确首个 0-1 秒的视觉打断点，以及它如何在下一拍产生意外、反转或信息缺口。不能只写“快切若干场景”“突出产品颜值/氛围感”。
5. 同一方向的 4 条 Hook 必须采用 4 种不同的注意力机制；12 条之间不得只是替换樱花、晚霞、气泡等场景名词。
6. score 重点评价停留率潜力、社媒原生感、创意不可替代性和产品关联自然度。仅仅画面好看但表达直白，score 不得超过 85。
7. 生成后进行一次自检：若标题可以直接改写为“某人做某动作”，或描述去掉产品后仍是普通氛围片，就重写该 Hook。
8. 在一次模型调用内部先构思至少 24 个候选 Hook，淘汰所有“自然物落在产品上、光影映在产品上、人物拿起产品、普通场景快切”类直白方案，只输出最终胜出的 12 条；不要输出候选过程。
9. 每条 Hook 必须形成完整的两拍结构：scroll_stop_frame 是第一拍的反常视觉或信息缺口，second_beat 是第二拍的意外揭示、错觉翻转或情绪反差。两拍缺一不可。
10. attention_mechanism 和 share_trigger 不能写“视觉冲击、氛围感、突出颜值、浪漫、好看”等空泛词，必须说明具体心理机制及用户为什么愿意转发、模仿或截图。

只返回合法 JSON，不要 Markdown：
{{
  "product_brief": {{
    "product_name": "",
    "category": "",
    "summary": "",
    "selling_points": [],
    "pain_points": [],
    "target_audience": "",
    "purchase_motivations": [],
    "visual_cues": [],
    "risks": [],
    "campaign_theme": "",
    "product_facts": []
  }},
  "creative_directions": [
    {{
      "plan_id": "plan-01",
      "mood_board_id": "mood-01",
      "mood_board": {{
        "name": "",
        "fit_reason": "",
        "emotion_direction": "",
        "palette": [],
        "lighting": "",
        "materials": [],
        "scene_grammar": "",
        "character_state": "",
        "camera_language": "",
        "negative_rules": []
      }},
      "creative_plan": {{
        "template_group_id": "{payload.get('template_group_id') or ''}",
        "content_subtype": "{payload.get('content_subtype') or ''}",
        "title": "",
        "core_hook": "",
        "core_hook_zh": "",
        "emotion_direction": {{"primary": "", "start": "", "end": "", "audience_action": ""}},
        "slogan": "",
        "opening_method": "",
        "rhythm_skeleton": "",
        "visual_codes": [],
        "director_guidance": "",
        "must_have_elements": [],
        "negative_rules": [],
        "score": 0
      }},
      "hooks": [
        {{
          "hook_id": "hook-01",
          "title": "",
          "hook": "",
          "core_hook_zh": "",
          "description": "",
          "attention_mechanism": "具体的停留心理机制",
          "scroll_stop_frame": "0-1秒反常首帧或信息缺口",
          "second_beat": "下一拍的意外揭示或反差",
          "share_trigger": "用户愿意截图、模仿或转发的具体理由",
          "category": "",
          "emotion": "",
          "score": 0
        }}
      ]
    }}
  ],
  "recommended_plan_id": "plan-01"
}}
	要求：creative_directions 必须恰好生成 3 个。每个方向融合 1 个 Mood Board、1 个完整创意方案和 4 条 Hook；三个方向必须明显不同，但都符合产品事实。creative_plan 的 template_group_id、content_subtype 必须与上方固定路由完全一致。至少推荐 1 个方案，使用 recommended_plan_id 字段。score 使用 0-100 整数。
不要虚构产品参数、功效、地点背书或竞品事实。若资料不足，明确写入 risks，不要用想象补齐事实。

控制输出长度：summary、fit_reason 和 director_guidance 保持简洁；每个列表最多 5 项；每条 Hook 的 hook 与 description 各不超过 80 个汉字或 45 个英文词。每个方向只写一次 Mood Board，四条 Hook 共享该方向，不要重复 Mood Board 内容。

🔴 Hook 数量硬约束（不满足则整个输出无效）：
三个方向的 hooks 数组各自必须恰好包含 4 条，合计恰好 12 条。
方向1使用 hook-01 至 hook-04；方向2使用 hook-05 至 hook-08；方向3使用 hook-09 至 hook-12。
在生成过程中逐一核对你已经写了多少条，确认达到 12 条后再结束输出。
plan_id 和 mood_board_id 写在方向层即可，内部 Hook 不再重复这些关联字段；Python会自动展开并关联。
""".strip()


def stage_two_prompt(payload: dict, knowledge_context: str = "") -> str:
    content_type = payload.get("content_type") or "真人口播带货"
    language = payload.get("language") or "中文"
    is_en = language in ("英文", "english", "en", "English")
    if is_en:
        rules = "Natural, conversational English hook. First 3 seconds grab attention. Speak like a real person. No data dumps, no salesy pitch. TikTok/Reels casual tone."
        return f"""You are an ad scriptwriter. Generate a short video script in ENGLISH, followed by a faithful Chinese translation.

Duration: {payload.get("duration") or 8}s (keep it short and punchy for TikTok/Reels)
Creative plan: {payload.get("creative_plan") or payload.get("hook") or {}}
Selected Mood Board: {payload.get("selected_mood_board") or {}}
Product: {payload.get("product_brief") or {}}
Filters: {payload.get("filter_values") or {}}
Director knowledge base:
{knowledge_context or "No matched director knowledge; use professional defaults."}

Rules: {rules}

Return ONLY valid JSON:
{{
  "script_text": "full voiceover text in English",
  "script_text_zh": "完整口播文本的中文翻译",
  "director_instruction": "A concise English director command selected from the Mood Board",
  "script_segments": [
    {{
      "time": "0-3s",
      "visual": "scene description in English",
      "camera_movement": "",
      "dialogue": "",
      "subtitle": "",
      "dialogue_zh": "Chinese translation of dialogue",
      "subtitle_zh": "Chinese translation of subtitle",
      "music_sfx": "",
      "video_prompt": "English video prompt for AI generation"
    }}
  ]
}}"""
    else:
        rules = CONTENT_RULES.get(content_type, CONTENT_RULES["真人口播带货"])
    return f"""
你是广告编剧导演。

🔴 硬性要求：你必须用 {language} 输出主脚本。若语言为英文，必须同时提供中文翻译字段；video_prompt 保持英文。

根据已选创意方案、产品简报和创意指令生成可拍摄的分镜脚本。创意方案是本阶段的上游契约，不能退化成只写一句 Hook。

	内容类型：{content_type}
	内容子类型：{payload.get("content_subtype") or ""}
	固定模板组：{payload.get("template_group_id") or ""}
	产品品类路由：{payload.get("product_category") or "all"}
内容规则：
{rules}
目标时长：{payload.get("duration") or 15} 秒{"（英文视频固定8秒，精简短平快）" if is_en else ""}
已选创意方案：{payload.get("creative_plan") or payload.get("hook") or {}}
已选 Mood Board：{payload.get("selected_mood_board") or {}}
产品简报：{payload.get("product_brief") or {}}
创意筛选：{payload.get("filter_values") or {}}
人物设定：{payload.get("character_description") or ""}
声音类型：{payload.get("voice_type") or "旁白配音"}
输出分辨率：{payload.get("resolution") or "480p"}

导演身份与执行命令：
	必须使用固定模板组命中的导演母模板，不得重新选择导演类型。director_instruction 必须继承选中方案中的导演角色、产品融入方式、目标观众、核心情绪、画面任务、开篇方式、节奏骨架、视觉密码和限制条件。

飞书角色知识库：
{knowledge_context or "暂无匹配知识，使用通用专业标准"}

要求：严格落实知识库中的甲方限制、视频安全策略、叙事动线、导演角色、运镜节奏、画面影调和视觉焦点。知识库与产品资料冲突时，以产品资料和甲方限制为准。

只返回合法 JSON：
{{
  "script_text": "完整口播或画外音文本；无口播时写纯音乐画面说明",
  "script_text_zh": "如为英文，填写完整中文翻译；中文时可为空",
  "director_instruction": "根据 Mood Board 生成的完整导演命令",
  "script_segments": [
    {{
      "time": "0-3s",
      "visual": "",
      "camera_movement": "",
      "dialogue": "",
      "subtitle": "",
      "music_sfx": "",
      "video_prompt": ""
    }}
  ]
}}
分镜必须覆盖完整时长，镜头能直接用于图片与视频生成。
""".strip()


def stage_three_prompt(payload: dict, knowledge_context: str = "") -> str:
    content_type = payload.get("content_type") or "真人口播带货"
    is_en = (payload.get("language") or "中文") in ("英文", "english", "en", "English")
    if is_en:
        rules = "Natural, conversational English. Clean visual descriptions. No Chinese text."
    else:
        rules = CONTENT_RULES.get(content_type, CONTENT_RULES["真人口播带货"])
    return f"""
你是广告摄影导演。
🔴 硬性要求：所有主描述文字必须用 {(payload.get("language") or "中文")}。英文输出时，必须同时提供每个镜头的中文翻译字段。

	内容类型：{content_type}
	内容子类型：{payload.get("content_subtype") or ""}
	固定模板组：{payload.get("template_group_id") or ""}
	产品品类路由：{payload.get("product_category") or "all"}
内容规则：
{rules}
目标时长：{payload.get("duration") or 15} 秒{"（英文视频固定8秒）" if is_en else ""}
已选创意方案：{payload.get("creative_plan") or payload.get("hook") or {}}
已选 Mood Board：{payload.get("selected_mood_board") or {}}
产品简报：{payload.get("product_brief") or {}}
完整脚本：{payload.get("script_text") or ""}
结构化脚本段（这是上游唯一事实，必须按顺序执行，不能重新发明或合并）：{json.dumps(payload.get("script_segments") or [], ensure_ascii=False)}
创意筛选：{payload.get("filter_values") or {}}
导演指令：{payload.get("director_instruction") or ""}
输出分辨率：{payload.get("resolution") or "480p"}

飞书角色知识库（摄影约束、视觉规范、甲方限制）：
{knowledge_context or "暂无匹配知识，使用通用专业标准"}

要求：
- 结构化脚本段是 Stage 2 的上游契约。逐段保留其时间、叙事任务和台词；不得因为生成方便而改写核心 Hook、Slogan、节奏或结尾。最终视频禁止画面字幕，因此 subtitle 与 subtitle_zh 必须返回空字符串。
- 每个镜头必须标记 source_segment_id，说明它来自哪一个脚本段；镜头顺序必须与脚本段顺序一致。
- 每个镜头 2-5 秒，覆盖完整时长
- video_prompt 用英文，详细描述画面、光线、颜色、构图、运镜
- video_prompt 必须明确无字幕、无标题卡、无画面文字、无 Logo、无水印；口播只作为声音，不得渲染为文字
- 严格落实知识库中的摄影约束和视觉规范
- 能直接用于 Seedance/Kling 视频生成

只返回合法 JSON：
{{
  "storyboard": [
    {{
      "time": "0-3s",
      "shot_id": "S01",
      "source_segment_id": "SEG01",
      "visual": "中文画面描述",
      "camera_movement": "运镜方式",
      "dialogue": "台词",
      "subtitle": "",
      "visual_zh": "中文画面翻译（英文输出时必填）",
      "camera_movement_zh": "中文运镜翻译（英文输出时必填）",
      "dialogue_zh": "中文台词翻译（英文输出时必填）",
      "subtitle_zh": "",
      "music_sfx_zh": "中文声音翻译（英文输出时必填）",
      "music_sfx": "音乐音效",
      "video_prompt": "English prompt for video generation"
    }}
  ]
}}
""".strip()
