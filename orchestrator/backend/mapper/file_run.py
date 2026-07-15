from __future__ import annotations

from pathlib import Path
from typing import Any

from orchestrator.codex_loop.models import CommandResult, TaskSpec, ValidationRound
from orchestrator.codex_loop.state import StateStore

from ..domain.models import TaskSnapshot


class FileRunMapper:
    """Read the existing atomic run artifacts without creating a second store."""

    def __init__(self, repo_root: str | Path) -> None:
        self.store = StateStore(repo_root)

    def validate_task_id(self, task_id: str) -> None:
        self.store.run_dir(task_id)

    def unfinished_task_ids(self) -> list[str]:
        return self.store.unfinished_task_ids()

    def load_task(self, task_id: str) -> TaskSpec | None:
        run_dir = self.store.run_dir(task_id)
        if not (run_dir / "task.json").is_file():
            return None
        return self.store.load_task(task_id)

    def load_snapshot(self, task_id: str) -> TaskSnapshot | None:
        run_dir = self.store.run_dir(task_id)
        if not (run_dir / "task.json").is_file() or not (
            run_dir / "state.json"
        ).is_file():
            return None

        task = self.store.load_task(task_id)
        state = self.store.load_state(task_id)
        return TaskSnapshot(
            task_id=task.task_id,
            requirement=task.requirement,
            acceptance_criteria=list(task.acceptance_criteria),
            status=state.status.value,
            phase=state.phase.value,
            thread_id=state.thread_id,
            turn_count=state.turn_count,
            failure_count=state.failure_count,
            rounds=[self._round_summary(item) for item in state.rounds],
            last_error_summary=state.last_error_summary,
            infrastructure_error=state.infrastructure_error,
            started_at=state.started_at,
            updated_at=state.updated_at,
            finished_at=state.finished_at,
            report_url=(
                f"/api/tasks/{task.task_id}/report"
                if (run_dir / "report.md").is_file()
                else None
            ),
        )

    def load_report(self, task_id: str) -> str | None:
        path = self.store.run_dir(task_id) / "report.md"
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _round_summary(validation_round: ValidationRound) -> dict[str, Any]:
        return {
            "round_number": validation_round.round_number,
            "passed": validation_round.passed,
            "stage": validation_round.stage,
            "started_at": validation_round.started_at,
            "finished_at": validation_round.finished_at,
            "failure_summary": validation_round.failure_summary,
            "infrastructure_error": validation_round.infrastructure_error,
            "commands": [
                FileRunMapper._command_summary(result)
                for result in validation_round.command_results
            ],
        }

    @staticmethod
    def _command_summary(result: CommandResult) -> dict[str, Any]:
        return {
            "command": list(result.command),
            "stage": result.stage,
            "duration_seconds": result.duration_seconds,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "infrastructure_error": result.infrastructure_error,
            "log_path": result.log_path,
            "passed": result.passed,
        }
