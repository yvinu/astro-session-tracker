"""The `astro` CLI driven end to end against the real API, with the HTTP layer swapped for the test client."""

import hashlib
import json
import os

import pytest
from fastapi.testclient import TestClient

from astro_cli import checkin as cli_checkin
from astro_cli import checkout as cli_checkout
from astro_cli import settings
from astro_cli.api import ApiError
from astro_tracker import library_storage, projects, server, storage, vocabulary_job

TOKEN = "test-token"


class ClientApi:
    """Stands in for astro_cli.api.Api, sending the same requests through FastAPI's test client."""

    def __init__(self, client, token=TOKEN):
        self.client = client
        self.headers = {"Authorization": f"Bearer {token}"}

    def _result(self, response):
        if response.status_code >= 400:
            raise ApiError(response.status_code, response.json().get("detail"))
        return response.json()

    def get_json(self, path):
        return self._result(self.client.get(path, headers=self.headers))

    def post_json(self, path, body):
        return self._result(self.client.post(path, json=body, headers=self.headers))

    def put_file(self, path, params, file_path):
        params = {k: v for k, v in params.items() if v is not None}
        with open(file_path, "rb") as f:
            return self._result(self.client.put(path, params=params, content=f.read(), headers=self.headers))


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A library of three S50 subs on 'the NAS', a Project with a Checkout, and a Mac work root."""
    library = tmp_path / "nas" / "library" / "SeestarMyWorks" / "M 8_sub"
    library.mkdir(parents=True)
    db = str(tmp_path / "c.db")
    conn = storage.connect(db)
    storage.init_schema(conn)
    conn.execute("INSERT INTO target_groups (created_at, updated_at) VALUES ('t', 't')")
    conn.execute("INSERT INTO sessions (target_group_id, observation_night, created_at, updated_at) VALUES (1, '2026-07-11', 't', 't')")
    for name in ("Light_M 8_b.fit", "Light_M 8_a.fit", "Light_M 8_c.fit"):
        data = f"pixels of {name}".encode()
        (library / name).write_bytes(data)
        # The catalog holds the path as the service sees it, inside its container.
        container_path = f"/library/SeestarMyWorks/M 8_sub/{name}"
        storage.upsert_file(conn, container_path, 5.0, len(data), {
            "file_name": name, "frame_type": "Light", "file_category": "Subframe", "target": "M 8",
            "optical_train": "Seestar S50", "filter": "LP", "exposure": 10})
        file_id = conn.execute("SELECT id FROM files WHERE path = ?", (container_path,)).fetchone()[0]
        conn.execute("UPDATE files SET target_group_id = 1, session_id = 1 WHERE id = ?", (file_id,))
        library_storage.set_content_hash(conn, file_id, hashlib.sha256(data).hexdigest(), len(data), 5.0)
    library_storage.upsert_rig(conn, "s50", "Seestar S50", ["*seestar s50*"], [])
    vocabulary_job.recompute(conn)

    projects_root = tmp_path / "nas" / "library" / "projects"
    monkeypatch.setenv("ASTRO_PROJECTS_ROOT", str(projects_root))
    monkeypatch.setenv("ASTRO_CLI_TOKEN", TOKEN)
    monkeypatch.setattr(server, "DB_PATH", db)
    project = projects.create_project(conn, 1)
    projects.create_checkout(conn, project, {})

    work_root = tmp_path / "mac" / "Temp_stacking"
    work_root.mkdir(parents=True)
    config = {"work_root": str(work_root), "path_map": {"/library": str(tmp_path / "nas" / "library")}}
    return {"api": ClientApi(TestClient(server.app)), "conn": conn, "config": config,
            "working": work_root / "M8__M8", "project_dir": projects_root / "M8" / "M8", "library": library}


def _checkout(env, **kw):
    return cli_checkout.run(env["api"], "M8", "naztronomy", None, env["config"], out=lambda *_: None, **kw)


def _checkin(env, **kw):
    return cli_checkin.run(env["api"], "M8", str(env["working"]), out=lambda *_: None, **kw)


def test_checkout_fills_a_flat_lights_folder_that_matches_the_manifest(env):
    summary = _checkout(env)

    assert summary["copied"] == 3 and summary["failed"] == []
    lights = env["working"] / "lights"
    assert sorted(p.name for p in lights.iterdir()) == ["Light_M 8_a.fit", "Light_M 8_b.fit", "Light_M 8_c.fit"]
    stored = json.loads((env["working"] / "astro-manifest.json").read_text())
    for entry in stored["groups"][0]["entries"]:
        assert hashlib.sha256((lights / entry["file_name"]).read_bytes()).hexdigest() == entry["handed_hash"]
    assert library_storage.get_checkouts(env["conn"], 1)[0]["working_dir"] == str(env["working"])


def test_rerun_copies_only_what_is_missing(env):
    _checkout(env)
    os.remove(env["working"] / "lights" / "Light_M 8_b.fit")
    summary = _checkout(env)
    assert (summary["copied"], summary["already_present"]) == (1, 2)


def test_file_that_does_not_verify_is_reported_and_not_left_in_place(env):
    (env["library"] / "Light_M 8_b.fit").write_bytes(b"changed since it was hashed")
    summary = _checkout(env)

    assert summary["failed"] == ["lights/Light_M 8_b.fit"] and summary["copied"] == 2
    assert not (env["working"] / "lights" / "Light_M 8_b.fit").exists()
    assert library_storage.get_checkouts(env["conn"], 1)[0]["working_dir"] is None


def test_unmapped_library_path_is_a_clear_error(env):
    env["config"]["path_map"] = {"/elsewhere": "/tmp"}
    with pytest.raises(settings.PathMapError):
        _checkout(env)


def test_wrong_token_is_refused(env):
    bad = ClientApi(env["api"].client, token="wrong")
    with pytest.raises(ApiError) as error:
        cli_checkout.run(bad, "M8", "naztronomy", None, env["config"], out=lambda *_: None)
    assert error.value.status == 401


def test_remote_sources_go_through_rsync_in_one_batch_per_folder(env):
    env["config"]["path_map"] = {"/library": "me@nas:/share/AstroPhotos"}
    calls = []
    summary = _checkout(env, remote_copy=calls.append)
    assert len(calls) == 1 and len(calls[0]) == 3
    assert calls[0][0][0].startswith("me@nas:/share/AstroPhotos/SeestarMyWorks/M 8_sub/")
    assert len(summary["failed"]) == 3  # nothing arrived, so nothing verified


def _process(env):
    """Simulate a Siril (Naztronomy) run in the working folder."""
    working = env["working"]
    (working / "process").mkdir()
    (working / "process" / "pp_lights_00001.fit").write_bytes(b"intermediate")
    (working / "process" / "lights_conversion.txt").write_text("'a' -> '../process/lights_00001.fit'\n")
    (working / "M_8_3x10sec_2026-07-11_og.fit").write_bytes(b"linear stack")
    (working / "M_8_3x10sec_2026-07-11_spcc.fit").write_bytes(b"colour calibrated stack")
    (working / "2026-07-12T02.04.48.log").write_text("18:09:13: Welcome to siril\n")


def test_checkin_stores_outputs_and_logs_but_not_subs_or_intermediates(env):
    _checkout(env)
    _process(env)

    summary = _checkin(env)

    assert sorted(item["stored_relpath"] for item in summary["stored"]) == [
        "runs/01_siril/2026-07-12T02.04.48.log",
        "runs/01_siril/lights_conversion.txt",
        "stacks/M8_s50_LP_stack-cc_3x10s_v01.fit",
        "stacks/M8_s50_LP_stack_3x10s_v01.fit",
    ]
    on_nas = sorted(str(p.relative_to(env["project_dir"])) for p in env["project_dir"].rglob("*") if p.is_file())
    assert not any("Light_M 8" in name or "pp_lights" in name for name in on_nas)
    assert (env["project_dir"] / "stacks" / "M8_s50_LP_stack_3x10s_v01.fit").read_bytes() == b"linear stack"
    assert "record.md" in on_nas


def test_second_checkin_uploads_nothing_and_leaves_no_empty_run(env):
    _checkout(env)
    _process(env)
    _checkin(env)

    summary = _checkin(env)

    assert summary["stored"] == [] and summary["already_stored"] == 4
    assert len(library_storage.get_runs(env["conn"], 1)) == 1


def test_changed_output_checked_in_again_is_the_next_version(env):
    _checkout(env)
    _process(env)
    _checkin(env)
    (env["working"] / "M_8_3x10sec_2026-07-11_og.fit").write_bytes(b"restacked")

    summary = _checkin(env)

    assert [item["stored_relpath"] for item in summary["stored"]] == ["stacks/M8_s50_LP_stack_3x10s_v02.fit"]
    assert (env["project_dir"] / "stacks" / "M8_s50_LP_stack_3x10s_v01.fit").exists()


def test_stage_can_be_overridden_or_an_image_skipped(env):
    _checkout(env)
    _process(env)
    summary = _checkin(env, stages={"M_8_3x10sec_2026-07-11_og.fit": "skip", "M_8_3x10sec_2026-07-11_spcc.fit": "final"})

    assert summary["skipped"] == ["M_8_3x10sec_2026-07-11_og.fit"]
    assert "finals/M8_s50_LP_final_3x10s_v01.fit" in [item["stored_relpath"] for item in summary["stored"]]


def test_photoshop_run_with_only_notes_and_a_psd(env):
    _checkout(env)
    (env["working"] / "m8.psd").write_bytes(b"layers")
    summary = _checkin(env, notes="Curves and a crop")

    assert summary["run"]["tool"] == "photoshop" and summary["run"]["notes"] == "Curves and a crop"
    assert [item["stored_relpath"] for item in summary["stored"]] == ["post/01_photoshop/m8.psd"]


def test_named_tool_decides_the_run_kind_even_with_siril_logs_in_the_folder(env):
    _checkout(env)
    _process(env)
    _checkin(env)
    (env["working"] / "m8.psd").write_bytes(b"layers")
    summary = _checkin(env, tool="photoshop")
    assert summary["run"]["kind"] == "post"
    assert [item["stored_relpath"] for item in summary["stored"]] == ["post/02_photoshop/m8.psd"]


def test_checked_in_stack_traces_back_to_the_checked_out_subs(env):
    _checkout(env)
    _process(env)
    _checkin(env)
    client = env["api"].client
    runs = client.get("/api/projects/M8/runs").json()["runs"]
    stack = next(a for a in runs[0]["artifacts"] if a["stage"] == "stack")

    inputs = client.get(f"/api/artifacts/{stack['id']}/inputs").json()
    assert [s["file_name"] for s in inputs["subs"]] == ["Light_M 8_a.fit", "Light_M 8_b.fit", "Light_M 8_c.fit"]
    uses = client.get(f"/api/files/{inputs['subs'][0]['file_id']}/uses").json()["uses"]
    assert sorted(u["stage"] for u in uses) == ["stack", "stack-cc"]


def test_map_path_prefers_the_longest_prefix():
    path_map = {"/library": "/Volumes/M", "/library/deep": "me@nas:/deep"}
    assert settings.map_path("/library/a/b.fit", path_map) == "/Volumes/M/a/b.fit"
    assert settings.map_path("/library/deep/b.fit", path_map) == "me@nas:/deep/b.fit"
    assert settings.is_remote("me@nas:/deep/b.fit") and not settings.is_remote("/Volumes/M/a:b.fit")
