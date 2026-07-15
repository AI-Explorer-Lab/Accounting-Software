# Codex Orchestrator API

这个 FastAPI 服务把网页请求交给现有 `orchestrator.codex_loop`。它不创建第二套任务数据，也不修改核心编排逻辑；任务、状态和报告仍保存在仓库根目录的 `.codex-orchestrator/`。

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
  --reload --host 127.0.0.1 --port 8100
```

默认配置位于 `config/app.yaml`。服务只监听本机地址，并只允许 `http://127.0.0.1:5100` 和 `http://localhost:5100` 跨域访问。

## 接口

| 方法 | 地址 | 用途 |
|---|---|---|
| `GET` | `/api/health` | 检查 API 是否可用，不启动 Codex |
| `POST` | `/api/tasks` | 提交需求，立即返回 `202` 和任务编号 |
| `GET` | `/api/tasks/{task_id}` | 查询阶段、验证轮次和最终状态 |
| `POST` | `/api/tasks/{task_id}/resume` | 后端中断后恢复原任务和原 thread |
| `GET` | `/api/tasks/{task_id}/report` | 读取完成后的 `report.md` |

创建任务示例：

```bash
curl -X POST http://127.0.0.1:8100/api/tasks \
  -H 'Content-Type: application/json' \
  -d '{"requirement":"交易列表支持按最低金额筛选","acceptance_criteria":["传入 min_amount=100 时，只返回金额大于或等于 100 的交易"]}'
```

API 在单工作线程中执行 Codex，因此 HTTP 请求不会等待开发和测试结束。同一时间只能有一个活动任务；已有未完成任务时，先使用恢复接口，不要创建新任务。

## 测试

后端测试使用假的 workflow 和临时任务目录，不会真实调用 Codex：

```bash
env PYTHONPYCACHEPREFIX=/private/tmp/accounting-pycache \
  conda run -n account pytest -q orchestrator/backend/tests
```

真实运行生成的脱敏日志、`result.json` 和 `report.md` 位于 `.codex-orchestrator/runs/<task-id>/`。
