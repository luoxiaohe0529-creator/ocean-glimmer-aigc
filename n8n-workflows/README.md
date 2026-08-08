# n8n 工作流模板

`public/` 中的文件来自本机当前“大海浮光 AIGC”主链路，并经过公开发布脱敏：

| 文件 | Webhook | 作用 |
| --- | --- | --- |
| `03-script-to-storyboard.json` | `ai-ad-script-to-video-task-v2` | 生成结构化分镜和视频提示词 |
| `04-video-generation.json` | `ai-ad-video-task-v2` | 创建、轮询并返回视频结果 |
| `05-storyboard-images.json` | `aigc-storyboard-images-v1` | 生成 9:16 分镜拍摄参考图 |

Stage 1（抓取、简报和 Hook）与 Stage 2（脚本生成）已迁移到 `python_service/`。旧 n8n 版本只作为迁移参考保存在 `legacy/`，新部署不需要激活它们。

这些模板默认 `active: false`。导入后必须：

1. 绑定自己的 n8n Credentials。
2. 替换飞书 App Token / Table ID 占位符。
3. 配置图像、视频与对象存储供应商。
4. 检查 Webhook 路径。
5. 使用测试数据逐条执行，再发布为生产 Webhook。

公开模板不包含真实密钥、凭证 ID、业务记录或本机路径。

## 成片流程的本地依赖

`04-video-generation.json` 的多段拼接节点面向自托管 n8n，需要运行环境提供 `ffmpeg`、`curl`，并允许 Code 节点使用 `child_process` 和 `fs`。生产部署建议将下载、拼接和上传迁移到独立媒体 Worker，避免长任务占用 n8n 主进程。
