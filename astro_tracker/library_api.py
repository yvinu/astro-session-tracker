"""API routes for the library manager: hashing, vocabularies, Sources, Projects and check-in.

Kept apart from server.py only for size. Handlers stay thin -- they
validate input, call the module that does the work, and shape the
response.
"""

from fastapi import APIRouter, HTTPException

from astro_tracker import config, hashing, jobs, library_storage, storage

router = APIRouter()


def _db_path():
    # Looked up at call time: server.main() sets DB_PATH from --db after import.
    from astro_tracker import server
    return server.DB_PATH


def _conn():
    conn = storage.connect(_db_path())
    storage.init_schema(conn)
    return conn


# ---- Content hashes ---------------------------------------------------------

@router.post("/api/hash/start")
def start_hashing():
    """Start a background pass hashing files under the configured library roots (all files if none are set)."""
    db_path = _db_path()
    prefixes = [path for _name, path in config.library_roots()] or None

    def work(job):
        return hashing.hash_pending(db_path, prefixes, should_stop=job.should_stop, progress=job.progress.update)

    try:
        return jobs.runner.start("hash", work)
    except jobs.JobAlreadyRunningError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/api/hash/status")
def hashing_status():
    conn = _conn()
    try:
        counts = library_storage.get_hash_counts(conn)
    finally:
        conn.close()
    return {"counts": counts, "job": jobs.runner.status("hash")}


@router.post("/api/hash/cancel")
def cancel_hashing():
    if not jobs.runner.cancel("hash"):
        raise HTTPException(status_code=409, detail="No hashing pass is running")
    return {"cancelled": True}
