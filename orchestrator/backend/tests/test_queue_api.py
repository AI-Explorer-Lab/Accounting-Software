from fastapi.testclient import TestClient

from orchestrator.backend.domain.models import QueueSnapshot, QueueSubtaskSnapshot
from orchestrator.backend.main import create_app


class FakeQueueService:
    def __init__(self) -> None:
        self.created: tuple[str, list[dict[str, object]]] | None = None
        self.resumed: str | None = None

    def start_queue(self, name: str, subtasks: list[dict[str, object]]) -> QueueSnapshot:
        self.created = (name, subtasks)
        return _queue()

    def get_queue(self, queue_id: str) -> QueueSnapshot:
        return _queue(queue_id=queue_id)

    def resume_queue(self, queue_id: str) -> QueueSnapshot:
        self.resumed = queue_id
        return _queue(queue_id=queue_id, status="infrastructure_error")

    def get_report(self, queue_id: str) -> str:
        return f"# Queue {queue_id}\n"

    def get_diff(self, queue_id: str) -> str:
        return f"diff --git a/{queue_id} b/{queue_id}\n"


def _queue(
    *, queue_id: str = "queue-1", status: str = "pending"
) -> QueueSnapshot:
    return QueueSnapshot(
        queue_id=queue_id,
        name="交易管理",
        status=status,
        base_ref="HEAD",
        base_commit="a" * 40,
        current_task_id=None,
        cumulative_diff_sha256="",
        last_error_summary="",
        subtasks=[
            QueueSubtaskSnapshot(
                task_id=f"{queue_id}-task-01",
                sequence=1,
                requirement="新增交易",
                acceptance_criteria=["可以新增"],
                status="pending",
                machine_status=None,
                review_status="pending",
                thread_id=None,
                last_error_summary="",
                updated_at="2026-07-17T08:00:00+08:00",
            ),
            QueueSubtaskSnapshot(
                task_id=f"{queue_id}-task-02",
                sequence=2,
                requirement="交易列表",
                acceptance_criteria=["可以查看"],
                status="pending",
                machine_status=None,
                review_status="pending",
                thread_id=None,
                last_error_summary="",
                updated_at="2026-07-17T08:00:00+08:00",
            ),
        ],
        started_at="2026-07-17T08:00:00+08:00",
        updated_at="2026-07-17T08:00:00+08:00",
        finished_at=None,
    )


def test_queue_endpoints_preserve_subtask_request_order() -> None:
    service = FakeQueueService()
    app = create_app(
        task_service=object(),
        queue_service=service,
        validate_config=False,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        created = client.post(
            "/api/queues",
            json={
                "name": " 交易管理 ",
                "subtasks": [
                    {
                        "requirement": " 新增交易 ",
                        "acceptance_criteria": [" 可以新增 "],
                    },
                    {
                        "requirement": "交易列表",
                        "acceptance_criteria": ["可以查看"],
                    },
                ],
            },
        )
        fetched = client.get("/api/queues/queue-9")
        resumed = client.post("/api/queues/queue-9/resume")
        report = client.get("/api/queues/queue-9/report")
        diff = client.get("/api/queues/queue-9/diff")

    assert created.status_code == 202
    assert [item["sequence"] for item in created.json()["data"]["subtasks"]] == [1, 2]
    assert service.created == (
        "交易管理",
        [
            {"requirement": "新增交易", "acceptance_criteria": ["可以新增"]},
            {"requirement": "交易列表", "acceptance_criteria": ["可以查看"]},
        ],
    )
    assert fetched.json()["data"]["queue_id"] == "queue-9"
    assert resumed.status_code == 202
    assert service.resumed == "queue-9"
    assert report.headers["content-type"].startswith("text/markdown")
    assert diff.headers["content-type"].startswith("text/x-diff")


def test_queue_requires_at_least_two_complete_subtasks() -> None:
    app = create_app(
        task_service=object(),
        queue_service=FakeQueueService(),
        validate_config=False,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/queues",
            json={
                "name": "Too short",
                "subtasks": [
                    {"requirement": "One", "acceptance_criteria": ["Works"]}
                ],
            },
        )

    assert response.status_code == 422
    assert response.json()["message"] == "Invalid request payload"
