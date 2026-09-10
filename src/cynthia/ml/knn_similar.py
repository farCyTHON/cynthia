"""k-NN similarity over historical focus sessions.

Uses ``sklearn.neighbors.NearestNeighbors`` with Euclidean distance on the
same standardized feature vector as K-Means focus analysis.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from .features import SessionLike, feature_matrix, feature_vector

DEFAULT_K = 3


@dataclass(frozen=True)
class SimilarSessionMatch:
    """One historical session ranked by similarity to the query."""

    session_id: int
    similarity_pct: float
    duration_minutes: float
    files_modified: int
    commits: int
    distance: float


@dataclass
class SimilarSessionsResult:
    """Result of a k-NN lookup against historical sessions."""

    enough_data: bool
    query_source: str
    matches: list[SimilarSessionMatch]
    message: Optional[str] = None


@dataclass
class SessionFeatureSnapshot:
    """In-memory feature row used as a k-NN query (active or synthetic)."""

    files_modified: int
    commits: int
    lines_added: int
    lines_deleted: int
    duration_minutes: float
    todo_changes: int
    id: int = -1


def similarity_from_distance(distance: float) -> float:
    """Map Euclidean distance to a 0–100 inverse-distance similarity score.

    ``100 / (1 + d)`` yields 100 at distance 0 and approaches 0 as distance grows.
    """
    return round(100.0 / (1.0 + max(0.0, float(distance))), 1)


def find_similar_sessions(
    query: SessionLike,
    historical: Sequence[SessionLike],
    *,
    k: int = DEFAULT_K,
    exclude_id: Optional[int] = None,
) -> SimilarSessionsResult:
    """Find the ``k`` historical sessions most similar to ``query``.

    Args:
        query: Session-like object providing the query feature vector.
        historical: Completed sessions to search (same project or broader).
        k: Number of neighbors to return (default 3).
        exclude_id: Optional session id to skip (e.g. when the query is itself
            a stored session).

    Returns:
        ``SimilarSessionsResult`` with ranked matches or a guard message.
    """
    candidates: list[SessionLike] = []
    for session in historical:
        sid = getattr(session, "id", None)
        if exclude_id is not None and sid == exclude_id:
            continue
        candidates.append(session)

    if not candidates:
        return SimilarSessionsResult(
            enough_data=False,
            query_source="query",
            matches=[],
            message="No historical sessions available to compare against.",
        )

    import numpy as np
    from sklearn.neighbors import NearestNeighbors
    from sklearn.preprocessing import StandardScaler

    n_neighbors = min(k, len(candidates))
    matrix = np.array(feature_matrix(candidates), dtype=float)
    scaler = StandardScaler()
    scaled = scaler.fit_transform(matrix)
    query_scaled = scaler.transform(np.array([feature_vector(query)], dtype=float))

    model = NearestNeighbors(n_neighbors=n_neighbors, metric="euclidean")
    model.fit(scaled)
    distances, indices = model.kneighbors(query_scaled)

    matches: list[SimilarSessionMatch] = []
    for dist, idx in zip(distances[0], indices[0], strict=True):
        session = candidates[int(idx)]
        matches.append(
            SimilarSessionMatch(
                session_id=int(getattr(session, "id")),
                similarity_pct=similarity_from_distance(float(dist)),
                duration_minutes=float(session.duration_minutes),
                files_modified=int(session.files_modified),
                commits=int(session.commits),
                distance=float(dist),
            )
        )

    return SimilarSessionsResult(
        enough_data=True,
        query_source="query",
        matches=matches,
    )
