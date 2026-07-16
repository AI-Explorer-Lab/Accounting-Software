from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class TaskSnapshot:
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
    rounds: list[dict[str, Any]] = field(default_factory=list)
    last_error_summary: str = ""
    infrastructure_error: str | None = None
    started_at: str = ""
    updated_at: str = ""
    finished_at: str | None = None
    report_url: str | None = None
    diff_url: str | None = None
    workspace: dict[str, Any] = field(default_factory=dict)
    permissions: dict[str, Any] = field(default_factory=dict)
    audit_summary: dict[str, Any] = field(default_factory=dict)
    changed_files: list[dict[str, Any]] = field(default_factory=list)
    codex_responses: list[dict[str, Any]] = field(default_factory=list)
    final_diff_sha256: str = ""
    diff_redaction_count: int = 0
    review: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "requirement": self.requirement,
            "acceptance_criteria": list(self.acceptance_criteria),
            "status": self.status,
            "schema_version": self.schema_version,
            "legacy": self.legacy,
            "history_warning": self.history_warning,
            "machine_status": self.machine_status or self.status,
            "review_status": self.review_status,
            "phase": self.phase,
            "thread_id": self.thread_id,
            "turn_count": self.turn_count,
            "failure_count": self.failure_count,
            "rounds": list(self.rounds),
            "last_error_summary": self.last_error_summary,
            "infrastructure_error": self.infrastructure_error,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "finished_at": self.finished_at,
            "report_url": self.report_url,
            "diff_url": self.diff_url,
            "workspace": dict(self.workspace),
            "permissions": dict(self.permissions),
            "audit_summary": dict(self.audit_summary),
            "changed_files": list(self.changed_files),
            "codex_responses": list(self.codex_responses),
            "final_diff_sha256": self.final_diff_sha256,
            "diff_redaction_count": self.diff_redaction_count,
            "review": None if self.review is None else dict(self.review),
        }
