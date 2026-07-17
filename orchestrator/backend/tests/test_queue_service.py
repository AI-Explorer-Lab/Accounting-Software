from pathlib import Path

from orchestrator.backend.service.queue_service import QueueService
from orchestrator.codex_loop.models import (
    QueueStatus,
    QueueTaskStatus,
    TaskQueueSpec,
)
from orchestrator.codex_loop.state import QueueStore


class CompletingQueueWorkflow:
    def __init__(self, store: QueueStore) -> None:
        self.store = store

    def prepare(
        self,
        name: str,
        subtasks: list[dict[str, object]],
        *,
        queue_id: str,
    ):
        spec = TaskQueueSpec.from_inputs(name, subtasks, queue_id=queue_id)
        spec.base_commit = "a" * 40
        return self.store.initialize_queue(spec)

    def run_current(self, queue_id: str):
        state = self.store.load_state(queue_id)
        child = state.next_pending()
        if child is not None:
            child.status = QueueTaskStatus.WAITING_REVIEW
            state.current_task_id = child.task_id
        state.status = QueueStatus.WAITING_REVIEW
        self.store.save_state(state)
        self.store.save_report(queue_id, "# Queue report\n")
        return state

    def resume(self, queue_id: str):
        return self.run_current(queue_id)


def _subtasks() -> list[dict[str, object]]:
    return [
        {"requirement": "First", "acceptance_criteria": ["Works"]},
        {"requirement": "Second", "acceptance_criteria": ["Works"]},
    ]


def test_queue_service_persists_before_background_execution(tmp_path: Path) -> None:
    store = QueueStore(tmp_path)
    service = QueueService(
        tmp_path,
        workflow_factory=lambda: CompletingQueueWorkflow(store),
    )
    try:
        accepted = service.start_queue("Queue", _subtasks())
        record = service.executor.get(accepted.queue_id)
        assert record is not None
        record.future.result(timeout=5)

        completed_machine_step = service.get_queue(accepted.queue_id)
        assert accepted.status in {"pending", "waiting_review"}
        assert completed_machine_step.status == "waiting_review"
        assert completed_machine_step.current_task_id
        assert service.get_report(accepted.queue_id) == "# Queue report\n"
    finally:
        service.executor.shutdown(wait=True)


def test_queue_resume_uses_pending_file_state_without_a_memory_future(
    tmp_path: Path,
) -> None:
    store = QueueStore(tmp_path)
    spec = TaskQueueSpec.from_inputs(
        "Queue",
        _subtasks(),
        queue_id="queue-resume",
    )
    spec.base_commit = "a" * 40
    store.initialize_queue(spec)
    service = QueueService(
        tmp_path,
        workflow_factory=lambda: CompletingQueueWorkflow(store),
    )
    try:
        snapshot = service.resume_queue(spec.queue_id)
        record = service.executor.get(spec.queue_id)
        assert record is not None
        record.future.result(timeout=5)
    finally:
        service.executor.shutdown(wait=True)

    assert snapshot.status == "pending"
    assert store.load_state(spec.queue_id).status is QueueStatus.WAITING_REVIEW
