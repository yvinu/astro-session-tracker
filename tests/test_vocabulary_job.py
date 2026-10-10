import sqlite3

import pytest

from astro_tracker import library_storage, storage, vocabulary_job


def _conn(tmp_path):
    conn = storage.connect(str(tmp_path / "c.db"))
    storage.init_schema(conn)
    return conn


def _add(conn, name, **meta):
    storage.upsert_file(conn, f"/lib/{name}", 1.0, 10, {"file_name": name, **meta})
    return conn.execute("SELECT id FROM files WHERE file_name = ?", (name,)).fetchone()[0]


def _group(conn, file_ids):
    conn.execute("INSERT INTO target_groups (created_at, updated_at) VALUES ('t', 't')")
    gid = conn.execute("SELECT MAX(id) FROM target_groups").fetchone()[0]
    conn.executemany("UPDATE files SET target_group_id = ? WHERE id = ?", [(gid, i) for i in file_ids])
    conn.commit()
    return gid


def test_files_get_rig_and_canonical_filter(tmp_path):
    conn = _conn(tmp_path)
    _add(conn, "a.fit", optical_train="Seestar S50 | Seestar S50 | 250mm", date="2026-07-12T06:00:00", filter="IRCUT")
    _add(conn, "b.fit", optical_train="C8 | ASI294", date="2026-07-12T06:00:00", filter="Mystery 7")
    library_storage.upsert_rig(conn, "s50", "Seestar S50", ["*seestar s50*"], [])

    summary = vocabulary_job.recompute(conn)

    rows = {r["file_name"]: dict(r) for r in conn.execute("SELECT file_name, rig_id, rig_status, filter_canonical FROM files")}
    assert rows["a.fit"] == {"file_name": "a.fit", "rig_id": "s50", "rig_status": "assigned", "filter_canonical": "UVIR"}
    assert rows["b.fit"]["rig_id"] is None and rows["b.fit"]["rig_status"] == "unassigned"
    assert rows["b.fit"]["filter_canonical"] == "Mystery-7"
    assert summary["rig_assigned"] == 1 and summary["rig_unassigned"] == 1


def test_editing_a_rig_reassigns_files_on_recompute(tmp_path):
    conn = _conn(tmp_path)
    _add(conn, "a.fit", optical_train="SW 80ED | ASI533MC", date="2026-07-12T06:00:00")
    library_storage.upsert_rig(conn, "80ed", "80ED", ["*80ed*"], [[None, "2026-01-01"]])
    vocabulary_job.recompute(conn)
    assert conn.execute("SELECT rig_id FROM files").fetchone()[0] is None

    library_storage.upsert_rig(conn, "80ed", "80ED", ["*80ed*"], [])
    assert vocabulary_job.recompute(conn)["files_changed"] == 1
    assert conn.execute("SELECT rig_id FROM files").fetchone()[0] == "80ed"


def test_second_recompute_changes_nothing(tmp_path):
    conn = _conn(tmp_path)
    _add(conn, "a.fit", optical_train="x", filter="LP")
    vocabulary_job.recompute(conn)
    assert vocabulary_job.recompute(conn)["files_changed"] == 0


def test_target_groups_get_default_names_made_unique(tmp_path):
    conn = _conn(tmp_path)
    g1 = _group(conn, [_add(conn, "a.fit", target="M 8"), _add(conn, "b.fit", target="M 8"), _add(conn, "c.fit", target="Lagoon")])
    g2 = _group(conn, [_add(conn, "d.fit", target="M 8")])

    assert vocabulary_job.recompute(conn)["targets_named"] == 2
    assert library_storage.get_target_name(conn, g1) == "M8"
    assert library_storage.get_target_name(conn, g2) == "M8-2"


def test_custom_target_name_survives_recompute(tmp_path):
    conn = _conn(tmp_path)
    gid = _group(conn, [_add(conn, "a.fit", target="M 8")])
    vocabulary_job.recompute(conn)
    library_storage.set_target_name(conn, gid, "Lagoon", aliases=["M8", "NGC6523"])

    vocabulary_job.recompute(conn)

    target = library_storage.get_target_names(conn)[0]
    assert (target["name"], target["aliases"], target["is_custom"]) == ("Lagoon", ["M8", "NGC6523"], True)


def test_two_groups_cannot_share_a_name(tmp_path):
    conn = _conn(tmp_path)
    g1 = _group(conn, [_add(conn, "a.fit", target="M 8")])
    g2 = _group(conn, [_add(conn, "b.fit", target="M 20")])
    vocabulary_job.recompute(conn)
    with pytest.raises(sqlite3.IntegrityError):
        library_storage.set_target_name(conn, g2, library_storage.get_target_name(conn, g1))


def test_name_is_removed_with_its_target_group(tmp_path):
    conn = _conn(tmp_path)
    gid = _group(conn, [_add(conn, "a.fit", target="M 8")])
    vocabulary_job.recompute(conn)
    conn.execute("UPDATE files SET target_group_id = NULL")
    conn.execute("DELETE FROM target_groups WHERE id = ?", (gid,))
    assert conn.execute("SELECT COUNT(*) FROM target_names").fetchone()[0] == 0


def test_filter_mapping_can_be_changed_and_removed(tmp_path):
    conn = _conn(tmp_path)
    _add(conn, "a.fit", filter="IRCUT")
    library_storage.set_filter_mapping(conn, " IRCUT ", "LUM")
    vocabulary_job.recompute(conn)
    assert conn.execute("SELECT filter_canonical FROM files").fetchone()[0] == "LUM"

    library_storage.set_filter_mapping(conn, "ircut", None)
    vocabulary_job.recompute(conn)
    assert conn.execute("SELECT filter_canonical FROM files").fetchone()[0] == "IRCUT"
