import math

import pytest

from astro_tracker.clustering import angular_separation_deg, cluster_files


class TestAngularSeparation:
    def test_same_point_is_zero(self):
        assert angular_separation_deg(83.8, -5.4, 83.8, -5.4) == pytest.approx(0.0, abs=1e-9)

    def test_known_separation(self):
        # Two points 1 degree apart in RA along the celestial equator.
        sep = angular_separation_deg(0.0, 0.0, 1.0, 0.0)
        assert sep == pytest.approx(1.0, abs=1e-6)

    def test_antipodal_points(self):
        sep = angular_separation_deg(0.0, 0.0, 180.0, 0.0)
        assert sep == pytest.approx(180.0, abs=1e-6)


class TestClusterFiles:
    def test_close_files_with_different_labels_merge(self):
        files = [
            {"id": 1, "ra": 83.80, "dec": -5.39, "target": "M42"},
            {"id": 2, "ra": 83.83, "dec": -5.42, "target": "Orion Nebula"},
        ]
        groups = cluster_files(files, tolerance_deg=1.0)
        assert groups[1] == groups[2]
        assert groups[1] is not None

    def test_distant_files_with_same_label_do_not_merge(self):
        files = [
            {"id": 1, "ra": 10.0, "dec": 20.0, "target": "M31"},
            {"id": 2, "ra": 200.0, "dec": -20.0, "target": "M31"},
        ]
        groups = cluster_files(files, tolerance_deg=1.0)
        assert groups[1] != groups[2]
        assert groups[1] is not None
        assert groups[2] is not None

    def test_transitive_chain_merges_into_one_group(self):
        # A is close to B, B is close to C, but A and C alone would be just
        # outside tolerance -- the chain should still merge all three.
        files = [
            {"id": 1, "ra": 100.0, "dec": 0.0},
            {"id": 2, "ra": 100.9, "dec": 0.0},
            {"id": 3, "ra": 101.8, "dec": 0.0},
        ]
        groups = cluster_files(files, tolerance_deg=1.0)
        assert groups[1] == groups[2] == groups[3]

    def test_missing_coordinates_are_ungrouped_not_crashed(self):
        files = [
            {"id": 1, "ra": None, "dec": None},
            {"id": 2, "ra": 50.0, "dec": 10.0},
        ]
        groups = cluster_files(files, tolerance_deg=1.0)
        assert groups[1] is None
        assert groups[2] is not None

    def test_malformed_coordinates_are_ungrouped_not_crashed(self):
        files = [
            {"id": 1, "ra": "not-a-number", "dec": "12:34:56"},
            {"id": 2, "ra": 50.0, "dec": 10.0},
            {"id": 3, "ra": float("nan"), "dec": 10.0},
        ]
        groups = cluster_files(files, tolerance_deg=1.0)
        assert groups[1] is None
        assert groups[3] is None
        assert groups[2] is not None

    def test_empty_input_returns_empty(self):
        assert cluster_files([]) == {}

    def test_single_file_gets_its_own_group(self):
        groups = cluster_files([{"id": 1, "ra": 10.0, "dec": 10.0}])
        assert groups[1] == 0
