# Codex Orchestrator Frontend

这是一个 Vue 3 + TypeScript 单页界面，用来提交需求，并展示任务 worktree、权限核验、越权次数、验证轮次、Codex 可见回复、变更文件、最终 diff 和人工审查。

## 安装与启动

Node 依赖只安装在当前前端目录：

```bash
npm ci --prefix orchestrator/frontend
npm --prefix orchestrator/frontend run dev
```

页面默认地址是 `http://127.0.0.1:5100`。开发服务器会把 `/api` 请求代理到 `http://127.0.0.1:8100`，因此需要同时启动 `orchestrator/backend`。

页面每两秒查询一次活动任务，机器流程完成后停止轮询并读取报告与 diff。自动测试通过仍显示“待人工审查”；审查人填写本地声明身份和说明后，可选择批准、要求修改或驳回。结论只能提交一次，并与页面所示 diff SHA-256 绑定。

旧任务会显示“历史记录不完整”，不会显示伪造的隔离、权限或审查数据，也不能提交审查。

## 测试与构建

```bash
npm --prefix orchestrator/frontend test
npm --prefix orchestrator/frontend run build
```

构建结果位于 `orchestrator/frontend/dist/`，该目录和 `node_modules/` 都不会提交到 Git。

第一版不包含账号、远程部署、任务取消、路由、Pinia、WebSocket 或并行任务。人工批准不会触发 commit、合并或部署。后端进程中断后，请先调用后端恢复接口，再回到页面继续查看原任务。
