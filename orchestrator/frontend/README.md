# Codex Orchestrator Frontend

这是一个 Vue 3 + TypeScript 单页界面，可以提交单任务，也可以把长任务人工拆成多个有固定顺序的子任务。页面展示队列进度、当前子任务 worktree、权限核验、验证轮次、Codex 可见回复、变更文件、diff 和人工审查。

## 安装与启动

Node 依赖只安装在当前前端目录：

```bash
npm ci --prefix orchestrator/frontend
npm --prefix orchestrator/frontend run dev
```

页面默认地址是 `http://127.0.0.1:8100`。通过 `orchestrator/start.sh` 启动时，开发服务器会把 `/api` 请求代理到仅供本机进程通信的后端端口 `18100`。

提交区可切换“单任务 / 长任务”。长任务默认至少两个子任务，可以添加、删除、上移或下移卡片；卡片顺序就是执行顺序，不显示依赖选择。页面每两秒查询活动队列，自动切换到当前子任务；机器流程完成后读取报告与 diff。批准后进入下一项，要求修改后继续显示原子任务的新轮次，驳回后停止队列。每次结论都与页面所示 diff SHA-256 绑定。

浏览器只保存最近一次任务类型及编号。刷新后，页面从后端文件记录恢复完整队列和当前子任务，不把调度状态保存在浏览器中。

旧任务会显示“历史记录不完整”，不会显示伪造的隔离、权限或审查数据，也不能提交审查。

## 测试与构建

```bash
npm --prefix orchestrator/frontend test
npm --prefix orchestrator/frontend run build
```

构建结果位于 `orchestrator/frontend/dist/`，该目录和 `node_modules/` 都不会提交到 Git。

当前版本不包含账号、远程部署、任务取消、路由、Pinia、WebSocket 或并行任务。人工批准不会触发 commit、合并或部署。后端进程中断后，请先调用对应的单任务或长任务恢复接口，再回到页面继续查看。
