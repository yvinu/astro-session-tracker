import sqlite3
from datetime import datetime

from astro_tracker import backup, config, migrations, storage
from astro_tracker.location import parse_location
from astro_tracker.migrate_catalog import rewrite_paths, rewrite_prefix


def test_library_roots_parsed_longest_first(monkeypatch):
    monkeypatch.setenv("ASTRO_LIBRARY_ROOTS", "Multimedia=/library; Deep=/library/deep/ ;bad")
    assert config.library_roots() == [("Deep", "/library/deep"), ("Multimedia", "/library")]


def test_location_from_configured_root():
    roots = [("Deep", "/library/deep"), ("Multimedia", "/library")]
    assert parse_location("/library/Seestar/a.fit", roots) == "Multimedia"
    assert parse_location("/library/deep/a.fit", roots) == "Deep"


def test_location_root_must_match_whole_segment():
    assert parse_location("/library2/a.fit", [("Multimedia", "/library")]) == "Internal"


def test_location_falls_back_to_volumes_rule_outside_roots():
    assert parse_location("/Volumes/Elements/a.fit", [("Multimedia", "/library")]) == "Elements"


def test_migrate_is_safe_to_run_twice(tmp_path):
    conn = storage.connect(str(tmp_path / "c.db"))
    storage.init_schema(conn)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    storage.init_schema(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == version == len(migrations.MIGRATIONS)


def test_migrate_upgrades_a_pre_versioning_catalog(tmp_path):
    db = str(tmp_path / "old.db")
    raw = sqlite3.connect(db)
    raw.executescript(storage.SCHEMA_SQL)
    raw.execute("ALTER TABLE files ADD COLUMN location TEXT")
    raw.execute(
        "INSERT INTO files (path, mtime, first_seen_at, last_updated_at) VALUES ('/Volumes/X/a.fit', 1, 't', 't')"
    )
    raw.commit()
    raw.close()

    conn = storage.connect(db)
    storage.init_schema(conn)
    row = conn.execute("SELECT location, optical_train FROM files").fetchone()
    assert row["location"] == "X"
    assert row["optical_train"] is None


def test_rewrite_prefix_only_matches_whole_directories():
    assert rewrite_prefix("/Volumes/M/a/b.fit", "/Volumes/M", "/library") == "/library/a/b.fit"
    assert rewrite_prefix("/Volumes/M2/b.fit", "/Volumes/M", "/library") is None


def _catalog_with_annotation(tmp_path):
    conn = storage.connect(str(tmp_path / "c.db"))
    storage.init_schema(conn)
    for path in ("/Volumes/M/AP/a.fit", "/Users/me/b.fit"):
        storage.upsert_file(conn, path, 1.0, 10, {"folder": path.rsplit("/", 1)[0], "location": parse_location(path)})
    conn.execute("INSERT INTO target_groups (created_at, updated_at) VALUES ('t', 't')")
    conn.execute(
        "INSERT INTO sessions (target_group_id, observation_night, created_at, updated_at) VALUES (1, '2026-01-01', 't', 't')"
    )
    storage.upsert_session_annotation(conn, 1, rating=4, notes="clear")
    conn.commit()
    return conn


def test_rewrite_paths_keeps_annotations_and_location(tmp_path):
    conn = _catalog_with_annotation(tmp_path)
    counts = rewrite_paths(conn, [("/Volumes/M", "/library")])

    assert counts == {"rewritten": 1, "conflicts": 0, "untouched": 1}
    row = conn.execute("SELECT path, folder, location FROM files WHERE path LIKE '/library%'").fetchone()
    assert (row["path"], row["folder"], row["location"]) == ("/library/AP/a.fit", "/library/AP", "M")
    assert storage.get_session_annotation(conn, 1)["notes"] == "clear"


def test_rewrite_paths_does_not_overwrite_an_existing_row(tmp_path):
    conn = _catalog_with_annotation(tmp_path)
    storage.upsert_file(conn, "/library/AP/a.fit", 1.0, 10, {})
    counts = rewrite_paths(conn, [("/Volumes/M", "/library")])
    assert counts["conflicts"] == 1
    assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 3


def test_snapshot_writes_a_readable_copy_and_prunes(tmp_path):
    db = str(tmp_path / "c.db")
    conn = storage.connect(db)
    storage.init_schema(conn)
    conn.close()
    out = tmp_path / "bk"

    for day in (1, 2, 3):
        path = backup.snapshot(db, str(out), keep=2, now=datetime(2026, 1, day))

    names = sorted(p.name for p in out.iterdir())
    assert names == ["catalog-20260102-000000.db", "catalog-20260103-000000.db"]
    assert sqlite3.connect(path).execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0


def test_prune_leaves_unrelated_files_alone(tmp_path):
    (tmp_path / "notes.txt").write_text("keep")
    (tmp_path / "catalog-20260101-000000.db").write_text("x")
    backup.prune(str(tmp_path), keep=0)
    assert [p.name for p in tmp_path.iterdir()] == ["notes.txt"]
