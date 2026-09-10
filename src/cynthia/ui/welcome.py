"""The welcome screen — what a bare `cynthia` prints before the prompt."""
from __future__ import annotations

from rich.align import Align
from rich.console import Console
from rich.text import Text

from . import theme
from .logo import render_logo


def render_welcome(console: Console, workspace_name: str | None) -> None:
    console.print(Align.center(render_logo()))
    console.print(
        Align.center(Text("context-aware developer workflows", style=f"italic {theme.SUBTEXT}"))
    )
    console.print()
    console.print(
        Text.from_markup(
            "[bold]CYNTHIA[/bold] helps you understand your projects,\n"
            "track progress, and work with clarity.",
            style=theme.TEXT,
        )
    )
    console.print()
    console.print(Text("Getting started:", style=f"bold {theme.PRIMARY}"))

    steps = [
        ("cynthia init", "Initialize a new workspace"),
        ("cynthia add <path>", "Add an existing project"),
        ("cynthia list", "List all projects"),
        ("cynthia help", "Show all commands"),
    ]
    for i, (cmd, desc) in enumerate(steps, start=1):
        line = Text()
        line.append(f"{i}. ", style=theme.MUTED)
        line.append(f"{cmd:<20}", style=f"bold {theme.ACCENT}")
        line.append(f" - {desc}", style=theme.SUBTEXT)
        console.print(line)

    console.print()
    tip = Text()
    tip.append("\U0001F4A1 Tip: ", style=theme.WARNING)
    tip.append("Run ", style=theme.SUBTEXT)
    tip.append("'cynthia help'", style=f"bold {theme.ACCENT}")
    tip.append(" to see all available commands.", style=theme.SUBTEXT)
    console.print(tip)
