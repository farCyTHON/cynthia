"""Tests for the `cynthia overview` multi-project dashboard."""
from __future__ import annotations

import time
from typing import Optional
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from cynthia.cli import app
from cynthia.git_observer import CommitInfo, GitInfo
from cynthia.health import HealthScore, score_band
from cynthia.overview import (
    ACTIVITY_HIGH,
    ACTIVITY_MEDIUM,
    activity_level,
    band_color_name,
    build_workspace_overview,
)
from cynthia.scanner import ScanResult
from cynthia.timeline import ActivitySeries
from cynthia.ui import theme
from cynthia.ui.overview import health_badge
from cynthia.workspace import ProjectSnapshot, add_project, init_workspace

runner = CliRunner()


@pytest.fixture
def workspace_home(tmp_path, monkeypatch):
    home = tmp_path / "cynthia-home"
    monkeypatch.setenv("CYNTHIA_HOME", str(home))
    init_workspace("test")
    return home


def _make_project(tmp_path, name: str):
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text(f"# {name}\n")
    (root / "main.py").write_text("print('ok')\n")
    return add_project(root, name=name)


def _snap(project, score: int, branch: str = "main", commit_at: Optional[float] = None):
    authored = commit_at if commit_at is not None else time.time() - 3600
    latest = CommitInfo(
        sha="a" * 40,
        short_sha="aaaaaaa",
        message="wip",
        author="tester",
        authored_at=authored,
    )
    git = GitInfo(
        is_repo=True,
        branch=branch,
        commit_count=5,
        contributors=1,
        latest_commit=latest,
        commits_by_weekday={"Mon": 1, "Tue": 0, "Wed": 0, "Thu": 0, "Fri": 0, "Sat": 0, "Sun": 0},
    )
    health = HealthScore(score=score, status="healthy", test_coverage=None, reasons=[])
    return ProjectSnapshot(project=project, scan=ScanResult(file_count=2), git=git, health=health)


def _series(total: int) -> ActivitySeries:
    # Put everything on Monday so total matches.
    counts = {d: 0 for d in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")}
    counts["Mon"] = total
    return ActivitySeries(counts=counts, total=total, from_watcher_events=False)


def test_empty_workspace(workspace_home):
    data = build_workspace_overview()
    assert data.is_empty
    assert data.total_projects == 0
    assert data.rows == []
    assert data.most_active is None

    result = runner.invoke(app, ["overview"])
    assert result.exit_code == 0, result.output
    assert "No projects registered yet" in result.output


def test_multiple_projects(workspace_home, tmp_path):
    alpha = _make_project(tmp_path, "alpha")
    beta = _make_project(tmp_path, "beta")

    snaps = {
        alpha.name: _snap(alpha, score=95, branch="main", commit_at=time.time() - 120),
        beta.name: _snap(beta, score=72, branch="dev", commit_at=time.time() - 7200),
    }
    series = {
        alpha.id: _series(ACTIVITY_HIGH + 2),
        beta.id: _series(ACTIVITY_MEDIUM),
    }

    def fake_snapshot(project):
        return snaps[project.name]

    def fake_series(storage, project_id, git_info, days=7):
        return series[project_id]

    with patch("cynthia.overview.workspace.snapshot", side_effect=fake_snapshot), patch(
        "cynthia.overview.build_activity_series", side_effect=fake_series
    ):
        data = build_workspace_overview()

    assert data.total_projects == 2
    assert data.healthy_projects == 1
    assert data.warning_projects == 1
    assert {r.name for r in data.rows} == {"alpha", "beta"}
    assert data.most_active == "alpha"

    by_name = {r.name: r for r in data.rows}
    assert by_name["alpha"].health_score == 95
    assert by_name["alpha"].activity_level == "High"
    assert by_name["alpha"].branch == "main"
    assert by_name["beta"].health_score == 72
    assert by_name["beta"].activity_level == "Medium"
    assert by_name["beta"].branch == "dev"


def test_sorting_by_activity(workspace_home, tmp_path):
    older = _make_project(tmp_path, "older")
    newer = _make_project(tmp_path, "newer")
    now = time.time()

    snaps = {
        older.name: _snap(older, score=80, commit_at=now - 86_400),
        newer.name: _snap(newer, score=80, commit_at=now - 60),
    }

    def fake_snapshot(project):
        return snaps[project.name]

    def fake_series(storage, project_id, git_info, days=7):
        return _series(5)

    with patch("cynthia.overview.workspace.snapshot", side_effect=fake_snapshot), patch(
        "cynthia.overview.build_activity_series", side_effect=fake_series
    ):
        data = build_workspace_overview()

    names = [r.name for r in data.rows]
    assert names[0] == "newer"
    assert names[1] == "older"
    assert data.rows[0].last_change_at > data.rows[1].last_change_at


def test_health_color_thresholds():
    assert score_band(100) == "green"
    assert score_band(90) == "green"
    assert score_band(89) == "yellow"
    assert score_band(70) == "yellow"
    assert score_band(69) == "red"
    assert score_band(0) == "red"

    assert band_color_name("green") == "green"
    assert band_color_name("yellow") == "yellow"
    assert band_color_name("red") == "red"

    green = health_badge(91, "green")
    yellow = health_badge(88, "yellow")
    red = health_badge(40, "red")
    assert green.plain == "91%"
    assert yellow.plain == "88%"
    assert red.plain == "40%"
    assert theme.SUCCESS in green.style
    assert theme.WARNING in yellow.style
    assert theme.CRITICAL in red.style


def test_activity_level_thresholds():
    assert activity_level(ACTIVITY_HIGH) == "High"
    assert activity_level(ACTIVITY_HIGH - 1) == "Medium"
    assert activity_level(ACTIVITY_MEDIUM) == "Medium"
    assert activity_level(ACTIVITY_MEDIUM - 1) == "Low"
    assert activity_level(0) == "Low"


def test_overview_command_renders_table(workspace_home, tmp_path):
    project = _make_project(tmp_path, "demo")
    snap = _snap(project, score=91, branch="main", commit_at=time.time() - 30)

    with patch("cynthia.overview.workspace.snapshot", return_value=snap), patch(
        "cynthia.overview.build_activity_series", return_value=_series(12)
    ):
        result = runner.invoke(app, ["overview"])

    assert result.exit_code == 0, result.output
    assert "Workspace Overview" in result.output
    assert "demo" in result.output
    assert "91%" in result.output
    assert "High" in result.output
    assert "main" in result.output
