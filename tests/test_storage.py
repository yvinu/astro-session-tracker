"""Storage layer is generally out of test scope for this project (see PRD.md), but
save_clustering's orphan cleanup previously crashed the whole scan with a real
FOREIGN KEY constraint failure whenever an orphaned target group had sessions --
this is a regression test for that specific fix, not general storage coverage.
"""

from astro_tracker import storage


def test_orphaned_target_group_with_sessions_is_cleaned_up_not_crashed(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = storage.connect(db_path)
    storage.init_schema(conn)

    # Seed a file clustered into group A, with a session (and annotation) hanging off it.
    now = storage._now()
    conn.execute(
        """INSERT INTO files (path, mtime, size, target, date, first_seen_at, last_updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("/a.fits", 1.0, 100, "M31", "2026-07-01", now, now),
    )
    file_id = conn.execute("SELECT id FROM files WHERE path = '/a.fits'").fetchone()["id"]
    cursor = conn.execute("INSERT INTO target_groups (created_at, updated_at) VALUES (?, ?)", (now, now))
    group_a = cursor.lastrowid
    conn.execute("UPDATE files SET target_group_id = ? WHERE id = ?", (group_a, file_id))
    cursor = conn.execute(
        "INSERT INTO sessions (target_group_id, observation_night, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (group_a, "2026-07-01", now, now),
    )
    session_id = cursor.lastrowid
    conn.execute(
        "INSERT INTO session_annotations (session_id, rating, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (session_id, 5, now, now),
    )
    # Files also reference sessions.id directly (files.session_id), same as
    # real post-clustering data would -- this is what the first version of
    # the fix (which only nulled target_group_id) missed.
    conn.execute("UPDATE files SET session_id = ? WHERE id = ?", (session_id, file_id))
    conn.commit()

    # Re-cluster with a result that doesn't include file_id at all (e.g. its
    # coordinates became unparseable) -- group_a no longer overlaps any new
    # cluster, so it's orphaned. This must not raise.
    storage.save_clustering(conn, {file_id: None})

    assert conn.execute("SELECT 1 FROM target_groups WHERE id = ?", (group_a,)).fetchone() is None
    assert conn.execute("SELECT 1 FROM sessions WHERE target_group_id = ?", (group_a,)).fetchone() is None
    assert conn.execute("SELECT 1 FROM session_annotations WHERE session_id = ?", (session_id,)).fetchone() is None

    conn.close()


def _insert_file(conn, path, exposure, first_seen_at, size=100, frame_type="Light"):
    now = storage._now()
    conn.execute(
        "INSERT INTO files (path, mtime, size, exposure, frame_type, first_seen_at, last_updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (path, 1.0, size, exposure, frame_type, first_seen_at, now),
    )
    return conn.execute("SELECT id FROM files WHERE path = ?", (path,)).fetchone()["id"]


def test_duplicate_group_counts_once_toward_aggregate_totals(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = storage.connect(db_path)
    storage.init_schema(conn)

    # Two physical copies of the same sub (different drives), plus one
    # unrelated, non-duplicated file.
    id_a = _insert_file(conn, "/a.fits", exposure=30.0, first_seen_at="2026-01-01T00:00:00")
    id_b = _insert_file(conn, "/b.fits", exposure=30.0, first_seen_at="2026-01-02T00:00:00")
    _insert_file(conn, "/c.fits", exposure=10.0, first_seen_at="2026-01-01T00:00:00")
    conn.commit()

    now = storage._now()
    cursor = conn.execute("INSERT INTO duplicate_groups (created_at, updated_at) VALUES (?, ?)", (now, now))
    group_id = cursor.lastrowid
    conn.execute("UPDATE files SET duplicate_group_id = ? WHERE id IN (?, ?)", (group_id, id_a, id_b))
    conn.commit()

    exclude_ids = storage.get_duplicate_exclusion_ids(conn)
    assert exclude_ids == {id_b}  # a.fits is the earlier first_seen_at, so b.fits (the redundant copy) is excluded

    assert storage.get_total_file_count(conn) == 3  # unaffected without exclude_ids (e.g. scan CLI summary)
    assert storage.get_total_file_count(conn, exclude_ids) == 2  # a + c, not b
    assert storage.get_total_exposure(conn, exclude_ids) == 40.0  # 30 (a) + 10 (c), not 30 + 30 + 10

    conn.close()


def test_get_files_for_target_group_excludes_redundant_duplicate_copies(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = storage.connect(db_path)
    storage.init_schema(conn)

    id_a = _insert_file(conn, "/a.fits", exposure=30.0, first_seen_at="2026-01-01T00:00:00")
    id_b = _insert_file(conn, "/b.fits", exposure=30.0, first_seen_at="2026-01-02T00:00:00")
    conn.commit()

    now = storage._now()
    cursor = conn.execute("INSERT INTO target_groups (created_at, updated_at) VALUES (?, ?)", (now, now))
    target_group_id = cursor.lastrowid
    cursor = conn.execute("INSERT INTO duplicate_groups (created_at, updated_at) VALUES (?, ?)", (now, now))
    dup_group_id = cursor.lastrowid
    conn.execute(
        "UPDATE files SET duplicate_group_id = ?, target_group_id = ? WHERE id IN (?, ?)",
        (dup_group_id, target_group_id, id_a, id_b),
    )
    conn.commit()

    exclude_ids = storage.get_duplicate_exclusion_ids(conn)
    files = storage.get_files_for_target_group(conn, target_group_id, exclude_ids)
    assert len(files) == 1
    assert files[0]["exposure"] == 30.0

    files_unfiltered = storage.get_files_for_target_group(conn, target_group_id)
    assert len(files_unfiltered) == 2

    conn.close()
