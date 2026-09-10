"""File Watcher — real-time filesystem observation for one project.

Wraps `watchdog`. Each watched project gets its own Observer + handler
(per the brief's "each project has its own file watcher"); every relevant
filesystem event is turned into an Event and handed to the shared Event
Bus, which the caller drains from an asyncio loop.
"""
from __future__ import annotations

from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .events import Event, EventBus

_TYPE_MAP = {
    "created": "file_created",
    "modified": "file_modified",
    "deleted": "file_deleted",
    "moved": "file_moved",
}


class _Handler(FileSystemEventHandler):
    def __init__(self, bus: EventBus, project_name: str, ignored_dirs: set[str]):
        self.bus = bus
        self.project_name = project_name
        self.ignored_dirs = ignored_dirs

    def _ignored(self, path: str) -> bool:
        parts = set(Path(path).parts)
        return bool(parts & self.ignored_dirs)

    def _handle(self, event: FileSystemEvent) -> None:
        if event.is_directory or self._ignored(event.src_path):
            return
        kind = _TYPE_MAP.get(event.event_type)
        if not kind:
            return
        self.bus.publish_threadsafe(
            Event(type=kind, project_name=self.project_name, payload={"path": event.src_path})
        )

    on_created = _handle
    on_modified = _handle
    on_deleted = _handle
    on_moved = _handle


class ProjectWatcher:
    """Starts/stops a watchdog Observer scoped to one project directory."""

    def __init__(self, project_name: str, root: str | Path, bus: EventBus, ignored_dirs: set[str] | None = None):
        self.project_name = project_name
        self.root = str(Path(root).expanduser().resolve())
        self.bus = bus
        self._observer = Observer()
        self._handler = _Handler(bus, project_name, ignored_dirs or set())

    def start(self) -> None:
        self._observer.schedule(self._handler, self.root, recursive=True)
        self._observer.start()

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join(timeout=5)
