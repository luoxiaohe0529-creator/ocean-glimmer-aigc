import json
import os
import unittest
from unittest.mock import patch

os.environ["PYTHON_MOCK_MODE"] = "1"

from python_service.server import (
    StageOneRequest,
    _infer_template_route,
    _normalize_stage_one,
    _stage_one_missing_fields,
    mock_stage_one,
    stage_one,
    stage_two,
    stage_three,
)
from python_service.feishu_knowledge import DEFAULT_FILTERS, FeishuKnowledge, WikiConfig, _parse_wiki_cards
from python_service.kie import create_image_task, create_kling_video_task, query_task


class ServiceTests(unittest.TestCase):
    def test_stage_one_accepts_theme_without_url(self):
        payload = StageOneRequest(campaign_theme="夏日樱花晚霞").model_dump()
        result = stage_one(payload)
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["creative_plans"]), 3)
        self.assertEqual(len(result["mood_boards"]), 3)
        self.assertEqual(len(result["hooks"]), 12)
        self.assertEqual(result["recommended_plan_id"], "plan-01")
        self.assertEqual(result["model_provider"], "mock")
        self.assertEqual(result["product_facts_provider"], "mock")
        self.assertIn("doubao_responses_creative_model", result["pipeline_trace"]["order"])

    def test_stage_one_uses_doubao_channel_for_creative_output(self):
        payload = StageOneRequest(campaign_theme="夏日樱花晚霞").model_dump()
        creative_output = mock_stage_one(payload)
        with patch.dict(os.environ, {"PYTHON_MOCK_MODE": "0"}):
            with patch("python_service.server.fetch_product_page", return_value={}):
                with patch("python_service.server.chat_json", return_value={"product_name": "测试产品", "category": "手机"}) as facts_model:
                    with patch("python_service.server.knowledge.context", return_value="广告策划知识"):
                        with patch("python_service.server.doubao_json", return_value=creative_output) as creative_model:
                            result = stage_one(payload)
        facts_model.assert_called_once()
        creative_model.assert_called_once()
        self.assertEqual(result["model_provider"], "doubao-responses")
        self.assertEqual(result["product_facts_provider"], "deepseek")

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
        result = stage_two({
            "hook": {"hook": "光落在肌肤上"},
            "product_brief": {"product_name": "测试产品"},
            "duration": 30,
        })
        self.assertTrue(result["script_text"])
        self.assertGreaterEqual(len(result["script_segments"]), 3)
        self.assertEqual(result["model_provider"], "mock")

    def test_stage_three_returns_camera_storyboard(self):
        result = stage_three({
            "script_text": "从真实体验开始讲述产品价值。",
            "product_brief": {"product_name": "测试产品"},
            "duration": 15,
        })
        self.assertTrue(result["ok"])
        self.assertGreaterEqual(len(result["storyboard"]), 3)
        self.assertEqual(result["knowledge_role"], "摄影摄像")

    def test_filter_schema_has_safe_fallback(self):
        client = FeishuKnowledge()
        client.app_id = ""
        client.app_secret = ""
        schema = client.filter_schema("高端TVC")
        self.assertEqual(schema["source"], "fallback")
        self.assertEqual(len(schema["filters"]), 3)
        self.assertEqual(schema["filters"], DEFAULT_FILTERS["高端TVC"])

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
            self.assertEqual(client.source_for(("广告策划",)), "fallback")
            self.assertEqual(client.records_for(("广告策划",)), {})

    def test_role_scoped_context_only_returns_requested_role(self):
        client = FeishuKnowledge()
        client.app_id = ""
        client.app_secret = ""
        context = client.context("高端TVC", {}, roles=("摄影摄像",), top_k=4)
        self.assertIn("摄影摄像知识卡", context)
        self.assertNotIn("编剧导演知识卡", context)

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
        stage_two_result = stage_two(dict(payload))
        self.assertEqual(stage_two_result["template_group_id"], "tvc-social-fastcut-v3")
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
