from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from orchestrator.codex_loop import codex_client
from orchestrator.codex_loop.codex_client import (
    CodexClient,
    CodexRunResult,
    InfrastructureError,
)


class FakeSandbox:
    workspace_write = object()


class FakeTurnStatus:
    completed = object()
    failed = "failed"


class FakeThread:
    def __init__(
        self,
        thread_id: str,
        results: list[Any] | None = None,
        history: list[Any] | None = None,
    ) -> None:
        self.id = thread_id
        self.results = list(results or [])
        self.history = list(history or [])
        self.prompts: list[str] = []

    def run(self, prompt: str) -> Any:
        self.prompts.append(prompt)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def read(self, *, include_turns: bool = False) -> Any:
        assert include_turns is True
        return SimpleNamespace(thread=SimpleNamespace(turns=self.history))


class FakeCodex:
    def __init__(
        self,
        *,
        account: Any = object(),
        start_thread: FakeThread | None = None,
        resume_thread: FakeThread | None = None,
        account_error: Exception | None = None,
    ) -> None:
        self.account_value = account
        self.start_thread_value = start_thread or FakeThread("thr_started")
        self.resume_thread_value = resume_thread or FakeThread("thr_resumed")
        self.account_error = account_error
        self.entered = False
        self.closed = False
        self.account_calls = 0
        self.start_kwargs: dict[str, Any] | None = None
        self.resume_args: tuple[str, dict[str, Any]] | None = None
        self.config: Any | None = None

    def __enter__(self) -> FakeCodex:
        self.entered = True
        return self

    def __exit__(self, *_args: Any) -> None:
        self.closed = True

    def account(self) -> Any:
        self.account_calls += 1
        if self.account_error is not None:
            raise self.account_error
        return SimpleNamespace(account=self.account_value)

    def thread_start(self, **kwargs: Any) -> FakeThread:
        self.start_kwargs = kwargs
        return self.start_thread_value

    def thread_resume(self, thread_id: str, **kwargs: Any) -> FakeThread:
        self.resume_args = (thread_id, kwargs)
        return self.resume_thread_value


class FakeCodexConfig:
    def __init__(self, *, codex_bin: str) -> None:
        self.codex_bin = codex_bin


def install_fake_sdk(
    monkeypatch: pytest.MonkeyPatch,
    fake_codex: Any,
    *,
    bypass_runtime_check: bool = True,
) -> None:
    def create_codex(config: Any) -> Any:
        fake_codex.config = config
        return fake_codex

    sdk_module = SimpleNamespace(
        Codex=create_codex,
        CodexConfig=FakeCodexConfig,
        Sandbox=FakeSandbox,
    )
    types_module = SimpleNamespace(TurnStatus=FakeTurnStatus)

    def fake_import(name: str) -> Any:
        if name == "openai_codex":
            return sdk_module
        if name == "openai_codex.types":
            return types_module
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr(codex_client, "import_module", fake_import)
    if bypass_runtime_check:
        monkeypatch.setattr(CodexClient, "_verify_runtime", lambda self: None)


def completed_result(text: str | None = "done") -> Any:
    return SimpleNamespace(
        status=FakeTurnStatus.completed,
        error=None,
        final_response=text,
    )


def test_missing_sdk_is_an_infrastructure_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    def missing_sdk(_name: str) -> Any:
        raise ModuleNotFoundError("openai_codex")

    monkeypatch.setattr(codex_client, "import_module", missing_sdk)

    with pytest.raises(InfrastructureError, match="SDK is unavailable"):
        CodexClient(tmp_path).preflight()


def test_preflight_checks_account_once_and_context_manager_closes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    fake = FakeCodex()
    install_fake_sdk(monkeypatch, fake)

    with CodexClient(tmp_path) as client:
        client.preflight()
        assert fake.entered is True
        assert fake.account_calls == 1
        assert fake.config.codex_bin == str(
            codex_client.DEFAULT_CODEX_RUNTIME_PATH.resolve()
        )

    assert fake.closed is True
    assert client.thread_id is None


def test_preflight_rejects_missing_authentication_and_closes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    fake = FakeCodex(account=None)
    install_fake_sdk(monkeypatch, fake)

    with pytest.raises(InfrastructureError, match="not authenticated"):
        CodexClient(tmp_path).preflight()

    assert fake.closed is True


def test_app_server_start_failure_is_an_infrastructure_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    class BrokenCodex:
        def __init__(self, _config: Any) -> None:
            raise OSError("app-server unavailable")

    sdk_module = SimpleNamespace(
        Codex=BrokenCodex,
        CodexConfig=FakeCodexConfig,
        Sandbox=FakeSandbox,
    )
    types_module = SimpleNamespace(TurnStatus=FakeTurnStatus)
    monkeypatch.setattr(
        codex_client,
        "import_module",
        lambda name: sdk_module if name == "openai_codex" else types_module,
    )
    monkeypatch.setattr(CodexClient, "_verify_runtime", lambda self: None)

    with pytest.raises(InfrastructureError, match="App Server"):
        CodexClient(tmp_path).preflight()


def test_missing_project_runtime_does_not_fall_back_to_global_codex(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    fake = FakeCodex()
    install_fake_sdk(monkeypatch, fake, bypass_runtime_check=False)
    missing_runtime = tmp_path / "missing" / "codex"

    with pytest.raises(
        InfrastructureError,
        match=r"Project-local Codex runtime is missing.*npm ci --prefix orchestrator",
    ):
        CodexClient(tmp_path, runtime_path=missing_runtime).preflight()

    assert fake.entered is False


def test_runtime_version_mismatch_is_an_infrastructure_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    fake = FakeCodex()
    install_fake_sdk(monkeypatch, fake, bypass_runtime_check=False)
    runtime = tmp_path / "codex"
    runtime.write_text("#!/bin/sh\n", encoding="utf-8")
    runtime.chmod(0o755)
    monkeypatch.setattr(
        codex_client.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="codex-cli 0.143.0\n",
            stderr="",
        ),
    )

    with pytest.raises(
        InfrastructureError,
        match=r"version mismatch \(required=0\.144\.4, found=0\.143\.0\)",
    ):
        CodexClient(tmp_path, runtime_path=runtime).preflight()

    assert fake.entered is False


def test_runtime_version_probe_timeout_is_an_infrastructure_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    fake = FakeCodex()
    install_fake_sdk(monkeypatch, fake, bypass_runtime_check=False)
    runtime = tmp_path / "codex"
    runtime.write_text("#!/bin/sh\n", encoding="utf-8")
    runtime.chmod(0o755)

    def time_out(*_args: Any, **_kwargs: Any) -> Any:
        raise codex_client.subprocess.TimeoutExpired(
            [str(runtime), "--version"], timeout=30
        )

    monkeypatch.setattr(codex_client.subprocess, "run", time_out)

    with pytest.raises(InfrastructureError, match="version check timed out"):
        CodexClient(tmp_path, runtime_path=runtime).preflight()

    assert fake.entered is False


def test_verified_project_runtime_is_passed_to_codex_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    fake = FakeCodex()
    install_fake_sdk(monkeypatch, fake, bypass_runtime_check=False)
    runtime = tmp_path / "codex"
    runtime.write_text("#!/bin/sh\n", encoding="utf-8")
    runtime.chmod(0o755)

    def verify_version(command: list[str], **kwargs: Any) -> Any:
        assert command == [str(runtime.resolve()), "--version"]
        assert kwargs == {
            "capture_output": True,
            "text": True,
            "timeout": 30,
            "check": False,
            "shell": False,
        }
        return SimpleNamespace(
            returncode=0,
            stdout=f"codex-cli {codex_client.PINNED_CODEX_RUNTIME_VERSION}\n",
            stderr="",
        )

    monkeypatch.setattr(codex_client.subprocess, "run", verify_version)

    with CodexClient(tmp_path, runtime_path=runtime) as client:
        assert fake.entered is True
        assert fake.config.codex_bin == str(runtime.resolve())

    assert fake.closed is True


def test_runtime_version_pin_matches_package_and_lock_file() -> None:
    orchestrator_root = Path(__file__).resolve().parents[1]
    package = json.loads(
        (orchestrator_root / "package.json").read_text(encoding="utf-8")
    )
    lock = json.loads(
        (orchestrator_root / "package-lock.json").read_text(encoding="utf-8")
    )
    expected = codex_client.PINNED_CODEX_RUNTIME_VERSION

    assert package["dependencies"]["@openai/codex"] == expected
    assert lock["packages"][""]["dependencies"]["@openai/codex"] == expected
    assert lock["packages"]["node_modules/@openai/codex"]["version"] == expected


def test_start_thread_uses_repo_root_workspace_write_and_default_sdk_options(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    fake = FakeCodex(start_thread=FakeThread("thr_new"))
    install_fake_sdk(monkeypatch, fake)
    client = CodexClient(tmp_path)

    assert client.start_thread() == "thr_new"
    assert client.thread_id == "thr_new"
    assert fake.start_kwargs == {
        "cwd": str(tmp_path.resolve()),
        "sandbox": FakeSandbox.workspace_write,
    }
    assert "model" not in fake.start_kwargs
    assert fake.account_calls == 1

    client.close()


def test_resume_then_run_reuses_thread_and_returns_stable_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    thread = FakeThread("thr_saved", [completed_result("fixed")])
    fake = FakeCodex(resume_thread=thread)
    install_fake_sdk(monkeypatch, fake)
    client = CodexClient(tmp_path)

    assert client.resume_thread("thr_saved") == "thr_saved"
    result = client.run("repair the failing test")

    assert result == CodexRunResult(
        thread_id="thr_saved",
        final_response="fixed",
    )
    assert thread.prompts == ["repair the failing test"]
    assert fake.resume_args == (
        "thr_saved",
        {
            "cwd": str(tmp_path.resolve()),
            "sandbox": FakeSandbox.workspace_write,
        },
    )

    client.close()


def test_non_completed_turn_is_an_infrastructure_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    failed = SimpleNamespace(
        status=FakeTurnStatus.failed,
        error=SimpleNamespace(message="network failed"),
        final_response=None,
    )
    thread = FakeThread("thr_failed", [failed])
    fake = FakeCodex(start_thread=thread)
    install_fake_sdk(monkeypatch, fake)
    client = CodexClient(tmp_path)
    client.start_thread()

    with pytest.raises(InfrastructureError, match="did not complete.*status=failed"):
        client.run("make the change")

    client.close()


def test_saved_turn_must_exist_and_be_completed_before_resume_validation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    completed_turn = SimpleNamespace(status=FakeTurnStatus.completed)
    thread = FakeThread("thr_saved", history=[completed_turn])
    fake = FakeCodex(resume_thread=thread)
    install_fake_sdk(monkeypatch, fake)
    client = CodexClient(tmp_path)
    client.resume_thread("thr_saved")

    client.verify_turn_completed(1)

    with pytest.raises(InfrastructureError, match="actual_turns=1"):
        client.verify_turn_completed(2)
    client.close()


def test_interrupted_saved_turn_is_an_infrastructure_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    interrupted_turn = SimpleNamespace(status="interrupted")
    thread = FakeThread("thr_saved", history=[interrupted_turn])
    fake = FakeCodex(resume_thread=thread)
    install_fake_sdk(monkeypatch, fake)
    client = CodexClient(tmp_path)
    client.resume_thread("thr_saved")

    with pytest.raises(InfrastructureError, match="not completed.*interrupted"):
        client.verify_turn_completed(1)
    client.close()


@pytest.mark.parametrize(
    ("stage", "expected"),
    [
        ("account", "authentication preflight"),
        ("turn", "turn could not be completed"),
    ],
)
def test_authentication_and_turn_transport_errors_are_infrastructure_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
    stage: str,
    expected: str,
) -> None:
    if stage == "account":
        fake = FakeCodex(account_error=ConnectionError("offline"))
        install_fake_sdk(monkeypatch, fake)
        action = lambda: CodexClient(tmp_path).preflight()
    else:
        thread = FakeThread("thr_network", [ConnectionError("offline")])
        fake = FakeCodex(start_thread=thread)
        install_fake_sdk(monkeypatch, fake)
        client = CodexClient(tmp_path)
        client.start_thread()
        action = lambda: client.run("make the change")

    with pytest.raises(InfrastructureError, match=expected):
        action()
