"""The status dashboard — everything `cynthia status` prints for one project."""
from __future__ import annotations

import datetime as dt

from rich.columns import Columns
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..timeline import ActivitySeries, WEEKDAYS, build_activity_series
from ..workspace import ProjectSnapshot
from . import theme

BAR_CHART_HEIGHT = 8


def _metric(icon: str, color: str, label: str, value: str) -> Text:
    t = Text()
    t.append(f"{icon} ", style=color)
    t.append(f"{label}\n", style=theme.SUBTEXT)
    t.append(value, style=f"bold {color}")
    return t


def _header_panel(snap: ProjectSnapshot) -> Panel:
    p = snap.project
    dot = "\u25cf" if _looks_active(snap) else "\u25cb"
    dot_color = theme.SUCCESS if _looks_active(snap) else theme.MUTED
    created = dt.datetime.fromtimestamp(p.created_at).strftime("%d %b %Y")

    title_line = Text()
    title_line.append("\U0001F4C1 ", style=theme.PRIMARY)
    title_line.append(p.name, style=f"bold {theme.TEXT}")
    subtitle = Text(p.path, style=theme.SUBTEXT)

    status_line = Text()
    status_line.append(f"{dot} ", style=dot_color)
    status_line.append("Active" if _looks_active(snap) else "Idle", style=dot_color)
    status_line.append("   Type: ", style=theme.SUBTEXT)
    status_line.append(snap.scan.kind, style=theme.ACCENT)
    status_line.append(f"   Created: {created}", style=theme.SUBTEXT)

    metrics = Columns(
        [
            _metric("\u2665", theme.STATUS_COLOR[snap.health.status], "Health", f"{snap.health.score}%"),
            _metric("\U0001F500", theme.PRIMARY, "Commits", str(snap.git.commit_count)),
            _metric("\U0001F4C4", theme.ACCENT, "Files", str(snap.scan.file_count)),
            _metric("\u26A0", theme.CRITICAL if snap.scan.todos else theme.SUCCESS, "Issues", str(len(snap.scan.todos))),
            _metric(
                "\U0001F9EA",
                theme.SUCCESS,
                "Tests",
                f"{snap.health.test_coverage}%" if snap.health.test_coverage is not None else "N/A",
            ),
        ],
        equal=True,
        expand=True,
    )

    body = Group(title_line, subtitle, Text(""), status_line, Text(""), metrics)
    return Panel(body, border_style=theme.PRIMARY, padding=(1, 2))


def _looks_active(snap: ProjectSnapshot) -> bool:
    if not snap.git.latest_commit:
        return False
    return (dt.datetime.now().timestamp() - snap.git.latest_commit.authored_at) < 60 * 60 * 24 * 14


def _activity_panel(series: ActivitySeries) -> Panel:
    nice_max = _nice_ceiling(series.max_count)
    rows: list[Text] = []
    for level in range(BAR_CHART_HEIGHT, 0, -1):
        row = Text()
        label = _axis_label(nice_max, level) if level % 2 == 0 or level == BAR_CHART_HEIGHT else ""
        row.append(f"{label:>4} ", style=theme.MUTED)
        for day in WEEKDAYS:
            bar_frac = 0 if nice_max == 0 else series.counts[day] / nice_max
            show = bar_frac * BAR_CHART_HEIGHT >= level
            row.append("\u2588\u2588  " if show else "    ", style=theme.PRIMARY if show else theme.DIM)
        rows.append(row)

    axis = Text("     ")
    for day in WEEKDAYS:
        axis.append(f"{day:<4}", style=theme.SUBTEXT)
    rows.append(axis)

    title = Text("ACTIVITY (7D)", style=f"bold {theme.PRIMARY}")
    return Panel(Group(title, Text(""), *rows), border_style=theme.MUTED, padding=(1, 2))


def _nice_ceiling(value: int) -> int:
    """Smallest 'round' ceiling whose quarters are clean integers, for tidy axis labels."""
    import math

    if value <= 0:
        return 4
    if value <= 40:
        return math.ceil(value / 4) * 4
    if value <= 100:
        return math.ceil(value / 20) * 20
    return math.ceil(value / 50) * 50


def _axis_label(nice_max: int, level: int) -> str:
    return str(round(nice_max * level / BAR_CHART_HEIGHT))


LANG_COLORS = [theme.PRIMARY, theme.ACCENT, "#3ce68c", "#ff4f9e", theme.WARNING, theme.MUTED]


def _languages_panel(snap: ProjectSnapshot) -> Panel:
    breakdown = snap.scan.language_breakdown[:6]
    title = Text("LANGUAGES", style=f"bold {theme.PRIMARY}")

    if not breakdown:
        body = Text("No source files detected.", style=theme.SUBTEXT)
        return Panel(Group(title, Text(""), body), border_style=theme.MUTED, padding=(1, 2))

    bar = Text()
    for i, (_, pct) in enumerate(breakdown):
        color = LANG_COLORS[i % len(LANG_COLORS)]
        width = max(1, round(pct / 100 * 24))
        bar.append("\u2588" * width, style=color)
    remaining = 24 - len(bar.plain)
    if remaining > 0:
        bar.append("\u2588" * remaining, style=theme.DIM)

    legend = Table.grid(padding=(0, 1))
    legend.add_column()
    legend.add_column()
    legend.add_column(justify="right")
    for i, (name, pct) in enumerate(breakdown):
        color = LANG_COLORS[i % len(LANG_COLORS)]
        legend.add_row(Text("\u25A0", style=color), Text(name, style=theme.TEXT), Text(f"{pct:.1f}%", style=theme.SUBTEXT))

    return Panel(Group(title, Text(""), bar, Text(""), legend), border_style=theme.MUTED, padding=(1, 2))


def _info_panel(snap: ProjectSnapshot) -> Panel:
    title = Text("PROJECT INFO", style=f"bold {theme.PRIMARY}")
    grid = Table.grid(padding=(0, 1))
    grid.add_column()
    grid.add_column()

    def row(icon: str, label: str, value: str, color: str = theme.TEXT):
        grid.add_row(Text(f"{icon} {label}", style=theme.SUBTEXT), Text(value, style=color))

    if snap.git.is_repo:
        row("\U0001F500", "Default Branch", snap.git.branch or "-", theme.ACCENT)
        row("\u25C7", "Latest Commit", snap.git.latest_commit.short_sha if snap.git.latest_commit else "-", theme.ACCENT)
        row("\u23F1", "Last Commit", snap.git.latest_commit.relative_time if snap.git.latest_commit else "-")
        row("\U0001F465", "Contributors", str(snap.git.contributors), theme.ACCENT)
    elif not snap.git.git_available:
        row("\u26A0", "Git", "not installed", theme.WARNING)
    else:
        row("\u26A0", "Git", "not a repository", theme.WARNING)
    row("\U0001F4BE", "Repo Size", snap.scan.human_size)

    return Panel(Group(title, Text(""), grid), border_style=theme.MUTED, padding=(1, 2))


def _history_panel(snap: ProjectSnapshot) -> Panel:
    title = Text("RECENT HISTORY", style=f"bold {theme.PRIMARY}")
    if not snap.git.recent_commits:
        if not snap.git.git_available:
            body = Text("Git is not installed — commit history unavailable.", style=theme.SUBTEXT)
        elif snap.git.is_repo:
            body = Text("No commits yet.", style=theme.SUBTEXT)
        else:
            body = Text("Not a git repository.", style=theme.SUBTEXT)
        return Panel(Group(title, Text(""), body), border_style=theme.MUTED, padding=(1, 2))

    table = Table.grid(padding=(0, 2), expand=True)
    table.add_column(width=2)
    table.add_column(style=theme.ACCENT)
    table.add_column(ratio=1)
    table.add_column(style=theme.PRIMARY)
    table.add_column(style=theme.SUBTEXT, justify="right")

    for i, c in enumerate(snap.git.recent_commits):
        dot_color = theme.COMMIT_DOTS[i % len(theme.COMMIT_DOTS)]
        table.add_row(Text("\u25CF", style=dot_color), c.short_sha, c.message, c.author, c.relative_time)

    hint = Text(f"Run 'cynthia log {snap.project.name}' to see full commit history", style=theme.MUTED)
    return Panel(Group(title, Text(""), table, Text(""), hint), border_style=theme.MUTED, padding=(1, 2))


def render_status(console: Console, snap: ProjectSnapshot, storage) -> None:
    series = build_activity_series(storage, snap.project.id, snap.git)

    console.print(_header_panel(snap))
    console.print()
    console.print(Columns([_activity_panel(series), _languages_panel(snap), _info_panel(snap)], equal=True, expand=True))
    console.print()
    console.print(_history_panel(snap))
