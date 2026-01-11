"""
Tests for strip accessibility algorithm.

Validates the core strip window requirement:
For a valid strip window [start, end], at any proportional time t_i = start + (i/K) * (end - start),
the corresponding strip sample point[i] must be visible to the satellite.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import List

import pytest

from engines.astrox.models import Satellite, Target
from engines.astrox.orbital.access import (
    compute_accessibility,
    compute_strip_accessibility,
    _interpolate_polyline,
    _find_candidate_passes,
    _validate_sweep,
    StripPoints,
)


TLE_LINE1 = "1 00876U 64053A   25197.80792236  .00000096  00000-0  38700-4 0  9997"
TLE_LINE2 = "2 00876  65.0587 236.5281 0126526  27.3600 333.4089 14.65407507239521"


@pytest.fixture
def satellite() -> Satellite:
    return Satellite(
        tle_line1=TLE_LINE1,
        tle_line2=TLE_LINE2,
        apogee_km=420.0,
        perigee_km=418.0,
        period_min=92.9,
        inclination_deg=65.06,
    )


@pytest.fixture
def time_window() -> tuple[str, str]:
    return ("2025-07-17T00:00:00.000Z", "2025-07-17T12:00:00.000Z")


class TestPolylineInterpolation:

    def test_interpolation_preserves_endpoints(self):
        points: StripPoints = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]
        samples = _interpolate_polyline(points, 5)
        assert len(samples) == 5
        assert samples[0] == (0.0, 0.0)
        assert samples[-1] == (1.0, 1.0)

    def test_interpolation_evenly_spaced(self):
        points: StripPoints = [(0.0, 0.0), (2.0, 0.0)]
        samples = _interpolate_polyline(points, 5)
        expected = [(0.0, 0.0), (0.5, 0.0), (1.0, 0.0), (1.5, 0.0), (2.0, 0.0)]
        for s, e in zip(samples, expected):
            assert abs(s[0] - e[0]) < 1e-9
            assert abs(s[1] - e[1]) < 1e-9

    def test_interpolation_handles_two_points(self):
        points: StripPoints = [(10.0, 20.0), (30.0, 40.0)]
        samples = _interpolate_polyline(points, 3)
        assert len(samples) == 3
        assert samples[0] == (10.0, 20.0)
        assert samples[-1] == (30.0, 40.0)


class TestStripWindowDefinition:
    """
    Core validation: a strip window must satisfy the monotonic sweep property.
    At t_i = start + (i/(K-1)) * (end - start), point[i] must be visible.
    """

    def test_strip_windows_satisfy_monotonic_sweep(
        self, satellite: Satellite, time_window: tuple[str, str]
    ):
        strip: StripPoints = [(40.0, -75.0), (45.0, -75.0)]
        num_samples = 10

        strip_windows = compute_strip_accessibility(
            satellite, strip, time_window, num_samples=num_samples
        )
        assert len(strip_windows) > 0, "Expected at least one strip window"

        samples = _interpolate_polyline(strip, num_samples)
        head_target = Target(latitude_deg=samples[0][0], longitude_deg=samples[0][1])
        tail_target = Target(latitude_deg=samples[-1][0], longitude_deg=samples[-1][1])

        for sw in strip_windows:
            strip_start = sw.start
            strip_end = sw.end

            query_start = strip_start - timedelta(seconds=5)
            query_end = strip_end + timedelta(seconds=5)
            query_window = (
                query_start.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                query_end.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            )

            head_windows = compute_accessibility(satellite, head_target, query_window)
            tail_windows = compute_accessibility(satellite, tail_target, query_window)
            assert head_windows and tail_windows

            head_start = head_windows[0].start
            tail_start = tail_windows[0].start
            is_forward = head_start <= tail_start

            ordered_samples = samples if is_forward else samples[::-1]

            for i, (lat, lon) in enumerate(ordered_samples):
                t_i = strip_start + (i / (num_samples - 1)) * (strip_end - strip_start)
                target = Target(latitude_deg=lat, longitude_deg=lon)

                point_windows = compute_accessibility(satellite, target, query_window)

                tolerance = timedelta(milliseconds=100)
                point_visible_at_ti = any(
                    (pw.start - tolerance) <= t_i <= (pw.end + tolerance)
                    for pw in point_windows
                )

                assert point_visible_at_ti, (
                    f"Strip window validation failed: "
                    f"at t_i={t_i.isoformat()} (i={i}/{num_samples}, {'forward' if is_forward else 'backward'}), "
                    f"point ({lat}, {lon}) is NOT visible. "
                    f"Strip window: {strip_start.isoformat()} -> {strip_end.isoformat()}"
                )

    def test_strip_windows_forward_and_backward_sweeps(
        self, satellite: Satellite, time_window: tuple[str, str]
    ):
        strip: StripPoints = [(40.0, -75.0), (42.0, -74.0), (44.0, -75.0)]
        num_samples = 8

        strip_windows = compute_strip_accessibility(
            satellite, strip, time_window, num_samples=num_samples
        )

        assert len(strip_windows) > 0, "Expected at least one strip window"

        samples = _interpolate_polyline(strip, num_samples)

        for sw in strip_windows:
            head_target = Target(latitude_deg=samples[0][0], longitude_deg=samples[0][1])
            tail_target = Target(latitude_deg=samples[-1][0], longitude_deg=samples[-1][1])

            query_start = sw.start - timedelta(seconds=1)
            query_end = sw.end + timedelta(seconds=1)
            pass_time_window = (
                query_start.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                query_end.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            )

            head_windows = compute_accessibility(satellite, head_target, pass_time_window)
            tail_windows = compute_accessibility(satellite, tail_target, pass_time_window)

            assert len(head_windows) > 0, "Head must be visible during strip window"
            assert len(tail_windows) > 0, "Tail must be visible during strip window"


class TestStripAccessibilityReturnsValidWindows:

    def test_returns_windows_for_short_strip(
        self, satellite: Satellite, time_window: tuple[str, str]
    ):
        strip: StripPoints = [(40.0, -75.0), (41.0, -75.0)]
        windows = compute_strip_accessibility(satellite, strip, time_window, num_samples=5)
        assert len(windows) > 0

    def test_returns_windows_for_long_strip(
        self, satellite: Satellite, time_window: tuple[str, str]
    ):
        strip: StripPoints = [(40.0, -75.0), (50.0, -75.0)]
        windows = compute_strip_accessibility(satellite, strip, time_window, num_samples=15)
        assert len(windows) > 0

    def test_returns_empty_for_invalid_strip(
        self, satellite: Satellite, time_window: tuple[str, str]
    ):
        strip: StripPoints = [(40.0, -75.0)]
        with pytest.raises(ValueError, match="at least 2 points"):
            compute_strip_accessibility(satellite, strip, time_window)


class TestStripWindowProperties:

    def test_strip_window_has_duration(
        self, satellite: Satellite, time_window: tuple[str, str]
    ):
        strip: StripPoints = [(40.0, -75.0), (42.0, -75.0)]
        windows = compute_strip_accessibility(satellite, strip, time_window, num_samples=5)
        assert len(windows) > 0
        for w in windows:
            assert w.start < w.end
            assert w.duration_sec > 0
            assert abs(w.duration_sec - (w.end - w.start).total_seconds()) < 0.1

    def test_strip_window_has_null_elevation_fields(
        self, satellite: Satellite, time_window: tuple[str, str]
    ):
        strip: StripPoints = [(40.0, -75.0), (42.0, -75.0)]
        windows = compute_strip_accessibility(satellite, strip, time_window, num_samples=5)
        assert len(windows) > 0
        for w in windows:
            assert w.max_elevation_deg is None
            assert w.max_elevation_point is None
            assert w.min_range_point is None
            assert w.mean_elevation_deg is None
            assert w.mean_range_m is None
            assert w.aer_samples is None
