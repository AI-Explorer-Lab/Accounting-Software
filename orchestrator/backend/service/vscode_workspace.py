from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class VSCodeWorkspaceError(RuntimeError):
    """Raised when a verified task worktree cannot be opened in VS Code."""


class VSCodeWorkspaceOpener:
    """Open one verified task worktree in the currently reused VS Code window."""

    _MACOS_CLI_CANDIDATES = (
        Path("/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"),
        Path.home()
        / "Applications/Visual Studio Code.app/Contents/Resources/app/bin/code",
    )

    def __init__(self, cli_path: str | Path | None = None) -> None:
        self.cli_path = Path(cli_path).expanduser().resolve() if cli_path else None

    def open_reusing_window(
        self,
        worktree: Path,
        expected_branch: str,
        expected_commit: str,
    ) -> None:
        resolved = worktree.expanduser().resolve()
        if not resolved.is_dir():
            raise VSCodeWorkspaceError("Task worktree is unavailable")

        actual_root = Path(
            self._git(resolved, "rev-parse", "--show-toplevel")
        ).resolve()
        if actual_root != resolved:
            raise VSCodeWorkspaceError("Task worktree points at an unexpected Git root")
        if (
            self._git(resolved, "rev-parse", "--abbrev-ref", "HEAD")
            != expected_branch
        ):
            raise VSCodeWorkspaceError(
                "Task worktree is no longer on its recorded branch"
            )
        if self._git(resolved, "rev-parse", "HEAD") != expected_commit:
            raise VSCodeWorkspaceError(
                "Task worktree HEAD no longer matches its committed delivery"
            )

        self._run(
            [str(self._resolve_cli()), "--reuse-window", str(resolved)],
            "VS Code could not open the task worktree",
        )

    def _git(self, worktree: Path, *arguments: str) -> str:
        completed = self._run(
            ["git", "-C", str(worktree), *arguments],
            "Task worktree verification failed",
        )
        return completed.stdout.strip()

    def _resolve_cli(self) -> Path:
        if self.cli_path is not None:
            if self.cli_path.is_file():
                return self.cli_path
            raise VSCodeWorkspaceError("Configured VS Code CLI does not exist")

        discovered = shutil.which("code")
        if discovered:
            return Path(discovered).resolve()
        for candidate in self._MACOS_CLI_CANDIDATES:
            if candidate.is_file():
                return candidate
        raise VSCodeWorkspaceError(
            "VS Code CLI was not found; install the 'code' command or use the "
            "standard macOS app location"
        )

    @staticmethod
    def _run(
        command: list[str], failure_message: str
    ) -> subprocess.CompletedProcess[str]:
        try:
            completed = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise VSCodeWorkspaceError(failure_message) from exc
        if completed.returncode != 0:
            raise VSCodeWorkspaceError(failure_message)
        return completed
