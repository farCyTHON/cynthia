"""Storage Layer — the single SQLite database backing a CYNTHIA workspace.

Tables:
  - meta: small key/value store (schema version, active project, focus snapshot, ...)
  - projects: every project registered with `cynthia add`
  - events: the append-only log the Event Bus writes to (file changes,
    commits observed, etc.) that the Timeline Engine reads back from.
  - sessions: focus sessions recorded via `cynthia focus start/stop`

Kept deliberately dependency-free (stdlib sqlite3 only) since this is the
one module everything else in CYNTHIA depends on.
"""
from __future__ import annotations

import contextlib
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Optional

from . import config

FOCUS_SNAPSHOT_KEY = "focus_snapshot"

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,
    path        TEXT UNIQUE NOT NULL,
    kind        TEXT DEFAULT 'unknown',
    created_at  REAL NOT NULL,
    last_opened REAL
);

CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    payload    TEXT,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_project ON events(project_id, created_at);

CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    started_at      REAL NOT NULL,
    ended_at        REAL NOT NULL,
    duration_minutes REAL NOT NULL,
    files_modified  INTEGER NOT NULL,
    commits         INTEGER NOT NULL,
    lines_added     INTEGER NOT NULL,
    lines_deleted   INTEGER NOT NULL,
    todo_changes    INTEGER NOT NULL,
    cluster_label   TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id, started_at);
"""


@dataclass
class Project:
    id: int
    name: str
    path: str
    kind: str
    created_at: float
    last_opened: Optional[float] = None


@dataclass
class Session:
    id: int
    project_id: int
    started_at: float
    ended_at: float
    duration_minutes: float
    files_modified: int
    commits: int
    lines_added: int
    lines_deleted: int
    todo_changes: int
    cluster_label: Optional[str] = None
    project_name: Optional[str] = None


class Storage:
    """Thin, explicit wrapper around the workspace SQLite file."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or config.db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- meta ---------------------------------------------------------
    def get_meta(self, key: str, default: Any = None) -> Any:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)
        ).fetchone()
        return json.loads(row["value"]) if row else default

    def set_meta(self, key: str, value: Any) -> None:
        self._conn.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )
        self._conn.commit()

    def delete_meta(self, key: str) -> None:
        self._conn.execute("DELETE FROM meta WHERE key = ?", (key,))
        self._conn.commit()

    # -- projects -------------------------------------------------------
    def add_project(self, name: str, path: str, kind: str = "unknown") -> Project:
        now = time.time()
        cur = self._conn.execute(
            "INSERT INTO projects(name, path, kind, created_at) VALUES (?, ?, ?, ?)",
            (name, path, kind, now),
        )
        self._conn.commit()
        return Project(id=cur.lastrowid, name=name, path=path, kind=kind, created_at=now)

    def remove_project(self, name: str) -> bool:
        cur = self._conn.execute("DELETE FROM projects WHERE name = ?", (name,))
        self._conn.commit()
        return cur.rowcount > 0

    def list_projects(self) -> list[Project]:
        rows = self._conn.execute(
            "SELECT * FROM projects ORDER BY last_opened DESC NULLS LAST, created_at DESC"
        ).fetchall()
        return [Project(**dict(r)) for r in rows]

    def get_project(self, name: str) -> Optional[Project]:
        row = self._conn.execute(
            "SELECT * FROM projects WHERE name = ?", (name,)
        ).fetchone()
        return Project(**dict(row)) if row else None

    def get_project_by_id(self, project_id: int) -> Optional[Project]:
        row = self._conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        return Project(**dict(row)) if row else None

    def get_project_by_path(self, path: str) -> Optional[Project]:
        row = self._conn.execute(
            "SELECT * FROM projects WHERE path = ?", (path,)
        ).fetchone()
        return Project(**dict(row)) if row else None

    def touch_project(self, name: str) -> None:
        self._conn.execute(
            "UPDATE projects SET last_opened = ? WHERE name = ?", (time.time(), name)
        )
        self._conn.commit()
        self.set_meta("active_project", name)

    def active_project(self) -> Optional[str]:
        return self.get_meta("active_project")

    # -- events -----------------------------------------------------------
    def log_event(self, project_id: int, event_type: str, payload: Optional[dict] = None) -> None:
        self._conn.execute(
            "INSERT INTO events(project_id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
            (project_id, event_type, json.dumps(payload or {}), time.time()),
        )
        self._conn.commit()

    def recent_events(self, project_id: int, since: float, limit: int = 500) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM events WHERE project_id = ? AND created_at >= ? "
            "ORDER BY created_at ASC LIMIT ?",
            (project_id, since, limit),
        ).fetchall()

    def latest_event_at(self, project_id: int, file_events_only: bool = True) -> Optional[float]:
        """Most recent event timestamp for a project, or None if none logged."""
        if file_events_only:
            row = self._conn.execute(
                "SELECT MAX(created_at) AS ts FROM events "
                "WHERE project_id = ? AND event_type LIKE 'file_%'",
                (project_id,),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT MAX(created_at) AS ts FROM events WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        if row is None or row["ts"] is None:
            return None
        return float(row["ts"])

    # -- sessions ---------------------------------------------------------
    def add_session(
        self,
        project_id: int,
        started_at: float,
        ended_at: float,
        duration_minutes: float,
        files_modified: int,
        commits: int,
        lines_added: int,
        lines_deleted: int,
        todo_changes: int,
        cluster_label: Optional[str] = None,
    ) -> Session:
        cur = self._conn.execute(
            """
            INSERT INTO sessions(
                project_id, started_at, ended_at, duration_minutes,
                files_modified, commits, lines_added, lines_deleted,
                todo_changes, cluster_label
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                started_at,
                ended_at,
                duration_minutes,
                files_modified,
                commits,
                lines_added,
                lines_deleted,
                todo_changes,
                cluster_label,
            ),
        )
        self._conn.commit()
        return Session(
            id=cur.lastrowid,
            project_id=project_id,
            started_at=started_at,
            ended_at=ended_at,
            duration_minutes=duration_minutes,
            files_modified=files_modified,
            commits=commits,
            lines_added=lines_added,
            lines_deleted=lines_deleted,
            todo_changes=todo_changes,
            cluster_label=cluster_label,
        )

    def list_sessions(self, project_id: Optional[int] = None) -> list[Session]:
        if project_id is None:
            rows = self._conn.execute(
                """
                SELECT s.*, p.name AS project_name
                FROM sessions s
                JOIN projects p ON p.id = s.project_id
                ORDER BY s.started_at DESC
                """
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT s.*, p.name AS project_name
                FROM sessions s
                JOIN projects p ON p.id = s.project_id
                WHERE s.project_id = ?
                ORDER BY s.started_at DESC
                """,
                (project_id,),
            ).fetchall()
        return [self._row_to_session(r) for r in rows]

    def count_sessions(self, project_id: Optional[int] = None) -> int:
        if project_id is None:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM sessions WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        return int(row["n"]) if row else 0

    def update_session_labels(self, mapping: dict[int, str]) -> None:
        for session_id, label in mapping.items():
            self._conn.execute(
                "UPDATE sessions SET cluster_label = ? WHERE id = ?",
                (label, session_id),
            )
        self._conn.commit()

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> Session:
        data = dict(row)
        return Session(
            id=data["id"],
            project_id=data["project_id"],
            started_at=data["started_at"],
            ended_at=data["ended_at"],
            duration_minutes=data["duration_minutes"],
            files_modified=data["files_modified"],
            commits=data["commits"],
            lines_added=data["lines_added"],
            lines_deleted=data["lines_deleted"],
            todo_changes=data["todo_changes"],
            cluster_label=data.get("cluster_label"),
            project_name=data.get("project_name"),
        )


@contextlib.contextmanager
def open_storage() -> Iterator[Storage]:
    s = Storage()
    try:
        yield s
    finally:
        s.close()
