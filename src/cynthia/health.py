"""Health Engine — turns raw scan + git data into one legible score.

Per the project brief, health considers build/test status, unresolved
TODOs, file churn, and dependency hygiene. This first version keeps the
formula transparent and local-only:

    100
    - TODO burden          (more unresolved TODOs -> lower, capped)
    - missing README        (-10)
    - missing tests dir      (-10)
    - stale git history      (-up to 15, scaled by days since last commit)

Test coverage is reported only when a real `coverage.xml` (Cobertura
format, produced by `coverage run` / `pytest --cov`) is found in the
project — CYNTHIA never fabricates a coverage number.

`compute_health` answers "how healthy is this?" as a HealthScore.
`build_health_report` is the wider diagnostic behind `cynthia doctor`:
it joins that score with repository, quality, activity, and churn-risk
facts, plus a rule-based summary sentence. No model, no network — every
sentence is derived from numbers gathered on this machine.
"""
from __future__ import annotations

import json
import sqlite3
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import config
from .git_observer import (
    GitInfo,
    file_change_counts,
    git_runtime_available,
    humanize_delta,
    read_git_info,
)
from .scanner import ScanResult, count_files_modified, scan_project
from .storage import Storage

STALE_AFTER_DAYS = 30
STALE_MAX_PENALTY = 15
TODO_MAX_PENALTY = 25

# `doctor` bands, deliberately stricter than the healthy/warning/critical
# split above: a project needs a near-clean bill of health to show green.
GREEN_MIN = 90
YELLOW_MIN = 70

WINDOW_DAYS = 7
MAX_RISK_FILES = 5
EVENT_SCAN_LIMIT = 5000
GIT_CHURN_COMMITS = 40
CHURN_NOTABLE = 4

# Filename keywords -> the topic named in the summary sentence. Ordered:
# the first matching topic wins, so specific concerns beat generic ones.
CHURN_TOPICS: list[tuple[tuple[str, ...], str]] = [
    (("auth", "login", "logout", "oauth", "token", "password", "credential"), "authentication"),
    (("security", "permission", "crypto"), "security"),
    (("migration", "schema", "model", "database", "storage", "sql", "repository"), "data-model"),
    (("api", "route", "endpoint", "controller", "handler", "server"), "API"),
    (("component", "view", "template", "widget", "layout", "style", "css", "html"), "UI"),
    (("test", "spec", "fixture"), "test"),
    (("config", "setting", "env"), "configuration"),
    (("cli", "command", "shell"), "CLI"),
    (("readme", "docs", "doc"), "documentation"),
]


class UnknownProject(LookupError):
    """Raised when a project id has no matching row in the workspace."""


@dataclass
class HealthScore:
    score: int
    status: str  # "healthy" | "warning" | "critical"
    test_coverage: Optional[float]  # None => no coverage report found
    reasons: list[str]

    @property
    def status_color(self) -> str:
        return {"healthy": "green", "warning": "yellow", "critical": "red"}[self.status]


@dataclass
class RepositoryFacts:
    git_available: bool
    is_repo: bool
    branch: Optional[str] = None
    commit_count: int = 0
    contributors: int = 0
    last_commit_age: Optional[str] = None
    last_commit_at: Optional[float] = None
    is_dirty: bool = False


@dataclass
class QualityFacts:
    todo_count: int = 0
    fixme_count: int = 0
    has_readme: bool = False
    has_tests: bool = False
    test_coverage: Optional[float] = None


@dataclass
class ActivityFacts:
    files_changed: int = 0
    commits: int = 0
    most_modified_file: Optional[str] = None
    source: str = "file timestamps"


@dataclass
class RiskFile:
    path: str
    changes: int


@dataclass
class HealthReport:
    """The complete `cynthia doctor` payload for one project."""

    project_name: str
    project_path: str
    project_kind: str
    last_scanned: float
    score: int
    band: str  # "green" | "yellow" | "red"
    status: str
    reasons: list[str]
    file_count: int
    size: str
    repository: RepositoryFacts
    quality: QualityFacts
    activity: ActivityFacts
    risks: list[RiskFile] = field(default_factory=list)
    risk_source: str = "no file-change history yet"
    summary: str = ""
    warnings: list[str] = field(default_factory=list)


def _status_for(score: int) -> str:
    if score >= 80:
        return "healthy"
    if score >= 50:
        return "warning"
    return "critical"


def score_band(score: int) -> str:
    """Map a 0-100 score onto the doctor's green / yellow / red band."""
    if score >= GREEN_MIN:
        return "green"
    if score >= YELLOW_MIN:
        return "yellow"
    return "red"


def _read_coverage_xml(root: Path) -> Optional[float]:
    for candidate in (root / "coverage.xml", root / "reports" / "coverage.xml"):
        if candidate.exists():
            try:
                tree = ET.parse(candidate)
                rate = tree.getroot().attrib.get("line-rate")
                if rate is not None:
                    return round(float(rate) * 100, 1)
            except (ET.ParseError, ValueError, OSError):
                continue
    return None


def compute_health(root: str | Path, scan: ScanResult, git_info: GitInfo) -> HealthScore:
    root = Path(root).expanduser().resolve()
    score = 100
    reasons: list[str] = []

    todo_penalty = min(TODO_MAX_PENALTY, len(scan.todos))
    if todo_penalty:
        score -= todo_penalty
        reasons.append(f"{len(scan.todos)} unresolved TODO/FIXME marker(s)")

    if not scan.has_readme:
        score -= 10
        reasons.append("no README found")

    if not scan.has_tests:
        score -= 10
        reasons.append("no tests directory found")

    if git_info.is_repo and git_info.latest_commit:
        import datetime as dt

        days_stale = (
            dt.datetime.now(dt.timezone.utc)
            - dt.datetime.fromtimestamp(git_info.latest_commit.authored_at, tz=dt.timezone.utc)
        ).days
        if days_stale > STALE_AFTER_DAYS:
            penalty = min(STALE_MAX_PENALTY, (days_stale - STALE_AFTER_DAYS) // 7 + 1)
            score -= penalty
            reasons.append(f"no commits in {days_stale} days")
    elif git_info.git_available and not git_info.is_repo:
        score -= 5
        reasons.append("not a git repository")

    score = max(0, min(100, score))
    coverage = _read_coverage_xml(root)

    return HealthScore(score=score, status=_status_for(score), test_coverage=coverage, reasons=reasons)


def build_health_report(project_id: int) -> HealthReport:
    """Assemble the full diagnostic for one registered project.

    Raises UnknownProject if the id isn't in the workspace. Everything
    else degrades into a warning on the report rather than an exception:
    a missing git repo, an empty directory, a project whose path was
    deleted, or an unreadable event log still produce a usable report.
    """
    settings = config.Settings.load()
    ignored = set(settings.ignored_dirs)
    now = time.time()
    window_start = now - WINDOW_DAYS * 86400
    warnings: list[str] = []

    with Storage() as db:
        project = db.get_project_by_id(project_id)
        if project is None:
            raise UnknownProject(f"No project with id {project_id} in this workspace.")
        try:
            event_rows = db.recent_events(project_id, since=window_start, limit=EVENT_SCAN_LIMIT)
        except sqlite3.DatabaseError as exc:
            event_rows = []
            warnings.append(f"event history unavailable ({exc})")

    root = Path(project.path).expanduser()
    if root.exists():
        scan = scan_project(root, ignored_dirs=ignored)
        git_info = read_git_info(root, recent_limit=5, activity_days=WINDOW_DAYS)
    else:
        warnings.append("project path no longer exists on disk")
        scan = ScanResult()
        git_info = GitInfo(is_repo=False, git_available=git_runtime_available())

    if not git_info.git_available:
        warnings.append("git is not installed — repository facts were skipped")
    if scan.file_count == 0 and root.exists():
        warnings.append("no files found to scan")

    health = compute_health(root, scan, git_info)

    repository = RepositoryFacts(
        git_available=git_info.git_available,
        is_repo=git_info.is_repo,
        branch=git_info.branch,
        commit_count=git_info.commit_count,
        contributors=git_info.contributors,
        last_commit_age=(
            humanize_delta(git_info.latest_commit.authored_at) if git_info.latest_commit else None
        ),
        last_commit_at=git_info.latest_commit.authored_at if git_info.latest_commit else None,
        is_dirty=git_info.is_dirty,
    )
    quality = QualityFacts(
        todo_count=sum(1 for t in scan.todos if t.tag == "TODO"),
        fixme_count=sum(1 for t in scan.todos if t.tag == "FIXME"),
        has_readme=scan.has_readme,
        has_tests=scan.has_tests,
        test_coverage=health.test_coverage,
    )

    event_churn = _churn_from_events(event_rows, root)
    if event_churn:
        churn, risk_source = event_churn, f"watcher events (last {WINDOW_DAYS} days)"
        files_changed, activity_source = len(event_churn), "watcher events"
    else:
        churn, risk_source = {}, "no file-change history yet"
        files_changed = (
            count_files_modified(root, window_start, now, ignored) if root.exists() else 0
        )
        activity_source = "file timestamps"
        if git_info.is_repo:
            churn = file_change_counts(root, limit=GIT_CHURN_COMMITS)
            if churn:
                risk_source = f"git history (last {GIT_CHURN_COMMITS} commits)"

    risks = [
        RiskFile(path=path, changes=count)
        for path, count in sorted(churn.items(), key=lambda kv: (-kv[1], kv[0]))[:MAX_RISK_FILES]
    ]
    activity = ActivityFacts(
        files_changed=files_changed,
        commits=sum(git_info.commits_by_weekday.values()),
        most_modified_file=risks[0].path if risks else None,
        source=activity_source,
    )

    return HealthReport(
        project_name=project.name,
        project_path=project.path,
        project_kind=project.kind,
        last_scanned=now,
        score=health.score,
        band=score_band(health.score),
        status=health.status,
        reasons=health.reasons,
        file_count=scan.file_count,
        size=scan.human_size,
        repository=repository,
        quality=quality,
        activity=activity,
        risks=risks,
        risk_source=risk_source,
        summary=summarize(
            band=score_band(health.score),
            file_count=scan.file_count,
            quality=quality,
            repository=repository,
            activity=activity,
            risks=risks,
        ),
        warnings=warnings,
    )


def churn_topic(path: str) -> Optional[str]:
    """Name the concern a hot file belongs to, e.g. 'authentication'."""
    lowered = path.lower()
    for keywords, topic in CHURN_TOPICS:
        if any(word in lowered for word in keywords):
            return topic
    return None


def summarize(
    *,
    band: str,
    file_count: int,
    quality: QualityFacts,
    repository: RepositoryFacts,
    activity: ActivityFacts,
    risks: list[RiskFile],
) -> str:
    """Write the human-readable verdict from the numbers alone (no LLM)."""
    if file_count == 0:
        return "Project directory looks empty — there is nothing to analyze yet."

    sentences: list[str] = []
    is_active = activity.commits > 0 or activity.files_changed > 0

    if band == "green":
        sentences.append(
            "Project is healthy and actively maintained."
            if is_active
            else f"Project is healthy but has been quiet for {WINDOW_DAYS} days."
        )
    elif band == "yellow":
        if not quality.has_tests:
            sentences.append("Project is stable but has missing tests.")
        elif not quality.has_readme:
            sentences.append("Project is stable but has no README.")
        else:
            sentences.append("Project is stable with a few issues worth cleaning up.")
    else:
        gaps = [
            label
            for present, label in ((quality.has_tests, "tests"), (quality.has_readme, "a README"))
            if not present
        ]
        sentences.append(
            f"Project needs attention: it is missing {_join(gaps)}."
            if gaps
            else "Project needs attention — several health checks are failing."
        )

    hottest = risks[0] if risks else None
    if hottest and hottest.changes >= CHURN_NOTABLE:
        topic = churn_topic(hottest.path)
        sentences.append(
            f"Project shows high churn in {topic}-related files."
            if topic
            else f"Most file churn is concentrated in {hottest.path}."
        )

    if not repository.git_available:
        sentences.append("Git is not installed, so history-based signals were skipped.")
    elif not repository.is_repo:
        sentences.append("This directory is not a git repository, so commit history is unavailable.")
    elif repository.commit_count and not activity.commits:
        sentences.append(f"No commits landed in the last {WINDOW_DAYS} days.")

    return " ".join(sentences)


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return items[0] if items else ""
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _churn_from_events(rows, root: Path) -> dict[str, int]:
    """Count file events per path from the local event log."""
    counts: dict[str, int] = {}
    for row in rows:
        if not str(row["event_type"]).startswith("file_"):
            continue
        try:
            payload = json.loads(row["payload"] or "{}")
        except (TypeError, ValueError):
            continue
        raw = payload.get("path") if isinstance(payload, dict) else None
        if not raw:
            continue
        key = _relative_to(str(raw), root)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _relative_to(path_str: str, root: Path) -> str:
    candidate = Path(path_str)
    try:
        return candidate.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return candidate.name
