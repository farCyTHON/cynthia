"""Tests for k-NN similar-session matching."""
from __future__ import annotations

from dataclasses import dataclass

from cynthia.ml.knn_similar import (
    SessionFeatureSnapshot,
    find_similar_sessions,
    similarity_from_distance,
)


@dataclass
class FakeSession:
    id: int
    files_modified: int
    commits: int
    lines_added: int
    lines_deleted: int
    duration_minutes: float
    todo_changes: int


def test_similarity_from_distance_bounds() -> None:
    assert similarity_from_distance(0.0) == 100.0
    assert 0.0 < similarity_from_distance(1.0) < 100.0
    assert similarity_from_distance(99.0) < similarity_from_distance(1.0)


def test_find_similar_returns_top_k() -> None:
    query = SessionFeatureSnapshot(
        files_modified=20,
        commits=3,
        lines_added=200,
        lines_deleted=10,
        duration_minutes=45,
        todo_changes=1,
    )
    historical = [
        FakeSession(1, 19, 3, 190, 12, 44, 1),
        FakeSession(2, 2, 0, 5, 1, 12, 0),
        FakeSession(3, 18, 4, 180, 15, 50, 0),
        FakeSession(4, 5, 2, 25, 80, 30, 10),
        FakeSession(5, 21, 3, 210, 8, 46, 2),
    ]
    result = find_similar_sessions(query, historical, k=3)
    assert result.enough_data is True
    assert len(result.matches) == 3
    assert all(0.0 <= m.similarity_pct <= 100.0 for m in result.matches)
    # Nearest should be the feature-like sessions, not the quiet one.
    assert result.matches[0].session_id in {1, 3, 5}


def test_find_similar_excludes_query_id() -> None:
    historical = [
        FakeSession(10, 10, 1, 50, 5, 20, 2),
        FakeSession(11, 11, 1, 55, 6, 22, 2),
        FakeSession(12, 1, 0, 2, 0, 5, 0),
    ]
    result = find_similar_sessions(historical[0], historical, k=2, exclude_id=10)
    assert all(m.session_id != 10 for m in result.matches)


def test_find_similar_empty_history() -> None:
    query = SessionFeatureSnapshot(1, 0, 0, 0, 1.0, 0)
    result = find_similar_sessions(query, [], k=3)
    assert result.enough_data is False
    assert result.matches == []
