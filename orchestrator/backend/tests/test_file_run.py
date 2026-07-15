from pathlib import Path

import pytest

from orchestrator.backend.mapper.file_run import FileRunMapper
from orchestrator.codex_loop.models import CommandResult, TaskSpec, ValidationRound
from orchestrator.codex_loop.report import ReportBuilder
from orchestrator.codex_loop.state import StateStore


def test_mapper_reads_running_and_final_artifacts(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    task = TaskSpec(
        task_id="task-1",
        requirement="Add filtering",
        acceptance_criteria=["Filtering returns matching rows"],
    )
    state = store.initialize_run(task)
    state.thread_id = "thread-1"
    validation_round = ValidationRound(
        round_number=1,
        passed=True,
        stage="full",
        targeted_results=[
            CommandResult(
                command=["pytest", "backend/tests/test_transactions.py"],
                stage="targeted",
                exit_code=0,
                stdout="secret output is intentionally not exposed",
                log_path=".codex-orchestrator/runs/task-1/logs/round-01/01.log",
            )
        ],
    )
    state.add_round(validation_round)
    state.mark_success("M backend/service.py")
    store.save_state(state)
    ReportBuilder().persist(store, task, state)

    mapper = FileRunMapper(tmp_path)
    snapshot = mapper.load_snapshot(task.task_id)

    assert snapshot is not None
    assert snapshot.status == "success"
    assert snapshot.thread_id == "thread-1"
    assert snapshot.report_url == "/api/tasks/task-1/report"
    assert snapshot.rounds[0]["commands"][0]["passed"] is True
    assert "stdout" not in snapshot.rounds[0]["commands"][0]
    assert "# Codex 编排结果" in (mapper.load_report(task.task_id) or "")


def test_mapper_returns_none_for_unknown_safe_task(tmp_path: Path) -> None:
    mapper = FileRunMapper(tmp_path)

    assert mapper.load_task("unknown-task") is None
    assert mapper.load_snapshot("unknown-task") is None
    assert mapper.load_report("unknown-task") is None


def test_mapper_rejects_unsafe_task_id(tmp_path: Path) -> None:
    mapper = FileRunMapper(tmp_path)

    with pytest.raises(ValueError, match="unsafe task id"):
        mapper.load_snapshot("../outside")
