from __future__ import annotations

from collections import deque
from pathlib import Path
import subprocess
from typing import Any

import pytest

from orchestrator.codex_loop.models import (
    CommandResult,
    InfrastructureError,
    PromptKind,
    RunPhase,
    RunStatus,
    TaskSpec,
    ValidationRound,
)
from orchestrator.codex_loop.state import ActiveRunError, StateStore
from orchestrator.codex_loop.workflow import OrchestrationWorkflow


class FakeCodexClient:
    def __init__(
        self,
        *,
        thread_id: str = "thread-one",
        enter_error: Exception | None = None,
        run_error: Exception | None = None,
        verify_error: Exception | None = None,
    ) -> None:
        self.saved_thread_id = thread_id
        self.enter_error = enter_error
        self.run_error = run_error
        self.verify_error = verify_error
        self.start_calls = 0
        self.resume_calls: list[str] = []
        self.prompts: list[str] = []
        self.verify_calls: list[int] = []
        self.closed = False

    def __enter__(self) -> "FakeCodexClient":
        if self.enter_error:
            raise self.enter_error
        return self

    def __exit__(self, *_args: Any) -> None:
        self.closed = True

    def start_thread(self) -> str:
        self.start_calls += 1
        return self.saved_thread_id

    def resume_thread(self, thread_id: str) -> str:
        self.resume_calls.append(thread_id)
        self.saved_thread_id = thread_id
        return thread_id

    def run(self, prompt: str) -> object:
        self.prompts.append(prompt)
        if self.run_error:
            raise self.run_error
        return object()

    def verify_turn_completed(self, expected_turn_count: int) -> None:
        self.verify_calls.append(expected_turn_count)
        if self.verify_error:
            raise self.verify_error


class FakeValidator:
    def __init__(
        self,
        outcomes: list[tuple[bool, list[int]]],
        *,
        preflight_error: Exception | None = None,
        validate_error: Exception | None = None,
    ) -> None:
        self.baseline = {"backend/tests/test_before.py": "digest"}
        self._protected_test_paths = set(self.baseline)
        self.outcomes = deque(outcomes)
        self.preflight_error = preflight_error
        self.validate_error = validate_error
        self.preflight_calls = 0
        self.round_numbers: list[int] = []

    @property
    def protected_test_paths(self) -> tuple[str, ...]:
        return tuple(sorted(self._protected_test_paths))

    def protect_tests(self, paths: list[str]) -> None:
        self._protected_test_paths.update(paths)

    def preflight(self) -> None:
        self.preflight_calls += 1
        if self.preflight_error:
            raise self.preflight_error

    def validate(self, round_number: int) -> ValidationRound:
        self.round_numbers.append(round_number)
        if self.validate_error:
            raise self.validate_error
        passed, exit_codes = self.outcomes.popleft()
        results = [
            CommandResult(
                command=["validation", str(index)],
                cwd="/repo",
                stage="full",
                exit_code=exit_code,
                stdout="ok" if exit_code == 0 else "",
                stderr="failure output" if exit_code else "",
            )
            for index, exit_code in enumerate(exit_codes, start=1)
        ]
        failures = [result for result in results if not result.passed]
        return ValidationRound(
            round_number=round_number,
            full_results=results,
            passed=passed,
            stage="full",
            failure_summary=(
                "; ".join(
                    f"{' '.join(item.command)}: exit code {item.exit_code}"
                    for item in failures
                )
                if failures
                else ""
            ),
        )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(
        ["git", "init", "-q", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    (tmp_path / "backend/tests").mkdir(parents=True)
    (tmp_path / "frontend").mkdir()
    (tmp_path / "backend/tests/test_before.py").write_text(
        "def test_before(): pass\n", encoding="utf-8"
    )
    (tmp_path / "frontend/package.json").write_text("{}\n", encoding="utf-8")
    return tmp_path


def task() -> TaskSpec:
    return TaskSpec(
        task_id="workflow-test",
        requirement="实现一个功能",
        acceptance_criteria=["行为符合验收标准"],
    )


def workflow_with(
    repo: Path, client: FakeCodexClient, validator: FakeValidator
) -> OrchestrationWorkflow:
    return OrchestrationWorkflow(
        repo,
        client_factory=lambda _root: client,
        validator_factory=lambda _root, _baseline: validator,
    )


def test_first_turn_success_creates_thread_state_logs_and_report(repo: Path) -> None:
    client = FakeCodexClient()
    validator = FakeValidator([(True, [0, 0, 0])])

    result = workflow_with(repo, client, validator).start(task())

    assert result.status is RunStatus.SUCCESS
    assert result.thread_id == "thread-one"
    assert result.turn_count == 1
    assert result.failure_count == 0
    assert client.start_calls == 1
    assert client.resume_calls == []
    assert len(client.prompts) == 1
    assert "实现一个功能" in client.prompts[0]
    run_dir = repo / ".codex-orchestrator/runs/workflow-test"
    assert (run_dir / "state.json").is_file()
    assert (run_dir / "result.json").is_file()
    assert (run_dir / "report.md").is_file()
    assert len(list((run_dir / "logs/round-01").glob("*.log"))) == 3
    saved_state = StateStore(repo).load_state("workflow-test")
    assert saved_state.protected_test_paths == ["backend/tests/test_before.py"]
    assert not (repo / ".codex-orchestrator/active.lock").exists()


def test_one_failure_then_success_uses_one_repair_on_same_thread(repo: Path) -> None:
    client = FakeCodexClient()
    validator = FakeValidator([(False, [1]), (True, [0, 0, 0])])

    result = workflow_with(repo, client, validator).start(task())

    assert result.status is RunStatus.SUCCESS
    assert result.failure_count == 1
    assert result.turn_count == 2
    assert result.thread_id == "thread-one"
    assert client.start_calls == 1
    assert len(client.prompts) == 2
    assert "修复第 1 次验证失败" in client.prompts[1]
    assert "failure output" in client.prompts[1]


def test_multiple_failed_commands_in_one_round_increment_only_once(repo: Path) -> None:
    client = FakeCodexClient()
    validator = FakeValidator([(False, [1, 2, 0]), (True, [0, 0, 0])])

    result = workflow_with(repo, client, validator).start(task())

    assert len(result.rounds[0].failed_results) == 2
    assert result.failure_count == 1
    assert result.turn_count == 2
    assert result.status is RunStatus.SUCCESS


def test_third_failure_stops_after_initial_and_two_repairs(repo: Path) -> None:
    client = FakeCodexClient()
    validator = FakeValidator(
        [(False, [1]), (False, [1]), (False, [1])]
    )

    result = workflow_with(repo, client, validator).start(task())

    assert result.status is RunStatus.MANUAL_REVIEW
    assert result.failure_count == 3
    assert result.turn_count == 3
    assert validator.round_numbers == [1, 2, 3]
    assert len(client.prompts) == 3
    assert sum("# 修复第" in prompt for prompt in client.prompts) == 2


def test_resume_uses_saved_thread_and_pending_repair(repo: Path) -> None:
    store = StateStore(repo)
    saved_task = task()
    state = store.initialize_run(saved_task)
    state.thread_id = "saved-thread"
    state.turn_count = 1
    failed = FakeValidator([(False, [1])]).validate(1)
    state.add_round(failed)
    assert state.phase is RunPhase.PROMPT_PENDING
    assert state.pending_prompt_kind is PromptKind.REPAIR
    store.save_state(state)

    client = FakeCodexClient(thread_id="unused")
    validator = FakeValidator([(True, [0, 0, 0])])
    result = workflow_with(repo, client, validator).resume(saved_task.task_id)

    assert result.status is RunStatus.SUCCESS
    assert result.thread_id == "saved-thread"
    assert client.start_calls == 0
    assert client.resume_calls == ["saved-thread"]
    assert len(client.prompts) == 1
    assert "修复第 1 次验证失败" in client.prompts[0]


def test_resume_from_in_progress_turn_does_not_duplicate_prompt(repo: Path) -> None:
    store = StateStore(repo)
    saved_task = task()
    state = store.initialize_run(saved_task)
    state.thread_id = "saved-thread"
    state.turn_count = 1
    state.phase = RunPhase.CODEX_TURN
    state.pending_prompt_kind = None
    store.save_state(state)

    client = FakeCodexClient()
    validator = FakeValidator([(True, [0, 0, 0])])
    result = workflow_with(repo, client, validator).resume(saved_task.task_id)

    assert result.status is RunStatus.SUCCESS
    assert client.resume_calls == ["saved-thread"]
    assert client.prompts == []
    assert client.verify_calls == [1]
    assert result.turn_count == 1


def test_resume_refuses_validation_when_saved_turn_cannot_be_confirmed(
    repo: Path,
) -> None:
    store = StateStore(repo)
    saved_task = task()
    state = store.initialize_run(saved_task)
    state.thread_id = "saved-thread"
    state.turn_count = 1
    state.phase = RunPhase.CODEX_TURN
    state.pending_prompt_kind = None
    store.save_state(state)

    client = FakeCodexClient(
        verify_error=InfrastructureError("saved turn is interrupted")
    )
    validator = FakeValidator([(True, [0, 0, 0])])
    result = workflow_with(repo, client, validator).resume(saved_task.task_id)

    assert result.status is RunStatus.INFRASTRUCTURE_ERROR
    assert result.failure_count == 0
    assert result.turn_count == 1
    assert validator.round_numbers == []
    assert client.prompts == []


def test_unfinished_state_blocks_a_different_new_task_after_process_exit(
    repo: Path,
) -> None:
    store = StateStore(repo)
    first = task()
    store.initialize_run(first)
    second = TaskSpec(
        task_id="second-task",
        requirement="另一个功能",
        acceptance_criteria=["另一个标准"],
    )
    client = FakeCodexClient()
    validator = FakeValidator([(True, [0, 0, 0])])

    with pytest.raises(ActiveRunError, match="unfinished task.*workflow-test"):
        workflow_with(repo, client, validator).start(second)

    assert not (repo / ".codex-orchestrator/active.lock").exists()
    assert not (store.run_dir(second.task_id) / "state.json").exists()


def test_unexpected_orchestrator_exception_becomes_reported_infrastructure_error(
    repo: Path,
) -> None:
    class BrokenPromptRenderer:
        def initial_prompt(self, *_args: Any) -> str:
            raise OSError("template unavailable")

    client = FakeCodexClient()
    validator = FakeValidator([(True, [0, 0, 0])])
    workflow = OrchestrationWorkflow(
        repo,
        client_factory=lambda _root: client,
        validator_factory=lambda _root, _baseline: validator,
        prompt_renderer=BrokenPromptRenderer(),  # type: ignore[arg-type]
    )

    result = workflow.start(task())

    assert result.status is RunStatus.INFRASTRUCTURE_ERROR
    assert result.failure_count == 0
    assert "OSError" in (result.infrastructure_error or "")
    assert (repo / ".codex-orchestrator/runs/workflow-test/report.md").is_file()
    assert not (repo / ".codex-orchestrator/active.lock").exists()


def test_validation_infrastructure_error_persists_partial_command_logs(
    repo: Path,
) -> None:
    class PartialInfrastructureValidator(FakeValidator):
        def __init__(self) -> None:
            super().__init__([])

        def validate(self, round_number: int) -> ValidationRound:
            self.round_numbers.append(round_number)
            completed = CommandResult(
                command=["first-check"],
                cwd=str(repo),
                stage="full",
                exit_code=0,
                stdout="completed before failure",
            )
            failed_to_start = CommandResult(
                command=["second-check"],
                cwd=str(repo),
                stage="full",
                exit_code=None,
                stderr="npm could not start",
                infrastructure_error="npm could not start",
            )
            return ValidationRound(
                round_number=round_number,
                full_results=[completed, failed_to_start],
                passed=False,
                stage="full",
                failure_summary="second-check: infrastructure error",
                infrastructure_error="npm could not start",
            )

    client = FakeCodexClient()
    validator = PartialInfrastructureValidator()

    result = workflow_with(repo, client, validator).start(task())

    assert result.status is RunStatus.INFRASTRUCTURE_ERROR
    assert result.failure_count == 0
    assert len(result.rounds) == 1
    assert len(result.rounds[0].full_results) == 2
    log_dir = repo / ".codex-orchestrator/runs/workflow-test/logs/round-01"
    assert len(list(log_dir.glob("*.log"))) == 2


@pytest.mark.parametrize(
    "failure_location",
    ["validation_preflight", "sdk_preflight", "turn", "validation"],
)
def test_infrastructure_error_stops_without_counting_validation_failure(
    repo: Path, failure_location: str
) -> None:
    error = InfrastructureError("network or local tool unavailable")
    client = FakeCodexClient(
        enter_error=error if failure_location == "sdk_preflight" else None,
        run_error=error if failure_location == "turn" else None,
    )
    validator = FakeValidator(
        [(True, [0])],
        preflight_error=(
            error if failure_location == "validation_preflight" else None
        ),
        validate_error=error if failure_location == "validation" else None,
    )
    if failure_location in {"validation_preflight", "sdk_preflight"}:
        expected_turns = 0
    else:
        expected_turns = 1

    result = workflow_with(repo, client, validator).start(task())

    assert result.status is RunStatus.INFRASTRUCTURE_ERROR
    assert result.failure_count == 0
    assert result.turn_count == expected_turns
    assert result.infrastructure_error == "network or local tool unavailable"
    assert not (repo / ".codex-orchestrator/active.lock").exists()
