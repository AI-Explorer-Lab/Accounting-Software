# Codex Orchestrator Frontend

这是一个 Vue 3 + TypeScript 单页界面，用来提交一条功能需求和至少一条验收标准，并展示现有编排器的运行阶段、验证轮次和最终报告。

## 安装与启动

Node 依赖只安装在当前前端目录：

```bash
npm ci --prefix orchestrator/frontend
npm --prefix orchestrator/frontend run dev
```

页面默认地址是 `http://127.0.0.1:5100`。开发服务器会把 `/api` 请求代理到 `http://127.0.0.1:8100`，因此需要同时启动 `orchestrator/backend`。

页面每两秒查询一次活动任务，任务完成后停止轮询并读取报告。最近一次任务编号保存在浏览器本地存储中，刷新页面后可继续查询；完整任务数据仍只保存在 `.codex-orchestrator/`。

## 测试与构建

```bash
npm --prefix orchestrator/frontend test
npm --prefix orchestrator/frontend run build
```

构建结果位于 `orchestrator/frontend/dist/`，该目录和 `node_modules/` 都不会提交到 Git。

第一版不包含账号、远程部署、任务取消、路由、Pinia、WebSocket 或并行任务。后端进程中断后，请先调用后端恢复接口，再回到页面继续查看原任务。
