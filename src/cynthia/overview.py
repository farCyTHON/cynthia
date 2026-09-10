"""Workspace overview — multi-project dashboard data for `cynthia overview`.

Reuses `workspace.snapshot` (scan + git + health), `timeline.build_activity_series`
(7-day activity), and `health.score_band` (green / yellow / red). No health
or activity math is reimplemented here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import config, workspace
from .git_observer import humanize_delta
from .health import score_band
from .storage import Storage
from .timeline import build_activity_series

# Absolute 7-day activity totals → High / Medium / Low labels.
ACTIVITY_HIGH = 10
ACTIVITY_MEDIUM = 3


@dataclass
class ProjectOverviewRow:
    name: str
    health_score: int
    band: str  # "green" | "yellow" | "red"
    activity_level: str  # "High" | "Medium" | "Low"
    activity_total: int
    last_change_at: Optional[float]
    last_change: str
    branch: str


@dataclass
class WorkspaceOverview:
    rows: list[ProjectOverviewRow] = field(default_factory=list)
    total_projects: int = 0
    healthy_projects: int = 0
    warning_projects: int = 0
    most_active: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        return self.total_projects == 0


def activity_level(total: int) -> str:
    """Map a 7-day activity total onto High / Medium / Low."""
    if total >= ACTIVITY_HIGH:
        return "High"
    if total >= ACTIVITY_MEDIUM:
        return "Medium"
    return "Low"


def band_color_name(band: str) -> str:
    """Stable color name for tests and badges (green / yellow / red)."""
    return band if band in ("green", "yellow", "red") else "red"


def build_workspace_overview() -> WorkspaceOverview:
    """Load every registered project and assemble the overview payload."""
    projects = workspace.list_projects()
    if not projects:
        return WorkspaceOverview()

    settings = config.Settings.load()
    days = settings.activity_window_days
    rows: list[ProjectOverviewRow] = []

    with Storage() as db:
        for project in projects:
            snap = workspace.snapshot(project)
            series = build_activity_series(db, project.id, snap.git, days=days)
            band = score_band(snap.health.score)

            last_at = _last_change_at(db, project.id, snap.git.latest_commit)
            if last_at is None and project.last_opened is not None:
                last_at = project.last_opened

            if snap.git.is_repo and snap.git.branch:
                branch = snap.git.branch
            elif not snap.git.git_available:
                branch = "—"
            else:
                branch = "—"

            rows.append(
                ProjectOverviewRow(
                    name=project.name,
                    health_score=snap.health.score,
                    band=band,
                    activity_level=activity_level(series.total),
                    activity_total=series.total,
                    last_change_at=last_at,
                    last_change=humanize_delta(last_at) if last_at else "never",
                    branch=branch,
                )
            )

    # Most recently active first; tie-break by higher 7-day activity, then name.
    rows.sort(
        key=lambda r: (
            r.last_change_at is not None,
            r.last_change_at or 0.0,
            r.activity_total,
            r.name.lower(),
        ),
        reverse=True,
    )

    healthy = sum(1 for r in rows if r.band == "green")
    # "Warning" covers amber + red so the summary matches the example labels.
    warning = sum(1 for r in rows if r.band != "green")
    most_active = max(rows, key=lambda r: (r.activity_total, r.last_change_at or 0.0)).name

    return WorkspaceOverview(
        rows=rows,
        total_projects=len(rows),
        healthy_projects=healthy,
        warning_projects=warning,
        most_active=most_active,
    )


def _last_change_at(db: Storage, project_id: int, latest_commit) -> Optional[float]:
    """Latest signal: watcher event or git commit author date."""
    candidates: list[float] = []
    if latest_commit is not None:
        candidates.append(float(latest_commit.authored_at))
    event_at = db.latest_event_at(project_id, file_events_only=True)
    if event_at is not None:
        candidates.append(event_at)
    return max(candidates) if candidates else None
