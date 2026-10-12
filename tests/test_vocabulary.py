import pytest

from astro_tracker import vocabulary as v

RIGS = [
    {"id": "s50", "patterns": ["*seestar s50*"], "date_ranges": []},
    {"id": "80ed-533", "patterns": ["*80ed*533*"], "date_ranges": [[None, "2026-05-31"]]},
    {"id": "80ed-533-r08", "patterns": ["*80ed*533*"], "date_ranges": [["2026-06-01", None]]},
]


def test_rig_matched_case_insensitively():
    assert v.assign_rig("Seestar S50 | Seestar S50 | 250mm", "2026-07-12T06:30:59", RIGS) == ("s50", v.RIG_ASSIGNED)


def test_rig_with_no_match_is_unassigned():
    assert v.assign_rig("C8 | ASI294", "2026-07-12", RIGS) == (None, v.RIG_UNASSIGNED)
    assert v.assign_rig(None, "2026-07-12", RIGS) == (None, v.RIG_UNASSIGNED)


def test_date_ranges_separate_two_configurations_of_one_scope():
    train = "SW 80ED | ASI533MC | 600mm"
    assert v.assign_rig(train, "2026-05-31T23:59:00", RIGS)[0] == "80ed-533"
    assert v.assign_rig(train, "2026-06-01T00:10:00", RIGS)[0] == "80ed-533-r08"


def test_overlapping_rigs_are_ambiguous_not_picked():
    rigs = [{"id": "a", "patterns": ["*80ed*"], "date_ranges": []},
            {"id": "b", "patterns": ["*533*"], "date_ranges": []}]
    assert v.assign_rig("SW 80ED | ASI533MC", "2026-01-01", rigs) == (None, v.RIG_AMBIGUOUS)


def test_dated_rig_does_not_claim_a_file_with_no_date():
    assert v.assign_rig("SW 80ED | ASI533MC", "Unknown", RIGS) == (None, v.RIG_UNASSIGNED)


def test_filter_values_meaning_the_same_thing_map_together():
    mapping = v.DEFAULT_FILTER_MAP
    assert {v.canonical_filter(raw, mapping) for raw in ("IRCUT", " ircut ", "Astro", "UV/IR")} == {"UVIR"}
    assert v.canonical_filter("No Filter", mapping) == v.NO_FILTER
    assert v.canonical_filter(None, mapping) == v.NO_FILTER


def test_unmapped_filter_passes_through_name_safe():
    assert v.canonical_filter("Optolong L-eXtreme 2\"", {}) == "Optolong-L-eXtreme-2"


def test_default_target_name_takes_majority_and_closes_catalogue_gap():
    assert v.default_target_name(["M 8", "M 8", "Lagoon", "Unknown"]) == "M8"
    assert v.default_target_name(["NGC 7380"]) == "NGC7380"
    assert v.default_target_name(["Butterfly in Cygnus"]) == "Butterfly-in-Cygnus"
    assert v.default_target_name(["Unknown", ""]) == "unknown"


def test_unique_name_adds_a_suffix_only_when_taken():
    assert v.unique_name("M8", {"M31"}) == "M8"
    assert v.unique_name("M8", {"M8", "M8-2"}) == "M8-3"


def test_night_spans_midnight():
    assert v.observation_night("2026-08-13T22:00:00") == "2026-08-13"
    assert v.observation_night("2026-08-14T03:00:00") == "2026-08-13"
    assert v.observation_night("2026-08-14T13:00:00") == "2026-08-14"


def test_night_uses_site_offset():
    # 13:30 UTC is 08:30 the same morning at UTC-5, still the night before;
    # 07:00 UTC is 12:30 local at UTC+5.5, past noon, so the next night.
    assert v.observation_night("2026-08-14T13:30:00", site_utc_offset_hours=-5) == "2026-08-13"
    assert v.observation_night("2026-08-14T07:00:00", site_utc_offset_hours=5.5) == "2026-08-14"


def test_night_unknown_for_unparseable_date():
    assert v.observation_night(None) == "Unknown"
    assert v.observation_night("garbage") == "Unknown"


def test_corrected_utc_identity_by_default():
    assert v.corrected_utc("2026-08-13T22:16:00.912") == "2026-08-13T22:16:00.912000"


def test_corrected_utc_for_local_end_of_exposure_headers():
    correction = {"utc_offset_hours": -5, "marks": "end"}
    assert v.corrected_utc("2026-08-13T22:16:15", 15, correction) == "2026-08-14T03:16:00"
    assert v.corrected_utc("nope", 15, correction) is None


def test_canonical_name_pattern():
    name = v.canonical_name("M8", "dwarfmini", "UVIR", "stack", 302, 15.0, 1, ".FITS")
    assert name == "M8_dwarfmini_UVIR_stack_302x15s_v01.fits"


def test_canonical_name_replaces_unsafe_characters_and_keeps_fields_splittable():
    name = v.canonical_name("NGC 6530 9", "80ed_533", "L-eXtreme", "final", 40, 2.5, 12, "tif")
    assert name == "NGC-6530-9_80ed-533_L-eXtreme_final_40x2.5s_v12.tif"
    assert len(name.rsplit(".", 1)[0].split("_")) == 6


def test_canonical_name_rejects_unknown_stage():
    with pytest.raises(ValueError):
        v.canonical_name("M8", "s50", "LP", "finished", 1, 10, 1, "fit")


def test_one_or_multi():
    assert v.one_or_multi(["s50", "s50"]) == "s50"
    assert v.one_or_multi(["s50", "dwarfmini"]) == v.MULTI
    assert v.one_or_multi([None, ""]) == "unknown"


# ---- camera + focal-length matching and Rig suggestions ----------------------

# (Optical Train label, camera, measured focal length) as the catalog stores them for each File.
USER_TRAINS = [
    ("OnStep | ZWO ASI294MC Pro | 373mm", "ZWO ASI294MC Pro", 373.0),
    ("OnStep | ZWO ASI294MC Pro | 369mm", "ZWO ASI294MC Pro", 369.0),
    ("OnStep | ZWO ASI294MC Pro | 374mm", "ZWO ASI294MC Pro", 374.0),
    ("OnStep | ZWO ASI294MC Pro | 372.534439682155mm", "ZWO ASI294MC Pro", 372.534439682155),
    ("OnStep | ZWO ASI294MC Pro | 372.431561787758mm", "ZWO ASI294MC Pro", 372.431561787758),
    ("OnStep | ZWO ASI294MC Pro | 372mm", "ZWO ASI294MC Pro", 372.0),
    ("Apertura 60ED 370@F\\6.2 | ZWO CCD ASI294MC Pro | 370.0mm", "ZWO CCD ASI294MC Pro", 370.0),
]


def test_camera_names_written_differently_normalise_to_one_key():
    assert v.normalize_camera("ZWO ASI294MC Pro") == v.normalize_camera("ZWO CCD ASI294MC Pro") == "asi294mcpro"
    assert v.normalize_camera("Unknown") == "" and v.normalize_camera(None) == ""


def test_one_camera_and_focal_range_rig_claims_every_spelling_of_the_same_setup():
    rig = {"id": "60ed-294", "camera": "asi294mcpro", "focal_min": 365, "focal_max": 378, "patterns": [], "date_ranges": []}
    for train, instrument, focal in USER_TRAINS:
        assert v.assign_rig(train, "2026-01-01", [rig], instrument, focal) == ("60ed-294", v.RIG_ASSIGNED), train


def test_focal_range_keeps_a_reducer_or_other_scope_out():
    rig = {"id": "60ed-294", "camera": "asi294mcpro", "focal_min": 365, "focal_max": 378, "patterns": [], "date_ranges": []}
    assert v.assign_rig("OnStep | ZWO ASI294MC Pro | 296mm", "2026-01-01", [rig], "ZWO ASI294MC Pro", 296.0)[1] == v.RIG_UNASSIGNED
    assert v.assign_rig("OnStep | ZWO ASI294MC Pro", "2026-01-01", [rig], "ZWO ASI294MC Pro", None)[1] == v.RIG_UNASSIGNED
    assert v.assign_rig("OnStep | ZWO ASI533MC | 372mm", "2026-01-01", [rig], "ZWO ASI533MC", 372.0)[1] == v.RIG_UNASSIGNED


def test_matching_uses_the_stored_focal_length_and_never_reads_it_from_the_label():
    rig = {"id": "60ed-294", "camera": "asi294mcpro", "focal_min": 365, "focal_max": 378, "patterns": [], "date_ranges": []}
    assert v.assign_rig("anything at all", "2026-01-01", [rig], "ZWO ASI294MC Pro", 372.5)[0] == "60ed-294"
    assert v.assign_rig("OnStep | ZWO ASI294MC Pro | 372mm", "2026-01-01", [rig], "ZWO ASI294MC Pro")[1] == v.RIG_UNASSIGNED


def test_camera_only_rig_claims_any_focal_length():
    rig = {"id": "s50", "camera": "seestars50", "patterns": [], "date_ranges": []}
    assert v.assign_rig("Seestar S50 | Seestar S50", "2026-01-01", [rig], "Seestar S50", None)[0] == "s50"


def _train(text, instrument, focal, count=10, unassigned=None, first="2026-01-01T00:00:00", last="2026-02-01T00:00:00"):
    return {"optical_train": text, "instrument": instrument, "focal_length": focal, "file_count": count,
            "unassigned_count": count if unassigned is None else unassigned, "first_date": first, "last_date": last}


def test_suggestion_groups_the_users_seven_spellings_into_one_rig():
    trains = [_train(t, i, f, count=100 if "373mm" in t else 10) for t, i, f in USER_TRAINS]
    proposals = v.suggest_rigs(trains)

    assert len(proposals) == 1
    p = proposals[0]
    assert (p["id"], p["camera"], p["file_count"]) == ("asi294mcpro-373mm", "asi294mcpro", 160)
    assert p["focal_min"] < 369 and p["focal_max"] > 374 and len(p["optical_trains"]) == 7
    rig = dict(p, patterns=[], date_ranges=[])
    assert all(v.assign_rig(t, "2026-01-01", [rig], i, f)[0] == p["id"] for t, i, f in USER_TRAINS)


def test_suggested_nominal_focal_length_is_the_middle_measured_value_by_file_count():
    trains = [_train("a", "ZWO ASI294MC Pro", 369.0, count=10), _train("b", "ZWO ASI294MC Pro", 372.4, count=10),
              _train("c", "ZWO ASI294MC Pro", 374.0, count=100)]
    proposal = v.suggest_rigs(trains)[0]

    assert proposal["focal_nominal"] == 374.0 and proposal["name"] == "ZWO ASI294MC Pro"
    assert proposal["focal_min"] < 369 < 374 < proposal["focal_max"]


def test_suggestion_separates_a_reducer_and_another_camera():
    trains = [_train("OnStep | ZWO ASI294MC Pro | 372mm", "ZWO ASI294MC Pro", 372.0, 50),
              _train("OnStep | ZWO ASI294MC Pro | 298mm", "ZWO ASI294MC Pro", 298.0, 30),
              _train("OnStep | ZWO ASI183MM | 372mm", "ZWO ASI183MM", 372.0, 20)]
    proposals = v.suggest_rigs(trains)
    assert [(p["id"], p["file_count"]) for p in proposals] == [
        ("asi294mcpro-372mm", 50), ("asi294mcpro-298mm", 30), ("asi183mm-372mm", 20)]
    assert proposals[0]["focal_min"] > proposals[1]["focal_max"]


def test_suggestion_skips_assigned_trains_and_ones_without_camera_or_focal_length():
    trains = [_train("OnStep | ZWO ASI294MC Pro | 372mm", "ZWO ASI294MC Pro", 372.0, unassigned=0),
              _train("Seestar S50 | Seestar S50", "Seestar S50", None),
              _train("C8 | 2032mm", "Unknown", 2032.0)]
    assert v.suggest_rigs(trains) == []
