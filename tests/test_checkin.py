import json
import os

import pytest

from astro_tracker import checkin, library_storage, projects, storage, vocabulary_job
from astro_tracker.checkin_kinds import KIND_IMAGE, KIND_PHOTOSHOP, KIND_SIRIL_LOG


@pytest.fixture
def env(tmp_path):
    """A Project for M8 with one Checkout of three S50/LP subs, and a projects root on disk."""
    conn = storage.connect(str(tmp_path / "c.db"))
    storage.init_schema(conn)
    conn.execute("INSERT INTO target_groups (created_at, updated_at) VALUES ('t', 't')")
    conn.execute("INSERT INTO sessions (target_group_id, observation_night, created_at, updated_at) VALUES (1, '2026-07-11', 't', 't')")
    ids = []
    for name in ("a.fit", "b.fit", "c.fit"):
        storage.upsert_file(conn, f"/lib/{name}", 5.0, 100, {
            "file_name": name, "frame_type": "Light", "file_category": "Subframe", "target": "M 8",
            "optical_train": "Seestar S50", "filter": "LP", "exposure": 10})
        file_id = conn.execute("SELECT id FROM files WHERE file_name = ?", (name,)).fetchone()[0]
        conn.execute("UPDATE files SET target_group_id = 1, session_id = 1 WHERE id = ?", (file_id,))
        library_storage.set_content_hash(conn, file_id, f"hash-{name}", 100, 5.0)
        ids.append(file_id)
    library_storage.upsert_rig(conn, "s50", "Seestar S50", ["*seestar s50*"], [])
    vocabulary_job.recompute(conn)
    root = str(tmp_path / "projects")
    project = projects.create_project(conn, 1)
    checkout_id = projects.create_checkout(conn, project, {"filters": ["LP"]}, root=root)
    return {"conn": conn, "root": root, "project": project, "checkout_id": checkout_id, "ids": ids,
            "dir": os.path.join(root, "M8", "M8")}


def _upload(env, run, relpath, data, kind=KIND_IMAGE, **kw):
    temp = checkin.incoming_path(env["project"], env["root"])
    with open(temp, "wb") as f:
        f.write(data)
    return checkin.store_artifact(env["conn"], env["project"], run, temp, relpath, kind, root=env["root"], **kw)


def _files(env):
    found = []
    for base, _dirs, names in os.walk(env["dir"]):
        found += [os.path.relpath(os.path.join(base, n), env["dir"]) for n in names]
    return sorted(found)


def test_stack_is_stored_under_a_canonical_name_and_log_under_the_run(env):
    run = checkin.start_run(env["conn"], env["project"], "stacking", "siril")
    stack, status = _upload(env, run, "M_8_3x10sec_2026-07-11_og.fit", b"stack", stage="stack")
    _upload(env, run, "2026-07-12T02.04.48.log", b"log", kind=KIND_SIRIL_LOG)

    assert status == checkin.STATUS_STORED
    assert stack["stored_relpath"] == "stacks/M8_s50_LP_stack_3x10s_v01.fit"
    assert stack["original_name"] == "M_8_3x10sec_2026-07-11_og.fit"
    assert "runs/01_siril/2026-07-12T02.04.48.log" in _files(env)
    assert "stacks/M8_s50_LP_stack_3x10s_v01.fit" in _files(env)


def test_frame_count_comes_from_the_tool_name_else_from_the_checkout(env):
    run = checkin.start_run(env["conn"], env["project"], "stacking", "stackingwizard")
    named, _ = _upload(env, run, "lights/M_8_wizardstack_2f.fits", b"one", stage="stack")
    unnamed, _ = _upload(env, run, "result.fits", b"two", stage="stack-cc")
    assert named["frames"] == 2 and unnamed["frames"] == 3


def test_final_goes_to_finals_and_post_run_gets_its_own_folder(env):
    run = checkin.start_run(env["conn"], env["project"], "post", "Photoshop", notes="Curves, saturation +10")
    final, _ = _upload(env, run, "m8_done.jpg", b"jpg", stage="final")
    _upload(env, run, "m8_done.psd", b"psd", kind=KIND_PHOTOSHOP)

    assert final["stored_relpath"] == "finals/M8_s50_LP_final_3x10s_v01.jpg"
    assert "post/01_Photoshop/m8_done.psd" in _files(env)


def test_same_bytes_are_not_stored_twice(env):
    run = checkin.start_run(env["conn"], env["project"], "stacking", "siril")
    first, _ = _upload(env, run, "x_og.fit", b"stack", stage="stack")
    again, status = _upload(env, run, "x_og.fit", b"stack", stage="stack")

    assert status == checkin.STATUS_EXISTS and again["id"] == first["id"]
    assert len([f for f in _files(env) if f.startswith("stacks/")]) == 1


def test_changed_image_becomes_the_next_version_and_the_earlier_one_is_kept(env):
    run = checkin.start_run(env["conn"], env["project"], "stacking", "siril")
    _upload(env, run, "x_og.fit", b"first", stage="stack")
    second, _ = _upload(env, run, "x_og.fit", b"second", stage="stack")

    assert second["version"] == 2
    assert [f for f in _files(env) if f.startswith("stacks/")] == [
        "stacks/M8_s50_LP_stack_3x10s_v01.fit", "stacks/M8_s50_LP_stack_3x10s_v02.fit"]


def test_hash_mismatch_stores_nothing(env):
    run = checkin.start_run(env["conn"], env["project"], "stacking", "siril")
    with pytest.raises(checkin.CheckinError):
        _upload(env, run, "x_og.fit", b"stack", stage="stack", declared_hash="0" * 64)

    assert library_storage.get_runs(env["conn"], env["project"]["id"])[0]["artifacts"] == []
    assert [f for f in _files(env) if not f.startswith("checkouts/")] == []


def test_image_without_a_valid_stage_is_refused(env):
    run = checkin.start_run(env["conn"], env["project"], "stacking", "siril")
    with pytest.raises(checkin.CheckinError):
        _upload(env, run, "x.fit", b"stack", stage="finished")
    assert os.listdir(os.path.join(env["dir"], checkin.INCOMING_DIR)) == []


def test_what_went_into_an_image_is_its_checkouts_subs_without_any_log(env):
    run = checkin.start_run(env["conn"], env["project"], "stacking", "siril")
    stack, _ = _upload(env, run, "x_og.fit", b"stack", stage="stack")
    inputs = library_storage.get_artifact_inputs(env["conn"], stack["id"])
    assert [(i["position"], i["file_name"], i["content_hash"]) for i in inputs] == [
        (1, "a.fit", "hash-a.fit"), (2, "b.fit", "hash-b.fit"), (3, "c.fit", "hash-c.fit")]


def test_where_a_sub_was_used_lists_outputs_of_every_checkout_that_held_it(env):
    conn = env["conn"]
    first = checkin.start_run(conn, env["project"], "stacking", "siril")
    _upload(env, first, "x_og.fit", b"stack", stage="stack")
    _upload(env, first, "run.log", b"log", kind=KIND_SIRIL_LOG)
    second_checkout = projects.create_checkout(conn, env["project"], {}, root=env["root"])
    second = checkin.start_run(conn, env["project"], "post", "astrowizard", checkout_id=second_checkout)
    _upload(env, second, "x.jpg", b"jpg", stage="final")

    uses = library_storage.get_uses_of_content(conn, "hash-a.fit")
    assert [(u["stage"], u["tool"]) for u in uses] == [("final", "astrowizard"), ("stack", "siril")]
    assert library_storage.get_uses_of_content(conn, "hash-of-something-else") == []


def test_run_defaults_to_the_latest_checkout(env):
    newer = projects.create_checkout(env["conn"], env["project"], {}, root=env["root"])
    run = checkin.start_run(env["conn"], env["project"], "stacking", "siril")
    assert run["checkout_id"] == newer


def test_empty_run_is_dropped_but_a_notes_only_run_is_kept(env):
    conn = env["conn"]
    empty = checkin.start_run(conn, env["project"], "stacking", "siril")
    assert checkin.finish_run(conn, env["project"], empty, env["root"]) is None
    noted = checkin.start_run(conn, env["project"], "post", "photoshop", notes="Cropped and sharpened")
    assert checkin.finish_run(conn, env["project"], noted, env["root"])["notes"] == "Cropped and sharpened"
    assert [r["tool"] for r in library_storage.get_runs(conn, env["project"]["id"])] == ["photoshop"]


def test_record_files_describe_runs_and_outputs(env):
    conn = env["conn"]
    run = checkin.start_run(conn, env["project"], "stacking", "siril", notes="Naztronomy script, defaults")
    _upload(env, run, "x_og.fit", b"stack", stage="stack")
    _upload(env, run, "run.log", b"log", kind=KIND_SIRIL_LOG)
    checkin.finish_run(conn, env["project"], run, env["root"])

    record = json.loads(open(os.path.join(env["dir"], "record.json")).read())
    assert record["runs"][0]["outputs"][0]["stored_relpath"] == "stacks/M8_s50_LP_stack_3x10s_v01.fit"
    assert record["runs"][0]["files"][0]["stored_relpath"] == "runs/01_siril/run.log"
    assert record["runs"][0]["checkout_number"] == 1
    markdown = open(os.path.join(env["dir"], "record.md")).read()
    assert "### 01 siril (stacking" in markdown and "Naztronomy script, defaults" in markdown
    assert "`stacks/M8_s50_LP_stack_3x10s_v01.fit` (was `x_og.fit`)" in markdown


def test_two_support_files_with_the_same_name_are_both_kept(env):
    run = checkin.start_run(env["conn"], env["project"], "stacking", "siril")
    _upload(env, run, "process/lights_conversion.txt", b"one", kind="siril-conversion")
    second, _ = _upload(env, run, "lights/lights_conversion.txt", b"two", kind="siril-conversion")
    assert second["stored_relpath"] == "runs/01_siril/lights_conversion-2.txt"


def test_no_projects_root_is_reported_clearly(env, monkeypatch):
    monkeypatch.delenv("ASTRO_PROJECTS_ROOT", raising=False)
    with pytest.raises(checkin.CheckinError):
        checkin.incoming_path(env["project"])
