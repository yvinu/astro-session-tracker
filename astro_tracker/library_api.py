"""API routes for the library manager: hashing, vocabularies, Sources, Projects and check-in.

Kept apart from server.py only for size. Handlers stay thin -- they
validate input, call the module that does the work, and shape the
response.
"""

import hmac
import sqlite3
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from astro_tracker import config, hashing, jobs, library_storage, storage, vocabulary, vocabulary_job

router = APIRouter()


# Set by server.py to a function returning the catalog path in use. It
# must come from the server module that is actually running: when the
# server is started with `python -m astro_tracker.server`, that module is
# `__main__`, and importing `astro_tracker.server` from here would load a
# second copy whose DB_PATH never saw the --db argument -- these routes
# would then quietly use the default catalog instead of the one asked for.
get_db_path = None


def _db_path():
    if get_db_path is None:
        raise RuntimeError("library_api.get_db_path has not been set by the server")
    return get_db_path()


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
    patterns: List[str] = []
    date_ranges: List[List[Optional[str]]] = []
    camera: Optional[str] = None
    focal_min: Optional[float] = None
    focal_max: Optional[float] = None


@router.get("/api/rigs")
def list_rigs():
    conn = _conn()
    try:
        trains = library_storage.get_optical_train_summary(conn)
        return {"rigs": library_storage.get_rigs(conn), "optical_trains": trains,
                "suggestions": vocabulary.suggest_rigs(trains)}
    finally:
        conn.close()


@router.put("/api/rigs/{rig_id}")
def save_rig(rig_id: str, body: RigBody):
    """Create or update a Rig, then reassign every file -- a Rig edit changes which files it claims."""
    if vocabulary.slug(rig_id, "") != rig_id:
        raise HTTPException(status_code=400, detail="Rig id may contain only letters, digits, dot and hyphen")
    patterns = [p.strip() for p in body.patterns if p.strip()]
    camera = vocabulary.normalize_camera(body.camera)
    if not patterns and not camera:
        raise HTTPException(status_code=400, detail="A Rig needs a camera or at least one Optical Train pattern")
    if body.focal_min is not None and body.focal_max is not None and body.focal_min > body.focal_max:
        raise HTTPException(status_code=400, detail="The focal length range is the wrong way round")
    if any(len(r) != 2 for r in body.date_ranges):
        raise HTTPException(status_code=400, detail="Each date range is [start, end]; either may be null")
    conn = _conn()
    try:
        rig = library_storage.upsert_rig(conn, rig_id, body.name.strip() or rig_id, patterns, body.date_ranges,
                                         camera, body.focal_min, body.focal_max)
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


# ---- Sources ----------------------------------------------------------------

class SourceBody(BaseModel):
    name: str
    source_dir: str
    mirror_dir: str
    profile: str = "all"
    host: Optional[str] = None
    interval_minutes: int = 60
    stability_seconds: int = 600
    enabled: bool = True


def _source_fields(body):
    from astro_tracker import source_pull
    if body.profile not in source_pull.PROFILES:
        raise HTTPException(status_code=400, detail=f"Unknown profile '{body.profile}'; expected one of {sorted(source_pull.PROFILES)}")
    if not body.name.strip() or not body.source_dir.strip() or not body.mirror_dir.strip():
        raise HTTPException(status_code=400, detail="name, source_dir and mirror_dir are required")
    if body.interval_minutes < 0 or body.stability_seconds < 0:
        raise HTTPException(status_code=400, detail="interval_minutes and stability_seconds cannot be negative")
    return {
        "name": body.name.strip(), "transport": "mounted_share", "profile": body.profile,
        "source_dir": body.source_dir.strip(), "mirror_dir": body.mirror_dir.strip().rstrip("/"),
        "host": (body.host or "").strip() or None, "interval_minutes": body.interval_minutes,
        "stability_seconds": body.stability_seconds, "enabled": int(body.enabled),
    }


@router.get("/api/sources")
def list_sources():
    from astro_tracker import source_pull
    conn = _conn()
    try:
        sources = library_storage.get_sources(conn)
        for source in sources:
            source["last_run"] = library_storage.get_last_source_run(conn, source["id"])
            source["job"] = jobs.runner.status(f"pull:{source['id']}")
            source["mirror_free_bytes"] = source_pull.free_space(source["mirror_dir"])
        return {"sources": sources, "profiles": sorted(source_pull.PROFILES)}
    finally:
        conn.close()


@router.post("/api/sources")
def create_source(body: SourceBody):
    conn = _conn()
    try:
        return library_storage.create_source(conn, _source_fields(body))
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail=f"A Source named '{body.name}' already exists")
    finally:
        conn.close()


@router.put("/api/sources/{source_id}")
def update_source(source_id: int, body: SourceBody):
    conn = _conn()
    try:
        if library_storage.get_source(conn, source_id) is None:
            raise HTTPException(status_code=404, detail=f"No Source {source_id}")
        return library_storage.update_source(conn, source_id, _source_fields(body))
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail=f"A Source named '{body.name}' already exists")
    finally:
        conn.close()


@router.delete("/api/sources/{source_id}")
def delete_source(source_id: int):
    """Remove a Source and its run history. The mirror folder and its catalogued files are kept."""
    if jobs.runner.is_running(f"pull:{source_id}"):
        raise HTTPException(status_code=409, detail="This Source is being pulled; wait for it to finish")
    conn = _conn()
    try:
        if not library_storage.delete_source(conn, source_id):
            raise HTTPException(status_code=404, detail=f"No Source {source_id}")
        return {"deleted": True}
    finally:
        conn.close()


@router.post("/api/sources/{source_id}/pull")
def pull_source_now(source_id: int):
    from astro_tracker import source_runs
    conn = _conn()
    try:
        if library_storage.get_source(conn, source_id) is None:
            raise HTTPException(status_code=404, detail=f"No Source {source_id}")
    finally:
        conn.close()
    try:
        return source_runs.start_pull_job(_db_path(), source_id)
    except jobs.JobAlreadyRunningError:
        raise HTTPException(status_code=409, detail="This Source is already being pulled")


@router.post("/api/sources/{source_id}/cancel")
def cancel_source_pull(source_id: int):
    if not jobs.runner.cancel(f"pull:{source_id}"):
        raise HTTPException(status_code=409, detail="This Source is not being pulled")
    return {"cancelled": True}


@router.get("/api/sources/{source_id}/runs")
def source_run_history(source_id: int):
    conn = _conn()
    try:
        return {"runs": library_storage.get_source_runs(conn, source_id)}
    finally:
        conn.close()


# ---- Projects and Checkouts -------------------------------------------------

class ProjectBody(BaseModel):
    target_group_id: int
    name: Optional[str] = None
    notes: Optional[str] = None


class SelectionBody(BaseModel):
    """Which of the Target's lights to check out. A field left null places no restriction."""
    session_ids: Optional[List[int]] = None
    rigs: Optional[List[str]] = None
    filters: Optional[List[str]] = None


def _project_or_404(conn, ref):
    project = library_storage.find_project(conn, ref)
    if project is None:
        raise HTTPException(status_code=404, detail=f"No Project '{ref}'")
    return project


def _without_entries(built):
    """A manifest summary for the selection form: group totals without the per-sub entries."""
    return dict(built, groups=[{k: v for k, v in g.items() if k != "entries"} for g in built["groups"]])


@router.get("/api/projects")
def list_projects():
    conn = _conn()
    try:
        return {"projects": library_storage.get_projects(conn)}
    finally:
        conn.close()


@router.post("/api/projects")
def create_project(body: ProjectBody):
    from astro_tracker import projects
    conn = _conn()
    try:
        return projects.create_project(conn, body.target_group_id, body.name, body.notes)
    except projects.ProjectError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@router.get("/api/projects/{ref}")
def get_project(ref: str):
    from astro_tracker import projects
    conn = _conn()
    try:
        project = _project_or_404(conn, ref)
        return {
            "project": project,
            "folder": projects.project_dir(project),
            "checkouts": library_storage.get_checkouts(conn, project["id"]),
            "options": projects.checkout_options(conn, project),
        }
    finally:
        conn.close()


@router.post("/api/projects/{ref}/checkouts/preview")
def preview_checkout(ref: str, body: SelectionBody):
    from astro_tracker import projects
    conn = _conn()
    try:
        project = _project_or_404(conn, ref)
        return _without_entries(projects.preview_checkout(conn, project, body.model_dump(exclude_none=True)))
    finally:
        conn.close()


@router.post("/api/projects/{ref}/checkouts")
def create_checkout(ref: str, body: SelectionBody):
    from astro_tracker import projects
    conn = _conn()
    try:
        project = _project_or_404(conn, ref)
        checkout_id = projects.create_checkout(conn, project, body.model_dump(exclude_none=True))
        return _without_entries(library_storage.get_checkout_manifest(conn, checkout_id))
    except projects.ProjectError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@router.get("/api/checkouts/{checkout_id}/manifest")
def get_manifest(checkout_id: int):
    conn = _conn()
    try:
        stored = library_storage.get_checkout_manifest(conn, checkout_id)
    finally:
        conn.close()
    if stored is None:
        raise HTTPException(status_code=404, detail=f"No Checkout {checkout_id}")
    return stored


# ---- Runs, Artifacts and lineage (read side, for the UI) ---------------------

@router.get("/api/projects/{ref}/runs")
def list_runs(ref: str):
    from astro_tracker import checkin
    conn = _conn()
    try:
        project = _project_or_404(conn, ref)
        runs = library_storage.get_runs(conn, project["id"])
        for run in runs:
            run["folder"] = checkin.run_folder(run)
        return {"runs": runs}
    finally:
        conn.close()


class NotesBody(BaseModel):
    notes: str


@router.put("/api/runs/{run_id}/notes")
def save_run_notes(run_id: int, body: NotesBody):
    """Record what was done in a run -- the only record there is for tools that write no log."""
    from astro_tracker import checkin
    conn = _conn()
    try:
        run = library_storage.get_run(conn, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"No run {run_id}")
        library_storage.set_run_notes(conn, run_id, body.notes)
        checkin.write_record(conn, library_storage.get_project(conn, run["project_id"]))
        return {"run_id": run_id, "notes": body.notes}
    finally:
        conn.close()


@router.get("/api/artifacts/{artifact_id}/inputs")
def artifact_inputs(artifact_id: int):
    """What went into an output: the subs of the Checkout its run worked from."""
    conn = _conn()
    try:
        artifact = library_storage.get_artifact(conn, artifact_id)
        if artifact is None:
            raise HTTPException(status_code=404, detail=f"No Artifact {artifact_id}")
        inputs = library_storage.get_artifact_inputs(conn, artifact_id)
        return {"artifact": artifact, "sub_count": len(inputs), "subs": inputs}
    finally:
        conn.close()


@router.get("/api/files/{file_id}/uses")
def file_uses(file_id: int):
    """Where a sub was used: every stack and final from a Checkout that included it."""
    conn = _conn()
    try:
        content_hash = library_storage.get_file_content_hash(conn, file_id)
        return {"file_id": file_id, "uses": library_storage.get_uses_of_content(conn, content_hash) if content_hash else []}
    finally:
        conn.close()


# ---- Mac CLI ----------------------------------------------------------------
#
# The UI has no login: it is a single-user tool on the home network. The
# CLI endpoints are the ones that hand out file paths in bulk and accept
# uploads into the library, so they require the shared token set in
# ASTRO_CLI_TOKEN, and are switched off entirely when it is not set.

def require_cli_token(request: Request):
    expected = config.cli_token()
    if not expected:
        raise HTTPException(status_code=503, detail="CLI access is not configured on the server (ASTRO_CLI_TOKEN)")
    supplied = request.headers.get("authorization", "")
    if not hmac.compare_digest(supplied.encode(), f"Bearer {expected}".encode()):
        raise HTTPException(status_code=401, detail="Missing or wrong CLI token")


cli = APIRouter(prefix="/api/cli", dependencies=[Depends(require_cli_token)])


@cli.get("/projects")
def cli_projects():
    conn = _conn()
    try:
        return {"projects": library_storage.get_projects(conn)}
    finally:
        conn.close()


@cli.get("/projects/{ref}/manifest")
def cli_latest_manifest(ref: str):
    """The manifest of a Project's most recent Checkout."""
    conn = _conn()
    try:
        project = _project_or_404(conn, ref)
        checkout_id = library_storage.get_latest_checkout_id(conn, project["id"])
        if checkout_id is None:
            raise HTTPException(status_code=404, detail=f"Project '{project['slug']}' has no Checkout yet; create one in the UI")
        return library_storage.get_checkout_manifest(conn, checkout_id)
    finally:
        conn.close()


class WorkingDirBody(BaseModel):
    working_dir: str


@cli.post("/checkouts/{checkout_id}/working-dir")
def cli_set_working_dir(checkout_id: int, body: WorkingDirBody):
    conn = _conn()
    try:
        if library_storage.get_checkout_manifest(conn, checkout_id) is None:
            raise HTTPException(status_code=404, detail=f"No Checkout {checkout_id}")
        library_storage.set_checkout_working_dir(conn, checkout_id, body.working_dir)
        return {"checkout_id": checkout_id, "working_dir": body.working_dir}
    finally:
        conn.close()


class HashesBody(BaseModel):
    hashes: List[str]


@cli.post("/projects/{ref}/known-hashes")
def cli_known_hashes(ref: str, body: HashesBody):
    """Which of these Content hashes the Project already holds, so check-in uploads only what is new."""
    conn = _conn()
    try:
        project = _project_or_404(conn, ref)
        return {"known": sorted(library_storage.get_known_artifact_hashes(conn, project["id"], body.hashes))}
    finally:
        conn.close()


class RunBody(BaseModel):
    kind: str
    tool: str
    checkout_id: Optional[int] = None
    notes: Optional[str] = None


@cli.post("/projects/{ref}/runs")
def cli_start_run(ref: str, body: RunBody):
    from astro_tracker import checkin
    conn = _conn()
    try:
        project = _project_or_404(conn, ref)
        run = checkin.start_run(conn, project, body.kind, body.tool, body.checkout_id, body.notes)
        return dict(run, folder=checkin.run_folder(run))
    except checkin.CheckinError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@cli.put("/runs/{run_id}/files")
async def cli_upload_file(run_id: int, request: Request, relpath: str, kind: str, sha256: str,
                          stage: Optional[str] = None, rig: Optional[str] = None,
                          filter: Optional[str] = None, frames: Optional[int] = None):
    """Receive one file for a run. The request body is the file's bytes.

    Written to a temporary file inside the Project folder first; it is
    only moved into place and recorded once its hash matches `sha256`.
    """
    from astro_tracker import checkin
    conn = _conn()
    try:
        run = library_storage.get_run(conn, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"No run {run_id}")
        project = library_storage.get_project(conn, run["project_id"])
        try:
            temp_path = checkin.incoming_path(project)
        except checkin.CheckinError as e:
            raise HTTPException(status_code=503, detail=str(e))
        try:
            with open(temp_path, "wb") as f:
                async for chunk in request.stream():
                    f.write(chunk)
            artifact, status = checkin.store_artifact(
                conn, project, run, temp_path, relpath, kind,
                declared_hash=sha256, stage=stage, rig=rig, filter_name=filter, frames=frames,
            )
        except checkin.CheckinError as e:
            raise HTTPException(status_code=400, detail=str(e))
        finally:
            import os
            if os.path.exists(temp_path):
                os.remove(temp_path)
        return {"status": status, "artifact": artifact}
    finally:
        conn.close()


@cli.post("/runs/{run_id}/finish")
def cli_finish_run(run_id: int):
    from astro_tracker import checkin
    conn = _conn()
    try:
        run = library_storage.get_run(conn, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"No run {run_id}")
        project = library_storage.get_project(conn, run["project_id"])
        kept = checkin.finish_run(conn, project, run)
        return {"kept": kept is not None, "run": kept}
    finally:
        conn.close()


router.include_router(cli)
