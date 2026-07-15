"""Serializable data models shared by the Codex orchestration layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
import json
from pathlib import Path
import re
from typing import Any, ClassVar, Mapping
from uuid import uuid4


PROJECT_TIMEZONE = timezone(timedelta(hours=8), "UTC+08:00")


def utc_now_iso() -> str:
    """Return a stable UTC+8 timestamp suitable for JSON."""

    return datetime.now(PROJECT_TIMEZONE).isoformat(timespec="milliseconds")


def generate_task_id() -> str:
    """Generate a UTC+8 task id that is also safe as a directory name."""

    timestamp = datetime.now(PROJECT_TIMEZONE).strftime("%Y%m%d-%H%M%S")
    return f"{timestamp}-{uuid4().hex[:8]}"


class InfrastructureError(RuntimeError):
    """A local runtime failure that Codex cannot fix by changing business code."""


class RunStatus(str, Enum):
    """Lifecycle values persisted in ``state.json`` and ``result.json``."""

    RUNNING = "running"
    SUCCESS = "success"
    MANUAL_REVIEW = "manual_review"
    INFRASTRUCTURE_ERROR = "infrastructure_error"

    @property
    def is_final(self) -> bool:
        return self is not RunStatus.RUNNING


class RunPhase(str, Enum):
    """Fine-grained checkpoints used to resume without repeating a prompt."""

    INITIALIZED = "initialized"
    PROMPT_PENDING = "prompt_pending"
    CODEX_TURN = "codex_turn"
    VALIDATION_PENDING = "validation_pending"
    VALIDATING = "validating"
    COMPLETED = "completed"


class PromptKind(str, Enum):
    INITIAL = "initial"
    REPAIR = "repair"


class JsonModel:
    """Small protocol-like base class for explicit JSON round trips."""

    def to_dict(self) -> dict[str, Any]:  # pragma: no cover - abstract contract
        raise NotImplementedError


@dataclass(slots=True)
class TaskSpec(JsonModel):
    """One feature request handled by one Codex thread."""

    requirement: str
    acceptance_criteria: list[str]
    task_id: str = field(default_factory=generate_task_id)
    created_at: str = field(default_factory=utc_now_iso)

    _TASK_ID_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"^[A-Za-z0-9][A-Za-z0-9._-]{0,126}[A-Za-z0-9]$|^[A-Za-z0-9]$"
    )

    def __post_init__(self) -> None:
        self.requirement = str(self.requirement).strip()
        if not self.requirement:
            raise ValueError("requirement must be a non-empty string")

        if isinstance(self.acceptance_criteria, (str, bytes)):
            raise ValueError("acceptance_criteria must be a list of strings")
        self.acceptance_criteria = [
            str(criterion).strip() for criterion in self.acceptance_criteria
        ]
        if not self.acceptance_criteria or any(
            not criterion for criterion in self.acceptance_criteria
        ):
            raise ValueError(
                "acceptance_criteria must contain at least one non-empty string"
            )

        self.task_id = str(self.task_id or generate_task_id()).strip()
        if (
            "/" in self.task_id
            or "\\" in self.task_id
            or ".." in self.task_id
            or not self._TASK_ID_PATTERN.fullmatch(self.task_id)
        ):
            raise ValueError(
                "task_id must contain only letters, numbers, '.', '_' or '-' "
                "and must not contain path separators"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "requirement": self.requirement,
            "acceptance_criteria": list(self.acceptance_criteria),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TaskSpec":
        criteria = data.get("acceptance_criteria")
        if not isinstance(criteria, list):
            raise ValueError("acceptance_criteria must be a JSON array of strings")
        task_id = data.get("task_id") or generate_task_id()
        return cls(
            task_id=str(task_id),
            requirement=str(data.get("requirement", "")),
            acceptance_criteria=list(criteria),
            created_at=str(data.get("created_at") or utc_now_iso()),
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "TaskSpec":
        with Path(path).open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("task file must contain one JSON object")
        return cls.from_dict(data)


@dataclass(slots=True)
class CommandResult(JsonModel):
    """Complete, redacted-at-persistence result for one validation command."""

    command: list[str]
    cwd: str = ""
    stage: str = ""
    started_at: str = field(default_factory=utc_now_iso)
    duration_seconds: float = 0.0
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    infrastructure_error: str | None = None
    log_path: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.command, (str, bytes)) or not self.command:
            raise ValueError("command must be a non-empty list of arguments")
        self.command = [str(argument) for argument in self.command]
        self.cwd = str(self.cwd)
        if self.log_path is not None:
            self.log_path = str(self.log_path)
        self.duration_seconds = max(0.0, float(self.duration_seconds))
        if self.exit_code is not None:
            self.exit_code = int(self.exit_code)

    @property
    def passed(self) -> bool:
        return (
            self.exit_code == 0
            and not self.timed_out
            and not self.infrastructure_error
        )

    @property
    def failed(self) -> bool:
        return not self.passed

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": list(self.command),
            "cwd": self.cwd,
            "stage": self.stage,
            "started_at": self.started_at,
            "duration_seconds": self.duration_seconds,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
            "infrastructure_error": self.infrastructure_error,
            "log_path": self.log_path,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CommandResult":
        command = data.get("command")
        if not isinstance(command, list):
            raise ValueError("command must be a JSON array")
        return cls(
            command=[str(argument) for argument in command],
            cwd=str(data.get("cwd", "")),
            stage=str(data.get("stage", "")),
            started_at=str(data.get("started_at") or utc_now_iso()),
            duration_seconds=float(data.get("duration_seconds", 0.0)),
            exit_code=(
                None if data.get("exit_code") is None else int(data["exit_code"])
            ),
            stdout=str(data.get("stdout", "")),
            stderr=str(data.get("stderr", "")),
            timed_out=bool(data.get("timed_out", False)),
            infrastructure_error=(
                None
                if data.get("infrastructure_error") is None
                else str(data["infrastructure_error"])
            ),
            log_path=(
                None if data.get("log_path") is None else str(data["log_path"])
            ),
        )


@dataclass(slots=True)
class ValidationRound(JsonModel):
    """All targeted and full validation commands run after one Codex turn."""

    round_number: int
    targeted_results: list[CommandResult] = field(default_factory=list)
    full_results: list[CommandResult] = field(default_factory=list)
    passed: bool = False
    stage: str = "targeted"
    started_at: str = field(default_factory=utc_now_iso)
    finished_at: str | None = None
    failure_summary: str = ""
    infrastructure_error: str | None = None

    def __post_init__(self) -> None:
        self.round_number = int(self.round_number)
        if self.round_number < 1:
            raise ValueError("round_number must be at least 1")

    @property
    def command_results(self) -> list[CommandResult]:
        return [*self.targeted_results, *self.full_results]

    @property
    def failed_results(self) -> list[CommandResult]:
        return [result for result in self.command_results if result.failed]

    @property
    def log_paths(self) -> list[str]:
        return [
            result.log_path
            for result in self.command_results
            if result.log_path is not None
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_number": self.round_number,
            "targeted_results": [result.to_dict() for result in self.targeted_results],
            "full_results": [result.to_dict() for result in self.full_results],
            "passed": self.passed,
            "stage": self.stage,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "failure_summary": self.failure_summary,
            "infrastructure_error": self.infrastructure_error,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ValidationRound":
        return cls(
            round_number=int(data["round_number"]),
            targeted_results=[
                CommandResult.from_dict(item)
                for item in data.get("targeted_results", [])
            ],
            full_results=[
                CommandResult.from_dict(item) for item in data.get("full_results", [])
            ],
            passed=bool(data.get("passed", False)),
            stage=str(data.get("stage", "targeted")),
            started_at=str(data.get("started_at") or utc_now_iso()),
            finished_at=(
                None if data.get("finished_at") is None else str(data["finished_at"])
            ),
            failure_summary=str(data.get("failure_summary", "")),
            infrastructure_error=(
                None
                if data.get("infrastructure_error") is None
                else str(data["infrastructure_error"])
            ),
        )


@dataclass(slots=True)
class RunState(JsonModel):
    """Durable workflow checkpoint for one task."""

    task_id: str
    repo_root: str
    status: RunStatus = RunStatus.RUNNING
    phase: RunPhase = RunPhase.INITIALIZED
    thread_id: str | None = None
    pending_prompt_kind: PromptKind | None = PromptKind.INITIAL
    failure_count: int = 0
    turn_count: int = 0
    rounds: list[ValidationRound] = field(default_factory=list)
    baseline_test_hashes: dict[str, str] = field(default_factory=dict)
    protected_test_paths: list[str] = field(default_factory=list)
    baseline_git_status: str = ""
    final_git_summary: str = ""
    last_error_summary: str = ""
    infrastructure_error: str | None = None
    started_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    finished_at: str | None = None

    @property
    def project_root(self) -> str:
        """Compatibility alias for callers that use ``project_root``."""

        return self.repo_root

    def touch(self) -> None:
        self.updated_at = utc_now_iso()

    def add_round(self, validation_round: ValidationRound) -> None:
        if any(
            existing.round_number == validation_round.round_number
            for existing in self.rounds
        ):
            raise ValueError(
                f"validation round {validation_round.round_number} already exists"
            )
        self.rounds.append(validation_round)
        self.last_error_summary = validation_round.failure_summary
        if validation_round.infrastructure_error:
            self.mark_infrastructure_error(validation_round.infrastructure_error)
        elif not validation_round.passed:
            self.failure_count += 1
            self.phase = RunPhase.PROMPT_PENDING
            self.pending_prompt_kind = PromptKind.REPAIR
            self.touch()
        else:
            self.touch()

    def mark_success(self, final_git_summary: str = "") -> None:
        self.status = RunStatus.SUCCESS
        self.phase = RunPhase.COMPLETED
        self.pending_prompt_kind = None
        self.final_git_summary = final_git_summary
        self.finished_at = utc_now_iso()
        self.touch()

    def mark_manual_review(self, final_git_summary: str = "") -> None:
        self.status = RunStatus.MANUAL_REVIEW
        self.phase = RunPhase.COMPLETED
        self.pending_prompt_kind = None
        self.final_git_summary = final_git_summary
        self.finished_at = utc_now_iso()
        self.touch()

    def mark_infrastructure_error(
        self, message: str, final_git_summary: str = ""
    ) -> None:
        self.status = RunStatus.INFRASTRUCTURE_ERROR
        self.phase = RunPhase.COMPLETED
        self.pending_prompt_kind = None
        self.infrastructure_error = str(message)
        self.last_error_summary = str(message)
        self.final_git_summary = final_git_summary
        self.finished_at = utc_now_iso()
        self.touch()

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "repo_root": self.repo_root,
            "status": self.status.value,
            "phase": self.phase.value,
            "thread_id": self.thread_id,
            "pending_prompt_kind": (
                None
                if self.pending_prompt_kind is None
                else self.pending_prompt_kind.value
            ),
            "failure_count": self.failure_count,
            "turn_count": self.turn_count,
            "rounds": [validation_round.to_dict() for validation_round in self.rounds],
            "baseline_test_hashes": dict(self.baseline_test_hashes),
            "protected_test_paths": sorted(set(self.protected_test_paths)),
            "baseline_git_status": self.baseline_git_status,
            "final_git_summary": self.final_git_summary,
            "last_error_summary": self.last_error_summary,
            "infrastructure_error": self.infrastructure_error,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "finished_at": self.finished_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RunState":
        prompt_kind = data.get("pending_prompt_kind")
        return cls(
            task_id=str(data["task_id"]),
            repo_root=str(data["repo_root"]),
            status=RunStatus(str(data.get("status", RunStatus.RUNNING.value))),
            phase=RunPhase(str(data.get("phase", RunPhase.INITIALIZED.value))),
            thread_id=(
                None if data.get("thread_id") is None else str(data["thread_id"])
            ),
            pending_prompt_kind=(
                None if prompt_kind is None else PromptKind(str(prompt_kind))
            ),
            failure_count=int(data.get("failure_count", 0)),
            turn_count=int(data.get("turn_count", 0)),
            rounds=[
                ValidationRound.from_dict(item) for item in data.get("rounds", [])
            ],
            baseline_test_hashes={
                str(path): str(digest)
                for path, digest in dict(
                    data.get("baseline_test_hashes", {})
                ).items()
            },
            protected_test_paths=sorted(
                {str(path) for path in data.get("protected_test_paths", [])}
            ),
            baseline_git_status=str(data.get("baseline_git_status", "")),
            final_git_summary=str(data.get("final_git_summary", "")),
            last_error_summary=str(data.get("last_error_summary", "")),
            infrastructure_error=(
                None
                if data.get("infrastructure_error") is None
                else str(data["infrastructure_error"])
            ),
            started_at=str(data.get("started_at") or utc_now_iso()),
            updated_at=str(data.get("updated_at") or utc_now_iso()),
            finished_at=(
                None if data.get("finished_at") is None else str(data["finished_at"])
            ),
        )


@dataclass(slots=True)
class RunResult(JsonModel):
    """Self-contained machine-readable final result."""

    task_id: str
    status: RunStatus
    requirement: str
    acceptance_criteria: list[str]
    repo_root: str
    thread_id: str | None
    turn_count: int
    failure_count: int
    rounds: list[ValidationRound]
    baseline_git_status: str
    final_git_summary: str
    log_paths: list[str] = field(default_factory=list)
    infrastructure_error: str | None = None
    started_at: str = ""
    finished_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        if not self.status.is_final:
            raise ValueError("RunResult status must be a final status")

    @classmethod
    def from_run(cls, task: TaskSpec, state: RunState) -> "RunResult":
        if not state.status.is_final:
            raise ValueError("cannot build a result before the run is final")
        log_paths = list(
            dict.fromkeys(
                path
                for validation_round in state.rounds
                for path in validation_round.log_paths
            )
        )
        return cls(
            task_id=task.task_id,
            status=state.status,
            requirement=task.requirement,
            acceptance_criteria=list(task.acceptance_criteria),
            repo_root=state.repo_root,
            thread_id=state.thread_id,
            turn_count=state.turn_count,
            failure_count=state.failure_count,
            rounds=list(state.rounds),
            baseline_git_status=state.baseline_git_status,
            final_git_summary=state.final_git_summary,
            log_paths=log_paths,
            infrastructure_error=state.infrastructure_error,
            started_at=state.started_at,
            finished_at=state.finished_at or utc_now_iso(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "requirement": self.requirement,
            "acceptance_criteria": list(self.acceptance_criteria),
            "repo_root": self.repo_root,
            "thread_id": self.thread_id,
            "turn_count": self.turn_count,
            "failure_count": self.failure_count,
            "rounds": [validation_round.to_dict() for validation_round in self.rounds],
            "baseline_git_status": self.baseline_git_status,
            "final_git_summary": self.final_git_summary,
            "log_paths": list(self.log_paths),
            "infrastructure_error": self.infrastructure_error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RunResult":
        return cls(
            task_id=str(data["task_id"]),
            status=RunStatus(str(data["status"])),
            requirement=str(data.get("requirement", "")),
            acceptance_criteria=[
                str(item) for item in data.get("acceptance_criteria", [])
            ],
            repo_root=str(data.get("repo_root", "")),
            thread_id=(
                None if data.get("thread_id") is None else str(data["thread_id"])
            ),
            turn_count=int(data.get("turn_count", 0)),
            failure_count=int(data.get("failure_count", 0)),
            rounds=[
                ValidationRound.from_dict(item) for item in data.get("rounds", [])
            ],
            baseline_git_status=str(data.get("baseline_git_status", "")),
            final_git_summary=str(data.get("final_git_summary", "")),
            log_paths=[str(path) for path in data.get("log_paths", [])],
            infrastructure_error=(
                None
                if data.get("infrastructure_error") is None
                else str(data["infrastructure_error"])
            ),
            started_at=str(data.get("started_at", "")),
            finished_at=str(data.get("finished_at") or utc_now_iso()),
        )


__all__ = [
    "CommandResult",
    "InfrastructureError",
    "PromptKind",
    "RunPhase",
    "RunResult",
    "RunState",
    "RunStatus",
    "TaskSpec",
    "ValidationRound",
    "generate_task_id",
    "utc_now_iso",
]
