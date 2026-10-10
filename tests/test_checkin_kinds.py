from astro_tracker import checkin_kinds as k
from astro_tracker import checkout_layout as layout


def test_outputs_and_records_are_recognised():
    assert k.classify("NGC_6530_9_302x15sec_2026-08-13_2334_og.fits") == k.KIND_IMAGE
    assert k.classify("lights/M_20_wizardstack_732f.fits") == k.KIND_IMAGE
    assert k.classify("final/M8.jpg") == k.KIND_IMAGE
    assert k.classify("2026-07-23T02.04.48.log") == k.KIND_SIRIL_LOG
    assert k.classify("process/lights_conversion.txt") == k.KIND_SIRIL_CONVERSION
    assert k.classify("lights/lights_conversion.txt") == k.KIND_SIRIL_CONVERSION
    assert k.classify("StackingWizard_BETA_build_2026-08-27.md") == k.KIND_WIZARD_LOG
    assert k.classify("AstroWizard.log.txt") == k.KIND_WIZARD_LOG
    assert k.classify("m8.xpsm") == k.KIND_PIXINSIGHT
    assert k.classify("m8_final.psd") == k.KIND_PHOTOSHOP
    assert k.classify("notes.txt") == k.KIND_ATTACHMENT


def test_siril_intermediates_and_housekeeping_are_ignored():
    for rel in ("process/pp_lights_00001.fit", "process/r_bkg_pp_lights_00412.fits", "process/lights_.seq",
                "r_pp_lights_00007.fit", "lights_00001.fits", "process/drizztmp/x.fits",
                ".DS_Store", ".astro/state.json", "astro-manifest.json", "copy.fits.part"):
        assert k.classify(rel) is None, rel


def test_a_stack_named_lights_is_not_mistaken_for_a_sequence_file():
    assert k.classify("process/lights.fit") is None  # inside process/: Siril's own working copy
    assert k.classify("lights.fit") == k.KIND_IMAGE


def test_a_result_with_a_year_in_its_name_is_kept():
    assert k.classify("m31_2026.fits") == k.KIND_IMAGE


def test_run_is_suggested_from_what_is_present():
    assert k.suggest_run([("a.log", k.KIND_SIRIL_LOG), ("x.fits", k.KIND_IMAGE)]) == ("siril", "stacking")
    assert k.suggest_run([("StackingWizard_BETA.md", k.KIND_WIZARD_LOG)]) == ("stackingwizard", "stacking")
    assert k.suggest_run([("AstroWizard.log.txt", k.KIND_WIZARD_LOG), ("x.tif", k.KIND_IMAGE)]) == ("astrowizard", "post")
    assert k.suggest_run([("m8.psd", k.KIND_PHOTOSHOP)]) == ("photoshop", "post")
    assert k.suggest_run([("x.jpg", k.KIND_IMAGE)]) == ("unknown", "post")


def test_frame_count_read_from_tool_names():
    assert k.guess_frames("NGC_6530_9_302x15sec_2026-08-13_2026-10-06_2334_og.fits") == 302
    assert k.guess_frames("Butterfly_in_Cygnus_2026x10sec_2026-07-12_1923_og.fit") == 2026
    assert k.guess_frames("M_20_wizardstack_732f.fits") == 732
    assert k.guess_frames("M8_dwarfmini_UVIR_stack_302x15s_v01.fits") == 302
    assert k.guess_frames("m8_final.tif") is None


def test_stage_guesses():
    assert k.guess_stage("x_302x15sec_og.fits", "stacking") == "stack"
    assert k.guess_stage("x_302x15sec_spcc.fits", "stacking") == "stack-cc"
    assert k.guess_stage("x_spcc_cropped.fit", "stacking") == "stack-cc"
    assert k.guess_stage("m8_starless.xisf", "post") == "starless"
    assert k.guess_stage("x_302x15sec_og.fits", "post") == "stack"
    assert k.guess_stage("M_20_wizardstack_732f.fits", "post") == "stack"
    assert k.guess_stage("m8.jpg", "stacking") == "final"
    assert k.guess_stage("m8_processed.xisf", "post") == "final"


def _manifest(groups):
    return {"project": {"slug": "M8-2", "target_name": "M8"},
            "groups": [{"key": f"{r}__{f}", "rig": r, "filter": f, "entries": [{"file_name": "a.fit"}]} for r, f in groups]}


def test_single_group_gets_one_flat_lights_folder():
    plan = layout.plan_layout(_manifest([("s50", "LP")]), "naztronomy")
    assert [p["lights_dir"] for p in plan] == ["lights"]


def test_several_groups_get_a_subfolder_each():
    plan = layout.plan_layout(_manifest([("s50", "LP"), ("dwarfmini", "UVIR")]), "naztronomy")
    assert [p["lights_dir"] for p in plan] == ["s50_LP/lights", "dwarfmini_UVIR/lights"]


def test_unknown_profile_is_rejected():
    import pytest
    with pytest.raises(ValueError):
        layout.plan_layout(_manifest([("s50", "LP")]), "wbpp")


def test_working_folder_is_named_for_target_and_project():
    assert layout.working_folder_name(_manifest([("s50", "LP")])) == "M8__M8-2"
