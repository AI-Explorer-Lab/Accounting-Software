"""Dynaconf settings loading and startup validation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dynaconf import Dynaconf


CONFIG_FILE = Path(__file__).with_name("app.yaml")

settings = Dynaconf(
    envvar_prefix="ACCOUNT",
    env_switcher="ACCOUNT_ENV",
    environments=True,
    load_dotenv=True,
    merge_enabled=True,
    settings_files=[str(CONFIG_FILE)],
)


def load_environment(environment: str | None = None) -> Dynaconf:
    """Select an environment and return the shared settings object."""
    selected = environment or os.getenv("ACCOUNT_ENV", "development")
    settings.setenv(selected)
    return settings


def validate_settings(config: Any = settings) -> None:
    """Fail fast when a required, non-secret database setting is absent."""
    required_keys = ("host", "port", "name", "user", "password")
    database = config.get("db", {})
    missing = [key for key in required_keys if not database.get(key)]
    if missing:
        fields = ", ".join(f"db.{key}" for key in missing)
        raise RuntimeError(f"Missing required configuration: {fields}")


load_environment()
