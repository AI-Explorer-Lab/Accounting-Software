from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from .models import TaskSnapshot


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T | None = None
    message: str = "ok"
    request_id: str | None = None


class HealthData(BaseModel):
    status: str
    environment: str
    version: str


class TaskData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    requirement: str
    acceptance_criteria: list[str]
    status: str
    schema_version: int = 1
    legacy: bool = False
    history_warning: str | None = None
    machine_status: str | None = None
    review_status: str = "pending"
    phase: str | None = None
    thread_id: str | None = None
    turn_count: int = 0
    failure_count: int = 0
    rounds: list[dict[str, Any]] = Field(default_factory=list)
    last_error_summary: str = ""
    infrastructure_error: str | None = None
    started_at: str = ""
    updated_at: str = ""
    finished_at: str | None = None
    report_url: str | None = None
    diff_url: str | None = None
    workspace: dict[str, Any] = Field(default_factory=dict)
    permissions: dict[str, Any] = Field(default_factory=dict)
    audit_summary: dict[str, Any] = Field(default_factory=dict)
    changed_files: list[dict[str, Any]] = Field(default_factory=list)
    codex_responses: list[dict[str, Any]] = Field(default_factory=list)
    final_diff_sha256: str = ""
    diff_redaction_count: int = 0
    review: dict[str, Any] | None = None

    @classmethod
    def from_snapshot(cls, snapshot: TaskSnapshot) -> "TaskData":
        return cls.model_validate(snapshot.to_dict())
