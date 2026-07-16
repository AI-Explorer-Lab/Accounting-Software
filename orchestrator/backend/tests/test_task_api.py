from __future__ import annotations

from fastapi.testclient import TestClient

from orchestrator.backend.domain.models import TaskSnapshot
from orchestrator.backend.exceptions.business_exception import TaskConflictError
from orchestrator.backend.main import create_app


class FakeTaskService:
    def __init__(self) -> None:
        self.created: tuple[str, list[str]] | None = None
        self.resumed: str | None = None

    def start_task(
        self,
        requirement: str,
        acceptance_criteria: list[str],
    ) -> TaskSnapshot:
        self.created = (requirement, acceptance_criteria)
        return _snapshot(status="accepted")

    def get_task(self, task_id: str) -> TaskSnapshot:
        return _snapshot(task_id=task_id, status="running")

    def resume_task(self, task_id: str) -> TaskSnapshot:
        self.resumed = task_id
        return _snapshot(task_id=task_id, status="running")

    def get_report(self, task_id: str) -> str:
        return f"# Report for {task_id}\n"

    def get_diff(self, task_id: str) -> str:
        return f"diff --git a/{task_id} b/{task_id}\n"

    def review_task(
        self,
        task_id: str,
        *,
        decision: str,
        reviewer: str,
        comment: str,
        reviewed_diff_sha256: str,
    ) -> TaskSnapshot:
        snapshot = _snapshot(task_id=task_id, status="success")
        values = snapshot.to_dict()
        values.update(
            review_status=decision,
            review={
                "decision": decision,
                "reviewer": reviewer,
                "comment": comment,
                "reviewed_diff_sha256": reviewed_diff_sha256,
            },
        )
        return TaskSnapshot(**values)


class ConflictingTaskService(FakeTaskService):
    def start_task(
        self,
        requirement: str,
        acceptance_criteria: list[str],
    ) -> TaskSnapshot:
        raise TaskConflictError("Another task is already running")


def _snapshot(
    *,
    task_id: str = "task-1",
    status: str,
) -> TaskSnapshot:
    return TaskSnapshot(
        task_id=task_id,
        requirement="Add filtering",
        acceptance_criteria=["Filtering works"],
        status=status,
        phase="initialized" if status == "running" else None,
        started_at="2026-07-15T08:00:00+08:00",
        updated_at="2026-07-15T08:00:00+08:00",
    )


def _client(service: FakeTaskService) -> TestClient:
    return TestClient(
        create_app(task_service=service, validate_config=False),
        raise_server_exceptions=False,
    )


def test_health_and_create_task() -> None:
    service = FakeTaskService()
    with _client(service) as client:
        health = client.get("/api/health", headers={"X-Request-ID": "request-1"})
        created = client.post(
            "/api/tasks",
            json={
                "requirement": "  Add filtering  ",
                "acceptance_criteria": ["  Filtering works  "],
            },
        )

    assert health.status_code == 200
    assert health.json()["data"]["status"] == "ok"
    assert health.headers["X-Request-ID"] == "request-1"
    assert created.status_code == 202
    assert created.json()["data"]["task_id"] == "task-1"
    assert service.created == ("Add filtering", ["Filtering works"])


def test_invalid_payload_is_422_without_echoing_details() -> None:
    with _client(FakeTaskService()) as client:
        response = client.post(
            "/api/tasks",
            json={"requirement": " ", "acceptance_criteria": []},
        )

    assert response.status_code == 422
    assert response.json()["message"] == "Invalid request payload"


def test_get_resume_and_report() -> None:
    service = FakeTaskService()
    with _client(service) as client:
        fetched = client.get("/api/tasks/task-9")
        resumed = client.post("/api/tasks/task-9/resume")
        report = client.get("/api/tasks/task-9/report")
        diff = client.get("/api/tasks/task-9/diff")

    assert fetched.status_code == 200
    assert fetched.json()["data"]["status"] == "running"
    assert resumed.status_code == 202
    assert service.resumed == "task-9"
    assert report.status_code == 200
    assert report.headers["content-type"].startswith("text/markdown")
    assert report.text == "# Report for task-9\n"
    assert diff.status_code == 200
    assert diff.headers["content-type"].startswith("text/x-diff")


def test_review_endpoint_returns_the_recorded_decision() -> None:
    sha = "a" * 64
    with _client(FakeTaskService()) as client:
        response = client.post(
            "/api/tasks/task-9/review",
            json={
                "decision": "approved",
                "reviewer": "Local Reviewer",
                "comment": "Checked.",
                "reviewed_diff_sha256": sha,
            },
        )

    assert response.status_code == 200
    assert response.json()["data"]["review_status"] == "approved"
    assert response.json()["data"]["review"]["reviewed_diff_sha256"] == sha


def test_conflict_is_returned_as_structured_409() -> None:
    with _client(ConflictingTaskService()) as client:
        response = client.post(
            "/api/tasks",
            json={
                "requirement": "Add filtering",
                "acceptance_criteria": ["Filtering works"],
            },
        )

    assert response.status_code == 409
    assert response.json()["code"] == "TASK_CONFLICT"
    assert response.json()["success"] is False
