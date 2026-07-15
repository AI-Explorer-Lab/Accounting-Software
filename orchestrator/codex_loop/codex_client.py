"""Small, version-isolated adapter around the Codex Python SDK."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
import os
from pathlib import Path
import re
import subprocess
from types import TracebackType
from typing import Any, Self

from .models import InfrastructureError
from .state import redact_sensitive_text


DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]
PINNED_CODEX_RUNTIME_VERSION = "0.144.4"
DEFAULT_CODEX_RUNTIME_PATH = (
    DEFAULT_REPO_ROOT / "orchestrator" / "node_modules" / ".bin" / "codex"
)


@dataclass(frozen=True, slots=True)
class CodexRunResult:
    """Stable result shape exposed to the workflow instead of an SDK object."""

    thread_id: str
    final_response: str | None


@dataclass(frozen=True, slots=True)
class _SdkBindings:
    Codex: Any
    CodexConfig: Any
    Sandbox: Any
    TurnStatus: Any


class CodexClient:
    """Own one local Codex SDK session and its currently selected thread.

    Imports of ``openai_codex`` are intentionally delayed until the client is
    used. This keeps the rest of the orchestrator importable for reports and
    tests even when the optional SDK is not installed.
    """

    def __init__(
        self,
        repo_root: str | Path | None = None,
        *,
        runtime_path: str | Path | None = None,
    ) -> None:
        self.repo_root = Path(repo_root or DEFAULT_REPO_ROOT).expanduser().resolve()
        self.runtime_path = Path(
            runtime_path or DEFAULT_CODEX_RUNTIME_PATH
        ).expanduser().resolve()
        self._sdk: _SdkBindings | None = None
        self._codex_context: Any | None = None
        self._codex: Any | None = None
        self._thread: Any | None = None
        self._thread_id: str | None = None
        self._preflight_complete = False
        self._runtime_verified = False

    @property
    def thread_id(self) -> str | None:
        """ID of the active thread, if one has been started or resumed."""

        return self._thread_id

    def __enter__(self) -> Self:
        self.preflight()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        try:
            self._shutdown(exc_type, exc, traceback)
        except InfrastructureError:
            # Do not hide the workflow error that caused the context to exit.
            if exc is None:
                raise
        return False

    def preflight(self) -> None:
        """Start the local App Server transport and confirm authentication."""

        if self._preflight_complete:
            return

        codex = self._ensure_codex()
        try:
            account_response = codex.account()
        except Exception as exc:
            self._discard_codex()
            raise self._error("Codex authentication preflight failed", exc) from exc

        if getattr(account_response, "account", None) is None:
            self._discard_codex()
            raise InfrastructureError(
                "Codex is not authenticated; sign in before starting the orchestrator"
            )

        self._preflight_complete = True

    def start_thread(self) -> str:
        """Create a persistent thread rooted at this repository."""

        self.preflight()
        assert self._codex is not None
        assert self._sdk is not None

        try:
            thread = self._codex.thread_start(
                cwd=str(self.repo_root),
                sandbox=self._sdk.Sandbox.workspace_write,
            )
        except Exception as exc:
            raise self._error("Unable to start a Codex thread", exc) from exc

        return self._select_thread(thread, "started")

    def resume_thread(self, thread_id: str) -> str:
        """Resume a stored thread and make it active for subsequent turns."""

        if not isinstance(thread_id, str) or not thread_id.strip():
            raise ValueError("thread_id must be a non-empty string")

        self.preflight()
        assert self._codex is not None
        assert self._sdk is not None

        try:
            thread = self._codex.thread_resume(
                thread_id,
                cwd=str(self.repo_root),
                sandbox=self._sdk.Sandbox.workspace_write,
            )
        except Exception as exc:
            raise self._error("Unable to resume the Codex thread", exc) from exc

        return self._select_thread(thread, "resumed")

    def run(self, prompt: str) -> CodexRunResult:
        """Run one turn on the active thread and require normal completion."""

        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")
        if self._thread is None or self._thread_id is None:
            raise RuntimeError("start or resume a Codex thread before running a turn")

        try:
            result = self._thread.run(prompt)
        except Exception as exc:
            raise self._error("Codex turn could not be completed", exc) from exc

        assert self._sdk is not None
        status = getattr(result, "status", None)
        if status != self._sdk.TurnStatus.completed:
            status_name = getattr(status, "value", status)
            turn_error = getattr(result, "error", None)
            error_name = type(turn_error).__name__ if turn_error is not None else "none"
            raise InfrastructureError(
                "Codex turn did not complete "
                f"(status={status_name!s}, error_type={error_name})"
            )

        return CodexRunResult(
            thread_id=self._thread_id,
            final_response=getattr(result, "final_response", None),
        )

    def verify_turn_completed(self, expected_turn_count: int) -> None:
        """Prove an interrupted-process checkpoint has a completed SDK turn.

        The workflow owns a dedicated thread, so its durable turn count must
        exactly match the thread history before validation may resume.
        """

        if expected_turn_count < 1:
            raise ValueError("expected_turn_count must be at least 1")
        if self._thread is None:
            raise RuntimeError("resume the Codex thread before inspecting it")

        try:
            response = self._thread.read(include_turns=True)
            thread_record = getattr(response, "thread", None)
            turns = getattr(thread_record, "turns", None)
        except Exception as exc:
            raise self._error("Unable to read Codex turn history", exc) from exc

        if not isinstance(turns, list):
            raise InfrastructureError("Codex returned no readable turn history")
        if len(turns) != expected_turn_count:
            raise InfrastructureError(
                "Saved Codex turn was not confirmed "
                f"(expected_turns={expected_turn_count}, actual_turns={len(turns)})"
            )

        assert self._sdk is not None
        last_status = getattr(turns[-1], "status", None)
        if last_status != self._sdk.TurnStatus.completed:
            status_name = getattr(last_status, "value", last_status)
            raise InfrastructureError(
                "Saved Codex turn is not completed "
                f"(status={status_name!s})"
            )

    def close(self) -> None:
        """Close the SDK context and its local App Server transport."""

        self._shutdown(None, None, None)

    def _load_sdk(self) -> _SdkBindings:
        if self._sdk is not None:
            return self._sdk

        try:
            sdk_module = import_module("openai_codex")
            types_module = import_module("openai_codex.types")
            bindings = _SdkBindings(
                Codex=sdk_module.Codex,
                CodexConfig=sdk_module.CodexConfig,
                Sandbox=sdk_module.Sandbox,
                TurnStatus=types_module.TurnStatus,
            )
        except (ImportError, ModuleNotFoundError, AttributeError) as exc:
            raise InfrastructureError(
                "The Codex Python SDK is unavailable; install the pinned "
                "orchestrator requirements"
            ) from exc

        self._sdk = bindings
        return bindings

    def _ensure_codex(self) -> Any:
        if self._codex is not None:
            return self._codex

        sdk = self._load_sdk()
        self._verify_runtime()
        context: Any | None = None
        try:
            config = sdk.CodexConfig(codex_bin=str(self.runtime_path))
            context = sdk.Codex(config)
            codex = context.__enter__()
        except Exception as exc:
            if context is not None:
                try:
                    context.__exit__(None, None, None)
                except Exception:
                    pass
            raise self._error("Unable to start the local Codex App Server", exc) from exc

        self._codex_context = context
        self._codex = codex
        return codex

    def _verify_runtime(self) -> None:
        if self._runtime_verified:
            return

        install_command = "npm ci --prefix orchestrator"
        if not self.runtime_path.is_file():
            raise InfrastructureError(
                "Project-local Codex runtime is missing at "
                f"{self.runtime_path}; run `{install_command}` from the repository root"
            )
        if not os.access(self.runtime_path, os.X_OK):
            raise InfrastructureError(
                "Project-local Codex runtime is not executable at "
                f"{self.runtime_path}; run `{install_command}` to reinstall it"
            )

        try:
            completed = subprocess.run(
                [str(self.runtime_path), "--version"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise InfrastructureError(
                "Project-local Codex runtime version check timed out"
            ) from exc
        except (FileNotFoundError, PermissionError, OSError) as exc:
            raise self._error(
                "Unable to execute the project-local Codex runtime", exc
            ) from exc

        output = "\n".join(
            part for part in (completed.stdout, completed.stderr) if part
        ).strip()
        if completed.returncode != 0:
            detail = redact_sensitive_text(output)[:2_000]
            suffix = f": {detail}" if detail else ""
            raise InfrastructureError(
                "Project-local Codex runtime version check failed "
                f"(exit_code={completed.returncode}){suffix}"
            )

        match = re.search(r"\bcodex-cli\s+([^\s]+)", output)
        actual_version = match.group(1) if match else None
        if actual_version != PINNED_CODEX_RUNTIME_VERSION:
            found = actual_version or "unknown"
            raise InfrastructureError(
                "Project-local Codex runtime version mismatch "
                f"(required={PINNED_CODEX_RUNTIME_VERSION}, found={found}); "
                f"run `{install_command}` from the repository root"
            )

        self._runtime_verified = True

    def _select_thread(self, thread: Any, operation: str) -> str:
        thread_id = getattr(thread, "id", None)
        if not isinstance(thread_id, str) or not thread_id:
            raise InfrastructureError(
                f"Codex returned no thread ID for the {operation} thread"
            )

        self._thread = thread
        self._thread_id = thread_id
        return thread_id

    def _shutdown(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        context = self._codex_context
        self._codex_context = None
        self._codex = None
        self._thread = None
        self._thread_id = None
        self._preflight_complete = False
        self._runtime_verified = False

        if context is None:
            return

        try:
            context.__exit__(exc_type, exc, traceback)
        except Exception as close_error:
            raise self._error("Unable to close the Codex App Server", close_error) from close_error

    def _discard_codex(self) -> None:
        try:
            self._shutdown(None, None, None)
        except InfrastructureError:
            pass

    @staticmethod
    def _error(action: str, exc: Exception) -> InfrastructureError:
        if isinstance(exc, InfrastructureError):
            return exc
        detail = redact_sensitive_text(str(exc)).strip()
        suffix = f": {detail[:2_000]}" if detail else ""
        return InfrastructureError(
            f"{action} ({type(exc).__name__}){suffix}"
        )
