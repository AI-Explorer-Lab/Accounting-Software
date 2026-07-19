"""Dynaconf loading and startup validation for the local orchestrator API."""

from __future__ import annotations

import os
from pathlib import Path
import re
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


def projects_from_settings(config: Any = settings) -> list[dict[str, object]]:
    """Return an allowlisted project registry with a backward-compatible default."""

    agent = config.get("agent", {}) or {}
    configured = agent.get("projects", []) or []
    if not configured:
        root = repo_root_from_settings(config)
        return [
            {
                "project_id": "default",
                "name": root.name,
                "repo_root": root,
                "is_default": True,
                "knowledge_actor_id": str(
                    agent.get("knowledge_actor_id", "")
                ).strip(),
            }
        ]
    if isinstance(configured, (str, bytes)):
        raise RuntimeError("agent.projects must be a list")
    projects: list[dict[str, object]] = []
    seen: set[str] = set()
    for index, item in enumerate(configured):
        if not isinstance(item, dict):
            raise RuntimeError("every agent.projects item must be an object")
        project_id = str(item.get("id", "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", project_id):
            raise RuntimeError(f"invalid project id at agent.projects[{index}]")
        if project_id in seen:
            raise RuntimeError(f"duplicate project id: {project_id}")
        seen.add(project_id)
        configured_root = item.get("repo_root")
        if configured_root in {None, ""}:
            raise RuntimeError(f"project {project_id} has no repo_root")
        root = Path(str(configured_root)).expanduser()
        if not root.is_absolute():
            root = REPO_ROOT / root
        root = root.resolve()
        projects.append(
            {
                "project_id": project_id,
                "name": str(item.get("name") or root.name),
                "repo_root": root,
                "is_default": bool(item.get("default", index == 0)),
                "knowledge_actor_id": str(
                    item.get("knowledge_actor_id", "")
                ).strip(),
            }
        )
    defaults = [item for item in projects if item["is_default"]]
    if len(defaults) != 1:
        raise RuntimeError("agent.projects must contain exactly one default project")
    return projects


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

    max_parallel = int(agent.get("max_parallel_projects", 1))
    if max_parallel < 1:
        raise RuntimeError("agent.max_parallel_projects must be at least 1")

    if bool(agent.get("harness_enabled", False)):
        knowledge = agent.get("knowledge", {}) or {}
        knowledge_root = Path(str(knowledge.get("repo_root", ""))).expanduser()
        registry_path = Path(str(knowledge.get("mcp_registry", ""))).expanduser()
        writer = str(knowledge.get("knowledge_writer_actor_id", "")).strip()
        if not knowledge_root.is_dir():
            raise RuntimeError("agent.knowledge.repo_root must exist")
        if not registry_path.is_file():
            raise RuntimeError("agent.knowledge.mcp_registry must exist")
        if not writer:
            raise RuntimeError(
                "agent.knowledge.knowledge_writer_actor_id must not be blank"
            )

    for project in projects_from_settings(config):
        repo_root = Path(project["repo_root"])
        if not repo_root.is_dir():
            raise RuntimeError(
                f"project repo_root does not exist: {repo_root}"
            )
        if bool(agent.get("harness_enabled", False)) and not str(
            project.get("knowledge_actor_id", "")
        ).strip():
            raise RuntimeError(
                f"project {project['project_id']} has no knowledge_actor_id"
            )


load_environment()
