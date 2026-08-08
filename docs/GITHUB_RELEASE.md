# GitHub 发布指南

这份清单用于把“大海浮光 AIGC 工作台”作为可理解、可运行、无敏感信息的公开项目发布。

## 发布内容

- `frontend/open-design.html`：当前正式前端
- `frontend/server.mjs`：本地服务和 n8n 同源代理
- `frontend/demo/`：公开演示成片
- `n8n-workflows/public/`：脱敏后的正式工作流
- `docs/`：架构、安装和接口契约
- `.env.example`：不含真实密钥的配置模板
- `scripts/`：工作流导出和安全检查

## 不应提交

- `.env`
- `frontend/backups/`
- `node_modules/`
- n8n SQLite 数据库、WAL 和 SHM 文件
- 私有工作流导出、执行历史和终端日志
- API Key、Bearer Token、Credentials ID
- 飞书 App Token、Table ID 和真实记录
- 对象存储桶、私有域名与本机绝对路径

这些内容已经写入 `.gitignore`，并会由 `npm run check` 检查配置模板和已跟踪文件。

## 发布前检查

在仓库根目录执行：

```bash
npm run check
git status --short
```

`npm run check` 会检查：

1. Node.js 服务端语法。
2. 公开 n8n JSON 是否可解析并保持未激活。
3. 公开文件中是否包含已知密钥、Token 或私有标识。
4. `.env`、n8n 数据库和其他本地运行文件没有进入 Git 跟踪范围。

随后手动确认：

- README 中的功能与当前界面一致。
- `frontend/open-design.html?demo=1` 可以正常展示三阶段流程。
- 两个演示视频可以从仓库打开。
- 公开工作流全部来自“大海浮光 AIGC”正式版。
- 工作流导入后只需要重新绑定 Credentials 和业务配置。

## 首次发布命令

先在 GitHub 创建一个空仓库，然后在本地执行：

```bash
git add .
git commit -m "feat: publish Dahai Fuguang AIGC workbench"
git branch -M main
git remote add origin https://github.com/<your-account>/<your-repository>.git
git push -u origin main
```

如果已经存在 `origin`，不要重复添加，先执行：

```bash
git remote -v
```

## GitHub 仓库建议

**Description**

```text
A role-based AI advertising video workbench powered by n8n, LLMs, image models and video generation.
```

**Topics**

```text
aigc
ai-video
n8n
workflow-automation
advertising
storyboard
deepseek
seedance
feishu
```

## 发布后验证

1. 在新的目录克隆公开仓库。
2. 按 README 执行安装和启动。
3. 使用 Demo 模式验证前端。
4. 向一个全新的 n8n 实例导入公开工作流。
5. 确认仓库搜索不到真实邮箱、Token、密钥和业务数据。
