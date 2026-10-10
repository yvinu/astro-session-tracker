from astro_tracker import manifest as m


def _sub(i, name, rig="s50", flt="LP", session=1, exposure=10, hashed=True, path=None):
    return {
        "id": i, "path": path or f"/lib/{name}", "file_name": name,
        "content_hash": f"h{i}" if hashed else None, "session_id": session, "night": f"2026-07-{10 + session}",
        "rig_id": rig, "filter_canonical": flt, "exposure": exposure, "size": 100,
    }


def test_every_selected_sub_appears_once_with_its_hash():
    result = m.build_manifest([_sub(1, "a.fit"), _sub(2, "b.fit")])
    entries = result["groups"][0]["entries"]
    assert [(e["file_id"], e["content_hash"], e["handed_hash"]) for e in entries] == [(1, "h1", "h1"), (2, "h2", "h2")]
    assert result["sub_count"] == 2 and result["integration_seconds"] == 20


def test_positions_follow_case_insensitive_file_name_order():
    # The order seen in a real Siril conversion file: lower-case "failed_" names sort before upper-case "NGC".
    files = [_sub(1, "NGC 6530_0002.fits"), _sub(2, "failed_NGC 6530_0009.fits"), _sub(3, "NGC 6530_0001.fits")]
    entries = m.build_manifest(files)["groups"][0]["entries"]
    assert [(e["position"], e["file_name"]) for e in entries] == [
        (1, "failed_NGC 6530_0009.fits"), (2, "NGC 6530_0001.fits"), (3, "NGC 6530_0002.fits"),
    ]


def test_rigs_and_filters_are_separate_groups_each_numbered_from_one():
    files = [_sub(1, "a.fit", rig="s50", flt="LP"), _sub(2, "b.fit", rig="s50", flt="UVIR"),
             _sub(3, "c.fit", rig="dwarfmini", flt="UVIR"), _sub(4, "d.fit", rig="s50", flt="LP")]
    groups = m.build_manifest(files)["groups"]
    assert [(g["key"], g["count"]) for g in groups] == [("dwarfmini__UVIR", 1), ("s50__LP", 2), ("s50__UVIR", 1)]
    assert all(g["entries"][0]["position"] == 1 for g in groups)


def test_duplicates_and_unhashed_subs_are_left_out_and_counted():
    files = [_sub(1, "a.fit"), _sub(2, "b.fit"), _sub(3, "c.fit", hashed=False)]
    result = m.build_manifest(files, duplicate_exclusion_ids={2})
    assert result["sub_count"] == 1
    assert result["left_out"] == {"duplicates": 1, "no_hash": 1, "name_collisions": 0}


def test_same_file_name_twice_in_a_group_keeps_one():
    files = [_sub(1, "a.fit", path="/lib/x/a.fit"), _sub(2, "A.FIT", path="/lib/y/A.FIT")]
    result = m.build_manifest(files)
    assert result["sub_count"] == 1 and result["left_out"]["name_collisions"] == 1


def test_file_without_a_rig_goes_to_the_unassigned_group():
    assert m.build_manifest([_sub(1, "a.fit", rig=None)])["groups"][0]["rig"] == m.UNASSIGNED_RIG


def test_selection_by_session_rig_and_filter():
    files = [_sub(1, "a.fit", session=1), _sub(2, "b.fit", session=2), _sub(3, "c.fit", session=2, flt="UVIR"),
             _sub(4, "d.fit", session=2, rig=None)]
    assert [f["id"] for f in m.select_lights(files, session_ids={2})] == [2, 3, 4]
    assert [f["id"] for f in m.select_lights(files, session_ids={2}, filters={"LP"}, rigs={"s50"})] == [2]
    assert [f["id"] for f in m.select_lights(files, rigs={m.UNASSIGNED_RIG})] == [4]
    assert len(m.select_lights(files)) == 4


def test_options_summary_counts_per_session_rig_and_filter():
    files = [_sub(1, "a.fit", session=1), _sub(2, "b.fit", session=2), _sub(3, "c.fit", session=2, flt="UVIR")]
    options = m.summarize_options(files)
    assert [(s["value"], s["label"], s["count"]) for s in options["sessions"]] == [(1, "2026-07-11", 1), (2, "2026-07-12", 2)]
    assert [(f["value"], f["count"]) for f in options["filters"]] == [("LP", 2), ("UVIR", 1)]
    assert options["rigs"] == [{"value": "s50", "count": 3, "integration_seconds": 30}]
