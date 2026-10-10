"""Background jobs keyed by name, for work started from the API or the scheduler.

A general form of the scan job manager (scan_job.py): each job runs in
its own thread, reports progress the UI can poll, and can be asked to
stop. Jobs are keyed (e.g. "hash", "pull:3") and at most one job per key
runs at a time, which is what stops two pulls of the same Source or two
hashing passes from overlapping. State is in memory only -- durable
history (such as Source runs) is written to the catalog by the job
itself.
"""

import threading
import time

STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_FAILED = "failed"
STATE_CANCELLED = "cancelled"


class JobAlreadyRunningError(Exception):
    pass


class Job:
    def __init__(self, key):
        self.key = key
        self.state = STATE_RUNNING
        self.progress = {}
        self.result = None
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
            "key": self.key,
            "state": self.state,
            "progress": dict(self.progress),
            "result": self.result,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class JobRunner:
    """Runs `fn(job)` in a background thread, one job per key at a time."""

    def __init__(self):
        self._lock = threading.Lock()
        self._jobs = {}

    def start(self, key, fn, wait=False):
        """Start `fn(job)` under `key`. Raises JobAlreadyRunningError if that key is running.

        `fn` returns the job's result. If it returns while the job was
        asked to stop, the job ends as cancelled. `wait=True` blocks
        until the job finishes (used by tests and the CLI).
        """
        with self._lock:
            current = self._jobs.get(key)
            if current is not None and current.state == STATE_RUNNING:
                raise JobAlreadyRunningError(f"'{key}' is already running")
            job = Job(key)
            self._jobs[key] = job

        thread = threading.Thread(target=self._run, args=(job, fn), daemon=True)
        thread.start()
        if wait:
            thread.join()
        return job.to_status_dict()

    def is_running(self, key):
        with self._lock:
            job = self._jobs.get(key)
            return job is not None and job.state == STATE_RUNNING

    def status(self, key):
        with self._lock:
            job = self._jobs.get(key)
            return job.to_status_dict() if job else None

    def cancel(self, key):
        with self._lock:
            job = self._jobs.get(key)
            if job is None or job.state != STATE_RUNNING:
                return False
            job.request_stop()
            return True

    def _run(self, job, fn):
        try:
            job.result = fn(job)
            job.state = STATE_CANCELLED if job.should_stop() else STATE_DONE
        except Exception as e:
            job.state = STATE_FAILED
            job.error = str(e)
        finally:
            job.finished_at = time.time()


runner = JobRunner()
