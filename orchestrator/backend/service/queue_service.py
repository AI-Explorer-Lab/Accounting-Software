from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any, Callable, Mapping

from orchestrator.codex_loop.queue_workflow import QueueWorkflow
from orchestrator.codex_loop.models import generate_queue_id
from orchestrator.codex_loop.state import ActiveRunError, StateStore

from ..domain.models import QueueSnapshot
from ..exceptions.business_exception import (
    InvalidQueueIdError,
    QueueNotFoundError,
    QueueNotReadyError,
    TaskConflictError,
)
from ..mapper.file_queue import FileQueueMapper
from ..utils.task_executor import TaskExecutor


QueueWorkflowFactory = Callable[[], QueueWorkflow]


class QueueService:
    """HTTP-facing service for durable, strictly ordered task queues."""

    def __init__(
        self,
        repo_root: str | Path,
        *,
        validation_timeout_seconds: float = 900.0,
        executor: TaskExecutor | None = None,
        mapper: FileQueueMapper | None = None,
        workflow_factory: QueueWorkflowFactory | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).expanduser().resolve()
        self.executor = executor or TaskExecutor()
        self.mapper = mapper or FileQueueMapper(self.repo_root)
        self.workflow_factory = workflow_factory or (
            lambda: QueueWorkflow(
                self.repo_root,
                validation_timeout_seconds=validation_timeout_seconds,
            )
        )
        self._submission_lock = RLock()

    def start_queue(
        self,
        name: str,
        subtasks: list[Mapping[str, Any]],
    ) -> QueueSnapshot:
        with self._submission_lock:
            self._ensure_available()
            workflow = self.workflow_factory()
            queue_id = generate_queue_id()
            try:
                state, _ = self.executor.prepare_and_submit(
                    queue_id,
                    lambda: workflow.prepare(name, subtasks, queue_id=queue_id),
                    lambda prepared: workflow.run_current(prepared.queue_id),
                )
            except (ActiveRunError, RuntimeError) as exc:
                raise TaskConflictError(str(exc)) from exc
        snapshot = self.mapper.load_snapshot(state.queue_id)
        if snapshot is None:  # pragma: no cover - prepare persists both files
            raise QueueNotFoundError(state.queue_id)
        return snapshot

    def get_queue(self, queue_id: str) -> QueueSnapshot:
        self._validate_queue_id(queue_id)
        snapshot = self.mapper.load_snapshot(queue_id)
        if snapshot is None:
            raise QueueNotFoundError(queue_id)
        return snapshot

    def resume_queue(self, queue_id: str) -> QueueSnapshot:
        snapshot = self.get_queue(queue_id)
        if snapshot.status in {"completed", "rejected", "waiting_review"}:
            return snapshot
        with self._submission_lock:
            if self.executor.active_task_id() is not None:
                raise TaskConflictError(
                    f"Another task is already running: {self.executor.active_task_id()}"
                )
            workflow = self.workflow_factory()
            try:
                self.executor.submit_operation(
                    queue_id,
                    lambda: workflow.resume(queue_id),
                )
            except RuntimeError as exc:
                raise TaskConflictError(str(exc)) from exc
        return snapshot

    def get_report(self, queue_id: str) -> str:
        self.get_queue(queue_id)
        report = self.mapper.load_report(queue_id)
        if report is None:
            raise QueueNotReadyError(queue_id)
        return report

    def get_diff(self, queue_id: str) -> str:
        self.get_queue(queue_id)
        diff = self.mapper.load_diff(queue_id)
        if diff is None:
            raise QueueNotReadyError(queue_id)
        return diff

    def _ensure_available(self) -> None:
        active = self.executor.active_task_id()
        if active is not None:
            raise TaskConflictError(f"Another task is already running: {active}")
        unfinished_tasks = StateStore(self.repo_root).unfinished_task_ids()
        if unfinished_tasks:
            raise TaskConflictError(
                "An unfinished task must be resumed before starting a queue: "
                + ", ".join(unfinished_tasks)
            )
        unfinished_queues = self.mapper.unfinished_queue_ids()
        if unfinished_queues:
            raise TaskConflictError(
                "An unfinished queue must be resumed before starting another queue: "
                + ", ".join(unfinished_queues)
            )

    def _validate_queue_id(self, queue_id: str) -> None:
        try:
            self.mapper.validate_queue_id(queue_id)
        except (TypeError, ValueError):
            raise InvalidQueueIdError() from None
