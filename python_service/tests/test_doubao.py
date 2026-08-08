import unittest

from python_service.doubao import _build_input, _response_text


class DoubaoAdapterTests(unittest.TestCase):
    def test_builds_responses_multimodal_input(self):
        messages = _build_input(
            "请输出 JSON",
            image_urls=[
                "https://example.com/product.jpg",
                {"url": "https://example.com/second.jpg"},
                "data:image/png;base64,not-sent-to-provider",
            ],
        )
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["content"][0]["type"], "input_image")
        self.assertEqual(messages[0]["content"][1]["image_url"], "https://example.com/second.jpg")
        self.assertEqual(messages[0]["content"][-1], {"type": "input_text", "text": "请输出 JSON"})
        self.assertEqual(len(messages[0]["content"]), 3)

    def test_reads_responses_output_text(self):
        data = {
            "output": [{
                "type": "message",
                "content": [{"type": "output_text", "text": "{\"ok\": true}"}],
            }],
        }
        self.assertEqual(_response_text(data), '{"ok": true}')


if __name__ == "__main__":
    unittest.main()
