import math
import random
import time

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

    def test_ra_wraparound_merges_across_0_360_boundary(self):
        # A target sitting right at RA=0h: one sub logged at 359.9, another
        # at 0.1 -- 0.2 degrees apart in reality, but naive grid bucketing
        # (floor(ra)) would put them in cell 359 and cell 0, which aren't
        # numerically adjacent without explicit wraparound handling.
        files = [
            {"id": 1, "ra": 359.9, "dec": 10.0},
            {"id": 2, "ra": 0.1, "dec": 10.0},
        ]
        groups = cluster_files(files, tolerance_deg=1.0)
        assert groups[1] == groups[2]
        assert groups[1] is not None

    def test_large_library_with_many_distinct_targets_completes_quickly(self):
        # Regression test for the O(n^2) full-pairwise scan that made
        # clustering a real ~46,000-file library hang for hours in
        # practice. 50 distinct target pointings x 1000 tightly-clustered
        # subs each, scattered across the whole sky (including near the
        # RA=0/360 boundary) -- should resolve to exactly 50 groups, fast.
        random.seed(42)
        num_targets = 50
        subs_per_target = 1000
        centers = [
            (random.uniform(0, 360), random.uniform(-70, 70))
            for _ in range(num_targets)
        ]

        files = []
        next_id = 1
        for center_ra, center_dec in centers:
            for _ in range(subs_per_target):
                ra = (center_ra + random.uniform(-0.05, 0.05)) % 360
                dec = center_dec + random.uniform(-0.05, 0.05)
                files.append({"id": next_id, "ra": ra, "dec": dec})
                next_id += 1

        start = time.monotonic()
        groups = cluster_files(files, tolerance_deg=1.0)
        elapsed = time.monotonic() - start

        assert len(set(groups.values())) == num_targets
        assert elapsed < 10, f"clustering {len(files)} files took {elapsed:.1f}s, expected well under 10s"
