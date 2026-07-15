"""Command-line entry point for starting and resuming one Codex task."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .models import (
    InfrastructureError,
    RunResult,
    RunState,
    RunStatus,
    TaskSpec,
)
from .report import ReportBuilder
from .state import ActiveRunError, StateStore, redact_sensitive_text
from .workflow import OrchestrationWorkflow


REPO_ROOT = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m orchestrator.codex_loop",
        description="Run one feature request through Codex and independent validation.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start", help="start one new task")
    start_parser.add_argument("--task-file", type=Path)
    start_parser.add_argument("--task-id")
    start_parser.add_argument("--requirement")
    start_parser.add_argument(
        "--acceptance-criterion",
        action="append",
        dest="acceptance_criteria",
        help="repeat once for each acceptance criterion",
    )
    _add_timeout_argument(start_parser)

    resume_parser = subparsers.add_parser("resume", help="resume a saved task")
    resume_parser.add_argument("--task-id")
    _add_timeout_argument(resume_parser)
    return parser


def _add_timeout_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=900.0,
        help="timeout for each validation command (default: 900)",
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    store = StateStore(REPO_ROOT)

    try:
        if args.command == "start":
            try:
                task = _task_from_arguments(args)
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                result = _record_invalid_configuration(store, exc)
                _print_result(result, store)
                return 2
            workflow = OrchestrationWorkflow(
                REPO_ROOT,
                store=store,
                validation_timeout_seconds=args.timeout_seconds,
            )
            result = workflow.start(task)
        else:
            task_id = args.task_id or _find_resumable_task_id(store)
            workflow = OrchestrationWorkflow(
                REPO_ROOT,
                store=store,
                validation_timeout_seconds=args.timeout_seconds,
            )
            result = workflow.resume(task_id)
    except ActiveRunError as exc:
        print(f"无法启动：{redact_sensitive_text(str(exc))}", file=sys.stderr)
        return 2
    except (InfrastructureError, OSError, ValueError) as exc:
        print(f"编排器错误：{redact_sensitive_text(str(exc))}", file=sys.stderr)
        return 2
    except (EOFError, KeyboardInterrupt):
        print("已取消。", file=sys.stderr)
        return 130

    _print_result(result, store)
    if result.status is RunStatus.SUCCESS:
        return 0
    if result.status is RunStatus.MANUAL_REVIEW:
        return 1
    return 2


def _task_from_arguments(args: argparse.Namespace) -> TaskSpec:
    if args.task_file is not None:
        if args.requirement or args.acceptance_criteria or args.task_id:
            raise ValueError(
                "--task-file cannot be combined with requirement, criteria, or task ID"
            )
        return TaskSpec.from_file(args.task_file)

    requirement = args.requirement
    criteria = list(args.acceptance_criteria or [])
    if requirement is None and not criteria:
        if not sys.stdin.isatty():
            raise ValueError(
                "provide --task-file or requirement and acceptance criteria"
            )
        requirement, criteria = _interactive_task_input()
    elif requirement is None or not criteria:
        raise ValueError(
            "requirement and at least one acceptance criterion must be provided together"
        )

    values: dict[str, Any] = {
        "requirement": requirement,
        "acceptance_criteria": criteria,
    }
    if args.task_id:
        values["task_id"] = args.task_id
    return TaskSpec.from_dict(values)


def _interactive_task_input() -> tuple[str, list[str]]:
    requirement = input("功能需求：").strip()
    first = input("验收标准 1：").strip()
    criteria = [first] if first else []
    index = 2
    while criteria:
        criterion = input(f"验收标准 {index}（直接回车结束）：").strip()
        if not criterion:
            break
        criteria.append(criterion)
        index += 1
    return requirement, criteria


def _find_resumable_task_id(store: StateStore) -> str:
    candidates: list[RunState] = []
    if store.runs_root.is_dir():
        for state_path in store.runs_root.glob("*/state.json"):
            try:
                state = store.load_state(state_path.parent.name)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if not state.status.is_final:
                candidates.append(state)

    if not candidates:
        raise ValueError("no unfinished task is available to resume")
    if len(candidates) > 1:
        task_ids = ", ".join(sorted(state.task_id for state in candidates))
        raise ValueError(f"multiple unfinished tasks found; choose --task-id: {task_ids}")
    return candidates[0].task_id


def _record_invalid_configuration(
    store: StateStore, error: Exception
) -> RunResult:
    task = TaskSpec(
        requirement="任务配置无效，未向 Codex 发送需求",
        acceptance_criteria=["人工修正任务输入后重新启动"],
    )
    lock = store.acquire_active_lock(task.task_id)
    try:
        unfinished = store.unfinished_task_ids()
        if unfinished:
            raise ActiveRunError(
                "an unfinished task must be resumed or reviewed before recording "
                f"another task (task_id={', '.join(unfinished)})"
            )
        state = store.initialize_run(task)
        message = (
            "Invalid task configuration "
            f"({type(error).__name__}): {redact_sensitive_text(str(error))}"
        )
        state.mark_infrastructure_error(message)
        store.save_state(state)
        result, report = ReportBuilder().build(task, state)
        store.save_result(result)
        store.save_report(task.task_id, report)
        return result
    finally:
        store.release_active_lock(lock)


def _print_result(result: RunResult, store: StateStore) -> None:
    run_dir = store.run_dir(result.task_id)
    print(f"任务：{result.task_id}")
    print(f"状态：{result.status.value}")
    print(f"报告：{run_dir / 'report.md'}")
    print(f"结果：{run_dir / 'result.json'}")


if __name__ == "__main__":
    raise SystemExit(main())
