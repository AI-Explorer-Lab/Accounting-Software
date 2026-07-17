"""Strictly serial orchestration for manually split multi-task queues."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from .audit import AuditRecorder
from .models import (
    InfrastructureError,
    PromptKind,
    QueueState,
    QueueStatus,
    QueueTaskStatus,
    ReviewRecord,
    ReviewStatus,
    RunResult,
    RunStatus,
    TaskQueueSpec,
    TaskSpec,
    utc_now_iso,
)
from .review import ReviewService
from .state import ActiveRunError, QueueStore, StateStore, redact_sensitive_text
from .workflow import OrchestrationWorkflow
from .workspace import WorkspaceInfo


WorkflowFactory = Callable[[StateStore, str, Path | None, str], Any]


class QueueWorkflow:
    """Persist and advance one ordered queue, one reviewed subtask at a time."""

    def __init__(
        self,
        repo_root: str | Path,
        *,
        queue_store: QueueStore | None = None,
        workflow_factory: WorkflowFactory | None = None,
        validation_timeout_seconds: float = 900.0,
    ) -> None:
        self.repo_root = Path(repo_root).expanduser().resolve()
        self.queue_store = queue_store or QueueStore(self.repo_root)
        self.validation_timeout_seconds = validation_timeout_seconds
        self.workflow_factory = workflow_factory or self._default_workflow

    def prepare(
        self,
        name: str,
        subtasks: list[Mapping[str, Any]],
        *,
        queue_id: str | None = None,
        base_ref: str = "HEAD",
    ) -> QueueState:
        """Validate and persist a queue without blocking on Codex execution."""

        self._assert_available()
        spec = TaskQueueSpec.from_inputs(
            name,
            subtasks,
            queue_id=queue_id,
            base_ref=base_ref,
        )
        spec.base_commit = self._resolve_commit(spec.base_ref)
        return self.queue_store.initialize_queue(spec)

    def start(
        self,
        name: str,
        subtasks: list[Mapping[str, Any]],
        *,
        queue_id: str | None = None,
        base_ref: str = "HEAD",
    ) -> QueueState:
        state = self.prepare(
            name,
            subtasks,
            queue_id=queue_id,
            base_ref=base_ref,
        )
        return self.run_current(state.queue_id)

    def run_current(self, queue_id: str) -> QueueState:
        """Start or resume the one child selected by durable queue state."""

        spec = self.queue_store.load_spec(queue_id)
        state = self.queue_store.load_state(queue_id)
        if state.status.is_final or state.status is QueueStatus.WAITING_REVIEW:
            return state

        if state.current_task_id is not None:
            child = state.task(state.current_task_id)
            if child.status is not QueueTaskStatus.RUNNING:
                return state
        else:
            child = state.next_pending()
            if child is None:
                if all(
                    item.status is QueueTaskStatus.COMPLETED
                    for item in state.subtasks
                ):
                    state.status = QueueStatus.COMPLETED
                    state.finished_at = utc_now_iso()
                    self.queue_store.save_state(state)
                    self._write_report(spec, state)
                return state
            child.status = QueueTaskStatus.RUNNING
            child.updated_at = utc_now_iso()
            state.current_task_id = child.task_id

        state.status = QueueStatus.RUNNING
        state.last_error_summary = ""
        self.queue_store.save_state(state)
        self.queue_store.append_event(
            queue_id,
            "subtask.started",
            {"task_id": child.task_id, "sequence": child.sequence},
        )

        task = self._task_spec(spec, child.task_id)
        store = self.queue_store.subtask_store(queue_id)
        try:
            inherited_path: Path | None = None
            inherited_sha = ""
            if child.sequence > 1:
                inherited_path = self.queue_store.cumulative_diff_path(queue_id)
                inherited_sha = state.cumulative_diff_sha256
                if not inherited_sha:
                    raise InfrastructureError(
                        "A later subtask has no approved cumulative diff baseline"
                    )
                if not inherited_path.is_file():
                    raise InfrastructureError(
                        "Approved cumulative diff does not exist"
                    )
                actual_sha = hashlib.sha256(inherited_path.read_bytes()).hexdigest()
                if actual_sha != inherited_sha:
                    raise InfrastructureError(
                        "Approved cumulative diff SHA-256 changed"
                    )
            workflow = self.workflow_factory(
                store,
                state.base_commit,
                inherited_path,
                inherited_sha,
            )
            if (store.run_dir(task.task_id) / "task.json").is_file():
                result: RunResult = workflow.resume(task.task_id)
            else:
                result = workflow.start(task)
        except ActiveRunError:
            raise
        except Exception as exc:
            child.status = QueueTaskStatus.INFRASTRUCTURE_ERROR
            child.last_error_summary = redact_sensitive_text(
                str(exc) or type(exc).__name__
            )
            child.updated_at = utc_now_iso()
            state.status = QueueStatus.INFRASTRUCTURE_ERROR
            state.last_error_summary = child.last_error_summary
            self.queue_store.save_state(state)
            self.queue_store.append_event(
                queue_id,
                "subtask.infrastructure_error",
                {"task_id": task.task_id, "error": child.last_error_summary},
            )
            self._write_report(spec, state)
            return state

        child.machine_status = result.status
        child.review_status = result.review_status
        child.thread_id = result.thread_id
        child.last_error_summary = result.infrastructure_error or ""
        child.updated_at = utc_now_iso()
        if result.status is RunStatus.INFRASTRUCTURE_ERROR:
            child.status = QueueTaskStatus.INFRASTRUCTURE_ERROR
            state.status = QueueStatus.INFRASTRUCTURE_ERROR
            state.last_error_summary = result.infrastructure_error or ""
            event_type = "subtask.infrastructure_error"
        else:
            child.status = QueueTaskStatus.WAITING_REVIEW
            state.status = QueueStatus.WAITING_REVIEW
            event_type = "subtask.waiting_review"
        self.queue_store.save_state(state)
        self.queue_store.append_event(
            queue_id,
            event_type,
            {
                "task_id": task.task_id,
                "machine_status": result.status.value,
                "review_status": result.review_status.value,
            },
        )
        self._write_report(spec, state)
        return state

    def record_review(
        self,
        queue_id: str,
        task_id: str,
        *,
        decision: ReviewStatus | str,
        reviewer: str,
        comment: str,
        reviewed_diff_sha256: str,
    ) -> tuple[QueueState, ReviewRecord]:
        """Record a child review and update the parent queue atomically."""

        spec = self.queue_store.load_spec(queue_id)
        state = self.queue_store.load_state(queue_id)
        if state.current_task_id != task_id:
            raise ValueError("only the current queue subtask can be reviewed")
        child = state.task(task_id)
        if child.status is not QueueTaskStatus.WAITING_REVIEW:
            raise ValueError("the current subtask is not waiting for review")
        store = self.queue_store.subtask_store(queue_id)
        normalized_decision = (
            decision
            if isinstance(decision, ReviewStatus)
            else ReviewStatus(str(decision))
        )
        if normalized_decision is ReviewStatus.APPROVED:
            self._validated_cumulative_source(queue_id, task_id)
        review = ReviewService(self.repo_root, store=store).record(
            task_id,
            decision=normalized_decision,
            reviewer=reviewer,
            comment=comment,
            reviewed_diff_sha256=reviewed_diff_sha256,
        )
        child.review_status = review.decision
        child.updated_at = utc_now_iso()

        if review.decision is ReviewStatus.APPROVED:
            try:
                self._promote_cumulative_diff(queue_id, task_id, state)
            except Exception as exc:
                message = redact_sensitive_text(str(exc) or type(exc).__name__)
                child.status = QueueTaskStatus.INFRASTRUCTURE_ERROR
                child.last_error_summary = message
                state.status = QueueStatus.INFRASTRUCTURE_ERROR
                state.last_error_summary = message
                self.queue_store.save_state(state)
                self.queue_store.append_event(
                    queue_id,
                    "cumulative_diff.infrastructure_error",
                    {"task_id": task_id, "error": message},
                )
                self._write_report(spec, state)
                raise InfrastructureError(message) from exc
            child.status = QueueTaskStatus.COMPLETED
            state.current_task_id = None
            if all(
                item.status is QueueTaskStatus.COMPLETED for item in state.subtasks
            ):
                state.status = QueueStatus.COMPLETED
                state.finished_at = utc_now_iso()
            else:
                state.status = QueueStatus.PENDING
            event_type = "subtask.approved"
        elif review.decision is ReviewStatus.CHANGES_REQUESTED:
            run_state = store.load_state(task_id)
            run_state.reopen_for_review_changes()
            store.save_state(run_state)
            child.status = QueueTaskStatus.RUNNING
            state.status = QueueStatus.RUNNING
            event_type = "subtask.changes_requested"
        else:
            child.status = QueueTaskStatus.REJECTED
            state.status = QueueStatus.REJECTED
            state.finished_at = utc_now_iso()
            event_type = "subtask.rejected"

        self.queue_store.save_state(state)
        self.queue_store.append_event(
            queue_id,
            event_type,
            {
                "task_id": task_id,
                "review_number": review.review_number,
                "reviewer": review.reviewer,
                "reviewed_diff_sha256": review.reviewed_diff_sha256,
            },
        )
        self._write_report(spec, state)
        return state, review

    def resume(self, queue_id: str) -> QueueState:
        state = self.queue_store.load_state(queue_id)
        if state.status is QueueStatus.INFRASTRUCTURE_ERROR:
            if state.current_task_id is None:
                raise InfrastructureError("queue has no current subtask to resume")
            child = state.task(state.current_task_id)
            if child.review_status is ReviewStatus.APPROVED:
                self._promote_cumulative_diff(queue_id, child.task_id, state)
                child.status = QueueTaskStatus.COMPLETED
                child.last_error_summary = ""
                state.current_task_id = None
                state.last_error_summary = ""
                if all(
                    item.status is QueueTaskStatus.COMPLETED
                    for item in state.subtasks
                ):
                    state.status = QueueStatus.COMPLETED
                    state.finished_at = utc_now_iso()
                else:
                    state.status = QueueStatus.PENDING
                self.queue_store.save_state(state)
                self.queue_store.append_event(
                    queue_id,
                    "cumulative_diff.recovered",
                    {"task_id": child.task_id},
                )
                self._write_report(self.queue_store.load_spec(queue_id), state)
                if state.status is QueueStatus.COMPLETED:
                    return state
                return self.run_current(queue_id)
            store = self.queue_store.subtask_store(queue_id)
            state_path = store.run_dir(child.task_id) / "state.json"
            if state_path.is_file():
                run_state = store.load_state(child.task_id)
                incomplete_prompt_kind: PromptKind | None = None
                if run_state.turn_count:
                    workspace = WorkspaceInfo.from_manifest(
                        self.repo_root,
                        store.load_manifest(child.task_id),
                    )
                    audit = AuditRecorder(
                        store.run_dir(child.task_id),
                        workspace.worktree,
                        run_state.base_commit,
                        inherited_baseline=run_state.inherited_baseline,
                        queue_task=True,
                    )
                    if not audit.has_event(
                        "turn.completed", turn_number=run_state.turn_count
                    ):
                        recorded_kind = audit.turn_prompt_kind(run_state.turn_count)
                        if recorded_kind is None:
                            raise InfrastructureError(
                                "Incomplete Codex turn has no recorded prompt kind"
                            )
                        try:
                            incomplete_prompt_kind = PromptKind(recorded_kind)
                        except ValueError as exc:
                            raise InfrastructureError(
                                "Incomplete Codex turn has an invalid prompt kind"
                            ) from exc
                run_state.reopen_after_infrastructure_error(
                    incomplete_prompt_kind=incomplete_prompt_kind
                )
                store.save_state(run_state)
            child.status = QueueTaskStatus.RUNNING
            child.last_error_summary = ""
            state.status = QueueStatus.RUNNING
            state.last_error_summary = ""
            self.queue_store.save_state(state)
        return self.run_current(queue_id)

    def _default_workflow(
        self,
        store: StateStore,
        base_commit: str,
        inherited_path: Path | None,
        inherited_sha: str,
    ) -> OrchestrationWorkflow:
        return OrchestrationWorkflow(
            self.repo_root,
            store=store,
            base_ref=base_commit,
            inherited_diff_path=inherited_path,
            inherited_diff_sha256=inherited_sha,
            validation_timeout_seconds=self.validation_timeout_seconds,
        )

    def _assert_available(self) -> None:
        unfinished_tasks = StateStore(self.repo_root).unfinished_task_ids()
        if unfinished_tasks:
            raise ActiveRunError(
                "an unfinished single task must be completed before a queue starts "
                f"(task_id={', '.join(unfinished_tasks)})"
            )
        unfinished_queues = self.queue_store.unfinished_queue_ids()
        if unfinished_queues:
            raise ActiveRunError(
                "an unfinished task queue must be resumed or reviewed first "
                f"(queue_id={', '.join(unfinished_queues)})"
            )

    def _promote_cumulative_diff(
        self, queue_id: str, task_id: str, state: QueueState
    ) -> None:
        source = self._validated_cumulative_source(queue_id, task_id)
        state.cumulative_diff_sha256 = self.queue_store.save_cumulative_diff(
            queue_id, source
        )

    def _validated_cumulative_source(self, queue_id: str, task_id: str) -> Path:
        run_dir = self.queue_store.subtask_store(queue_id).run_dir(task_id)
        metadata_path = run_dir / "changes/files.json"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise InfrastructureError("queued subtask changes metadata is unreadable") from exc
        cumulative = metadata.get("cumulative_diff", {})
        if not isinstance(cumulative, Mapping):
            raise InfrastructureError("queued subtask has no cumulative diff metadata")
        if int(cumulative.get("redaction_count", 0)):
            raise InfrastructureError("redacted cumulative diff cannot be inherited")
        relative_path = str(cumulative.get("path", "changes/cumulative.diff"))
        if relative_path != "changes/cumulative.diff":
            raise InfrastructureError(
                "queued subtask cumulative diff path is invalid"
            )
        source = run_dir / relative_path
        try:
            content = source.read_bytes()
        except OSError as exc:
            raise InfrastructureError(
                "queued subtask cumulative diff is unreadable"
            ) from exc
        raw_sha = hashlib.sha256(content).hexdigest()
        if raw_sha != str(cumulative.get("raw_sha256", "")):
            raise InfrastructureError("queued subtask cumulative diff SHA-256 changed")
        return source

    @staticmethod
    def _task_spec(spec: TaskQueueSpec, task_id: str) -> TaskSpec:
        for task in spec.subtasks:
            if task.task_id == task_id:
                return task
        raise ValueError(f"unknown queue subtask: {task_id}")

    def _resolve_commit(self, base_ref: str) -> str:
        try:
            completed = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.repo_root),
                    "rev-parse",
                    "--verify",
                    f"{base_ref}^{{commit}}",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (FileNotFoundError, PermissionError, OSError) as exc:
            raise InfrastructureError("Unable to resolve queue base commit") from exc
        if completed.returncode != 0:
            detail = redact_sensitive_text(
                (completed.stderr or completed.stdout).strip()
            )[:2_000]
            raise InfrastructureError(f"Unable to resolve queue base commit: {detail}")
        commit = completed.stdout.strip()
        if len(commit) != 40:
            raise InfrastructureError("Git did not return a full queue base commit")
        return commit

    def _write_report(self, spec: TaskQueueSpec, state: QueueState) -> None:
        rows = [
            f"# 长任务报告：{spec.name}",
            "",
            f"- 长任务编号：`{spec.queue_id}`",
            f"- 状态：`{state.status.value}`",
            f"- 原始基线：`{state.base_commit}`",
            f"- 当前子任务：`{state.current_task_id or '无'}`",
            f"- 累计 Diff SHA-256：`{state.cumulative_diff_sha256 or '尚未生成'}`",
            "",
            "## 子任务",
            "",
        ]
        task_specs = {task.task_id: task for task in spec.subtasks}
        for child in state.ordered_subtasks():
            task = task_specs[child.task_id]
            reviews = self.queue_store.subtask_store(
                spec.queue_id
            ).load_review_history(child.task_id)
            rows.extend(
                [
                    f"### {child.sequence}. {task.requirement}",
                    "- 验收标准：" + "；".join(task.acceptance_criteria),
                    f"- 调度状态：`{child.status.value}`",
                    f"- 机器状态：`{child.machine_status.value if child.machine_status else 'pending'}`",
                    f"- 审查状态：`{child.review_status.value}`",
                    f"- Thread：`{child.thread_id or '尚未创建'}`",
                    f"- 子任务报告：`subtasks/{child.task_id}/report.md`",
                    "",
                ]
            )
            if reviews:
                rows.extend(["审查历史：", ""])
                for review in reviews:
                    rows.append(
                        f"- 第 {review.review_number} 次：`{review.decision.value}`，"
                        f"审查人 {review.reviewer}，Diff `{review.reviewed_diff_sha256}`，"
                        f"说明：{review.comment or '无'}"
                    )
                rows.append("")
        if state.last_error_summary:
            rows.extend(["## 当前错误", "", state.last_error_summary, ""])
        self.queue_store.save_report(spec.queue_id, "\n".join(rows))


__all__ = ["QueueWorkflow", "WorkflowFactory"]
