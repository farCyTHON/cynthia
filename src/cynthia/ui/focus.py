"""Focus / sessions UI — tables and the Focus Analysis panel."""
from __future__ import annotations

import datetime as dt

from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..ml.kmeans_focus import WORK_MODES
from ..ml.knn_similar import SimilarSessionsResult
from ..sessions import AnalyzeResult
from ..storage import Session
from . import theme

BAR_WIDTH = 12
FOOTER = "Detected automatically using K-Means clustering over real session metrics."


def render_sessions_table(console: Console, sessions: list[Session]) -> None:
    """Render a Rich table of stored focus sessions."""
    if not sessions:
        console.print("[dim]No focus sessions recorded yet. Try 'cynthia focus start'.[/dim]")
        return

    table = Table(title="Focus Sessions", border_style=theme.MUTED, expand=True)
    table.add_column("ID", style=theme.ACCENT, justify="right")
    table.add_column("Project", style=theme.TEXT)
    table.add_column("Duration", style=theme.SUBTEXT, justify="right")
    table.add_column("Files", justify="right")
    table.add_column("Commits", justify="right")
    table.add_column("+/- Lines", justify="right")
    table.add_column("TODOs", justify="right")
    table.add_column("Mode", style=theme.PRIMARY)

    for s in sessions:
        started = dt.datetime.fromtimestamp(s.started_at).strftime("%Y-%m-%d %H:%M")
        table.add_row(
            str(s.id),
            f"{s.project_name or '?'}\n[dim]{started}[/dim]",
            f"{s.duration_minutes:.1f}m",
            str(s.files_modified),
            str(s.commits),
            f"+{s.lines_added}/-{s.lines_deleted}",
            str(s.todo_changes),
            s.cluster_label or "—",
        )
    console.print(table)


def render_similar_table(console: Console, result: SimilarSessionsResult) -> None:
    """Render the k-NN similar-sessions table."""
    if not result.enough_data:
        console.print(f"[yellow]{result.message}[/yellow]")
        return

    table = Table(
        title="Similar Sessions",
        border_style=theme.PRIMARY,
        expand=True,
        caption=f"Query: {result.query_source}",
        caption_style=theme.SUBTEXT,
    )
    table.add_column("Session ID", style=theme.ACCENT, justify="right")
    table.add_column("Similarity %", style=f"bold {theme.PRIMARY}", justify="right")
    table.add_column("Duration", style=theme.TEXT, justify="right")
    table.add_column("Files modified", justify="right")
    table.add_column("Commits", justify="right")

    for match in result.matches:
        table.add_row(
            str(match.session_id),
            f"{match.similarity_pct:.1f}%",
            f"{match.duration_minutes:.1f}m",
            str(match.files_modified),
            str(match.commits),
        )

    console.print(Align.center(table))
    console.print(
        Align.center(
            Text(
                "Ranked by Euclidean k-NN on standardized session metrics.",
                style=f"italic {theme.SUBTEXT}",
            )
        )
    )


def _bar(pct: int, color: str) -> Text:
    filled = max(0, min(BAR_WIDTH, round(pct / 100 * BAR_WIDTH)))
    empty = BAR_WIDTH - filled
    t = Text()
    t.append("█" * filled, style=f"bold {color}")
    t.append("░" * empty, style=theme.MUTED)
    return t


def render_focus_analysis(console: Console, result: AnalyzeResult) -> None:
    """Render the centered K-Means work-mode breakdown panel."""
    if not result.enough_data:
        console.print(Align.center(Text(result.message or "", style=theme.WARNING)))
        return

    rows = Table.grid(padding=(0, 2))
    rows.add_column(justify="left", min_width=22)
    rows.add_column(justify="left")
    rows.add_column(justify="right", min_width=4)

    for i, mode in enumerate(WORK_MODES):
        pct = result.percentages.get(mode, 0)
        color = theme.GRADIENT[min(i * 2, len(theme.GRADIENT) - 1)]
        rows.add_row(
            Text(mode, style=f"bold {color}"),
            _bar(pct, color),
            Text(f"{pct}%", style=f"bold {theme.TEXT}"),
        )

    body = Group(
        Align.center(Text("Work-mode breakdown", style=f"bold {theme.PRIMARY}")),
        Text(""),
        Align.center(rows),
        Text(""),
        Align.center(Text(FOOTER, style=f"italic {theme.SUBTEXT}")),
    )
    panel = Panel(
        body,
        title="[bold]CYNTHIA · Focus[/bold]",
        border_style=theme.PRIMARY,
        padding=(1, 3),
        width=min(72, console.width or 72),
    )
    console.print(Align.center(panel))
