from astro_tracker.location import parse_location
from astro_tracker.metadata import get_fits_metadata, normalize_frame_type


class TestNormalizeFrameType:
    def test_unknown_when_missing(self):
        assert normalize_frame_type(None) == "Unknown"
        assert normalize_frame_type("") == "Unknown"
        assert normalize_frame_type("Unknown") == "Unknown"

    def test_light_variants(self):
        assert normalize_frame_type("Light Frame") == "Light"
        assert normalize_frame_type("light") == "Light"
        assert normalize_frame_type("0") == "Light"
        assert normalize_frame_type("science") == "Light"

    def test_calibration_variants(self):
        assert normalize_frame_type("Dark Frame") == "Dark"
        assert normalize_frame_type("2") == "Dark"
        assert normalize_frame_type("Bias Frame") == "Bias"
        assert normalize_frame_type("1") == "Bias"
        assert normalize_frame_type("Flat Frame") == "Flat"
        assert normalize_frame_type("3") == "Flat"

    def test_master_variants_checked_before_substring_match(self):
        assert normalize_frame_type("Master Dark") == "Master Dark"
        assert normalize_frame_type("MASTER FLAT FRAME") == "Master Flat"
        assert normalize_frame_type("master bias") == "Master Bias"
        assert normalize_frame_type("Master Light") == "Master Light"
        assert normalize_frame_type("Master") == "Master"

    def test_malformed_header_junk_is_unknown(self):
        assert normalize_frame_type("IMAGETYP= 'Light   '") == "Unknown"
        assert normalize_frame_type("FOO: BAR") == "Unknown"
        assert normalize_frame_type("x" * 60) == "Unknown"
        assert normalize_frame_type("   ") == "Unknown"

    def test_unrecognized_but_printable_value_is_preserved(self):
        assert normalize_frame_type("Calibration") == "Calibration"


class TestGetFitsMetadata:
    def test_extracts_core_fields(self, make_fits):
        path = make_fits("light_001.fits", {
            "IMAGETYP": "Light Frame",
            "OBJECT": "M31",
            "DATE-OBS": "2026-07-01T21:00:00",
            "EXPTIME": 30.0,
            "GAIN": 100,
            "SET-TEMP": -10,
            "FILTER": "LP",
            "INSTRUME": "Seestar S50",
        })
        meta = get_fits_metadata(path)
        assert meta is not None
        assert meta["target"] == "M31"
        assert meta["frame_type"] == "Light"
        assert meta["file_category"] == "Subframe"
        assert meta["exposure"] == 30.0
        assert meta["filter"] == "LP"
        assert meta["instrument"] == "Seestar S50"

    def test_filename_keyword_marks_processed(self, make_fits):
        path = make_fits("M31_stacked.fits", {"IMAGETYP": "Light Frame", "OBJECT": "M31"})
        meta = get_fits_metadata(path)
        assert meta["file_category"] == "Processed"

    def test_master_frame_type_marks_processed_even_without_filename_keyword(self, make_fits):
        path = make_fits("cal_001.fits", {"IMAGETYP": "Master Dark"})
        meta = get_fits_metadata(path)
        assert meta["file_category"] == "Processed"
        assert meta["frame_type"] == "Master Dark"

    def test_missing_header_falls_back_to_defaults(self, make_fits):
        path = make_fits("no_headers.fits", {})
        meta = get_fits_metadata(path)
        assert meta["target"] == "Unknown"
        assert meta["frame_type"] == "Unknown"
        assert meta["filter"] == "No Filter"

    def test_ra_dec_extracted_when_present(self, make_fits):
        path = make_fits("m42.fits", {"OBJECT": "M42", "RA": 83.822, "DEC": -5.391})
        meta = get_fits_metadata(path)
        assert meta["ra"] == 83.822
        assert meta["dec"] == -5.391

    def test_corrupt_file_returns_none(self, tmp_path):
        bad_path = tmp_path / "corrupt.fits"
        bad_path.write_bytes(b"not a real fits file")
        assert get_fits_metadata(str(bad_path)) is None

    def test_location_matches_path_parsing(self, make_fits):
        path = make_fits("light_001.fits", {"OBJECT": "M31"})
        meta = get_fits_metadata(path)
        assert meta["location"] == parse_location(path)
