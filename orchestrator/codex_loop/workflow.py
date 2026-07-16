"""Durable isolated Codex -> validate -> repair -> human review workflow."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
import subprocess
from typing import Any

from .audit import AuditRecorder, file_sha256
from .codex_client import CodexClient, CodexRunResult
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
from .policy import ExecutionPolicy
from .report import PromptRenderer, ReportBuilder
from .state import ActiveRunError, StateStore, redact_sensitive_text
from .validation_runner import ValidationRunner
from .workspace import WorkspaceInfo, WorkspaceManager


MAX_VALIDATION_FAILURES = 3
MAX_CODEX_TURNS = 3

ClientFactory = Callable[[Path], Any]
ValidatorFactory = Callable[[Path, Mapping[str, str] | None], Any]


class OrchestrationWorkflow:
    """Run one task in a dedicated branch/worktree with complete audit data."""

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
        base_ref: str = "HEAD",
    ) -> None:
        self.control_repo_root = Path(repo_root).expanduser().resolve()
        self.repo_root = self.control_repo_root  # compatibility alias
        if not self.control_repo_root.is_dir():
            raise InfrastructureError(
                f"Project root does not exist: {self.control_repo_root}"
            )
        if validation_timeout_seconds <= 0:
            raise ValueError("validation_timeout_seconds must be greater than zero")

        self.store = store or StateStore(self.control_repo_root)
        self.client_factory = client_factory
        self.validator_factory = validator_factory
        self.prompt_renderer = prompt_renderer or PromptRenderer()
        self.report_builder = report_builder or ReportBuilder()
        self.validation_timeout_seconds = validation_timeout_seconds
        self.workspace_manager = WorkspaceManager(
            self.control_repo_root, base_ref=base_ref
        )

    def start(self, task: TaskSpec) -> RunResult:
        """Create the isolated workspace before starting a Codex thread."""

        lock = self.store.acquire_active_lock(task.task_id)
        state: RunState | None = None
        audit: AuditRecorder | None = None
        try:
            self._assert_no_other_unfinished_task()
            if self.store.run_dir(task.task_id).exists():
                raise InfrastructureError(
                    f"Task {task.task_id!r} already exists; use resume instead"
                )

            workspace = self.workspace_manager.create(task)
            state = self.store.initialize_run(
                task,
                task_repo_root=workspace.worktree,
                workspace={
                    "base_ref": workspace.base_ref,
                    "base_commit": workspace.base_commit,
                    "task_branch": workspace.task_branch,
                    "worktree_relative_path": workspace.worktree_relative_path,
                    "source_worktree_was_dirty": workspace.source_worktree_was_dirty,
                },
                baseline_git_status=(
                    "source worktree dirty"
                    if workspace.source_worktree_was_dirty
                    else "source worktree clean"
                ),
            )
            self.store.save_manifest(task.task_id, workspace.manifest())
            audit = self._audit(state)
            audit.append("run.created", {"task_id": task.task_id})
            audit.append(
                "workspace.created",
                {
                    "base_commit": workspace.base_commit,
                    "branch": workspace.task_branch,
                    "worktree": workspace.worktree_relative_path,
                },
            )

            policy = ExecutionPolicy(self.control_repo_root, workspace)
            self.store.save_permissions(task.task_id, policy.requested_snapshot())
            policy.prepare_runtime()
            self.workspace_manager.verify(workspace, require_clean=True)
            audit.append(
                "workspace.verified",
                {
                    "branch": workspace.task_branch,
                    "head": workspace.base_commit,
                    "clean": True,
                },
            )

            validator = self._make_validator(workspace, policy, None)
            state.baseline_test_hashes = dict(validator.baseline)
            state.protected_test_paths = self._validator_protected_tests(
                validator, fallback=state.baseline_test_hashes
            )
            self.store.save_state(state)
            validator.preflight()

            with self._make_client(workspace, policy, audit, state) as client:
                state.thread_id = client.start_thread()
                self._verify_permissions(task.task_id, state, policy, client, audit)
                state.phase = RunPhase.PROMPT_PENDING
                state.pending_prompt_kind = PromptKind.INITIAL
                self.store.save_state(state)
                return self._drive(task, state, client, validator, audit)
        except ActiveRunError:
            raise
        except Exception as exc:
            error = self._as_infrastructure_error(exc)
            if state is None:
                raise error from exc
            return self._finish_infrastructure_error(task, state, error, audit)
        finally:
            self.store.release_active_lock(lock)

    def resume(self, task_id: str) -> RunResult:
        """Verify the saved workspace/thread before continuing a checkpoint."""

        lock = self.store.acquire_active_lock(task_id)
        state: RunState | None = None
        task: TaskSpec | None = None
        audit: AuditRecorder | None = None
        try:
            self._assert_no_other_unfinished_task(excluding=task_id)
            task = self.store.load_task(task_id)
            state = self.store.load_state(task_id)
            if state.schema_version == 0:
                if state.status.is_final and (
                    self.store.run_dir(task_id) / "result.json"
                ).is_file():
                    return self.store.load_result(task_id)
                raise InfrastructureError(
                    "legacy_v0 runs are read-only and cannot be resumed"
                )
            result_path = self.store.run_dir(task_id) / "result.json"

            manifest = self.store.load_manifest(task_id)
            workspace = WorkspaceInfo.from_manifest(
                self.control_repo_root, manifest
            )
            self.workspace_manager.verify(workspace)
            policy = ExecutionPolicy(self.control_repo_root, workspace)
            policy.prepare_runtime()
            audit = self._audit(state)
            audit.append(
                "workspace.verified",
                {"branch": workspace.task_branch, "head": workspace.base_commit},
            )
            if state.phase is not RunPhase.CODEX_TURN and state.last_diff_sha256:
                if audit.current_diff_sha256() != state.last_diff_sha256:
                    raise InfrastructureError(
                        "Task worktree changed outside the saved workflow checkpoint"
                    )
            if state.status.is_final:
                required_artifacts = (
                    result_path,
                    self.store.run_dir(task_id) / "report.md",
                    self.store.run_dir(task_id) / "changes/files.json",
                    self.store.run_dir(task_id) / "changes/final.diff",
                )
                if all(path.is_file() for path in required_artifacts):
                    return self.store.load_result(task_id)
                return self._persist_final(task, state, audit)

            validator = self._make_validator(
                workspace, policy, state.baseline_test_hashes
            )
            protect_tests = getattr(validator, "protect_tests", None)
            if callable(protect_tests):
                protect_tests(state.protected_test_paths)
            validator.preflight()

            with self._make_client(workspace, policy, audit, state) as client:
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
                self._verify_permissions(task_id, state, policy, client, audit)
                return self._drive(task, state, client, validator, audit)
        except ActiveRunError:
            raise
        except Exception as exc:
            error = self._as_infrastructure_error(exc)
            if state is None or task is None:
                raise error from exc
            return self._finish_infrastructure_error(task, state, error, audit)
        finally:
            self.store.release_active_lock(lock)

    def _drive(
        self,
        task: TaskSpec,
        state: RunState,
        client: Any,
        validator: Any,
        audit: AuditRecorder,
    ) -> RunResult:
        while state.status is RunStatus.RUNNING:
            self._recover_round_checkpoint(state, audit)
            if state.status.is_final:
                return self._persist_final(task, state, audit)
            if state.phase is RunPhase.INITIALIZED:
                state.phase = RunPhase.PROMPT_PENDING
                state.pending_prompt_kind = PromptKind.INITIAL
                self.store.save_state(state)
                continue
            if state.phase is RunPhase.PROMPT_PENDING:
                self._ensure_retry_event(state, audit)
                self._run_pending_turn(task, state, client, audit)
                continue
            if state.phase is RunPhase.CODEX_TURN:
                self._recover_or_dispatch_turn(state, client, audit)
                continue
            if state.phase in {RunPhase.VALIDATION_PENDING, RunPhase.VALIDATING}:
                self._run_validation(state, validator, audit)
                if state.status.is_final:
                    return self._persist_final(task, state, audit)
                continue
            if state.phase is RunPhase.COMPLETED:
                return self._persist_final(task, state, audit)
            raise InfrastructureError(f"Unsupported workflow phase: {state.phase}")
        return self._persist_final(task, state, audit)

    def _run_pending_turn(
        self,
        task: TaskSpec,
        state: RunState,
        client: Any,
        audit: AuditRecorder,
    ) -> None:
        if state.turn_count >= MAX_CODEX_TURNS:
            state.mark_manual_review(self._safe_git_summary(Path(state.repo_root)))
            self.store.save_state(state)
            return

        prompt_kind = state.pending_prompt_kind
        if prompt_kind is PromptKind.INITIAL:
            prompt = self.prompt_renderer.initial_prompt(task, state)
        elif prompt_kind is PromptKind.REPAIR:
            if not state.rounds or state.failure_count not in {1, 2}:
                raise InfrastructureError("No failed validation round is available to repair")
            prompt = self.prompt_renderer.repair_prompt(
                task,
                state,
                state.rounds[-1],
                changed_files=audit.changed_paths(),
                diff_sha256=audit.current_diff_sha256(),
            )
        else:
            raise InfrastructureError("No pending Codex prompt is recorded")

        turn_number = state.turn_count + 1
        state.last_diff_sha256 = audit.current_diff_sha256()
        checkpoint_paths = audit.changed_paths()
        prompt_path = audit.save_prompt(turn_number, prompt)
        audit.append(
            "turn.started",
            {
                "prompt_kind": prompt_kind.value,
                "prompt_path": prompt_path.relative_to(audit.run_dir).as_posix(),
                "diff_sha256": state.last_diff_sha256,
                "changed_paths": checkpoint_paths,
            },
            source="codex",
            turn_number=turn_number,
            redacted=True,
        )
        state.turn_count = turn_number
        state.phase = RunPhase.CODEX_TURN
        state.pending_prompt_kind = None
        self.store.save_state(state)

        result: CodexRunResult = client.run(prompt)
        self._complete_turn(state, result, audit, recovered=False)

    def _recover_or_dispatch_turn(
        self,
        state: RunState,
        client: Any,
        audit: AuditRecorder,
    ) -> None:
        turn_number = state.turn_count
        recorded_sha = audit.latest_recorded_worktree_diff_sha256(turn_number)
        recovered: CodexRunResult | None = client.verify_turn_completed(turn_number)
        if recovered is None:
            # The prompt was durably saved but App Server has no matching turn,
            # so this is the one safe point where dispatch may be retried.
            result: CodexRunResult = client.run(audit.load_prompt(turn_number))
            self._complete_turn(state, result, audit, recovered=True)
            return
        if not recovered.history_complete:
            raise InfrastructureError(
                "Completed Codex turn history is incomplete and cannot be audited"
            )

        current_sha = audit.current_diff_sha256()
        if recorded_sha and current_sha != recorded_sha:
            raise InfrastructureError(
                "Task worktree changed after the last recorded Codex file event"
            )

        audit.backfill_completed_items(turn_number, recovered.items)
        if not recorded_sha:
            allowed_paths = audit.turn_checkpoint_paths(turn_number)
            allowed_paths.update(audit.codex_changed_paths(turn_number))
            unexpected = set(audit.changed_paths()) - allowed_paths
            if unexpected:
                raise InfrastructureError(
                    "Task worktree contains changes not declared by the recovered "
                    f"Codex turn: {', '.join(sorted(unexpected))}"
                )
        self._complete_turn(state, recovered, audit, recovered=True)

    def _complete_turn(
        self,
        state: RunState,
        result: CodexRunResult,
        audit: AuditRecorder,
        *,
        recovered: bool,
    ) -> None:
        turn_number = state.turn_count
        backfilled = audit.backfill_completed_items(turn_number, result.items)
        response_path = audit.save_response(turn_number, result.final_response)
        if not audit.has_event("turn.completed", turn_number=turn_number):
            audit.append(
                "turn.completed",
                {
                    "turn_id": result.turn_id,
                    "response_path": response_path.relative_to(
                        audit.run_dir
                    ).as_posix(),
                    "usage": result.usage,
                    "recovered": recovered,
                    "backfilled_items": backfilled,
                },
                source="codex",
                turn_number=turn_number,
                redacted=True,
            )
        state.last_diff_sha256 = audit.current_diff_sha256()
        state.phase = RunPhase.VALIDATION_PENDING
        state.pending_prompt_kind = None
        self.store.save_state(state)

    def _run_validation(
        self, state: RunState, validator: Any, audit: AuditRecorder
    ) -> None:
        state.phase = RunPhase.VALIDATING
        self.store.save_state(state)
        round_number = len(state.rounds) + 1
        audit.append("validation.started", {}, round_number=round_number)

        validation_round: ValidationRound = validator.validate(round_number)
        state.protected_test_paths = self._validator_protected_tests(
            validator, fallback=state.protected_test_paths
        )
        for command_index, command_result in enumerate(
            validation_round.command_results, start=1
        ):
            log_path = self.store.write_command_log(
                state.task_id, round_number, command_index, command_result
            )
            audit.append(
                "validation.command.completed",
                {
                    "command": command_result.command,
                    "cwd": command_result.cwd,
                    "exit_code": command_result.exit_code,
                    "duration_seconds": command_result.duration_seconds,
                    "timed_out": command_result.timed_out,
                    "infrastructure_error": command_result.infrastructure_error,
                    "log_path": log_path.relative_to(audit.run_dir).as_posix(),
                    "log_sha256": file_sha256(log_path),
                },
                round_number=round_number,
                redacted=True,
            )
        self.store.save_round(state.task_id, validation_round)
        state.add_round(validation_round)
        state.last_diff_sha256 = audit.current_diff_sha256()
        self.store.save_state(state)
        audit.append(
            "validation.completed",
            {
                "passed": validation_round.passed,
                "failure_summary": validation_round.failure_summary,
                "diff_sha256": state.last_diff_sha256,
            },
            round_number=round_number,
            redacted=True,
        )

        if validation_round.infrastructure_error:
            raise InfrastructureError(validation_round.infrastructure_error)
        if validation_round.passed:
            state.mark_success(self._safe_git_summary(Path(state.repo_root)))
        elif state.failure_count >= MAX_VALIDATION_FAILURES:
            state.mark_manual_review(self._safe_git_summary(Path(state.repo_root)))
        else:
            audit.append(
                "retry.scheduled",
                {
                    "failure_count": state.failure_count,
                    "next_turn": state.turn_count + 1,
                },
                round_number=round_number,
            )
        self.store.save_state(state)

    def _recover_round_checkpoint(
        self, state: RunState, audit: AuditRecorder
    ) -> None:
        """Finish a validation projection already saved before a crash."""

        if not state.rounds:
            return
        latest = state.rounds[-1]
        round_number = latest.round_number
        if not audit.has_event("validation.started", round_number=round_number):
            return
        if not audit.has_event("validation.completed", round_number=round_number):
            audit.append(
                "validation.completed",
                {
                    "passed": latest.passed,
                    "failure_summary": latest.failure_summary,
                    "diff_sha256": state.last_diff_sha256,
                    "recovered": True,
                },
                round_number=round_number,
                redacted=True,
            )
        if latest.passed and state.phase is RunPhase.VALIDATING:
            state.mark_success(self._safe_git_summary(Path(state.repo_root)))
            self.store.save_state(state)
        elif not latest.passed and state.failure_count >= MAX_VALIDATION_FAILURES:
            state.mark_manual_review(self._safe_git_summary(Path(state.repo_root)))
            self.store.save_state(state)

    @staticmethod
    def _ensure_retry_event(state: RunState, audit: AuditRecorder) -> None:
        if (
            state.pending_prompt_kind is not PromptKind.REPAIR
            or not state.rounds
            or state.failure_count >= MAX_VALIDATION_FAILURES
        ):
            return
        round_number = state.rounds[-1].round_number
        if not audit.has_event("validation.started", round_number=round_number):
            return
        if not audit.has_event("retry.scheduled", round_number=round_number):
            audit.append(
                "retry.scheduled",
                {
                    "failure_count": state.failure_count,
                    "next_turn": state.turn_count + 1,
                    "recovered": True,
                },
                round_number=round_number,
            )

    def _verify_permissions(
        self,
        task_id: str,
        state: RunState,
        policy: ExecutionPolicy,
        client: Any,
        audit: AuditRecorder,
    ) -> None:
        client.verify_thread_workspace()
        effective_config = client.effective_config()
        snapshot = policy.verify_effective(effective_config)
        self.store.save_permissions(task_id, snapshot)
        manifest = self.store.load_manifest(task_id)
        runtime = manifest.get("runtime")
        if isinstance(runtime, dict):
            reported_model = effective_config.get("model")
            runtime["model"] = (
                str(reported_model).strip() if reported_model else "not-reported"
            )
            self.store.save_manifest(task_id, manifest)
        state.permission_verified = True
        self.store.save_state(state)
        audit.append(
            "permissions.verified",
            snapshot["effective"],
        )

    def _make_client(
        self,
        workspace: WorkspaceInfo,
        policy: ExecutionPolicy,
        audit: AuditRecorder,
        state: RunState,
    ) -> Any:
        if self.client_factory is None:
            return CodexClient(
                workspace.worktree,
                policy=policy,
                event_sink=lambda notification: audit.record_codex_notification(
                    state.turn_count, notification
                ),
                permission_denial_sink=lambda method, params: audit.record_permission_denial(
                    state.turn_count, method, params
                ),
            )
        return self.client_factory(workspace.worktree)

    def _make_validator(
        self,
        workspace: WorkspaceInfo,
        policy: ExecutionPolicy,
        baseline: Mapping[str, str] | None,
    ) -> Any:
        if self.validator_factory is not None:
            return self.validator_factory(workspace.worktree, baseline)
        return ValidationRunner(
            workspace.worktree,
            timeout_seconds=self.validation_timeout_seconds,
            baseline_hashes=baseline,
            environment=policy.validation_environment(),
            command_prefix=policy.validation_command_prefix(),
        )

    def _finish_infrastructure_error(
        self,
        task: TaskSpec,
        state: RunState,
        error: Exception,
        audit: AuditRecorder | None,
    ) -> RunResult:
        message = redact_sensitive_text(str(error) or type(error).__name__)
        state.mark_infrastructure_error(
            message, self._safe_git_summary(Path(state.repo_root))
        )
        self.store.save_state(state)
        recorder = audit or self._audit(state)
        return self._persist_final(task, state, recorder)

    def _persist_final(
        self, task: TaskSpec, state: RunState, audit: AuditRecorder
    ) -> RunResult:
        if not state.status.is_final:
            raise InfrastructureError("Cannot write a final report for a running task")
        changes = audit.capture_final_changes()
        final_diff = changes.get("final_diff", {})
        state.last_diff_sha256 = str(final_diff.get("raw_sha256", ""))
        state.diff_redaction_count = int(final_diff.get("redaction_count", 0))
        self.store.save_state(state)
        event_type = (
            "run.failed"
            if state.status is RunStatus.INFRASTRUCTURE_ERROR
            else "run.completed"
        )
        if not audit.has_event(event_type):
            audit.append(
                event_type,
                {
                    "machine_status": state.status.value,
                    "review_status": state.review_status.value,
                    "diff_sha256": state.last_diff_sha256,
                },
            )
        permissions_path = self.store.run_dir(task.task_id) / "permissions.json"
        permissions = (
            self.store.load_permissions(task.task_id)
            if permissions_path.is_file()
            else {"effective": {"verified": False}}
        )
        review_path = self.store.run_dir(task.task_id) / "review.json"
        review = self.store.load_review(task.task_id) if review_path.is_file() else None
        result, report = self.report_builder.build(
            task,
            state,
            permissions=permissions,
            changes=changes,
            review=review,
            denied_event_count=audit.denied_event_count(),
        )
        self.store.save_result(result)
        self.store.save_report(task.task_id, report)
        return result

    def _audit(self, state: RunState) -> AuditRecorder:
        if not state.base_commit:
            raise InfrastructureError("Run state has no baseline commit")
        return AuditRecorder(
            self.store.run_dir(state.task_id),
            state.repo_root,
            state.base_commit,
        )

    def _assert_no_other_unfinished_task(
        self, *, excluding: str | None = None
    ) -> None:
        unfinished = self.store.unfinished_task_ids(excluding=excluding)
        if unfinished:
            raise ActiveRunError(
                "an unfinished task must be resumed or reviewed before starting "
                f"another task (task_id={', '.join(unfinished)})"
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

    def _safe_git_summary(self, root: Path) -> str:
        try:
            status = self._run_git(root, "status", "--short", "--untracked-files=all")
            unstaged = self._run_git(root, "diff", "--stat")
            staged = self._run_git(root, "diff", "--cached", "--stat")
            return "\n\n".join(
                [
                    "git status --short:\n" + (status.strip() or "（工作区干净）"),
                    "git diff --stat:\n" + (unstaged.strip() or "（无未暂存差异）"),
                    "git diff --cached --stat:\n" + (staged.strip() or "（无已暂存差异）"),
                ]
            )
        except InfrastructureError as exc:
            return f"无法读取最终 Git 摘要：{redact_sensitive_text(str(exc))}"

    @staticmethod
    def _run_git(root: Path, *arguments: str) -> str:
        try:
            completed = subprocess.run(
                ["git", "-C", str(root), *arguments],
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
            detail = redact_sensitive_text(
                (completed.stderr or completed.stdout).strip()
            )[:1_000]
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
