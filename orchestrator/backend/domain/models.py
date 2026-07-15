from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class TaskSnapshot:
    task_id: str
    requirement: str
    acceptance_criteria: list[str]
    status: str
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "requirement": self.requirement,
            "acceptance_criteria": list(self.acceptance_criteria),
            "status": self.status,
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
        }
