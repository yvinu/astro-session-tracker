import os

import pytest

from astro_tracker import source_pull as sp

OLD = 1_000_000.0
NOW = OLD + 100_000


def _write(root, rel, data=b"x" * 10, mtime=OLD):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def dirs(tmp_path):
    device, mirror = tmp_path / "device", tmp_path / "mirror"
    device.mkdir()
    mirror.mkdir()
    return device, mirror


def _pull(device, mirror, **kw):
    return sp.pull(str(device), str(mirror), sp.select_seestar, now=NOW, **kw)


def test_seestar_selection_rules():
    assert sp.select_seestar("M 31_sub/Light_M 31_10.0s_LP_20260101-010101.fit") == sp.KIND_SUB
    assert sp.select_seestar("M 31_sub/Light_M 31_thn.jpg") is None
    assert sp.select_seestar("M 31/Stacked_210_M 31_10.0s_LP.fit") == sp.KIND_DEVICE_PRODUCT
    assert sp.select_seestar("M 31/Stacked_210_M 31.jpg") == sp.KIND_DEVICE_PRODUCT


def test_missing_files_are_copied_with_device_dates(dirs):
    device, mirror = dirs
    _write(device, "M 31_sub/a.fit")
    _write(device, "M 31/Stacked.fit")
    _write(device, "M 31_sub/a_thn.jpg")

    summary = _pull(device, mirror)

    assert sorted(summary["copied"]) == ["M 31/Stacked.fit", "M 31_sub/a.fit"]
    assert summary["bytes"] == 20
    assert not (mirror / "M 31_sub/a_thn.jpg").exists()
    assert os.stat(mirror / "M 31_sub/a.fit").st_mtime == OLD


def test_second_pull_copies_nothing(dirs):
    device, mirror = dirs
    _write(device, "M 31_sub/a.fit")
    _pull(device, mirror)
    summary = _pull(device, mirror)
    assert summary["copied"] == [] and summary["present"] == 1


def test_recently_modified_file_waits_for_a_later_run(dirs):
    device, mirror = dirs
    _write(device, "M 31_sub/a.fit", mtime=NOW - 60)

    assert _pull(device, mirror, stability_seconds=600)["recent"] == 1
    assert not (mirror / "M 31_sub/a.fit").exists()

    later = sp.pull(str(device), str(mirror), sp.select_seestar, now=NOW + 3600, stability_seconds=600)
    assert later["copied"] == ["M 31_sub/a.fit"]


def test_future_dated_file_is_not_held_back(dirs):
    device, mirror = dirs
    _write(device, "M 31_sub/a.fit", mtime=NOW + 10 * 365 * 86400)
    assert _pull(device, mirror)["copied"] == ["M 31_sub/a.fit"]


def test_existing_mirror_file_is_never_overwritten_and_difference_is_reported(dirs):
    device, mirror = dirs
    _write(device, "M 31_sub/a.fit", data=b"new-and-longer")
    _write(mirror, "M 31_sub/a.fit", data=b"old")

    summary = _pull(device, mirror)

    assert summary["differing"] == ["M 31_sub/a.fit"] and summary["copied"] == []
    assert (mirror / "M 31_sub/a.fit").read_bytes() == b"old"


def test_interrupted_copy_leaves_nothing_under_the_final_name(dirs, monkeypatch):
    device, mirror = dirs
    _write(device, "M 31_sub/a.fit", data=b"x" * 100)
    monkeypatch.setattr(sp, "COPY_CHUNK", 10)
    calls = []

    def stop_after_first_chunk():
        calls.append(1)
        return len(calls) > 2

    summary = _pull(device, mirror, should_stop=stop_after_first_chunk)

    assert summary["cancelled"] and summary["copied"] == []
    assert list((mirror).rglob("*.*")) == []

    assert _pull(device, mirror)["copied"] == ["M 31_sub/a.fit"]
    assert (mirror / "M 31_sub/a.fit").stat().st_size == 100


def test_leftover_partial_file_does_not_block_the_next_run(dirs):
    device, mirror = dirs
    _write(device, "M 31_sub/a.fit", data=b"complete")
    _write(mirror, "M 31_sub/a.fit" + sp.PART_SUFFIX, data=b"comp")

    assert _pull(device, mirror)["copied"] == ["M 31_sub/a.fit"]
    assert (mirror / "M 31_sub/a.fit").read_bytes() == b"complete"
    assert not (mirror / ("M 31_sub/a.fit" + sp.PART_SUFFIX)).exists()


def test_source_changing_during_copy_is_left_for_later(dirs, monkeypatch):
    device, mirror = dirs
    src = _write(device, "M 31_sub/a.fit", data=b"x" * 50)
    monkeypatch.setattr(sp, "COPY_CHUNK", 10)
    calls = []

    def grow_mid_copy():
        calls.append(1)
        if len(calls) == 3:  # after the copy has started reading
            with open(src, "ab") as f:
                f.write(b"more")
        return False

    summary = _pull(device, mirror, should_stop=grow_mid_copy)
    assert summary["copied"] == [] and summary["recent"] == 1
    assert not (mirror / "M 31_sub/a.fit").exists()


def test_device_is_never_written_to(dirs):
    device, mirror = dirs
    _write(device, "M 31_sub/a.fit")
    before = sorted((str(p), p.stat().st_mtime, p.stat().st_size) for p in device.rglob("*"))
    _pull(device, mirror)
    assert sorted((str(p), p.stat().st_mtime, p.stat().st_size) for p in device.rglob("*")) == before


def test_reachability_needs_ping_and_mount(tmp_path):
    assert sp.is_reachable(str(tmp_path), host="h", ping_fn=lambda h: True)
    assert not sp.is_reachable(str(tmp_path), host="h", ping_fn=lambda h: False)
    assert not sp.is_reachable(str(tmp_path / "absent"), host="h", ping_fn=lambda h: True)
    assert sp.is_reachable(str(tmp_path), host=None, ping_fn=lambda h: False)


# ---- a Source's settings ------------------------------------------------------

def test_source_settings_are_tidied_into_the_stored_form():
    fields = sp.source_fields(" S50 ", " /devices/s50/MyWorks ", "/library/SeestarMyWorks/", "seestar",
                                       host=" ", interval_minutes=30, stability_seconds=0, enabled=True)
    assert fields == {
        "name": "S50", "transport": "mounted_share", "profile": "seestar",
        "source_dir": "/devices/s50/MyWorks", "mirror_dir": "/library/SeestarMyWorks", "host": None,
        "interval_minutes": 30, "stability_seconds": 0, "enabled": 1,
    }


@pytest.mark.parametrize("change, message", [
    ({"profile": "telescope"}, "Unknown profile"),
    ({"name": "  "}, "required"),
    ({"mirror_dir": ""}, "required"),
    ({"interval_minutes": -1}, "cannot be negative"),
    ({"stability_seconds": -1}, "cannot be negative"),
    ({"mirror_dir": "/devices/s50/"}, "cannot be the device folder"),
])
def test_invalid_source_settings_are_refused_with_a_reason(change, message):
    given = {"name": "S50", "source_dir": "/devices/s50", "mirror_dir": "/library/s50", **change}
    with pytest.raises(sp.SourceError, match=message):
        sp.source_fields(**given)
