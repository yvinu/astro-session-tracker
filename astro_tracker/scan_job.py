"""Background scan job manager for the /scan launch page.

Runs a directory scan (and/or clustering) in a background thread so the
browser UI can start a job, poll its progress, and cancel it, instead of
an HTTP request blocking for the duration of a full library scan. This is
a local, single-user, single-server-process tool, so a module-level
singleton holding at most one job at a time is sufficient -- no job
registry or persistence across server restarts is needed.
"""

import threading
import time

from astro_tracker import scanner, storage

MODE_FULL = "full"
MODE_FULL_CLUSTER = "full_cluster"
MODE_CLUSTER_ONLY = "cluster_only"
VALID_MODES = (MODE_FULL, MODE_FULL_CLUSTER, MODE_CLUSTER_ONLY)

STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_FAILED = "failed"
STATE_CANCELLED = "cancelled"


class JobAlreadyRunningError(Exception):
    pass


class ScanJob:
    """One scan run's mutable state, updated live from the background thread."""

    def __init__(self, job_id, mode, directory, db_path, force=False):
        self.job_id = job_id
        self.mode = mode
        self.directory = directory
        self.db_path = db_path
        self.force = force
        self.state = STATE_RUNNING
        self.counts = {"new": 0, "updated": 0, "skipped": 0, "failed": 0, "links": 0, "total_seen": 0, "cancelled": False}
        self.failures = []
        self.library_summary = None
        self.cluster_summary = None
        self.error = None
        self.started_at = time.time()
        self.finished_at = None
        self._stop_requested = threading.Event()

    def request_stop(self):
        self._stop_requested.set()

    def should_stop(self):
        return self._stop_requested.is_set()

    def to_status_dict(self):
        return {
            "job_id": self.job_id,
            "mode": self.mode,
            "directory": self.directory,
            "force": self.force,
            "state": self.state,
            "counts": dict(self.counts),
            "failures": list(self.failures),
            "library_summary": self.library_summary,
            "cluster_summary": self.cluster_summary,
            "error": self.error,
        }


class ScanJobManager:
    """Owns at most one running ScanJob at a time."""

    def __init__(self):
        self._lock = threading.Lock()
        self._job = None
        self._next_id = 1

    def current_status(self):
        with self._lock:
            if self._job is None:
                return None
            return self._job.to_status_dict()

    def start(self, mode, directory, db_path, force=False):
        if mode not in VALID_MODES:
            raise ValueError(f"Invalid mode: {mode}")

        with self._lock:
            if self._job is not None and self._job.state == STATE_RUNNING:
                raise JobAlreadyRunningError("A scan is already running")
            job = ScanJob(self._next_id, mode, directory, db_path, force=force)
            self._next_id += 1
            self._job = job

        thread = threading.Thread(target=self._run, args=(job,), daemon=True)
        thread.start()
        return job.to_status_dict()

    def cancel(self):
        with self._lock:
            job = self._job
            if job is None or job.state != STATE_RUNNING:
                return False
            job.request_stop()
            return True

    def _on_progress(self, job, counts, file_path, status, detail=None):
        job.counts.update(counts)
        if status == "failed":
            job.failures.append({"path": file_path, "reason": detail or "Unknown error"})

    def _run(self, job):
        try:
            if job.mode in (MODE_FULL, MODE_FULL_CLUSTER):
                final_counts = scanner.scan_directory(
                    job.directory,
                    job.db_path,
                    error_log_path=scanner.DEFAULT_ERROR_LOG,
                    progress_callback=lambda c, p, s, d=None: self._on_progress(job, c, p, s, d),
                    should_stop=job.should_stop,
                    force=job.force,
                )
                job.counts.update(final_counts)

                conn = storage.connect(job.db_path)
                storage.init_schema(conn)
                job.library_summary = {
                    "total_files": storage.get_total_file_count(conn),
                    "category_breakdown": storage.get_category_breakdown(conn),
                    "frame_type_breakdown": storage.get_frame_type_breakdown(conn),
                }
                conn.close()

                if final_counts.get("cancelled"):
                    job.state = STATE_CANCELLED
                    return

            if job.mode in (MODE_FULL_CLUSTER, MODE_CLUSTER_ONLY):
                conn = storage.connect(job.db_path)
                storage.init_schema(conn)
                job.cluster_summary = scanner.run_clustering(conn)
                conn.close()

            job.state = STATE_DONE
        except Exception as e:
            job.state = STATE_FAILED
            job.error = str(e)
        finally:
            job.finished_at = time.time()


job_manager = ScanJobManager()
