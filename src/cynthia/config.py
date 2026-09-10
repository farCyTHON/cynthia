"""Workspace configuration: where CYNTHIA keeps its local state.

Everything lives under ~/.cynthia (overridable via the CYNTHIA_HOME env
var, mainly so tests don't touch a real home directory). Nothing here
ever talks to the network — CYNTHIA is local-first by design.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import tomli_w

DEFAULT_HOME = Path.home() / ".cynthia"


def workspace_home() -> Path:
    override = os.environ.get("CYNTHIA_HOME")
    return Path(override).expanduser() if override else DEFAULT_HOME


def db_path() -> Path:
    return workspace_home() / "workspace.db"


def config_path() -> Path:
    return workspace_home() / "config.toml"


@dataclass
class Settings:
    """User-facing settings, persisted as TOML."""

    workspace_name: str = "default"
    theme: str = "gemini"
    activity_window_days: int = 7
    ignored_dirs: list[str] = field(
        default_factory=lambda: [
            ".git", "node_modules", "__pycache__", ".venv", "venv",
            "dist", "build", ".mypy_cache", ".pytest_cache", ".idea",
            ".vscode", "target", ".next", ".turbo",
        ]
    )

    @classmethod
    def load(cls) -> "Settings":
        path = config_path()
        if not path.exists():
            return cls()
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls(**{**cls().__dict__, **data})

    def save(self) -> None:
        workspace_home().mkdir(parents=True, exist_ok=True)
        with open(config_path(), "wb") as f:
            tomli_w.dump(self.__dict__, f)


def is_initialized() -> bool:
    return db_path().exists() and config_path().exists()


def ensure_initialized() -> None:
    """Raise a clear, catchable error if `cynthia init` hasn't run yet."""
    if not is_initialized():
        raise WorkspaceNotInitialized(
            "No CYNTHIA workspace found. Run 'cynthia init' first."
        )


class WorkspaceNotInitialized(RuntimeError):
    pass
