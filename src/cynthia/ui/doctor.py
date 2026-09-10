"""The doctor dashboard — everything `cynthia doctor` prints for one project.

Layout is a single centered column: header, health score, three fact
panels side by side, the churn-risk table, and the plain-English verdict.
Borders stay thin and muted so the numbers carry the page.
"""
from __future__ import annotations

import datetime as dt
import time

from rich import box
from rich.align import Align
from rich.columns import Columns
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

from ..health import HealthReport
from . import theme

REPORT_WIDTH = 92
STACK_WIDTH = 78  # below this the three fact panels stack vertically
RISK_BAR = 16
MAX_REASONS = 4

BAND_COLOR = {"green": theme.SUCCESS, "yellow": theme.WARNING, "red": theme.CRITICAL}

CHECK = "\u2713"
CROSS = "\u2717"


def _title(label: str) -> Text:
    return Text(label, style=f"bold {theme.PRIMARY}")


def _panel(*renderables, width: int, border: str = theme.MUTED) -> Panel:
    return Panel(Group(*renderables), border_style=border, padding=(1, 2), width=width)


def _header_panel(report: HealthReport, width: int) -> Panel:
    scanned = dt.datetime.fromtimestamp(report.last_scanned).strftime("%d %b %Y, %H:%M")

    heading = Text()
    heading.append("\u2695 ", style=theme.PRIMARY)
    heading.append(report.project_name, style=f"bold {theme.TEXT}")
    heading.append("   diagnostic report", style=theme.MUTED)

    meta = Text()
    meta.append(f"Last scanned {scanned}", style=theme.SUBTEXT)
    meta.append("   \u00b7   ", style=theme.DIM)
    meta.append(report.project_kind, style=theme.ACCENT)
    meta.append(f"   \u00b7   {report.file_count} files, {report.size}", style=theme.SUBTEXT)

    return _panel(
        heading,
        Text(report.project_path, style=theme.SUBTEXT),
        Text(""),
        meta,
        width=width,
        border=theme.PRIMARY,
    )


def _health_panel(report: HealthReport, width: int) -> Panel:
    color = BAND_COLOR[report.band]

    headline = Text()
    headline.append(str(report.score), style=f"bold {color}")
    headline.append(" / 100    ", style=theme.SUBTEXT)
    headline.append(report.status.upper(), style=f"bold {color}")

    bar = ProgressBar(
        total=100,
        completed=report.score,
        width=width - 8,
        complete_style=color,
        finished_style=color,
        style=theme.DIM,
    )

    body: list = [_title("HEALTH"), Text(""), headline, Text(""), bar, Text("")]
    if report.reasons:
        for reason in report.reasons[:MAX_REASONS]:
            body.append(Text(f"  \u2022 {reason}", style=theme.SUBTEXT))
    else:
        body.append(Text("  No penalties applied.", style=theme.SUBTEXT))

    return _panel(*body, width=width)


def _facts_panel(
    label: str,
    rows: list[tuple[str, str, str]],
    width: int,
    notes: list[Text] | None = None,
) -> Panel:
    """A label/value grid. Labels never truncate; long values ellipsize."""
    grid = Table.grid(padding=(0, 1))
    grid.add_column(style=theme.SUBTEXT, no_wrap=True)
    grid.add_column(justify="right", no_wrap=True, overflow="ellipsis")
    for name, value, color in rows:
        grid.add_row(Text(name), Text(value, style=color))

    body: list = [_title(label), Text(""), grid]
    if notes:
        body.append(Text(""))
        body.extend(notes)
    return _panel(*body, width=width)


def _repository_panel(report: HealthReport, width: int) -> Panel:
    repo = report.repository
    if not repo.git_available or not repo.is_repo:
        message = "Git is not installed." if not repo.git_available else "Not a git repository."
        return _panel(
            _title("REPOSITORY"),
            Text(""),
            Text(message, style=theme.WARNING),
            width=width,
        )

    rows = [
        ("Branch", repo.branch or "detached", theme.ACCENT),
        ("Commits", str(repo.commit_count), theme.TEXT),
        ("Authors", str(repo.contributors), theme.TEXT),
        (
            "Updated",
            _compact_age(repo.last_commit_at) if repo.last_commit_at else "never",
            theme.TEXT,
        ),
        (
            "Tree",
            "modified" if repo.is_dirty else "clean",
            theme.WARNING if repo.is_dirty else theme.SUCCESS,
        ),
    ]
    return _facts_panel("REPOSITORY", rows, width)


def _compact_age(timestamp: float) -> str:
    """'3d ago' rather than '3 days ago' — the fact panels are narrow."""
    delta = max(0.0, time.time() - timestamp)
    for unit, seconds in (("y", 31_536_000), ("mo", 2_592_000), ("d", 86_400), ("h", 3_600), ("m", 60)):
        if delta >= seconds:
            return f"{int(delta // seconds)}{unit} ago"
    return "just now"


def _quality_rows(report: HealthReport) -> list[tuple[str, str, str]]:
    quality = report.quality
    rows = [
        ("TODO", str(quality.todo_count), theme.WARNING if quality.todo_count else theme.SUCCESS),
        ("FIXME", str(quality.fixme_count), theme.CRITICAL if quality.fixme_count else theme.SUCCESS),
        ("README", *_presence(quality.has_readme)),
        ("Tests", *_presence(quality.has_tests)),
    ]
    if quality.test_coverage is not None:
        rows.append(("Coverage", f"{quality.test_coverage}%", theme.ACCENT))
    return rows


def _presence(present: bool) -> tuple[str, str]:
    return (
        (f"{CHECK} present", theme.SUCCESS) if present else (f"{CROSS} missing", theme.CRITICAL)
    )


def _activity_panel(report: HealthReport, width: int) -> Panel:
    activity = report.activity
    rows = [
        ("Changed", str(activity.files_changed), theme.ACCENT),
        ("Commits", str(activity.commits), theme.ACCENT),
    ]
    notes = [
        Text("Most modified", style=theme.SUBTEXT),
        Text(
            activity.most_modified_file or "\u2014",
            style=theme.TEXT,
            no_wrap=True,
            overflow="ellipsis",
        ),
        Text("Measured via", style=theme.SUBTEXT),
        Text(activity.source, style=theme.MUTED, no_wrap=True, overflow="ellipsis"),
    ]
    return _facts_panel("ACTIVITY (7D)", rows, width, notes)


def _risk_panel(report: HealthReport, width: int) -> Panel:
    if not report.risks:
        target = (
            f'"{report.project_name}"' if " " in report.project_name else report.project_name
        )
        hint = Text(
            f"No file-change history yet. Run 'cynthia watch {target}' to start collecting it.",
            style=theme.SUBTEXT,
        )
        return _panel(_title("RISK \u00b7 HIGHEST CHURN"), Text(""), hint, width=width)

    top = report.risks[0].changes or 1
    table = Table(box=box.SIMPLE, border_style=theme.DIM, expand=True, pad_edge=False)
    table.add_column("File", style=theme.TEXT, no_wrap=True, overflow="ellipsis", ratio=2)
    table.add_column("Churn", justify="left", width=RISK_BAR)
    table.add_column("Changes", justify="right", style=theme.SUBTEXT, width=7)

    for i, risk in enumerate(report.risks):
        color = theme.gradient_color(i / max(1, len(report.risks) - 1))
        filled = max(1, round(risk.changes / top * RISK_BAR))
        bar = Text()
        bar.append("\u2588" * filled, style=color)
        bar.append("\u2591" * (RISK_BAR - filled), style=theme.DIM)
        table.add_row(risk.path, bar, str(risk.changes))

    # box.SIMPLE already opens with a blank line, so no spacer before the table.
    source = Text(f"Source: {report.risk_source}", style=theme.MUTED)
    return _panel(_title("RISK \u00b7 HIGHEST CHURN"), table, source, width=width)


def _summary_panel(report: HealthReport, width: int) -> Panel:
    body: list = [_title("SUMMARY"), Text(""), Text(report.summary, style=theme.TEXT)]
    if report.warnings:
        body.append(Text(""))
        for warning in report.warnings:
            body.append(Text(f"\u26a0 {warning}", style=theme.WARNING))
    return _panel(*body, width=width, border=theme.ACCENT)


def render_doctor(console: Console, report: HealthReport) -> None:
    """Print the full diagnostic for one project, centered in the terminal."""
    width = min(REPORT_WIDTH, console.width or REPORT_WIDTH)

    console.print(Align.center(_header_panel(report, width)))
    console.print()
    console.print(Align.center(_health_panel(report, width)))
    console.print()

    column = (width - 6) // 3 if width >= STACK_WIDTH else width
    panels = [
        _repository_panel(report, column),
        _facts_panel("QUALITY", _quality_rows(report), column),
        _activity_panel(report, column),
    ]
    if width >= STACK_WIDTH:
        console.print(Align.center(Columns(panels, padding=(0, 1))))
    else:
        for panel in panels:
            console.print(Align.center(panel))

    console.print()
    console.print(Align.center(_risk_panel(report, width)))
    console.print()
    console.print(Align.center(_summary_panel(report, width)))
