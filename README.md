# CYNTHIA
[![PyPI version](https://badge.fury.io/py/cynthia-cli.svg)](https://pypi.org/project/cynthia-cli/)
[![PyPI Downloads](https://img.shields.io/pypi/dm/cynthia-cli.svg)](https://pypistats.org/packages/cynthia-cli)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**AI-native, local-first developer intelligence CLI.**

CYNTHIA doesn't write code for you. It watches, remembers, and explains
what's happening across your projects — git activity, file churn, TODOs,
focus sessions, and overall project health — from a local SQLite store on
your own machine. No cloud upload, no changing how you work.

Start with [`cynthia doctor`](#project-doctor-cynthia-doctor) for a deep
single-project diagnostic, or [`cynthia overview`](#workspace-overview-cynthia-overview)
to compare every registered project at a glance.

```
 ██████╗██╗   ██╗███╗   ██╗████████╗██╗  ██╗██╗ █████╗
██╔════╝╚██╗ ██╔╝████╗  ██║╚══██╔══╝██║  ██║██║██╔══██╗
██║      ╚████╔╝ ██╔██╗ ██║   ██║   ███████║██║███████║
██║       ╚██╔╝  ██║╚██╗██║   ██║   ██╔══██║██║██╔══██║
╚██████╗   ██║   ██║ ╚████║   ██║   ██║  ██║██║██║  ██║
 ╚═════╝   ╚═╝   ╚═╝  ╚═══╝   ╚═╝   ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝
        context-aware developer workflows
```

## Install

```bash
cd cynthia
pip install -e .          # or: pip install -e ".[dev]" to also get pytest
```

This registers a `cynthia` command on your PATH (via the `[project.scripts]`
entry point in `pyproject.toml`).

On Windows with a virtual environment:

```powershell
cd "path\to\cynthia"
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Three names are involved, and they are deliberately different:

| Name | Value | Why |
|------|-------|-----|
| Distribution (PyPI) | `cynthia-cli` | `cynthia` is a common name on PyPI; the `-cli` suffix keeps the project publishable |
| Import package | `cynthia` | What `import cynthia` and `from cynthia.cli import app` use |
| Console command | `cynthia` | What you type in the terminal |

**Git (optional but recommended):** install [Git for Windows](https://git-scm.com/download/win)
and reopen your terminal so `git --version` works. Without Git, local scanning
still works; commit history, line diffs, and some focus metrics are skipped.

### Verify the install

```bash
cynthia --version
```

```text
CYNTHIA 0.1.0
AI-native developer intelligence CLI
```

`--version` and its short form `-v` are eager Typer options on the root
callback, so they print and exit **before** the bare-`cynthia` interactive
shell would otherwise start.

The version has one source of truth, `__version__` in
`src/cynthia/__init__.py`, which `cli.get_version()` reads:

```python
def get_version() -> str:
    try:
        from . import __version__

        version = str(__version__).strip()
    except Exception:
        return "unknown"
    return version or "unknown"
```

The `try` matters: on a broken or partial install `cynthia --version`
returns `unknown` instead of dumping a traceback at someone who was just
asking which build they have. `pyproject.toml` keeps its own `version`
field because packaging tools read metadata without importing the
package — the two are checked against each other in `tests/test_version.py`.

**If `cynthia` is "not recognized"** the virtual environment simply isn't
active in that shell — the launcher lives inside `.venv`, not on your
global PATH:

```powershell
.\.venv\Scripts\Activate.ps1        # then: cynthia --version
.\.venv\Scripts\cynthia.exe --version   # or call it directly, no activation
```

If PowerShell blocks the activation script, allow it for that shell only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Quick start

```bash
cynthia --version                     # confirm which build you're running
cynthia init                          # create ~/.cynthia (workspace db + config)
cynthia add ~/projects/my-app         # register a project (local path or git URL)
cynthia list                          # see everything you've registered
cynthia status my-app                 # the full dashboard
cynthia doctor my-app                 # full diagnostic + plain-English verdict
cynthia overview                      # multi-project health / activity table
cynthia log my-app                    # recent commit history
cynthia watch my-app                  # live file-change monitoring (Ctrl+C to stop)

# Focus sessions (work tracking + clustering)
cynthia focus start my-app            # begin a focus session
cynthia focus stop                    # end it (≥1 minute) and store metrics
cynthia sessions                      # list recorded sessions
cynthia sessions analyze              # K-Means work-mode breakdown (needs 8+)
cynthia focus                         # same clustering with Rich bar panel
cynthia similar                       # 3 most similar historical sessions (k-NN)
```

Or just run `cynthia` with no arguments for the interactive shell shown
above — it accepts the same commands, plus `project open <path>` to
switch your active project for the session so you can type `status`
without repeating the name:

```
> project open ~/projects/chronicle
✓ Opened project: chronicle
> status
╭─ chronicle ──────────────────────────────────────╮
│ ♥ Health 92%   ⎇ Commits 72   📄 Files 284  ...  │
╰────────────────────────────────────────────────────╯
> doctor
> overview
> help                                  # every shell command
```

## Project doctor (`cynthia doctor`)

`cynthia doctor` answers one question in one screen: **what is the state of
this project right now?** Health score, repository facts, quality gaps,
7-day activity, the files churning hardest, and a plain-English verdict.

It is a *reader*, not a second implementation: it calls the same Health
Engine, Scanner, Git Observer, and event log that `cynthia status` uses, so
the two can never disagree about a number.

### Commands

```bash
cynthia doctor                 # active project, or the most recently opened one
cynthia doctor my-app          # by registered name
cynthia doctor ~/projects/app  # by path (resolved to a registered project)
```

```powershell
cd "path\to\cynthia"
.\.venv\Scripts\Activate.ps1
cynthia doctor
```

Inside the interactive shell — same renderer, same data:

```text
> doctor
> doctor my-app
```

With no argument, the project is resolved in this order:

1. The **active project** (whatever `project open`, `status`, or `doctor` last touched).
2. The **most recently opened** project in the `projects` table.

That second step is why `cynthia doctor` works in a fresh terminal without
setting an active project first. Like `status`, running `doctor` also marks
that project active for subsequent commands.

### What it reports

| Section | Contents | Source |
|---------|----------|--------|
| Header | Name, absolute path, last-scanned time, kind, file count, size | `scanner.py` + `projects` table |
| Health | 0–100 score, colored bar, status word, penalty reasons | `health.compute_health()` |
| Repository | Branch, commits, authors, last-commit age, working-tree state | `git_observer.read_git_info()` |
| Quality | TODO count, FIXME count, README, tests, coverage | `scanner.py` scan result |
| Activity (7D) | Files changed, commits, most-modified file, measurement source | `events` table, or `mtime` walk + git |
| Risk | Up to 5 files ranked by modification frequency | `events` table, falling back to git history |
| Summary | One to three rule-based sentences | `health.summarize()` — no LLM |

### Score bands

`doctor` grades harder than the `status` dashboard on purpose: a project
needs a nearly clean bill of health to show green.

| Band | Score | Color |
|------|-------|-------|
| Healthy | 90–100 | green (`theme.SUCCESS`) |
| Stable, with gaps | 70–89 | amber (`theme.WARNING`) |
| Needs attention | 0–69 | red (`theme.CRITICAL`) |

The underlying score is unchanged — the same transparent penalties described
in [Notes on the numbers](#notes-on-the-numbers). Only the display
thresholds are stricter, and they live in one place (`health.score_band()`)
so the CLI and any future UI agree.

### Where "risk" comes from

The risk table ranks files by how often they changed. CYNTHIA tries the
most precise source first and always prints which one it used:

| Priority | Source | Label shown | When it applies |
|---|---|---|---|
| 1 | `events` table (file events from `cynthia watch`) | `watcher events (last 7 days)` | Any project you have watched recently |
| 2 | Git history, last 40 non-merge commits | `git history (last 40 commits)` | A git repo that has never been watched |
| 3 | Nothing | `no file-change history yet` | Neither available — panel suggests `cynthia watch` |

Merge commits are skipped in the git fallback so a single merge doesn't
credit every file on the branch. `Activity → Files changed` follows the same
idea: unique paths from watcher events when they exist, otherwise an `mtime`
walk over the working tree.

### Summary rules (no LLM)

The verdict is composed from the numbers by `health.summarize()`. It is
deterministic, offline, and unit-tested — three clauses at most:

1. **Band + activity** → `"Project is healthy and actively maintained."`,
   `"Project is stable but has missing tests."`, or
   `"Project needs attention: it is missing tests and a README."`
2. **Churn topic**, when the hottest file changed 4+ times → the file path
   is matched against a keyword table and named as a concern, e.g.
   `"Project shows high churn in authentication-related files."`
3. **Git caveat**, when relevant → git not installed, not a repository, or
   no commits in the last 7 days.

Topics are keyword-matched against the hot file's path (first match wins,
so specific concerns beat generic ones):

| Topic | Matched on |
|-------|-----------|
| authentication | `auth`, `login`, `logout`, `oauth`, `token`, `password`, `credential` |
| security | `security`, `permission`, `crypto` |
| data-model | `migration`, `schema`, `model`, `database`, `storage`, `sql`, `repository` |
| API | `api`, `route`, `endpoint`, `controller`, `handler`, `server` |
| UI | `component`, `view`, `template`, `widget`, `layout`, `style`, `css`, `html` |
| test | `test`, `spec`, `fixture` |
| configuration | `config`, `setting`, `env` |
| CLI | `cli`, `command`, `shell` |
| documentation | `readme`, `docs`, `doc` |

No keyword match falls back to naming the file itself, so the sentence is
never vague: `"Most file churn is concentrated in src/thing.py."`

### Example output

Real run, after `cynthia watch` recorded four edits to `index.html`, two to
`ATTRIBUTIONS.md`, and one to `README.md`:

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│  ⚕ pawsphere-demo   diagnostic report                                        │
│  /tmp/cynthia-doctor-demo/pawsphere-demo                                      │
│                                                                              │
│  Last scanned 06 Aug 2026, 03:55   ·   node   ·   67 files, 580.4 KB         │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│  HEALTH                                                                      │
│                                                                              │
│  90 / 100    HEALTHY                                                         │
│                                                                              │
│  ----------------------------------------------------------------            │
│    • no tests directory found                                                │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘

   ┌──────────────────────┐ ┌──────────────────────┐ ┌──────────────────────┐
   │                      │ │                      │ │                      │
   │  REPOSITORY          │ │  QUALITY             │ │  ACTIVITY (7D)       │
   │                      │ │                      │ │                      │
   │  Branch      main    │ │  TODO           0    │ │  Changed 3           │
   │  Commits        8    │ │  FIXME          0    │ │  Commits 8           │
   │  Authors        2    │ │  README ✓ present    │ │                      │
   │  Updated   4d ago    │ │  Tests  ✗ missing    │ │  Most modified       │
   │  Tree    modified    │ │                      │ │  index.html          │
   │                      │ └──────────────────────┘ │  Measured via        │
   └──────────────────────┘                          │  watcher events      │
                                                     │                      │
                                                     └──────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│  RISK · HIGHEST CHURN                                                        │
│                                                                              │
│   File                                          Churn              Changes   │
│   ────────────────────────────────────────────────────────────────────────   │
│   index.html                                    ████████████████         4   │
│   ATTRIBUTIONS.md                               ████████░░░░░░░░         2   │
│   README.md                                     ████░░░░░░░░░░░░         1   │
│                                                                              │
│  Source: watcher events (last 7 days)                                        │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│  SUMMARY                                                                     │
│                                                                              │
│  Project is healthy and actively maintained. Project shows high churn in     │
│  UI-related files.                                                           │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

That capture is verbatim, which is why two things look plain. Colors are
stripped when output is piped to a file, and the health bar is a Rich
`ProgressBar` that falls back to ASCII in a legacy Windows console — it still
draws the correct fraction (90% of the bar width), and the numeric score sits
directly above it. In Windows Terminal you get a solid bar tinted green,
amber, or red by band.

### UI layout

Rendering lives in `src/cynthia/ui/doctor.py`, using the shared
`ui/theme.py` palette so it matches the welcome screen, dashboard, and
focus panel.

- One **centered** column, capped at 92 columns, so it stays readable on an
  ultrawide terminal instead of stretching edge to edge.
- Thin, muted panel borders; only the header (purple) and summary (cyan) are
  accented, which keeps the eye moving down the page.
- The three fact panels sit side by side down to 78 columns and **stack**
  below that. Labels are marked no-wrap so they stay on one line, and long
  values ellipsize rather than squeezing the label out.
- Commit ages compress to `4d ago`, because a three-column layout has no room
  for `4 days ago`. The report carries both forms, so `cynthia status` keeps
  the long phrasing.

### Error handling

Only an unknown project stops the command. Everything else is reported
inside the report, because a partially-answerable question still deserves an
answer:

| Situation | Behaviour |
|-----------|-----------|
| Project name not registered | `Error: No project named 'x'. Try 'cynthia list'.`, exit code 1 |
| No projects registered at all | `Error: No projects registered yet. Try 'cynthia add <path>'.`, exit code 1 |
| Workspace not initialized | `Error: No CYNTHIA workspace found. Run 'cynthia init' first.`, exit code 1 |
| Git not installed | Repository panel says so; warning on the report; score/scan unaffected |
| Not a git repository | Repository panel says so; summary notes history is unavailable |
| Empty project directory | `"Project directory looks empty — there is nothing to analyze yet."` |
| Project path deleted from disk | Warning `project path no longer exists on disk`; report still renders |
| Corrupted / unreadable event log | Warning `event history unavailable (...)`; health and git sections still render |
| Corrupted workspace database | Friendly error naming `~/.cynthia/workspace.db`, exit code 1 — never a traceback |

### Flow

```text
  cynthia doctor [name]
       │
       ▼
  workspace.resolve_project_or_recent(name)     # active → most recent
       │
       ▼
  health.build_health_report(project_id)
       │
       ├─ scanner.scan_project()                # files, languages, TODO/FIXME, README, tests
       ├─ git_observer.read_git_info()           # branch, commits, authors, 7-day buckets
       ├─ health.compute_health()                # 0–100 score + penalty reasons
       ├─ storage.recent_events()                # churn from the watcher's event log
       │     └─ fallback: git_observer.file_change_counts()
       └─ health.summarize()                     # rule-based verdict, no LLM
       │
       ▼
  ui/doctor.render_doctor()                      # centered Rich panels + tables + bar
```

### Related files

| File | Role |
|------|------|
| `src/cynthia/health.py` | `build_health_report()`, `summarize()`, `score_band()`, the report dataclasses |
| `src/cynthia/ui/doctor.py` | `render_doctor()` — panels, fact grids, churn table, score bar |
| `src/cynthia/git_observer.py` | `file_change_counts()` — per-file churn from recent commits |
| `src/cynthia/scanner.py` | `count_files_modified()` — the `mtime` activity fallback |
| `src/cynthia/workspace.py` | `resolve_project_or_recent()` — active-or-most-recent resolution |
| `src/cynthia/cli.py` / `shell.py` | The `doctor` command in both front ends |
| `tests/test_doctor.py` | Score range, summary rules, churn ranking, every error path |

## Workspace overview (`cynthia overview`)

`cynthia overview` answers a different question from `doctor`: **how do all
my projects look side by side?** One summary strip and one table — health,
activity level, last change, and branch for every registered project,
sorted by most recent activity.

Where `doctor` goes deep on a single project, `overview` stays wide. It is
also a *reader*: it reuses `workspace.snapshot`, `timeline.build_activity_series`,
and `health.score_band` rather than inventing a second health formula.

### Commands

```bash
cynthia overview
```

```powershell
cd "path\to\cynthia"
.\.venv\Scripts\Activate.ps1
cynthia overview
```

Inside the interactive shell:

```text
> overview
```

No arguments: the command always loads **every** project in the workspace.
An empty workspace prints a friendly nudge instead of an empty table:

```text
No projects registered yet. Try 'cynthia add <path>'.
```

### What it shows

**Summary panel (top)**

| Stat | Meaning |
|------|---------|
| Projects | Count of registered projects |
| Healthy | Projects with health score ≥ 90 (green band) |
| Warning | Projects below 90 (yellow **or** red) |
| Most active | Project with the highest 7-day activity total (ties break on most recent change) |

**Table (one row per project)**

| Column | Contents | Source |
|--------|----------|--------|
| Project | Registered name | `projects` table |
| Health | 0–100 score with color badge | `workspace.snapshot` → `compute_health` + `score_band` |
| Activity | High / Medium / Low | `timeline.build_activity_series` total over 7 days |
| Last Change | Relative time (`2 minutes ago`, …) | Latest of watcher file-event or git commit; falls back to `last_opened` |
| Branch | Active branch, or `—` if not a git repo | `git_observer.read_git_info` via the snapshot |

### Health color badges

Same 90 / 70 bands as `cynthia doctor`, so the two screens never disagree
about whether a score is green, yellow, or red:

| Band | Score | Color |
|------|-------|-------|
| Healthy | 90–100 | green (`theme.SUCCESS`) |
| Warning | 70–89 | amber (`theme.WARNING`) |
| Critical | 0–69 | red (`theme.CRITICAL`) |

### Activity levels

The 7-day activity total (commits by weekday **plus** watcher file events)
is mapped to a short label:

| Level | 7-day activity total |
|-------|----------------------|
| High | 10 or more |
| Medium | 3 to 9 |
| Low | 0 to 2 |

Thresholds live in `overview.ACTIVITY_HIGH` / `ACTIVITY_MEDIUM` so the CLI,
shell, and tests share one definition.

### Sorting

Rows are sorted **most recently active first**:

1. `last_change_at` descending (git commit or watcher event)
2. then 7-day `activity_total` descending
3. then project name (stable tie-break)

That is why a quiet project you touched this morning still ranks above a
busier one that has been idle for a week.

### Example output

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                         CYNTHIA · Workspace Overview                         │
│                                                                              │
│    Projects     Healthy     Warning                Most active               │
│       2            1           1           Chefona AI Cooking Assistant      │
└──────────────────────────────────────────────────────────────────────────────┘

   ┌─────────────────────────────┬────────┬──────────┬─────────────┬───────┐
   │Project                      │ Health │ Activity │ Last Change │ Branch│
   ├─────────────────────────────┼────────┼──────────┼─────────────┼───────┤
   │Chefona AI Cooking Assistant │    85% │   Low    │  3 days ago │ —     │
   │WEB-pawsphere                │    90% │   Low    │  8 days ago │ main  │
   └─────────────────────────────┴────────┴──────────┴─────────────┴───────┘
     Health: 90+ green · 70–89 yellow · below 70 red   ·   Sorted by most
                                recent activity
```

In this capture, WEB-pawsphere is green (90%) and Chefona is amber (85%),
so Healthy = 1 and Warning = 1. Branch shows `—` when the project is not a
git repository. Colors are stripped when output is piped; in a real terminal
the health percentages are tinted green / amber / red.

### UI layout

Rendering lives in `src/cynthia/ui/overview.py`, using the shared
`ui/theme.py` palette:

- Centered summary panel with a purple border (`theme.PRIMARY`)
- Rounded Rich table with muted borders — one row per project
- Caption under the table reminding readers of the 90 / 70 legend and the
  sort order
- Activity labels colored High → green, Medium → amber, Low → muted

### Flow

```text
  cynthia overview
       │
       ▼
  workspace.list_projects()
       │
       ▼  (for each project)
  workspace.snapshot(project)              # scan + git + compute_health
  timeline.build_activity_series(...)      # 7-day commits + watcher events
  health.score_band(score)                 # green / yellow / red
  storage.latest_event_at(...)             # last watcher touch
       │
       ▼
  sort by last_change_at, activity_total
       │
       ▼
  ui/overview.render_overview()            # summary panel + table
```

### Related files

| File | Role |
|------|------|
| `src/cynthia/overview.py` | `build_workspace_overview()`, activity labels, row/summary dataclasses |
| `src/cynthia/ui/overview.py` | `render_overview()`, health badges, summary panel + table |
| `src/cynthia/workspace.py` | `list_projects()`, `snapshot()` — health + git for each row |
| `src/cynthia/timeline.py` | `build_activity_series()` — 7-day activity total |
| `src/cynthia/health.py` | `score_band()` — shared green / yellow / red thresholds |
| `src/cynthia/storage.py` | `latest_event_at()` — last file-event timestamp |
| `src/cynthia/cli.py` / `shell.py` | The `overview` command in both front ends |
| `tests/test_overview.py` | Empty workspace, multiple projects, sort order, color thresholds |

### When to use overview vs doctor vs status

| Command | Scope | Best for |
|---------|-------|----------|
| `cynthia overview` | All projects | “Which project needs attention today?” |
| `cynthia doctor [name]` | One project | Full diagnostic + churn risk + verdict |
| `cynthia status [name]` | One project | Languages, commit history, 7-day chart |

## Focus sessions

A **session** is a bounded stretch of work on one project. Both the
interactive shell and the CLI write to the same `sessions` table (which
also feeds `sessions analyze`).

For the full walkthrough of **automatic** recording inside the interactive
shell (watcher, flow, and step-by-step commands), see
[Auto session recording (interactive shell)](#auto-session-recording-interactive-shell).

### Explicit CLI recording

Outside the shell (each command is a separate process — no live watcher):

1. **`cynthia focus start [project]`** — snapshots start time, git commit
   count, and TODO count into workspace metadata.
2. **`cynthia focus stop`** — re-scans, diffs against the snapshot, and
   stores a row (files modified via mtime walk when no watcher is attached).

Sessions shorter than **1 minute** are discarded:
`Session too short to record.`

### Listing and analysis

1. **`cynthia sessions [project]`** — lists recorded sessions.
2. **`cynthia sessions analyze [project|--all]`** — runs K-Means
   (`n_clusters=4`) on standardized session features and reports a
   percentage breakdown of work modes.
3. **`cynthia focus`** — same clustering with the centered Rich bar panel
   (see [Focus analysis (K-Means work modes)](#focus-analysis-k-means-work-modes)).
4. **`cynthia similar`** — top historical sessions like the current one
   (see [Similar sessions (k-NN)](#similar-sessions-k-nn)).

```
╭─ CYNTHIA · Focus Analysis ─────────────╮
│ Feature Development        52%         │
│ Bug Fixing                 31%         │
│ Refactoring                 12%        │
│ Documentation                5%        │
╰─────────────────────────────────────────╯
```

Analyze needs **at least 8 sessions**. With fewer, CYNTHIA prints a guard
message instead of clustering:

```text
Not enough sessions yet to analyze focus patterns (need 8+, have N).
```

Cluster labels are assigned with post-hoc centroid heuristics (Feature
Development / Bug Fixing / Refactoring / Documentation). Percentages are
rounded so they always sum to **100**.

## Auto session recording (interactive shell)

CYNTHIA can record a work session **automatically** while you use the
interactive shell. Opening a project starts a real session backed by your
local project files and Git history — not mock data. Events feed the same
`sessions` table used by `cynthia sessions` and `cynthia sessions analyze`.

Unlike CLI `focus start` / `focus stop` (separate processes, no live
watcher), the shell stays open, so a file watcher can count files you
actually touch.

### Flow

```text
  cynthia                          # start interactive shell
       │
       ▼
  project open / status            # open or switch active project
       │
       ├─ snapshot: start time, commit count, TODO count
       └─ start file watcher (unique paths touched)
       │
       ▼
  edit / save files                # work for ≥ 1 minute
       │
       ▼
  switch project  OR  exit / Ctrl+C  OR  focus stop
       │
       ├─ stop watcher
       ├─ compute metrics from real git + scan data
       └─ insert row into sessions table
```

### Step-by-step

```powershell
cd "path\to\cynthia"
.\.venv\Scripts\Activate.ps1
cynthia list                       # optional: see registered projects
cynthia                            # enter the interactive shell
```

Inside the shell:

```text
> project open "Your Project Name"
# You should see a dim line: Recording focus session for ...
# Edit and save files in that project for at least 1 minute

> sessions                         # list sessions recorded so far
> exit                             # finalizes the active session
```

After exit (or from another terminal):

```powershell
cynthia sessions                   # table of recorded sessions
cynthia sessions analyze           # work-mode % (needs 8+ sessions)
```

If the shell starts and you already have an **active project**, recording
begins for that project automatically.

### When a session ends

| Trigger | What happens |
|---------|----------------|
| `project open` / `status` switches to another project | Previous session finalized; new one starts |
| `remove` of the active / tracked project | Session finalized |
| `exit`, `quit`, Ctrl+C, or EOF | Session finalized; watcher stopped |
| `focus stop` | Watcher stopped; session finalized via the shared path |

### What gets stored

| Field | Source |
|-------|--------|
| `duration_minutes` | `(ended_at - started_at) / 60` |
| `files_modified` | Unique file paths from the live watcher |
| `commits` | Git commits authored in the session time window (falls back to commit-count delta) |
| `lines_added` / `lines_deleted` | `git log --numstat` in the window **plus** uncommitted `git diff --numstat` |
| `todo_changes` | Absolute change in TODO/FIXME/HACK/XXX count from the scanner |

### Guards

- Sessions shorter than **1 minute** are discarded (quiet skip on quick
  project switches; no noisy error in the shell).
- Only **one** active session snapshot at a time (opening another project
  or running `focus start` rotates cleanly).

### Related commands

| Command | Role |
|---------|------|
| `project open <path-or-name>` | Open project and start auto recording |
| `sessions` / `cynthia sessions` | List stored sessions |
| `sessions analyze` | K-Means work-mode breakdown (8+ sessions) |
| `focus start` / `focus stop` | Explicit control inside the shell, or CLI-only recording outside it — see [Focus sessions](#focus-sessions) |

## Focus analysis (K-Means work modes)

CYNTHIA classifies recorded focus sessions into four work modes using
**scikit-learn K-Means** over **real session metrics** (never mock data).
The model lives in `src/cynthia/ml/kmeans_focus.py` and is shared by
`cynthia focus`, `cynthia sessions analyze`, and the interactive shell.

### Input features

| Feature | Meaning |
|---------|---------|
| `files_modified` | Files touched in the session |
| `commits` | Commits in the session window |
| `lines_added` | Lines added (git numstat + uncommitted diff) |
| `lines_deleted` | Lines deleted |
| `duration_minutes` | How long the session lasted |
| `todo_changes` | Absolute change in TODO/FIXME markers |

Features are standardized with `StandardScaler`, then clustered with
`KMeans(n_clusters=4, n_init=10, random_state=42)`.

### Cluster → label mapping (heuristics)

K-Means only produces unlabeled clusters (0–3). Labels are assigned from
each cluster’s centroid:

| Label | Heuristic |
|-------|-----------|
| Feature Development | Highest `lines_added + files_modified` |
| Refactoring | Highest `lines_deleted / max(lines_added, 1)` |
| Bug Fixing | Highest `todo_changes` |
| Documentation | Remaining (lowest-activity) cluster |

Percentages use largest-remainder rounding so they **always sum to 100**.

### Commands

```powershell
cd "path\to\cynthia"
.\.venv\Scripts\Activate.ps1

cynthia focus              # Rich panel for the active project (or all if none)
cynthia focus --all        # cluster sessions from every project
cynthia sessions analyze   # same clustering via the sessions command
```

Inside the interactive shell:

```text
> focus                    # same K-Means breakdown panel
> sessions analyze
```

You need **at least 8 recorded sessions**. With fewer:

```text
Not enough sessions yet to analyze focus patterns (need 8+, have N).
```

### UI (Gemini-style panel)

`cynthia focus` renders a **centered** Rich panel using the purple / pink /
blue theme (`ui/theme.py`), with progress-style bars and a footer:

```text
╭──────────── CYNTHIA · Focus ────────────╮
│                                         │
│         Work-mode breakdown             │
│                                         │
│  Feature Development  ████████████  52% │
│  Bug Fixing           ████████░░░░  31% │
│  Refactoring          ███░░░░░░░░░  12% │
│  Documentation        █░░░░░░░░░░░   5% │
│                                         │
│  Detected automatically using K-Means   │
│  clustering over real session metrics.  │
│                                         │
╰─────────────────────────────────────────╯
```

### Flow

```text
  recorded sessions (SQLite)
           │
           ▼
  load metrics → StandardScaler → KMeans (k=4)
           │
           ▼
  map centroids → Feature / Bug / Refactor / Docs
           │
           ▼
  save cluster_label on each session row
           │
           ▼
  Rich panel: bars + percentages + footer
```

### Related files

| File | Role |
|------|------|
| `src/cynthia/ml/kmeans_focus.py` | Clustering + heuristic labeling |
| `src/cynthia/ui/focus.py` | Centered panel, bars, footer |
| `src/cynthia/sessions.py` | Loads sessions and calls the ML module |
| `tests/test_kmeans_focus.py` | Guard + 4-label / sum-to-100 tests |

## Similar sessions (k-NN)

CYNTHIA can find historical focus sessions that look like your **current**
work using **k-nearest neighbors** (`sklearn.neighbors.NearestNeighbors`)
on the **same 6-D feature vector** as K-Means. Logic lives in
`src/cynthia/ml/knn_similar.py`; the Rich table lives in `ui/focus.py`.

### Feature vector (shared)

Shared with K-Means via `src/cynthia/ml/features.py`:

| Feature | Meaning |
|---------|---------|
| `files_modified` | Files touched in the session |
| `commits` | Commits in the session window |
| `lines_added` | Lines added |
| `lines_deleted` | Lines deleted |
| `duration_minutes` | Session length |
| `todo_changes` | Absolute TODO/FIXME change |

Features are standardized, then compared with **Euclidean** distance.

### Similarity score

```text
similarity% = 100 / (1 + distance)
```

Distance `0` → `100%`. Larger distance → score approaches `0`. Scores are
shown on a **0–100** scale (inverse-distance, not a probability).

### Query source

`cynthia similar` builds the query from the **active project** automatically:

1. **Prefer** the in-progress focus snapshot (live metrics: duration so far,
   watcher/mtime files, git commits/lines, TODO delta).
2. If no snapshot is active, **fall back** to the latest stored session for
   the active project (that session is excluded from the neighbor list).

In the interactive shell, when a watcher is running, unique file paths from
the watcher are passed into the live metrics.

### Commands

```powershell
cd "path\to\cynthia"
.\.venv\Scripts\Activate.ps1

cynthia similar          # top 3 similar historical sessions
cynthia similar -k 5     # top 5
```

Inside the interactive shell (uses the currently active project):

```text
> project open "Your Project Name"
# work for a bit (optional: keep the auto session running)
> similar                # top 3
> similar 5              # top 5
> focus                  # K-Means breakdown (related)
```

### Example output

```text
                         Similar Sessions
┏━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━┓
┃ Session ID ┃ Similarity % ┃ Duration ┃ Files modified ┃ Commits ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━┩
│         12 │        87.3% │    42.0m │             18 │       3 │
│          7 │        71.1% │    35.5m │             14 │       2 │
│          3 │        54.2% │    28.0m │             11 │       1 │
└────────────┴──────────────┴──────────┴────────────────┴─────────┘
              Query: active snapshot
  Ranked by Euclidean k-NN on standardized session metrics.
```

### Flow

```text
  active snapshot  OR  latest stored session
           │
           ▼
  6-D feature vector (ml/features.py)
           │
           ▼
  StandardScaler + NearestNeighbors (k=3, Euclidean)
           │
           ▼
  similarity% = 100 / (1 + distance)
           │
           ▼
  Rich table: id, similarity, duration, files, commits
```

### Guards

- No historical sessions for the project → clear message, no crash.
- Fewer than `k` candidates → returns as many neighbors as exist.
- When the query is a stored session, that id is **excluded** from matches.

### Related files

| File | Role |
|------|------|
| `src/cynthia/ml/features.py` | Shared feature vector for K-Means and k-NN |
| `src/cynthia/ml/knn_similar.py` | NearestNeighbors + similarity scoring |
| `src/cynthia/sessions.py` | `similar_to_active_session()` / live metrics |
| `src/cynthia/ui/focus.py` | `render_similar_table()` |
| `tests/test_knn_similar.py` | Distance score, top-k, exclude-id, empty history |

## How it's organized

### Repository layout

```text
cynthia/
├─ pyproject.toml          # packaging metadata: deps, entry point, license, classifiers
├─ LICENSE                 # MIT text; bundled into the wheel automatically
├─ README.md               # this file — also the PyPI long description
├─ .gitignore              # caches, .venv, build artifacts, local workspace db
├─ src/
│  └─ cynthia/             # import package (shipped as the `cynthia-cli` distribution)
│     ├─ __init__.py       # __version__ — single source of truth
│     ├─ cli.py            # Typer app: every command, plus --version
│     ├─ shell.py          # interactive REPL front end
│     ├─ config.py         # ~/.cynthia paths + Settings (CYNTHIA_HOME override)
│     ├─ storage.py        # SQLite: projects, events, sessions, meta
│     ├─ workspace.py      # registers/resolves projects, builds snapshots
│     ├─ scanner.py        # filesystem walk: files, languages, TODOs, mtime counts
│     ├─ git_observer.py   # read-only GitPython: branch, commits, per-file churn
│     ├─ watcher.py        # watchdog observer, one per project
│     ├─ events.py         # asyncio pub/sub bridging watcher threads to storage
│     ├─ health.py         # 0–100 score + the full doctor report
│     ├─ overview.py       # multi-project overview rows + summary stats
│     ├─ timeline.py       # 7-day activity series
│     ├─ sessions.py       # focus snapshot/finalize + analysis entry points
│     ├─ ml/               # scikit-learn: shared features, K-Means, k-NN
│     └─ ui/               # Rich rendering, one module per screen
└─ tests/                  # pytest suite, one file per subsystem
```

The `src/` layout is deliberate: because the package isn't importable from
the repository root, `pytest` and `cynthia` always exercise the **installed**
copy rather than accidentally picking up the working tree. That's why
`pyproject.toml` sets `[tool.setuptools.packages.find] where = ["src"]`.

### Module map

Each module in the brief maps to one file, so it's easy to find (and
extend) any single piece of behaviour:

| Brief's "Core Module" | File | Responsibility |
|---|---|---|
| Workspace Manager | `workspace.py` | Registers/resolves projects, wires everything together |
| Project Scanner | `scanner.py` | Walks the directory: file counts, language %, TODO/FIXME, size |
| Git Observer | `git_observer.py` | Read-only GitPython wrapper: branch, commits, contributors |
| File Watcher | `watcher.py` | `watchdog`-based real-time filesystem observation |
| Event Bus | `events.py` | asyncio pub/sub bridging the watcher (its own thread) to storage |
| Storage Layer | `storage.py` | SQLite: projects, event log, sessions, workspace metadata |
| Health Engine | `health.py` | Turns scan + git data into a 0–100 score, and assembles the full `doctor` report |
| Workspace Overview | `overview.py` | Multi-project table: health badges, activity levels, last change, branch |
| Timeline Engine | `timeline.py` | Builds the 7-day activity series from commits + watched events |
| Focus Sessions | `sessions.py` | Snapshot start/stop metrics + K-Means work-mode analysis |
| Focus ML | `ml/kmeans_focus.py` | StandardScaler + KMeans (k=4) and work-mode label heuristics |
| Similar ML | `ml/knn_similar.py` | Euclidean k-NN over session metrics + inverse-distance % |
| ML features | `ml/features.py` | Shared 6-D feature vector for K-Means and k-NN |
| Terminal UI | `ui/` | Rich rendering: gradient logo, welcome screen, dashboard, focus panel, doctor report, overview table |

`cli.py` (Typer commands) and `shell.py` (the interactive REPL) are both
thin front ends over the same `workspace`/`ui` functions, so they never
drift out of sync with each other. Every command reachable from one is
reachable from the other — including `doctor` and `overview`, which appear
in `cynthia --help` and in the shell's `help` table.

### Two health types, one score

`health.py` exposes two dataclasses, and the distinction is worth knowing
before reading the code:

| Type | Returned by | Contains |
|------|-------------|----------|
| `HealthScore` | `compute_health()` | Just the verdict: score, status, coverage, penalty reasons |
| `HealthReport` | `build_health_report()` | The whole `doctor` payload: a score *plus* repository, quality, activity, risk, and summary sections |

`status` needs only the first; `doctor` needs the second. Keeping them
separate means the dashboard doesn't pay for churn analysis it never shows.

### Shared helpers, single implementation

Two functions moved so that `doctor` could reuse them instead of copying
them — worth knowing if you're looking for where they used to be:

| Function | Now lives in | Also used by |
|----------|--------------|--------------|
| `count_files_modified()` | `scanner.py` (filesystem walking belongs there) | `sessions.py` re-exports it, so focus sessions are unchanged |
| `file_change_counts()` | `git_observer.py` (new) | `doctor`'s risk fallback |

## Notes on the numbers

- **Health %** is computed transparently from real signals: unresolved
  TODO/FIXME markers, a missing README, a missing tests directory, and
  stale git history. Run `cynthia status` and check `report.reasons` in
  code (or extend the UI to print them) to see exactly why a score is
  what it is.
- **Tests %** is only ever shown when a real `coverage.xml` (Cobertura
  format — what `pytest --cov --cov-report=xml` produces) is found in
  the project root. Otherwise it honestly shows `N/A` rather than
  guessing.
- **Issues** is the count of TODO/FIXME/HACK/XXX markers found in source
  files — matching the brief's "extracts TODO/FIXME comments" rather
  than a GitHub Issues integration (CYNTHIA is local-first and doesn't
  call out to any API).
- **Activity (7D)** combines git commit dates with any live file-change
  events CYNTHIA has logged while `cynthia watch` was running. A
  never-watched project still shows accurate activity — just from
  commits alone.
- **Focus metrics** at stop time: duration; files modified (watcher
  unique paths in the shell, or `mtime` walk for CLI `focus stop`);
  commits in the session window; `git log --numstat` plus uncommitted
  `git diff --numstat` line totals; absolute TODO-count change.
- **`doctor` / `overview` bands vs. `status` labels** are two different
  readings of the *same* score. `status` says healthy / warning / critical at
  80 and 50; `doctor` and `overview` color green / amber / red at 90 and 70.
  Nothing is recomputed — they share `health.score_band()`. In the overview
  summary strip, **Warning** counts every project below 90 (yellow *and* red)
  so the headline stays to four stats.
- **`overview` activity levels** are absolute on the 7-day timeline total
  (High ≥ 10, Medium ≥ 3, Low otherwise). A brand-new workspace can show
  every row as Low until you watch or commit — that is expected, not a bug.
- **`doctor`'s TODO and FIXME counters** count those two tags literally, so
  `HACK` and `XXX` markers appear in neither column even though they do lower
  the score and do show under **Issues** on the `status` dashboard.
- **"Files changed" from `mtime`** measures the working tree, not authorship.
  A freshly cloned repository legitimately reports every file as changed,
  because cloning wrote them all moments ago. The panel always names its
  source (`watcher events` vs `file timestamps`) so the number is never
  ambiguous — watch a project for a while and it becomes precise.
- **The two 7-day windows differ slightly by design.** Commit counts reuse
  the Git Observer's weekday buckets, which start at midnight seven calendar
  days back; churn from the event log uses a rolling 168 hours. Aligning them
  would mean either a second `git log` pass or coarser event data, for a
  difference smaller than the signal itself.

## Try it against a real repo

```bash
cynthia init
cynthia add /path/to/any/git/repo          # local folder
cynthia add https://github.com/OWNER/REPO  # clone-and-register (needs Git)
cynthia status <repo-name>
cynthia doctor <repo-name>                 # diagnostic + verdict
cynthia overview                           # all projects at a glance
```

On a repo you've never watched, `doctor`'s risk table falls back to git
history, so it has something real to show immediately. After two or more
projects are registered, `cynthia overview` is the fastest way to compare
them.

## Manual testing (doctor)

The risk table's primary source is the watcher's event log, so verifying it
end to end means watching a project while you change files. Use an isolated
workspace via `CYNTHIA_HOME` so your real `~/.cynthia` is untouched:

```powershell
$T = "$env:TEMP\cynthia-doctor-demo"
$env:CYNTHIA_HOME = "$T\home"

cynthia init demo
cynthia add "path\to\some\git\repo"
```

In one terminal, start watching:

```powershell
cynthia watch <project-name>        # leave running; Ctrl+C to stop
```

In a second terminal, make a few edits — more to one file than the others,
so the ranking is obvious:

```powershell
Add-Content "path\to\repo\index.html" "<!-- edit -->"   # repeat 4x
Add-Content "path\to\repo\README.md" "note"            # once
```

Stop the watcher, then run the report:

```powershell
cynthia doctor <project-name>
```

| Check | Pass if |
|-------|---------|
| Risk source | Footer reads `Source: watcher events (last 7 days)` |
| Risk ranking | The file you edited most sits on top with the right count |
| Activity | `Measured via watcher events`, and `Most modified` matches row 1 |
| Summary | One to three sentences, no placeholder text |
| Repository | Branch, commit count, and `Tree: modified` reflect your edits |

Then clean up:

```powershell
Remove-Item -Recurse -Force "$env:TEMP\cynthia-doctor-demo"
Remove-Item Env:CYNTHIA_HOME
```

**Degraded paths worth exercising**, none of which should ever produce a
traceback:

```powershell
cynthia doctor no-such-project     # -> Error: No project named '...'
cynthia doctor                     # in a fresh shell: falls back to most recent project
cynthia add "path\to\empty\folder" # then doctor it -> "Project directory looks empty"
```

## Manual testing (focus sessions)

Use these steps to verify focus tracking by hand (PowerShell example):

```powershell
cd "path\to\cynthia"
.\.venv\Scripts\Activate.ps1
git --version

cynthia list
cynthia focus start "Your Project Name"
```

Then edit and save a file in that project, wait **at least 1 minute**, and:

```powershell
cynthia focus stop
cynthia sessions
```

**Too-short guard** (stop immediately after start):

```powershell
cynthia focus start "Your Project Name"
cynthia focus stop
# Expect: Session too short to record.  (no new row in `cynthia sessions`)
```

**Analyze guard** (fewer than 8 sessions):

```powershell
cynthia sessions analyze
cynthia sessions analyze --all
# Expect: Not enough sessions yet to analyze focus patterns (need 8+, have N).
```

**Interactive shell:**

```powershell
cynthia
```

```text
> help
> focus start "Your Project Name"
> focus stop
> sessions
> sessions analyze
> exit
```

| Step | Command | Pass if |
|------|---------|---------|
| Start | `cynthia focus start ...` | Confirmation printed |
| Short stop | `focus stop` immediately | “too short”, no new session |
| Real stop | wait 1+ min, `focus stop` | Session recorded |
| List | `cynthia sessions` | Table shows sessions |
| Analyze early | `cynthia sessions analyze` | Guard message, no traceback |
| Unit tests | `pytest tests/ -v` | All green |

Clustering with real percentages needs **8+ recorded sessions** (≥1 min each).
For clustering math without waiting, run the automated tests below.

## Running the test suite

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

50 tests, no network, no fixtures on your real machine — every test that
needs a workspace points `CYNTHIA_HOME` at a `tmp_path`, and git facts are
stubbed where a result would otherwise depend on whether git happens to be
installed on the runner.

| File | Covers |
|------|--------|
| `tests/test_version.py` | `get_version()` is a non-empty semantic version, matches `cynthia.__version__`, and both `--version` / `-v` print the banner |
| `tests/test_doctor.py` | Score stays in 0–100, summary is non-empty, churn ranking and 5-file cap, plus every degraded path: no git, empty project, deleted path, unreadable event log, unknown project |
| `tests/test_overview.py` | Empty workspace, multiple projects, sort-by-activity, health color thresholds (90 / 70) |
| `tests/test_health.py` | Score penalties, TODO capping, coverage reported only when real |
| `tests/test_scanner.py` | File/language counts, TODO extraction, ignore rules |
| `tests/test_sessions.py` | Metric diffing, too-short discard, analyze guard, percentages summing to 100 |
| `tests/test_kmeans_focus.py` | Clustering guard and the 4-label / sum-to-100 contract |
| `tests/test_knn_similar.py` | Distance scoring, top-k, exclude-id, empty history |

Run a single area while iterating:

```bash
pytest tests/test_doctor.py -v
pytest tests/test_overview.py -v
pytest tests/test_version.py -v
```

## Packaging and release

The project is set up for a public GitHub and PyPI release.

```bash
pip install build twine
python -m build            # writes dist/*.whl and dist/*.tar.gz
twine check dist/*         # validates metadata + README rendering on PyPI
```

```text
Successfully built cynthia_cli-0.1.0.tar.gz and cynthia_cli-0.1.0-py3-none-any.whl
Checking dist\cynthia_cli-0.1.0-py3-none-any.whl: PASSED
Checking dist\cynthia_cli-0.1.0.tar.gz: PASSED
```

Publish to TestPyPI first, then the real index:

```bash
twine upload --repository testpypi dist/*
pip install --index-url https://test.pypi.org/simple/ cynthia-cli
```

Clear `dist/` before rebuilding at a new version, or `twine upload` will try
to re-upload the old artifacts.

### Metadata choices

| Field | Value | Reason |
|-------|-------|--------|
| `name` | `cynthia-cli` | Distribution name; the command and import package stay `cynthia` |
| `license` | `"MIT"` (SPDX string) | PEP 639 form. The older `{ text = "MIT" }` table and the `License :: OSI Approved ::` classifier are both deprecated and stop working after 2027-02-18 |
| `requires = ["setuptools>=77.0"]` | build backend floor | SPDX license expressions are only understood from 77.0 onward; an older backend would reject `license = "MIT"` |
| `readme` | `README.md` | Becomes the PyPI long description — which is why `twine check` validates this file |
| `requires-python` | `>=3.10` | Uses `X | Y` type unions and `tomllib` |
| `classifiers` | Alpha, Developers, Console, Version Control, Utilities | Drives PyPI search and the sidebar |
| `[project.urls]` | Homepage + Repository | Renders the sidebar links on PyPI |

`LICENSE` is not listed explicitly anywhere: setuptools discovers it and
records `License-File: LICENSE`, placing it at
`cynthia_cli-0.1.0.dist-info/licenses/LICENSE` inside the wheel.

The version lives in two places on purpose — `__init__.py` for runtime and
`pyproject.toml` for packaging (build tools read metadata without importing
the package). `tests/test_version.py` asserts they agree, so they can't
silently drift.

## Configuration

Settings live in `~/.cynthia/config.toml` (edit directly, or extend the
CLI with a `cynthia config` command). Currently configurable:

- `workspace_name` — cosmetic label shown in the shell footer
- `activity_window_days` — size of the activity window (default 7)
- `ignored_dirs` — directories the Scanner/Watcher never descend into

Set `CYNTHIA_HOME` to point the whole workspace somewhere other than
`~/.cynthia` (handy for tests, or for keeping multiple isolated
workspaces).

## Roadmap (from the project brief)

The current build covers sections 1–13 of the brief end-to-end
(multi-project workspace, event-driven scanning, health scoring, the
Gemini-inspired terminal UI), plus focus sessions with K-Means work-mode
analysis, the `doctor` diagnostic with rule-based summaries, the multi-project
`overview` dashboard, and packaging metadata ready for PyPI. Section 14's
future scope — AI recommendations,
semantic search, cloud sync, VS Code integration, team workspaces,
dependency graphs — is intentionally left for later; the module boundaries
above (especially the Event Bus and Storage Layer) were built to make those
additions straightforward rather than requiring a rewrite.

The `doctor` summary is a good example of that boundary paying off: it is
deliberately rule-based today, so swapping in a model later means replacing
one function (`health.summarize()`) rather than touching the CLI, the
renderer, or the data layer.

## License

[MIT](LICENSE) © Fardin Hasan Siam.
