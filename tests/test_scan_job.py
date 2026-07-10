import threading
import time

import pytest

from astro_tracker import scan_job
from astro_tracker.scan_job import (
    MODE_CLUSTER_ONLY,
    MODE_FULL,
    MODE_FULL_CLUSTER,
    STATE_CANCELLED,
    STATE_DONE,
    STATE_FAILED,
    JobAlreadyRunningError,
    ScanJobManager,
)


def _wait_until_finished(manager, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = manager.current_status()
        if status is not None and status["state"] != "running":
            return status
        time.sleep(0.01)
    raise AssertionError("job did not finish within timeout")


def _make_blocking_scan(started_event, release_event):
    def fake_scan_directory(directory, db_path, error_log_path=None, progress_callback=None, should_stop=None):
        counts = {"new": 0, "updated": 0, "skipped": 0, "failed": 0, "total_seen": 0, "cancelled": False}
        started_event.set()
        while not release_event.is_set():
            if should_stop is not None and should_stop():
                counts["cancelled"] = True
                return counts
            time.sleep(0.01)
        counts["new"] = 1
        counts["total_seen"] = 1
        return counts

    return fake_scan_directory


class FakeConn:
    def close(self):
        pass


def _stub_storage(monkeypatch):
    monkeypatch.setattr(scan_job.storage, "connect", lambda db_path: FakeConn())
    monkeypatch.setattr(scan_job.storage, "init_schema", lambda conn: None)
    monkeypatch.setattr(scan_job.storage, "get_total_file_count", lambda conn: 0)
    monkeypatch.setattr(scan_job.storage, "get_category_breakdown", lambda conn: [])
    monkeypatch.setattr(scan_job.storage, "get_frame_type_breakdown", lambda conn: [])


def test_current_status_is_none_before_any_job_starts():
    manager = ScanJobManager()
    assert manager.current_status() is None


def test_start_with_invalid_mode_raises():
    manager = ScanJobManager()
    with pytest.raises(ValueError):
        manager.start("bogus_mode", "/some/dir", "test.db")


def test_cancel_with_no_running_job_returns_false():
    manager = ScanJobManager()
    assert manager.cancel() is False


def test_second_start_while_running_raises(monkeypatch):
    _stub_storage(monkeypatch)
    started = threading.Event()
    release = threading.Event()
    monkeypatch.setattr(scan_job.scanner, "scan_directory", _make_blocking_scan(started, release))

    manager = ScanJobManager()
    manager.start(MODE_FULL, "/some/dir", "test.db")
    assert started.wait(timeout=2), "fake scan never started"

    with pytest.raises(JobAlreadyRunningError):
        manager.start(MODE_FULL, "/some/dir", "test.db")

    release.set()
    _wait_until_finished(manager)


def test_cancel_stops_scan_before_completion(monkeypatch):
    _stub_storage(monkeypatch)
    started = threading.Event()
    release = threading.Event()
    monkeypatch.setattr(scan_job.scanner, "scan_directory", _make_blocking_scan(started, release))

    manager = ScanJobManager()
    manager.start(MODE_FULL, "/some/dir", "test.db")
    assert started.wait(timeout=2), "fake scan never started"

    assert manager.cancel() is True

    status = _wait_until_finished(manager)
    assert status["state"] == STATE_CANCELLED
    # Cancellation fired before the fake scan reached its "completed" branch.
    assert status["counts"]["new"] == 0


def test_cluster_only_mode_skips_scan_phase(monkeypatch):
    _stub_storage(monkeypatch)
    scan_called = []
    monkeypatch.setattr(
        scan_job.scanner, "scan_directory",
        lambda *a, **k: scan_called.append(True),
    )
    monkeypatch.setattr(
        scan_job.scanner, "run_clustering",
        lambda conn: {
            "target_groups": 2, "ungrouped_files": 0,
            "orphaned_groups": 0, "sessions": 2, "stale_sessions": 0,
        },
    )

    manager = ScanJobManager()
    manager.start(MODE_CLUSTER_ONLY, None, "test.db")
    status = _wait_until_finished(manager)

    assert scan_called == []
    assert status["state"] == STATE_DONE
    assert status["cluster_summary"]["target_groups"] == 2
    assert status["library_summary"] is None


def test_full_cluster_mode_runs_scan_then_clustering(monkeypatch):
    _stub_storage(monkeypatch)
    call_order = []

    def fake_scan_directory(directory, db_path, error_log_path=None, progress_callback=None, should_stop=None):
        call_order.append("scan")
        return {"new": 3, "updated": 0, "skipped": 0, "failed": 0, "total_seen": 3, "cancelled": False}

    def fake_run_clustering(conn):
        call_order.append("cluster")
        return {"target_groups": 1, "ungrouped_files": 0, "orphaned_groups": 0, "sessions": 1, "stale_sessions": 0}

    monkeypatch.setattr(scan_job.scanner, "scan_directory", fake_scan_directory)
    monkeypatch.setattr(scan_job.scanner, "run_clustering", fake_run_clustering)

    manager = ScanJobManager()
    manager.start(MODE_FULL_CLUSTER, "/some/dir", "test.db")
    status = _wait_until_finished(manager)

    assert call_order == ["scan", "cluster"]
    assert status["state"] == STATE_DONE
    assert status["counts"]["new"] == 3
    assert status["cluster_summary"]["target_groups"] == 1
    assert status["library_summary"] is not None


def test_full_mode_without_cluster_does_not_run_clustering(monkeypatch):
    _stub_storage(monkeypatch)
    cluster_called = []
    monkeypatch.setattr(
        scan_job.scanner, "scan_directory",
        lambda *a, **k: {"new": 1, "updated": 0, "skipped": 0, "failed": 0, "total_seen": 1, "cancelled": False},
    )
    monkeypatch.setattr(scan_job.scanner, "run_clustering", lambda conn: cluster_called.append(True))

    manager = ScanJobManager()
    manager.start(MODE_FULL, "/some/dir", "test.db")
    status = _wait_until_finished(manager)

    assert cluster_called == []
    assert status["state"] == STATE_DONE
    assert status["cluster_summary"] is None


def test_failures_are_collected_with_path_and_reason(monkeypatch):
    _stub_storage(monkeypatch)

    def fake_scan_directory(directory, db_path, error_log_path=None, progress_callback=None, should_stop=None):
        counts = {"new": 0, "updated": 0, "skipped": 0, "failed": 1, "total_seen": 1, "cancelled": False}
        if progress_callback:
            progress_callback(counts, "/bad/file.fits", "failed", "corrupt header")
        return counts

    monkeypatch.setattr(scan_job.scanner, "scan_directory", fake_scan_directory)

    manager = ScanJobManager()
    manager.start(MODE_FULL, "/some/dir", "test.db")
    status = _wait_until_finished(manager)

    assert status["failures"] == [{"path": "/bad/file.fits", "reason": "corrupt header"}]
    assert status["counts"]["failed"] == 1


def test_exception_during_scan_marks_job_failed(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("disk error")

    monkeypatch.setattr(scan_job.scanner, "scan_directory", boom)

    manager = ScanJobManager()
    manager.start(MODE_FULL, "/some/dir", "test.db")
    status = _wait_until_finished(manager)

    assert status["state"] == STATE_FAILED
    assert "disk error" in status["error"]


def test_new_job_can_start_after_previous_one_completes(monkeypatch):
    _stub_storage(monkeypatch)
    monkeypatch.setattr(
        scan_job.scanner, "scan_directory",
        lambda *a, **k: {"new": 1, "updated": 0, "skipped": 0, "failed": 0, "total_seen": 1, "cancelled": False},
    )

    manager = ScanJobManager()
    manager.start(MODE_FULL, "/some/dir", "test.db")
    _wait_until_finished(manager)

    # Should not raise -- the previous job is no longer "running".
    manager.start(MODE_FULL, "/some/other/dir", "test.db")
    status = _wait_until_finished(manager)
    assert status["state"] == STATE_DONE
