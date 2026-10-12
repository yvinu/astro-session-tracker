"""Background jobs for work started from the API or the scheduler.

One runner owns every background job, so that it can decide what may
run at the same time. Each job is submitted to one of three lanes:

- LANE_QUEUE: work that rewrites the catalog (scan and derive). One
  runs at a time, in the order submitted. A second request with the
  same key as one already waiting is merged into it.
- LANE_FILLER: work that should use idle time (hashing). It runs only
  while the queue is empty, stops when something joins the queue, and
  is resumed afterwards.
- LANE_FREE: work that touches nothing the others do (copying from a
  device, header analysis). It runs at once, one job per key.

A job reports progress the pages can poll and can be cancelled while
waiting or running. State is in memory only: every job is safe to
repeat, and durable history (such as Source runs) is written to the
catalog by the job itself.
"""

import threading
import time

LANE_QUEUE = "queue"
LANE_FILLER = "filler"
LANE_FREE = "free"

STATE_WAITING = "waiting"
STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_FAILED = "failed"
STATE_CANCELLED = "cancelled"

ACTIVE_STATES = (STATE_WAITING, STATE_RUNNING)
FINISHED_KEPT = 30


class JobAlreadyRunningError(Exception):
    pass


class Job:
    def __init__(self, job_id, key, lane, kind=None, label=None, meta=None):
        self.id = job_id
        self.key = key
        self.lane = lane
        self.kind = kind or key
        self.label = label or key
        self.meta = dict(meta or {})
        self.state = STATE_WAITING
        self.progress = {}
        self.result = None
        self.error = None
        self.created_at = time.time()
        self.started_at = None
        self.finished_at = None
        self.paused = False
        self._stop_requested = threading.Event()
        self._finished = threading.Event()
        self._must_yield = None

    def request_stop(self):
        self._stop_requested.set()

    def should_stop(self):
        """True when the job was cancelled, or (for a filler job) when queued work is waiting for its turn."""
        if self._stop_requested.is_set():
            return True
        if self._must_yield is not None and self._must_yield():
            self.paused = True
            return True
        return False

    def to_status_dict(self):
        return {
            "id": self.id,
            "key": self.key,
            "kind": self.kind,
            "label": self.label,
            "lane": self.lane,
            "meta": dict(self.meta),
            "state": self.state,
            "paused": self.paused,
            "progress": dict(self.progress),
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class JobRunner:
    def __init__(self):
        self._cond = threading.Condition()
        self._jobs = {}
        self._queue = []
        self._fillers = []
        self._next_id = 1
        self._worker = None

    # ---- submitting ---------------------------------------------------------

    def submit(self, key, fn, lane=LANE_QUEUE, kind=None, label=None, meta=None, wait=False):
        """Submit `fn(job)` under `key` and return the job's status.

        `fn` returns the job's result. A queued or filler request whose
        key matches a job that is already waiting returns that job
        instead of adding another. A free job whose key is already
        running raises JobAlreadyRunningError. `wait=True` blocks until
        the job has finished (used by tests and the command line).
        """
        existing = None
        with self._cond:
            if lane == LANE_FREE:
                if any(j.key == key and j.state == STATE_RUNNING for j in self._jobs.values()):
                    raise JobAlreadyRunningError(f"'{key}' is already running")
            else:
                for candidate in self._jobs.values():
                    merge = candidate.state == STATE_WAITING or (
                        lane == LANE_FILLER and candidate.state == STATE_RUNNING)
                    if candidate.key == key and candidate.lane == lane and merge:
                        existing = candidate
                        break
        if existing is not None:
            if wait:
                existing._finished.wait()
            return existing.to_status_dict()

        with self._cond:
            job = Job(self._next_id, key, lane, kind, label, meta)
            job._fn = fn
            self._next_id += 1
            self._jobs[job.id] = job

            if lane == LANE_FREE:
                job.state = STATE_RUNNING
                job.started_at = time.time()
                threading.Thread(target=self._run_free, args=(job,), daemon=True).start()
            else:
                if lane == LANE_FILLER:
                    job._must_yield = self._queue_has_work
                    self._fillers.append(job)
                else:
                    self._queue.append(job)
                self._ensure_worker()
                self._cond.notify_all()

        if wait:
            job._finished.wait()
        return job.to_status_dict()

    def start(self, key, fn, wait=False):
        """Run `fn(job)` at once in the free lane. Raises JobAlreadyRunningError if that key is running."""
        return self.submit(key, fn, lane=LANE_FREE, wait=wait)

    # ---- inspecting ---------------------------------------------------------

    def status(self, key):
        """Status of the most recently submitted job with this key, or None."""
        with self._cond:
            matching = [j for j in self._jobs.values() if j.key == key]
            return max(matching, key=lambda j: j.id).to_status_dict() if matching else None

    def get(self, job_id):
        with self._cond:
            job = self._jobs.get(job_id)
            return job.to_status_dict() if job else None

    def is_running(self, key):
        with self._cond:
            return any(j.key == key and j.state == STATE_RUNNING for j in self._jobs.values())

    def is_active(self, key):
        """Whether a job with this key is waiting or running."""
        with self._cond:
            return any(j.key == key and j.state in ACTIVE_STATES for j in self._jobs.values())

    def list(self):
        """Running jobs, then waiting jobs in the order they will run, then recently finished ones."""
        with self._cond:
            running = [j for j in self._jobs.values() if j.state == STATE_RUNNING]
            waiting = list(self._queue) + [j for j in self._fillers if j.state == STATE_WAITING]
            finished = sorted((j for j in self._jobs.values() if j.state not in ACTIVE_STATES),
                              key=lambda j: j.finished_at or 0, reverse=True)
            return {
                "running": [j.to_status_dict() for j in sorted(running, key=lambda j: j.started_at or 0)],
                "waiting": [j.to_status_dict() for j in waiting],
                "finished": [j.to_status_dict() for j in finished[:10]],
            }

    # ---- cancelling ---------------------------------------------------------

    def cancel_job(self, job_id):
        """Cancel one waiting or running job. Returns False if it is not active."""
        with self._cond:
            job = self._jobs.get(job_id)
            if job is None or job.state not in ACTIVE_STATES:
                return False
            self._cancel(job)
            return True

    def cancel(self, key):
        """Cancel every waiting or running job with this key. Returns False if there was none."""
        with self._cond:
            active = [j for j in self._jobs.values() if j.key == key and j.state in ACTIVE_STATES]
            for job in active:
                self._cancel(job)
            return bool(active)

    def cancel_waiting(self):
        """Cancel every job that has not started. Returns how many were cancelled."""
        with self._cond:
            waiting = [j for j in self._jobs.values() if j.state == STATE_WAITING]
            for job in waiting:
                self._cancel(job)
            return len(waiting)

    def _cancel(self, job):
        job.request_stop()
        if job.state == STATE_WAITING:
            if job in self._queue:
                self._queue.remove(job)
            if job in self._fillers:
                self._fillers.remove(job)
            self._finish(job, STATE_CANCELLED)

    # ---- running ------------------------------------------------------------

    def _queue_has_work(self):
        return bool(self._queue)

    def _ensure_worker(self):
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(target=self._work, daemon=True)
            self._worker.start()

    def _work(self):
        """Run queued jobs one at a time, and a filler job whenever the queue is empty."""
        while True:
            with self._cond:
                while not self._queue and not self._fillers:
                    self._cond.wait()
                job = self._queue.pop(0) if self._queue else self._fillers.pop(0)
                job.state = STATE_RUNNING
                job.paused = False
                job.started_at = job.started_at or time.time()
            self._execute(job)

    def _run_free(self, job):
        self._execute(job)

    def _execute(self, job):
        try:
            result = job._fn(job)
        except Exception as e:
            with self._cond:
                job.error = str(e)
                self._finish(job, STATE_FAILED)
            return
        with self._cond:
            job.result = result
            if job._stop_requested.is_set():
                self._finish(job, STATE_CANCELLED)
            elif job.paused:
                # A filler job that gave way to queued work goes back to wait for the queue to empty.
                job.state = STATE_WAITING
                self._fillers.append(job)
                self._cond.notify_all()
            else:
                self._finish(job, STATE_DONE)

    def _finish(self, job, state):
        job.state = state
        job.finished_at = time.time()
        job._finished.set()
        finished = sorted((j for j in self._jobs.values() if j.state not in ACTIVE_STATES),
                          key=lambda j: j.finished_at or 0)
        for old in finished[:-FINISHED_KEPT]:
            del self._jobs[old.id]


runner = JobRunner()
