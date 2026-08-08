# 大海浮光 AIGC 工作台前端

浏览器以“广告策划、编剧导演、摄影摄像”三个岗位组织产品输入、创意方案选择、脚本确认、人物设定与结果展示。Stage 1/2/3 的结构化内容由 Python 服务生成，n8n 负责媒体任务、轮询、飞书工作台写入和对象存储。

## 启动

```bash
cd frontend
npm install
cd ..
npm run dev
```

默认打开 `http://localhost:4173/open-design.html`。

前端同源代理默认把请求转到 `http://localhost:5678/webhook`。如果工作流只在 n8n 编辑器里监听测试事件，可以这样启动：

```bash
N8N_WEBHOOK_PREFIX=webhook-test npm run dev
```

需要换 n8n 地址时：

```bash
N8N_BASE_URL=http://127.0.0.1:5678 npm run dev
```

## 主要契约

1. `POST /api/fast/stage-1` -> `product_record_id`、`product_brief`、`mood_boards[]`、`creative_plans[]`、`recommended_plan_id`、兼容字段 `hooks[]`
2. `POST /api/fast/stage-2` -> `script_record_id`、`script_preview`；请求携带已选 `creative_plan`
3. `POST /api/fast/stage-3` -> `video_task_record_id`、`task_preview`
4. `POST /api/workflow/stage-4` -> `video_url`、`segments[]`、`status`
5. `POST /api/workflow/stage-5` -> `storyboard_images[]`

Stage 1、Stage 2 和 Stage 3 的旧 n8n 内容入口已禁用，不再作为前端回退路径。Stage 4/5/6 仍由 n8n 负责媒体任务、轮询和合成。

可用 `http://localhost:4173/open-design.html?demo=1` 查看不调用真实模型的界面演示。
