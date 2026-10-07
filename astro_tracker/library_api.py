"""API routes for the library manager: hashing, vocabularies, Sources, Projects and check-in.

Kept apart from server.py only for size. Handlers stay thin -- they
validate input, call the module that does the work, and shape the
response.
"""

import sqlite3
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from astro_tracker import config, hashing, jobs, library_storage, storage, vocabulary, vocabulary_job

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


# ---- Vocabularies: Rigs, Filters, Targets -----------------------------------

class RigBody(BaseModel):
    name: str
    patterns: List[str]
    date_ranges: List[List[Optional[str]]] = []


@router.get("/api/rigs")
def list_rigs():
    conn = _conn()
    try:
        return {"rigs": library_storage.get_rigs(conn), "optical_trains": library_storage.get_optical_train_summary(conn)}
    finally:
        conn.close()


@router.put("/api/rigs/{rig_id}")
def save_rig(rig_id: str, body: RigBody):
    """Create or update a Rig, then reassign every file -- a Rig edit changes which files it claims."""
    if vocabulary.slug(rig_id, "") != rig_id:
        raise HTTPException(status_code=400, detail="Rig id may contain only letters, digits, dot and hyphen")
    patterns = [p.strip() for p in body.patterns if p.strip()]
    if not patterns:
        raise HTTPException(status_code=400, detail="A Rig needs at least one Optical Train pattern")
    if any(len(r) != 2 for r in body.date_ranges):
        raise HTTPException(status_code=400, detail="Each date range is [start, end]; either may be null")
    conn = _conn()
    try:
        rig = library_storage.upsert_rig(conn, rig_id, body.name.strip() or rig_id, patterns, body.date_ranges)
        return {"rig": rig, "recompute": vocabulary_job.recompute(conn)}
    finally:
        conn.close()


@router.delete("/api/rigs/{rig_id}")
def remove_rig(rig_id: str):
    conn = _conn()
    try:
        if not library_storage.delete_rig(conn, rig_id):
            raise HTTPException(status_code=404, detail=f"No Rig '{rig_id}'")
        return {"deleted": True, "recompute": vocabulary_job.recompute(conn)}
    finally:
        conn.close()


class FilterMappingBody(BaseModel):
    raw: str
    canonical: Optional[str] = None


@router.get("/api/filters")
def list_filters():
    conn = _conn()
    try:
        return {"mapping": library_storage.get_filter_map(conn), "in_library": library_storage.get_filter_summary(conn)}
    finally:
        conn.close()


@router.put("/api/filters")
def save_filter_mapping(body: FilterMappingBody):
    """Map a header filter value to a canonical Filter; a null `canonical` removes the mapping."""
    canonical = body.canonical.strip() if body.canonical else None
    if canonical is not None and vocabulary.slug(canonical, "") != canonical:
        raise HTTPException(status_code=400, detail="A canonical Filter may contain only letters, digits, dot and hyphen")
    conn = _conn()
    try:
        library_storage.set_filter_mapping(conn, body.raw, canonical)
        return {"recompute": vocabulary_job.recompute(conn)}
    finally:
        conn.close()


class TargetNameBody(BaseModel):
    name: str
    aliases: Optional[List[str]] = None


@router.get("/api/targets")
def list_targets():
    conn = _conn()
    try:
        return {"targets": library_storage.get_target_names(conn), "stages": list(vocabulary.STAGES)}
    finally:
        conn.close()


@router.put("/api/targets/{target_group_id}")
def save_target_name(target_group_id: int, body: TargetNameBody):
    name = body.name.strip()
    if not name or vocabulary.slug(name, "") != name:
        raise HTTPException(status_code=400, detail="A Target name may contain only letters, digits, dot and hyphen")
    conn = _conn()
    try:
        library_storage.set_target_name(conn, target_group_id, name, body.aliases)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail=f"Another target is already named '{name}', or the target group does not exist")
    finally:
        conn.close()
    return {"target_group_id": target_group_id, "name": name}


@router.post("/api/vocabulary/recompute")
def recompute_vocabulary():
    conn = _conn()
    try:
        return vocabulary_job.recompute(conn)
    finally:
        conn.close()
