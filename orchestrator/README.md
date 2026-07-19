# Codex Orchestrator

这是一个本机、文件化、严格受控的 Loop Engineering Harness。它在原有“隔离 worktree 中生成代码 → 固定验证 → 同线程修复 → 人工审查”链路上增加了冻结 Context、本地离线 MCP、自动规划、独立规范/架构评估、中期记忆、自动提交与归档。Generator 仍是现有 Codex；外部知识和 Git 写操作只由控制面执行。

```text
原仓库（控制面）
├── .git/
├── .codex-orchestrator/
│   ├── active.lock
│   ├── worktrees/<task-id>/       codex/<task-id> 专用工作区
│   ├── runs/<task-id>/            单任务状态、事件和审计产物
│   └── queues/<queue-id>/         长任务与嵌套的子任务运行记录
└── orchestrator/

增强任务流程（通过 Web/API 启用）
任务输入 → 冻结 generation Context → Codex Generator
   ↓
固定语法/逻辑验证 → 冻结 evaluation Context
   ↓
独立规范/架构评估 → 同一 Generator thread 修复（总计最多三轮）
   ↓
人工审查精确 Diff 与 commit subject
   ↓
任务分支单次 commit → 本地归档/中期记忆 → Knowledge-Base draft outbox

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
  --commit-subject "implement reviewed change" \
  --reviewed-diff-sha256 <raw-diff-sha256>
```

`decision` 还可填写 `changes_requested` 或 `rejected`。审查结论与原始 Diff SHA-256 绑定。Web/API 审批还会把单行 commit subject 一并绑定；批准后控制面只暂存已审查文件，并在 `codex/<task-id>` 创建一个快照 commit。队列子任务的 commit 始终以队列原始基线为 parent，内容是截至该子任务的累计快照。任何额外文件、HEAD/branch/tree 变化、敏感内容、空 Diff 或缺失 Git identity 都会失败关闭。

网页版可用一个脚本启动：

```bash
./orchestrator/start.sh
```

页面和 API 统一从 `http://127.0.0.1:8100` 访问。脚本会把 `/api` 转发到
仅供本机进程通信的后端端口 `18100`。

增强 Harness 默认读取 `orchestrator/backend/config/app.yaml`：Accounting 项目的知识消费 actor 是 `zhangsan`，归档 writer 是 `orchestrator`，MCP registry 是 `/Users/mon/Documents/mcp/registry.json`。MCP 使用官方 Python SDK 和本机 `stdio`，read/archive 两种模式工具集合严格分离，均禁用网络。Generator 只收到带来源和哈希的冻结快照，不能直接访问 Knowledge-Base 或 MCP。

创建页保留“单任务”和“手工长任务”，并新增“自动规划”。Plan 草稿可以是一条任务，也可以是两条以上的串行队列；Planner 只能拆分、排序并引用原始 `AC-xxx`，不能创建依赖或新验收标准。草稿允许人工编辑，只有明确确认后才会创建任务、队列、branch 或 worktree。

## 状态含义

- `machine_status=success`：固定自动验证通过，不代表人工接受。
- `machine_status=manual_review`：三轮验证仍失败，需要人工判断。
- `machine_status=infrastructure_error`：隔离、权限、SDK 或本地工具发生故障。
- `review_status=pending`：机器流程结束，但尚无人工结论。
- `approved`、`changes_requested`、`rejected`：人工针对一份确定 diff 提交的最终结论。
- `delivery_status` 独立记录 `not_ready → commit_pending → committing → committed → archive_pending → archived`，可恢复失败使用 `failed`。
- 长任务只有当前子任务机器验证通过且人工 `approved` 才会进入下一项；`waiting_review`、`changes_requested` 和 `infrastructure_error` 都会暂停队列。

增强 Web/API Harness 会在 `approved` 后自动 commit 到任务分支；不会 merge、push、创建 PR、rebase、tag、改写 Git identity、连接生产数据库、运行迁移或部署。Knowledge-Base 回写会按适用范围创建受治理的 Layer 1 技术知识、Layer 2 业务知识或绑定当前 `project_id` 的 Layer 3 项目知识，编号由 Knowledge-Base 按现有顺序规则分配；不会自动提交 Knowledge-Base 仓库。

## 权限边界

- Codex 的当前目录和唯一可写根是任务 worktree，原仓库与运行记录不向 Codex 开放。
- 审批模式为 deny-all；网络、Web Search、Apps、MCP、插件、multi-agent 和技能脚本关闭。
- 本地 MCP 只属于控制面：read 模式只能访问 registry 白名单根；archive 模式只能调用知识治理写入；拒绝绝对路径、`..`、符号链接逃逸和跨模式工具。
- Skills 是 `/Users/mon/Documents/mcp/skills/*/SKILL.md` 中的纯文本方法建议，会记录版本和哈希，但不执行脚本，也不作为安全、规范或架构强约束。
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
├── context/                  generation 与 evaluation 冻结快照
├── evaluations/              规范、架构与四层聚合结果
├── delivery/commit.json      review 绑定、intent、commit 与恢复证据
├── archive/                  packet、summary、角色产物与幂等 outbox
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
| `mcp_client.py`、`knowledge.py`、`skills.py` | 能力隔离的 MCP 客户端、知识分层检索与只读 Skill 选择 |
| `context.py`、`memory.py` | 阶段快照冻结、哈希校验和可复算的中期记忆召回 |
| `planner.py`、`role_runner.py` | 人工门禁 Plan 与独立结构化角色 thread |
| `evaluation.py` | 规范/架构评估、强约束阻断、警告和 `not_evaluated` 聚合 |
| `git_delivery.py`、`archiver.py` | review 绑定的单次 commit、崩溃恢复、本地优先归档与 outbox |
| `state.py` | 原子持久化、全局单执行锁、队列目录和敏感信息脱敏 |
| `report.py` 与 `templates/` | 渲染实际 prompt 和人工报告 |

## 测试

```bash
conda run -n account pytest -q orchestrator/tests
conda run -n account pytest -q orchestrator/backend/tests
npm --prefix orchestrator/frontend test
npm --prefix orchestrator/frontend run build
conda run -n account pytest -q /Users/mon/Documents/mcp/servers/harness_local/tests
```

所有 Git、Knowledge-Base 写入与 MCP 破坏性验证都使用临时 fixture；不会修改真实 Knowledge-Base 或当前项目任务分支。真实知识回写和真实任务 commit 只在获得单独授权后执行。
