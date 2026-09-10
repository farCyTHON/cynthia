"""Focus sessions — snapshot-based work tracking and K-Means mode analysis.

`begin_session` / `focus start` records a lightweight snapshot in storage.meta.
`finalize_session` / `focus stop` re-scans and diffs against that snapshot.
The interactive shell also auto-begins sessions and passes watcher-based
`files_modified` into finalize. Sessions are classified into work modes via
StandardScaler + KMeans when enough history exists.
"""
from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import config, workspace
from .git_observer import git_runtime_available, read_git_info
from .ml.kmeans_focus import WORK_MODES, cluster_recent_sessions
from .ml.knn_similar import (
    DEFAULT_K,
    SessionFeatureSnapshot,
    SimilarSessionsResult,
    find_similar_sessions,
)
from .scanner import DEFAULT_IGNORES, count_files_modified, scan_project
from .storage import FOCUS_SNAPSHOT_KEY, Project, Session, Storage

MIN_SESSION_MINUTES = 1.0
MIN_SESSIONS_FOR_ANALYZE = 8

FEATURE_KEYS = (
    "files_modified",
    "commits",
    "lines_added",
    "lines_deleted",
    "duration_minutes",
    "todo_changes",
)


class FocusAlreadyActive(RuntimeError):
    pass


class NoActiveFocus(RuntimeError):
    pass


class SessionTooShort(RuntimeError):
    pass


@dataclass
class FocusStartResult:
    project_name: str
    started_at: float


@dataclass
class AnalyzeResult:
    """Result of K-Means work-mode analysis over stored sessions."""

    enough_data: bool
    session_count: int
    percentages: dict[str, int]
    message: Optional[str] = None


@dataclass
class LiveSessionMetrics:
    """Computed metrics for the in-progress focus snapshot (not yet persisted)."""

    project: Project
    started_at: float
    ended_at: float
    duration_minutes: float
    files_modified: int
    commits: int
    lines_added: int
    lines_deleted: int
    todo_changes: int


def begin_session(project: Project, *, replace_active: bool = False) -> FocusStartResult:
    """Snapshot project state and mark a focus session as active."""
    config.ensure_initialized()
    settings = config.Settings.load()
    with Storage() as db:
        existing = db.get_meta(FOCUS_SNAPSHOT_KEY)
        if existing and not replace_active:
            raise FocusAlreadyActive(
                f"A focus session is already active for '{existing.get('project_name')}'. "
                "Run 'cynthia focus stop' first."
            )
        if existing and replace_active:
            db.delete_meta(FOCUS_SNAPSHOT_KEY)

        scan = scan_project(project.path, ignored_dirs=set(settings.ignored_dirs))
        git_info = read_git_info(project.path)
        started_at = time.time()
        db.set_meta(
            FOCUS_SNAPSHOT_KEY,
            {
                "project_id": project.id,
                "project_name": project.name,
                "project_path": project.path,
                "started_at": started_at,
                "commit_count": git_info.commit_count if git_info.is_repo else 0,
                "todo_count": len(scan.todos),
            },
        )
        db.touch_project(project.name)
    return FocusStartResult(project_name=project.name, started_at=started_at)


def start_focus(project: Project) -> FocusStartResult:
    """CLI alias for begin_session."""
    return begin_session(project)


def has_active_session() -> bool:
    config.ensure_initialized()
    with Storage() as db:
        return db.get_meta(FOCUS_SNAPSHOT_KEY) is not None


def active_session_project_name() -> Optional[str]:
    config.ensure_initialized()
    with Storage() as db:
        snap = db.get_meta(FOCUS_SNAPSHOT_KEY)
        return snap.get("project_name") if snap else None


def compute_live_metrics(*, files_modified: Optional[int] = None) -> LiveSessionMetrics:
    """Compute real-time metrics for the active focus snapshot.

    Args:
        files_modified: Optional watcher-based file count from the interactive shell.
            When omitted, files are counted via mtime walk.

    Returns:
        ``LiveSessionMetrics`` for the current snapshot.

    Raises:
        NoActiveFocus: If no focus snapshot is active.
    """
    config.ensure_initialized()
    settings = config.Settings.load()
    with Storage() as db:
        snap = db.get_meta(FOCUS_SNAPSHOT_KEY)
        if not snap:
            raise NoActiveFocus("No active focus session. Run 'cynthia focus start' first.")

        project = db.get_project_by_id(int(snap["project_id"]))
        if not project:
            raise NoActiveFocus("The project for this focus session no longer exists.")

        started_at = float(snap["started_at"])
        ended_at = time.time()
        duration_minutes = (ended_at - started_at) / 60.0
        path = Path(project.path)
        stop_scan = scan_project(path, ignored_dirs=set(settings.ignored_dirs))

        commits = count_commits_in_window(path, started_at, ended_at)
        if commits == 0:
            stop_git = read_git_info(path)
            start_commits = int(snap.get("commit_count") or 0)
            stop_commits = stop_git.commit_count if stop_git.is_repo else 0
            commits = max(0, stop_commits - start_commits)

        committed_added, committed_deleted = read_line_stats(path, started_at, ended_at)
        dirty_added, dirty_deleted = read_uncommitted_line_stats(path)
        lines_added = committed_added + dirty_added
        lines_deleted = committed_deleted + dirty_deleted

        if files_modified is None:
            files_modified = count_files_modified(
                path, started_at, ended_at, ignored_dirs=set(settings.ignored_dirs)
            )
        todo_changes = abs(len(stop_scan.todos) - int(snap.get("todo_count") or 0))

        return LiveSessionMetrics(
            project=project,
            started_at=started_at,
            ended_at=ended_at,
            duration_minutes=round(duration_minutes, 2),
            files_modified=int(files_modified),
            commits=commits,
            lines_added=lines_added,
            lines_deleted=lines_deleted,
            todo_changes=todo_changes,
        )


def finalize_session(*, files_modified: Optional[int] = None) -> Session:
    """End the active session, compute metrics, and persist a sessions row.

    If ``files_modified`` is provided (shell watcher path), that count is used.
    Otherwise files are counted via mtime walk (CLI focus stop).
    """
    metrics = compute_live_metrics(files_modified=files_modified)
    if metrics.duration_minutes < MIN_SESSION_MINUTES:
        with Storage() as db:
            db.delete_meta(FOCUS_SNAPSHOT_KEY)
        raise SessionTooShort("Session too short to record.")

    with Storage() as db:
        session = db.add_session(
            project_id=metrics.project.id,
            started_at=metrics.started_at,
            ended_at=metrics.ended_at,
            duration_minutes=metrics.duration_minutes,
            files_modified=metrics.files_modified,
            commits=metrics.commits,
            lines_added=metrics.lines_added,
            lines_deleted=metrics.lines_deleted,
            todo_changes=metrics.todo_changes,
        )
        session.project_name = metrics.project.name
        db.delete_meta(FOCUS_SNAPSHOT_KEY)
        return session


def stop_focus() -> Session:
    """CLI alias for finalize_session (mtime-based file count)."""
    return finalize_session(files_modified=None)


def list_focus_sessions(project_name: Optional[str] = None) -> list[Session]:
    """List stored focus sessions, optionally filtered by project name."""
    config.ensure_initialized()
    with Storage() as db:
        project_id = None
        if project_name:
            project = workspace.resolve_project(project_name)
            project_id = project.id
        return db.list_sessions(project_id)


def similar_to_active_session(
    *,
    files_modified: Optional[int] = None,
    k: int = DEFAULT_K,
) -> SimilarSessionsResult:
    """Find the ``k`` historical sessions most similar to the current focus context.

    Prefer the in-progress focus snapshot (live metrics). If none is active,
    fall back to the most recent completed session for the active project.

    Args:
        files_modified: Optional watcher unique-path count from the shell.
        k: Number of neighbors to return.

    Returns:
        ``SimilarSessionsResult`` from the k-NN module.
    """
    config.ensure_initialized()
    exclude_id: Optional[int] = None
    query_source = "active snapshot"

    try:
        metrics = compute_live_metrics(files_modified=files_modified)
        project = metrics.project
        query: SessionFeatureSnapshot | Session = SessionFeatureSnapshot(
            files_modified=metrics.files_modified,
            commits=metrics.commits,
            lines_added=metrics.lines_added,
            lines_deleted=metrics.lines_deleted,
            duration_minutes=metrics.duration_minutes,
            todo_changes=metrics.todo_changes,
        )
    except NoActiveFocus:
        project = workspace.resolve_project(None)
        with Storage() as db:
            historical = db.list_sessions(project.id)
        if not historical:
            return SimilarSessionsResult(
                enough_data=False,
                query_source="none",
                matches=[],
                message=(
                    "No active focus session and no stored sessions for this project. "
                    "Open a project and record sessions first."
                ),
            )
        query = historical[0]  # most recent (list is started_at DESC)
        exclude_id = query.id
        query_source = f"latest session #{query.id}"

    with Storage() as db:
        historical = db.list_sessions(project.id)

    result = find_similar_sessions(
        query,
        historical,
        k=k,
        exclude_id=exclude_id,
    )
    result.query_source = query_source
    return result


def analyze_sessions(
    project_name: Optional[str] = None,
    all_projects: bool = False,
) -> AnalyzeResult:
    """Cluster sessions into four work modes and return percentage breakdown."""
    config.ensure_initialized()
    with Storage() as db:
        if all_projects:
            sessions = db.list_sessions(None)
        elif project_name:
            project = workspace.resolve_project(project_name)
            sessions = db.list_sessions(project.id)
        else:
            project = workspace.resolve_project(None)
            sessions = db.list_sessions(project.id)

        n = len(sessions)
        if n < MIN_SESSIONS_FOR_ANALYZE:
            return AnalyzeResult(
                enough_data=False,
                session_count=n,
                percentages={mode: 0 for mode in WORK_MODES},
                message=(
                    f"Not enough sessions yet to analyze focus patterns "
                    f"(need {MIN_SESSIONS_FOR_ANALYZE}+, have {n})."
                ),
            )

        clustered = cluster_recent_sessions(sessions)
        db.update_session_labels(clustered.labels_by_session_id)
        return AnalyzeResult(
            enough_data=True,
            session_count=n,
            percentages=clustered.percentages,
        )


def count_commits_in_window(root: str | Path, started_at: float, ended_at: float) -> int:
    """Count commits whose author date falls in [started_at, ended_at]."""
    if not git_runtime_available():
        return 0

    import os

    os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")
    try:
        from git import GitCommandError, InvalidGitRepositoryError, NoSuchPathError, Repo
    except ImportError:
        return 0

    root = Path(root).expanduser().resolve()
    try:
        repo = Repo(root, search_parent_directories=False)
    except (InvalidGitRepositoryError, NoSuchPathError):
        return 0

    since = dt.datetime.fromtimestamp(started_at, tz=dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    until = dt.datetime.fromtimestamp(ended_at, tz=dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    try:
        branch = repo.active_branch.name
    except (TypeError, ValueError):
        branch = "HEAD"

    try:
        commits = list(
            repo.iter_commits(branch, since=since, until=until, max_count=500)
        )
        return len(commits)
    except (GitCommandError, ValueError):
        return 0


def read_line_stats(root: str | Path, started_at: float, ended_at: float) -> tuple[int, int]:
    """Sum lines added/deleted via `git log --numstat` in the session window."""
    if not git_runtime_available():
        return 0, 0

    import os

    os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")
    try:
        from git import GitCommandError, InvalidGitRepositoryError, NoSuchPathError, Repo
    except ImportError:
        return 0, 0

    root = Path(root).expanduser().resolve()
    try:
        repo = Repo(root, search_parent_directories=False)
    except (InvalidGitRepositoryError, NoSuchPathError):
        return 0, 0

    since = dt.datetime.fromtimestamp(started_at, tz=dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    until = dt.datetime.fromtimestamp(ended_at, tz=dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    try:
        branch = repo.active_branch.name
    except (TypeError, ValueError):
        branch = "HEAD"

    try:
        raw = repo.git.log(
            branch,
            "--numstat",
            "--pretty=format:",
            f"--since={since}",
            f"--until={until}",
        )
    except GitCommandError:
        return 0, 0

    return _parse_numstat(raw)


def read_uncommitted_line_stats(root: str | Path) -> tuple[int, int]:
    """Sum uncommitted line churn via `git diff --numstat` (staged + unstaged)."""
    if not git_runtime_available():
        return 0, 0

    import os

    os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")
    try:
        from git import GitCommandError, InvalidGitRepositoryError, NoSuchPathError, Repo
    except ImportError:
        return 0, 0

    root = Path(root).expanduser().resolve()
    try:
        repo = Repo(root, search_parent_directories=False)
    except (InvalidGitRepositoryError, NoSuchPathError):
        return 0, 0

    added = 0
    deleted = 0
    for args in (["--numstat", "HEAD"], ["--numstat", "--cached", "HEAD"]):
        try:
            raw = repo.git.diff(*args)
        except GitCommandError:
            continue
        a, d = _parse_numstat(raw)
        added += a
        deleted += d
    return added, deleted


def _parse_numstat(raw: str) -> tuple[int, int]:
    added = 0
    deleted = 0
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        a, d = parts[0], parts[1]
        if a.isdigit():
            added += int(a)
        if d.isdigit():
            deleted += int(d)
    return added, deleted
