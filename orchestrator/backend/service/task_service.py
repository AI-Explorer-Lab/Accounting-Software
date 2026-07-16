from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Callable

from orchestrator.codex_loop.models import TaskSpec
from orchestrator.codex_loop.review import ReviewError, ReviewService
from orchestrator.codex_loop.state import redact_sensitive_text
from orchestrator.codex_loop.workflow import OrchestrationWorkflow

from ..constant.enums import ApiTaskStatus
from ..domain.models import TaskSnapshot
from ..exceptions.business_exception import (
    InvalidTaskIdError,
    ReviewConflictError,
    TaskConflictError,
    TaskNotFoundError,
    TaskNotReadyError,
)
from ..mapper.file_run import FileRunMapper
from ..utils.task_executor import TaskExecutor


WorkflowFactory = Callable[[], OrchestrationWorkflow]


class TaskService:
    """Bridge the HTTP API to the existing blocking orchestration workflow."""

    def __init__(
        self,
        repo_root: str | Path,
        *,
        validation_timeout_seconds: float = 900.0,
        executor: TaskExecutor | None = None,
        mapper: FileRunMapper | None = None,
        workflow_factory: WorkflowFactory | None = None,
        review_service: ReviewService | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).expanduser().resolve()
        self.executor = executor or TaskExecutor()
        self.mapper = mapper or FileRunMapper(self.repo_root)
        self.workflow_factory = workflow_factory or (
            lambda: OrchestrationWorkflow(
                self.repo_root,
                validation_timeout_seconds=validation_timeout_seconds,
            )
        )
        self.review_service = review_service or ReviewService(self.repo_root)
        self._submission_lock = RLock()

    def start_task(
        self,
        requirement: str,
        acceptance_criteria: list[str],
    ) -> TaskSnapshot:
        task = TaskSpec(
            requirement=requirement,
            acceptance_criteria=acceptance_criteria,
        )
        with self._submission_lock:
            self._ensure_available()
            try:
                self.executor.submit(
                    task,
                    lambda: self.workflow_factory().start(task),
                )
            except RuntimeError as exc:
                raise TaskConflictError(str(exc)) from exc
        return self._accepted_snapshot(task)

    def get_task(self, task_id: str) -> TaskSnapshot:
        self._validate_task_id(task_id)
        snapshot = self.mapper.load_snapshot(task_id)
        if snapshot is not None:
            return snapshot

        record = self.executor.get(task_id)
        if record is None:
            raise TaskNotFoundError(task_id)
        if not record.future.done():
            return self._accepted_snapshot(record.task)

        error = record.future.exception()
        if error is not None:
            message = redact_sensitive_text(str(error) or type(error).__name__)
            values = self._accepted_snapshot(record.task).to_dict()
            values.update(
                status=ApiTaskStatus.INFRASTRUCTURE_ERROR.value,
                infrastructure_error=message,
                last_error_summary=message,
            )
            return TaskSnapshot(**values)
        raise TaskNotFoundError(task_id)

    def resume_task(self, task_id: str) -> TaskSnapshot:
        self._validate_task_id(task_id)
        task = self.mapper.load_task(task_id)
        snapshot = self.mapper.load_snapshot(task_id)
        if task is None or snapshot is None:
            raise TaskNotFoundError(task_id)
        if snapshot.status != ApiTaskStatus.RUNNING.value:
            return snapshot

        with self._submission_lock:
            active_task_id = self.executor.active_task_id()
            if active_task_id is not None:
                raise TaskConflictError(
                    f"Another task is already running: {active_task_id}"
                )
            try:
                self.executor.submit(
                    task,
                    lambda: self.workflow_factory().resume(task_id),
                )
            except RuntimeError as exc:
                raise TaskConflictError(str(exc)) from exc
        return snapshot

    def get_report(self, task_id: str) -> str:
        self._validate_task_id(task_id)
        task = self.mapper.load_task(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        report = self.mapper.load_report(task_id)
        if report is None:
            raise TaskNotReadyError(task_id)
        return report

    def get_diff(self, task_id: str) -> str:
        self._validate_task_id(task_id)
        task = self.mapper.load_task(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        diff = self.mapper.load_diff(task_id)
        if diff is None:
            raise TaskNotReadyError(task_id)
        return diff

    def review_task(
        self,
        task_id: str,
        *,
        decision: str,
        reviewer: str,
        comment: str,
        reviewed_diff_sha256: str,
    ) -> TaskSnapshot:
        self._validate_task_id(task_id)
        if self.mapper.load_task(task_id) is None:
            raise TaskNotFoundError(task_id)
        try:
            self.review_service.record(
                task_id,
                decision=decision,
                reviewer=reviewer,
                comment=comment,
                reviewed_diff_sha256=reviewed_diff_sha256,
            )
        except ReviewError as exc:
            raise ReviewConflictError(str(exc)) from exc
        snapshot = self.mapper.load_snapshot(task_id)
        if snapshot is None:  # pragma: no cover - guarded by persisted task/state
            raise TaskNotFoundError(task_id)
        return snapshot

    def close(self, *, wait: bool = False) -> None:
        self.executor.shutdown(wait=wait)

    def _ensure_available(self) -> None:
        active_task_id = self.executor.active_task_id()
        if active_task_id is not None:
            raise TaskConflictError(f"Another task is already running: {active_task_id}")
        unfinished = self.mapper.unfinished_task_ids()
        if unfinished:
            raise TaskConflictError(
                "An unfinished task must be resumed before starting another task: "
                + ", ".join(unfinished)
            )

    def _validate_task_id(self, task_id: str) -> None:
        try:
            self.mapper.validate_task_id(task_id)
        except (TypeError, ValueError):
            raise InvalidTaskIdError() from None

    @staticmethod
    def _accepted_snapshot(task: TaskSpec) -> TaskSnapshot:
        return TaskSnapshot(
            task_id=task.task_id,
            requirement=task.requirement,
            acceptance_criteria=list(task.acceptance_criteria),
            status=ApiTaskStatus.ACCEPTED.value,
            started_at=task.created_at,
            updated_at=task.created_at,
        )
