# Codex Orchestrator

这是一个本机、单项目、严格串行的 Loop Engineering 基础 harness。单任务仍按原方式运行；人工拆分的长任务按页面中的子任务顺序逐个执行，每个子任务都放进独立 Git worktree，让 Codex 在最小权限下修改代码，由 Python 执行固定验证，并经过人工审查后才进入下一项。

```text
原仓库（控制面）
├── .git/
├── .codex-orchestrator/
│   ├── active.lock
│   ├── worktrees/<task-id>/       codex/<task-id> 专用工作区
│   ├── runs/<task-id>/            单任务状态、事件和审计产物
│   └── queues/<queue-id>/         长任务与嵌套的子任务运行记录
└── orchestrator/

任务流程
基线 commit
   ↓ 创建 branch + worktree
权限生效检查
   ↓
Codex turn 流式事件 → 固定验证 → 最多三轮修复
   ↓
最终 diff + machine_status
   ↓
人工提交一次 review_status

长任务流程
人工填写子任务顺序
   ↓
子任务 1 → 机器验证 → 人工批准
   ↓ 累计 Diff 作为下一 worktree 的 index 基线
子任务 2 → 机器验证 → 人工批准 → …… → 队列完成
```

## 运行方式

依赖安装在现有 Conda `account` 环境；Codex SDK 和 CLI 版本保持固定：

```bash
conda activate account
python -m pip install -r orchestrator/requirements.txt
python -m pip install -r orchestrator/backend/requirements.txt
npm ci --prefix orchestrator
npm ci --prefix orchestrator/frontend
```

命令行启动或恢复任务：

```bash
python -m orchestrator.codex_loop start --task-file orchestrator/task.example.json
python -m orchestrator.codex_loop resume --task-id <task-id>
python -m orchestrator.codex_loop queue-start --task-file orchestrator/queue.example.json
python -m orchestrator.codex_loop queue-show --queue-id <queue-id>
python -m orchestrator.codex_loop queue-resume --queue-id <queue-id>
```

`active.lock` 只表示某个 orchestrator 进程当前占用执行权。进程意外退出后，
过期锁可以被清除，但原任务的未完成状态仍然有效：新任务继续被禁止，必须先
`resume` 原任务；只有原任务进入机器终态后，下一任务才能启动。

查看隔离、权限和审计摘要，然后记录唯一一次人工结论：

```bash
python -m orchestrator.codex_loop show --task-id <task-id>
python -m orchestrator.codex_loop review \
  --task-id <task-id> \
  --decision approved \
  --reviewer "Local Reviewer" \
  --comment "已检查需求、测试与 diff" \
  --reviewed-diff-sha256 <raw-diff-sha256>
```

`decision` 还可填写 `changes_requested` 或 `rejected`。审查结论与当时的原始 diff SHA-256 绑定。单任务只记录一次结论；长任务子任务会追加保存每次审查，`changes_requested` 继续使用相同 worktree 和 thread，`rejected` 停止整个队列。worktree 在审查前发生变化、diff 含疑似密钥或任务尚未结束时都会拒绝提交。

网页版可用一个脚本启动：

```bash
./orchestrator/start.sh
```

页面和 API 统一从 `http://127.0.0.1:8100` 访问。脚本会把 `/api` 转发到
仅供本机进程通信的后端端口 `18100`。

## 状态含义

- `machine_status=success`：固定自动验证通过，不代表人工接受。
- `machine_status=manual_review`：三轮验证仍失败，需要人工判断。
- `machine_status=infrastructure_error`：隔离、权限、SDK 或本地工具发生故障。
- `review_status=pending`：机器流程结束，但尚无人工结论。
- `approved`、`changes_requested`、`rejected`：人工针对一份确定 diff 提交的最终结论。
- 长任务只有当前子任务机器验证通过且人工 `approved` 才会进入下一项；`waiting_review`、`changes_requested` 和 `infrastructure_error` 都会暂停队列。

本系统不会自动 commit、push、创建 PR、合并 main/master、连接生产数据库、运行迁移或部署。`approved` 也只表示该份 diff 被本地审查人接受。

## 权限边界

- Codex 的当前目录和唯一可写根是任务 worktree，原仓库与运行记录不向 Codex 开放。
- 审批模式为 deny-all；网络、Web Search、Apps、MCP、插件、multi-agent 和技能脚本关闭。
- 运行环境采用变量 allowlist，密钥、Token、数据库 URL、云与 Kubernetes/SSH 信息不传入任务。
- Git branch/commit 操作、生产数据库客户端和部署工具被拒绝并记录。
- Python 只执行源码中固定的验证命令，使用相同的无网络、脱敏环境，不执行 Codex 回复建议的任意命令。
- App Server 返回的实际权限比请求范围更宽或无法读取时，发送首个 prompt 前立即停止。

## 运行记录

```text
.codex-orchestrator/runs/<task-id>/
├── task.json                 原始需求，创建后不改
├── manifest.json             基线、branch、worktree、运行版本
├── permissions.json          请求权限与实际生效权限
├── state.json                中断恢复检查点
├── events.jsonl              连续序号、只追加的事件时间线
├── turns/turn-XX/            实际 prompt 与 Codex 可见回复
├── rounds/round-XX.json      验证轮次
├── logs/                     Codex 与固定验证的脱敏日志
├── changes/files.json        变更状态、内容哈希和增删行数
├── changes/final.diff        相对基线的完整脱敏 diff
├── result.json               机器结果与产物索引
├── review.json               人工提交后才出现，不可覆盖
└── report.md                 面向人的汇总
```

包含至少两个子任务的长任务单独保存，不复制进顶层 `runs`：

```text
.codex-orchestrator/queues/<queue-id>/
├── queue.json                不可变的名称、基线与子任务顺序
├── state.json                当前子任务和整体状态
├── events.jsonl              只追加的调度与审查事件
├── changes/cumulative.diff   已批准代码相对原始基线的累计 Diff
├── subtasks/<task-id>/       子任务自己的完整运行与审查历史
└── report.md                 长任务汇总
```

没有 `schema_version` 的旧任务按 `legacy_v0` 只读展示，并明确标注“历史记录不完整”。系统不会为旧记录补造缺失的 worktree、权限、prompt、diff 或审查信息，也不会恢复或审查旧任务。

## 核心模块

| 文件 | 职责 |
|---|---|
| `workspace.py` | 解析基线，创建并核验任务 branch/worktree |
| `policy.py` | 最小权限配置、环境 allowlist、生产命令阻断与实际权限核验 |
| `audit.py` | 顺序事件、prompt/回复、日志、文件清单和最终 diff |
| `codex_client.py` | 固定 SDK/runtime、deny-all thread、turn stream 和恢复核对 |
| `validation_runner.py` | 在任务 worktree 内执行固定分层验证 |
| `workflow.py` | 串联隔离、权限、Codex、验证、重试和机器结论 |
| `queue_workflow.py` | 固定顺序调度、人工审查门禁、累计 Diff 交接与故障恢复 |
| `review.py` | CLI/API 共用的单任务审查与队列追加审查规则 |
| `state.py` | 原子持久化、全局单执行锁、队列目录和敏感信息脱敏 |
| `report.py` 与 `templates/` | 渲染实际 prompt 和人工报告 |

## 测试

```bash
conda run -n account pytest -q orchestrator/tests
conda run -n account pytest -q orchestrator/backend/tests
npm --prefix orchestrator/frontend test
npm --prefix orchestrator/frontend run build
```

`orchestrator/tests/` 包含真实临时 Git 仓库测试，覆盖 worktree 身份、main 不变、脏改动不带入、权限收窄、事件顺序、完整 diff、敏感信息阻断、队列严格顺序、累计 Diff 继承、返修审查历史、驳回和故障恢复。
