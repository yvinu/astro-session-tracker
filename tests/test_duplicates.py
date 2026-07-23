from astro_tracker.duplicates import find_duplicate_groups


class TestFindDuplicateGroups:
    def test_matching_fingerprint_groups_together(self):
        files = [
            {"id": 1, "size": 100, "date": "2026-07-01T21:00:00", "exposure": 30.0,
             "target": "M31", "instrument": "Seestar S50"},
            {"id": 2, "size": 100, "date": "2026-07-01T21:00:00", "exposure": 30.0,
             "target": "M31", "instrument": "Seestar S50"},
        ]
        groups = find_duplicate_groups(files)
        assert groups[1] == groups[2]
        assert groups[1] is not None

    def test_differing_size_does_not_group(self):
        base = {"date": "2026-07-01T21:00:00", "exposure": 30.0, "target": "M31", "instrument": "Seestar S50"}
        files = [{"id": 1, "size": 100, **base}, {"id": 2, "size": 200, **base}]
        groups = find_duplicate_groups(files)
        assert groups[1] is None
        assert groups[2] is None

    def test_differing_date_does_not_group(self):
        base = {"size": 100, "exposure": 30.0, "target": "M31", "instrument": "Seestar S50"}
        files = [
            {"id": 1, "date": "2026-07-01T21:00:00", **base},
            {"id": 2, "date": "2026-07-01T21:00:05", **base},
        ]
        groups = find_duplicate_groups(files)
        assert groups[1] is None
        assert groups[2] is None

    def test_differing_exposure_does_not_group(self):
        base = {"size": 100, "date": "2026-07-01T21:00:00", "target": "M31", "instrument": "Seestar S50"}
        files = [{"id": 1, "exposure": 30.0, **base}, {"id": 2, "exposure": 10.0, **base}]
        groups = find_duplicate_groups(files)
        assert groups[1] is None
        assert groups[2] is None

    def test_differing_target_does_not_group(self):
        base = {"size": 100, "date": "2026-07-01T21:00:00", "exposure": 30.0, "instrument": "Seestar S50"}
        files = [{"id": 1, "target": "M31", **base}, {"id": 2, "target": "M42", **base}]
        groups = find_duplicate_groups(files)
        assert groups[1] is None
        assert groups[2] is None

    def test_differing_instrument_does_not_group(self):
        base = {"size": 100, "date": "2026-07-01T21:00:00", "exposure": 30.0, "target": "M31"}
        files = [{"id": 1, "instrument": "Seestar S50", **base}, {"id": 2, "instrument": "ZWO ASI294MC", **base}]
        groups = find_duplicate_groups(files)
        assert groups[1] is None
        assert groups[2] is None

    def test_missing_fingerprint_field_is_ungrouped_not_crashed(self):
        files = [
            {"id": 1, "size": 100, "date": None, "exposure": 30.0, "target": "M31", "instrument": "Seestar S50"},
            {"id": 2, "size": 100, "date": "2026-07-01T21:00:00", "exposure": 30.0,
             "target": "M31", "instrument": "Seestar S50"},
        ]
        groups = find_duplicate_groups(files)
        assert groups[1] is None
        assert groups[2] is None  # file 2 has no other file sharing its complete fingerprint

    def test_lone_file_with_unique_fingerprint_is_ungrouped(self):
        files = [
            {"id": 1, "size": 100, "date": "2026-07-01T21:00:00", "exposure": 30.0,
             "target": "M31", "instrument": "Seestar S50"},
        ]
        groups = find_duplicate_groups(files)
        assert groups[1] is None

    def test_three_way_duplicate_all_grouped_together(self):
        base = {"size": 100, "date": "2026-07-01T21:00:00", "exposure": 30.0,
                "target": "M31", "instrument": "Seestar S50"}
        files = [{"id": 1, **base}, {"id": 2, **base}, {"id": 3, **base}]
        groups = find_duplicate_groups(files)
        assert groups[1] == groups[2] == groups[3]
        assert groups[1] is not None

    def test_two_separate_duplicate_pairs_get_different_groups(self):
        base = {"size": 100, "exposure": 30.0, "target": "M31", "instrument": "Seestar S50"}
        files = [
            {"id": 1, "date": "2026-07-01T21:00:00", **base},
            {"id": 2, "date": "2026-07-01T21:00:00", **base},
            {"id": 3, "date": "2026-07-02T21:00:00", **base},
            {"id": 4, "date": "2026-07-02T21:00:00", **base},
        ]
        groups = find_duplicate_groups(files)
        assert groups[1] == groups[2]
        assert groups[3] == groups[4]
        assert groups[1] != groups[3]

    def test_empty_input_returns_empty(self):
        assert find_duplicate_groups([]) == {}
