import os
import stat
import subprocess

from astro_tracker.siril_export import build_lights_export


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"fake fits data")
    return path


def test_lights_dir_created_flat_for_single_camera_filter_combo(tmp_path):
    src_dir = tmp_path / "src"
    light1 = _touch(str(src_dir / "light1.fit"))

    files = [
        {"path": light1, "frame_type": "Light", "filter": "LP", "target": "Heart Nebula", "optical_train": "Seestar S50"},
        {"path": _touch(str(src_dir / "flat1.fit")), "frame_type": "Flat", "filter": "LP", "target": "Heart Nebula"},
    ]

    dest_root = tmp_path / "dest"
    dest_root.mkdir()
    result = build_lights_export(files, str(dest_root), group_id=11)

    lights_dir = os.path.join(result["destination"], "lights")
    assert os.path.isdir(lights_dir)
    assert result["total_files"] == 1  # the Flat frame is excluded entirely
    assert result["combos"] == [
        {"camera": "Seestar_S50", "filter": "LP", "lights_dir": lights_dir, "count": 1}
    ]
    assert not os.path.islink(lights_dir)  # a real directory, not a symlink target


def test_multiple_camera_filter_combos_get_separate_lights_dirs(tmp_path):
    src_dir = tmp_path / "src"
    files = [
        {"path": _touch(str(src_dir / "a.fit")), "frame_type": "Light", "filter": "LP", "target": "M31", "optical_train": "Seestar S50"},
        {"path": _touch(str(src_dir / "b.fit")), "frame_type": "Light", "filter": "Ha", "target": "M31", "optical_train": "Dwarf 3"},
    ]

    dest_root = tmp_path / "dest"
    dest_root.mkdir()
    result = build_lights_export(files, str(dest_root), group_id=1)

    lights_dirs = {c["lights_dir"] for c in result["combos"]}
    assert len(lights_dirs) == 2
    for d in lights_dirs:
        assert os.path.isdir(d)
        assert os.path.basename(d) == "lights"
        # camera+filter subfolder keeps the two combos apart
        assert os.path.dirname(d) != result["destination"]


def test_group_folder_named_from_most_common_label(tmp_path):
    src_dir = tmp_path / "src"
    files = [
        {"path": _touch(str(src_dir / f"a{i}.fit")), "frame_type": "Light", "filter": "LP", "target": "Heart Nebula"}
        for i in range(3)
    ]
    files.append({
        "path": _touch(str(src_dir / "b.fit")), "frame_type": "Light", "filter": "LP", "target": "Horsehead Nebula",
    })

    dest_root = tmp_path / "dest"
    dest_root.mkdir()
    result = build_lights_export(files, str(dest_root), group_id=11)

    assert os.path.basename(result["destination"]) == "Heart_Nebula_group11"


def test_no_light_frames_returns_empty_summary_without_touching_disk(tmp_path):
    src_dir = tmp_path / "src"
    files = [
        {"path": _touch(str(src_dir / "f.fit")), "frame_type": "Flat", "filter": "LP", "target": "M31"},
    ]

    dest_root = tmp_path / "dest"
    dest_root.mkdir()
    result = build_lights_export(files, str(dest_root), group_id=5)

    assert result == {"destination": None, "script_path": None, "combos": [], "total_files": 0}
    assert os.listdir(dest_root) == []


def test_missing_filter_falls_back_to_nofilter(tmp_path):
    src_dir = tmp_path / "src"
    f = _touch(str(src_dir / "a.fit"))
    files = [{"path": f, "frame_type": "Light", "filter": None, "target": "M31"}]

    dest_root = tmp_path / "dest"
    dest_root.mkdir()
    result = build_lights_export(files, str(dest_root), group_id=1)

    assert result["combos"][0]["filter"] == "NoFilter"


def test_no_recognizable_label_falls_back_to_generic_name(tmp_path):
    src_dir = tmp_path / "src"
    f = _touch(str(src_dir / "a.fit"))
    files = [{"path": f, "frame_type": "Light", "filter": "L", "target": None}]

    dest_root = tmp_path / "dest"
    dest_root.mkdir()
    result = build_lights_export(files, str(dest_root), group_id=7)

    assert os.path.basename(result["destination"]) == "target_group7"


def test_rerunning_export_does_not_touch_existing_lights_contents(tmp_path):
    src_dir = tmp_path / "src"
    files = [{"path": _touch(str(src_dir / "a.fit")), "frame_type": "Light", "filter": "LP", "target": "M31"}]

    dest_root = tmp_path / "dest"
    dest_root.mkdir()
    result = build_lights_export(files, str(dest_root), group_id=1)

    # Simulate a file the user already copied in (e.g. from running the script once).
    sentinel = os.path.join(result["destination"], "lights", "already_here.fit")
    with open(sentinel, "wb") as fh:
        fh.write(b"do not touch me")

    build_lights_export(files, str(dest_root), group_id=1)

    assert os.path.exists(sentinel)


def test_script_written_executable_and_references_sources(tmp_path):
    src_dir = tmp_path / "src"
    light1 = _touch(str(src_dir / "light1.fit"))
    files = [{"path": light1, "frame_type": "Light", "filter": "LP", "target": "M31"}]

    dest_root = tmp_path / "dest"
    dest_root.mkdir()
    result = build_lights_export(files, str(dest_root), group_id=1)

    script_path = result["script_path"]
    assert script_path == os.path.join(result["destination"], "copy_lights.sh")
    assert os.path.isfile(script_path)
    assert os.stat(script_path).st_mode & stat.S_IXUSR

    content = open(script_path).read()
    assert content.startswith("#!/bin/bash")
    assert light1 in content
    assert result["combos"][0]["lights_dir"] in content
    # nothing should have been copied by generating the script
    assert os.listdir(os.path.join(result["destination"], "lights")) == []


def test_script_copies_files_and_reports_summary(tmp_path):
    src_dir = tmp_path / "src"
    light1 = _touch(str(src_dir / "light1.fit"))
    files = [{"path": light1, "frame_type": "Light", "filter": "LP", "target": "M31"}]

    dest_root = tmp_path / "dest"
    dest_root.mkdir()
    result = build_lights_export(files, str(dest_root), group_id=1)

    proc = subprocess.run(
        ["bash", result["script_path"]],
        capture_output=True, text=True, timeout=30,
    )

    assert proc.returncode == 0, proc.stderr
    copied = os.path.join(result["destination"], "lights", "light1.fit")
    assert os.path.isfile(copied)
    assert "Copied:                    1" in proc.stdout


def test_script_skips_missing_source_gracefully(tmp_path):
    files = [{"path": str(tmp_path / "src" / "gone.fit"), "frame_type": "Light", "filter": "LP", "target": "M31"}]

    dest_root = tmp_path / "dest"
    dest_root.mkdir()
    result = build_lights_export(files, str(dest_root), group_id=1)

    proc = subprocess.run(
        ["bash", result["script_path"]],
        capture_output=True, text=True, timeout=30,
    )

    assert proc.returncode == 0, proc.stderr
    assert "SKIP (source not found)" in proc.stderr
    assert "Skipped (source missing):  1" in proc.stdout


def test_script_aborts_when_volumes_source_not_mounted(tmp_path):
    fake_volume_path = "/Volumes/DefinitelyNotMounted_xyz/light1.fit"
    files = [{"path": fake_volume_path, "frame_type": "Light", "filter": "LP", "target": "M31"}]

    dest_root = tmp_path / "dest"
    dest_root.mkdir()
    result = build_lights_export(files, str(dest_root), group_id=1)

    proc = subprocess.run(
        ["bash", result["script_path"]],
        capture_output=True, text=True, timeout=30,
    )

    assert proc.returncode == 1
    assert "does not appear to be mounted" in proc.stderr
    assert os.listdir(os.path.join(result["destination"], "lights")) == []
