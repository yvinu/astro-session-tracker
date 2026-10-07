import os
from datetime import datetime, timedelta, timezone

import pytest

from astro_tracker import jobs, library_storage, source_runs, storage

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
OLD = 1_000_000.0


def _source(**overrides):
    return {"enabled": True, "interval_minutes": 60, **overrides}


def test_never_run_source_is_due():
    assert source_runs.is_due(_source(), None, NOW)


def test_due_only_after_a_full_interval():
    assert not source_runs.is_due(_source(), (NOW - timedelta(minutes=59)).isoformat(), NOW)
    assert source_runs.is_due(_source(), (NOW - timedelta(minutes=60)).isoformat(), NOW)


def test_disabled_or_unscheduled_source_is_never_due():
    assert not source_runs.is_due(_source(enabled=False), None, NOW)
    assert not source_runs.is_due(_source(interval_minutes=0), None, NOW)


@pytest.fixture
def setup(tmp_path, make_fits):
    """A catalog with one Seestar Source whose device folder holds one sub and one device stack."""
    device, mirror = tmp_path / "device", tmp_path / "mirror"
    (device / "M 31_sub").mkdir(parents=True)
    (device / "M 31").mkdir()
    mirror.mkdir()
    for rel, cards in (("M 31_sub/a.fit", {"IMAGETYP": "Light", "OBJECT": "M 31", "FILTER": "IRCUT"}),
                       ("M 31/Stacked_2_M 31.fit", {"IMAGETYP": "Light", "OBJECT": "M 31"})):
        made = make_fits("tmp.fit", cards)
        os.replace(made, device / rel)
        os.utime(device / rel, (OLD, OLD))

    db = str(tmp_path / "c.db")
    conn = storage.connect(db)
    storage.init_schema(conn)
    source = library_storage.create_source(conn, {
        "name": "S50", "transport": "mounted_share", "profile": "seestar",
        "source_dir": str(device), "mirror_dir": str(mirror), "host": "s50.local",
        "interval_minutes": 60, "stability_seconds": 600, "enabled": 1,
    })
    return db, conn, source, device, mirror


def test_pull_copies_catalogs_and_records_the_run(setup):
    db, conn, source, device, mirror = setup

    result = source_runs.run_pull(db, source["id"], ping_fn=lambda h: True)

    assert result["outcome"] == "ok" and result["files_copied"] == 2
    run = library_storage.get_last_source_run(conn, source["id"])
    assert (run["outcome"], run["files_copied"], run["finished_at"] is not None) == ("ok", 2, True)
    rows = {r["file_name"]: dict(r) for r in conn.execute(
        "SELECT file_name, source_id, file_category, filter_canonical, mtime FROM files")}
    assert rows["a.fit"]["source_id"] == source["id"] and rows["a.fit"]["file_category"] == "Subframe"
    assert rows["a.fit"]["filter_canonical"] == "UVIR" and rows["a.fit"]["mtime"] == OLD
    assert rows["Stacked_2_M 31.fit"]["file_category"] == "Device Stack"


def test_device_switched_off_is_recorded_as_unreachable_not_error(setup):
    db, conn, source, device, mirror = setup

    result = source_runs.run_pull(db, source["id"], ping_fn=lambda h: False)

    assert result["outcome"] == "unreachable"
    assert library_storage.get_last_source_run(conn, source["id"])["outcome"] == "unreachable"
    assert list(mirror.iterdir()) == []


def test_second_pull_copies_nothing_and_still_records_a_run(setup):
    db, conn, source, device, mirror = setup
    source_runs.run_pull(db, source["id"], ping_fn=lambda h: True)
    result = source_runs.run_pull(db, source["id"], ping_fn=lambda h: True)

    assert result["files_copied"] == 0 and result["outcome"] == "ok"
    assert len(library_storage.get_source_runs(conn, source["id"])) == 2


def test_differing_device_file_is_reported_in_the_run(setup):
    db, conn, source, device, mirror = setup
    (mirror / "M 31_sub").mkdir()
    (mirror / "M 31_sub/a.fit").write_bytes(b"short")

    source_runs.run_pull(db, source["id"], ping_fn=lambda h: True)

    run = library_storage.get_last_source_run(conn, source["id"])
    assert run["differing"] == 1 and "M 31_sub/a.fit" in run["detail"]
    assert (mirror / "M 31_sub/a.fit").read_bytes() == b"short"


def test_tick_starts_due_sources_once(setup, monkeypatch):
    db, conn, source, device, mirror = setup
    monkeypatch.setattr(source_runs.source_pull, "ping", lambda h: False)
    started = []

    class FakeRunner:
        def is_running(self, key):
            return False

        def start(self, key, fn, wait=False):
            started.append(key)
            library_storage.start_source_run(conn, source["id"])

    assert source_runs.tick(db, runner=FakeRunner()) == [source["id"]]
    assert source_runs.tick(db, runner=FakeRunner()) == []
    assert started == [f"pull:{source['id']}"]


def test_pull_now_is_rejected_while_that_source_is_running(setup):
    db, conn, source, device, mirror = setup
    import threading
    release = threading.Event()
    runner = jobs.JobRunner()
    runner.start(f"pull:{source['id']}", lambda job: release.wait(5))
    with pytest.raises(jobs.JobAlreadyRunningError):
        source_runs.start_pull_job(db, source["id"], runner)
    release.set()


def test_deleting_a_source_keeps_its_files_and_mirror(setup):
    db, conn, source, device, mirror = setup
    source_runs.run_pull(db, source["id"], ping_fn=lambda h: True)

    assert library_storage.delete_source(conn, source["id"])
    assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM source_runs").fetchone()[0] == 0
    assert (mirror / "M 31_sub/a.fit").exists()
