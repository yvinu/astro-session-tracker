"""The scan, activity and header-analysis routes, through HTTP against a real temporary catalog."""

import threading
import time

import pytest
from fastapi.testclient import TestClient

from astro_tracker import jobs, server, storage


def _wait_until(condition, seconds=10):
    deadline = time.time() + seconds
    while not condition():
        assert time.time() < deadline, "timed out"
        time.sleep(0.01)


@pytest.fixture
def site(tmp_path, make_fits, monkeypatch):
    """A folder of two subs configured as a library root, an empty catalog, and a client for the app."""
    folder = tmp_path / "library"
    folder.mkdir()
    for n in range(2):
        make_fits(f"tmp{n}.fits", {"IMAGETYP": "Light", "OBJECT": "M 31", "RA": 10.68, "DEC": 41.27,
                                   "DATE-OBS": f"2026-09-01T03:0{n}:00", "EXPTIME": 10.0 + n})
        (tmp_path / f"tmp{n}.fits").rename(folder / f"light_{n}.fits")
    db = str(tmp_path / "catalog.db")
    monkeypatch.setenv("ASTRO_LIBRARY_ROOTS", f"NAS={folder}")
    monkeypatch.setattr(server, "DB_PATH", db)
    monkeypatch.setattr(jobs, "runner", jobs.JobRunner())
    return TestClient(server.app), folder, db


def _idle(client):
    activity = client.get("/api/jobs").json()
    return not activity["running"] and not activity["waiting"]


def test_a_scan_started_over_http_catalogs_groups_and_hashes(site):
    client, folder, db = site

    started = client.post("/api/scan/start", json={"directory": str(folder)}).json()
    _wait_until(lambda: _idle(client))

    status = client.get(f"/api/scan/status?job_id={started['job_id']}").json()
    assert status["state"] == "done" and status["directory"] == str(folder)
    assert status["counts"]["new"] == 2 and status["library_summary"]["total_files"] == 2
    assert status["cluster_summary"]["target_groups"] == 1
    assert client.get("/api/hash/status").json()["counts"]["hashed"] == 2


def test_the_old_scan_only_mode_now_ingests_in_full(site):
    client, folder, db = site

    client.post("/api/scan/start", json={"mode": "full", "directory": str(folder)})
    _wait_until(lambda: _idle(client))

    assert client.get("/api/scan/status").json()["cluster_summary"]["target_groups"] == 1


def test_scan_start_rejects_a_missing_folder_and_an_unknown_mode(site):
    client, folder, db = site
    assert client.post("/api/scan/start", json={"directory": str(folder / "nope")}).status_code == 400
    assert client.post("/api/scan/start", json={"mode": "sideways", "directory": str(folder)}).status_code == 400
    assert client.post("/api/scan/start", json={"mode": "full_cluster"}).status_code == 400


def test_a_second_scan_waits_and_can_be_cancelled_from_the_activity_list(site):
    client, folder, db = site
    release = threading.Event()
    jobs.runner.submit("ingest:/busy", lambda job: release.wait(5), lane=jobs.LANE_QUEUE, kind="ingest", label="Scan /busy")
    _wait_until(lambda: jobs.runner.is_running("ingest:/busy"))

    waiting = client.post("/api/scan/start", json={"directory": str(folder)}).json()
    regroup = client.post("/api/scan/start", json={"mode": "cluster_only"}).json()

    assert waiting["state"] == "waiting" and waiting["waiting_behind"] == ["Scan /busy"]
    activity = client.get("/api/jobs").json()
    assert [j["label"] for j in activity["waiting"]] == [f"Scan {folder}", "Regroup the library"]

    assert client.post(f"/api/jobs/{waiting['job_id']}/cancel").json() == {"cancelled": True}
    assert client.post(f"/api/jobs/{waiting['job_id']}/cancel").status_code == 409
    assert client.get(f"/api/scan/status?job_id={waiting['job_id']}").json()["state"] == "cancelled"
    assert client.post("/api/jobs/cancel-waiting").json() == {"cancelled": 1}
    assert client.get(f"/api/scan/status?job_id={regroup['job_id']}").json()["state"] == "cancelled"

    release.set()
    _wait_until(lambda: _idle(client))
    conn = storage.connect(db)
    storage.init_schema(conn)
    assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0
    conn.close()


def test_scan_status_is_idle_before_any_scan(site):
    client, folder, db = site
    assert client.get("/api/scan/status").json() == {"state": "idle"}
    assert client.post("/api/scan/cancel").status_code == 409


def test_hashing_waits_while_a_scan_holds_the_queue(site):
    client, folder, db = site
    release = threading.Event()
    jobs.runner.submit("ingest:/busy", lambda job: release.wait(5), lane=jobs.LANE_QUEUE)
    _wait_until(lambda: jobs.runner.is_running("ingest:/busy"))

    assert client.post("/api/hash/start").json()["state"] == "waiting"
    assert client.get("/api/hash/status").json()["job"]["state"] == "waiting"
    assert client.post("/api/hash/cancel").json() == {"cancelled": True}
    assert client.post("/api/hash/cancel").status_code == 409
    release.set()
    _wait_until(lambda: _idle(client))


def test_header_analysis_runs_beside_the_queue_and_reports_results(site):
    client, folder, db = site
    release = threading.Event()
    jobs.runner.submit("ingest:/busy", lambda job: release.wait(5), lane=jobs.LANE_QUEUE)
    _wait_until(lambda: jobs.runner.is_running("ingest:/busy"))

    assert client.get("/api/header-analysis/status").json()["status"] == "idle"
    assert client.post("/api/header-analysis/start", json={"directory": str(folder)}).status_code == 200
    _wait_until(lambda: client.get("/api/header-analysis/status").json()["status"] != "running")

    status = client.get("/api/header-analysis/status").json()
    assert status["status"] == "completed" and status["progress_pct"] == 100.0 and status["results"]
    assert jobs.runner.is_running("ingest:/busy")
    release.set()
    _wait_until(lambda: _idle(client))


def test_the_activity_script_is_served(site):
    client, folder, db = site
    assert "activityPanel" in client.get("/static/activity.js").text
    assert client.get("/static/nope.js").status_code == 404


def test_restart_repair_marks_cut_off_pulls_and_reports_pending_hashes(site):
    client, folder, db = site
    client.post("/api/scan/start", json={"directory": str(folder)})
    _wait_until(lambda: _idle(client))
    assert server.repair_after_restart(db) is False

    conn = storage.connect(db)
    conn.execute("UPDATE files SET content_hash = NULL")
    conn.commit()
    conn.close()
    assert server.repair_after_restart(db) is True
