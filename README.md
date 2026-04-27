<p align="center">
  <img src="./assets/icon.png" alt="KeyLife" width="180">
</p>

<h1 align="center">KeyLife</h1>

<p align="center">
  <strong>Personal keyboard usage tracker for Windows</strong><br>
  Privacy-preserving aggregate statistics — counts only, never sequences.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/platform-Windows-blue" alt="Platform">
  <img src="https://img.shields.io/badge/python-3.11+-yellow" alt="Python">
  <img src="https://img.shields.io/badge/backend-FastAPI-009688" alt="FastAPI">
  <img src="https://img.shields.io/badge/frontend-Vue%203-42b883" alt="Vue 3">
  <img src="https://img.shields.io/badge/gui-PySide6-green" alt="PySide6">
  <img src="https://img.shields.io/badge/license-MIT-lightgrey" alt="License">
</p>

---

## What it does

KeyLife runs in the background, captures keystrokes via a Win32 low-level hook,
and stores **only aggregate counts** per `(virtual_key, scancode)` bucketed by
hour and day. It never records the order in which keys were pressed, so
keystroke sequences (passwords, messages, search queries) cannot be
reconstructed from the database.

The data is exposed through a local HTTP API and visualized either in a
PySide6 desktop UI or in a Vue 3 web UI served on loopback.

## Features

| View | Description |
|------|-------------|
| **Dashboard** | Today's total, all-time total, current session, first recorded date |
| **Calendar** | Daily totals over a date range, GitHub-style activity heatmap |
| **Hourly** | Hour × day heatmap to see when you type most |
| **Keyboard** | Per-key heatmap rendered on a real Q6 HE ANSI IT layout |
| **Top keys** | Ranked list of most-pressed keys for any range |
| **Settings** | Flush interval, autostart, start-minimized, theme |

## Architecture

```
Win32 low-level hook  ──►  in-memory aggregator  ──►  SQLite (WAL)
                              │                          ▲
                              │ periodic flush           │
                              ▼                          │
                          FastAPI  ────────────►  Vue 3 web UI
                              │
                              └─────────────────►  PySide6 desktop UI
```

- **Hook** (`backend/app/hook/`): Win32 `WH_KEYBOARD_LL` callback, ignores
  auto-repeat, drops the original key sequence at the boundary.
- **Aggregator** (`backend/app/aggregator/buffer.py`): bounded in-memory
  counters with TTL anti-stale on stuck DOWN events.
- **Storage** (`backend/app/storage/`): SQLAlchemy 2 + Alembic migrations,
  SQLite in WAL mode, single-writer invariant enforced via flush lock.
- **API** (`backend/app/api/`): FastAPI on loopback only, read-only stats
  endpoints.
- **UI**: native Qt UI (`backend/app/ui/qt/`) or Vue 3 SPA (`frontend/`).

## Privacy

This is the core design constraint, not a feature.

- The aggregator only stores `(vk, scancode) → count` per hour/day.
- The live monitor UI shows only the **last** event (no timestamp, no
  history list).
- The HTTP API binds to `127.0.0.1` and never accepts remote connections.
- The DB lives under `%APPDATA%/KeyLife/` (or wherever `data_dir` is
  configured) and contains no reconstructable text.
- A per-install secret is generated at first launch in `backend/.secret_key`
  (mode `0o600`, never committed).

See `CLAUDE.md` for the full security audit log.

## Installation

### From source

```bash
git clone https://github.com/arcademman/KeyLife.git
cd KeyLife
python -m venv .venv
.venv\Scripts\activate
pip install -e .
cd frontend && npm install && npm run build && cd ..
python run.py
```

### From release

1. Download `KeyLife_Setup_<version>.exe` from
   [Releases](https://github.com/arcademman/KeyLife/releases)
2. Run the installer
3. Launch **KeyLife** from the Start Menu

## Usage

```bash
python run.py                 # Qt UI + HTTP API (default)
python run.py --serve         # headless: daemon + API + web UI on loopback
python run.py --headless      # daemon only, no UI
python run.py --minimized     # Qt UI, hidden in the tray
python run.py --monitor       # legacy Tk hook monitor (debug)
python run.py --log-level=DEBUG
```

`run.py` automatically applies pending Alembic migrations before starting.

## Build

A standalone Windows installer is produced in two steps:

```bash
pyinstaller run.spec                                  # → dist/KeyLife/
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```

Output: `installer_output/KeyLife_Setup_<version>.exe`

## Project layout

```
backend/
  app/
    hook/         # Win32 low-level keyboard hook
    aggregator/   # in-memory counters + flush
    storage/      # SQLAlchemy models, repository, session
    service/      # daemon orchestration
    api/          # FastAPI routes & schemas
    ui/qt/        # PySide6 desktop UI
    ui/monitor.py # debug monitor
  alembic/        # DB migrations
frontend/         # Vue 3 + Vite + Tailwind + ECharts
run.py            # launcher (migrations + entry point)
run.spec          # PyInstaller config
installer.iss     # Inno Setup config
```

## License

[MIT](LICENSE) © 2026 ArcademMan
