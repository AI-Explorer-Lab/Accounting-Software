from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from threading import RLock
from typing import Callable

from orchestrator.codex_loop.models import RunResult, TaskSpec


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
    task: TaskSpec
    future: Future[RunResult]


class TaskExecutor:
    """Run at most one blocking orchestrator workflow outside the event loop."""

    def __init__(self) -> None:
        self._pool = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="codex-orchestrator",
        )
        self._records: dict[str, ExecutionRecord] = {}
        self._lock = RLock()
        self._closed = False

    def submit(
        self,
        task: TaskSpec,
        operation: Callable[[], RunResult],
    ) -> ExecutionRecord:
        with self._lock:
            if self._closed:
                raise RuntimeError("Task executor is closed")
            if self.active_task_id() is not None:
                raise RuntimeError("Another task is already running")
            future = self._pool.submit(operation)
            record = ExecutionRecord(task=task, future=future)
            self._records[task.task_id] = record
            return record

    def active_task_id(self) -> str | None:
        with self._lock:
            for task_id, record in self._records.items():
                if not record.future.done():
                    return task_id
        return None

    def get(self, task_id: str) -> ExecutionRecord | None:
        with self._lock:
            return self._records.get(task_id)

    def shutdown(self, *, wait: bool = False) -> None:
        with self._lock:
            self._closed = True
        self._pool.shutdown(wait=wait, cancel_futures=False)
