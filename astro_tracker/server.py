"""Local read-only API server exposing the SQLite inventory to the dashboard.

Single-user, local-only: no auth. Serves both the JSON API and the
dashboard HTML from the same origin so the browser never has to deal
with CORS.
"""

import argparse
import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from astro_tracker import integration, storage
from astro_tracker.exporter import records_to_csv
from astro_tracker.scanner import DEFAULT_DB_PATH

DASHBOARD_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard.html")

DB_PATH = os.environ.get("ASTRO_TRACKER_DB", DEFAULT_DB_PATH)

app = FastAPI(title="Astro Session Tracker API")


def get_conn():
    return storage.connect(DB_PATH)


@app.get("/")
def serve_dashboard():
    return FileResponse(DASHBOARD_PATH)


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
        groups = storage.get_target_groups_summary(conn)
        for group in groups:
            group_files = storage.get_files_for_target_group(conn, group["target_group_id"])
            group["integration_seconds"] = integration.total_integration_seconds(group_files)
            group["mean_midpoint"] = integration.grand_integrated_mean_midpoint(group_files)
        return {
            "groups": groups,
            "ungrouped_file_count": storage.get_ungrouped_file_count(conn),
        }
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
