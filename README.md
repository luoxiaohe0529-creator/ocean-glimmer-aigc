# 大海浮光 AIGC 广告视频工作台

一套面向商业广告生产的多阶段 AI 工作流。系统从产品链接、营销主题和参考图片出发，将产品事实逐层转换为 Mood Board、12 条营销 Hook、导演脚本、摄影分镜、角色参考图与无字幕广告成片。

项目重点不是单次“文生视频”，而是建立可选择、可追踪、可复用的广告生产链路：知识库负责方法，模型负责推理，Python 负责内容契约，n8n 负责异步媒体任务，前端负责人工决策。

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
  CRAWLER --> FACTS["DeepSeek · 产品事实整理"]
  FACTS --> KB1["广告策划 Wiki"]
  KB1 --> GEMINI1["Gemini 3.1 Pro · Hook 与 Mood Board"]
  GEMINI1 --> SELECT["用户选择 Hook"]
  SELECT --> KB2["编剧导演 Wiki"]
  KB2 --> GEMINI2["Gemini 3.1 Pro · 导演脚本"]
  GEMINI2 --> KB3["摄影摄像 Wiki"]
  KB3 --> GEMINI3["Gemini 3.1 Pro · 摄影分镜"]
  GEMINI3 --> N8N["n8n · 图像与视频任务编排"]
  N8N --> VIDEO["无字幕广告成片"]
```

### 01 广告策划

Stage 1 严格分为两次模型调用：

1. DeepSeek 仅整理产品名称、品类、目标人群、卖点、痛点、使用场景和限制，不生成创意。
2. 系统读取广告策划 Wiki 后，由 Gemini 3.1 Pro 生成 12 条 Hook、简要 Mood Board 和供 Stage 2 使用的隐藏创意板。

这一分层避免产品事实与广告想象互相污染。

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
| 策划模型 | DeepSeek | 可验证产品事实与简报 |
| 创意模型 | Gemini 3.1 Pro via KIE.ai | Hook、Mood Board、导演脚本、摄影分镜 |
| 编排层 | n8n | TOS 上传、图像/视频任务、等待、轮询、回写 |
| 知识层 | 飞书 Wiki | 广告策划、编剧导演、摄影摄像模板 |
| 媒体层 | 火山 TOS、FFmpeg | 公网素材与本地后期处理 |

## 唯一入口

整个项目只需要一个启动命令：

```bash
npm start
```

该命令统一管理前端、Python 服务和 n8n，避免重复启动造成 `EADDRINUSE`。

默认地址：

- 工作台：<http://localhost:4174>
- Python 健康检查：<http://127.0.0.1:8787/health>
- n8n：<http://127.0.0.1:5678>

## 本地安装

### 1. 安装依赖

```bash
npm install
python3 -m pip install -r python_service/requirements.txt
```

### 2. 配置环境

```bash
cp .env.example .env
```

按需填写 DeepSeek、KIE.ai、飞书和媒体服务配置。真实密钥只能存放在 `.env` 或 n8n Credentials 中。

### 3. 安装 TOS 上传工作流

首次运行前，在 n8n 中准备兼容 S3 的火山 TOS Credential，然后执行：

```bash
npm run install:asset-upload
```

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
│   ├── deepseek.py            # 产品事实模型
│   └── gemini_kie.py          # Gemini 3.1 Pro 通道
├── n8n-workflows/public/      # 脱敏公开工作流
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

## 安全与公开边界

公开仓库不包含：

- `.env` 与任何 API Key
- n8n 数据库、Credential 或执行历史
- 飞书 App Secret、Base Token 和真实业务记录
- 火山 TOS 私有地址与本机绝对路径
- 运行日志、缓存、恢复文件和历史备份

## 项目价值

这个项目展示的不只是模型 API 调用，还包括 AI 产品流程设计、知识库分层、结构化提示词工程、多模型路由、异步任务编排、对象存储、前后端状态管理和可观测的数据交接。它适合作为 AI 产品经理、AI 应用工程师、Agent 工作流工程师或 AIGC 创意技术岗位的作品集项目。

## 进一步阅读

- [系统架构](docs/ARCHITECTURE.md)
- [安装说明](docs/SETUP.md)
- [接口契约](docs/WORKFLOW_CONTRACTS.md)
- [飞书知识库接入](docs/FEISHU_KNOWLEDGE.md)
- [GitHub 发布检查](docs/GITHUB_RELEASE.md)
