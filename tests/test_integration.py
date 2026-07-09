import pytest

from astro_tracker.integration import grand_integrated_mean_midpoint, total_integration_seconds


class TestTotalIntegrationSeconds:
    def test_sums_light_frames_only(self):
        files = [
            {"frame_type": "Light", "exposure": 30},
            {"frame_type": "Light", "exposure": 30},
            {"frame_type": "Light", "exposure": 30},
            {"frame_type": "Dark", "exposure": 30},
            {"frame_type": "Flat", "exposure": 5},
        ]
        assert total_integration_seconds(files) == 90

    def test_empty_input_is_zero(self):
        assert total_integration_seconds([]) == 0

    def test_no_light_frames_is_zero(self):
        files = [{"frame_type": "Dark", "exposure": 30}]
        assert total_integration_seconds(files) == 0

    def test_missing_or_zero_exposure_treated_as_zero(self):
        files = [
            {"frame_type": "Light", "exposure": None},
            {"frame_type": "Light", "exposure": 0},
            {"frame_type": "Light", "exposure": 10},
        ]
        assert total_integration_seconds(files) == 10


class TestGrandIntegratedMeanMidpoint:
    def test_single_file(self):
        # Midpoint = start + exposure/2 = 21:00:00 + 30s = 21:00:30
        files = [{"frame_type": "Light", "date": "2026-07-08T21:00:00", "exposure": 60}]
        result = grand_integrated_mean_midpoint(files)
        assert result == "2026-07-08T21:00:30+00:00"

    def test_hand_computed_weighted_average(self):
        # A: start 20:00:00, exposure 60s  -> midpoint 20:00:30
        # B: start 20:10:00, exposure 180s -> midpoint 20:11:30
        # Weighted mean (seconds since 20:00:00): (30*60 + 690*180) / 240 = 525s = 20:08:45
        files = [
            {"frame_type": "Light", "date": "2026-07-08T20:00:00", "exposure": 60},
            {"frame_type": "Light", "date": "2026-07-08T20:10:00", "exposure": 180},
        ]
        result = grand_integrated_mean_midpoint(files)
        assert result == "2026-07-08T20:08:45+00:00"

    def test_midnight_boundary(self):
        # A: start 23:30:00 Jul 8, exposure 1800s (30min) -> midpoint 23:45:00 Jul 8
        # B: start 00:15:00 Jul 9, exposure 1800s (30min) -> midpoint 00:30:00 Jul 9
        # Equal weights -> mean is the plain midpoint between the two: 00:07:30 Jul 9
        files = [
            {"frame_type": "Light", "date": "2026-07-08T23:30:00", "exposure": 1800},
            {"frame_type": "Light", "date": "2026-07-09T00:15:00", "exposure": 1800},
        ]
        result = grand_integrated_mean_midpoint(files)
        assert result == "2026-07-09T00:07:30+00:00"
        assert total_integration_seconds(files) == 3600

    def test_excludes_calibration_frames_from_midpoint(self):
        files = [
            {"frame_type": "Light", "date": "2026-07-08T21:00:00", "exposure": 60},
            {"frame_type": "Dark", "date": "2026-07-08T19:00:00", "exposure": 60},
        ]
        result = grand_integrated_mean_midpoint(files)
        assert result == "2026-07-08T21:00:30+00:00"

    def test_no_light_frames_returns_none(self):
        files = [{"frame_type": "Dark", "date": "2026-07-08T21:00:00", "exposure": 60}]
        assert grand_integrated_mean_midpoint(files) is None

    def test_empty_input_returns_none(self):
        assert grand_integrated_mean_midpoint([]) is None

    def test_unparseable_date_is_excluded_not_crashed(self):
        files = [
            {"frame_type": "Light", "date": "Unknown", "exposure": 60},
            {"frame_type": "Light", "date": "2026-07-08T21:00:00", "exposure": 60},
        ]
        result = grand_integrated_mean_midpoint(files)
        assert result == "2026-07-08T21:00:30+00:00"
