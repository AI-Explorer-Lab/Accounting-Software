# Accounting Software

The project has separate backend and frontend applications. Commands must be
run in the corresponding directory, or with the directory prefix shown below.

## Start the database and backend

```bash
docker compose up -d database
conda activate account
cd backend
uvicorn main:app --reload
```

The backend runs at `http://127.0.0.1:8000`.

## Start the frontend

Open another terminal at the repository root and run:

```bash
npm --prefix frontend run dev
```

The frontend runs at `http://127.0.0.1:5173`. Running `npm run dev` directly
from the repository root does not work because `package.json` belongs to the
`frontend` directory.

## Run all tests

```bash
conda run -n account pytest -q backend/tests
npm --prefix frontend test
npm --prefix frontend run build
```

## Run the Codex orchestrator

The orchestrator handles one feature request at a time. For every new task it
creates `codex/<task-id>` and a dedicated Git worktree, then runs Codex and the
fixed validation commands only inside that worktree. It reuses the same Codex
thread for repairs and stops after three failed validation rounds.

Use the existing `account` Conda environment and install the orchestrator's
separate, pinned Python SDK and project-local Codex runtime:

```bash
conda activate account
python -m pip install -r orchestrator/requirements.txt
npm ci --prefix orchestrator
```

Start interactively and enter only the requirement and acceptance criteria:

```bash
python -m orchestrator.codex_loop start
```

For a non-interactive caller, pass the same information as arguments or in a
JSON file shaped like `orchestrator/task.example.json`:

```bash
python -m orchestrator.codex_loop start \
  --requirement "交易列表支持按最低金额筛选" \
  --acceptance-criterion "传入 min_amount=100 时，只返回金额大于或等于 100 的交易"

python -m orchestrator.codex_loop start \
  --task-file orchestrator/task.example.json
```

If a process was interrupted, resume the saved task and Codex thread instead
of starting another one:

```bash
python -m orchestrator.codex_loop resume --task-id <task-id>
```

Runtime state, redacted command logs, `result.json`, and `report.md` are stored
under `.codex-orchestrator/runs/<task-id>/`. This directory is local-only and
ignored by Git. Prompts, visible Codex replies, ordered events, permission
snapshots, file hashes and the complete final diff are stored there too.

Machine success is not an approval. Review the saved diff and record one final
local decision bound to its SHA-256:

```bash
python -m orchestrator.codex_loop show --task-id <task-id>
python -m orchestrator.codex_loop review \
  --task-id <task-id> \
  --decision approved \
  --reviewer "Local Reviewer" \
  --comment "Tests and diff checked" \
  --reviewed-diff-sha256 <sha256>
```

The other decisions are `changes_requested` and `rejected`. A decision cannot
be overwritten. The orchestrator never commits, pushes, merges, connects to a
production database, or deploys. Worktrees and task branches remain available
for inspection.

## Run the Codex orchestrator web interface

The web interface adds a local Vue page and FastAPI API around the same
orchestration workflow. It still handles only one active task at a time and
continues to use `.codex-orchestrator/` as its only task store.

Install every Python dependency into the existing `account` Conda environment.
Do not create a repository-local virtual environment:

```bash
conda activate account
python -m pip install -r orchestrator/requirements.txt
python -m pip install -r orchestrator/backend/requirements.txt
npm ci --prefix orchestrator
npm ci --prefix orchestrator/frontend
```

Start both services from the repository root. The script uses Python from the
`account` environment and stops both processes together when you press
`Ctrl+C`:

```bash
./orchestrator/start.sh
```

To run the services separately, start the API from the repository root:

```bash
conda run -n account uvicorn orchestrator.backend.main:app \
  --reload --host 127.0.0.1 --port 8100
```

Then start the page in another terminal:

```bash
npm --prefix orchestrator/frontend run dev
```

Open `http://127.0.0.1:5100`. The page submits a requirement and one or more
acceptance criteria, polls the task every two seconds, and displays workspace,
permissions, validation, visible Codex replies, changed files and the final
diff. It also records the same immutable review decision as the CLI. The API
listens only on `127.0.0.1:8100` by default and reuses the Codex login on this
computer.

Runs created before schema version 1 remain readable, but are labelled as
incomplete `legacy_v0` history. Missing isolation, permission, prompt, diff or
review data is never invented, and legacy runs cannot be resumed or reviewed.

If the API process was interrupted while a task was running, restart it and
resume the saved task and thread:

```bash
curl -X POST http://127.0.0.1:8100/api/tasks/<task-id>/resume
```

The browser remembers the most recent task ID and will continue querying it
after a refresh. See `orchestrator/backend/README.md` and
`orchestrator/frontend/README.md` for API and test commands.

### Pinned Codex runtime

`openai-codex==0.1.0b3` bundles Codex runtime `0.137.0a4`, which is too old for
the current default model. The orchestrator therefore uses the SDK's supported
`codex_bin` setting to select the project-local official
`@openai/codex@0.144.4` runtime. It checks that exact version before starting
App Server and never falls back to an unrelated global `codex` executable.

If the runtime is missing or has the wrong version, run
`npm ci --prefix orchestrator` again. Future runtime upgrades must update the
exact version in `orchestrator/package.json`, regenerate its lock file, and
pass the orchestrator tests plus a real end-to-end run before being accepted.
