"""Run a Source pull end to end, and decide when Sources are due.

run_pull is what a scheduled or "pull now" job executes: check the
device is there, copy what the mirror is missing (source_pull.py),
record the run, and catalog what arrived. The scheduler is a small loop
that starts a pull job for each Source whose interval has passed.
"""

import threading
from datetime import datetime, timedelta, timezone

from astro_tracker import backup, config, jobs, library_storage, scanner, source_pull, storage

OUTCOME_OK = "ok"
OUTCOME_UNREACHABLE = "unreachable"
OUTCOME_ERROR = "error"
OUTCOME_CANCELLED = "cancelled"


def run_pull(db_path, source_id, should_stop=None, progress=None, ping_fn=source_pull.ping, now=None):
    """Pull one Source and record the run. Returns the run's summary dict.

    A device that is switched off is the normal case between sessions,
    so it ends the run as "unreachable" -- recorded, but not an error.
    Files that could not be copied make the run an error while everything
    that did copy is kept and catalogued.
    """
    conn = storage.connect(db_path)
    storage.init_schema(conn)
    source = library_storage.get_source(conn, source_id)
    if source is None:
        conn.close()
        raise ValueError(f"No Source with id {source_id}")
    run_id = library_storage.start_source_run(conn, source_id)

    try:
        if not source_pull.is_reachable(source["source_dir"], source["host"], ping_fn):
            library_storage.finish_source_run(conn, run_id, OUTCOME_UNREACHABLE)
            return {"run_id": run_id, "outcome": OUTCOME_UNREACHABLE, "files_copied": 0}

        select = source_pull.PROFILES.get(source["profile"], source_pull.select_all)
        summary = source_pull.pull(
            source["source_dir"], source["mirror_dir"], select,
            now=now, stability_seconds=source["stability_seconds"],
            should_stop=should_stop, progress=progress,
        )

        details = []
        if summary["errors"]:
            details.append("; ".join(f"{rel}: {reason}" for rel, reason in summary["errors"][:20]))
        if summary["differing"]:
            details.append("Differs from the mirror copy (not overwritten): " + ", ".join(summary["differing"][:20]))
        outcome = (OUTCOME_ERROR if summary["errors"]
                   else OUTCOME_CANCELLED if summary["cancelled"] else OUTCOME_OK)
        library_storage.finish_source_run(
            conn, run_id, outcome,
            files_copied=len(summary["copied"]), bytes_copied=summary["bytes"],
            held_back=summary["recent"], differing=len(summary["differing"]),
            detail=" | ".join(details) or None,
        )
    except Exception as e:
        library_storage.finish_source_run(conn, run_id, OUTCOME_ERROR, detail=str(e))
        conn.close()
        raise

    result = {
        "run_id": run_id, "outcome": outcome, "files_copied": len(summary["copied"]),
        "bytes_copied": summary["bytes"], "held_back": summary["recent"], "differing": len(summary["differing"]),
    }
    if summary["copied"]:
        result["scan"] = scanner.scan_directory(source["mirror_dir"], db_path)
        result["derived"] = scanner.run_clustering(conn)
    else:
        library_storage.tag_source_files(conn)
    conn.close()
    return result


def is_due(source, last_started_at, now):
    """Whether a Source should be pulled now.

    Due when it is enabled, has a positive interval, and either has never
    run or last started at least one interval ago. Measured from the
    start of the last run -- reachable or not -- so a powered-off device
    is retried once per interval rather than every scheduler tick.
    """
    if not source["enabled"] or not source["interval_minutes"] or source["interval_minutes"] <= 0:
        return False
    if not last_started_at:
        return True
    last = datetime.fromisoformat(last_started_at)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return now - last >= timedelta(minutes=source["interval_minutes"])


def start_pull_job(db_path, source_id, runner=jobs.runner):
    """Start a background pull for one Source. Raises jobs.JobAlreadyRunningError if it is already running."""
    def work(job):
        return run_pull(db_path, source_id, should_stop=job.should_stop, progress=job.progress.update)
    return runner.start(f"pull:{source_id}", work)


def tick(db_path, now=None, runner=jobs.runner):
    """One scheduler pass: start a pull for every due Source, and take the nightly catalog snapshot.

    Returns the ids of Sources a pull was started for.
    """
    now = now or datetime.now(timezone.utc)
    conn = storage.connect(db_path)
    storage.init_schema(conn)
    started = []
    try:
        for source in library_storage.get_sources(conn):
            last = library_storage.get_last_source_run(conn, source["id"])
            if runner.is_running(f"pull:{source['id']}"):
                continue
            if is_due(source, last["started_at"] if last else None, now):
                try:
                    start_pull_job(db_path, source["id"], runner)
                    started.append(source["id"])
                except jobs.JobAlreadyRunningError:
                    pass
    finally:
        conn.close()

    backup_dir = config.backup_dir()
    if backup_dir and backup.snapshot_is_due(backup_dir, now):
        backup.snapshot(db_path, backup_dir, keep=config.backup_keep())
    return started


class Scheduler:
    """Calls tick() once a minute on a daemon thread."""

    def __init__(self, db_path, interval_seconds=60):
        self.db_path = db_path
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            try:
                tick(self.db_path)
            except Exception as e:  # a bad tick must not end scheduling
                print(f"Scheduler tick failed: {e}")
            self._stop.wait(self.interval_seconds)
