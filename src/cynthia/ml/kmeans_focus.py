"""K-Means clustering of focus sessions into work-mode labels.

Uses scikit-learn StandardScaler + KMeans on real session metrics
(files_modified, commits, lines_added, lines_deleted, duration_minutes,
todo_changes). Cluster ids are mapped to human labels via centroid heuristics.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from .features import FEATURE_NAMES, SessionLike, feature_matrix

WORK_MODES = (
    "Feature Development",
    "Bug Fixing",
    "Refactoring",
    "Documentation",
)

N_CLUSTERS = 4
MIN_SESSIONS = 8

__all__ = [
    "FEATURE_NAMES",
    "WORK_MODES",
    "ClusterResult",
    "SessionLike",
    "cluster_recent_sessions",
    "percentages_sum_to_100",
]


@dataclass
class ClusterResult:
    """Outcome of clustering a batch of sessions into work modes."""

    enough_data: bool
    session_count: int
    labels_by_session_id: dict[int, str]
    percentages: dict[str, int]
    message: Optional[str] = None


def cluster_recent_sessions(sessions: Sequence[SessionLike]) -> ClusterResult:
    """Cluster sessions into four work modes; percentages sum to 100 when enough data.

    Args:
        sessions: Historical sessions exposing the shared feature fields and an ``id``.

    Returns:
        ``ClusterResult`` with per-session labels and percentage breakdown, or a
        guard message when fewer than ``MIN_SESSIONS`` rows are available.
    """
    n = len(sessions)
    if n < MIN_SESSIONS:
        return ClusterResult(
            enough_data=False,
            session_count=n,
            labels_by_session_id={},
            percentages={mode: 0 for mode in WORK_MODES},
            message=(
                f"Not enough sessions yet to analyze focus patterns "
                f"(need {MIN_SESSIONS}+, have {n})."
            ),
        )

    labels = _fit_and_label(sessions)
    mapping = {int(getattr(session, "id")): labels[i] for i, session in enumerate(sessions)}
    counts = {mode: 0 for mode in WORK_MODES}
    for label in mapping.values():
        counts[label] = counts.get(label, 0) + 1
    percentages = percentages_sum_to_100(counts)
    return ClusterResult(
        enough_data=True,
        session_count=n,
        labels_by_session_id=mapping,
        percentages=percentages,
    )


def _fit_and_label(sessions: Sequence[SessionLike]) -> list[str]:
    """Run K-Means and map cluster ids to work-mode labels via centroid heuristics.

    Fast follow-up: a 7th feature ``doc_file_ratio`` would make Documentation
    separable on its own axis instead of by elimination.
    """
    import numpy as np
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler

    matrix = np.array(feature_matrix(sessions), dtype=float)
    # Column order: files, commits, lines_added, lines_deleted, duration, todos
    scaled = StandardScaler().fit_transform(matrix)
    model = KMeans(n_clusters=N_CLUSTERS, n_init=10, random_state=42)
    cluster_ids = model.fit_predict(scaled)

    centroids = []
    for cid in range(N_CLUSTERS):
        mask = cluster_ids == cid
        centroids.append(matrix[mask].mean(axis=0) if mask.any() else np.zeros(6))

    assigned: dict[int, str] = {}
    remaining = set(range(N_CLUSTERS))

    # Feature Development: highest lines_added + files_modified
    feature_scores = {
        cid: centroids[cid][2] + centroids[cid][0] for cid in remaining
    }
    feature_cid = max(feature_scores, key=feature_scores.get)
    assigned[feature_cid] = "Feature Development"
    remaining.remove(feature_cid)

    # Refactoring: highest lines_deleted / max(lines_added, 1)
    refactor_scores = {
        cid: centroids[cid][3] / max(centroids[cid][2], 1.0) for cid in remaining
    }
    refactor_cid = max(refactor_scores, key=refactor_scores.get)
    assigned[refactor_cid] = "Refactoring"
    remaining.remove(refactor_cid)

    # Bug Fixing: highest todo_changes
    bug_scores = {cid: centroids[cid][5] for cid in remaining}
    bug_cid = max(bug_scores, key=bug_scores.get)
    assigned[bug_cid] = "Bug Fixing"
    remaining.remove(bug_cid)

    # Documentation: remaining cluster
    doc_cid = remaining.pop()
    assigned[doc_cid] = "Documentation"

    return [assigned[int(cid)] for cid in cluster_ids]


def percentages_sum_to_100(counts: dict[str, int]) -> dict[str, int]:
    """Largest-remainder rounding so percentages always sum to 100."""
    total = sum(counts.values())
    if total == 0:
        return {mode: 0 for mode in WORK_MODES}

    raw = {mode: (counts.get(mode, 0) / total) * 100 for mode in WORK_MODES}
    floored = {mode: int(v) for mode, v in raw.items()}
    remainder = 100 - sum(floored.values())
    order = sorted(
        WORK_MODES,
        key=lambda m: (raw[m] - floored[m], counts.get(m, 0)),
        reverse=True,
    )
    for mode in order[:remainder]:
        floored[mode] += 1
    return floored
