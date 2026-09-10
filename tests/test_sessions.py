"""Tests for focus sessions, metric diffing, and K-Means analysis."""
from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from cynthia import sessions as sessions_mod
from cynthia.config import Settings
from cynthia.git_observer import GitInfo
from cynthia.scanner import ScanResult, TodoItem
from cynthia.storage import Session, Storage
from cynthia.workspace import init_workspace, add_project


@pytest.fixture
def workspace_home(tmp_path, monkeypatch):
    home = tmp_path / "cynthia-home"
    monkeypatch.setenv("CYNTHIA_HOME", str(home))
    init_workspace("test")
    return home


@pytest.fixture
def sample_project(workspace_home, tmp_path):
    project_dir = tmp_path / "demo-app"
    project_dir.mkdir()
    (project_dir / "README.md").write_text("# Demo\n")
    (project_dir / "main.py").write_text("print('hi')\n")
    return add_project(project_dir)


def test_metric_diffing_math(workspace_home, sample_project, monkeypatch):
    start_scan = ScanResult(todos=[TodoItem("a.py", 1, "TODO", "fix")])
    stop_scan = ScanResult(
        todos=[
            TodoItem("a.py", 1, "TODO", "fix"),
            TodoItem("b.py", 2, "FIXME", "bug"),
            TodoItem("c.py", 3, "TODO", "more"),
        ]
    )
    start_git = GitInfo(is_repo=True, commit_count=10)
    stop_git = GitInfo(is_repo=True, commit_count=13)

    monkeypatch.setattr(sessions_mod, "scan_project", lambda *a, **k: start_scan)
    monkeypatch.setattr(sessions_mod, "read_git_info", lambda *a, **k: start_git)
    sessions_mod.start_focus(sample_project)

    # Force started_at far enough in the past so duration >= 1 minute.
    with Storage() as db:
        snap = db.get_meta("focus_snapshot")
        snap["started_at"] = time.time() - 120
        db.set_meta("focus_snapshot", snap)

    monkeypatch.setattr(sessions_mod, "scan_project", lambda *a, **k: stop_scan)
    monkeypatch.setattr(sessions_mod, "read_git_info", lambda *a, **k: stop_git)
    monkeypatch.setattr(sessions_mod, "count_commits_in_window", lambda *a, **k: 0)
    monkeypatch.setattr(sessions_mod, "read_line_stats", lambda *a, **k: (40, 12))
    monkeypatch.setattr(sessions_mod, "read_uncommitted_line_stats", lambda *a, **k: (0, 0))
    monkeypatch.setattr(sessions_mod, "count_files_modified", lambda *a, **k: 5)

    session = sessions_mod.stop_focus()

    assert session.commits == 3
    assert session.lines_added == 40
    assert session.lines_deleted == 12
    assert session.files_modified == 5
    assert session.todo_changes == 2
    assert session.duration_minutes >= 1.0


def test_finalize_uses_explicit_files_modified(workspace_home, sample_project, monkeypatch):
    monkeypatch.setattr(sessions_mod, "scan_project", lambda *a, **k: ScanResult())
    monkeypatch.setattr(
        sessions_mod,
        "read_git_info",
        lambda *a, **k: GitInfo(is_repo=False, git_available=False),
    )
    monkeypatch.setattr(sessions_mod, "count_commits_in_window", lambda *a, **k: 0)
    monkeypatch.setattr(sessions_mod, "read_line_stats", lambda *a, **k: (0, 0))
    monkeypatch.setattr(sessions_mod, "read_uncommitted_line_stats", lambda *a, **k: (0, 0))

    # If override works, mtime walk must not be consulted.
    def _boom(*a, **k):
        raise AssertionError("mtime walk should not run when files_modified is provided")

    monkeypatch.setattr(sessions_mod, "count_files_modified", _boom)

    sessions_mod.begin_session(sample_project)
    with Storage() as db:
        snap = db.get_meta("focus_snapshot")
        snap["started_at"] = time.time() - 120
        db.set_meta("focus_snapshot", snap)

    session = sessions_mod.finalize_session(files_modified=7)
    assert session.files_modified == 7


def test_begin_replace_clears_previous_snapshot(workspace_home, sample_project, tmp_path, monkeypatch):
    monkeypatch.setattr(sessions_mod, "scan_project", lambda *a, **k: ScanResult())
    monkeypatch.setattr(
        sessions_mod,
        "read_git_info",
        lambda *a, **k: GitInfo(is_repo=False, git_available=False),
    )

    other_dir = tmp_path / "other-app"
    other_dir.mkdir()
    (other_dir / "README.md").write_text("# Other\n")
    other = add_project(other_dir)

    sessions_mod.begin_session(sample_project)
    assert sessions_mod.active_session_project_name() == sample_project.name

    sessions_mod.begin_session(other, replace_active=True)
    assert sessions_mod.active_session_project_name() == other.name


def test_sync_event_collector_unique_paths():
    from cynthia.events import Event, SyncEventCollector

    bus = SyncEventCollector()
    bus.publish_threadsafe(Event("file_modified", "p", {"path": "/a.py"}))
    bus.publish_threadsafe(Event("file_modified", "p", {"path": "/a.py"}))
    bus.publish_threadsafe(Event("file_created", "p", {"path": "/b.py"}))
    assert bus.count == 3
    assert bus.unique_paths() == {"/a.py", "/b.py"}
    bus.clear()
    assert bus.count == 0


def test_too_short_session_discarded(workspace_home, sample_project, monkeypatch):
    monkeypatch.setattr(
        sessions_mod,
        "scan_project",
        lambda *a, **k: ScanResult(),
    )
    monkeypatch.setattr(
        sessions_mod,
        "read_git_info",
        lambda *a, **k: GitInfo(is_repo=False, git_available=False),
    )

    sessions_mod.start_focus(sample_project)
    with pytest.raises(sessions_mod.SessionTooShort, match="too short"):
        sessions_mod.stop_focus()

    with Storage() as db:
        assert db.count_sessions() == 0
        assert db.get_meta("focus_snapshot") is None


def test_analyze_guard_too_few_sessions(workspace_home, sample_project):
    result = sessions_mod.analyze_sessions(project_name=sample_project.name)
    assert result.enough_data is False
    assert result.session_count == 0
    assert "need 8+" in (result.message or "")
    assert sum(result.percentages.values()) == 0


def test_clustering_returns_four_labels_summing_to_100(workspace_home, sample_project):
    # Eight synthetic sessions with separable modes.
    profiles = [
        # Feature Development-ish
        dict(duration_minutes=45, files_modified=20, commits=3, lines_added=200, lines_deleted=10, todo_changes=1),
        dict(duration_minutes=50, files_modified=18, commits=4, lines_added=180, lines_deleted=15, todo_changes=0),
        # Bug Fixing-ish
        dict(duration_minutes=25, files_modified=4, commits=1, lines_added=20, lines_deleted=5, todo_changes=12),
        dict(duration_minutes=30, files_modified=5, commits=2, lines_added=25, lines_deleted=8, todo_changes=15),
        # Refactoring-ish
        dict(duration_minutes=40, files_modified=10, commits=2, lines_added=30, lines_deleted=90, todo_changes=2),
        dict(duration_minutes=35, files_modified=12, commits=1, lines_added=20, lines_deleted=100, todo_changes=1),
        # Documentation-ish
        dict(duration_minutes=15, files_modified=2, commits=0, lines_added=5, lines_deleted=1, todo_changes=0),
        dict(duration_minutes=12, files_modified=1, commits=0, lines_added=3, lines_deleted=0, todo_changes=0),
    ]
    now = time.time()
    with Storage() as db:
        for i, p in enumerate(profiles):
            db.add_session(
                project_id=sample_project.id,
                started_at=now - (i + 2) * 3600,
                ended_at=now - (i + 1) * 3600,
                **p,
            )

    result = sessions_mod.analyze_sessions(project_name=sample_project.name)
    assert result.enough_data is True
    assert result.session_count == 8
    assert set(result.percentages.keys()) == set(sessions_mod.WORK_MODES)
    assert sum(result.percentages.values()) == 100
    assert all(pct >= 0 for pct in result.percentages.values())

    with Storage() as db:
        labeled = db.list_sessions(sample_project.id)
    assert all(s.cluster_label in sessions_mod.WORK_MODES for s in labeled)


def test_percentages_sum_to_100_helper():
    from cynthia.ml.kmeans_focus import percentages_sum_to_100

    counts = {
        "Feature Development": 3,
        "Bug Fixing": 2,
        "Refactoring": 2,
        "Documentation": 1,
    }
    pct = percentages_sum_to_100(counts)
    assert sum(pct.values()) == 100


def test_files_modified_counts_mtime_window(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x\n")
    now = time.time()
    os.utime(f, (now - 10, now - 10))
    older = tmp_path / "old.py"
    older.write_text("y\n")
    os.utime(older, (now - 10_000, now - 10_000))

    count = sessions_mod.count_files_modified(tmp_path, now - 60, now)
    assert count == 1
