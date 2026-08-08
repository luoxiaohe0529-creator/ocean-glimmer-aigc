# 前端、Python 与 n8n 接口契约

所有浏览器请求先发送到本地 Node.js 服务。Stage 1 / 2 / 3 与后期处理转发到 Python；Stage 4 / 5 / 6 转发到 n8n。

## 路由表

| 前端 API | 后端 | 用途 |
| --- | --- | --- |
| `POST /api/fast/stage-1` | Python `/stage-1` | 产品链接、营销主题、Office 文本或产品图一次生成简报、Mood Board 和完整创意方案池 |
| `POST /api/fast/stage-2` | Python `/stage-2` | 选中创意方案生成脚本 |
| `POST /api/fast/stage-3` | Python `/stage-3` | 读取摄影摄像知识，把脚本拆成可生成视频的精细分镜 |
| `POST /api/workflow/stage-3` | `ai-ad-script-to-video-task-v2` | 可选的 n8n 任务建档兼容入口 |
| `POST /api/workflow/stage-4` | `ai-ad-video-task-v2` | 生成视频分段或成片 |
| `POST /api/workflow/stage-5` | `aigc-storyboard-images-v1` | 生成主人公图或一张 9:16 多宫格分镜图 |
| `POST /api/workflow/stage-6` | `ai-ad-video-concat` | 合并多段视频 |
| `POST /api/media/edit` | Python `/media/edit` | 截取、画幅、配乐和字幕 |
| `POST /api/providers/kie/character` | Python `/providers/kie/character` | 提交 GPT Image 2 主人公任务 |
| `POST /api/providers/kie/storyboard` | Python `/providers/kie/storyboard` | 提交 Nano Banana 2 分镜图任务 |
| `POST /api/providers/kie/overseas-video` | Python `/providers/kie/overseas-video` | 提交 Veo 3.1 海外视频任务 |
| `POST /api/providers/kie/status` | Python `/providers/kie/status` | 查询 KIE 异步任务状态 |

文档入口、资产上传和多段拼接属于可选扩展。未导入对应工作流时，应在 `.env` 中关闭相关入口或补充自己的工作流。

## Stage 1：产品策略

请求核心字段：

```json
{
  "product_url": "",
  "document_text": "",
  "language": "中文",
  "content_type": "高端TVC",
  "product_images": []
}
```

响应核心字段：

```json
{
  "ok": true,
  "product_record_id": "record-id",
  "product_brief": {
    "product_name": "示例产品",
    "selling_points": []
  },
  "mood_boards": [
    {"mood_board_id": "mood-01", "name": "清凉通透"}
  ],
  "creative_plans": [
    {
      "plan_id": "plan-01",
      "title": "方案标题",
      "core_hook": "核心创意切入",
      "mood_board_id": "mood-01",
      "slogan": "一句可传播表达",
      "opening_method": "开篇方式",
      "rhythm_skeleton": "节奏骨架",
      "visual_codes": [],
      "director_guidance": "给 Stage 2 的导演指导",
      "score": 86,
    }
  ],
  "recommended_plan_id": "plan-01",
  "hooks": []
}
```

`hooks[]` 仅为旧前端兼容投影，不再是 Stage 1 的主数据结构。

## Stage 2：编剧脚本

输入包含 `product_brief`、选中 `creative_plan`（同时兼容旧 `hook`）、内容类型、目标时长、创意筛选与声音类型。Stage 2 只读取编剧导演角色知识。

响应至少返回：

```json
{
  "ok": true,
  "script_text": "完整脚本",
  "script_segments": [],
  "model_provider": "gemini"
}
```

Stage 1 的产品事实整理和创意方案默认都通过豆包 Responses 多模态通道生成，并返回 `product_facts_provider: doubao-responses` 与 `model_provider: doubao-responses`；中文导演脚本和摄影分镜仍通过 KIE.ai 的 Gemini 3.1 Pro 通道生成；英文脚本当前使用 DeepSeek，并返回 `model_provider: deepseek`。

## KIE 异步任务

提交接口统一返回：

```json
{
  "ok": true,
  "provider": "kie.ai",
  "kind": "character",
  "model": "gpt-image-2-text-to-image",
  "task_id": "task-id"
}
```

状态接口输入 `task_id` 与 `kind`，输出标准化的 `status` 和 `urls`。它们是供应商适配与本地调试入口；正式图片链路由 n8n 05 直接完成提交、Wait、轮询、前端回写与失败处理。

## Stage 3：摄影摄像分镜

正式入口输入包含 Stage 2 脚本、已选 `creative_plan` 和产品简报，Python Stage 3 只读取摄影摄像角色知识，响应至少返回：

```json
{
  "ok": true,
  "video_task_id": "task-id",
  "storyboard": [
    {
      "time": "0-3s",
      "visual": "画面描述",
      "camera_movement": "运镜",
      "dialogue": "台词或旁白",
      "video_prompt": "视频模型提示词"
    }
  ]
}
```

展示副本如果还需要在 n8n 工作台创建视频任务，会先调用 Python Stage 3，再把返回的 `storyboard` 交给 n8n 兼容入口建档。

## Stage 4：视频生成

输入包含任务 ID、分镜、产品图、角色图、时长与声音配置。单段可直接返回 `video_url`；多段应返回 `segments[]`，由 Stage 6 合并。

## 后期剪辑

输入 `source_video_url`、截取时间、输出画幅、可选配乐 Data URL、音量和字幕文本。响应返回工作台可直接播放的 `output_url`。

## 错误格式

所有 API 应使用非 2xx 状态码并返回结构化错误：

```json
{
  "ok": false,
  "error": "upstream_error",
  "message": "视频供应商暂时不可用"
}
```
