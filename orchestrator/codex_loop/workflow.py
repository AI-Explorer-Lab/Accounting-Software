"""Durable single-task Codex -> validate -> repair workflow."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
import subprocess
from typing import Any

from .codex_client import CodexClient
from .models import (
    InfrastructureError,
    PromptKind,
    RunPhase,
    RunResult,
    RunState,
    RunStatus,
    TaskSpec,
    ValidationRound,
)
from .report import PromptRenderer, ReportBuilder
from .state import ActiveLock, ActiveRunError, StateStore, redact_sensitive_text
from .validation_runner import ValidationRunner


MAX_VALIDATION_FAILURES = 3
MAX_CODEX_TURNS = 3

ClientFactory = Callable[[Path], Any]
ValidatorFactory = Callable[[Path, Mapping[str, str] | None], Any]


class OrchestrationWorkflow:
    """Run one feature request while preserving resumable checkpoints.

    A prompt is marked as consumed before it is sent. If the Python process is
    interrupted during a turn, ``resume`` conservatively validates the current
    workspace instead of sending the same prompt a second time.
    """

    def __init__(
        self,
        repo_root: str | Path,
        *,
        store: StateStore | None = None,
        client_factory: ClientFactory | None = None,
        validator_factory: ValidatorFactory | None = None,
        prompt_renderer: PromptRenderer | None = None,
        report_builder: ReportBuilder | None = None,
        validation_timeout_seconds: float = 900.0,
    ) -> None:
        self.repo_root = Path(repo_root).expanduser().resolve()
        if not self.repo_root.is_dir():
            raise InfrastructureError(
                f"Project root does not exist: {self.repo_root}"
            )
        if validation_timeout_seconds <= 0:
            raise ValueError("validation_timeout_seconds must be greater than zero")

        self.store = store or StateStore(self.repo_root)
        self.client_factory = client_factory or (lambda root: CodexClient(root))
        self.validator_factory = validator_factory or (
            lambda root, baseline: ValidationRunner(
                root,
                timeout_seconds=validation_timeout_seconds,
                baseline_hashes=baseline,
            )
        )
        self.prompt_renderer = prompt_renderer or PromptRenderer()
        self.report_builder = report_builder or ReportBuilder()

    def start(self, task: TaskSpec) -> RunResult:
        """Start a new task, creating and immediately persisting one thread ID."""

        lock = self.store.acquire_active_lock(task.task_id)
        state: RunState | None = None
        try:
            self._assert_no_other_unfinished_task()
            if (self.store.run_dir(task.task_id) / "state.json").exists():
                raise InfrastructureError(
                    f"Task {task.task_id!r} already exists; use resume instead"
                )

            state = self.store.initialize_run(task)
            state.baseline_git_status = self._git_status()

            validator = self.validator_factory(self.repo_root, None)
            state.baseline_test_hashes = dict(validator.baseline)
            state.protected_test_paths = self._validator_protected_tests(
                validator, fallback=state.baseline_test_hashes
            )
            self.store.save_state(state)
            validator.preflight()

            with self.client_factory(self.repo_root) as client:
                state.thread_id = client.start_thread()
                state.phase = RunPhase.PROMPT_PENDING
                state.pending_prompt_kind = PromptKind.INITIAL
                self.store.save_state(state)
                result = self._drive(task, state, client, validator)

            return result
        except ActiveRunError:
            raise
        except Exception as exc:
            infrastructure_error = self._as_infrastructure_error(exc)
            if state is None:
                raise infrastructure_error from exc
            result = self._finish_infrastructure_error(
                task, state, infrastructure_error
            )
            return result
        finally:
            self.store.release_active_lock(lock)

    def resume(self, task_id: str) -> RunResult:
        """Resume saved state and the saved SDK thread without creating a new one."""

        lock = self.store.acquire_active_lock(task_id)
        state: RunState | None = None
        task: TaskSpec | None = None
        try:
            self._assert_no_other_unfinished_task(excluding=task_id)
            task = self.store.load_task(task_id)
            state = self.store.load_state(task_id)

            if state.status.is_final:
                result = self._persist_final(task, state)
                return result

            validator = self.validator_factory(
                self.repo_root, state.baseline_test_hashes
            )
            protect_tests = getattr(validator, "protect_tests", None)
            if callable(protect_tests):
                protect_tests(state.protected_test_paths)
            validator.preflight()

            with self.client_factory(self.repo_root) as client:
                if state.thread_id:
                    resumed_id = client.resume_thread(state.thread_id)
                    if resumed_id != state.thread_id:
                        raise InfrastructureError(
                            "Codex resumed a different thread than the saved thread"
                        )
                else:
                    state.thread_id = client.start_thread()
                    state.phase = RunPhase.PROMPT_PENDING
                    state.pending_prompt_kind = PromptKind.INITIAL
                    self.store.save_state(state)

                result = self._drive(task, state, client, validator)

            return result
        except ActiveRunError:
            raise
        except Exception as exc:
            infrastructure_error = self._as_infrastructure_error(exc)
            if state is None or task is None:
                raise infrastructure_error from exc
            result = self._finish_infrastructure_error(
                task, state, infrastructure_error
            )
            return result
        finally:
            self.store.release_active_lock(lock)

    def _drive(
        self,
        task: TaskSpec,
        state: RunState,
        client: Any,
        validator: Any,
    ) -> RunResult:
        while state.status is RunStatus.RUNNING:
            if state.phase is RunPhase.INITIALIZED:
                state.phase = RunPhase.PROMPT_PENDING
                state.pending_prompt_kind = PromptKind.INITIAL
                self.store.save_state(state)
                continue

            if state.phase is RunPhase.PROMPT_PENDING:
                self._run_pending_turn(task, state, client)
                continue

            if state.phase is RunPhase.CODEX_TURN:
                # Only validation after the SDK proves that the consumed prompt
                # produced a completed turn. Missing/interrupted history is an
                # infrastructure error, never a successful no-op validation.
                client.verify_turn_completed(state.turn_count)
                state.phase = RunPhase.VALIDATION_PENDING
                state.pending_prompt_kind = None
                self.store.save_state(state)
                continue

            if state.phase in {
                RunPhase.VALIDATION_PENDING,
                RunPhase.VALIDATING,
            }:
                self._run_validation(state, validator)
                if state.status.is_final:
                    return self._persist_final(task, state)
                continue

            if state.phase is RunPhase.COMPLETED:
                return self._persist_final(task, state)

            raise InfrastructureError(f"Unsupported workflow phase: {state.phase}")

        return self._persist_final(task, state)

    def _run_pending_turn(
        self, task: TaskSpec, state: RunState, client: Any
    ) -> None:
        if state.turn_count >= MAX_CODEX_TURNS:
            state.mark_manual_review(self._safe_git_summary())
            self.store.save_state(state)
            return

        prompt_kind = state.pending_prompt_kind
        if prompt_kind is PromptKind.INITIAL:
            prompt = self.prompt_renderer.initial_prompt(task, self.repo_root)
        elif prompt_kind is PromptKind.REPAIR:
            if not state.rounds or state.failure_count not in {1, 2}:
                raise InfrastructureError("No failed validation round is available to repair")
            prompt = self.prompt_renderer.repair_prompt(
                task, state, state.rounds[-1]
            )
        else:
            raise InfrastructureError("No pending Codex prompt is recorded")

        # Persist before calling the SDK. A crash may lose this turn, but it
        # cannot silently send the same requirement or repair twice.
        state.turn_count += 1
        state.phase = RunPhase.CODEX_TURN
        state.pending_prompt_kind = None
        self.store.save_state(state)

        client.run(prompt)

        state.phase = RunPhase.VALIDATION_PENDING
        self.store.save_state(state)

    def _run_validation(self, state: RunState, validator: Any) -> None:
        state.phase = RunPhase.VALIDATING
        self.store.save_state(state)

        round_number = len(state.rounds) + 1
        validation_round: ValidationRound = validator.validate(round_number)
        state.protected_test_paths = self._validator_protected_tests(
            validator, fallback=state.protected_test_paths
        )
        for command_index, command_result in enumerate(
            validation_round.command_results, start=1
        ):
            self.store.write_command_log(
                state.task_id,
                round_number,
                command_index,
                command_result,
            )
        self.store.save_round(state.task_id, validation_round)
        state.add_round(validation_round)
        self.store.save_state(state)

        if validation_round.infrastructure_error:
            raise InfrastructureError(validation_round.infrastructure_error)

        if validation_round.passed:
            state.mark_success(self._safe_git_summary())
        elif state.failure_count >= MAX_VALIDATION_FAILURES:
            state.mark_manual_review(self._safe_git_summary())

        self.store.save_state(state)

    def _assert_no_other_unfinished_task(
        self, *, excluding: str | None = None
    ) -> None:
        unfinished = self.store.unfinished_task_ids(excluding=excluding)
        if unfinished:
            task_ids = ", ".join(unfinished)
            raise ActiveRunError(
                "an unfinished task must be resumed or reviewed before starting "
                f"another task (task_id={task_ids})"
            )

    @staticmethod
    def _as_infrastructure_error(error: Exception) -> InfrastructureError:
        if isinstance(error, InfrastructureError):
            return error
        detail = redact_sensitive_text(str(error)).strip()
        suffix = f": {detail}" if detail else ""
        return InfrastructureError(
            f"Orchestrator infrastructure failure ({type(error).__name__}){suffix}"
        )

    @staticmethod
    def _validator_protected_tests(
        validator: Any, *, fallback: Mapping[str, str] | list[str]
    ) -> list[str]:
        protected = getattr(validator, "protected_test_paths", None)
        if protected is None:
            values = fallback.keys() if isinstance(fallback, Mapping) else fallback
            return sorted({str(path) for path in values})
        return sorted({str(path) for path in protected})

    def _finish_infrastructure_error(
        self, task: TaskSpec, state: RunState, error: Exception
    ) -> RunResult:
        message = redact_sensitive_text(str(error) or type(error).__name__)
        state.mark_infrastructure_error(message, self._safe_git_summary())
        self.store.save_state(state)
        return self._persist_final(task, state)

    def _persist_final(self, task: TaskSpec, state: RunState) -> RunResult:
        if not state.status.is_final:
            raise InfrastructureError("Cannot write a final report for a running task")
        result, report = self.report_builder.build(task, state)
        self.store.save_result(result)
        self.store.save_report(task.task_id, report)
        return result

    def _git_status(self) -> str:
        output = self._run_git("status", "--short", "--untracked-files=all")
        return output.strip() or "（工作区干净）"

    def _git_summary(self) -> str:
        status = self._run_git("status", "--short", "--untracked-files=all")
        unstaged = self._run_git("diff", "--stat")
        staged = self._run_git("diff", "--cached", "--stat")
        sections = [
            "git status --short:\n" + (status.strip() or "（工作区干净）"),
            "git diff --stat:\n" + (unstaged.strip() or "（无未暂存差异）"),
            "git diff --cached --stat:\n" + (staged.strip() or "（无已暂存差异）"),
        ]
        return "\n\n".join(sections)

    def _safe_git_summary(self) -> str:
        try:
            return self._git_summary()
        except InfrastructureError as exc:
            return f"无法读取最终 Git 摘要：{redact_sensitive_text(str(exc))}"

    def _run_git(self, *arguments: str) -> str:
        command = ["git", "-C", str(self.repo_root), *arguments]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                shell=False,
            )
        except (FileNotFoundError, PermissionError, OSError) as exc:
            raise InfrastructureError(
                f"Unable to run git ({type(exc).__name__})"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise InfrastructureError("Git inspection timed out") from exc

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            detail = redact_sensitive_text(detail)[:1_000]
            raise InfrastructureError(
                f"Git inspection failed with exit code {completed.returncode}: {detail}"
            )
        return completed.stdout


__all__ = [
    "MAX_CODEX_TURNS",
    "MAX_VALIDATION_FAILURES",
    "ActiveRunError",
    "OrchestrationWorkflow",
]
