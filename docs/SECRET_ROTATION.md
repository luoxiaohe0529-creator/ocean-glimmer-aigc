# 密钥轮换与合并前安全清单

当前仓库已经移除了工作区文件中的真实凭证，但如果旧值曾经进入 Git 历史，删除当前文件并不会让旧值失效。合并前必须在对应服务后台作废旧值，再生成新值。

## 必须轮换的凭证

逐项确认旧值已经失效，不要把新值粘贴到 Issue、Pull Request、聊天记录或 shell 命令中：

- 飞书：App Secret、Wiki/知识库访问 Token，以及仍在使用的 Base Token。
- 模型服务：DeepSeek、KIE.ai、Minimax、Topaz 等 API Key。
- 火山 TOS：Access Key、Secret Key，以及绑定在 n8n Credential 中的对象存储凭证。
- 其他外部服务：检查 `.env`、n8n Credentials 和部署平台环境变量中是否还有同一批旧值。

## 推荐操作顺序

1. 在各服务后台撤销或轮换旧凭证，并记录轮换时间，不记录凭证内容。
2. 更新本机 `.env`、n8n Credentials 和部署环境变量；`.env` 只保存在本机，不要提交。
3. 先用 `PYTHON_MOCK_MODE=1 npm run check` 验证仓库结构，再用新凭证做一次最小化健康检查。
4. 在 GitHub PR 的 Checks 区确认 `Repository checks / check` 为绿色。
5. 完成轮换后，将 PR 从 Draft 改为 Ready for review，再合并到 `main`。

## 历史提交说明

本 PR 清理的是当前分支可见文件，不会自动改写已有提交。若 GitHub Secret Scanning 或安全审计仍发现旧值：

- 先确认对应凭证已经作废；
- 再评估是否需要使用 `git filter-repo` 重写公开历史；
- 重写历史会改变提交 ID，并要求所有协作者重新同步，不能在没有明确决定的情况下直接强推。

## 合并前记录

- [ ] 旧飞书凭证已作废并重新生成
- [ ] 旧模型 API Key 已作废并重新生成
- [ ] 旧 TOS 凭证已作废并重新生成
- [x] 当前文件通过公开密钥扫描
- [x] GitHub Actions 检查通过
- [ ] PR 已从 Draft 改为 Ready
