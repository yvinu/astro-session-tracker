import os

from astro_tracker.siril_export import build_working_folder


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"fake fits data")
    return path


def test_symlinks_created_under_frame_type_and_filter_subfolders(tmp_path):
    src_dir = tmp_path / "src"
    light1 = _touch(str(src_dir / "light1.fit"))
    flat1 = _touch(str(src_dir / "flat1.fit"))

    files = [
        {"path": light1, "frame_type": "Light", "filter": "LP", "target": "Heart Nebula"},
        {"path": flat1, "frame_type": "Flat", "filter": "Ha", "target": "Heart Nebula"},
    ]

    dest_root = tmp_path / "dest"
    dest_root.mkdir()
    result = build_working_folder(files, str(dest_root), group_id=11)

    light_link = os.path.join(result["destination"], "lights", "LP", "light1.fit")
    flat_link = os.path.join(result["destination"], "flats", "Ha", "flat1.fit")

    assert os.path.islink(light_link)
    assert os.path.realpath(light_link) == os.path.realpath(light1)
    assert os.path.islink(flat_link)
    assert os.path.realpath(flat_link) == os.path.realpath(flat1)
    assert result["total_linked"] == 2
    assert result["missing"] == []


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
    result = build_working_folder(files, str(dest_root), group_id=11)

    assert os.path.basename(result["destination"]) == "Heart_Nebula_group11"


def test_missing_source_file_is_skipped_and_reported(tmp_path):
    src_dir = tmp_path / "src"
    existing = _touch(str(src_dir / "exists.fit"))
    missing_path = str(src_dir / "does_not_exist.fit")

    files = [
        {"path": existing, "frame_type": "Light", "filter": "LP", "target": "M31"},
        {"path": missing_path, "frame_type": "Light", "filter": "LP", "target": "M31"},
    ]

    dest_root = tmp_path / "dest"
    dest_root.mkdir()
    result = build_working_folder(files, str(dest_root), group_id=5)

    assert result["total_linked"] == 1
    assert result["missing"] == [missing_path]


def test_filename_collision_gets_unique_suffix(tmp_path):
    src_dir1 = tmp_path / "session1"
    src_dir2 = tmp_path / "session2"
    file1 = _touch(str(src_dir1 / "light.fit"))
    file2 = _touch(str(src_dir2 / "light.fit"))

    files = [
        {"path": file1, "frame_type": "Light", "filter": "LP", "target": "M42"},
        {"path": file2, "frame_type": "Light", "filter": "LP", "target": "M42"},
    ]

    dest_root = tmp_path / "dest"
    dest_root.mkdir()
    result = build_working_folder(files, str(dest_root), group_id=1)

    linked_dir = os.path.join(result["destination"], "lights", "LP")
    linked_names = sorted(os.listdir(linked_dir))
    assert linked_names == ["light.fit", "light_1.fit"]
    assert result["total_linked"] == 2


def test_missing_filter_falls_back_to_nofilter(tmp_path):
    src_dir = tmp_path / "src"
    f = _touch(str(src_dir / "a.fit"))
    files = [{"path": f, "frame_type": "Light", "filter": None, "target": "M31"}]

    dest_root = tmp_path / "dest"
    dest_root.mkdir()
    result = build_working_folder(files, str(dest_root), group_id=1)

    linked = os.path.join(result["destination"], "lights", "NoFilter", "a.fit")
    assert os.path.islink(linked)


def test_no_recognizable_label_falls_back_to_generic_name(tmp_path):
    src_dir = tmp_path / "src"
    f = _touch(str(src_dir / "a.fit"))
    files = [{"path": f, "frame_type": "Light", "filter": "L", "target": None}]

    dest_root = tmp_path / "dest"
    dest_root.mkdir()
    result = build_working_folder(files, str(dest_root), group_id=7)

    assert os.path.basename(result["destination"]) == "target_group7"


def test_counts_summary_reflects_frame_type_and_filter_breakdown(tmp_path):
    src_dir = tmp_path / "src"
    files = [
        {"path": _touch(str(src_dir / "l1.fit")), "frame_type": "Light", "filter": "LP", "target": "M31"},
        {"path": _touch(str(src_dir / "l2.fit")), "frame_type": "Light", "filter": "LP", "target": "M31"},
        {"path": _touch(str(src_dir / "l3.fit")), "frame_type": "Light", "filter": "Ha", "target": "M31"},
        {"path": _touch(str(src_dir / "f1.fit")), "frame_type": "Flat", "filter": "LP", "target": "M31"},
    ]

    dest_root = tmp_path / "dest"
    dest_root.mkdir()
    result = build_working_folder(files, str(dest_root), group_id=2)

    assert result["counts"] == [
        {"frame_type": "flats", "filter": "LP", "count": 1},
        {"frame_type": "lights", "filter": "Ha", "count": 1},
        {"frame_type": "lights", "filter": "LP", "count": 2},
    ]
