import threading
import time

import pytest

from astro_tracker import ingest, jobs, library_storage, storage


def _wait_until(condition, seconds=10):
    deadline = time.time() + seconds
    while not condition():
        assert time.time() < deadline, "timed out"
        time.sleep(0.01)


@pytest.fixture
def library(tmp_path, make_fits, monkeypatch):
    """A folder of three subs of one target, configured as a library root, and an empty catalog."""
    folder = tmp_path / "library"
    folder.mkdir()
    for n in range(3):
        made = make_fits(f"tmp{n}.fits", {
            "IMAGETYP": "Light", "OBJECT": "M 31", "RA": 10.68, "DEC": 41.27, "EXPTIME": 10.0 + n,
            "DATE-OBS": f"2026-09-01T03:0{n}:00", "INSTRUME": "ZWO ASI294MC Pro", "FOCALLEN": 372.5,
        })
        (tmp_path / f"tmp{n}.fits").rename(folder / f"light_{n}.fits")
    monkeypatch.setenv("ASTRO_LIBRARY_ROOTS", f"NAS={folder}")
    return str(tmp_path / "catalog.db"), folder


def _counts(db):
    conn = storage.connect(db)
    try:
        return {
            "files": conn.execute("SELECT COUNT(*) FROM files").fetchone()[0],
            "grouped": conn.execute("SELECT COUNT(*) FROM files WHERE target_group_id IS NOT NULL").fetchone()[0],
            "in_session": conn.execute("SELECT COUNT(*) FROM files WHERE session_id IS NOT NULL").fetchone()[0],
            "hashed": library_storage.get_hash_counts(conn)["hashed"],
        }
    finally:
        conn.close()


def test_ingest_scans_derives_and_hashes(library):
    db, folder = library

    result = ingest.run(db, str(folder))

    assert result["scan"]["new"] == 3 and result["cancelled"] is False
    assert result["derived"]["target_groups"] == 1 and result["derived"]["sessions"] == 1
    assert result["hash"]["hashed"] == 3
    assert _counts(db) == {"files": 3, "grouped": 3, "in_session": 3, "hashed": 3}


def test_ingest_reports_each_step_as_it_goes(library):
    db, folder = library
    steps = []

    ingest.run(db, str(folder), progress=lambda update: steps.append(update["step"]))

    assert [s for i, s in enumerate(steps) if i == 0 or steps[i - 1] != s] == ["scan", "derive", "hash"]


def test_files_outside_the_hash_scope_are_catalogued_but_not_hashed(library, monkeypatch):
    db, folder = library
    monkeypatch.delenv("ASTRO_LIBRARY_ROOTS")

    result = ingest.run(db, str(folder))

    assert result["hash"]["skipped"]
    assert _counts(db) == {"files": 3, "grouped": 3, "in_session": 3, "hashed": 0}


def test_a_source_mirror_is_in_the_hash_scope_without_being_a_library_root(library, monkeypatch):
    db, folder = library
    monkeypatch.delenv("ASTRO_LIBRARY_ROOTS")
    conn = storage.connect(db)
    storage.init_schema(conn)
    library_storage.create_source(conn, {
        "name": "S50", "transport": "mounted_share", "profile": "all", "source_dir": "/nowhere",
        "mirror_dir": str(folder), "host": None, "interval_minutes": 0, "stability_seconds": 0, "enabled": 1,
    })
    conn.close()

    assert ingest.hash_scope(db) == [str(folder)]
    assert ingest.run(db, str(folder))["hash"]["hashed"] == 3


def test_a_stopped_scan_keeps_what_it_read_and_is_not_followed_by_derive(library):
    db, folder = library
    seen = []

    def stop_after_one():
        return len(seen) >= 1

    result = ingest.run(db, str(folder), should_stop=stop_after_one,
                        progress=lambda update: seen.append(update) if update.get("current") else None)

    assert result["cancelled"] is True and result["derived"] is None and result["hash"] is None
    assert _counts(db)["files"] == 1 and _counts(db)["grouped"] == 0

    again = ingest.run(db, str(folder))
    assert again["scan"]["new"] == 2 and again["scan"]["skipped"] == 1
    assert _counts(db) == {"files": 3, "grouped": 3, "in_session": 3, "hashed": 3}


def test_failed_files_are_reported_with_their_reason(library):
    db, folder = library
    (folder / "broken.fits").write_bytes(b"not a fits file")

    result = ingest.run(db, str(folder))

    assert result["scan"]["failed"] == 1
    assert [f["path"] for f in result["failures"]] == [str(folder / "broken.fits")]
    assert result["failures"][0]["reason"]


def test_derive_alone_regroups_without_reading_the_disk(library):
    db, folder = library
    ingest.run(db, str(folder))
    for path in folder.iterdir():
        path.unlink()

    summary = ingest.derive(db)

    assert summary["target_groups"] == 1 and summary["sessions"] == 1
    assert _counts(db)["grouped"] == 3


def test_a_submitted_ingest_scans_and_derives_in_the_queue_then_hashes_in_idle_time(library):
    db, folder = library
    runner = jobs.JobRunner()

    job = ingest.submit(db, str(folder), runner=runner)
    _wait_until(lambda: runner.get(job["id"])["state"] == jobs.STATE_DONE)
    _wait_until(lambda: (runner.status(ingest.HASH_KEY) or {}).get("state") == jobs.STATE_DONE)

    finished = runner.get(job["id"])
    assert finished["lane"] == jobs.LANE_QUEUE and finished["result"]["hash"] is None
    assert finished["progress"]["cluster_summary"]["target_groups"] == 1
    assert runner.status(ingest.HASH_KEY)["lane"] == jobs.LANE_FILLER
    assert _counts(db) == {"files": 3, "grouped": 3, "in_session": 3, "hashed": 3}


def test_two_submitted_ingests_never_derive_at_the_same_time(library, monkeypatch):
    db, folder = library
    runner = jobs.JobRunner()
    active, overlaps = [0], []
    real_derive = ingest.derive

    def watched_derive(db_path):
        active[0] += 1
        overlaps.append(active[0])
        time.sleep(0.05)
        try:
            return real_derive(db_path)
        finally:
            active[0] -= 1

    monkeypatch.setattr(ingest, "derive", watched_derive)
    first = ingest.submit(db, str(folder), runner=runner)
    second = ingest.submit_derive(db, runner=runner)

    _wait_until(lambda: runner.get(second["id"])["state"] == jobs.STATE_DONE)
    assert runner.get(first["id"])["state"] == jobs.STATE_DONE
    assert overlaps == [1, 1]


def test_hashing_is_not_requested_when_nothing_is_in_scope(library, monkeypatch):
    db, folder = library
    monkeypatch.delenv("ASTRO_LIBRARY_ROOTS")
    runner = jobs.JobRunner()

    assert ingest.request_hashing(db, runner=runner) is None
    explicit = ingest.request_hashing(db, runner=runner, everything_if_unscoped=True)
    assert explicit["kind"] == ingest.KIND_HASH
