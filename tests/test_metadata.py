from astro_tracker.location import parse_location
from astro_tracker.metadata import derive_optical_train, get_fits_metadata, normalize_frame_type


class TestDeriveOpticalTrain:
    def test_all_fields_present(self):
        assert derive_optical_train("Celestron NexStar 8SE", "ZWO ASI294MC Pro", 1200) == \
            "Celestron NexStar 8SE | ZWO ASI294MC Pro | 1200mm"

    def test_missing_telescope_uses_remaining_fields(self):
        assert derive_optical_train(None, "ZWO ASI294MC Pro", 1200) == "ZWO ASI294MC Pro | 1200mm"

    def test_missing_instrument_uses_remaining_fields(self):
        assert derive_optical_train("Celestron NexStar 8SE", None, 1200) == "Celestron NexStar 8SE | 1200mm"

    def test_missing_focal_length_uses_remaining_fields(self):
        assert derive_optical_train("Celestron NexStar 8SE", "ZWO ASI294MC Pro", None) == \
            "Celestron NexStar 8SE | ZWO ASI294MC Pro"

    def test_only_one_field_present(self):
        assert derive_optical_train(None, "Seestar S50", None) == "Seestar S50"

    def test_all_missing_falls_back_to_unknown(self):
        assert derive_optical_train(None, None, None) == "Unknown"
        assert derive_optical_train("", "", "") == "Unknown"


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

    def test_resolution_reflects_actual_image_dimensions(self, make_fits):
        # NAXIS1/NAXIS2 are structural FITS keywords astropy derives from the
        # real data array (width=cols=NAXIS1, height=rows=NAXIS2) -- shape
        # (3672, 5496) means 3672 rows x 5496 cols.
        path = make_fits("light_001.fits", {}, shape=(3672, 5496))
        meta = get_fits_metadata(path)
        assert meta["resolution"] == "5496x3672"

    def test_binning_extracted_when_present(self, make_fits):
        path = make_fits("light_001.fits", {"XBINNING": 2, "YBINNING": 2})
        meta = get_fits_metadata(path)
        assert meta["binning"] == "2x2"

    def test_binning_unknown_when_missing(self, make_fits):
        # XBINNING/YBINNING are optional header cards, unlike NAXIS1/NAXIS2
        # which astropy always derives from the data array -- many real
        # observatory headers omit binning entirely.
        path = make_fits("no_headers.fits", {})
        meta = get_fits_metadata(path)
        assert meta["binning"] == "Unknown"

    def test_optical_train_derived_from_headers(self, make_fits):
        path = make_fits("light_001.fits", {"TELESCOP": "Celestron NexStar 8SE", "INSTRUME": "ZWO ASI294MC Pro", "FOCALLEN": 1200})
        meta = get_fits_metadata(path)
        assert meta["optical_train"] == "Celestron NexStar 8SE | ZWO ASI294MC Pro | 1200mm"

    def test_optical_train_unknown_when_all_headers_missing(self, make_fits):
        path = make_fits("no_headers.fits", {})
        meta = get_fits_metadata(path)
        assert meta["optical_train"] == "Unknown"
