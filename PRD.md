# PRD: Astro Session Tracker (FITS_Report v2)

## Problem Statement

I run a Seestar (and potentially other) astrophotography setup and shoot subs on an ongoing basis — the image library grows daily/weekly. Today, `FITS_Analysis.py` gives me a one-shot, full-directory scan that dumps every FITS/XISF file's header metadata into a flat CSV, viewed through a standalone `dashboard.html`. Two things are missing:

1. **No memory.** Every scan re-parses every file from scratch and produces a fresh CSV with no persistent state — there's no way to ask "what's new since last time?" without re-processing everything, and nowhere to attach my own judgment (session quality, conditions, notes) since that data would just get wiped on the next scan.
2. **No sense of "session" or "target" beyond the filename.** Files are tracked individually. Two nights of subs on the same object don't get connected unless the OBJECT header string matches exactly — so a mistagged or inconsistently-named target silently fragments my actual integration time across "different" targets, and I have no easy way to spot that two file groups are actually pointed at the same patch of sky.

I want a tool that recognizes what's already been logged, quickly tells me what's new, groups my subs into meaningful sessions and true targets (by sky position, not just by label), and lets me layer my own subjective tracking on top — without losing any of that when I rescan.

## Solution

Evolve the existing FITS_Report scanner + dashboard into a persistent, incremental, single-user astro session tracker:

- The scanner becomes **incremental**: it upserts into a local SQLite database keyed on file path + modification time, so re-scans only touch new or changed files, and it can answer "what targets got new subs since my last scan?" instantly.
- Files are automatically grouped into **sessions** (same target + same night), and sessions can be manually annotated (star rating, bortle scale, notes) without those annotations being lost on the next scan.
- A new **FOV clustering** step groups files/sessions by actual RA/DEC sky position (not by OBJECT label), so mislabeled or inconsistently named targets are still recognized as the same integration project.
- An **integration calculator** computes the grand integrated mean midpoint per matched target group (for PixInsight/Siril-style post-processing workflows) and displays total integration time per group.
- A small local web server (Flask/FastAPI) sits in front of SQLite, serving both the read data and write endpoints for annotations, replacing the current CSV-upload flow.
- The existing D3.js dashboard is evolved (not replaced) to fetch live data from this local server instead of requiring a manual CSV upload, and gains new views for sessions and target groups.
- CSV export remains available on demand, generated from the database rather than being the source of truth.

This is a **single-user, local-first, desktop-only** tool — no accounts, no multi-user, no field/mobile use case, no gamification, no calendar view, no PDF/text export, and no true plate-solving in this version.

## User Stories

1. As the sole user, I want to re-scan my image library and have it finish quickly even as the library grows, so that daily/weekly scans don't become a bottleneck.
2. As the sole user, I want the scanner to skip files it has already parsed and whose modification time hasn't changed, so that re-scans only do work proportional to what's new.
3. As the sole user, I want to see which targets received new subs since my last scan, so that I can quickly check on active integration projects.
4. As the sole user, I want to see which brand-new targets were added since my last scan, so that I notice new projects without manually diffing anything.
5. As the sole user, I want every FITS/XISF file's metadata (target, date, frame type, exposure, gain, temp, filter, instrument) extracted automatically, so that I don't have to enter technical details by hand.
6. As the sole user, I want files classified as Processed or Subframe based on filename patterns, so that I can separate raw data from finished/master outputs.
7. As the sole user, I want inconsistent or malformed frame-type header values normalized into standard categories (Light, Dark, Bias, Flat, Master variants, Unknown), so that my breakdowns aren't fragmented by naming noise.
8. As the sole user, I want failed-to-parse files logged with a reason and timestamp, so that I can investigate corrupt or unusual files without the whole scan failing.
9. As the sole user, I want files automatically grouped into sessions by target + observation night, so that I don't have to manually create a session before my data is organized.
10. As the sole user, I want to attach a 5-star quality rating to an auto-derived session, so that I can track how good the conditions/results were on a given night.
11. As the sole user, I want to record a bortle scale value for a session, so that I can correlate sky darkness with my results over time.
12. As the sole user, I want to add free-text notes to a session, so that I can record transparency, guiding behavior, or anything else not captured by structured fields.
13. As the sole user, I want my manual session annotations to survive future re-scans of the same directory, so that I never lose my own notes/ratings by re-running the scanner.
14. As the sole user, I want files/sessions clustered by RA/DEC proximity into target groups, so that two nights shot under different or inconsistent OBJECT names but pointing at the same sky position are recognized as the same target.
15. As the sole user, I want the FOV clustering to account for the Seestar's small field of view when deciding what counts as "close enough," so that genuinely distinct nearby targets aren't incorrectly merged.
16. As the sole user, I want files with missing or malformed RA/DEC headers to be handled gracefully (e.g. left ungrouped or flagged) rather than crashing the clustering step, so that a few bad headers don't break the whole grouping run.
17. As the sole user, I want to see total accumulated integration time per matched target group (summed net exposure across all its sessions), so that I know how much data I actually have on a given object regardless of how it was labeled.
18. As the sole user, I want to calculate the grand integrated mean midpoint timestamp across the subs in a target group, so that I can use it in PixInsight/Siril post-processing workflows (e.g. astrometry/timestamp-sensitive steps).
19. As the sole user, I want to run a local web server with a single command, so that starting the tool is as low-friction as running the current script.
20. As the sole user, I want the dashboard to load live data from the local server automatically, so that I no longer need to manually export and upload a CSV file each time.
21. As the sole user, I want the dashboard's existing stat cards, charts (frame type, category, top targets, exposure histogram), and searchable/sortable/paginated table to keep working after the switch to a live data source, so that I don't lose functionality I already rely on.
22. As the sole user, I want new dashboard views for sessions and target groups (including their ratings, notes, integration time, and mean midpoint), so that the new data isn't only accessible via raw API calls.
23. As the sole user, I want to add or edit a session's rating/bortle/notes directly from the dashboard, so that I don't need a separate tool or direct database access to annotate my data.
24. As the sole user, I want to export the current (filtered) dataset to CSV on demand, so that I retain the portability of the original tool for ad hoc analysis in Excel/Sheets.
25. As the sole user, I want the tool to keep working for FITS files from non-Seestar equipment, so that gear-specific assumptions don't break scans of my other telescope's data.
26. As the sole user, I want Seestar-specific fields (e.g. distinguishing S50 vs S30, mount mode) surfaced when present in headers, so that I get extra context for Seestar data without it being required for other gear.
27. As the sole user, I want to pick a target folder and start a scan from a browser page, so that I no longer need to run the Python CLI with hand-typed arguments.
28. As the sole user, I want to choose between a full scan, a full scan with clustering, or clustering only, so that I can pick the right amount of work for the situation (e.g. skip re-walking the filesystem when I only need to re-cluster).
29. As the sole user, I want a native folder picker rather than typing a path by hand, so that selecting a directory is fast and error-free.
30. As the sole user, I want the folder field to remember my recently-used directories, so that rescanning the same one or two library locations doesn't require re-browsing every time.
31. As the sole user, I want to see live progress while a scan runs (files processed, new/updated/skipped/failed counts), so that I know it's working and roughly how much is left, especially for large libraries.
32. As the sole user, I want to cancel a scan that's in progress, so that pointing the picker at the wrong (e.g. huge) folder by mistake doesn't force me to wait it out or kill the server process.
33. As the sole user, I want to see which files failed to parse and why, directly in the browser, so that I don't have to separately open a log file to investigate.
34. As the sole user, I want the scan page to show me a run that's already in progress if I reload or revisit it, so that I never lose visibility into a long-running scan.

## Implementation Decisions

- **Persistence**: SQLite is the source of truth, replacing the CSV-as-source-of-truth model. The CSV becomes a generated export, not an input artifact.
- **Scanner module** (evolves `FITS_Analysis.py`): walks the target directory, and for each FITS/XISF file compares path + mtime (and size) against the stored record.
  - Unchanged path+mtime → skip (no header re-parse).
  - New path → parse, insert.
  - Changed mtime → re-parse, update (upsert semantics, not append).
  - Retains existing header parsing, Processed/Subframe classification (filename keyword match: stack/starless/starmask/master), and frame-type normalization logic from the current script.
  - Each scan run records a `scanned_at` timestamp so "what's new since last scan" is a simple query rather than a computed diff.
  - Continues to write per-file errors to an error log for files that fail to parse.
- **Storage module**: SQLite schema and a repository-style access layer (no raw SQL scattered through other modules). Tables include (at minimum): files (one row per FITS/XISF file, all extracted metadata + path/mtime), sessions (auto-derived, one row per target+night grouping), session_annotations (rating, bortle, notes — separate from auto-derived session data so annotations are never overwritten by a re-derive), target_groups (FOV-cluster membership), and scan_runs (timestamps, for "since last scan" queries).
- **Session Deriver module**: groups files into sessions using target (post-FOV-clustering target group, not raw OBJECT string) + observation night. Runs after clustering so sessions reflect true targets, not just label matches. Pure function over file records in, session groupings out — annotations are attached separately and are never touched by re-derivation.
- **FOV Clustering module**: reads RA/DEC (or OBJCTRA/OBJCTDEC) header values and clusters files whose coordinates fall within a proximity tolerance sized to the Seestar's field of view (~1°). Files with missing/malformed coordinates are excluded from clustering (left in their own singleton group or flagged as "ungrouped") rather than erroring the run. Output is a target-group assignment per file, independent of the OBJECT label.
- **Integration Calculator module**: given a target group's set of files (with DATE-OBS and exposure time), computes (a) total net integration time (sum of exposure across subframes) and (b) the grand integrated mean midpoint timestamp (exposure-weighted average of each sub's midpoint time). Pure calculation module, no I/O.
- **API Server module**: a local Flask or FastAPI server providing read endpoints (files, sessions, target groups, stats, "what's new since last scan") and write endpoints (create/update session annotations). Single-command startup. No auth (single-user, local-only).
- **Dashboard module**: evolves the existing D3.js `dashboard.html` to fetch from the local API instead of requiring CSV upload. Existing stat cards, bar/pie/histogram charts, and searchable/sortable/paginated table are preserved. New views added for sessions (with annotation editing) and target groups (integration time, mean midpoint, member sessions).
- **CSV Exporter module**: generates a CSV from current database state on demand (via API endpoint or CLI flag), preserving the existing CSV schema/format for continuity with any existing external workflows the user has around the current CSV.
- **Tech stack continuity**: Python remains the backend language (stdlib `sqlite3`, `astropy`, optional `xisf`, plus a lightweight web framework). Dashboard remains vanilla JS + D3.js — no frontend framework/build step introduced.
- **Gear model**: no hardcoded device picker (e.g. no explicit S50/S30 selector). All fields are read from whatever headers are present; Seestar-originated files naturally populate Seestar-flavored fields (INSTRUME, etc.) without special-casing, per the gear-agnostic decision made during scoping.
- **Scan Launch Page module**: a dedicated `/scan` route (separate from the `/` dashboard, linked from its header) that replaces hand-typed CLI invocation with a browser form:
  - **Mode selector**: Full scan / Full scan + clustering (default) / Clustering only — maps 1:1 to the scanner's existing `--cluster`/`--cluster-only` flags, no new scanner semantics. Selecting "Clustering only" hides the folder field entirely, since that mode never touches the filesystem.
  - **Folder picker**: a "Browse…" button calls a local API endpoint that shells out to `osascript` to open the native macOS "Choose Folder" dialog and returns the chosen path — macOS-specific by design, since this tool only ever runs on the user's own Mac. A dropdown of the last 5 distinct directories used (derived from `scan_runs.directory`, most-recent first) is offered alongside Browse so regularly-used library locations don't need re-browsing.
  - **Execution model**: starting a scan launches a background job on the server (not a blocking request) and returns a job id immediately; the page polls a status endpoint every 1-2 seconds to show live progress (files processed, new/updated/skipped/failed) using the scanner's existing progress-callback hook. Only one scan job may run at a time; starting a second while one is active is rejected with a clear message.
  - **Cancellation**: a "Cancel" button sets a stop flag the background job checks between files (cooperative, not a thread kill) so it stops promptly; files already upserted before cancellation remain committed, matching how an interrupted CLI run already behaves today.
  - **Completion**: the page stays put and shows the final summary in place (same shape as today's CLI output: counts, category/frame-type breakdown, clustering/session results), plus an expandable list of any failed files (path + reason) sourced from the same data written to the error log — with a "View Dashboard →" link to move on when ready.
  - **Reload/revisit behavior**: on load, the page checks the status endpoint for an in-progress job and shows its live progress immediately rather than a fresh "start a scan" form, so a job started earlier is never invisible after a refresh or a later visit.
  - **DB path**: fixed to however the server process was started (`--db` / `ASTRO_TRACKER_DB`); the scan page never exposes a database picker, avoiding any risk of scanning into the wrong `.db` file.
  - **Job Manager submodule**: the background job state machine (pending → running → done/failed/cancelled, single-job enforcement, cancellation timing, recent-directory tracking) is written as a distinct, testable unit separate from the thin FastAPI route handlers that call it.

## Testing Decisions

- Tests should verify external behavior (given inputs, expected outputs/state), not internal implementation details — consistent with treating Scanner, FOV Clustering, and Integration Calculator as modules with narrow, stable interfaces around non-trivial logic.
- **Scanner**: unit tests using fixture FITS files (including malformed/edge-case headers) covering: frame-type normalization (master vs. non-master, numeric IMAGETYP codes, malformed/junk header values falling back to "Unknown"), Processed vs. Subframe classification by filename keyword, and incremental skip logic (same path+mtime → no re-parse; changed mtime → re-parse and update, not duplicate).
- **FOV Clustering**: unit tests using synthetic RA/DEC coordinate sets covering: files within tolerance cluster together regardless of differing OBJECT labels, files outside tolerance remain separate even with identical OBJECT labels, and files with missing/malformed coordinates are excluded from clustering without raising an error.
- **Integration Calculator**: unit tests covering: total integration time is the correct sum of exposure times for a group, the grand integrated mean midpoint matches a hand-computed exposure-weighted average for a known input set, and edge cases (single file, files spanning midnight/date boundary) compute correctly.
- No existing test suite exists in this repo to follow as prior art; these will be the first automated tests introduced. Standard Python `unittest` or `pytest` conventions apply.
- Storage/Repository layer and API Server are out of this PRD's explicit test scope (per user decision) — may be covered in a future iteration.
- **Scan Launch Page**: the Job Manager submodule (state transitions, single-job enforcement, cancellation stopping before the next file, recent-directory tracking) gets unit tests, consistent with the rigor applied to Scanner/FOV Clustering/Integration Calculator. The FastAPI route handlers and the `osascript` native-picker integration are out of test scope, consistent with the existing "API server not covered" decision above — `osascript` in particular isn't practically unit-testable since it drives a real OS dialog.

## Out of Scope

- Achievement/gamification system (tiers, badges, categories).
- Calendar view.
- Per-target goal-setting and goal-based progress bars (total integration time display per target group is in scope; goal input is not).
- PDF and plain-text export formats (CSV export only).
- True plate-solving (astrometry.net/ASTAP or similar) — FOV clustering uses header RA/DEC only.
- Mobile/responsive design and field-use workflows.
- Multi-user support, accounts, authentication, sharing.
- A Seestar-specific device model (e.g. explicit S50/S30 picker, mount-mode field) — the tool stays gear-agnostic and header-driven.
- Frontend framework rebuild (React/Vite, etc.) — dashboard stays vanilla JS/D3.

## Further Notes

- This PRD consolidates functionality from the existing local `FITS_Report` project (`FITS_Analysis.py` scanner + `dashboard.html` D3 dashboard) with concepts drawn from SeeSession (a Base44/React reference product for Seestar users) — scoped down to what's needed for a single-user, local-first tool, not a full re-implementation of SeeSession's feature set or tech stack.
- The project is not currently a git repository; this PRD is being tracked as a local file (`PRD.md`) rather than published to an issue tracker, since none is configured yet.
- Deferred items (calendar view, PDF export, goal-setting, gamification, true plate-solving, mobile support) were explicitly discussed and deferred rather than rejected — worth revisiting as v1.1+ candidates once the core incremental-scan + session/FOV-grouping foundation is in place.
