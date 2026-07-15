# Orchestrator 整体架构

```text
正常业务运行
───────────
Vue 前端
   ↓ HTTP
FastAPI 后端
   ↓
PostgreSQL 数据库


自动开发流程
───────────
用户输入需求和验收标准
   ↓
Python Orchestrator
   ├── 创建/恢复 Codex thread
   ├── 让 Codex 修改 backend/ 或 frontend/
   ├── 独立运行相关测试
   ├── 独立运行全部测试和前端构建
   ├── 失败后让同一个 thread 修复
   └── 保存状态、日志和最终报告
```

如果不启动 orchestrator，原来的前端、后端和数据库仍然可以正常运行。orchestrator是作为Loop Engineering的一环，处理用户输入的需求，并自动生成代码

## 网页版运行方式

网页版只给现有 `codex_loop` 增加本机输入与状态展示层，不复制任务状态，也不改变原来的 thread、验证和失败修复规则。

```text
浏览器 127.0.0.1:5100
  ↓ 每 2 秒查询
orchestrator/backend 127.0.0.1:8100
  ↓ 单工作线程
codex_loop
  ↓
.codex-orchestrator/runs/<task-id>/
```

所有 Python 依赖必须安装到现有 Conda `account` 环境；Node 依赖分别安装在 `orchestrator/node_modules/` 和 `orchestrator/frontend/node_modules/`：

```bash
conda activate account
python -m pip install -r orchestrator/requirements.txt
python -m pip install -r orchestrator/backend/requirements.txt
npm ci --prefix orchestrator
npm ci --prefix orchestrator/frontend
```

从仓库根目录运行一个脚本即可同时启动前后端。脚本会使用 `account` 环境中的 Python；按 `Ctrl+C` 时会一起关闭两个服务：

```bash
./orchestrator/start.sh
```

需要分别观察或调试进程时，也可以手动启动后端和前端：

```bash
conda run -n account uvicorn orchestrator.backend.main:app \
  --reload --host 127.0.0.1 --port 8100

npm --prefix orchestrator/frontend run dev
```

打开 `http://127.0.0.1:5100`。页面要求填写一条功能需求和至少一条可验证的验收标准；提交后会立即获得任务编号，并展示执行阶段、Codex 轮次、验证结果和最终报告。同一时间只能运行一条需求。编排器后端固定使用 `http://127.0.0.1:8100`，与项目原有服务端口分开。

后端进程中断后，先重新启动后端，再恢复已保存任务。恢复会继续使用原来的 Codex thread：

```bash
curl -X POST http://127.0.0.1:8100/api/tasks/<task-id>/resume
```

接口与测试详见 [backend/README.md](/Users/mon/Documents/Accounting-Software/orchestrator/backend/README.md:1)，页面说明详见 [frontend/README.md](/Users/mon/Documents/Accounting-Software/orchestrator/frontend/README.md:1)。

## 架构解读

| 文件 | 功能 |
|---|---|
| [\_\_init\_\_.py](/Users/mon/Documents/Accounting-Software/orchestrator/__init__.py:1) | 把 `orchestrator` 标记为一个 Python 包，本身没有业务逻辑。 |
| [requirements.txt](/Users/mon/Documents/Accounting-Software/orchestrator/requirements.txt:1) | 固定 Python Codex SDK 版本 `openai-codex==0.1.0b3`，不混入 FastAPI 后端依赖。 |
| [package.json](/Users/mon/Documents/Accounting-Software/orchestrator/package.json:1) | 声明项目本地 Codex runtime `@openai/codex@0.144.4`。它不是另一个 Node 服务，只负责安装 Codex。 |
| [package-lock.json](/Users/mon/Documents/Accounting-Software/orchestrator/package-lock.json:1) | 锁定 Codex runtime 的版本、下载地址、完整性哈希和各操作系统安装包，确保 `npm ci` 安装结果一致。 |
| [task.example.json](/Users/mon/Documents/Accounting-Software/orchestrator/task.example.json:1) | 外部任务 JSON 的格式示例，只包含“本次做什么”：功能需求和验收标准。实际使用时也可以直接在命令行输入，不要求手写这个文件。 |
| [start.sh](/Users/mon/Documents/Accounting-Software/orchestrator/start.sh:1) | 使用 Conda `account` 环境同时启动编排器前后端，并统一处理退出和清理。 |
| [backend/](/Users/mon/Documents/Accounting-Software/orchestrator/backend/README.md:1) | 本机 FastAPI 调用层，接收、查询和恢复任务，并读取现有报告。 |
| [frontend/](/Users/mon/Documents/Accounting-Software/orchestrator/frontend/README.md:1) | Vue 3 + TypeScript 单页界面，负责提交需求、轮询状态和展示结果。 |

## codex_loop 核心模块细节

### 架构

```text
workflow.py            大脑，决定下一步做什么
codex_client.py        Codex 操作员
validation_runner.py   独立验收员
state.py               状态档案和任务锁
report.py              提示词和报告生成器
models.py              所有模块共同使用的数据格式
```

### 架构解读

| 文件 | 功能 |
|---|---|
| [codex_loop/\_\_init\_\_.py](/Users/mon/Documents/Accounting-Software/orchestrator/codex_loop/__init__.py:1) | 对外公开 `OrchestrationWorkflow`，让其他 Python 程序可以直接调用编排流程。 |
| [\_\_main\_\_.py](/Users/mon/Documents/Accounting-Software/orchestrator/codex_loop/__main__.py:1) | 命令行入口。支持 `start`、`resume`、交互输入、命令参数和任务 JSON；最后显示任务状态、报告路径和结果路径。 |
| [models.py](/Users/mon/Documents/Accounting-Software/orchestrator/codex_loop/models.py:1) | 定义所有数据格式和状态，包括任务、测试命令结果、验证轮次、运行状态、最终结果，以及 `success`、`manual_review` 等状态。 |
| [workflow.py](/Users/mon/Documents/Accounting-Software/orchestrator/codex_loop/workflow.py:1) | 整个编排器的主控制器。负责串联 Codex、测试、状态和报告；确保复用同一 thread；限制最多3个 Codex turn、3次验证失败。 |
| [codex_client.py](/Users/mon/Documents/Accounting-Software/orchestrator/codex_loop/codex_client.py:1) | 所有 Codex SDK 操作都集中在这里，包括检查本地 runtime、检查登录、启动 App Server、创建/恢复 thread、执行 turn 和确认中断前的 turn 是否完成。 |
| [validation_runner.py](/Users/mon/Documents/Accounting-Software/orchestrator/codex_loop/validation_runner.py:1) | 正式的测试执行器。自动发现本次新增或修改的测试，先跑相关测试，再跑三项全量验证；还会防止 Codex 删除测试。 |
| [state.py](/Users/mon/Documents/Accounting-Software/orchestrator/codex_loop/state.py:1) | 管理任务状态、单任务锁、日志和安全落盘；使用原子写入避免文件写到一半；过滤 API Key、Token、密码等敏感信息。 |
| [report.py](/Users/mon/Documents/Accounting-Software/orchestrator/codex_loop/report.py:1) | 把任务数据填入提示模板，把失败结果整理成修复提示，并生成最终的机器结果和人工报告。 |

### 核心数据关系

```text
TaskSpec
├── task_id
├── requirement
└── acceptance_criteria

RunState
├── thread_id
├── 当前 phase / status
├── turn_count / failure_count
├── 测试文件基线
├── 受保护测试清单
└── ValidationRound[]

ValidationRound
├── targeted_results[]
└── full_results[]

CommandResult
├── 执行命令和工作目录
├── stdout / stderr
├── 退出码、耗时和超时状态
└── 日志路径

RunResult
└── 根据最终 TaskSpec 和 RunState 生成的机器可读结果
```

# 完整流程

```text
1. 接收需求和验收标准
2. 生成 task-id，锁定当前项目
3. 记录当前 Git 状态和已有测试
4. 检查 Conda、npm、pytest、Codex 登录状态
5. 创建 Codex thread 并保存 thread-id
6. 发送首次开发要求
7. Codex 修改代码
8. Python 独立验证
   ├── 先跑新增或修改的相关测试
   └── 再跑后端全量、前端全量、前端构建
9. 根据结果处理
   ├── 通过 → success
   ├── 第 1/2 次失败 → 同一 thread 修复
   ├── 第 3 次失败 → manual_review
   └── 环境故障 → infrastructure_error
10. 生成 result.json 和 report.md
```

# 项目整体架构

```text
Accounting-Software/
├── backend/                 FastAPI 财务后端
├── frontend/                Vue 财务前端
├── compose.yaml             PostgreSQL 数据库
├── orchestrator/            Codex 自动开发编排器
└── .codex-orchestrator/     编排器运行记录，运行时生成
```

# 模板文件

| 文件 | 功能 |
|---|---|
| [initial_prompt.md](/Users/mon/Documents/Accounting-Software/orchestrator/codex_loop/templates/initial_prompt.md:1) | 第一次发给 Codex 的任务格式。包含项目目录、需求、验收标准，以及不能提交或清理 Git、不能删除或弱化测试等限制。 |
| [repair_prompt.md](/Users/mon/Documents/Accounting-Software/orchestrator/codex_loop/templates/repair_prompt.md:1) | 验证失败后发给同一个 thread。包含原需求、当前失败次数，以及经过脱敏和长度限制的失败命令与错误信息。 |
| [final_report.md](/Users/mon/Documents/Accounting-Software/orchestrator/codex_loop/templates/final_report.md:1) | 最终人工报告格式。包含 thread、turn 数、失败次数、每轮验证、日志位置、Git 基线和最终变更摘要。 |

`task.example.json` 和模板的职责不同：

```text
task.example.json = 每个任务都会变化的数据，例如需求和验收标准
Markdown 模板      = 所有任务共同使用的消息格式和行为规则
```

Python 会在运行时读取任务数据，把它填入对应模板，再发送给 Codex 或生成最终报告。

# Orchestrator 自身测试

| 文件 | 功能 |
|---|---|
| [conftest.py](/Users/mon/Documents/Accounting-Software/orchestrator/tests/conftest.py:1) | 配置测试导入路径，确保测试使用当前仓库中的 `orchestrator` 包。 |
| [test_codex_client.py](/Users/mon/Documents/Accounting-Software/orchestrator/tests/test_codex_client.py:1) | 测试 SDK、认证、项目本地 runtime 版本、App Server、thread 创建与恢复、turn 完成检查，以及禁止回退到全局 Codex。 |
| [test_validation_runner.py](/Users/mon/Documents/Accounting-Software/orchestrator/tests/test_validation_runner.py:1) | 测试相关测试发现、全量验证、超时、环境预检、防止测试被删除，以及中断恢复后的测试基线。 |
| [test_workflow.py](/Users/mon/Documents/Accounting-Software/orchestrator/tests/test_workflow.py:1) | 测试首轮成功、失败修复、同一 thread、三次失败上限、中断恢复、并行任务阻止和基础设施错误等完整状态流。 |
| [test_state_report.py](/Users/mon/Documents/Accounting-Software/orchestrator/tests/test_state_report.py:1) | 测试状态保存、原子写入、任务锁、陈旧锁清理、日志脱敏、模板生成和最终报告。 |

## 业务测试、验证器和编排器测试的区别

```text
backend/tests/、frontend 中的 *.test.ts
└── 测试财务业务功能是否正确

validation_runner.py
└── 负责执行上述业务测试并收集结果

orchestrator/tests/
└── 测试自动开发、验证、修复和恢复流程自身是否可靠
```

因此，`orchestrator/tests/` 不会替代后端或前端业务测试；它检查的是“监考和循环规则”有没有正确执行。

# 运行时生成目录

以下目录不是正式源码，不需要提交 Git：

```text
orchestrator/node_modules/
└── npm ci 安装的项目本地 Codex runtime，可以删除后重新安装

orchestrator/**/__pycache__/
└── Python 导入和测试生成的字节码缓存，可以安全删除

.pytest_cache/
└── Pytest 测试缓存，可以安全删除

.codex-orchestrator/
├── active.lock                         当前运行任务的进程锁
└── runs/<task-id>/
    ├── task.json                       原始任务数据
    ├── state.json                      当前阶段、thread ID、失败次数
    ├── rounds/round-01.json            每轮验证的结构化记录
    ├── logs/round-01/*.log             每条验证命令的完整脱敏日志
    ├── result.json                     最终机器可读结果
    └── report.md                       最终人工报告
```

`.codex-orchestrator/` 位于仓库根目录，不在 `orchestrator/` 源码目录中。它只在实际执行任务时生成，用于恢复中断任务和人工审计。

# 运行边界

- Orchestrator 不属于 FastAPI 后端，不会随业务服务启动。
- Orchestrator 一次只处理一个项目中的一个功能需求。
- Codex 负责修改代码，Python 编排器负责运行和判断测试结果。
- 验证命令来自源码中的固定安全列表，不执行 Codex 回复中的任意命令。
- 普通代码验证失败最多允许三轮；第 3 次失败后停止并转人工审核。
- SDK、认证、网络、Conda 或 npm 等环境故障归类为 `infrastructure_error`，不计入三次业务验证失败。
- Orchestrator 不会自动提交、重置、回滚或清理 Git 变更。
