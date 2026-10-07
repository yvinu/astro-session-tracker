"""Local read-only API server exposing the SQLite inventory to the dashboard.

Single-user, local-only: no auth. Serves both the JSON API and the
dashboard HTML from the same origin so the browser never has to deal
with CORS.
"""

import argparse
import os
import subprocess
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from astro_tracker import config, integration, scan_job, siril_export, storage
from astro_tracker.exporter import records_to_csv
from astro_tracker.scanner import DEFAULT_DB_PATH

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_PATH = os.path.join(REPO_ROOT, "dashboard.html")
SCAN_PAGE_PATH = os.path.join(REPO_ROOT, "scan.html")
STUDIO_PATH = os.path.join(REPO_ROOT, "fits_studio.html")

from fastapi.middleware.cors import CORSMiddleware

DB_PATH = os.environ.get("ASTRO_TRACKER_DB", DEFAULT_DB_PATH)

app = FastAPI(title="Astro Session Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_conn():
    return storage.connect(DB_PATH)


@app.get("/")
def serve_dashboard():
    return FileResponse(DASHBOARD_PATH)


@app.get("/scan")
def serve_scan_page():
    return FileResponse(SCAN_PAGE_PATH)


@app.get("/studio")
def serve_studio_page():
    return FileResponse(STUDIO_PATH)


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
    mode: str
    directory: Optional[str] = None
    force: bool = False


@app.post("/api/scan/start")
def start_scan(body: ScanStartRequest):
    if body.mode not in scan_job.VALID_MODES:
        raise HTTPException(status_code=400, detail=f"Invalid mode: {body.mode}")

    if body.mode != scan_job.MODE_CLUSTER_ONLY:
        if not body.directory:
            raise HTTPException(status_code=400, detail="directory is required for this mode")
        if not os.path.isdir(body.directory):
            raise HTTPException(status_code=400, detail=f"'{body.directory}' is not a directory")

    try:
        return scan_job.job_manager.start(body.mode, body.directory, DB_PATH, force=body.force)
    except scan_job.JobAlreadyRunningError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/api/scan/status")
def scan_status():
    status = scan_job.job_manager.current_status()
    if status is None:
        return {"state": "idle"}
    return status


@app.post("/api/scan/cancel")
def cancel_scan():
    cancelled = scan_job.job_manager.cancel()
    if not cancelled:
        raise HTTPException(status_code=409, detail="No scan is currently running")
    return {"cancelled": True}


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


analysis_job_state = {
    "status": "idle",
    "progress_pct": 0.0,
    "processed": 0,
    "total": 0,
    "current_file": "",
    "results": None,
    "error": None
}


@app.post("/api/header-analysis/start")
def start_header_analysis(body: HeaderAnalysisRequest):
    global analysis_job_state
    dir_path = os.path.expanduser(body.directory)
    if not os.path.exists(dir_path):
        raise HTTPException(status_code=400, detail=f"Directory '{dir_path}' does not exist.")

    if analysis_job_state["status"] == "running":
        raise HTTPException(status_code=409, detail="An analysis job is already running.")

    analysis_job_state = {
        "status": "running",
        "progress_pct": 0.0,
        "processed": 0,
        "total": 0,
        "current_file": "Initializing scan...",
        "results": None,
        "error": None
    }

    def worker():
        global analysis_job_state
        try:
            from fits_header_analyzer import run_analysis
            def progress_cb(current, total, file_path):
                analysis_job_state["processed"] = current
                analysis_job_state["total"] = total
                analysis_job_state["progress_pct"] = round((current / total) * 100, 1) if total > 0 else 0
                analysis_job_state["current_file"] = os.path.basename(file_path)

            res = run_analysis(dir_path, ignore_symlinks=body.ignore_symlinks, min_combo_pct=body.min_combo_pct, progress_callback=progress_cb)
            analysis_job_state["results"] = res
            analysis_job_state["status"] = "completed"
            analysis_job_state["progress_pct"] = 100.0
            analysis_job_state["current_file"] = "Analysis complete!"
        except Exception as e:
            analysis_job_state["status"] = "failed"
            analysis_job_state["error"] = str(e)

    import threading
    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return {"status": "started", "directory": dir_path}


@app.get("/api/header-analysis/status")
def get_header_analysis_status():
    return analysis_job_state


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
