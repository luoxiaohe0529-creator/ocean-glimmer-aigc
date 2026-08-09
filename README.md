# 大海浮光 AIGC 广告视频工作台

一套面向商业广告生产的多阶段 AI 工作流。系统从产品链接、营销主题和参考图片出发，将产品事实逐层转换为 Mood Board、12 条营销 Hook、导演脚本、摄影分镜、角色参考图与无字幕广告成片。

项目重点不是单次“文生视频”，而是建立可选择、可追踪、可复用的广告生产链路：知识库负责方法，模型负责推理，Python 负责内容契约，n8n 负责异步媒体任务，前端负责人工决策。

> Portfolio-grade AI application prototype：用人机协同把“产品事实 → 创意方案 → 导演脚本 → 摄影分镜 → 异步媒体任务”串成一条可追踪的生产链。

## 60 秒看懂

| 你想看什么 | 入口 |
| --- | --- |
| 先看真实产出 | [中文版成片](frontend/showcase/videos/中文视频-国内电商/美白奶罐_高端TVC_0729_0434.mp4) · [英文版成片](frontend/showcase/videos/英文视频-跨境电商/veo-2_字幕.mp4) |
| 看工作台 | [真实运行快照](frontend/showcase/workbench/open-design-demo.html?demo=1) · [中英文视频目录](frontend/showcase/README.md) |
| 看系统怎么拆 | [系统架构](docs/ARCHITECTURE.md) |
| 看一次完整产品决策 | [Case Study](docs/CASE_STUDY.md) |
| 看质量和安全边界 | [GitHub 发布检查](docs/GITHUB_RELEASE.md) · `npm run check` |

## README 视频预览

下面两个播放器使用 GitHub 附件托管，打开 README 后即可直接点击播放键观看。

### 中文成片

https://github.com/user-attachments/assets/74734f72-d492-4dd3-a5c0-b4d841303856

### English cut

https://github.com/user-attachments/assets/8b56f676-ef79-4034-8571-fb77ebd9df3a

如果只有一分钟，先看上面的中英文成片和 [Case Study](docs/CASE_STUDY.md)，再看 [frontend/server.mjs](frontend/server.mjs)、[python_service/server.py](python_service/server.py) 与 [n8n-workflows/public/04-video-generation.json](n8n-workflows/public/04-video-generation.json)。

## 这个项目解决什么问题

传统的“调用一个模型生成广告”很难稳定复用：产品事实容易被创意污染，用户无法在关键节点做选择，异步媒体任务也很难和上游创意决策重新关联。

这个工作台把流程拆成三个可验证的决策阶段：

1. Stage 1 抽取产品事实，读取广告策划 Wiki，生成 12 个可比较的 Hook、Mood Board 和完整创意方案。
2. 用户选择 Hook/方案后，Stage 2 生成导演脚本；Stage 3 再把脚本转换为摄影分镜和视频生成提示词。
3. n8n 只负责图片、视频、轮询、对象存储和结果回写等异步媒体任务。

每一阶段都通过结构化字段、ID、状态和 trace 交接，而不是把上一阶段的自然语言全文直接塞给下一阶段。

## 核心能力

- 抓取产品页面并区分事实信息与创意推演
- 根据真人口播、好物推荐、高端 TVC 及其子类型匹配广告模板
- 一次生成 12 条差异化 Hook，每条绑定简要 Mood Board 与隐藏创意板
- 将用户选中的 Hook 原样传递给编剧导演与摄影摄像阶段
- 生成结构化逐镜脚本、英文视频提示词和连续性约束
- 上传产品图到火山 TOS，前端只保存可复用的公网 URL
- 调用异步图像与视频模型，处理轮询、分段结果和成片回写
- 支持 480p、720p、1080p 分辨率，并在全链路保持用户选择
- 最终视频默认禁止字幕、标题卡、Logo、水印、UI 和渲染文字

## 生产流程

```mermaid
flowchart LR
  INPUT["产品链接 / 营销主题 / 产品图片"] --> CRAWLER["产品页面抓取"]
  CRAWLER --> FACTS["豆包 Responses · 产品事实整理"]
  FACTS --> KB1["广告策划 Wiki"]
  KB1 --> DOUBAO1["豆包 Responses · Hook 与 Mood Board"]
  DOUBAO1 --> SELECT["用户选择 Hook"]
  SELECT --> KB2["编剧导演 Wiki"]
  KB2 --> GEMINI2["Gemini 3.1 Pro · 导演脚本"]
  GEMINI2 --> KB3["摄影摄像 Wiki"]
  KB3 --> GEMINI3["Gemini 3.1 Pro · 摄影分镜"]
  GEMINI3 --> N8N["n8n · 图像与视频任务编排"]
  N8N --> VIDEO["无字幕广告成片"]
```

### 01 广告策划

Stage 1 有两种运行模式，但两种模式都会读取广告策划飞书 Wiki：

1. 默认快速模式用一次豆包 Responses 生成结构化 Stage 1 结果，同时仍读取并注入广告策划 Wiki，减少一次模型等待。
2. 将 `STAGE1_FAST_MODE=0` 后，豆包先整理产品名称、品类、目标人群、卖点、痛点、使用场景和限制；系统读取广告策划 Wiki 后，再由豆包生成 12 条 Hook、简要 Mood Board 和供 Stage 2 使用的隐藏创意板。

两种模式都保留“产品资料 → 广告策划 Wiki → 创意生成”的知识约束；完整模式额外把产品事实模型单独拆出，进一步避免产品事实与广告想象互相污染。

### 02 编剧导演

用户选择 Hook 后，系统读取对应导演模板。Gemini 3.1 Pro 继承产品简报、Mood Board、Slogan、开篇方式、节奏骨架、视觉密码、必须出现元素和禁止事项，输出覆盖完整时长的导演脚本。

### 03 摄影摄像

摄影阶段不重新策划方向，只把导演脚本转换为可生成的逐镜任务，包括时间、景别、主体动作、产品露出、光线、材质、运镜、转场、声音和连续性锚点。

### 04 媒体生成

n8n 处理产品图对象存储、分镜图、角色图、视频任务提交、状态轮询和结果回写。复杂的异步媒体链路留在编排器中，直接 HTTP + LLM + JSON 的内容阶段统一保留在 Python 服务中。

## 知识架构

系统只读取三个飞书 Wiki 文档作为方法论知识源：

```text
广告策划知识库
├── 真人口播带货母模板
├── 好物推荐母模板
└── 高端 TVC
    ├── 品牌叙事 TVC
    ├── 社媒氛围快剪 TVC
    └── 产品材质视觉 TVC

编剧导演知识库
├── 真人口播导演模板
├── 好物推荐导演模板
└── 高端 TVC 视觉导演模板
    ├── 电影叙事导演
    ├── 社媒氛围快剪导演
    └── 产品材质视觉导演

摄影摄像知识库
├── 真人口播摄影模板
├── 好物推荐摄影模板
└── 高端 TVC 摄影模板
    ├── 电影叙事摄影
    ├── 快剪视觉摄影
    └── 微距材质摄影
```

产品、Hook、脚本与视频任务属于运行数据，不会被误当成知识库内容。

## 技术架构

| 层级 | 技术 | 职责 |
| --- | --- | --- |
| 交互层 | HTML、CSS、JavaScript | 产品输入、Hook 选择、阶段确认、媒体预览 |
| 网关层 | Node.js | 静态服务、同源代理、文件解析、统一入口 |
| 内容层 | Python | 抓取、知识检索、模型调用、结构化契约、媒体适配 |
| Stage 1 模型 | 豆包 Responses API | 产品图理解、可验证产品事实、Hook、Mood Board、完整创意方案 |
| 英文 Stage 2 文本模型 | DeepSeek | 英文脚本路径的文本生成 |
| Stage 2/3 中文文本模型 | Gemini 3.1 Pro via KIE.ai | 导演脚本、摄影分镜 |
| 编排层 | n8n | TOS 上传、图像/视频任务、等待、轮询、回写 |
| 知识层 | 飞书 Wiki | 广告策划、编剧导演、摄影摄像模板 |
| 媒体层 | 火山 TOS、FFmpeg | 公网素材与本地后期处理 |

## 唯一入口

整个项目只需要一个启动命令：

```bash
npm start
```

该命令统一管理前端、Python 服务和商品爬虫，避免本地服务重复启动造成 `EADDRINUSE`。n8n 是独立服务，需要单独启动。

默认地址：

- 工作台：<http://localhost:4174>
- Python 健康检查：<http://127.0.0.1:8787/health>
- n8n：<http://127.0.0.1:5678>

## 本地安装

### 1. 安装依赖

```bash
npm install
python3 -m pip install -r python_service/requirements.txt
npm exec playwright install chromium
```

### 2. 配置环境

```bash
cp .env.example .env
```

按需填写 DeepSeek、豆包、KIE.ai、飞书和媒体服务配置。真实密钥只能存放在本机 `.env` 或 n8n Credentials 中，不能写进 Python 源码。

启动 n8n 后，再确认 `.env` 中的 `N8N_BASE_URL`、Webhook 路径和媒体工作流配置一致。

### 3. 配置 Python 图片上传

图片由 Python 使用 TOS SDK 直接上传。如果凭据已保存在本机 n8n 中，可执行一次安全迁移：

```bash
npm run migrate:tos-credential
```

迁移只写入本机 `.env`，不会显示密钥，也不会写入 Git。

### 4. 启动

```bash
npm start
```

## 项目结构

```text
.
├── frontend/
│   ├── open-design.html       # 唯一正式工作台
│   ├── portfolio.html         # 作品集页面
│   └── server.mjs             # Node 网关与统一代理
├── python_service/
│   ├── server.py              # Stage 1 / 2 / 3 API
│   ├── prompts.py             # 结构化提示词契约
│   ├── feishu_knowledge.py    # Wiki-only 知识读取器
│   ├── deepseek.py            # 英文 Stage 2 文本模型
│   ├── doubao.py              # Stage 1 豆包 Responses 多模态通道
│   └── gemini_kie.py          # Stage 2/3 Gemini 3.1 Pro 通道
├── n8n-workflows/public/      # 脱敏公开工作流
├── scraper-service.mjs        # Playwright 商品爬虫服务
├── docs/knowledge/            # 三份知识库整理版
├── docs/                      # 架构、配置与接口文档
├── scripts/                   # 检查、导出和安装工具
├── .env.example
└── package.json
```

## 质量检查

```bash
npm run check
```

检查范围包括：

- Node.js 语法与唯一入口契约
- Python 单元测试
- 公开 n8n 工作流结构
- 私密 Token、对象存储地址和本机路径泄漏
- Stage 1 → Stage 2 → Stage 3 数据传递约束

GitHub Actions 会在 push 和 Pull Request 时自动运行同一套检查。

## 安全与公开边界

公开仓库不包含：

- `.env` 与任何 API Key
- n8n 数据库、Credential 或执行历史
- 飞书 App Secret、Base Token 和真实业务记录
- 火山 TOS 私有地址与本机绝对路径
- 运行日志、缓存、恢复文件和历史备份

合并前请先完成[密钥轮换与合并前安全清单](docs/SECRET_ROTATION.md)。当前文件的清理和 CI 扫描不能让已经进入 Git 历史的旧凭证自动失效。

## 项目价值

这个项目展示的不只是模型 API 调用，还包括 AI 产品流程设计、知识库分层、结构化提示词工程、多模型路由、异步任务编排、对象存储、前后端状态管理和可观测的数据交接。它适合作为 AI 产品经理、AI 应用工程师、Agent 工作流工程师或 AIGC 创意技术岗位的作品集项目。

## 进一步阅读

- [系统架构](docs/ARCHITECTURE.md)
- [安装说明](docs/SETUP.md)
- [接口契约](docs/WORKFLOW_CONTRACTS.md)
- [飞书知识库接入](docs/FEISHU_KNOWLEDGE.md)
- [Case Study：一次完整的产品决策](docs/CASE_STUDY.md)
- [GitHub 发布检查](docs/GITHUB_RELEASE.md)
- [密钥轮换与合并前安全清单](docs/SECRET_ROTATION.md)
