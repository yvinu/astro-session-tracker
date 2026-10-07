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
