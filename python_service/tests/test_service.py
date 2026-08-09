import json
import os
import unittest
from unittest.mock import patch

import httpx

from python_service.server import (
    StageOneRequest,
    _infer_template_route,
    _normalize_stage_one,
    _stage_one_doubao_json,
    _stage_one_missing_fields,
    stage_one,
    stage_two,
    stage_three,
)
from python_service.doubao import DoubaoTimeoutError, _stream_response_text
from python_service.feishu_knowledge import FILTER_DEFINITIONS, FeishuKnowledge, WikiConfig, _parse_wiki_cards
from python_service.kie import create_image_task, create_kling_video_task, query_task
from python_service.prompts import stage_one_prompt


def stage_one_fixture():
    moods = [
        {
            "mood_board_id": f"mood-{index:02d}",
            "name": f"测试视觉方向 {index}",
            "palette": ["测试色"],
            "lighting": "测试光线",
            "materials": ["测试材质"],
            "scene_grammar": "测试场景",
        }
        for index in range(1, 4)
    ]
    plans = [
        {
            "plan_id": f"plan-{index:02d}",
            "mood_board_id": f"mood-{index:02d}",
            "title": f"测试方案 {index}",
            "core_hook": f"测试核心 Hook {index}",
        }
        for index in range(1, 4)
    ]
    hooks = [
        {
            "hook_id": f"hook-{index:02d}",
            "plan_id": f"plan-{((index - 1) // 4) + 1:02d}",
            "mood_board_id": f"mood-{((index - 1) // 4) + 1:02d}",
            "title": f"测试 Hook {index}",
            "hook": f"测试文案 {index}",
        }
        for index in range(1, 13)
    ]
    return {
        "product_brief": {"product_name": "测试产品", "category": "测试品类"},
        "mood_boards": moods,
        "creative_plans": plans,
        "hooks": hooks,
        "recommended_plan_id": "plan-01",
    }


def stage_two_fixture():
    return {
        "script_text": "测试脚本",
        "director_instruction": "测试导演指令",
        "script_segments": [{"time": "0-3s", "visual": "测试画面"}],
    }


def stage_three_fixture():
    return {
        "storyboard": [{
            "time": "0-3s",
            "visual": "测试镜头",
            "camera_movement": "测试运镜",
            "video_prompt": "test shot",
        }],
    }


class ServiceTests(unittest.TestCase):
    def test_stage_one_prompt_requires_social_native_hook_mechanics(self):
        prompt = stage_one_prompt({"content_type": "高端TVC"}, "产品资料", "飞书知识")
        self.assertIn("首个 0-1 秒的视觉打断点", prompt)
        self.assertIn("不得写成分镜动作清单", prompt)
        self.assertIn("12 条之间不得只是替换", prompt)
        self.assertIn('"scroll_stop_frame"', prompt)
        self.assertIn("至少 24 个候选 Hook", prompt)
        self.assertIn("两拍结构", prompt)

    def test_doubao_stream_parser_collects_responses_api_deltas(self):
        lines = [
            'event: response.output_text.delta',
            'data: {"type":"response.output_text.delta","delta":"{\\"ok\\":"}',
            'data: {"type":"response.output_text.delta","delta":"true}"}',
            'data: [DONE]',
        ]
        self.assertEqual(_stream_response_text(lines), '{"ok":true}')

    def test_stage_one_doubao_retries_with_lite_after_primary_timeout(self):
        with patch.dict(os.environ, {
            "DOUBAO_MODEL": "doubao-pro-test",
            "DOUBAO_FALLBACK_MODEL": "doubao-lite-test",
        }):
            with patch(
                "python_service.server.doubao_json",
                side_effect=[DoubaoTimeoutError("primary timeout"), {"ok": True}],
            ) as model:
                result, used_model, fallback_used = _stage_one_doubao_json("test")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(used_model, "doubao-lite-test")
        self.assertTrue(fallback_used)
        self.assertEqual(model.call_count, 2)

    def test_stage_one_accepts_theme_without_url(self):
        payload = StageOneRequest(campaign_theme="夏日樱花晚霞").model_dump()
        with patch.dict(os.environ, {"STAGE1_FAST_MODE": "1"}):
            with patch("python_service.server.fetch_product_page", return_value={}):
                with patch("python_service.server.knowledge.records_for", return_value={"广告策划": []}) as wiki_prefetch:
                    with patch("python_service.server.knowledge.context", return_value="真实飞书策划知识"):
                        with patch(
                            "python_service.server.gemini_kie_json",
                            return_value=stage_one_fixture(),
                        ):
                            result = stage_one(payload)
        wiki_prefetch.assert_called_once_with(("广告策划",))
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["creative_plans"]), 3)
        self.assertEqual(len(result["mood_boards"]), 3)
        self.assertEqual(len(result["hooks"]), 12)
        self.assertEqual(result["recommended_plan_id"], "plan-01")
        self.assertEqual(result["model_provider"], "gemini-kie")
        self.assertEqual(result["product_facts_provider"], "gemini-kie")
        self.assertIn("gemini_kie_3_1_pro_stage1_model", result["pipeline_trace"]["order"])

    def test_fused_creative_directions_expand_to_frontend_contract(self):
        directions = []
        for direction_index in range(1, 4):
            directions.append({
                "plan_id": f"plan-{direction_index:02d}",
                "mood_board_id": f"mood-{direction_index:02d}",
                "mood_board": {
                    "name": f"融合视觉 {direction_index}",
                    "palette": ["测试色"],
                    "materials": ["测试材质"],
                    "scene_grammar": "测试场景",
                },
                "creative_plan": {"title": f"融合方案 {direction_index}", "core_hook": "测试核心"},
                "hooks": [
                    {"title": f"融合 Hook {direction_index}-{hook_index}", "hook": "测试文案"}
                    for hook_index in range(1, 5)
                ],
            })
        result = _normalize_stage_one({
            "product_brief": {"product_name": "测试产品"},
            "creative_directions": directions,
            "recommended_plan_id": "plan-01",
        }, {"content_type": "高端TVC"})
        self.assertEqual(len(result["creative_plans"]), 3)
        self.assertEqual(len(result["mood_boards"]), 3)
        self.assertEqual(len(result["hooks"]), 12)
        self.assertEqual(result["hooks"][4]["plan_id"], "plan-02")
        self.assertEqual(result["hooks"][8]["mood_board_id"], "mood-03")
        self.assertEqual(_stage_one_missing_fields(result), [])

    def test_stage_one_uses_one_kie_gemini_call_even_if_legacy_fast_flag_is_zero(self):
        payload = StageOneRequest(campaign_theme="夏日樱花晚霞").model_dump()
        creative_output = stage_one_fixture()
        with patch.dict(os.environ, {"STAGE1_FAST_MODE": "0"}):
            with patch("python_service.server.fetch_product_page", return_value={}):
                with patch("python_service.server.knowledge.context", return_value="广告策划知识"):
                    with patch(
                        "python_service.server.gemini_kie_json",
                        return_value=creative_output,
                    ) as stage1_model:
                        result = stage_one(payload)
        self.assertEqual(stage1_model.call_count, 1)
        self.assertEqual(result["model_provider"], "gemini-kie")
        self.assertEqual(result["product_facts_provider"], "gemini-kie")
        self.assertIn("gemini_kie_3_1_pro_stage1_model", result["pipeline_trace"]["order"])

    def test_stage_one_sends_uploaded_https_image_to_kie_gemini(self):
        payload = StageOneRequest(
            campaign_theme="夏日樱花晚霞",
            product_images=["https://assets.example.com/product.jpg"],
        ).model_dump()
        with patch.dict(os.environ, {"STAGE1_FAST_MODE": "1"}):
            with patch("python_service.server.fetch_product_page", return_value={}):
                with patch("python_service.server.knowledge.context", return_value="飞书广告策划知识"):
                    with patch(
                        "python_service.server.gemini_kie_json",
                        return_value=stage_one_fixture(),
                    ) as model:
                        result = stage_one(payload)
        self.assertEqual(model.call_count, 1)
        self.assertEqual(model.call_args.kwargs["image_urls"], ["https://assets.example.com/product.jpg"])
        self.assertNotIn("endpoint_override", model.call_args.kwargs)
        self.assertNotIn("model_override", model.call_args.kwargs)
        self.assertIn("飞书广告策划知识", model.call_args.args[0])
        self.assertEqual(result["image_inputs_received"], 1)
        self.assertEqual(result["image_inputs_sent"], 1)
        self.assertTrue(result["image_vision_used"])

    def test_stage_one_rejects_non_public_image_instead_of_silently_dropping_it(self):
        payload = StageOneRequest(
            campaign_theme="夏日樱花晚霞",
            product_images=["blob:http://localhost/private-image"],
        ).model_dump()
        with self.assertRaisesRegex(ValueError, "公开 HTTPS URL"):
            stage_one(payload)

    def test_stage_one_keeps_twelve_hooks_and_links_mood_summary(self):
        data = {
            "product_brief": {"product_name": "测试产品"},
            "mood_boards": [{
                "mood_board_id": "mood-01",
                "name": "清凉通透",
                "emotion_direction": "清凉",
                "palette": ["冰透蓝"],
                "materials": ["凝露"],
                "scene_grammar": "泳池与海边",
            }],
            "creative_plans": [{"plan_id": "plan-01", "mood_board_id": "mood-01"}],
            "hooks": [{"hook_id": f"hook-{index:02d}", "plan_id": "plan-01"} for index in range(1, 13)],
        }
        result = _normalize_stage_one(data, {})
        self.assertEqual(len(result["hooks"]), 12)
        self.assertEqual(result["hooks"][0]["mood_board_summary"]["name"], "清凉通透")

    def test_stage_one_reports_legacy_hook_only_response(self):
        missing = _stage_one_missing_fields({
            "product_brief": {"product_name": "测试产品"},
            "hooks": [{"title": "旧版 Hook"}],
        })
        self.assertEqual(missing, ["creative_plans", "mood_boards", "hooks(需要12条，实际1条)"])

    def test_stage_one_accepts_wrapped_structured_response(self):
        missing = _stage_one_missing_fields({
            "data": {
                "product_brief": {"product_name": "测试产品"},
                "creative_plans": [{"plan_id": "plan-01"}],
                "mood_boards": [{"palette": ["冰透蓝"]}],
                "hooks": [{"hook_id": f"hook-{index:02d}"} for index in range(1, 13)],
            },
        })
        self.assertEqual(missing, [])

    def test_stage_two_returns_segments(self):
        with patch("python_service.server.knowledge.context", return_value="真实飞书导演知识"):
            with patch("python_service.server.gemini_kie_json", return_value=stage_two_fixture()):
                result = stage_two({
                    "hook": {"hook": "光落在肌肤上"},
                    "product_brief": {"product_name": "测试产品"},
                    "duration": 30,
                })
        self.assertTrue(result["script_text"])
        self.assertGreaterEqual(len(result["script_segments"]), 1)
        self.assertEqual(result["model_provider"], "gemini-kie")

    def test_stage_three_returns_camera_storyboard(self):
        with patch("python_service.server.knowledge.context", return_value="真实飞书摄影知识"):
            with patch("python_service.server.gemini_kie_json", return_value=stage_three_fixture()):
                result = stage_three({
                    "script_text": "从真实体验开始讲述产品价值。",
                    "product_brief": {"product_name": "测试产品"},
                    "duration": 15,
                })
        self.assertTrue(result["ok"])
        self.assertGreaterEqual(len(result["storyboard"]), 1)
        self.assertEqual(result["knowledge_role"], "摄影摄像")

    def test_filter_schema_has_no_local_fallback(self):
        client = FeishuKnowledge()
        client.app_id = ""
        client.app_secret = ""
        schema = client.filter_schema("高端TVC")
        self.assertEqual(schema["source"], "unavailable")
        self.assertEqual(len(schema["filters"]), 3)
        self.assertEqual(schema["filters"], FILTER_DEFINITIONS["高端TVC"])
        self.assertTrue(all(not item["options"] for item in schema["filters"]))

    def test_feishu_records_drive_filters_and_prompt_context(self):
        records = {
            "广告策划": [{
                "role": "广告策划",
                "knowledge_text": "使用场景 use_scene：化妆台前、日常通勤\n卖点转译：成分科技、使用体验",
            }],
            "编剧导演": [{
                "role": "编剧导演",
                "knowledge_text": "达人气质 creator_vibe：邻家亲和、专业可信\n表达方式 speaking_style：闺蜜聊天、专业讲解",
            }],
            "摄影摄像": [{
                "role": "摄影摄像",
                "knowledge_text": "视频安全策略：避免功效夸大\n视觉焦点：产品微距、真实肤感",
            }],
        }
        client = FeishuKnowledge()
        client.app_id = "test-app-id"
        client.app_secret = "test-app-secret"
        wiki_configs = (
            WikiConfig("广告策划", "planning-node", "广告策划知识库"),
            WikiConfig("编剧导演", "director-node", "编剧导演知识库"),
            WikiConfig("摄影摄像", "camera-node", "摄影摄像知识库"),
        )
        with patch("python_service.feishu_knowledge.WIKIS", wiki_configs):
            with patch.object(client, "records_for", return_value=records):
                schema = client.filter_schema("真人口播带货")
                context = client.context("真人口播带货", {"creator_vibe": "邻家亲和"})
        self.assertEqual(schema["source"], "wiki")
        self.assertIn("邻家亲和", schema["filters"][0]["options"])
        self.assertIn("广告策划知识", context)
        self.assertIn("摄影摄像知识", context)

    def test_live_wiki_replaces_generic_default_cards(self):
        client = FeishuKnowledge()
        client.app_id = "test-app-id"
        client.app_secret = "test-app-secret"
        wiki_configs = (WikiConfig("广告策划", "planning-node", "广告策划知识库"),)
        records = {
            "广告策划": [{
                "record_id": "wiki:planning-node:custom",
                "role": "广告策划",
                "card_id": "custom",
                "name": "用户专属策划知识",
                "knowledge_text": "必须采用用户知识库里的独特叙事气质。",
            }],
        }
        with patch("python_service.feishu_knowledge.WIKIS", wiki_configs):
            with patch.object(client, "records_for", return_value=records):
                context = client.context("高端TVC", {}, roles=("广告策划",), top_k=3)
        self.assertIn("用户专属策划知识", context)
        self.assertNotIn("完整创意方案池输出契约", context)

    def test_docx_token_is_retried_after_wiki_token_lookup_fails(self):
        client = FeishuKnowledge()
        config = WikiConfig("广告策划", "docx-object-token", "广告策划知识库")
        requested_types = []

        def handler(request):
            if request.url.path.endswith("/wiki/v2/spaces/get_node"):
                obj_type = request.url.params.get("obj_type")
                requested_types.append(obj_type)
                if obj_type == "wiki":
                    return httpx.Response(400, json={"code": 99991663, "msg": "invalid param"})
                return httpx.Response(200, json={"code": 0, "data": {"node": {
                    "title": "真实策划知识库", "obj_type": "docx", "obj_token": "docx-object-token"
                }}})
            return httpx.Response(200, json={"code": 0, "data": {"content": "真实飞书知识正文"}})

        with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
            cards = client._wiki_document_text(http_client, "tenant-token", config)
        self.assertEqual(requested_types, ["wiki", "docx"])
        self.assertEqual(cards[0]["knowledge_text"], "真实飞书知识正文")

    def test_base_configuration_can_never_enable_knowledge(self):
        client = FeishuKnowledge()
        client.app_id = "app-id"
        client.app_secret = "app-secret"
        empty_wikis = (
            WikiConfig("广告策划", "", "广告策划知识库"),
            WikiConfig("编剧导演", "", "编剧导演知识库"),
            WikiConfig("摄影摄像", "", "摄影摄像知识库"),
        )
        with patch("python_service.feishu_knowledge.WIKIS", empty_wikis):
            self.assertEqual(client.source_for(("广告策划",)), "unavailable")
            self.assertEqual(client.records_for(("广告策划",)), {})

    def test_unconfigured_context_fails_instead_of_using_local_template(self):
        client = FeishuKnowledge()
        client.app_id = ""
        client.app_secret = ""
        with self.assertRaisesRegex(RuntimeError, "不提供本地知识模板"):
            client.context("高端TVC", {}, roles=("摄影摄像",), top_k=4)

    def test_status_reports_unconfigured_wiki_roles_without_exposing_tokens(self):
        client = FeishuKnowledge()
        client.app_id = ""
        client.app_secret = ""
        result = client.status()
        self.assertEqual(result["reader"], "wiki-only-v3")
        self.assertFalse(result["read_ok"])
        self.assertEqual(set(result["roles"]), {"广告策划", "编剧导演", "摄影摄像"})
        for item in result["roles"].values():
            self.assertFalse(item["configured"])
            serialized = json.dumps(item, ensure_ascii=False).lower()
            self.assertNotIn("node_token", serialized)
            self.assertNotIn("app_secret", serialized)

    def test_wiki_card_blocks_are_split_into_retrievable_cards(self):
        cards = _parse_wiki_cards(
            """CARD_START
card_id: camera-test-01
card_type: camera_execution
name: 测试摄影卡
tags: 蓝色；凝露
rule: 产品参与动作
CARD_END

CARD_START
card_id: camera-test-02
name: 测试安全卡
rule: 无字幕
CARD_END""",
            WikiConfig("摄影摄像", "camera-node", "摄影摄像知识库"),
            {"title": "摄影摄像知识库"},
            "obj-token",
        )
        self.assertEqual([card["card_id"] for card in cards], ["camera-test-01", "camera-test-02"])
        self.assertEqual(cards[0]["card_type"], "camera_execution")
        self.assertIn("无字幕", cards[1]["knowledge_text"])

    def test_v3_local_documents_have_all_template_routes(self):
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        documents = {
            "广告策划": "01-广告策划知识库-Wiki整理版.md",
            "编剧导演": "02-编剧导演知识库-Wiki整理版.md",
            "摄影摄像": "03-摄影摄像知识库-Wiki整理版.md",
        }
        expected_groups = {
            "live-general-v3",
            "review-general-v3",
            "tvc-brand-v3",
            "tvc-social-fastcut-v3",
            "tvc-material-v3",
        }
        for role, filename in documents.items():
            path = os.path.join(root, "docs", "knowledge", filename)
            with open(path, encoding="utf-8") as source:
                cards = _parse_wiki_cards(
                    source.read(),
                    WikiConfig(role, f"{role}-node", f"{role}知识库"),
                    {"title": f"{role}知识库"},
                    f"{role}-object",
                )
            groups = {card.get("template_group_id") for card in cards}
            self.assertTrue(expected_groups.issubset(groups), role)

    def test_exact_template_group_cannot_read_other_tvc_master(self):
        source = """CARD_START
card_id: director-tvc-brand-v3
template_group_id: tvc-brand-v3
content_type: 高端TVC
content_subtype: 品牌叙事TVC
product_category: all
rule: 电影叙事
CARD_END

CARD_START
card_id: director-tvc-social-fastcut-v3
template_group_id: tvc-social-fastcut-v3
content_type: 高端TVC
content_subtype: 社媒氛围快剪TVC
product_category: all
rule: 十五个一秒快剪
CARD_END

CARD_START
card_id: director-category-phone-v3
card_type: category_patch
product_category: 手机与数码
rule: 保持手机外观一致
CARD_END


CARD_START
card_id: director-legacy-v2
card_type: director_contract
rule: 旧版通用导演规则
CARD_END"""
        rows = _parse_wiki_cards(
            source,
            WikiConfig("编剧导演", "director-node", "编剧导演知识库"),
            {"title": "编剧导演知识库"},
            "director-object",
        )
        client = FeishuKnowledge()
        client.app_id = "app-id"
        client.app_secret = "app-secret"
        with patch.object(client, "records_for", return_value={"编剧导演": rows}), patch.object(
            client, "configured_for", return_value=True
        ), patch.object(client, "source_for", return_value="wiki"):
            context = client.context(
                "高端TVC",
                {},
                "蓝色手机",
                roles=("编剧导演",),
                top_k=4,
                content_subtype="社媒氛围快剪TVC",
                product_category="手机与数码",
                template_group_id="tvc-social-fastcut-v3",
            )
        self.assertIn("十五个一秒快剪", context)
        self.assertIn("保持手机外观一致", context)
        self.assertNotIn("电影叙事", context)
        self.assertNotIn("旧版通用导演规则", context)
        self.assertIn("director-tvc-social-fastcut-v3", client.last_context_meta["card_ids"])

    def test_summer_social_campaign_routes_to_fastcut_group(self):
        subtype, group = _infer_template_route({
            "content_type": "高端TVC",
            "campaign_theme": "夏日少女感，小红书高截图率氛围快剪",
        })
        self.assertEqual(subtype, "社媒氛围快剪TVC")
        self.assertEqual(group, "tvc-social-fastcut-v3")

    def test_stage_handoff_preserves_selected_template_group(self):
        payload = {
            "content_type": "高端TVC",
            "template_group_id": "tvc-social-fastcut-v3",
            "content_subtype": "社媒氛围快剪TVC",
            "product_category": "手机与数码",
            "hook": {"hook": "气泡化作手机背板凝露"},
            "product_brief": {"product_name": "蓝色手机", "category": "手机"},
            "duration": 15,
        }
        with patch("python_service.server.knowledge.context", return_value="真实飞书导演知识"):
            with patch("python_service.server.gemini_kie_json", return_value=stage_two_fixture()):
                stage_two_result = stage_two(dict(payload))
        self.assertEqual(stage_two_result["template_group_id"], "tvc-social-fastcut-v3")
        with patch("python_service.server.knowledge.context", return_value="真实飞书摄影知识"):
            with patch("python_service.server.gemini_kie_json", return_value=stage_three_fixture()):
                stage_three_result = stage_three({
                    **payload,
                    "script_text": stage_two_result["script_text"],
                    "script_segments": stage_two_result["script_segments"],
                })
        self.assertEqual(stage_three_result["template_group_id"], "tvc-social-fastcut-v3")

    @patch("python_service.kie._request")
    def test_kie_storyboard_uses_nano_banana(self, request):
        request.return_value = {"code": 200, "data": {"taskId": "image-task-1"}}
        result = create_image_task("storyboard", {
            "prompt": "九宫格分镜",
            "reference_images": ["https://example.com/product.png"],
        })
        self.assertEqual(result["model"], "nano-banana-pro")
        self.assertEqual(result["task_id"], "image-task-1")
        request.assert_called_once()

    @patch("python_service.kie._request")
    def test_kie_image_status_parses_result_json(self, request):
        request.return_value = {
            "code": 200,
            "data": {
                "state": "success",
                "resultJson": '{"resultUrls":["https://example.com/result.png"]}',
            },
        }
        result = query_task({"task_id": "image-task-1", "kind": "storyboard"})
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["urls"], ["https://example.com/result.png"])

    @patch("python_service.kie._request")
    def test_kling_fallback_uses_kling_3(self, request):
        request.return_value = {"code": 200, "data": {"taskId": "kling-task-1"}}
        result = create_kling_video_task({
            "prompt": "真人护肤广告",
            "image_urls": ["https://example.com/face.png"],
            "duration": 15,
        })
        self.assertEqual(result["model"], "kling-3.0/video")
        body = request.call_args.kwargs["json"]
        self.assertEqual(body["input"]["mode"], "pro")
        self.assertEqual(body["input"]["duration"], "15")

    @patch("python_service.kie._request")
    def test_kling_status_uses_video_terminal_state(self, request):
        request.return_value = {"code": 200, "data": {"state": "success", "resultJson": '{"resultUrls":["https://example.com/video.mp4"]}'}}
        result = query_task({"task_id": "kling-task-1", "kind": "kling_video"})
        self.assertEqual(result["status"], "succeeded")


if __name__ == "__main__":
    unittest.main()
