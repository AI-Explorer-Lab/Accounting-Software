from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from orchestrator.backend.service import vscode_workspace
from orchestrator.backend.service.vscode_workspace import (
    VSCodeWorkspaceError,
    VSCodeWorkspaceOpener,
)


def test_opener_verifies_delivery_then_reuses_the_current_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    cli = tmp_path / "code"
    cli.write_text("", encoding="utf-8")
    commands: list[list[str]] = []

    def run(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        arguments = command[3:] if command[:3] == ["git", "-C", str(worktree)] else []
        outputs = {
            ("rev-parse", "--show-toplevel"): str(worktree),
            ("rev-parse", "--abbrev-ref", "HEAD"): "codex/task-1",
            ("rev-parse", "HEAD"): "a" * 40,
        }
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=outputs.get(tuple(arguments), ""),
            stderr="",
        )

    monkeypatch.setattr(vscode_workspace.subprocess, "run", run)
    VSCodeWorkspaceOpener(cli).open_reusing_window(
        worktree,
        "codex/task-1",
        "a" * 40,
    )

    assert commands[-1] == [str(cli), "--reuse-window", str(worktree)]


def test_opener_refuses_a_worktree_on_an_unexpected_branch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    cli = tmp_path / "code"
    cli.write_text("", encoding="utf-8")

    def run(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        arguments = command[3:]
        output = (
            str(worktree)
            if arguments == ["rev-parse", "--show-toplevel"]
            else "main"
        )
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")

    monkeypatch.setattr(vscode_workspace.subprocess, "run", run)
    with pytest.raises(VSCodeWorkspaceError, match="recorded branch"):
        VSCodeWorkspaceOpener(cli).open_reusing_window(
            worktree,
            "codex/task-1",
            "a" * 40,
        )
