"""Shared session feature vectors for ML helpers (K-Means, k-NN, etc.)."""
from __future__ import annotations

from typing import Protocol, Sequence

FEATURE_NAMES: tuple[str, ...] = (
    "files_modified",
    "commits",
    "lines_added",
    "lines_deleted",
    "duration_minutes",
    "todo_changes",
)


class SessionLike(Protocol):
    """Minimal session shape required for feature extraction."""

    files_modified: int
    commits: int
    lines_added: int
    lines_deleted: int
    duration_minutes: float
    todo_changes: int


def feature_vector(session: SessionLike) -> list[float]:
    """Return the standard 6-D feature vector for a session-like object.

    Order matches ``FEATURE_NAMES`` and is shared by K-Means and k-NN.
    """
    return [
        float(session.files_modified),
        float(session.commits),
        float(session.lines_added),
        float(session.lines_deleted),
        float(session.duration_minutes),
        float(session.todo_changes),
    ]


def feature_matrix(sessions: Sequence[SessionLike]) -> list[list[float]]:
    """Build a feature matrix (one row per session)."""
    return [feature_vector(s) for s in sessions]
