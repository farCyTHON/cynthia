"""Git Observer — reads repository metadata via GitPython.

Read-only: CYNTHIA never commits, stages, or mutates the repos it
watches. Everything here is derived from `git log` / refs / diff stats.

Git is optional: when the `git` executable is not installed, Cynthia
still starts and scans local projects — commit history is simply skipped.
"""
from __future__ import annotations

import datetime as dt
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_GIT_MODULE: Any | None = None
_GIT_RUNTIME_AVAILABLE: bool | None = None


def git_runtime_available() -> bool:
    """True when a `git` executable is on PATH."""
    global _GIT_RUNTIME_AVAILABLE
    if _GIT_RUNTIME_AVAILABLE is None:
        _GIT_RUNTIME_AVAILABLE = shutil.which("git") is not None
    return _GIT_RUNTIME_AVAILABLE


def _load_git():
    global _GIT_MODULE
    if _GIT_MODULE is not None:
        return _GIT_MODULE
    if not git_runtime_available():
        return None
    os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")
    try:
        import git as git_module

        _GIT_MODULE = git_module
        return git_module
    except ImportError:
        return None


@dataclass
class CommitInfo:
    sha: str
    short_sha: str
    message: str
    author: str
    authored_at: float

    @property
    def relative_time(self) -> str:
        return humanize_delta(authored_at=self.authored_at)


@dataclass
class GitInfo:
    is_repo: bool
    git_available: bool = True
    branch: Optional[str] = None
    commit_count: int = 0
    contributors: int = 0
    latest_commit: Optional[CommitInfo] = None
    recent_commits: list[CommitInfo] = field(default_factory=list)
    commits_by_weekday: dict[str, int] = field(default_factory=dict)  # Mon..Sun -> count
    is_dirty: bool = False
    remote_url: Optional[str] = None


def humanize_delta(authored_at: float) -> str:
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    delta = max(0, now - authored_at)
    if delta < 60:
        return "just now"
    if delta < 3600:
        m = int(delta // 60)
        return f"{m} minute{'s' if m != 1 else ''} ago"
    if delta < 86400:
        h = int(delta // 3600)
        return f"{h} hour{'s' if h != 1 else ''} ago"
    if delta < 86400 * 30:
        d = int(delta // 86400)
        return f"{d} day{'s' if d != 1 else ''} ago"
    if delta < 86400 * 365:
        mo = int(delta // (86400 * 30))
        return f"{mo} month{'s' if mo != 1 else ''} ago"
    y = int(delta // (86400 * 365))
    return f"{y} year{'s' if y != 1 else ''} ago"


def file_change_counts(root: str | Path, limit: int = 40) -> dict[str, int]:
    """Count how many of the last `limit` commits touched each file.

    Merge commits are skipped so a merge doesn't credit every file in the
    branch. Returns repo-relative paths; empty when git is unavailable.
    """
    git = _load_git()
    if git is None:
        return {}

    root = Path(root).expanduser().resolve()
    try:
        repo = git.Repo(root, search_parent_directories=False)
    except (git.InvalidGitRepositoryError, git.NoSuchPathError):
        return {}

    counts: dict[str, int] = {}
    try:
        for commit in repo.iter_commits(max_count=limit):
            if len(commit.parents) > 1:
                continue
            for path in commit.stats.files:
                key = str(path).replace("\\", "/")
                counts[key] = counts.get(key, 0) + 1
    except Exception:
        # Partial counts are still useful; a shallow clone or an unreadable
        # object shouldn't take the whole report down.
        return counts
    return counts


def read_git_info(root: str | Path, recent_limit: int = 5, activity_days: int = 7) -> GitInfo:
    root = Path(root).expanduser().resolve()
    git = _load_git()
    if git is None:
        return GitInfo(is_repo=False, git_available=False)

    InvalidGitRepositoryError = git.InvalidGitRepositoryError
    NoSuchPathError = git.NoSuchPathError
    GitCommandError = git.GitCommandError
    Repo = git.Repo

    try:
        repo = Repo(root, search_parent_directories=False)
    except (InvalidGitRepositoryError, NoSuchPathError):
        return GitInfo(is_repo=False)

    try:
        branch = repo.active_branch.name
    except (TypeError, ValueError):
        branch = "detached"

    try:
        remote_url = next(iter(repo.remotes)).url if repo.remotes else None
    except Exception:
        remote_url = None

    try:
        all_commits = list(repo.iter_commits(branch, max_count=2000))
    except (GitCommandError, ValueError):
        all_commits = []

    commit_count = len(all_commits)
    contributors = len({c.author.email or c.author.name for c in all_commits}) if all_commits else 0

    recent = [
        CommitInfo(
            sha=c.hexsha,
            short_sha=c.hexsha[:7],
            message=c.message.strip().splitlines()[0] if c.message.strip() else "(no message)",
            author=c.author.name,
            authored_at=c.authored_date,
        )
        for c in all_commits[:recent_limit]
    ]
    latest = recent[0] if recent else None

    # Bucket commits from the last `activity_days` days by weekday name.
    now = dt.datetime.now(dt.timezone.utc)
    window_start = (now - dt.timedelta(days=activity_days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    weekday_order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    by_weekday = {d: 0 for d in weekday_order}
    for c in all_commits:
        committed = dt.datetime.fromtimestamp(c.authored_date, tz=dt.timezone.utc)
        if committed >= window_start:
            by_weekday[weekday_order[committed.weekday()]] += 1

    try:
        is_dirty = repo.is_dirty(untracked_files=True)
    except Exception:
        is_dirty = False

    return GitInfo(
        is_repo=True,
        branch=branch,
        commit_count=commit_count,
        contributors=contributors,
        latest_commit=latest,
        recent_commits=recent,
        commits_by_weekday=by_weekday,
        is_dirty=is_dirty,
        remote_url=remote_url,
    )
