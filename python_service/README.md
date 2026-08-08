# Python service

Stage 1, Stage 2 and Stage 3 run here because they are direct HTTP + LLM + JSON tasks. Stage 1 follows a fixed order: crawler, DeepSeek factual product analysis, advertising-planning Wiki retrieval, then Doubao Responses for multimodal 12 Hooks and compact Mood Boards. Stage 2 uses the existing Gemini 3.1 Pro channel with the selected Hook, Mood Board and director Wiki; Stage 3 uses the resulting script with the camera Wiki. The service also exposes KIE.ai task adapters and a local FFmpeg editing endpoint.

Endpoints:

- `GET /health`
- `POST /stage-1`
- `POST /stage-2`
- `POST /stage-3`
- `POST /media/edit`
- `POST /providers/kie/character`
- `POST /providers/kie/storyboard`
- `POST /providers/kie/overseas-video`
- `POST /providers/kie/status`
- `GET /knowledge/filters?content_type=高端TVC`

Configuration is read from the project `.env`. Use `PYTHON_MOCK_MODE=1` for local UI tests without calling external models.

The root `npm start` command also starts the Node Playwright scraper on `SCRAPER_SERVICE_URL` (default `http://127.0.0.1:9876`). Install its browser once with `npm exec playwright install chromium`.

The three Feishu role Wiki documents are the stable knowledge/configuration layer:

- 广告策划：受众、卖点转译、核心视觉资产、场景资源、甲方限制
- 编剧导演：叙事动线、导演角色、输出模板、品牌参考
- 摄影摄像：安全策略、运镜节奏、影调、视觉焦点

Each stage reads only its own role Wiki. The reader keeps a five-minute per-role cache, caps the selected context at 4000-5200 characters, and marks the source in `knowledge_trace`. Built-in structured cards are only an emergency local contract when Feishu permissions or network access are temporarily unavailable; no Base/table knowledge path exists.

`AI视频工厂工作台` remains the runtime store for products, hooks, scripts, and video tasks. Add the Feishu app as a collaborator to the three Wiki documents and configure `FEISHU_APP_ID` / `FEISHU_APP_SECRET` locally.
# Provider routing

- Chinese video starts with the official Seedance 2.0 workflow. A confirmed face, identity, moderation, or safety-policy block is routed to KIE Kling 3.0 (`kling-3.0/video`). Other Seedance errors remain visible and do not silently consume fallback credits.
- English video continues to use KIE Veo 3.1.
- Storyboards use Nano Banana Pro and character references use Image 2.
- Post-production uses Topaz Video AI (`ghq-5` by default) for asynchronous enhancement, followed by the local FFmpeg editing endpoint for trimming, music, subtitles, and delivery.
- ChatCut Skills are the optional editable finishing path. They require a ChatCut project/session, so they are not treated as a stateless production API and do not block the automated SaaS path.
