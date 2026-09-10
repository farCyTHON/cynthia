"""Timeline Engine — turns raw events + commits into the 7-day activity series.

CYNTHIA is event-driven: instead of rescanning a project from scratch on
every `status` call, it combines whatever the Git Observer already knows
about commit dates with whatever the File Watcher has logged into the
Storage Layer while `cynthia watch` was running. If a project has never
been watched, the series simply reflects commit activity — still
accurate, just less granular.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from .git_observer import GitInfo
from .storage import Storage

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@dataclass
class ActivitySeries:
    counts: dict[str, int]  # Mon..Sun -> combined activity count
    total: int
    from_watcher_events: bool  # True if any live-watched data contributed

    @property
    def max_count(self) -> int:
        return max(self.counts.values(), default=0)


def build_activity_series(
    storage: Storage, project_id: int, git_info: GitInfo, days: int = 7
) -> ActivitySeries:
    counts = {d: 0 for d in WEEKDAYS}
    for day, n in git_info.commits_by_weekday.items():
        counts[day] = counts.get(day, 0) + n

    now = dt.datetime.now(dt.timezone.utc)
    window_start = (now - dt.timedelta(days=days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).timestamp()

    rows = storage.recent_events(project_id, since=window_start, limit=5000)
    saw_watcher_events = False
    for row in rows:
        if row["event_type"].startswith("file_"):
            saw_watcher_events = True
            ts = dt.datetime.fromtimestamp(row["created_at"], tz=dt.timezone.utc)
            counts[WEEKDAYS[ts.weekday()]] += 1

    return ActivitySeries(counts=counts, total=sum(counts.values()), from_watcher_events=saw_watcher_events)
