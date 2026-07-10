import os
import time

from astro_tracker import storage
from astro_tracker.scanner import scan_directory


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
