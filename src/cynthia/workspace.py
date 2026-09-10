"""Workspace Manager — the front door every command goes through.

Owns the lifecycle of a CYNTHIA workspace: creating it, registering
projects into it, and resolving "which project does the user mean"
(explicit name, path, or the currently active one). Everything else
(scanning, git reading, health scoring) is delegated to its own module —
this file just wires them together.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from git import GitCommandError
from git import Repo as GitRepo

from . import config
from .git_observer import GitInfo, read_git_info
from .health import HealthScore, compute_health
from .scanner import ScanResult, scan_project
from .storage import Project, Storage


class ProjectNotFound(RuntimeError):
    pass


class ProjectAlreadyExists(RuntimeError):
    pass


class NoActiveProject(RuntimeError):
    pass


class CloneFailed(RuntimeError):
    pass


_URL_PATTERN = re.compile(r"^(https?://|git@|ssh://|git://)")


def _is_remote_url(path_or_url: str) -> bool:
    return bool(_URL_PATTERN.match(str(path_or_url)))


def _name_from_url(url: str) -> str:
    tail = url.rstrip("/").split("/")[-1]
    return tail[:-4] if tail.endswith(".git") else tail


def _clone_dir() -> Path:
    d = config.workspace_home() / "repos"
    d.mkdir(parents=True, exist_ok=True)
    return d


def clone_project(url: str, name: Optional[str] = None) -> Path:
    """Clone a remote repo into the workspace's local cache and return its path."""
    project_name = name or _name_from_url(url)
    dest = _clone_dir() / project_name
    if dest.exists():
        return dest
    try:
        GitRepo.clone_from(url, dest)
    except GitCommandError as exc:
        raise CloneFailed(f"Could not clone '{url}': {exc}") from exc
    return dest


@dataclass
class ProjectSnapshot:
    """Everything the UI needs to render `status` for one project, in one place."""

    project: Project
    scan: ScanResult
    git: GitInfo
    health: HealthScore


def init_workspace(name: str = "default") -> config.Settings:
    settings = config.Settings(workspace_name=name)
    settings.save()
    with Storage() as db:
        db.set_meta("initialized_at", __import__("time").time())
    return settings


def add_project(path: str | Path, name: Optional[str] = None) -> Project:
    config.ensure_initialized()

    if _is_remote_url(str(path)):
        project_name = name or _name_from_url(str(path))
        resolved = clone_project(str(path), project_name).resolve()
    else:
        resolved = Path(path).expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"No such path: {resolved}")
        project_name = name or resolved.name

    with Storage() as db:
        existing = db.get_project_by_path(str(resolved))
        if existing:
            return existing
        if db.get_project(project_name):
            raise ProjectAlreadyExists(
                f"A project named '{project_name}' is already registered. "
                f"Pass an explicit name to disambiguate."
            )
        scan = scan_project(resolved)
        return db.add_project(name=project_name, path=str(resolved), kind=scan.kind)


def remove_project(name: str) -> None:
    config.ensure_initialized()
    with Storage() as db:
        if not db.remove_project(name):
            raise ProjectNotFound(f"No project named '{name}'.")


def list_projects() -> list[Project]:
    config.ensure_initialized()
    with Storage() as db:
        return db.list_projects()


def resolve_project(name: Optional[str]) -> Project:
    """Resolve a project by name, falling back to the active one."""
    config.ensure_initialized()
    with Storage() as db:
        if name:
            project = db.get_project(name)
            if not project:
                # Also allow resolving by path, for convenience.
                resolved_path = str(Path(name).expanduser().resolve())
                project = db.get_project_by_path(resolved_path)
            if not project:
                raise ProjectNotFound(f"No project named '{name}'. Try 'cynthia list'.")
            return project

        active = db.active_project()
        if not active:
            raise NoActiveProject(
                "No active project. Use 'cynthia status <name>' or 'cynthia project open <path>' first."
            )
        project = db.get_project(active)
        if not project:
            raise NoActiveProject("The active project no longer exists. Try 'cynthia list'.")
        return project


def resolve_project_or_recent(name: Optional[str]) -> Project:
    """Like resolve_project, but falls back to the most recently opened one.

    Used by read-only commands (`doctor`) that should still have something
    sensible to report on when no project has been marked active yet.
    """
    try:
        return resolve_project(name)
    except NoActiveProject:
        with Storage() as db:
            projects = db.list_projects()  # last_opened DESC, then created_at DESC
        if not projects:
            raise ProjectNotFound(
                "No projects registered yet. Try 'cynthia add <path>'."
            ) from None
        return projects[0]


def open_project(path_or_name: str) -> Project:
    """Register a project if new, then mark it active — mirrors `cynthia project open`."""
    config.ensure_initialized()
    with Storage() as db:
        project = db.get_project(path_or_name)
        if not project:
            if _is_remote_url(path_or_name):
                project = add_project(path_or_name)
            else:
                candidate = Path(path_or_name).expanduser()
                if candidate.exists():
                    project = db.get_project_by_path(str(candidate.resolve()))
                    if not project:
                        project = add_project(candidate)
                else:
                    raise ProjectNotFound(f"No project named '{path_or_name}' and no such path.")
        db.touch_project(project.name)
        return project


def snapshot(project: Project) -> ProjectSnapshot:
    """Gather scan + git + health data for one project in a single pass."""
    settings = config.Settings.load()
    scan = scan_project(project.path, ignored_dirs=set(settings.ignored_dirs))
    git_info = read_git_info(project.path, activity_days=settings.activity_window_days)
    health = compute_health(project.path, scan, git_info)
    return ProjectSnapshot(project=project, scan=scan, git=git_info, health=health)