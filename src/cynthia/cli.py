"""CYNTHIA's command-line entry point.

Every subcommand here is a thin wrapper around `workspace` / `ui` —
the same functions the interactive shell (`shell.py`) calls — so the
two front ends never drift apart.
"""
from __future__ import annotations

import asyncio
import sqlite3
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.text import Text

from . import config, health, overview, sessions, workspace
from .storage import Storage
from .ui import theme
from .ui.dashboard import render_status
from .ui.doctor import render_doctor
from .ui.focus import render_focus_analysis, render_sessions_table, render_similar_table
from .ui.overview import render_overview


def _configure_stdio() -> None:
    """Use UTF-8 on Windows so Rich can print symbols and emoji."""
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            reconfigure = getattr(stream, "reconfigure", None)
            if reconfigure:
                try:
                    reconfigure(encoding="utf-8")
                except Exception:
                    pass


_configure_stdio()

app = typer.Typer(
    name="cynthia",
    help="CYNTHIA — a local-first developer intelligence CLI.",
    no_args_is_help=False,
    add_completion=False,
)
project_app = typer.Typer(help="Manage the active project for this session.")
focus_app = typer.Typer(
    help="Focus sessions: start/stop tracking, or show K-Means work-mode breakdown.",
    invoke_without_command=True,
    no_args_is_help=False,
)
app.add_typer(project_app, name="project")
app.add_typer(focus_app, name="focus")

console = Console()

TAGLINE = "AI-native developer intelligence CLI"


def get_version() -> str:
    """Return the package version from `cynthia.__version__`.

    Falls back to "unknown" rather than raising, so `--version` never
    dies with a traceback on a broken or partial install.
    """
    try:
        from . import __version__

        version = str(__version__).strip()
    except Exception:
        return "unknown"
    return version or "unknown"


def _print_version() -> None:
    line = Text()
    line.append("CYNTHIA ", style=f"bold {theme.PRIMARY}")
    line.append(get_version(), style=f"bold {theme.ACCENT}")
    console.print(line)
    console.print(Text(TAGLINE, style=f"italic {theme.SUBTEXT}"))


def _version_callback(value: bool) -> None:
    if value:
        _print_version()
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show the CYNTHIA version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    if ctx.invoked_subcommand is None:
        from .shell import run_shell

        run_shell()


@app.command()
def init(name: str = typer.Argument("default", help="Workspace name")) -> None:
    """Initialize a new CYNTHIA workspace in ~/.cynthia."""
    workspace.init_workspace(name)
    console.print(f"[green]\u2713[/green] Initialized workspace [bold]{name}[/bold] at [dim]{config.workspace_home()}[/dim]")


@app.command()
def add(
    path: str = typer.Argument(..., help="Local path OR a git URL (https://, git@, ssh://) to clone"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Override the project name"),
) -> None:
    """Register an existing project, or clone-and-register a remote repo URL."""
    try:
        project = workspace.add_project(path, name)
    except (
        config.WorkspaceNotInitialized,
        workspace.ProjectAlreadyExists,
        workspace.CloneFailed,
        FileNotFoundError,
    ) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)
    console.print(f"[green]\u2713[/green] Added project: [bold]{project.name}[/bold]  [dim]{project.path}[/dim]")


@app.command(name="list")
def list_cmd() -> None:
    """List every project registered in this workspace."""
    try:
        projects = workspace.list_projects()
    except config.WorkspaceNotInitialized as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)
    if not projects:
        console.print("[dim]No projects registered yet. Try 'cynthia add <path>'.[/dim]")
        return
    with Storage() as db:
        active = db.active_project()
    for p in projects:
        marker = "\u25CF" if p.name == active else " "
        console.print(f" {marker} [bold]{p.name}[/bold]  [dim]{p.path}[/dim]  [magenta]{p.kind}[/magenta]")


@app.command()
def remove(name: str = typer.Argument(..., help="Registered project name")) -> None:
    """Remove a project from the workspace (does not touch files on disk)."""
    try:
        workspace.remove_project(name)
    except (config.WorkspaceNotInitialized, workspace.ProjectNotFound) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)
    console.print(f"[green]\u2713[/green] Removed project: [bold]{name}[/bold]")


@project_app.command("open")
def project_open(path_or_name: str = typer.Argument(..., help="Registered name, local path, or git URL")) -> None:
    """Register (if new) and mark a project as active for this session."""
    try:
        project = workspace.open_project(path_or_name)
    except (config.WorkspaceNotInitialized, workspace.ProjectNotFound, workspace.CloneFailed) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)
    console.print(f"[green]\u2713[/green] Opened project: [bold]{project.name}[/bold]")


@app.command()
def status(name: Optional[str] = typer.Argument(None, help="Project name (defaults to the active project)")) -> None:
    """Show the full health/activity dashboard for a project."""
    try:
        project = workspace.resolve_project(name)
        snap = workspace.snapshot(project)
    except (config.WorkspaceNotInitialized, workspace.ProjectNotFound, workspace.NoActiveProject) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)
    with Storage() as db:
        db.touch_project(project.name)
        render_status(console, snap, db)


@app.command()
def doctor(
    name: Optional[str] = typer.Argument(
        None, help="Project name (defaults to the active or most recently opened project)"
    ),
) -> None:
    """Run a full diagnostic: health, repository, quality, activity, and risk."""
    try:
        project = workspace.resolve_project_or_recent(name)
        report = health.build_health_report(project.id)
        with Storage() as db:
            db.touch_project(project.name)
    except (
        config.WorkspaceNotInitialized,
        workspace.ProjectNotFound,
        workspace.NoActiveProject,
        health.UnknownProject,
    ) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)
    except sqlite3.DatabaseError as exc:
        console.print(
            f"[red]Error:[/red] the workspace database could not be read ({exc}).\n"
            "[dim]If it is corrupted, move ~/.cynthia/workspace.db aside and run 'cynthia init'.[/dim]"
        )
        raise typer.Exit(1)
    render_doctor(console, report)


@app.command("overview")
def overview_cmd() -> None:
    """Show a multi-project workspace overview: health, activity, and branch."""
    try:
        data = overview.build_workspace_overview()
    except config.WorkspaceNotInitialized as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)
    except sqlite3.DatabaseError as exc:
        console.print(
            f"[red]Error:[/red] the workspace database could not be read ({exc}).\n"
            "[dim]If it is corrupted, move ~/.cynthia/workspace.db aside and run 'cynthia init'.[/dim]"
        )
        raise typer.Exit(1)
    render_overview(console, data)


@app.command()
def log(
    name: Optional[str] = typer.Argument(None, help="Project name (defaults to the active project)"),
    limit: int = typer.Option(20, "--limit", "-l", help="Number of commits to show"),
) -> None:
    """Show recent commit history for a project."""
    from .git_observer import read_git_info

    try:
        project = workspace.resolve_project(name)
    except (config.WorkspaceNotInitialized, workspace.ProjectNotFound, workspace.NoActiveProject) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)

    info = read_git_info(project.path, recent_limit=limit)
    if not info.git_available:
        console.print(
            "[yellow]Git is not installed on this system — commit history is unavailable.[/yellow]\n"
            "[dim]Local scanning (status, file counts, TODOs) still works without Git.[/dim]"
        )
        return
    if not info.is_repo:
        console.print("[yellow]Not a git repository.[/yellow]")
        return
    console.print(f"[bold]{project.name}[/bold] [dim]— {len(info.recent_commits)} commit(s)[/dim]\n")
    for i, c in enumerate(info.recent_commits):
        dot = theme.COMMIT_DOTS[i % len(theme.COMMIT_DOTS)]
        console.print(
            f"[{dot}]\u25CF[/{dot}] [cyan]{c.short_sha}[/cyan]  {c.message}  "
            f"[magenta]{c.author}[/magenta]  [dim]{c.relative_time}[/dim]"
        )


@app.command()
def watch(name: Optional[str] = typer.Argument(None, help="Project name (defaults to the active project)")) -> None:
    """Watch a project in real time, logging file events into the workspace."""
    try:
        project = workspace.resolve_project(name)
    except (config.WorkspaceNotInitialized, workspace.ProjectNotFound, workspace.NoActiveProject) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)

    console.print(f"\U0001F441  Watching [bold]{project.name}[/bold] — press Ctrl+C to stop.\n")
    asyncio.run(_watch_loop(project))


@focus_app.callback(invoke_without_command=True)
def focus_main(
    ctx: typer.Context,
    all_projects: bool = typer.Option(
        False, "--all", help="Analyze sessions across every project"
    ),
) -> None:
    """Show K-Means focus breakdown (or run a focus subcommand)."""
    if ctx.invoked_subcommand is not None:
        return
    try:
        result = sessions.analyze_sessions(all_projects=all_projects)
    except workspace.NoActiveProject:
        # Bare `cynthia focus` with no active project → analyze everything.
        result = sessions.analyze_sessions(all_projects=True)
    except (
        config.WorkspaceNotInitialized,
        workspace.ProjectNotFound,
    ) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)
    render_focus_analysis(console, result)


@focus_app.command("start")
def focus_start(
    name: Optional[str] = typer.Argument(None, help="Project name (defaults to the active project)"),
) -> None:
    """Begin a focus session by snapshotting the current project state."""
    try:
        project = workspace.resolve_project(name)
        result = sessions.start_focus(project)
    except (
        config.WorkspaceNotInitialized,
        workspace.ProjectNotFound,
        workspace.NoActiveProject,
        sessions.FocusAlreadyActive,
    ) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)
    import datetime as dt

    started = dt.datetime.fromtimestamp(result.started_at).strftime("%H:%M:%S")
    console.print(
        f"[green]\u2713[/green] Focus started on [bold]{result.project_name}[/bold] "
        f"at [dim]{started}[/dim]"
    )


@focus_app.command("stop")
def focus_stop() -> None:
    """End the active focus session and store computed metrics."""
    try:
        session = sessions.stop_focus()
    except (config.WorkspaceNotInitialized, sessions.NoActiveFocus) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)
    except sessions.SessionTooShort as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        return

    console.print(
        f"[green]\u2713[/green] Focus session recorded for "
        f"[bold]{session.project_name}[/bold] "
        f"([cyan]{session.duration_minutes:.1f}m[/cyan], "
        f"{session.files_modified} files, "
        f"+{session.lines_added}/-{session.lines_deleted} lines)"
    )


@app.command("sessions")
def sessions_cmd(
    args: Optional[list[str]] = typer.Argument(
        None,
        help="Optional project name, or 'analyze' [project]",
    ),
    all_projects: bool = typer.Option(
        False, "--all", help="With analyze: use sessions from every project"
    ),
) -> None:
    """List recorded focus sessions, or run work-mode analysis.

    Examples:
      cynthia sessions
      cynthia sessions my-app
      cynthia sessions analyze
      cynthia sessions analyze my-app
      cynthia sessions analyze --all
    """
    parts = list(args or [])
    try:
        if parts and parts[0] == "analyze":
            name = parts[1] if len(parts) > 1 else None
            result = sessions.analyze_sessions(
                project_name=name if not all_projects else None,
                all_projects=all_projects,
            )
            render_focus_analysis(console, result)
            return

        if all_projects and not parts:
            # `--all` alone implies analyze across projects
            result = sessions.analyze_sessions(all_projects=True)
            render_focus_analysis(console, result)
            return

        name = parts[0] if parts else None
        rows = sessions.list_focus_sessions(name)
        render_sessions_table(console, rows)
    except (
        config.WorkspaceNotInitialized,
        workspace.ProjectNotFound,
        workspace.NoActiveProject,
    ) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)


@app.command("similar")
def similar_cmd(
    k: int = typer.Option(3, "--k", "-k", help="Number of similar sessions to return"),
) -> None:
    """Find historical sessions most similar to the current focus context (k-NN)."""
    try:
        result = sessions.similar_to_active_session(k=k)
    except (
        config.WorkspaceNotInitialized,
        workspace.ProjectNotFound,
        workspace.NoActiveProject,
    ) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)
    render_similar_table(console, result)


async def _watch_loop(project) -> None:
    from .events import EventBus
    from .watcher import ProjectWatcher

    settings = config.Settings.load()
    bus = EventBus()
    bus.bind_loop(asyncio.get_running_loop())
    watcher = ProjectWatcher(project.name, project.path, bus, ignored_dirs=set(settings.ignored_dirs))
    watcher.start()

    with Storage() as db:
        try:
            async for event in bus.subscribe():
                db.log_event(project.id, event.type, event.payload)
                path = event.payload.get("path", "")
                console.print(f"[dim]{event.type}[/dim]  {path}")
        except asyncio.CancelledError:
            pass
        finally:
            watcher.stop()


def run() -> None:
    app()


if __name__ == "__main__":
    run()
