# 安装与配置

## 环境要求

- Node.js 22+
- Python 3.10+
- n8n 2.x
- `unzip`（用于解析 DOCX / XLSX / PPTX）
- FFmpeg（后期剪辑、配乐和字幕需要）
- Chromium（商品页面 Playwright 抓取服务使用）

公开的 04 成片模板还需要自托管 n8n 允许 Code 节点访问 `child_process` 和 `fs`。托管版 n8n 或受限运行环境应改用独立媒体 Worker。

## 前端与 Python 服务

```bash
python3 -m pip install -r python_service/requirements.txt
npm exec playwright install chromium
cp .env.example .env
npm run dev
```

在 `.env` 中填写 `DEEPSEEK_API_KEY` 与 `KIE_API_KEY`。`FFMPEG_PATH` 可以留空，服务会从系统 `PATH` 查找 ffmpeg；只有在自定义安装路径时才需要填写。Stage 1 创意生成、Stage 2 中文导演脚本和 Stage 3 摄影分镜统一通过 KIE.ai 的 Gemini 3.1 Pro 通道。要启用动态知识筛选器，还需配置飞书 App 凭证和三个角色 Wiki；详见 [飞书知识库接入](FEISHU_KNOWLEDGE.md)。`npm start` 会从唯一入口统一启动 Python、Node 网关与 Playwright 商品爬虫，n8n 需要单独启动。

默认地址：`http://localhost:4173/open-design.html`

服务端默认连接：`http://127.0.0.1:5678/webhook`

商品爬虫默认监听：`http://127.0.0.1:9876`。

如需使用 n8n 编辑器的测试 Webhook：

```bash
N8N_WEBHOOK_PREFIX=webhook-test npm run dev
```

## n8n

1. 打开 `n8n-workflows/public/`。
2. 逐个导入所需 JSON。
3. 在 n8n 中创建并绑定 Credentials：
   - 飞书：推荐使用自定义 Header Auth 或 OAuth
   - KIE.ai：Header Auth，供 GPT Image 2 / Nano Banana 2 图片任务使用
   - Seedance：官网 API 对应的 Bearer Auth，保留中文视频链路
   - 对象存储：供应商凭证或签名服务
4. 将模板中的占位符替换为自己的资源标识。
5. 发布工作流，确认 Webhook 路径与 `.env` 一致。

## 安全要求

- 不要把密钥直接写进 HTTP Request 的 Header 文本框。
- 不要把密钥写进 Code、Set、飞书字段或 `.env.example`。
- 真实凭证只保存在 n8n Credentials。
- 曾经粘贴到聊天、截图或 Git 历史中的 Token 应立即轮换。

## 验证

```bash
npm run check
curl http://127.0.0.1:4173/api/health
curl 'http://127.0.0.1:4173/api/knowledge/filters?content_type=高端TVC'
```

`/api/health` 会分别报告前端、Python 与 n8n 的连接状态。

## 常见问题

### Stage 1 / 2 返回 502

Python 服务没有启动，或 `PYTHON_SERVICE_URL` 配置错误。

### Stage 3 / 4 / 5 返回 502

n8n 没有启动，或 `N8N_BASE_URL` 配置错误。

### 请求返回 404

工作流未发布，或 Webhook 路径与 `.env` 中对应值不一致。

### Office 文件无法解析

仅支持 DOCX、XLSX 和 PPTX。旧版 DOC / XLS / PPT 需先另存为新版格式。

### 视频长时间没有结果

检查 n8n 执行记录中的供应商任务 ID、轮询次数和失败分支。模型请求节点应设置重试与明确的错误响应。
