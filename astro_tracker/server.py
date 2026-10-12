"""Local read-only API server exposing the SQLite inventory to the dashboard.

Single-user, local-only: no auth. Serves both the JSON API and the
dashboard HTML from the same origin so the browser never has to deal
with CORS.
"""

import argparse
import os
from contextlib import asynccontextmanager
import subprocess
import threading
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from astro_tracker import config, ingest, integration, jobs, library_storage, siril_export, storage
from astro_tracker.exporter import records_to_csv
from astro_tracker.scanner import DEFAULT_DB_PATH, DEFAULT_ERROR_LOG

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_PATH = os.path.join(REPO_ROOT, "dashboard.html")
SCAN_PAGE_PATH = os.path.join(REPO_ROOT, "scan.html")
STUDIO_PATH = os.path.join(REPO_ROOT, "fits_studio.html")
LIBRARY_PAGE_PATH = os.path.join(REPO_ROOT, "library.html")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

from fastapi.middleware.cors import CORSMiddleware

DB_PATH = os.environ.get("ASTRO_TRACKER_DB", DEFAULT_DB_PATH)

def repair_after_restart(db_path):
    """Put right what a stopped service left behind. Returns whether any file is waiting for a Content hash.

    Jobs live in memory, so a restart drops whatever was running or
    waiting. Nothing is lost -- every job is safe to repeat -- but a
    Source run cut off mid-pull would otherwise show as running forever.
    """
    conn = storage.connect(db_path)
    storage.init_schema(conn)
    try:
        library_storage.close_abandoned_source_runs(conn)
        scope = ingest.hash_scope(db_path)
        return bool(scope) and bool(library_storage.get_files_needing_hash(conn, scope))
    finally:
        conn.close()


@asynccontextmanager
async def lifespan(_app):
    """Repair after a restart, resume hashing, and start scheduled Source pulls when enabled.

    The scheduler is off by default so that running the server on a
    laptop, or under tests, never starts copying from devices on its own.
    Hashing resumes only where a library root or a Source is configured.
    """
    resume = None
    if repair_after_restart(DB_PATH):
        resume = threading.Timer(config.hash_resume_delay(), ingest.request_hashing, args=(DB_PATH,))
        resume.daemon = True
        resume.start()
    if config.scheduler_enabled():
        from astro_tracker import source_runs
        source_runs.Scheduler(DB_PATH).start()
    yield
    if resume is not None:
        resume.cancel()


app = FastAPI(title="Astro Session Tracker API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_conn():
    return storage.connect(DB_PATH)


from astro_tracker import library_api  # noqa: E402  (needs `app` to exist)

app.include_router(library_api.router)
library_api.get_db_path = lambda: DB_PATH  # read at call time: main() sets DB_PATH from --db




@app.get("/")
def serve_dashboard():
    return FileResponse(DASHBOARD_PATH)


@app.get("/scan")
def serve_scan_page():
    return FileResponse(SCAN_PAGE_PATH)


@app.get("/studio")
def serve_studio_page():
    return FileResponse(STUDIO_PATH)


@app.get("/library")
def serve_library_page():
    return FileResponse(LIBRARY_PAGE_PATH)


@app.get("/api/fits-dictionary")
def get_fits_dictionary():
    dict_path = os.path.join(REPO_ROOT, "astro_tracker", "fits_dictionary.json")
    if os.path.exists(dict_path):
        return FileResponse(dict_path, media_type="application/json")
    raise HTTPException(status_code=404, detail="Dictionary file not found")


@app.post("/api/corpus/reset")
def reset_corpus_api():
    try:
        from astro_tracker.fits_graph_db import FITSGraphDB
        graph_db = FITSGraphDB()
        graph_db.reset_database()
        return {"status": "success", "message": "Corpus database and dictionary reset successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/files")
def list_files():
    conn = get_conn()
    try:
        return storage.get_all_files(conn)
    finally:
        conn.close()


@app.get("/api/stats")
def get_stats():
    conn = get_conn()
    try:
        return storage.get_summary_stats(conn)
    finally:
        conn.close()


@app.get("/api/target-groups")
def list_target_groups():
    conn = get_conn()
    try:
        exclude_ids = storage.get_duplicate_exclusion_ids(conn)
        groups = storage.get_target_groups_summary(conn)
        for group in groups:
            group_files = storage.get_files_for_target_group(conn, group["target_group_id"], exclude_ids)
            group["integration_seconds"] = integration.total_integration_seconds(group_files)
            group["mean_midpoint"] = integration.grand_integrated_mean_midpoint(group_files)
        return {
            "groups": groups,
            "ungrouped_file_count": storage.get_ungrouped_file_count(conn),
        }
    finally:
        conn.close()


@app.get("/api/duplicates")
def list_duplicates():
    conn = get_conn()
    try:
        return {"groups": storage.get_duplicate_groups_summary(conn)}
    finally:
        conn.close()


@app.get("/api/sessions")
def list_sessions():
    conn = get_conn()
    try:
        return storage.get_sessions_summary(conn)
    finally:
        conn.close()


class SessionAnnotationUpdate(BaseModel):
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    bortle: Optional[int] = Field(default=None, ge=1, le=9)
    notes: Optional[str] = None


@app.put("/api/sessions/{session_id}/annotation")
def update_session_annotation(session_id: int, body: SessionAnnotationUpdate):
    conn = get_conn()
    try:
        session_exists = conn.execute(
            "SELECT 1 FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not session_exists:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        return storage.upsert_session_annotation(
            conn, session_id, rating=body.rating, bortle=body.bortle, notes=body.notes
        )
    finally:
        conn.close()


@app.get("/api/whats-new")
def whats_new():
    conn = get_conn()
    try:
        return storage.get_whats_new_since_last_scan(conn)
    finally:
        conn.close()


@app.get("/api/export.csv")
def export_csv():
    conn = get_conn()
    try:
        records = storage.get_all_files(conn)
    finally:
        conn.close()
    return PlainTextResponse(
        records_to_csv(records),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=astro_inventory_export.csv"},
    )


class ScanStartRequest(BaseModel):
    mode: str = "full_cluster"
    directory: Optional[str] = None
    force: bool = False


SCAN_KINDS = (ingest.KIND_INGEST, ingest.KIND_DERIVE)
MODE_CLUSTER_ONLY = "cluster_only"
SCAN_MODES = ("full_cluster", "full", MODE_CLUSTER_ONLY)  # "full" is the old scan-only mode; it now ingests in full


def _scan_status(job, activity):
    """A runner job in the shape the scan page reads."""
    progress, result = job["progress"], job["result"] or {}
    status = {
        "job_id": job["id"],
        "mode": job["meta"].get("mode"),
        "directory": job["meta"].get("directory"),
        "force": job["meta"].get("force", False),
        "state": job["state"],
        "step": progress.get("step"),
        "counts": progress.get("counts") or {},
        "failures": progress.get("failures") or [],
        "library_summary": progress.get("library_summary"),
        "cluster_summary": progress.get("cluster_summary"),
        "error": job["error"],
    }
    if job["state"] == jobs.STATE_WAITING:
        ahead = [j for j in activity["running"] + activity["waiting"]
                 if j["lane"] == jobs.LANE_QUEUE and j["id"] < job["id"]]
        status["waiting_behind"] = [j["label"] for j in ahead]
    if result.get("cancelled") and job["state"] == jobs.STATE_DONE:
        status["state"] = jobs.STATE_CANCELLED
    return status


@app.post("/api/scan/start")
def start_scan(body: ScanStartRequest):
    """Queue an ingest of a folder, or a regroup of the library with no scan."""
    if body.mode not in SCAN_MODES:
        raise HTTPException(status_code=400, detail=f"Invalid mode: {body.mode}")

    if body.mode == MODE_CLUSTER_ONLY:
        job = ingest.submit_derive(DB_PATH)
    else:
        if not body.directory:
            raise HTTPException(status_code=400, detail="directory is required for this mode")
        if not os.path.isdir(body.directory):
            raise HTTPException(status_code=400, detail=f"'{body.directory}' is not a directory")
        job = ingest.submit(DB_PATH, body.directory, force=body.force, error_log=DEFAULT_ERROR_LOG)
    return _scan_status(job, jobs.runner.list())


@app.get("/api/scan/status")
def scan_status(job_id: Optional[int] = None):
    """The scan with this id; without one, the scan that is running, else the most recent."""
    activity = jobs.runner.list()
    if job_id is not None:
        job = jobs.runner.get(job_id)
        if job is None or job["kind"] not in SCAN_KINDS:
            return {"state": "idle"}
        return _scan_status(job, activity)
    scans = [j for group in ("running", "waiting", "finished") for j in activity[group] if j["kind"] in SCAN_KINDS]
    if not scans:
        return {"state": "idle"}
    running = [j for j in scans if j["state"] == jobs.STATE_RUNNING]
    return _scan_status(running[0] if running else max(scans, key=lambda j: j["id"]), activity)


@app.post("/api/scan/cancel")
def cancel_scan(job_id: Optional[int] = None):
    """Cancel the scan with this id; without one, the scan that is running."""
    if job_id is None:
        running = [j for j in jobs.runner.list()["running"] if j["kind"] in SCAN_KINDS]
        job_id = running[0]["id"] if running else None
    if job_id is None or not jobs.runner.cancel_job(job_id):
        raise HTTPException(status_code=409, detail="No scan is currently running")
    return {"cancelled": True}


# ---- Activity: every background job, for the panel shown on each page ----------

@app.get("/api/jobs")
def list_jobs():
    return jobs.runner.list()


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: int):
    if not jobs.runner.cancel_job(job_id):
        raise HTTPException(status_code=409, detail="That job is not waiting or running")
    return {"cancelled": True}


@app.post("/api/jobs/cancel-waiting")
def cancel_waiting_jobs():
    return {"cancelled": jobs.runner.cancel_waiting()}


@app.get("/static/{name}")
def static_file(name: str):
    path = os.path.join(STATIC_DIR, os.path.basename(name))
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path)


@app.get("/api/scan/recent-directories")
def recent_directories():
    conn = get_conn()
    try:
        recent = storage.get_recent_scan_directories(conn)
    finally:
        conn.close()
    # Configured library roots come first: on the NAS there is no native
    # folder picker, so these are how a scan target is chosen.
    roots = [path for _name, path in config.library_roots()]
    return {"directories": roots + [d for d in recent if d not in roots]}


@app.get("/api/library-roots")
def library_roots():
    return {"roots": [{"name": name, "path": path} for name, path in config.library_roots()]}


BROWSE_FOLDER_PROMPTS = {
    "scan": "Select a folder to scan",
    "siril_export": "Select a destination folder for the Siril working folder",
}


class BrowseFolderRequest(BaseModel):
    purpose: str = "scan"


@app.post("/api/browse-folder")
def browse_folder(body: BrowseFolderRequest = BrowseFolderRequest()):
    """Open the native macOS folder-choice dialog and return the path picked.

    Single-user, local-only tool that only ever runs on the user's own Mac,
    so shelling out to osascript for a real OS picker is reasonable here
    (no equivalent exists via a browser file input, which only exposes
    relative paths). `purpose` only selects among a small fixed set of
    prompt strings server-side -- request data is never interpolated
    into the AppleScript command itself.
    """
    prompt = BROWSE_FOLDER_PROMPTS.get(body.purpose, "Select a folder")
    script = f'POSIX path of (choose folder with prompt "{prompt}")'
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=300,
        )
    except FileNotFoundError:
        # Not macOS (e.g. the container on the NAS): no native picker. The
        # scan page falls back to configured roots and a typed path.
        return {"directory": None, "unavailable": True}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="Folder picker timed out")

    if result.returncode != 0:
        # Most commonly the user clicked Cancel in the dialog.
        return {"directory": None}

    return {"directory": result.stdout.strip()}


class SirilExportRequest(BaseModel):
    destination: str


@app.post("/api/target-groups/{group_id}/export-siril")
def export_target_group_to_siril(group_id: int, body: SirilExportRequest):
    if not body.destination or not os.path.isdir(body.destination):
        raise HTTPException(status_code=400, detail=f"'{body.destination}' is not a directory")

    conn = get_conn()
    try:
        files = storage.get_files_for_siril_export(conn, group_id)
    finally:
        conn.close()

    if not files:
        raise HTTPException(status_code=404, detail=f"Target group {group_id} has no Light frames")

    return siril_export.build_lights_export(files, body.destination, group_id)


class HeaderAnalysisRequest(BaseModel):
    directory: str
    ignore_symlinks: bool = True
    min_combo_pct: float = 1.0
    update_graph: bool = True


ANALYSIS_KEY = "header-analysis"
ANALYSIS_IDLE = {"status": "idle", "progress_pct": 0.0, "processed": 0, "total": 0,
                 "current_file": "", "results": None, "error": None}


class AnalysisStopped(Exception):
    pass


@app.post("/api/header-analysis/start")
def start_header_analysis(body: HeaderAnalysisRequest):
    """Start a header analysis. It only reads files, so it runs beside the catalog queue, not in it."""
    dir_path = os.path.expanduser(body.directory)
    if not os.path.exists(dir_path):
        raise HTTPException(status_code=400, detail=f"Directory '{dir_path}' does not exist.")

    def work(job):
        from fits_header_analyzer import run_analysis

        def on_file(current, total, file_path):
            if job.should_stop():
                raise AnalysisStopped()
            job.progress.update({"processed": current, "total": total, "current": file_path})

        try:
            return run_analysis(dir_path, ignore_symlinks=body.ignore_symlinks,
                                min_combo_pct=body.min_combo_pct, progress_callback=on_file)
        except AnalysisStopped:
            return None

    try:
        jobs.runner.submit(ANALYSIS_KEY, work, lane=jobs.LANE_FREE, kind="analysis",
                           label=f"Header analysis of {dir_path}", meta={"directory": dir_path})
    except jobs.JobAlreadyRunningError:
        raise HTTPException(status_code=409, detail="An analysis job is already running.")
    return {"status": "started", "directory": dir_path}


@app.get("/api/header-analysis/status")
def get_header_analysis_status():
    """The analysis job in the shape FITS Studio reads."""
    job = jobs.runner.status(ANALYSIS_KEY)
    if job is None:
        return dict(ANALYSIS_IDLE)
    processed, total = job["progress"].get("processed", 0), job["progress"].get("total", 0)
    done = job["state"] == jobs.STATE_DONE
    return {
        "status": {jobs.STATE_DONE: "completed", jobs.STATE_CANCELLED: "failed"}.get(job["state"], job["state"]),
        "progress_pct": 100.0 if done else (round(processed / total * 100, 1) if total else 0.0),
        "processed": processed,
        "total": total,
        "current_file": "Analysis complete!" if done else os.path.basename(job["progress"].get("current", "")) or "Initializing scan...",
        "results": job["result"] if done else None,
        "error": "Cancelled" if job["state"] == jobs.STATE_CANCELLED else job["error"],
    }


def main():
    parser = argparse.ArgumentParser(description="Run the local astro-tracker API + dashboard server.")
    parser.add_argument('--db', default=DEFAULT_DB_PATH,
                         help=f'SQLite database path (default: {DEFAULT_DB_PATH})')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()

    global DB_PATH
    DB_PATH = args.db

    import uvicorn
    print(f"Serving dashboard + API from {args.db} at http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
