import os
import sqlite3
import time

from astro_tracker import storage
from astro_tracker.scanner import log_error, scan_directory


def test_first_scan_inserts_all_files(tmp_path, make_fits):
    make_fits("a.fits", {"IMAGETYP": "Light Frame", "OBJECT": "M31"})
    make_fits("b.fits", {"IMAGETYP": "Dark Frame"})
    db_path = str(tmp_path / "test.db")

    counts = scan_directory(str(tmp_path), db_path)

    assert counts["new"] == 2
    assert counts["updated"] == 0
    assert counts["skipped"] == 0
    assert counts["failed"] == 0

    conn = storage.connect(db_path)
    assert storage.get_total_file_count(conn) == 2
    conn.close()


def test_rescan_with_no_changes_skips_everything(tmp_path, make_fits):
    make_fits("a.fits", {"IMAGETYP": "Light Frame"})
    make_fits("b.fits", {"IMAGETYP": "Dark Frame"})
    db_path = str(tmp_path / "test.db")

    scan_directory(str(tmp_path), db_path)
    counts = scan_directory(str(tmp_path), db_path)

    assert counts["new"] == 0
    assert counts["updated"] == 0
    assert counts["skipped"] == 2
    assert counts["failed"] == 0


def test_modified_file_is_updated_not_duplicated(tmp_path, make_fits):
    path_a = make_fits("a.fits", {"IMAGETYP": "Light Frame", "OBJECT": "M31"})
    make_fits("b.fits", {"IMAGETYP": "Dark Frame"})
    db_path = str(tmp_path / "test.db")

    scan_directory(str(tmp_path), db_path)

    # Rewrite a.fits with different header content and bump its mtime forward.
    make_fits("a.fits", {"IMAGETYP": "Light Frame", "OBJECT": "M42"})
    future = time.time() + 5
    os.utime(path_a, (future, future))

    counts = scan_directory(str(tmp_path), db_path)

    assert counts["new"] == 0
    assert counts["updated"] == 1
    assert counts["skipped"] == 1

    conn = storage.connect(db_path)
    assert storage.get_total_file_count(conn) == 2  # no duplicate row
    row = conn.execute("SELECT target FROM files WHERE path = ?", (path_a,)).fetchone()
    assert row["target"] == "M42"
    conn.close()


def test_new_file_added_between_scans_is_inserted(tmp_path, make_fits):
    make_fits("a.fits", {"IMAGETYP": "Light Frame"})
    db_path = str(tmp_path / "test.db")

    scan_directory(str(tmp_path), db_path)

    make_fits("c.fits", {"IMAGETYP": "Flat Frame"})
    counts = scan_directory(str(tmp_path), db_path)

    assert counts["new"] == 1
    assert counts["skipped"] == 1

    conn = storage.connect(db_path)
    assert storage.get_total_file_count(conn) == 2
    conn.close()


def test_corrupt_file_is_logged_and_does_not_crash_scan(tmp_path, make_fits):
    make_fits("good.fits", {"IMAGETYP": "Light Frame"})
    bad_path = tmp_path / "bad.fits"
    bad_path.write_bytes(b"not a real fits file")
    db_path = str(tmp_path / "test.db")
    error_log = str(tmp_path / "errors.log")

    counts = scan_directory(str(tmp_path), db_path, error_log_path=error_log)

    assert counts["new"] == 1
    assert counts["failed"] == 1
    assert os.path.exists(error_log)
    with open(error_log) as f:
        assert "bad.fits" in f.read()


def test_failed_file_passes_reason_to_progress_callback(tmp_path):
    bad_path = tmp_path / "bad.fits"
    bad_path.write_bytes(b"not a real fits file")
    db_path = str(tmp_path / "test.db")

    calls = []

    def progress_callback(counts, file_path, status, detail=None):
        calls.append((file_path, status, detail))

    scan_directory(str(tmp_path), db_path, progress_callback=progress_callback)

    assert len(calls) == 1
    file_path, status, detail = calls[0]
    assert status == "failed"
    assert detail  # some non-empty reason string


def test_db_insert_failure_is_logged_and_scan_continues(tmp_path, make_fits, monkeypatch):
    make_fits("a.fits", {"IMAGETYP": "Light Frame"})
    make_fits("b.fits", {"IMAGETYP": "Dark Frame"})
    db_path = str(tmp_path / "test.db")
    error_log = str(tmp_path / "errors.log")

    original_upsert = storage.upsert_file

    def flaky_upsert(conn, path, mtime, size, metadata, force=False):
        if path.endswith("a.fits"):
            raise sqlite3.IntegrityError("UNIQUE constraint failed: files.path")
        return original_upsert(conn, path, mtime, size, metadata, force=force)

    monkeypatch.setattr(storage, "upsert_file", flaky_upsert)

    counts = scan_directory(str(tmp_path), db_path, error_log_path=error_log)

    assert counts["failed"] == 1
    assert counts["new"] == 1

    conn = storage.connect(db_path)
    assert storage.get_total_file_count(conn) == 1  # only b.fits made it in
    conn.close()

    with open(error_log) as f:
        content = f.read()
    assert "a.fits" in content
    assert "IntegrityError" in content


def test_db_insert_failure_passes_reason_to_progress_callback(tmp_path, make_fits, monkeypatch):
    make_fits("a.fits", {"IMAGETYP": "Light Frame"})
    db_path = str(tmp_path / "test.db")

    def always_fails(conn, path, mtime, size, metadata, force=False):
        raise sqlite3.IntegrityError("UNIQUE constraint failed: files.path")

    monkeypatch.setattr(storage, "upsert_file", always_fails)

    calls = []

    def progress_callback(counts, file_path, status, detail=None):
        calls.append((file_path, status, detail))

    scan_directory(str(tmp_path), db_path, progress_callback=progress_callback)

    assert len(calls) == 1
    file_path, status, detail = calls[0]
    assert status == "failed"
    assert "UNIQUE constraint failed" in detail


def test_log_error_includes_exception_type_name(tmp_path):
    error_log = str(tmp_path / "errors.log")
    log_error(error_log, "/some/file.fits", sqlite3.IntegrityError("UNIQUE constraint failed: files.path"))

    with open(error_log) as f:
        content = f.read()
    assert "IntegrityError" in content
    assert "UNIQUE constraint failed" in content


def test_log_error_accepts_plain_string_reason(tmp_path):
    error_log = str(tmp_path / "errors.log")
    log_error(error_log, "/some/file.fits", "Failed to extract metadata")

    with open(error_log) as f:
        content = f.read()
    assert "Failed to extract metadata" in content


def test_force_reparses_unchanged_file_and_updates_stored_fields(tmp_path, make_fits):
    path = make_fits("a.fits", {"IMAGETYP": "Light Frame", "OBJECT": "M31"})
    db_path = str(tmp_path / "test.db")

    scan_directory(str(tmp_path), db_path)
    original_mtime = os.stat(path).st_mtime

    # Rewrite the file's header content but restore the original mtime
    # afterward, simulating a field added after this file was already
    # scanned -- without --force, a plain rescan sees the unchanged mtime
    # and skips it, so the new header content never gets re-read.
    make_fits("a.fits", {"IMAGETYP": "Light Frame", "OBJECT": "M42"})
    os.utime(path, (original_mtime, original_mtime))

    counts = scan_directory(str(tmp_path), db_path)
    assert counts["skipped"] == 1

    conn = storage.connect(db_path)
    assert conn.execute("SELECT target FROM files WHERE path = ?", (path,)).fetchone()["target"] == "M31"
    conn.close()

    counts = scan_directory(str(tmp_path), db_path, force=True)
    assert counts["updated"] == 1
    assert counts["skipped"] == 0

    conn = storage.connect(db_path)
    assert conn.execute("SELECT target FROM files WHERE path = ?", (path,)).fetchone()["target"] == "M42"
    assert storage.get_total_file_count(conn) == 1  # still no duplicate row
    conn.close()


def test_normal_scan_is_not_marked_cancelled(tmp_path, make_fits):
    make_fits("a.fits", {"IMAGETYP": "Light Frame"})
    db_path = str(tmp_path / "test.db")

    counts = scan_directory(str(tmp_path), db_path)

    assert counts["cancelled"] is False


def test_should_stop_halts_scan_early_and_marks_cancelled(tmp_path, make_fits):
    for i in range(5):
        make_fits(f"f{i}.fits", {"IMAGETYP": "Light Frame"})
    db_path = str(tmp_path / "test.db")

    processed = []

    def progress_callback(counts, file_path, status, detail=None):
        processed.append(file_path)

    def should_stop():
        return len(processed) >= 2

    counts = scan_directory(
        str(tmp_path), db_path, progress_callback=progress_callback, should_stop=should_stop
    )

    assert counts["cancelled"] is True
    assert counts["total_seen"] == 2
    assert len(processed) == 2

    conn = storage.connect(db_path)
    assert storage.get_total_file_count(conn) == 2
    conn.close()


def test_symbolic_links_are_ignored_not_failed(tmp_path, make_fits):
    library = tmp_path / "library"
    library.mkdir()
    real = make_fits(library / "light_001.fits")
    os.symlink(real, library / "linked_00001.fits")
    os.symlink(tmp_path / "gone" / "light_002.fits", library / "linked_00002.fits")
    db_path = str(tmp_path / "test.db")
    error_log = tmp_path / "errors.log"

    counts = scan_directory(str(library), db_path, str(error_log))

    assert counts["new"] == 1
    assert counts["links"] == 2
    assert counts["failed"] == 0
    assert not error_log.exists()
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 1
    conn.close()
