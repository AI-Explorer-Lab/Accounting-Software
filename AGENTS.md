# Accounting-Software project map

This file is a compact route map. It does not copy governed rule text and does
not replace the task-specific `RuleSetSnapshot` produced by the control plane.

## Authoritative inputs

- Business repository: this checkout.
- Reusable control plane: `/Users/mon/Documents/Loop-Engineering`.
- Governed knowledge and rule metadata:
  `/Users/mon/Documents/Knowledge-Base`.
- Offline MCP registry: `/Users/mon/Documents/mcp/registry.json`.
- Accounting project registration and fixed validation profile:
  `/Users/mon/Documents/Loop-Engineering/backend/config/app.local.yaml`.
- A task's frozen rules and evidence:
  `.codex-orchestrator/runs/<task-id>/context/` and the matching run directory.

Knowledge-Base is the rule fact source. This file only points to architecture,
commands, specifications and generated evidence.

## Business application layout

- `backend/`: FastAPI application, domain models, controllers, services,
  mappers, database configuration and backend tests.
- `frontend/`: Vue application, API adapters, views, components and UI tests.
- `compose.yaml`: local PostgreSQL service definition.
- `start.sh`: starts the business frontend and backend together.
- `README.md`: primary local startup, test and Orchestrator usage guide.
- `backend/README.md` and `frontend/README.md`: component-specific commands
  and implementation notes.
- FastAPI schema while the backend is running: `/docs` and `/openapi.json`.

## Harness and specification layout

- `.codex-orchestrator/`: local run, queue, evidence and notification state.
  Generated records are not business source files and historical evidence must
  not be retroactively rewritten.
- `orchestrator/`: the earlier in-repository Orchestrator implementation kept
  for compatibility and history. Confirm whether a change belongs here or in
  the reusable `Loop-Engineering` control plane before editing it.
- `plan/`: personal drafts and annotated design documents, not the formal
  specification store.
- `.harness/specs/active/`: reserved location for confirmed, Git-tracked
  specifications.
- `.harness/specs/archive/`: reserved location for completed specifications.

## Business validation commands

Run from the repository root:

```bash
docker compose up -d database
conda run -n account pytest -q backend/tests
npm --prefix frontend test
npm --prefix frontend run build
```

The reusable control plane executes the fixed profile configured for project
`accounting`; generated code and retrieved knowledge cannot replace those
commands.

## Local startup

```bash
docker compose up -d database
./start.sh
```

The public business page is `http://127.0.0.1:8101`. The business backend uses
the internal loopback port `18101`.

For the reusable Orchestrator workbench, start the services from
`/Users/mon/Documents/Loop-Engineering`; its local configuration registers
this repository as project `accounting`.

## Boundaries

- Governed knowledge changes go through
  `Knowledge-Base/tools/knowledge_governance.py` and retain revision, maturity,
  conflict and audit history.
- MCP reads and archives only through the allowlisted offline registry.
- Task rules are frozen into the run before generation or evaluation; current
  Knowledge-Base contents must not be used to rewrite an older run's history.
- Confirmed specifications belong under `.harness/specs/`; drafts and user
  annotations remain under `plan/`.
