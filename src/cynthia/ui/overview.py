"""Workspace overview UI — the multi-project table for `cynthia overview`."""
from __future__ import annotations

from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..health import GREEN_MIN, YELLOW_MIN
from ..overview import WorkspaceOverview, band_color_name
from . import theme

BAND_STYLE = {
    "green": theme.SUCCESS,
    "yellow": theme.WARNING,
    "red": theme.CRITICAL,
}

ACTIVITY_STYLE = {
    "High": theme.SUCCESS,
    "Medium": theme.WARNING,
    "Low": theme.MUTED,
}


def health_badge(score: int, band: str) -> Text:
    """Colored health badge using the 90 / 70 doctor bands."""
    color = BAND_STYLE[band_color_name(band)]
    return Text(f"{score}%", style=f"bold {color}")


def render_overview(console: Console, overview: WorkspaceOverview) -> None:
    """Print the centered summary panel + project table."""
    if overview.is_empty:
        console.print(
            Align.center(
                Text(
                    "No projects registered yet. Try 'cynthia add <path>'.",
                    style=theme.SUBTEXT,
                )
            )
        )
        return

    width = min(92, console.width or 92)
    console.print(Align.center(_summary_panel(overview, width)))
    console.print()
    console.print(Align.center(_projects_table(overview)))


def _summary_panel(overview: WorkspaceOverview, width: int) -> Panel:
    title = Text()
    title.append("CYNTHIA", style=f"bold {theme.PRIMARY}")
    title.append(" · ", style=theme.MUTED)
    title.append("Workspace Overview", style=f"bold {theme.TEXT}")

    stats = Table.grid(expand=True, padding=(0, 2))
    stats.add_column(justify="center")
    stats.add_column(justify="center")
    stats.add_column(justify="center")
    stats.add_column(justify="center")
    stats.add_row(
        _stat("Projects", str(overview.total_projects), theme.ACCENT),
        _stat("Healthy", str(overview.healthy_projects), theme.SUCCESS),
        _stat("Warning", str(overview.warning_projects), theme.WARNING),
        _stat("Most active", overview.most_active or "—", theme.PRIMARY),
    )

    body = Group(Align.center(title), Text(""), stats)
    return Panel(body, border_style=theme.PRIMARY, padding=(1, 2), width=width)


def _stat(label: str, value: str, color: str) -> Text:
    t = Text()
    t.append(f"{label}\n", style=theme.SUBTEXT)
    t.append(value, style=f"bold {color}")
    return t


def _projects_table(overview: WorkspaceOverview) -> Table:
    table = Table(
        box=box.ROUNDED,
        border_style=theme.MUTED,
        header_style=f"bold {theme.PRIMARY}",
        expand=True,
        pad_edge=False,
        show_lines=False,
    )
    table.add_column("Project", style=theme.TEXT, no_wrap=True, overflow="ellipsis")
    table.add_column("Health", justify="right")
    table.add_column("Activity", justify="center")
    table.add_column("Last Change", style=theme.SUBTEXT, justify="right")
    table.add_column("Branch", style=theme.ACCENT, justify="left")

    for row in overview.rows:
        activity = Text(
            row.activity_level,
            style=f"bold {ACTIVITY_STYLE.get(row.activity_level, theme.MUTED)}",
        )
        table.add_row(
            row.name,
            health_badge(row.health_score, row.band),
            activity,
            row.last_change,
            row.branch,
        )

    # Quiet legend so the 90/70 thresholds stay discoverable.
    table.caption = (
        f"Health: {GREEN_MIN}+ green · {YELLOW_MIN}–{GREEN_MIN - 1} yellow · "
        f"below {YELLOW_MIN} red   ·   Sorted by most recent activity"
    )
    table.caption_style = theme.MUTED
    return table
