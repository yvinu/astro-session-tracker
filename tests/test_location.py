from astro_tracker.location import parse_location


def test_volumes_path_returns_volume_name():
    assert parse_location("/Volumes/Elements_1TB_clone/Astrophotography/M31/light_001.fits") == "Elements_1TB_clone"


def test_volume_name_with_spaces():
    assert parse_location("/Volumes/Elements 1TB/AP/light_001.fits") == "Elements 1TB"


def test_home_directory_path_is_internal():
    assert parse_location("/Users/yvinu/Documents/AP/light_001.fits") == "Internal"


def test_double_leading_slash_is_handled():
    assert parse_location("//Volumes/Multimedia/AstroPhotos/light_001.fits") == "Multimedia"


def test_relative_path_falls_back_to_internal():
    assert parse_location("AP/light_001.fits") == "Internal"


def test_volumes_root_with_no_volume_name_falls_back_to_internal():
    assert parse_location("/Volumes/") == "Internal"
