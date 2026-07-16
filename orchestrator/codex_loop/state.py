"""Atomic persistence, active-run locking, and secret-safe log storage."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import hashlib
import os
from pathlib import Path
import re
import shlex
import socket
import tempfile
import time
from typing import Any, Iterator, Mapping
from uuid import uuid4

from .models import (
    CommandResult,
    ReviewRecord,
    RunResult,
    RunState,
    TaskSpec,
    ValidationRound,
    utc_now_iso,
)


class ActiveRunError(RuntimeError):
    """Raised when another live process owns the repository-wide task lock."""


_SENSITIVE_NAME = re.compile(
    r"(?:api[_-]?key|token|password|passwd|pwd|secret|credential|authorization|"
    r"access[_-]?key|private[_-]?key)",
    re.IGNORECASE,
)
_ASSIGNED_QUOTED = re.compile(
    r"(?i)(\b(?:api[_-]?key|token|password|passwd|pwd|secret|client[_-]?secret|"
    r"access[_-]?token|refresh[_-]?token|authorization)\b\s*[:=]\s*)"
    r"([\"'])(.*?)(\2)"
)
_ASSIGNED_PLAIN = re.compile(
    r"(?i)(\b(?:api[_-]?key|token|password|passwd|pwd|secret|client[_-]?secret|"
    r"access[_-]?token|refresh[_-]?token|authorization)\b\s*[:=]\s*)"
    r"([^\s,;]+)"
)
_AUTH_SCHEME = re.compile(r"(?i)\b(Basic|Bearer)\s+[A-Za-z0-9._~+/=-]+")
_API_KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")
_PREFIXED_TOKEN = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"npm_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|"
    r"(?:AKIA|ASIA)[A-Z0-9]{16})\b"
)
_JWT = re.compile(
    r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b"
)
_URI_PASSWORD = re.compile(
    r"(?i)\b([a-z][a-z0-9+.-]*://[^/\s:@]+:)([^@\s/]+)(@)"
)


def _sensitive_environment_values(
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    source = os.environ if environ is None else environ
    values = {
        str(value)
        for name, value in source.items()
        if _SENSITIVE_NAME.search(str(name))
        and str(value)
        and len(str(value)) >= 3
        and str(value).lower() not in {"true", "false", "none", "null"}
    }
    return sorted(values, key=len, reverse=True)


def redact_sensitive_text(
    text: str,
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Remove common credentials and values of sensitive environment variables."""

    redacted = str(text)
    for value in _sensitive_environment_values(environ):
        redacted = redacted.replace(value, "[REDACTED]")
    redacted = _AUTH_SCHEME.sub(
        lambda match: f"{match.group(1)} [REDACTED]", redacted
    )
    redacted = _API_KEY.sub("[REDACTED]", redacted)
    redacted = _PREFIXED_TOKEN.sub("[REDACTED]", redacted)
    redacted = _JWT.sub("[REDACTED]", redacted)
    redacted = _URI_PASSWORD.sub(
        lambda match: f"{match.group(1)}[REDACTED]{match.group(3)}", redacted
    )
    redacted = _ASSIGNED_QUOTED.sub(
        lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]{match.group(4)}",
        redacted,
    )
    redacted = _ASSIGNED_PLAIN.sub(
        lambda match: f"{match.group(1)}[REDACTED]", redacted
    )
    return redacted


def redact_sensitive_data(value: Any) -> Any:
    """Recursively redact strings before writing JSON to disk."""

    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, dict):
        return {str(key): redact_sensitive_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive_data(item) for item in value]
    return value


def sanitize_for_codex(text: str, max_chars: int = 8_000) -> str:
    """Redact and bound text before including it in a Codex repair prompt."""

    if max_chars < 200:
        raise ValueError("max_chars must be at least 200")
    redacted = redact_sensitive_text(text)
    if len(redacted) <= max_chars:
        return redacted
    marker = f"\n\n... [truncated {len(redacted) - max_chars} characters] ...\n\n"
    available = max_chars - len(marker)
    head_length = max(1, available * 3 // 4)
    tail_length = max(1, available - head_length)
    return f"{redacted[:head_length]}{marker}{redacted[-tail_length:]}"


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        _fsync_directory(path.parent)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary_path.unlink(missing_ok=True)
        raise


def _atomic_write_json(path: Path, data: Mapping[str, Any]) -> None:
    safe_data = redact_sensitive_data(dict(data))
    content = json.dumps(safe_data, ensure_ascii=False, indent=2, sort_keys=True)
    _atomic_write_text(path, f"{content}\n")


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return data


@dataclass(frozen=True, slots=True)
class ActiveLock:
    task_id: str
    pid: int
    token: str
    acquired_at: str


class StateStore:
    """Manage all durable artifacts below ``repo/.codex-orchestrator``."""

    def __init__(self, repo_root: str | Path) -> None:
        self.repo_root = Path(repo_root).expanduser().resolve()
        self.root = self.repo_root / ".codex-orchestrator"
        self.runs_root = self.root / "runs"
        self.active_lock_path = self.root / "active.lock"

    def run_dir(self, task_id: str) -> Path:
        TaskSpec._TASK_ID_PATTERN.fullmatch(task_id) or self._raise_bad_task_id(task_id)
        if "/" in task_id or "\\" in task_id or ".." in task_id:
            self._raise_bad_task_id(task_id)
        return self.runs_root / task_id

    @staticmethod
    def _raise_bad_task_id(task_id: str) -> None:
        raise ValueError(f"unsafe task id: {task_id!r}")

    def initialize_run(
        self,
        task: TaskSpec,
        *,
        task_repo_root: str | Path | None = None,
        workspace: Mapping[str, Any] | None = None,
        baseline_git_status: str = "",
        baseline_test_hashes: Mapping[str, str] | None = None,
    ) -> RunState:
        run_directory = self.run_dir(task.task_id)
        if run_directory.exists() and any(run_directory.iterdir()):
            raise ValueError(f"run directory already exists: {task.task_id}")
        run_directory.mkdir(parents=True, exist_ok=True)
        workspace_values = dict(workspace or {})
        state = RunState(
            task_id=task.task_id,
            repo_root=str(Path(task_repo_root or self.repo_root).resolve()),
            control_repo_root=str(self.repo_root),
            base_ref=str(workspace_values.get("base_ref", "HEAD")),
            base_commit=str(workspace_values.get("base_commit", "")),
            task_branch=str(workspace_values.get("task_branch", "")),
            worktree_relative_path=str(
                workspace_values.get("worktree_relative_path", "")
            ),
            source_worktree_was_dirty=bool(
                workspace_values.get("source_worktree_was_dirty", False)
            ),
            baseline_git_status=baseline_git_status,
            baseline_test_hashes=dict(baseline_test_hashes or {}),
            protected_test_paths=sorted((baseline_test_hashes or {}).keys()),
        )
        self.save_task(task)
        self.save_state(state)
        return state

    def save_task(self, task: TaskSpec) -> Path:
        path = self.run_dir(task.task_id) / "task.json"
        if path.is_file():
            existing = TaskSpec.from_dict(_read_json(path))
            if existing.to_dict() != task.to_dict():
                raise ValueError("task.json is immutable once created")
            return path
        _atomic_write_json(path, task.to_dict())
        return path

    def load_task(self, task_id: str) -> TaskSpec:
        return TaskSpec.from_dict(_read_json(self.run_dir(task_id) / "task.json"))

    def save_state(self, state: RunState) -> Path:
        state.touch()
        path = self.run_dir(state.task_id) / "state.json"
        _atomic_write_json(path, state.to_dict(include_output=False))
        return path

    def load_state(self, task_id: str) -> RunState:
        return RunState.from_dict(_read_json(self.run_dir(task_id) / "state.json"))

    def save_result(self, result: RunResult) -> Path:
        path = self.run_dir(result.task_id) / "result.json"
        _atomic_write_json(path, result.to_dict())
        return path

    def load_result(self, task_id: str) -> RunResult:
        return RunResult.from_dict(_read_json(self.run_dir(task_id) / "result.json"))

    def save_manifest(self, task_id: str, manifest: Mapping[str, Any]) -> Path:
        path = self.run_dir(task_id) / "manifest.json"
        _atomic_write_json(path, manifest)
        return path

    def load_manifest(self, task_id: str) -> dict[str, Any]:
        return _read_json(self.run_dir(task_id) / "manifest.json")

    def save_permissions(
        self, task_id: str, permissions: Mapping[str, Any]
    ) -> Path:
        path = self.run_dir(task_id) / "permissions.json"
        _atomic_write_json(path, permissions)
        return path

    def load_permissions(self, task_id: str) -> dict[str, Any]:
        return _read_json(self.run_dir(task_id) / "permissions.json")

    def save_review(self, review: ReviewRecord) -> Path:
        path = self.run_dir(review.task_id) / "review.json"
        if path.exists():
            raise ValueError("review.json already exists and cannot be overwritten")
        _atomic_write_json(path, review.to_dict())
        return path

    def load_review(self, task_id: str) -> ReviewRecord:
        return ReviewRecord.from_dict(
            _read_json(self.run_dir(task_id) / "review.json")
        )

    def unfinished_task_ids(self, *, excluding: str | None = None) -> list[str]:
        """Return durable non-final tasks, independent of process-lock liveness."""

        if not self.runs_root.is_dir():
            return []
        task_ids: list[str] = []
        for state_path in sorted(self.runs_root.glob("*/state.json")):
            task_id = state_path.parent.name
            if task_id == excluding:
                continue
            state = RunState.from_dict(_read_json(state_path))
            if not state.status.is_final:
                task_ids.append(task_id)
        return task_ids

    def save_report(self, task_id: str, report: str) -> Path:
        path = self.run_dir(task_id) / "report.md"
        _atomic_write_text(path, redact_sensitive_text(report))
        return path

    def save_round(self, task_id: str, validation_round: ValidationRound) -> Path:
        path = (
            self.run_dir(task_id)
            / "rounds"
            / f"round-{validation_round.round_number:02d}.json"
        )
        _atomic_write_json(path, validation_round.to_dict(include_output=False))
        return path

    def load_round(self, task_id: str, round_number: int) -> ValidationRound:
        path = self.run_dir(task_id) / "rounds" / f"round-{round_number:02d}.json"
        return ValidationRound.from_dict(_read_json(path))

    def write_command_log(
        self,
        task_id: str,
        round_number: int,
        command_index: int,
        result: CommandResult,
    ) -> Path:
        """Persist full output after redaction, without summary truncation."""

        stage = re.sub(r"[^A-Za-z0-9_-]+", "-", result.stage or "command")
        path = (
            self.run_dir(task_id)
            / "logs"
            / f"round-{round_number:02d}"
            / f"{command_index:02d}-{stage}.log"
        )
        content = "\n".join(
            [
                f"command: {shlex.join(result.command)}",
                f"cwd: {result.cwd}",
                f"started_at: {result.started_at}",
                f"duration_seconds: {result.duration_seconds:.3f}",
                f"exit_code: {result.exit_code}",
                f"timed_out: {str(result.timed_out).lower()}",
                f"infrastructure_error: {result.infrastructure_error or ''}",
                "",
                "--- stdout ---",
                result.stdout,
                "",
                "--- stderr ---",
                result.stderr,
                "",
            ]
        )
        _atomic_write_text(path, redact_sensitive_text(content))
        result.log_path = str(path.relative_to(self.repo_root))
        result.log_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        return path

    def acquire_active_lock(self, task_id: str) -> ActiveLock:
        self.run_dir(task_id)  # validate before creating a lock
        self.root.mkdir(parents=True, exist_ok=True)
        while True:
            lock = ActiveLock(
                task_id=task_id,
                pid=os.getpid(),
                token=uuid4().hex,
                acquired_at=utc_now_iso(),
            )
            metadata = {
                "task_id": lock.task_id,
                "pid": lock.pid,
                "token": lock.token,
                "hostname": socket.gethostname(),
                "acquired_at": lock.acquired_at,
            }
            candidate = self.root / f".active-{lock.token}.tmp"
            _atomic_write_json(candidate, metadata)
            try:
                os.link(candidate, self.active_lock_path)
                _fsync_directory(self.root)
                return lock
            except FileExistsError:
                if self._existing_lock_is_active():
                    owner = self._read_lock_metadata()
                    raise ActiveRunError(
                        "another task is active "
                        f"(task_id={owner.get('task_id', 'unknown')}, "
                        f"pid={owner.get('pid', 'unknown')})"
                    )
                self._remove_stale_lock()
            finally:
                candidate.unlink(missing_ok=True)

    def release_active_lock(self, lock: ActiveLock) -> None:
        try:
            metadata = self._read_lock_metadata()
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            return
        if metadata.get("token") == lock.token and metadata.get("pid") == lock.pid:
            self.active_lock_path.unlink(missing_ok=True)
            _fsync_directory(self.root)

    @contextmanager
    def active_lock(self, task_id: str) -> Iterator[ActiveLock]:
        lock = self.acquire_active_lock(task_id)
        try:
            yield lock
        finally:
            self.release_active_lock(lock)

    def _read_lock_metadata(self) -> dict[str, Any]:
        return _read_json(self.active_lock_path)

    def _existing_lock_is_active(self) -> bool:
        try:
            metadata = self._read_lock_metadata()
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            try:
                return time.time() - self.active_lock_path.stat().st_mtime < 5.0
            except FileNotFoundError:
                return False
        if metadata.get("hostname") != socket.gethostname():
            return True
        try:
            pid = int(metadata["pid"])
        except (KeyError, TypeError, ValueError):
            return False
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def _remove_stale_lock(self) -> None:
        self.active_lock_path.unlink(missing_ok=True)
        _fsync_directory(self.root)


__all__ = [
    "ActiveLock",
    "ActiveRunError",
    "StateStore",
    "redact_sensitive_data",
    "redact_sensitive_text",
    "sanitize_for_codex",
]
