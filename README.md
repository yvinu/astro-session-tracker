# Astro Session Tracker (FITS/XISF Inventory)

A local-first tool for astrophotographers to track a growing FITS/XISF image library: an incremental SQLite scanner, RA/DEC-based target-group clustering, session derivation, duplicate detection across drives, and a live browser dashboard — all running on your own machine, no accounts or cloud services involved.

The project has two parts:

- **`astro_tracker`** (current, primary tool) — an incremental scanner backed by SQLite, a local API server, and a live dashboard. This is what the rest of this README documents.
- **`FITS_Analysis.py`** (legacy) — the original one-shot CLI that scans a directory and dumps a flat CSV. Still works, but has no memory between runs and none of the grouping/dedup features below. See [Legacy one-shot scanner](#legacy-one-shot-scanner).

## Features

- **Incremental scanning**: files are upserted into SQLite keyed on path + modification time — unchanged files are skipped on re-scans, so repeat scans of a growing library stay fast.
- **Crash-resilient**: a single file that fails to parse or write to the database is logged and skipped, not fatal to the whole scan.
- **Multi-location aware**: each file's Location (which external drive or NAS share it lives on, e.g. `/Volumes/<name>`) is tracked automatically, filterable in the dashboard.
- **Duplicate detection**: files copied across more than one drive are recognized via a metadata fingerprint (size, timestamp, exposure, target, camera) — no slow full-file hashing, so it stays fast even over a NAS on WiFi. Aggregate stats and integration-time totals count each duplicate once; a dedicated Duplicates view shows every group, and a reclaim summary (pick your canonical/NAS location) tells you how much space you'd free up per drive and exports a list of redundant file paths.
- **RA/DEC target-group clustering**: files are grouped by actual sky position (not just the `OBJECT` header string), so inconsistently- or mis-named targets are still recognized as the same project.
- **Sessions**: files are auto-derived into sessions (target group + observation night), with manual star rating / Bortle scale / notes annotations that survive re-scans.
- **Integration calculator**: total integration time and the exposure-weighted grand mean midpoint per target group, for PixInsight/Siril-style post-processing.
- **Rich filtering**: filter by category, frame type, target, filter, location, camera, resolution, binning, and optical train (scope + camera + focal length, auto-derived).
- **Multiple format support**: FITS (`.fits`, `.fit`, `.fts`) and XISF (`.xisf`, optional dependency).
- **FITS Header Analyzer & Dictionary Suite**: Analyze header field combinations across collections, detect software publishers, and standardize synonyms via an interactive dictionary and KùzuDB property graph engine.
- **FITS Studio Web App (`/studio`)**: Unified 3-tab web interface featuring folder pickers (native OS + webkit), live glowing progress bars, interactive dictionary search, and 2D property graph visualization.
- **Browser-based scan launcher**: pick a folder (native macOS picker) and run scans without touching the CLI, with live progress and cancellation.
- **CSV export** on demand, from either the CLI or the dashboard.
- **Siril export**: symlink a target group's files into a Siril-shaped working folder.

## Installation

```bash
# Core dependencies (required)
pip install -r requirements.txt

# Property Graph Engine (KùzuDB - required for dictionary graph)
pip install kuzu

# XISF support (optional but recommended)
pip install xisf
```

The script/server will run without optional libraries — fallback engines (e.g. SQLite for property graphs, skipping XISF files) are used automatically.

## Quick start

```bash
# Option A: Launch FITS Studio Web Application (3-Tab Suite)
python3 fits_dictionary_cli.py --studio

# Option B: Serve the main inventory dashboard + API server
python3 -m astro_tracker.server --db astro_inventory.db
```

Then open `http://127.0.0.1:8000`:
- **`http://127.0.0.1:8000/studio`**: FITS Studio Suite (Runner with live progress & folder pickers, Interactive Dictionary, and KùzuDB Graph Explorer).
- **`http://127.0.0.1:8000/`**: Inventory Dashboard (live stats, target groups, sessions, duplicate detection, and file table).
- **`http://127.0.0.1:8000/scan`**: Scan Launcher page.

## FITS Header Analyzer & Dictionary Suite

### 1. FITS Studio Web Application Suite (`/studio`)

The FITS Studio web suite (`fits_studio.html`) provides an interactive 3-tab application accessible via `http://127.0.0.1:8000/studio` or `python3 fits_dictionary_cli.py --studio`:

- **⚡ Tab 1: Scan & Runner**:
  - **Dual Folder Pickers**:
    - **`📁 Browse OS Folder...`**: Triggers native macOS folder picker dialogs via `/api/browse-folder` (AppleScript).
    - **`📂 Select Folder...`**: Browser-native directory selection via HTML5 `<input type="file" webkitdirectory>`.
    - **Quick Path Presets**: One-click shortcuts for `📁 AP Images` (`/Users/yvinu/Documents/AP`), `📁 FITS Workspace` (`/Users/yvinu/Automation/FITS_Report`), and `📁 External Drives` (`/Volumes/`).
  - **Live Scanner Progress Bar & Completion Banner**:
    - Animated progress bar (`0.0%` to `100.0%`) updating live every 400ms.
    - Live file counter (`processed / total files`), elapsed timer (`⏱️ MM:SS`), status badges (`⚡ RUNNING ANALYSIS`, `✅ COMPLETE`, `❌ FAILED`), and live file name indicator (`File: IMG_0042.fits`).
    - Emerald green completion notification banner detailing scanned file count and elapsed execution seconds.
    - Automatic dashboard metrics refresh (Total Image Files, Processed FITS, Field Signatures, Publishers Detected) and dynamic rendering of **Top Header Combination Signatures**.
  - **Standalone & File Protocol Support**: Works seamlessly whether accessed via HTTP or opened directly as a static file (`file:///...`), automatically resolving API requests to `http://127.0.0.1:8000`.

- **📖 Tab 2: Interactive Dictionary**:
  - Searchable mapping interface connecting canonical astronomical concepts (`exposure`, `gain`, `sensor_temp`, `target_name`, `frame_type`, `instrument`, etc.) to specific header cards (`EXPTIME`, `DET-TEMP`, `EGAIN`, `IMAGETYP`).
  - Publisher badges showing origin software writing each card variation (`ZWO ASIAIR`, `DWARFLAB`, `Seestar S50`, `N.I.N.A.`, `Siril`, `PixInsight`).

- **🌌 Tab 3: Graph Explorer**:
  - Interactive 2D property graph visualizer powered by `vis-network.js`.
  - Color-coded node rendering for Canonical Concepts (Purple), Header Cards (Cyan), and Software Publishers (Green) linked by `MAPS_TO` and `WRITTEN_BY` edges.

---

### 2. Header Analyzer Engine (`fits_header_analyzer.py`)

Scans FITS collections to answer 5 key metadata questions across drives without mutating original files:
1. **Most common field sets**: Primary header combinations present across files.
2. **Unique field combinations**: Distinct header signatures (filtered by `--min-combo-pct`).
3. **Master field list**: Complete manifest of unique header cards identified.
4. **Standardization candidates**: Competing synonym fields (e.g., `EXPTIME` vs `EXPOSURE`, `CCD-TEMP` vs `DET-TEMP`).
5. **Software publishers**: Origin software detected (`ZWO ASIAIR`, `DWARFLAB`, `Seestar S50`, `N.I.N.A.`, `Siril`, `PixInsight`).

```bash
# Run header analysis on a folder with default 1.0% signature threshold
python3 fits_header_analyzer.py -d /path/to/fits/folder --min-combo-pct 1.0
```

---

### 3. KùzuDB Property Graph & Dictionary CLI (`fits_dictionary_cli.py`)

Integrates metadata into a cumulative property graph database (`astro_fits_graph.kuzu_db`) connecting `CanonicalConcept`, `HeaderCard`, and `SoftwarePublisher` nodes via `MAPS_TO` and `WRITTEN_BY` relationships.

```bash
# Lookup canonical mapping for a header card (e.g., DET-TEMP)
python3 fits_dictionary_cli.py --lookup DET-TEMP

# Query cards written by a specific publisher (e.g., DWARFLAB)
python3 fits_dictionary_cli.py --publisher DWARFLAB

# Inspect property graph node & edge statistics
python3 fits_dictionary_cli.py --graph-stats

# Test standardized dictionary mapping on sample header dict
python3 fits_dictionary_cli.py --test '{"EXPTIME": 120, "DET-TEMP": -10, "CAMERA": "DWARF3"}'

# Launch FITS Studio Web App
python3 fits_dictionary_cli.py --studio

# Reset cumulative corpus DB & return to clean seed state
python3 fits_dictionary_cli.py --reset-corpus
```

## Usage

### Scanning (CLI)

```bash
python3 -m astro_tracker.scanner [options]
```

| Flag | Description |
|------|-------------|
| `-d, --directory` | Directory to scan (default: `/Users/yvinu/Documents/AP`). Ignored with `--cluster-only`. |
| `--db` | SQLite database path (default: `astro_inventory.db`). |
| `-e, --error-log` | Error log file name (default: `fits_analysis_errors.log`). |
| `--cluster` | Recompute RA/DEC target-group clustering, session derivation, and duplicate detection after scanning. |
| `--cluster-only` | Skip the filesystem walk entirely and just re-run clustering/sessions/duplicates against files already in the database. Implies `--cluster`. Useful for large libraries where re-walking the filesystem just to re-cluster is wasted time. |
| `--force` | Re-parse every file's header and re-write its row even when path+mtime match what's already stored. Ordinary scans should omit this — it re-reads every file. Use it once after upgrading to backfill fields (resolution, binning, optical train) that need a header re-read on files scanned before those fields existed; Location backfills itself automatically and doesn't need `--force`. |

Examples:

```bash
# Incremental scan, no clustering
python3 -m astro_tracker.scanner -d /Volumes/MyDrive/AstroPhotos --db astro_inventory.db

# Scan + full recompute (clustering, sessions, duplicates)
python3 -m astro_tracker.scanner -d /Volumes/MyDrive/AstroPhotos --db astro_inventory.db --cluster

# Re-cluster/re-dedup without touching the filesystem
python3 -m astro_tracker.scanner --db astro_inventory.db --cluster-only

# One-time backfill of Resolution/Binning/Optical Train on an existing library
python3 -m astro_tracker.scanner -d /Volumes/MyDrive/AstroPhotos --db astro_inventory.db --force --cluster
```

If you have multiple drives/shares (e.g. external drives plus a NAS), scan each one — the same database can be scanned from as many locations as you like; files are tracked per physical copy (one row per location), and duplicate detection finds copies that ended up on more than one.

### Server + dashboard

```bash
python3 -m astro_tracker.server [options]
```

| Flag | Description |
|------|-------------|
| `--db` | SQLite database path (default: `astro_inventory.db`). Also settable via the `ASTRO_TRACKER_DB` environment variable. |
| `--host` | Bind address (default: `127.0.0.1`). |
| `--port` | Port (default: `8000`). |

The server is single-user/local-only (no auth) and serves both the JSON API and the dashboard HTML from the same origin.

### CSV export

```bash
# From the CLI, against a database directly
python3 -m astro_tracker.exporter --db astro_inventory.db -o astro_inventory_report.csv

# From the dashboard: "Export CSV" exports the currently filtered view
# From the API directly: GET /api/export.csv
```

### API reference

All endpoints are served locally by `astro_tracker.server`, no auth:

| Endpoint | Description |
|----------|-------------|
| `GET /studio` | Serves FITS Studio 3-Tab Web Application Suite (`fits_studio.html`). |
| `GET /api/fits-dictionary` | Returns standard astronomical card mapping dictionary JSON. |
| `POST /api/header-analysis/start` | Starts background header analysis job across FITS collections. |
| `GET /api/header-analysis/status` | Polls live progress percentages, file counters, elapsed timer, and header signature results. |
| `POST /api/corpus/reset` | Resets cumulative KùzuDB property graph database and dictionary corpus to clean seed state. |
| `GET /api/files` | Every file record (the raw, non-deduplicated table). |
| `GET /api/stats` | Library-wide summary stats (category/frame-type/filter breakdowns, total exposure, unique targets) — each duplicate group counts once. |
| `GET /api/target-groups` | RA/DEC-clustered target groups, with integration time and mean midpoint (deduplicated). |
| `GET /api/sessions` | Auto-derived sessions (target group + night), with annotations. |
| `PUT /api/sessions/{id}/annotation` | Set a session's rating/Bortle/notes. |
| `GET /api/duplicates` | Duplicate groups with each copy's location and path. |
| `GET /api/whats-new` | Targets/subs added since the last scan run. |
| `GET /api/export.csv` | CSV export of the full file table. |
| `POST /api/scan/start`, `GET /api/scan/status`, `POST /api/scan/cancel` | Background scan job control (used by the `/scan` page). |
| `GET /api/scan/recent-directories` | Recently-used scan directories. |
| `POST /api/browse-folder` | Opens the native macOS folder picker (macOS only). |
| `POST /api/target-groups/{id}/export-siril` | Symlinks a target group's files into a Siril-shaped working folder. |

## Data model

Each file is one row in `files`, keyed by its absolute path (so the same file copied to two drives is two rows). Extracted/derived per file:

| Field | Source |
|-------|--------|
| `file_name`, `folder` | Path |
| `location` | Parsed from the path's `/Volumes/<name>` mount segment (macOS), or `Internal` for the boot volume |
| `file_category` | `Processed` (stack/starless/starmask/master filename keywords, or a Master frame type) or `Subframe` |
| `target` | `OBJECT` header |
| `date` | `DATE-OBS` header |
| `frame_type` | Normalized `IMAGETYP` (Light/Dark/Bias/Flat/Master variants/Unknown) |
| `exposure`, `gain`, `temp`, `filter`, `instrument` | `EXPTIME`/`GAIN`/`SET-TEMP`/`FILTER`/`INSTRUME` headers |
| `resolution`, `binning` | `NAXIS1`x`NAXIS2` and `XBINNING`x`YBINNING`, formatted as `WIDTHxHEIGHT` |
| `optical_train` | Derived from whichever of `TELESCOP`/`INSTRUME`/`FOCALLEN` are present, e.g. `"Celestron NexStar 8SE \| ZWO ASI294MC Pro \| 1200mm"` |
| `ra`, `dec` | `RA`/`DEC` (or `OBJCTRA`/`OBJCTDEC`) headers, used for target-group clustering |

Derived groupings (recomputed by `--cluster`/`--cluster-only`, not stored per-scan):

- **Target groups**: RA/DEC clusters (~1° tolerance, sized to a small-FOV imager), independent of the `OBJECT` label.
- **Sessions**: target group + observation night.
- **Duplicate groups**: files sharing an identical (size, date, exposure, target, instrument) fingerprint — the same capture, found at more than one Location. Aggregate stats/integration time count each group once (earliest-scanned copy); the raw file table still shows every physical copy.

## Testing

```bash
pip install -r requirements.txt  # includes pytest
pytest
```

Tests cover the scanner's incremental/crash-resilience behavior, metadata extraction and normalization, RA/DEC clustering, duplicate detection, session derivation, the integration calculator, and the scan job state machine. The storage/API layer is largely untested by design (thin repository/route code), except for a couple of targeted regression tests protecting specific bug fixes.

## Legacy one-shot scanner

```bash
python3 FITS_Analysis.py [-d DIRECTORY] [-o OUTPUT.csv] [-e ERROR_LOG]
```

Walks a directory once and writes a flat CSV — no database, no memory between runs, no clustering/sessions/duplicate detection. Kept for continuity with older workflows built around the CSV; new usage should prefer the `astro_tracker` scanner + dashboard above. The legacy `dashboard.html` CSV-upload flow it used to pair with has been replaced by the live API-backed dashboard.

## Troubleshooting

**XISF files not processing** — install the optional dependency: `pip install xisf`.

**`ModuleNotFoundError` for pandas/astropy/fastapi/uvicorn** — `pip install -r requirements.txt`.

**Empty or missing metadata** — files with incomplete headers are still included, with `Unknown`/`N/A`/`0` fallback values rather than being dropped.

**Resolution/Binning/Optical Train show blank on files scanned before this feature existed** — run a scan with `--force` once to backfill them (see [Scanning (CLI)](#scanning-cli)); Location backfills itself automatically without `--force`.

**A scan fails partway through** — check the error log (`fits_analysis_errors.log` by default) for the specific file and exception type; a single bad file no longer aborts the whole scan.

## Notes

- Metadata extraction is read-only and never modifies your image files; nothing in this tool ever deletes files (including the duplicate reclaim feature — it only tells you what to remove, you remove it yourself).
- Scanning recurses into all subdirectories.
- SQLite is the single source of truth; the CSV export is a generated view, not an input.
