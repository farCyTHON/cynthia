"""Interactive shell — what runs when you type a bare `cynthia`.

Shows the welcome screen once, then drops into a `> ` prompt that accepts
the same commands as the regular CLI (with or without the leading
`cynthia`), keeping a little session state (the active project) so you
can `project open <path>` once and `status` / `log` afterwards without
repeating the name.

Opening a project automatically begins a focus session and starts a
file watcher; switching projects or exiting the shell finalizes it.
"""
from __future__ import annotations

import shlex
from typing import Optional

from rich.console import Console
from rich.text import Text

from . import config, health, overview, sessions, workspace
from .events import SyncEventCollector
from .storage import Project, Storage
from .ui import theme
from .ui.dashboard import render_status
from .ui.doctor import render_doctor
from .ui.focus import render_focus_analysis, render_sessions_table, render_similar_table
from .ui.overview import render_overview
from .ui.welcome import render_welcome
from .watcher import ProjectWatcher

HINTS = "[dim]\u2325\u21E5 tab next    g graph    e explore    ? help[/dim]"


class ShellSessionRuntime:
    """In-process watcher + session rotation for the interactive shell."""

    def __init__(self) -> None:
        self.collector: Optional[SyncEventCollector] = None
        self.watcher: Optional[ProjectWatcher] = None
        self.tracking_project: Optional[str] = None

    def start_tracking(self, project: Project, console: Console) -> None:
        self.stop_watcher_only()
        try:
            if sessions.has_active_session():
                active = sessions.active_session_project_name()
                if active == project.name:
                    # Resume watcher on an already-open snapshot (e.g. re-entry).
                    pass
                else:
                    sessions.begin_session(project, replace_active=True)
            else:
                sessions.begin_session(project)
        except sessions.FocusAlreadyActive:
            sessions.begin_session(project, replace_active=True)

        settings = config.Settings.load()
        self.collector = SyncEventCollector()
        self.watcher = ProjectWatcher(
            project.name,
            project.path,
            self.collector,
            ignored_dirs=set(settings.ignored_dirs),
        )
        self.watcher.start()
        self.tracking_project = project.name
        console.print(
            f"[dim]Recording focus session for [bold]{project.name}[/bold] "
            f"(auto-stops on exit or project switch)[/dim]"
        )

    def stop_watcher_only(self) -> None:
        if self.watcher is not None:
            try:
                self.watcher.stop()
            except Exception:
                pass
        self.watcher = None
        self.collector = None

    def files_modified_count(self) -> int:
        if self.collector is None:
            return 0
        return len(self.collector.unique_paths())

    def finalize(
        self,
        console: Console,
        *,
        quiet_short: bool = True,
    ) -> Optional[sessions.Session]:
        """Stop watcher and persist the active session if any."""
        files_modified = self.files_modified_count()
        self.stop_watcher_only()
        self.tracking_project = None

        if not sessions.has_active_session():
            return None
        try:
            session = sessions.finalize_session(files_modified=files_modified)
        except sessions.SessionTooShort:
            if not quiet_short:
                console.print("[dim]Session too short to record.[/dim]")
            return None
        except sessions.NoActiveFocus:
            return None

        console.print(
            f"[green]\u2713[/green] Session recorded for "
            f"[bold]{session.project_name}[/bold] "
            f"([cyan]{session.duration_minutes:.1f}m[/cyan], "
            f"{session.files_modified} files)"
        )
        return session

    def ensure_project(
        self,
        console: Console,
        project: Project,
        previous_name: Optional[str],
    ) -> None:
        """Rotate session when the active project changes."""
        if previous_name and previous_name != project.name:
            self.finalize(console, quiet_short=True)
        if self.tracking_project != project.name or not sessions.has_active_session():
            self.start_tracking(project, console)


def _footer(console: Console, active_project: str | None) -> None:
    settings = config.Settings.load() if config.is_initialized() else None
    left = active_project or "~"
    workspace_label = settings.workspace_name if settings else "no workspace"

    console.print()
    console.rule(style=theme.MUTED)
    line = Text()
    line.append(f"\U0001F4C1 {left}", style=theme.PRIMARY)
    line.append("    " + workspace_label, style=theme.MUTED)
    console.print(line)
    console.print(Text.from_markup(HINTS))


def run_shell() -> None:
    console = Console()
    settings = config.Settings.load() if config.is_initialized() else None
    render_welcome(console, settings.workspace_name if settings else None)
    _footer(console, active_project=None)

    runtime = ShellSessionRuntime()
    active_project: str | None = None
    if config.is_initialized():
        with Storage() as db:
            active_project = db.active_project()
        if active_project:
            try:
                project = workspace.resolve_project(active_project)
                runtime.start_tracking(project, console)
            except Exception:
                pass

    try:
        while True:
            try:
                raw = console.input("\n[bold]>[/bold] ")
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Goodbye![/dim]")
                break

            raw = raw.strip()
            if not raw:
                continue
            if raw in ("exit", "quit", ":q"):
                console.print("[dim]Goodbye![/dim]")
                break
            if raw == "clear":
                console.clear()
                continue

            try:
                active_project = _dispatch(console, raw, active_project, runtime)
            except Exception as exc:  # keep the shell alive no matter what a command does
                console.print(f"[bold red]Error:[/bold red] {exc}")

            _footer(console, active_project)
    finally:
        runtime.finalize(console, quiet_short=True)


def _dispatch(
    console: Console,
    raw: str,
    active_project: str | None,
    runtime: ShellSessionRuntime,
) -> str | None:
    parts = shlex.split(raw)
    if parts and parts[0] == "cynthia":
        parts = parts[1:]
    if not parts:
        return active_project

    cmd, *rest = parts

    if cmd == "init":
        name = rest[0] if rest else "default"
        workspace.init_workspace(name)
        console.print(f"[green]\u2713[/green] Initialized workspace [bold]{name}[/bold]")

    elif cmd == "add":
        if not rest:
            console.print("[red]Usage: add <path> [name][/red]")
            return active_project
        path = rest[0]
        name = rest[1] if len(rest) > 1 else None
        project = workspace.add_project(path, name)
        console.print(f"[green]\u2713[/green] Added project: [bold]{project.name}[/bold]")

    elif cmd == "list":
        projects = workspace.list_projects()
        if not projects:
            console.print("[dim]No projects registered yet. Try 'add <path>'.[/dim]")
        for p in projects:
            marker = "\u25CF" if p.name == active_project else " "
            console.print(f" {marker} [bold]{p.name}[/bold]  [dim]{p.path}[/dim]")

    elif cmd == "remove":
        if not rest:
            console.print("[red]Usage: remove <name>[/red]")
            return active_project
        removed = rest[0]
        if removed == active_project or removed == runtime.tracking_project:
            runtime.finalize(console, quiet_short=True)
        workspace.remove_project(removed)
        console.print(f"[green]\u2713[/green] Removed project: [bold]{removed}[/bold]")
        if removed == active_project:
            active_project = None

    elif cmd == "project" and rest and rest[0] == "open":
        if len(rest) < 2:
            console.print("[red]Usage: project open <path-or-name>[/red]")
            return active_project
        project = workspace.open_project(rest[1])
        console.print(f"[green]\u2713[/green] Opened project: [bold]{project.name}[/bold]")
        runtime.ensure_project(console, project, active_project)
        return project.name

    elif cmd == "status":
        name = rest[0] if rest else active_project
        project = workspace.resolve_project(name)
        snap = workspace.snapshot(project)
        with Storage() as db:
            db.touch_project(project.name)
            render_status(console, snap, db)
        runtime.ensure_project(console, project, active_project)
        return project.name

    elif cmd == "doctor":
        project = workspace.resolve_project_or_recent(rest[0] if rest else active_project)
        report = health.build_health_report(project.id)
        with Storage() as db:
            db.touch_project(project.name)
        render_doctor(console, report)
        runtime.ensure_project(console, project, active_project)
        return project.name

    elif cmd == "overview":
        data = overview.build_workspace_overview()
        render_overview(console, data)

    elif cmd == "log":
        name = rest[0] if rest else active_project
        project = workspace.resolve_project(name)
        _print_log(console, project)
        return project.name

    elif cmd == "focus":
        if not rest:
            try:
                result = sessions.analyze_sessions(all_projects=False)
            except workspace.NoActiveProject:
                result = sessions.analyze_sessions(all_projects=True)
            render_focus_analysis(console, result)
            return active_project
        if rest[0] not in ("start", "stop"):
            console.print("[red]Usage: focus | focus start [project] | focus stop[/red]")
            return active_project
        if rest[0] == "start":
            name = rest[1] if len(rest) > 1 else active_project
            project = workspace.resolve_project(name)
            # One active snapshot: finalize auto-tracking first, then begin.
            runtime.finalize(console, quiet_short=True)
            result = sessions.begin_session(project, replace_active=True)
            runtime.start_tracking(project, console)
            console.print(
                f"[green]\u2713[/green] Focus started on [bold]{result.project_name}[/bold]"
            )
            return project.name
        runtime.stop_watcher_only()
        try:
            session = sessions.stop_focus()
        except sessions.SessionTooShort as exc:
            console.print(f"[yellow]{exc}[/yellow]")
            runtime.tracking_project = None
            return active_project
        runtime.tracking_project = None
        console.print(
            f"[green]\u2713[/green] Focus session recorded for "
            f"[bold]{session.project_name}[/bold] "
            f"([cyan]{session.duration_minutes:.1f}m[/cyan])"
        )
        return session.project_name or active_project

    elif cmd == "similar":
        k = 3
        if rest:
            try:
                k = int(rest[0])
            except ValueError:
                console.print("[red]Usage: similar [k][/red]")
                return active_project
        files_count = (
            runtime.files_modified_count()
            if runtime.tracking_project
            else None
        )
        result = sessions.similar_to_active_session(
            files_modified=files_count,
            k=k,
        )
        render_similar_table(console, result)

    elif cmd == "sessions":
        if rest and rest[0] == "analyze":
            analyze_rest = rest[1:]
            all_projects = "--all" in analyze_rest
            name = next((a for a in analyze_rest if a != "--all"), None)
            result = sessions.analyze_sessions(
                project_name=name if not all_projects else None,
                all_projects=all_projects,
            )
            render_focus_analysis(console, result)
        else:
            name = rest[0] if rest else None
            rows = sessions.list_focus_sessions(name)
            render_sessions_table(console, rows)

    elif cmd in ("help", "?"):
        _print_help(console)

    else:
        console.print(f"[red]Unknown command:[/red] {cmd}  [dim](try 'help')[/dim]")

    return active_project


def _print_log(console: Console, project) -> None:
    from .git_observer import read_git_info

    info = read_git_info(project.path, recent_limit=50)
    if not info.is_repo:
        console.print("[yellow]Not a git repository.[/yellow]")
        return
    for i, c in enumerate(info.recent_commits):
        dot = theme.COMMIT_DOTS[i % len(theme.COMMIT_DOTS)]
        console.print(
            f"[{dot}]\u25CF[/{dot}] [cyan]{c.short_sha}[/cyan]  {c.message}  "
            f"[magenta]{c.author}[/magenta]  [dim]{c.relative_time}[/dim]"
        )


def _print_help(console: Console) -> None:
    rows = [
        ("init [name]", "Initialize a new workspace"),
        ("add <path> [name]", "Register a project"),
        ("list", "List all registered projects"),
        ("remove <name>", "Remove a registered project"),
        ("project open <path>", "Open project (starts auto session + watcher)"),
        ("status [name]", "Show the dashboard for a project"),
        ("doctor [name]", "Full diagnostic: health, quality, activity, risk"),
        ("overview", "Multi-project health and activity overview"),
        ("log [name]", "Show recent commit history"),
        ("focus", "Show K-Means work-mode breakdown"),
        ("focus start [name]", "Begin / restart a focus session"),
        ("focus stop", "End focus session and store metrics"),
        ("similar [k]", "Find k most similar historical sessions"),
        ("sessions [name]", "List recorded focus sessions"),
        ("sessions analyze", "Cluster sessions into work modes"),
        ("clear", "Clear the screen"),
        ("exit / quit", "Leave the shell (finalizes active session)"),
    ]
    console.print(Text("Commands:", style=f"bold {theme.PRIMARY}"))
    for cmd, desc in rows:
        console.print(f"  [bold cyan]{cmd:<22}[/bold cyan] [dim]{desc}[/dim]")
    console.print(
        "\n[dim]Tip: opening a project automatically records a focus session "
        "until you switch projects or exit. Use 'focus' and 'similar' on the "
        "active project.[/dim]"
    )
