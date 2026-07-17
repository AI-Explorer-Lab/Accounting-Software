# Codex Orchestrator API

这个 FastAPI 服务把网页请求交给现有 `orchestrator.codex_loop`。它不创建第二套任务数据；单任务来自 `.codex-orchestrator/runs/`，长任务及其子任务来自 `.codex-orchestrator/queues/`。CLI 与 API 复用相同的调度和人工审查规则。

## 安装

所有 Python 依赖都安装到现有 Conda `account` 环境，不创建 `.venv`：

```bash
conda activate account
python -m pip install -r orchestrator/requirements.txt
python -m pip install -r orchestrator/backend/requirements.txt
npm ci --prefix orchestrator
```

最后一条命令安装现有编排器固定版本的 Codex runtime。服务继续复用本机 Codex 登录，不使用 API Key。

## 启动

在仓库根目录运行：

```bash
conda run -n account uvicorn orchestrator.backend.main:app \
  --reload --host 127.0.0.1 --port 18100
```

通过 `orchestrator/start.sh` 启动时，页面和 API 统一从
`http://127.0.0.1:8100` 访问；`18100` 仅用于 Vite 与 FastAPI 之间的本机通信。
默认配置位于 `config/app.yaml`，并只允许来自 8100 端口的本机页面跨域访问。

## 接口

| 方法 | 地址 | 用途 |
|---|---|---|
| `GET` | `/api/health` | 检查 API 是否可用，不启动 Codex |
| `POST` | `/api/tasks` | 提交需求，立即返回 `202` 和任务编号 |
| `GET` | `/api/tasks/{task_id}` | 查询阶段、验证轮次和最终状态 |
| `POST` | `/api/tasks/{task_id}/resume` | 后端中断后恢复原任务和原 thread |
| `GET` | `/api/tasks/{task_id}/report` | 读取完成后的 `report.md` |
| `GET` | `/api/tasks/{task_id}/diff` | 只读获取脱敏后的最终 diff |
| `POST` | `/api/tasks/{task_id}/review` | 提交一次人工结论并绑定 diff SHA-256 |
| `POST` | `/api/queues` | 提交至少两个有固定顺序的子任务 |
| `GET` | `/api/queues/{queue_id}` | 查询整体进度和当前子任务 |
| `POST` | `/api/queues/{queue_id}/resume` | 环境故障修复后恢复当前子任务 |
| `GET` | `/api/queues/{queue_id}/report` | 读取长任务汇总报告 |
| `GET` | `/api/queues/{queue_id}/diff` | 读取已批准的最终累计 Diff |

创建任务示例：

```bash
curl -X POST http://127.0.0.1:8100/api/tasks \
  -H 'Content-Type: application/json' \
  -d '{"requirement":"交易列表支持按最低金额筛选","acceptance_criteria":["传入 min_amount=100 时，只返回金额大于或等于 100 的交易"]}'
```

API 在单工作线程中执行 Codex，因此 HTTP 请求不会等待开发和测试结束。同一时间只能有一个活动任务；已有未完成任务时，先使用恢复接口，不要创建新任务。

创建长任务时，`subtasks` 数组顺序就是唯一执行顺序，不接收依赖字段。每项分别包含 `requirement` 和至少一条 `acceptance_criteria`。当前子任务机器流程结束后，仍使用 `/api/tasks/{task_id}`、`report`、`diff` 和 `review` 查看及审查；批准后后台单工作线程才会执行下一项。

审查请求包含 `decision`、`reviewer`、`comment` 和 `reviewed_diff_sha256`。只允许 `approved`、`changes_requested`、`rejected`；任务未结束、diff 已变化、diff 含疑似密钥或旧任务时返回冲突。单任务结论不可覆盖；队列子任务的多次返修审查按历史追加保存。`reviewer` 是本地声明身份，不是登录认证身份。

## 测试

后端测试使用假的 workflow 和临时任务目录，不会真实调用 Codex：

```bash
env PYTHONPYCACHEPREFIX=/private/tmp/accounting-pycache \
  conda run -n account pytest -q orchestrator/backend/tests
```

没有 schema version 的旧任务只读展示，并明确标记历史信息不完整；不能恢复或提交审查。系统不会自动合并或部署。
