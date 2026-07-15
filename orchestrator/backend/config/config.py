"""Dynaconf loading and startup validation for the local orchestrator API."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dynaconf import Dynaconf


CONFIG_FILE = Path(__file__).with_name("app.yaml")
REPO_ROOT = Path(__file__).resolve().parents[3]

settings = Dynaconf(
    envvar_prefix="ORCHESTRATOR",
    env_switcher="ORCHESTRATOR_ENV",
    environments=True,
    load_dotenv=True,
    merge_enabled=True,
    settings_files=[str(CONFIG_FILE)],
)


def load_environment(environment: str | None = None) -> Dynaconf:
    """Select the configured environment and return the shared settings."""

    selected = environment or os.getenv("ORCHESTRATOR_ENV", "development")
    settings.setenv(selected)
    return settings


def repo_root_from_settings(config: Any = settings) -> Path:
    """Resolve the target repository without depending on the process cwd."""

    agent = config.get("agent", {}) or {}
    configured = agent.get("repo_root")
    if configured in {None, ""}:
        return REPO_ROOT
    path = Path(str(configured)).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def validate_settings(config: Any = settings) -> None:
    """Fail fast for invalid local API or orchestrator settings."""

    server = config.get("server", {}) or {}
    agent = config.get("agent", {}) or {}

    port = int(server.get("port", 0))
    if not 1 <= port <= 65535:
        raise RuntimeError("server.port must be between 1 and 65535")

    origins = server.get("cors_origins", [])
    if isinstance(origins, (str, bytes)) or not origins:
        raise RuntimeError("server.cors_origins must contain at least one origin")

    timeout = float(agent.get("validation_timeout_seconds", 0))
    if timeout <= 0:
        raise RuntimeError("agent.validation_timeout_seconds must be greater than zero")

    repo_root = repo_root_from_settings(config)
    if not repo_root.is_dir():
        raise RuntimeError(f"agent.repo_root does not exist: {repo_root}")


load_environment()
