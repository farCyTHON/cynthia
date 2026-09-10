# CYNTHIA — Engineering Case Study

**Version:** 0.1.0 · **Distribution:** `cynthia-cli` · **License:** MIT  
**Author:** Fardin Hasan Siam  
**Stack:** Python 3.10+, Typer, Rich, SQLite, GitPython, watchdog, scikit-learn

---

## 1. Project Overview

### What CYNTHIA is

CYNTHIA is a **local-first developer intelligence CLI**. It does not write code, call cloud APIs, or replace an IDE. It watches, remembers, and explains what is happening across a developer’s projects—git activity, file churn, TODO/FIXME burden, focus sessions, and overall project health—from a SQLite database on the user’s machine.

The package installs as **`cynthia-cli`** on PyPI naming conventions, but the import package and console command are both **`cynthia`**. The interactive entry point is either a Typer subcommand (`cynthia status`, `cynthia doctor`, …) or a bare `cynthia` that drops into an interactive Rich shell.

### The original goal

The original brief asked for a Gemini-inspired terminal experience that could:

- Manage multiple local projects in one workspace
- Scan directories without requiring Git
- Observe Git history when available
- Watch files in real time
- Score project “health” transparently
- Present results in a premium purple/pink/blue Rich UI

Later milestones extended that core into session tracking and lightweight ML over *real* session metrics—not mock data.

### Why it was built

Developers often juggle several repositories. Context switches erase mental models: which project is healthy, which is silent, which file keeps changing, and whether the last stretch of work looked like feature work or bug fixing. Existing tools either stay inside one repo (Git UIs), stay in the cloud (analytics SaaS), or generate code (AI assistants). CYNTHIA sits in the gap: **multi-project awareness, offline, explainable, and terminal-native**.

### The problem it solves

| Pain | CYNTHIA’s answer |
|------|------------------|
| “I forget which side projects are rotting.” | `cynthia overview` + health scores |
| “What changed while I was focused?” | Watcher events + focus sessions |
| “Is this repo in good shape?” | `cynthia doctor` / `cynthia status` |
| “What kind of work have I been doing?” | K-Means work-mode breakdown |
| “Have I done something like this before?” | k-NN similar sessions |

Everything stays under `~/.cynthia` (overridable via `CYNTHIA_HOME`), with no network requirement for core features.

---

## 2. Development Journey

### Initial prototype

The first vertical slice was a **workspace + scanner + Git observer + status dashboard**:

1. `cynthia init` creates config and SQLite
2. `cynthia add` registers a path or clones a URL
3. `scanner.py` walks the tree (languages, TODOs, README/tests)
4. `git_observer.py` reads branch/commits when Git exists
5. `health.py` turns those signals into a 0–100 score
6. `ui/dashboard.py` renders a Gemini-styled Rich panel

Git was optional from day one: if `git` is missing, scanning still works and history is skipped—critical for student machines and locked-down environments.

### Major milestones

| Stage | Capability | Evidence in tree |
|-------|------------|------------------|
| Core workspace | init / add / list / remove / status / log / watch | `workspace.py`, `cli.py`, `watcher.py` |
| Interactive shell | Bare `cynthia` REPL with shared commands | `shell.py`, `ui/welcome.py` |
| Focus sessions | Snapshot start/stop, SQLite `sessions` table | `sessions.py`, `storage.py` |
| Auto recording | Shell opens project → watcher + session finalize on exit | `shell.ShellSessionRuntime` |
| K-Means focus | Work-mode percentages (need 8+ sessions) | `ml/kmeans_focus.py`, `ui/focus.py` |
| k-NN similar | Top-k historical sessions | `ml/knn_similar.py` |
| Version polish | `cynthia --version` / `-v` from `__version__` | `cli.get_version()`, `tests/test_version.py` |
| Packaging | MIT, SPDX license, `cynthia-cli`, twine-ready | `pyproject.toml`, `LICENSE` |
| Doctor | Deep single-project diagnostic + rule summary | `health.build_health_report`, `ui/doctor.py` |
| Overview | Multi-project health/activity table | `overview.py`, `ui/overview.py` |

### Evolution: simple CLI → developer intelligence tool

The project grew by **adding readers and classifiers on top of stable seams**, not by rewriting the core:

- Storage and Event Bus stayed the persistence/reactive spine
- Scanner + Git Observer stayed the fact sources
- Health stayed a transparent formula
- New surfaces (`doctor`, `overview`, ML) **compose** those facts

That is why `cli.py` and `shell.py` are deliberately thin: both call the same workspace/UI functions so the two front ends cannot drift.

---

## 3. Architecture

### Overall design

CYNTHIA is a **layered, event-aware CLI**:

1. **Presentation** — Typer CLI + interactive shell + Rich UI modules  
2. **Application** — workspace orchestration, sessions, overview, doctor reports  
3. **Domain services** — scanner, git observer, health, timeline, ML  
4. **Infrastructure** — SQLite storage, watchdog watcher, asyncio event bus  
5. **Config** — `~/.cynthia/config.toml` + `CYNTHIA_HOME`

### ASCII architecture diagram

```text
┌──────────────────────────────────────────────────────────────┐
│  Front ends                                                   │
│  cli.py (Typer)  ←→  shell.py (interactive REPL)              │
└─────────────┬────────────────────────────┬───────────────────┘
              │                            │
              ▼                            ▼
┌─────────────────────────┐    ┌───────────────────────────────┐
│  ui/  theme, welcome,   │    │  Application services         │
│  dashboard, doctor,     │◄───│  workspace · sessions ·       │
│  focus, overview        │    │  overview · health reports    │
└─────────────────────────┘    └───────────────┬───────────────┘
                                               │
               ┌───────────────────────────────┼────────────────┐
               ▼                               ▼                ▼
        ┌────────────┐                  ┌────────────┐   ┌──────────┐
        │  scanner   │                  │git_observer│   │   ml/    │
        │  timeline  │                  │   health   │   │kmeans+knn│
        └──────┬─────┘                  └──────┬─────┘   └────┬─────┘
               │                               │              │
               └───────────────┬───────────────┴──────────────┘
                               ▼
                    ┌─────────────────────┐
                    │  storage.py (SQLite) │
                    │  projects · events · │
                    │  sessions · meta     │
                    └──────────▲──────────┘
                               │
                    ┌──────────┴──────────┐
                    │ events.py EventBus  │
                    │ watcher.py (thread) │
                    └─────────────────────┘
```

### Role of each major area

| Area | Role |
|------|------|
| `workspace.py` | Register/resolve projects; build `ProjectSnapshot` |
| `storage.py` | Single SQLite schema for the workspace |
| `scanner.py` | Filesystem facts without Git |
| `git_observer.py` | Read-only GitPython facts + churn counts |
| `health.py` | Score + full doctor report + rule-based summary |
| `timeline.py` | 7-day activity series (commits + events) |
| `watcher.py` / `events.py` | Real-time file observation → bus → storage |
| `sessions.py` | Focus snapshot/finalize + analysis entry points |
| `overview.py` | Multi-project dashboard payload |
| `ml/` | Shared features, K-Means, k-NN |
| `ui/` | All Rich rendering; one module per screen |
| `config.py` | Paths, settings, init guard |

---

## 4. File-by-File Breakdown

### Package root (`src/cynthia/`)

#### `__init__.py`
- **Purpose:** Package docstring and single runtime version source.  
- **Key:** `__version__ = "0.1.0"`.  
- **Interactions:** `cli.get_version()` imports this; packaging also keeps `version` in `pyproject.toml`.

#### `config.py`
- **Purpose:** Workspace home (`~/.cynthia` or `CYNTHIA_HOME`), DB/config paths, `Settings` TOML load/save.  
- **Main types:** `Settings`, `WorkspaceNotInitialized`, `ensure_initialized()`.  
- **Interactions:** Almost every command checks initialization through workspace/storage.

#### `storage.py`
- **Purpose:** SQLite wrapper—`meta`, `projects`, `events`, `sessions`.  
- **Main API:** `add_project`, `list_projects`, `log_event`, `recent_events`, `latest_event_at`, session CRUD, focus snapshot meta key.  
- **Interactions:** Used by workspace, watch loop, sessions, timeline, doctor, overview.

#### `workspace.py`
- **Purpose:** Front door for project lifecycle.  
- **Main API:** `init_workspace`, `add_project`, `remove_project`, `list_projects`, `resolve_project`, `resolve_project_or_recent`, `open_project`, `snapshot`.  
- **Key logic:** URL detection + clone into workspace `repos/`; snapshot = scan + git + `compute_health`.  
- **Interactions:** CLI/shell; consumes scanner, git_observer, health, storage.

#### `scanner.py`
- **Purpose:** Directory walk—file counts, language bytes, kind markers, TODO/FIXME, README/tests, size.  
- **Main types:** `ScanResult`, `TodoItem`; `scan_project()`, `count_files_modified()`.  
- **Interactions:** Health, sessions, workspace snapshot, doctor.

#### `git_observer.py`
- **Purpose:** Optional, read-only Git metadata.  
- **Main types:** `GitInfo`, `CommitInfo`; `read_git_info()`, `file_change_counts()`, `humanize_delta()`, `git_runtime_available()`.  
- **Key logic:** Graceful degradation when Git missing; weekday commit buckets; merge commits skipped in churn.  
- **Interactions:** Status, log, health, doctor risk fallback, overview last-change.

#### `health.py`
- **Purpose:** Transparent scoring + doctor aggregate.  
- **Main types:** `HealthScore` (from `compute_health`), `HealthReport` (from `build_health_report`), quality/repo/activity/risk dataclasses.  
- **Key logic:** Penalties for TODOs, missing README/tests, stale git; `score_band` (90/70); `summarize()` rule sentences (no LLM).  
- **Interactions:** Workspace snapshot, doctor UI, overview badges.

#### `timeline.py`
- **Purpose:** Combine git weekday commits with watcher file events into a 7-day `ActivitySeries`.  
- **Interactions:** Status activity chart; overview activity High/Medium/Low.

#### `watcher.py`
- **Purpose:** Per-project `watchdog` Observer.  
- **Main class:** `ProjectWatcher` with ignored-dir filtering.  
- **Interactions:** Publishes to `EventBus` / `SyncEventCollector`.

#### `events.py`
- **Purpose:** Async pub/sub + sync collector for the shell.  
- **Main types:** `Event`, `EventBus`, `SyncEventCollector`.  
- **Key logic:** `publish_threadsafe` bridges watchdog threads into asyncio.

#### `sessions.py`
- **Purpose:** Focus session lifecycle and analysis entry points.  
- **Key logic:** Snapshot start metrics; on stop, diff commits/lines/TODOs/files; discard &lt; 1 minute; K-Means analyze; k-NN similar query.  
- **Interactions:** Storage, scanner, git_observer, ml/, shell runtime.

#### `overview.py`
- **Purpose:** Build `WorkspaceOverview` for all projects.  
- **Key logic:** Reuse snapshot + timeline + `score_band`; sort by last change; summary counts.  
- **Interactions:** `ui/overview.py`, CLI/shell.

#### `cli.py`
- **Purpose:** Typer app and console entry (`cynthia = cynthia.cli:app`).  
- **Key:** Eager `--version`/`-v`; commands for init/add/list/remove/status/doctor/overview/log/watch/focus/sessions/similar.  
- **Interactions:** All application modules + UI renderers.

#### `shell.py`
- **Purpose:** Interactive REPL mirroring CLI commands.  
- **Main class:** `ShellSessionRuntime` (auto focus + watcher).  
- **Interactions:** Same services as CLI; welcome/footer UI.

### ML (`src/cynthia/ml/`)

#### `features.py`
Shared 6-D vector: `files_modified`, `commits`, `lines_added`, `lines_deleted`, `duration_minutes`, `todo_changes`.

#### `kmeans_focus.py`
`StandardScaler` + `KMeans(n_clusters=4)`; centroid heuristics → Feature / Bug Fixing / Refactoring / Documentation; percentages sum to 100; guard at &lt; 8 sessions.

#### `knn_similar.py`
`NearestNeighbors` Euclidean; `similarity% = 100 / (1 + distance)`; exclude query id when searching stored sessions.

### UI (`src/cynthia/ui/`)

| File | Responsibility |
|------|----------------|
| `theme.py` | Gemini gradient palette and status colors |
| `logo.py` | Figlet wordmark with per-column gradient |
| `welcome.py` | Shell welcome screen |
| `dashboard.py` | `cynthia status` panels |
| `doctor.py` | Doctor diagnostic layout |
| `focus.py` | Sessions table, K-Means panel, similar table |
| `overview.py` | Multi-project summary + table |

---

## 5. Features Implemented

### Workspace management
`init`, `add` (path or git URL), `list`, `remove`, `project open`, active-project meta. State under `~/.cynthia`.

### Project scanning
Language breakdown, kind detection (`pyproject.toml`, `package.json`, …), TODO/FIXME/HACK/XXX, README/tests presence, human-readable size. Ignores `.git`, `node_modules`, venvs, etc.

### Git analytics
Branch, commit count, contributors, recent commits, dirty flag, remote URL, weekday activity. Optional Git—no hard dependency at runtime.

### Timeline tracking
`timeline.build_activity_series` merges commit weekdays with `file_*` events for the status chart and overview activity levels.

### Real-time watching
`cynthia watch` runs an asyncio loop logging watcher events to SQLite. The shell uses `SyncEventCollector` for live unique-path counts during auto sessions.

### Health scoring
Transparent 0–100 formula (TODO penalty capped, missing README/tests, stale history). Coverage shown only from real Cobertura `coverage.xml`. Doctor/overview use stricter **90 / 70** color bands via `score_band()`.

### Interactive shell
Welcome logo, prompt, shared commands, auto session on `project open`/`status`, finalize on switch/exit.

### Doctor dashboard
Header, health bar, repository/quality/activity panels, top-5 churn risk (watcher events preferred, else git history), rule-based summary. Degrades gracefully (no git, empty dir, deleted path, bad event log).

### Focus analysis
Store sessions; `focus` / `sessions analyze` run K-Means; Rich bar panel.

### Similar-session retrieval
`cynthia similar [-k]` uses live snapshot or latest stored session as query.

### Overview dashboard
`cynthia overview`: summary (projects, healthy, warning, most active) + sorted table (health, activity High/Medium/Low, last change, branch).

---

## 6. AI / ML Components

CYNTHIA’s “AI-native” claim is intentionally modest: **classical ML on real local metrics**, not generative models.

### K-Means clustering
- **Where:** `ml/kmeans_focus.py`  
- **Input:** Standardized 6-D session features  
- **Output:** Four work-mode labels + percentages  
- **Why K-Means:** Unsupervised, fast, deterministic with fixed `random_state`, interpretable once centroids are labeled by heuristics  
- **Guard:** Needs 8+ sessions so clusters are not noise

### k-NN similarity
- **Where:** `ml/knn_similar.py`  
- **Metric:** Euclidean on the same standardized space as K-Means  
- **Score:** Inverse distance to 0–100  
- **Why k-NN:** Natural “find sessions like this one” without training a model; works with small personal datasets

### Shared features
Keeping `ml/features.py` shared prevents K-Means and k-NN from silently disagreeing on what a session “is.”

### Real data only
Session rows come from git diffs, TODO scans, watcher/mtime file counts, and durations—never synthetic demo vectors in production paths. Tests may inject fixtures; the product path does not.

---

## 7. Problems Encountered

Evidence drawn from code structure, packaging, tests, and documented behavior:

1. **Duplicate logic** — `count_files_modified` lived in `sessions.py` while doctor/overview also needed mtime windows.  
2. **`HealthReport` naming conflict** — Doctor required `build_health_report() -> HealthReport`, but that name already meant the small score object.  
3. **Packaging / version split** — Runtime version vs `pyproject.toml` version; PyPI name `cynthia` contested → `cynthia-cli`.  
4. **Setuptools license warning** — `license = { text = "MIT" }` and license classifier deprecated under PEP 639.  
5. **Twine / README as long description** — PyPI render validation depends on README integrity.  
6. **Watcher shutdown** — Observer runs on another thread; shell must stop watcher and finalize sessions on exit/switch.  
7. **Data aggregation consistency** — Doctor risk vs activity vs timeline windows (calendar weekday buckets vs rolling 7 days).  
8. **Windows terminal rendering** — Legacy consoles force ASCII progress bars; piped output strips color.  
9. **PATH / venv discovery** — `cynthia` not on PATH unless `.venv` activated.  
10. **CLI vs shell drift risk** — Two front ends could diverge without discipline.

---

## 8. How Each Problem Was Fixed

| Problem | Root cause | Fix | Why better |
|---------|------------|-----|------------|
| Duplicate mtime walk | Feature growth without extraction | Moved `count_files_modified` to `scanner.py`; sessions re-exports | Single filesystem walker |
| HealthReport name | Overloaded type for score vs full report | Renamed score to `HealthScore`; `HealthReport` = doctor payload | Matches API brief; clear types |
| Version dual source | Packaging can’t import package during metadata read | `__version__` for runtime; `pyproject.toml` for build; test asserts equality | Safe packaging + tested sync |
| License deprecation | Old TOML table + classifier | `license = "MIT"` + `setuptools>=77` | PEP 639 / future-proof |
| Twine validation | README is the long description | Keep README fences balanced; `twine check` in release flow | PyPI-ready artifacts |
| Watcher lifecycle | Threaded observer outlives commands | `ProjectWatcher.stop()`; shell `finalize()` on exit/switch | No orphan observers; sessions close cleanly |
| Aggregation honesty | Different natural windows | Document sources on UI (`Measured via`, risk footer); reuse timeline totals for overview | Users see provenance |
| Windows Rich limits | `legacy_windows` ASCII fallback | Accept ASCII bars; keep numeric scores primary | Correctness over cosmetics |
| Command not found | Scripts only in venv | Document Activate.ps1 / direct `.exe` path | Matches real student Windows setups |
| Front-end drift | Two UIs | Thin wrappers over shared functions; shell help mirrors CLI | One behavior, two entry points |

---

## 9. Testing

**Current count: 50 tests collected** (`pytest --collect-only`).

| File | What it validates |
|------|-------------------|
| `tests/test_scanner.py` | File/language counts, TODOs/tests dir, project kind, human size |
| `tests/test_health.py` | High scores, README/tests penalties, TODO cap, coverage `None` |
| `tests/test_sessions.py` | Metric diffs, files_modified override, snapshot replace, sync collector, too-short discard, analyze guard, clustering %, mtime window |
| `tests/test_kmeans_focus.py` | &lt;8 guard; four labels; percentages sum to 100 |
| `tests/test_knn_similar.py` | Distance→similarity bounds, top-k, exclude id, empty history |
| `tests/test_version.py` | Non-empty semver, matches `__version__`, `--version`/`-v` banner |
| `tests/test_doctor.py` | Score range, summary, risk ranking/cap, degraded paths, bands, CLI invoke |
| `tests/test_overview.py` | Empty workspace, multiple projects, sort order, color thresholds, CLI render |

Tests isolate via `CYNTHIA_HOME` → `tmp_path` and stub Git where needed—no network, no real home pollution.

---

## 10. Packaging & Release

### `pyproject.toml`
- **Name:** `cynthia-cli`  
- **Version:** `0.1.0`  
- **License:** SPDX `"MIT"`  
- **Requires-Python:** `>=3.10`  
- **Entry point:** `cynthia = cynthia.cli:app`  
- **Build backend:** setuptools ≥ 77 (SPDX support)  
- **Layout:** `src/` discovery  

### Version management
Runtime: `src/cynthia/__init__.py` → `__version__`.  
Packaging: `[project].version`.  
Enforced equal by `tests/test_version.py`.

### MIT licensing
Full text in `LICENSE` (Copyright 2026 Fardin Hasan Siam); bundled into the wheel as `License-File`.

### Builds
```bash
python -m build          # sdist + wheel under dist/
twine check dist/*       # PASSED for both artifacts
```

### TestPyPI readiness
Metadata includes description, authors, keywords, classifiers, Homepage/Repository URLs, markdown README. Distribution name avoids the generic `cynthia` collision. Project is **ready for TestPyPI upload** pending credentials and a clean `dist/` for the intended version.

---

## 11. Current Status

### Fully complete
- Multi-project workspace (init/add/list/remove/open)  
- Scanner + optional Git observer  
- Status dashboard + log + watch  
- Interactive shell with auto focus recording  
- Health scoring + doctor + overview  
- Focus sessions + K-Means + k-NN  
- Version flag, MIT packaging metadata, 50-test suite  

### Partially complete / intentionally thin
- Coverage display only when `coverage.xml` exists (no coverage runner integration)  
- Summary language is rule-based (not model-backed)  
- Activity “High/Medium/Low” uses absolute thresholds (may read “Low” on quiet personal repos)  
- README documents packaging; automated release CI is not present in-repo  

### Future scope (not implemented)
From the original brief’s later sections and roadmap notes: LLM recommendations, semantic code search, cloud sync, VS Code extension, team workspaces, dependency graphs. The Event Bus and Storage Layer were designed so these can plug in without a rewrite—for example, replacing `health.summarize()` with a model later touches one function, not the CLI or renderer.

---

## 12. Technical Highlights

1. **Local-first by construction** — No cloud calls in the core path; `CYNTHIA_HOME` makes tests and multi-workspace use trivial.  
2. **Optional Git** — Correct degradation beats hard failure; students can still scan and score.  
3. **Two front ends, one domain** — CLI and shell share services; a classic way to prevent feature skew.  
4. **Explainable health** — Penalties are listed; coverage is never invented.  
5. **Event-driven timeline** — Status/overview improve when `watch` runs, but still work from commits alone.  
6. **Shared ML feature vector** — K-Means and k-NN cannot diverge on schema.  
7. **Doctor as composition** — Showcase UI without a second health engine.  
8. **Packaging hygiene** — SPDX license, src layout, twine-validated README, tested version sync.  
9. **Graceful diagnostics** — Doctor/overview prefer warnings over tracebacks for missing Git, empty trees, and corrupt event slices.

---

## 13. Future Roadmap

Realistic next steps, separated from what already ships:

| Horizon | Idea | Prerequisite |
|---------|------|--------------|
| Near | CI workflow (pytest + build + twine check) | GitHub Actions |
| Near | `cynthia config` command for settings | Existing TOML settings |
| Medium | Optional LLM summary behind `summarize()` interface | User API key; keep offline default |
| Medium | Richer risk signals (PR size, dependency age) | Extra scanners; still local |
| Longer | VS Code sidebar viewing the same SQLite | Stable storage schema |
| Longer | Team workspace sync | Explicit opt-in networking |

Non-goals for the near term: becoming a code generator, requiring always-on cloud, or hiding health math behind an opaque model.

---

## 14. Conclusion

CYNTHIA is a coherent answer to a practical question: *how do I understand the health and rhythm of my local projects without leaving the terminal or uploading my work?* Starting from a multi-project scanner and Gemini-styled status UI, it grew into a local intelligence layer—real-time watching, transparent health scoring, focus sessions, classical ML over genuine metrics, and showcase diagnostics (`doctor`, `overview`)—while keeping packaging and tests at release quality. The engineering story is less about adding features than about **preserving seams**: storage, events, scan/git facts, and shared UI theme so each new surface remains a reader or classifier, not a fork of the truth. At 0.1.0 with fifty automated tests and TestPyPI-ready metadata, CYNTHIA stands as a complete academic and portfolio-grade CLI: offline by default, explainable by design, and ready for measured future extensions rather than a rewrite.

---

*Document generated from the CYNTHIA codebase at version 0.1.0. Feature claims are limited to what exists under `src/cynthia` and `tests/`.*
