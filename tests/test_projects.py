import json

import pytest

from astro_tracker import library_storage, projects, storage, vocabulary_job


@pytest.fixture
def conn(tmp_path):
    conn = storage.connect(str(tmp_path / "c.db"))
    storage.init_schema(conn)
    return conn


def _light(conn, name, session, hashed=True, **meta):
    path = f"/lib/{name}"
    fields = {"file_name": name, "frame_type": "Light", "file_category": "Subframe", "target": "M 8",
              "optical_train": "Seestar S50", "filter": "LP", "exposure": 10, **meta}
    storage.upsert_file(conn, path, 5.0, 100, fields)
    file_id = conn.execute("SELECT id FROM files WHERE path = ?", (path,)).fetchone()[0]
    conn.execute("UPDATE files SET target_group_id = 1, session_id = ? WHERE id = ?", (session, file_id))
    if hashed:
        library_storage.set_content_hash(conn, file_id, f"hash-{name}", 100, 5.0)
    conn.commit()
    return file_id


@pytest.fixture
def target(conn):
    """One target group with two sessions of S50 lights, a Rig, and names assigned."""
    conn.execute("INSERT INTO target_groups (created_at, updated_at) VALUES ('t', 't')")
    for night in ("2026-07-11", "2026-07-12"):
        conn.execute(
            "INSERT INTO sessions (target_group_id, observation_night, created_at, updated_at) VALUES (1, ?, 't', 't')", (night,)
        )
    ids = [_light(conn, "b.fit", 1), _light(conn, "A.fit", 1), _light(conn, "c.fit", 2), _light(conn, "d.fit", 2, hashed=False)]
    storage.upsert_file(conn, "/lib/dark.fit", 5.0, 100, {"file_name": "dark.fit", "frame_type": "Dark", "file_category": "Subframe"})
    conn.execute("UPDATE files SET target_group_id = 1 WHERE file_name = 'dark.fit'")
    library_storage.upsert_rig(conn, "s50", "Seestar S50", ["*seestar s50*"], [])
    vocabulary_job.recompute(conn)
    return ids


def test_project_takes_the_target_name_and_a_unique_slug(conn, target):
    first = projects.create_project(conn, 1)
    second = projects.create_project(conn, 1)
    named = projects.create_project(conn, 1, name="Lagoon wide field")
    assert (first["slug"], first["target_name"], first["status"]) == ("M8", "M8", "open")
    assert second["slug"] == "M8-2" and named["slug"] == "Lagoon-wide-field"


def test_project_needs_an_existing_target(conn):
    with pytest.raises(projects.ProjectError):
        projects.create_project(conn, 99)


def test_checkout_holds_exactly_the_selected_lights(conn, target, tmp_path):
    project = projects.create_project(conn, 1)
    checkout_id = projects.create_checkout(conn, project, {"session_ids": [1]}, root=str(tmp_path))

    stored = library_storage.get_checkout_manifest(conn, checkout_id)
    entries = stored["groups"][0]["entries"]
    assert [(e["position"], e["file_name"], e["content_hash"]) for e in entries] == [
        (1, "A.fit", "hash-A.fit"), (2, "b.fit", "hash-b.fit")]
    assert stored["groups"][0]["key"] == "s50__LP" and stored["sub_count"] == 2
    assert stored["checkout"]["number"] == 1


def test_unhashed_lights_are_left_out_and_counted_and_calibration_frames_never_appear(conn, target, tmp_path):
    project = projects.create_project(conn, 1)
    preview = projects.preview_checkout(conn, project, {})
    assert preview["sub_count"] == 3 and preview["left_out"]["no_hash"] == 1
    assert "dark.fit" not in [e["file_name"] for g in preview["groups"] for e in g["entries"]]


def test_stale_hash_counts_as_no_hash(conn, target):
    conn.execute("UPDATE files SET mtime = 99 WHERE file_name = 'c.fit'")
    project = projects.create_project(conn, 1)
    assert projects.preview_checkout(conn, project, {})["left_out"]["no_hash"] == 2


def test_new_selection_makes_a_new_checkout_and_leaves_the_first_unchanged(conn, target, tmp_path):
    project = projects.create_project(conn, 1)
    first = projects.create_checkout(conn, project, {"session_ids": [1]}, root=str(tmp_path))
    before = library_storage.get_checkout_manifest(conn, first)
    second = projects.create_checkout(conn, project, {}, root=str(tmp_path))

    assert library_storage.get_checkout_manifest(conn, first) == before
    assert library_storage.get_checkout_manifest(conn, second)["checkout"]["number"] == 2
    assert library_storage.get_latest_checkout_id(conn, project["id"]) == second


def test_manifest_file_on_disk_matches_the_stored_manifest(conn, target, tmp_path):
    project = projects.create_project(conn, 1)
    checkout_id = projects.create_checkout(conn, project, {}, root=str(tmp_path))
    on_disk = json.loads((tmp_path / "M8" / "M8" / "checkouts" / "01" / "manifest.json").read_text())
    assert on_disk == library_storage.get_checkout_manifest(conn, checkout_id)


def test_empty_selection_is_refused(conn, target, tmp_path):
    project = projects.create_project(conn, 1)
    with pytest.raises(projects.ProjectError):
        projects.create_checkout(conn, project, {"filters": ["Ha"]}, root=str(tmp_path))
    assert library_storage.get_checkouts(conn, project["id"]) == []


def test_checkout_survives_its_target_group_being_dropped_by_reclustering(conn, target, tmp_path):
    project = projects.create_project(conn, 1)
    checkout_id = projects.create_checkout(conn, project, {}, root=str(tmp_path))
    storage.save_clustering(conn, {})

    assert library_storage.get_checkout_manifest(conn, checkout_id)["sub_count"] == 3
    assert library_storage.get_project(conn, project["id"])["target_name"] == "M8"


def test_options_list_sessions_rigs_and_filters(conn, target):
    project = projects.create_project(conn, 1)
    options = projects.checkout_options(conn, project)
    assert [(s["label"], s["count"]) for s in options["sessions"]] == [("2026-07-11", 2), ("2026-07-12", 2)]
    assert [r["value"] for r in options["rigs"]] == ["s50"]
