"""Project Scanner — walks a project directory and reads its shape.

Produces the data CYNTHIA can get without touching Git: file counts,
a language breakdown by bytes, a rough project "kind", TODO/FIXME
locations, and total on-disk size. The Health Engine and the UI both
consume a ScanResult.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Extension -> display language. Deliberately covers what a student /
# early-stage repo is likely to contain; unknown extensions fall under "Other".
LANGUAGE_MAP = {
    ".py": "Python", ".pyi": "Python",
    ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".java": "Java", ".kt": "Kotlin",
    ".c": "C", ".h": "C",
    ".cpp": "C++", ".cc": "C++", ".hpp": "C++",
    ".cs": "C#",
    ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP",
    ".swift": "Swift", ".m": "Objective-C",
    ".html": "HTML", ".htm": "HTML", ".css": "CSS", ".scss": "CSS",
    ".md": "Markdown", ".rst": "Markdown",
    ".yml": "YAML", ".yaml": "YAML",
    ".toml": "TOML", ".json": "JSON",
    ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell",
    ".sql": "SQL",
}

# Kind detection: marker file -> project kind.
KIND_MARKERS = [
    ("pyproject.toml", "python"), ("requirements.txt", "python"), ("setup.py", "python"),
    ("package.json", "node"), ("Cargo.toml", "rust"), ("go.mod", "go"),
    ("pom.xml", "java"), ("build.gradle", "java"), ("Gemfile", "ruby"),
    ("composer.json", "php"), (".csproj", "dotnet"),
]

TODO_PATTERN = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b[:\s]*(.*)", re.IGNORECASE)

DEFAULT_IGNORES = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".mypy_cache", ".pytest_cache", ".idea", ".vscode",
    "target", ".next", ".turbo", ".tox", "site-packages", ".eggs",
}

# Skip binary-ish / huge extensions when looking for TODOs to avoid
# wasting time decoding things that were never going to contain one.
_BINARYISH = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".tar", ".gz",
    ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".mp3", ".wav", ".so", ".dll",
    ".exe", ".bin", ".db", ".sqlite", ".sqlite3", ".lock",
}

MAX_TODO_SCAN_BYTES = 2_000_000  # skip TODO scanning inside very large files


@dataclass
class TodoItem:
    file: str
    line: int
    tag: str
    text: str


@dataclass
class ScanResult:
    file_count: int = 0
    total_bytes: int = 0
    language_bytes: dict[str, int] = field(default_factory=dict)
    todos: list[TodoItem] = field(default_factory=list)
    kind: str = "unknown"
    has_readme: bool = False
    has_tests: bool = False

    @property
    def language_breakdown(self) -> list[tuple[str, float]]:
        """Languages sorted by share, as (name, percent) pairs."""
        total = sum(self.language_bytes.values())
        if total == 0:
            return []
        ranked = sorted(self.language_bytes.items(), key=lambda kv: -kv[1])
        return [(name, (n / total) * 100) for name, n in ranked]

    @property
    def human_size(self) -> str:
        size = float(self.total_bytes)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024 or unit == "TB":
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


def _detect_kind(root: Path) -> str:
    for marker, kind in KIND_MARKERS:
        if marker.startswith("."):
            if any(root.glob(f"*{marker}")):
                return kind
        elif (root / marker).exists():
            return kind
    return "unknown"


def scan_project(root: str | Path, ignored_dirs: set[str] | None = None) -> ScanResult:
    root = Path(root).expanduser().resolve()
    ignores = ignored_dirs or DEFAULT_IGNORES
    result = ScanResult(kind=_detect_kind(root))

    for path in root.rglob("*"):
        # prune ignored directories cheaply
        if any(part in ignores for part in path.relative_to(root).parts[:-1]):
            continue
        if path.is_dir():
            if path.name in ignores:
                continue
            continue
        if path.name in ignores:
            continue

        try:
            size = path.stat().st_size
        except OSError:
            continue

        result.file_count += 1
        result.total_bytes += size

        ext = path.suffix.lower()
        lang = LANGUAGE_MAP.get(ext)
        if lang:
            result.language_bytes[lang] = result.language_bytes.get(lang, 0) + size
        elif ext and ext not in _BINARYISH:
            result.language_bytes["Other"] = result.language_bytes.get("Other", 0) + size

        name_lower = path.name.lower()
        rel_parts = [p.lower() for p in path.relative_to(root).parts]
        if name_lower.startswith("readme"):
            result.has_readme = True
        if (
            any(part in ("test", "tests", "__tests__", "spec") for part in rel_parts)
            or name_lower.startswith("test_")
            or name_lower.endswith("_test.py")
            or name_lower.endswith(".test.js")
            or name_lower.endswith(".spec.ts")
        ):
            result.has_tests = True

        if ext not in _BINARYISH and size <= MAX_TODO_SCAN_BYTES and ext in LANGUAGE_MAP:
            _scan_todos(path, root, result)

    return result


def count_files_modified(
    root: str | Path,
    started_at: float,
    ended_at: float,
    ignored_dirs: set[str] | None = None,
) -> int:
    """Count files whose mtime falls inside [started_at, ended_at].

    The fallback for "what changed recently" when no watcher was running.
    """
    root = Path(root).expanduser().resolve()
    ignored = ignored_dirs if ignored_dirs is not None else set(DEFAULT_IGNORES)
    count = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in ignored for part in path.parts):
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if started_at <= mtime <= ended_at:
            count += 1
    return count


def _scan_todos(path: Path, root: Path, result: ScanResult) -> None:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return
    rel = str(path.relative_to(root))
    for i, line in enumerate(text.splitlines(), start=1):
        match = TODO_PATTERN.search(line)
        if match:
            result.todos.append(
                TodoItem(file=rel, line=i, tag=match.group(1).upper(), text=match.group(2).strip()[:120])
            )
