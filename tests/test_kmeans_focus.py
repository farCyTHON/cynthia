"""Tests for ml.kmeans_focus clustering."""
from __future__ import annotations

from dataclasses import dataclass

from cynthia.ml.kmeans_focus import WORK_MODES, cluster_recent_sessions


@dataclass
class FakeSession:
    id: int
    files_modified: int
    commits: int
    lines_added: int
    lines_deleted: int
    duration_minutes: float
    todo_changes: int


def test_cluster_guard_too_few():
    result = cluster_recent_sessions([])
    assert result.enough_data is False
    assert "need 8+" in (result.message or "")


def test_cluster_four_labels_sum_100():
    profiles = [
        FakeSession(1, 20, 3, 200, 10, 45, 1),
        FakeSession(2, 18, 4, 180, 15, 50, 0),
        FakeSession(3, 4, 1, 20, 5, 25, 12),
        FakeSession(4, 5, 2, 25, 8, 30, 15),
        FakeSession(5, 10, 2, 30, 90, 40, 2),
        FakeSession(6, 12, 1, 20, 100, 35, 1),
        FakeSession(7, 2, 0, 5, 1, 15, 0),
        FakeSession(8, 1, 0, 3, 0, 12, 0),
    ]
    result = cluster_recent_sessions(profiles)
    assert result.enough_data is True
    assert set(result.percentages.keys()) == set(WORK_MODES)
    assert sum(result.percentages.values()) == 100
    assert len(result.labels_by_session_id) == 8
    assert all(label in WORK_MODES for label in result.labels_by_session_id.values())
