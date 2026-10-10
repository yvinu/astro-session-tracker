import hashlib
import os

from astro_tracker import hashing, library_storage, storage
from astro_tracker.scanner import scan_directory


def _scan(tmp_path, make_fits, names=("a.fits", "b.fits")):
    for name in names:
        make_fits(name, {"IMAGETYP": "Light Frame", "OBJECT": name})
    db = str(tmp_path / "c.db")
    scan_directory(str(tmp_path), db)
    return db


def _hash_of(conn, name):
    return conn.execute("SELECT content_hash FROM files WHERE file_name = ?", (name,)).fetchone()[0]


def test_hash_matches_an_independent_hash_of_the_same_bytes(tmp_path, make_fits):
    db = _scan(tmp_path, make_fits)
    counts = hashing.hash_pending(db)

    assert counts["hashed"] == 2 and counts["failed"] == 0
    conn = storage.connect(db)
    expected = hashlib.sha256((tmp_path / "a.fits").read_bytes()).hexdigest()
    assert _hash_of(conn, "a.fits") == expected


def test_second_pass_rehashes_nothing(tmp_path, make_fits):
    db = _scan(tmp_path, make_fits)
    hashing.hash_pending(db)
    assert hashing.hash_pending(db)["total"] == 0


def test_stopped_pass_resumes_with_only_what_is_left(tmp_path, make_fits):
    db = _scan(tmp_path, make_fits, names=("a.fits", "b.fits", "c.fits"))
    seen = []
    first = hashing.hash_pending(db, should_stop=lambda: len(seen) >= 1, progress=seen.append)

    assert first["cancelled"] and first["hashed"] == 1
    second = hashing.hash_pending(db)
    assert second["total"] == 2 and second["hashed"] == 2


def test_file_changed_and_rescanned_is_hashed_again(tmp_path, make_fits):
    db = _scan(tmp_path, make_fits)
    hashing.hash_pending(db)
    conn = storage.connect(db)
    before = _hash_of(conn, "a.fits")

    path = make_fits("a.fits", {"IMAGETYP": "Light Frame", "OBJECT": "changed"})
    os.utime(path, (1, 1))
    scan_directory(str(tmp_path), db)

    assert [os.path.basename(f["path"]) for f in library_storage.get_files_needing_hash(conn)] == ["a.fits"]
    hashing.hash_pending(db)
    assert _hash_of(conn, "a.fits") != before


def test_unreadable_file_is_recorded_as_failed_and_pass_continues(tmp_path, make_fits):
    db = _scan(tmp_path, make_fits)
    os.remove(tmp_path / "a.fits")

    counts = hashing.hash_pending(db)

    assert counts == {"hashed": 1, "failed": 1, "total": 2, "cancelled": False}
    conn = storage.connect(db)
    assert library_storage.get_hash_counts(conn) == {"hashed": 1, "failed": 1, "pending": 0, "total": 2}


def test_pass_can_be_limited_to_a_directory(tmp_path, make_fits):
    db = _scan(tmp_path, make_fits)
    other = tmp_path / "other_dir"
    assert hashing.hash_pending(db, path_prefixes=[str(other)])["total"] == 0
    assert hashing.hash_pending(db, path_prefixes=[str(tmp_path)])["total"] == 2


def test_prefix_filter_treats_underscore_literally(tmp_path, make_fits):
    db = _scan(tmp_path, make_fits)
    lookalike = str(tmp_path).replace(tmp_path.name, tmp_path.name[:-1] + "_") if not tmp_path.name.endswith("_") else None
    if lookalike:
        assert hashing.hash_pending(db, path_prefixes=[lookalike])["total"] == 0


def test_verify_distinguishes_ok_stale_mismatch_and_missing(tmp_path):
    path = tmp_path / "f.bin"
    path.write_bytes(b"abc")
    stat = os.stat(path)
    digest = hashing.hash_file(str(path))

    assert hashing.verify_file(str(path), digest, stat.st_size, stat.st_mtime) == hashing.VERIFY_OK
    assert hashing.verify_file(str(path), "0" * 64, stat.st_size, stat.st_mtime) == hashing.VERIFY_MISMATCH

    path.write_bytes(b"abcd")
    assert hashing.verify_file(str(path), digest, stat.st_size, stat.st_mtime) == hashing.VERIFY_STALE

    os.remove(path)
    assert hashing.verify_file(str(path), digest, stat.st_size, stat.st_mtime) == hashing.VERIFY_MISSING
