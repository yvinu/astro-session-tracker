"""Ingest: bring the catalog up to date with the files in a folder.

One sequence, used by every way files arrive -- a scan started from the
page, a Source pull, or the command line:

1. scan    read the headers of new and changed files (scanner.py)
2. derive  regroup the whole library: target groups, sessions,
           Duplicate Groups, then Rig, Filter and Target names
3. hash    compute the Content hash of files that lack one

A file that has been ingested is therefore always grouped and named,
and hashed soon after, which is what a Checkout requires of its subs.
Hashing covers only files the service can read cheaply -- those under a
configured library root or a Source's Mirror -- so scanning an external
drive from a laptop never reads every byte over the cable (ADR-0001).

`run` does the whole sequence in the calling thread. `submit` hands it
to the job runner, where scan and derive take a turn in the queue and
hashing follows in idle time.
"""

from astro_tracker import (
    clustering, config, duplicates, hashing, jobs, library_storage, scanner, sessions, storage, vocabulary_job,
)

KIND_INGEST = "ingest"
KIND_DERIVE = "derive"
KIND_HASH = "hash"
HASH_KEY = "hash"
DERIVE_KEY = "derive"

FAILURES_KEPT = 500


def derive(db_path):
    """Regroup and rename every File from what the catalog already holds. Returns a summary dict.

    Runs over the whole library, not just new files: one new sub can
    join two target groups, start a session, or complete a Duplicate
    Group.
    """
    conn = storage.connect(db_path)
    storage.init_schema(conn)
    try:
        group_of = clustering.cluster_files(storage.get_all_files_for_clustering(conn))
        n_groups, n_orphaned = storage.save_clustering(conn, group_of)

        session_groups = sessions.derive_sessions(storage.get_all_files_for_sessions(conn))
        n_sessions, n_stale_sessions = storage.save_sessions(conn, session_groups)

        duplicate_group_of = duplicates.find_duplicate_groups(storage.get_all_files_for_duplicates(conn))
        n_duplicate_groups = storage.save_duplicate_groups(conn, duplicate_group_of)

        return {
            "vocabulary": vocabulary_job.recompute(conn),
            "target_groups": n_groups,
            "ungrouped_files": storage.get_ungrouped_file_count(conn),
            "orphaned_groups": n_orphaned,
            "sessions": n_sessions,
            "stale_sessions": n_stale_sessions,
            "duplicate_groups": n_duplicate_groups,
        }
    finally:
        conn.close()


def library_summary(db_path):
    conn = storage.connect(db_path)
    try:
        return {
            "total_files": storage.get_total_file_count(conn),
            "category_breakdown": storage.get_category_breakdown(conn),
            "frame_type_breakdown": storage.get_frame_type_breakdown(conn),
        }
    finally:
        conn.close()


def hash_scope(db_path):
    """The folders whose files get a Content hash: configured library roots and every Source's Mirror."""
    conn = storage.connect(db_path)
    storage.init_schema(conn)
    try:
        mirrors = [source["mirror_dir"] for source in library_storage.get_sources(conn)]
    finally:
        conn.close()
    scope = [path for _name, path in config.library_roots()]
    return scope + [m for m in mirrors if m not in scope]


def hash_pending(db_path, should_stop=None, progress=None, everything_if_unscoped=False):
    """Hash files in the hash scope that lack a current Content hash.

    With no library root and no Source configured there is no scope, and
    nothing is hashed unless `everything_if_unscoped` is set (the
    explicit "start hashing" action).
    """
    scope = hash_scope(db_path)
    if not scope and not everything_if_unscoped:
        return {"hashed": 0, "failed": 0, "total": 0, "cancelled": False, "skipped": "no library root or Source configured"}
    return hashing.hash_pending(db_path, scope or None, should_stop=should_stop, progress=progress)


def run(db_path, directory, force=False, should_stop=None, progress=None, error_log=None, hash_now=True):
    """Ingest one folder: scan it, derive, then hash. Returns {"scan", "library", "derived", "hash", "cancelled"}.

    Stopping part-way keeps what was finished; the next ingest of the
    folder picks up the rest. A stopped scan is not followed by derive.
    `progress` is called with {"step": ..., and that step's own counts}.
    `hash_now=False` leaves hashing to the caller (the job runner does
    it in idle time).
    """
    failures = []
    report = progress or (lambda update: None)

    def on_file(counts, file_path, status, detail=None):
        if status == "failed" and len(failures) < FAILURES_KEPT:
            failures.append({"path": file_path, "reason": detail or "Unknown error"})
        report({"step": "scan", "counts": dict(counts), "failures": list(failures), "current": file_path})

    result = {"scan": None, "library": None, "derived": None, "hash": None, "cancelled": False, "failures": failures}
    result["scan"] = scanner.scan_directory(
        directory, db_path, error_log_path=error_log, progress_callback=on_file, should_stop=should_stop, force=force)
    result["library"] = library_summary(db_path)
    report({"step": "scan", "counts": dict(result["scan"]), "failures": list(failures), "library_summary": result["library"]})
    if result["scan"].get("cancelled"):
        result["cancelled"] = True
        return result

    report({"step": "derive"})
    result["derived"] = derive(db_path)
    report({"step": "derive", "cluster_summary": result["derived"]})

    if hash_now:
        report({"step": "hash"})
        result["hash"] = hash_pending(
            db_path, should_stop=should_stop, progress=lambda counts: report({"step": "hash", "hash": counts}))
        result["cancelled"] = bool(result["hash"].get("cancelled"))
    return result


# ---- on the job runner -------------------------------------------------------

def submit(db_path, directory, force=False, runner=None, error_log=None, label=None):
    """Queue an ingest of `directory`. Returns the job's status.

    A request for a folder that is already waiting is merged into the
    waiting one. When scan and derive finish, hashing is requested and
    runs in idle time.
    """
    runner = runner or jobs.runner

    def work(job):
        result = run(db_path, directory, force=force, should_stop=job.should_stop,
                     progress=job.progress.update, error_log=error_log, hash_now=False)
        if not result["cancelled"]:
            request_hashing(db_path, runner=runner)
        return result

    return runner.submit(
        f"ingest:{directory}", work, lane=jobs.LANE_QUEUE, kind=KIND_INGEST,
        label=label or f"Scan {directory}", meta={"directory": directory, "force": force, "mode": "full_cluster"})


def submit_derive(db_path, runner=None):
    """Queue a derive with no scan, for after Rigs, Filters or clustering rules change."""
    runner = runner or jobs.runner

    def work(job):
        job.progress.update({"step": "derive"})
        summary = derive(db_path)
        job.progress.update({"cluster_summary": summary})
        return {"scan": None, "library": None, "derived": summary, "hash": None, "cancelled": False, "failures": []}

    return runner.submit(DERIVE_KEY, work, lane=jobs.LANE_QUEUE, kind=KIND_DERIVE,
                         label="Regroup the library", meta={"mode": "cluster_only"})


def request_hashing(db_path, runner=None, everything_if_unscoped=False):
    """Ask for hashing in idle time. Returns the job's status, or None when there is nothing in scope."""
    runner = runner or jobs.runner
    if not everything_if_unscoped and not hash_scope(db_path):
        return None

    def work(job):
        return hash_pending(db_path, should_stop=job.should_stop, progress=job.progress.update,
                            everything_if_unscoped=everything_if_unscoped)

    return runner.submit(HASH_KEY, work, lane=jobs.LANE_FILLER, kind=KIND_HASH, label="Hash files")
