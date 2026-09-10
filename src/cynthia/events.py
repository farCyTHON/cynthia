"""Event Bus — the seam between "things happened" and "things are stored".

A tiny asyncio pub/sub. The File Watcher (running on a background thread,
per watchdog's design) publishes onto it via a thread-safe bridge; the
`cynthia watch` command's async loop subscribes and persists each event
through the Storage Layer. Kept separate from Storage on purpose: nothing
about "how do I react to a change" should need to know "how is a change
persisted", and vice versa.

`SyncEventCollector` is the same publish surface without an asyncio loop —
used by the interactive shell to count file changes during a focus session.
"""
from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


@dataclass
class Event:
    type: str  # "file_created" | "file_modified" | "file_deleted" | "commit_detected" | ...
    project_name: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class EventBus:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Call once from within the running loop so other threads can publish safely."""
        self._loop = loop

    def publish(self, event: Event) -> None:
        """Publish from within the event loop's own thread."""
        self._queue.put_nowait(event)

    def publish_threadsafe(self, event: Event) -> None:
        """Publish from a *different* thread (e.g. a watchdog observer thread)."""
        if self._loop is None:
            raise RuntimeError("EventBus.bind_loop() must be called before publish_threadsafe()")
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event)

    async def subscribe(self) -> AsyncIterator[Event]:
        while True:
            yield await self._queue.get()


class SyncEventCollector:
    """Thread-safe sink with the same `publish_threadsafe` surface as EventBus.

    Used by the interactive shell (no asyncio loop) to collect watcher events
    and count unique file paths touched during a session.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[Event] = []

    def publish_threadsafe(self, event: Event) -> None:
        with self._lock:
            self._events.append(event)

    def publish(self, event: Event) -> None:
        self.publish_threadsafe(event)

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._events)

    def unique_paths(self) -> set[str]:
        with self._lock:
            paths: set[str] = set()
            for event in self._events:
                path = event.payload.get("path")
                if path:
                    paths.add(str(path))
                dest = event.payload.get("dest_path")
                if dest:
                    paths.add(str(dest))
            return paths

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
