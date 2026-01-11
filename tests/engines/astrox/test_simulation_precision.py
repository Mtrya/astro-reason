"""
Simulation precision tests that cross-validate the physics engine by:
1. Checking geometric occlusion (LOS) against computed access windows.
2. Verifying quaternion round-trip (geometric windows -> quaternions -> recomputed windows).
"""

from __future__ import annotations

import math
import requests
from datetime import datetime, timezone, timedelta
from typing import List, Tuple, Optional

import pytest

from engines.astrox.orbital.access import compute_accessibility, ASTROX_API_URL, AstroxAPIError
from engines.astrox.orbital.propagation import propagate_satellite
from engines.astrox.orbital.attitude import lla_to_eci, calculate_quaternion_series, quaternion_eci_to_ecef
from engines.astrox.models import Satellite, Target, AccessWindow, ElevationAngleConstraint


ISS_TLE_LINE1 = "1 00876U 64053A   25197.80792236  .00000096  00000-0  38700-4 0  9997"
ISS_TLE_LINE2 = "2 00876  65.0587 236.5281 0126526  27.3600 333.4089 14.65407507239521"

EARTH_RADIUS_M = 6378137.0
EARTH_RADIUS_POLAR_M = 6356752.3


def _dot(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _sub(a: List[float], b: List[float]) -> List[float]:
    return [x - y for x, y in zip(a, b)]


def _norm(v: List[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def is_occluded_by_earth(sat_pos_m: List[float], target_pos_m: List[float]) -> bool:
    """Check if LOS from satellite to target is blocked by Earth."""
    earth_center = [0.0, 0.0, 0.0]
    r_earth = (EARTH_RADIUS_M + EARTH_RADIUS_POLAR_M) / 2

    d = _sub(target_pos_m, sat_pos_m)
    f = _sub(sat_pos_m, earth_center)

    a = _dot(d, d)
    b = 2.0 * _dot(f, d)
    c = _dot(f, f) - r_earth * r_earth

    discriminant = b * b - 4 * a * c
    if discriminant < 0:
        return False

    sqrt_disc = math.sqrt(discriminant)
    t1 = (-b - sqrt_disc) / (2 * a)
    t2 = (-b + sqrt_disc) / (2 * a)

    return (0 < t1 < 1) or (0 < t2 < 1)


def compute_access_with_orientation(
    satellite: Satellite,
    target: Target,
    time_window: Tuple[str, str],
    orientation_epoch: str,
    unit_quaternion_series: List[float],
    sensor_half_angle_deg: float = 5.0,
) -> List[AccessWindow]:
    """Compute access windows with custom orientation (CzmlOrientation) and sensor."""
    start_time, end_time = time_window

    payload = {
        "Start": start_time,
        "Stop": end_time,
        "FromObjectPath": {
            "Name": "target",
            "Position": {
                "$type": "SitePosition",
                "cartographicDegrees": [
                    target.longitude_deg,
                    target.latitude_deg,
                    target.altitude_m,
                ],
            },
        },
        "ToObjectPath": {
            "Name": "sat",
            "Position": {
                "$type": "SGP4",
                "TLEs": [satellite.tle_line1, satellite.tle_line2],
            },
            "Orientation": {
                "$type": "CzmlOrientation",
                "epoch": orientation_epoch,
                "unitQuaternion": unit_quaternion_series,
                "interpolationAlgorithm": "LINEAR",
                "interpolationDegree": 1,
            },
            "Sensor": {
                "$type": "Conic",
                "outerHalfAngle": sensor_half_angle_deg,
            },
        },
        "ComputeAER": True,
    }

    response = requests.post(
        f"{ASTROX_API_URL}/access/AccessComputeV2", json=payload, timeout=60
    )
    response.raise_for_status()
    data = response.json()

    if not data.get("IsSuccess"):
        raise AstroxAPIError(f"Astrox API error: {data.get('Message', 'Unknown')}")

    windows: List[AccessWindow] = []
    for pass_data in data.get("Passes", []):
        start = datetime.fromisoformat(pass_data["AccessStart"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(pass_data["AccessStop"].replace("Z", "+00:00"))
        windows.append(
            AccessWindow(
                start=start,
                end=end,
                duration_sec=pass_data["Duration"],
                max_elevation_deg=pass_data.get("MaxElevationData", {}).get("Elevation"),
            )
        )
    return windows


class TestGeometricOcclusionValidation:
    """Test 1: Validate access windows by checking LOS geometry."""

    @pytest.fixture
    def satellite(self) -> Satellite:
        return Satellite(
            tle_line1=ISS_TLE_LINE1,
            tle_line2=ISS_TLE_LINE2,
            apogee_km=420,
            perigee_km=415,
            period_min=92.9,
            inclination_deg=51.64,
        )

    @pytest.fixture
    def target(self) -> Target:
        return Target(latitude_deg=40.0, longitude_deg=-74.0, altitude_m=0.0)

    def test_access_windows_match_occlusion_geometry(self, satellite: Satellite, target: Target):
        """Verify that computed access windows match LOS geometry."""
        base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end_time = base_time + timedelta(hours=6)

        windows = compute_accessibility(
            satellite,
            target,
            (base_time.isoformat().replace("+00:00", "Z"), end_time.isoformat().replace("+00:00", "Z")),
        )

        assert len(windows) > 0, "Expected at least one access window"

        target_eci_cache = {}

        def get_target_eci(dt: datetime) -> List[float]:
            key = dt.isoformat()
            if key not in target_eci_cache:
                pos = lla_to_eci(target.latitude_deg, target.longitude_deg, target.altitude_m, dt)
                target_eci_cache[key] = list(pos)
            return target_eci_cache[key]

        in_window_samples: List[datetime] = []
        for w in windows:
            mid = w.start + (w.end - w.start) / 2
            in_window_samples.append(mid)
            if (w.end - w.start).total_seconds() > 60:
                in_window_samples.append(w.start + timedelta(seconds=30))
                in_window_samples.append(w.end - timedelta(seconds=30))

        out_of_window_samples: List[datetime] = []
        sorted_windows = sorted(windows, key=lambda w: w.start)

        if sorted_windows[0].start > base_time + timedelta(minutes=5):
            out_of_window_samples.append(base_time + timedelta(minutes=2))

        for i in range(len(sorted_windows) - 1):
            gap_start = sorted_windows[i].end
            gap_end = sorted_windows[i + 1].start
            gap_duration = (gap_end - gap_start).total_seconds()
            if gap_duration > 60:
                out_of_window_samples.append(gap_start + timedelta(seconds=gap_duration / 2))

        if sorted_windows[-1].end < end_time - timedelta(minutes=5):
            out_of_window_samples.append(end_time - timedelta(minutes=2))

        all_samples = in_window_samples + out_of_window_samples
        rv_list = propagate_satellite(satellite.tle_line1, satellite.tle_line2, all_samples)

        in_window_results = []
        for i, sample in enumerate(in_window_samples):
            sat_pos, _ = rv_list[i]
            target_pos = get_target_eci(sample)
            occluded = is_occluded_by_earth(sat_pos, target_pos)
            in_window_results.append((sample, occluded))

        out_window_results = []
        offset = len(in_window_samples)
        for i, sample in enumerate(out_of_window_samples):
            sat_pos, _ = rv_list[offset + i]
            target_pos = get_target_eci(sample)
            occluded = is_occluded_by_earth(sat_pos, target_pos)
            out_window_results.append((sample, occluded))

        in_window_failures = [(t, occ) for t, occ in in_window_results if occ]
        assert len(in_window_failures) == 0, (
            f"Expected no occlusion within access windows, but found {len(in_window_failures)} occluded samples: "
            f"{[(t.isoformat(), occ) for t, occ in in_window_failures[:3]]}"
        )

        out_window_passes = [(t, occ) for t, occ in out_window_results if not occ]
        assert len(out_window_passes) == 0, (
            f"Expected all samples outside windows to be occluded, but {len(out_window_passes)} of "
            f"{len(out_window_results)} had LOS. This may indicate a geometry mismatch."
        )


class TestQuaternionDiagnostic:
    """Focused diagnostic tests to isolate quaternion-related issues."""

    @pytest.fixture
    def satellite(self) -> Satellite:
        return Satellite(
            tle_line1=ISS_TLE_LINE1,
            tle_line2=ISS_TLE_LINE2,
            apogee_km=420,
            perigee_km=415,
            period_min=92.9,
            inclination_deg=51.64,
        )

    @pytest.fixture
    def target(self) -> Target:
        return Target(latitude_deg=20.0, longitude_deg=139.0, altitude_m=0.0)

    def test_quaternion_points_at_target(self, satellite: Satellite, target: Target):
        """Verify that calculated quaternions actually point the sensor at the target."""
        base_time = datetime(2025, 7, 16, 0, 0, 0, tzinfo=timezone.utc)
        end_time = base_time + timedelta(hours=24)
        time_window = (
            base_time.isoformat().replace("+00:00", "Z"),
            end_time.isoformat().replace("+00:00", "Z"),
        )

        geometric_windows = compute_accessibility(satellite, target, time_window)
        assert len(geometric_windows) > 0, "Expected at least one geometric access window"

        window = geometric_windows[0]
        mid_time = window.start + (window.end - window.start) / 2

        rv_list = propagate_satellite(satellite.tle_line1, satellite.tle_line2, [mid_time])
        sat_pos, sat_vel = rv_list[0]
        target_eci = list(lla_to_eci(target.latitude_deg, target.longitude_deg, target.altitude_m, mid_time))

        target_obs_actions = [(mid_time, mid_time, target.latitude_deg, target.longitude_deg, target.altitude_m)]
        strip_obs_actions = []  # Empty list for strip observations
        quaternions = calculate_quaternion_series(
            satellite.tle_line1, satellite.tle_line2, target_obs_actions, strip_obs_actions, [mid_time]
        )
        q = quaternions[0]

        def quat_rotate(q, v):
            """Rotate vector v by quaternion q (x, y, z, w format)."""
            qx, qy, qz, qw = q
            vx, vy, vz = v
            
            t0 = qw * vx + qy * vz - qz * vy
            t1 = qw * vy + qz * vx - qx * vz
            t2 = qw * vz + qx * vy - qy * vx
            t3 = -qx * vx - qy * vy - qz * vz

            rx = t0 * qw - t1 * qz + t2 * qy - t3 * qx
            ry = t1 * qw - t2 * qx + t0 * qz - t3 * qy
            rz = t2 * qw - t0 * qy + t1 * qx - t3 * qz
            
            return [rx, ry, rz]

        sensor_z_body = [0.0, 0.0, 1.0]
        sensor_z_eci = quat_rotate(q, sensor_z_body)

        target_dir = _sub(target_eci, sat_pos)
        target_dir_norm = [x / _norm(target_dir) for x in target_dir]

        dot_product = _dot(sensor_z_eci, target_dir_norm)
        angle_deg = math.degrees(math.acos(max(-1.0, min(1.0, dot_product))))

        print(f"\n{'='*80}")
        print("QUATERNION POINTING DIAGNOSTIC")
        print(f"{'='*80}")
        print(f"Time: {mid_time.isoformat()}")
        print(f"Sat position (ECI): [{sat_pos[0]:.0f}, {sat_pos[1]:.0f}, {sat_pos[2]:.0f}] m")
        print(f"Target position (ECI): [{target_eci[0]:.0f}, {target_eci[1]:.0f}, {target_eci[2]:.0f}] m")
        print(f"Quaternion (x,y,z,w): [{q[0]:.6f}, {q[1]:.6f}, {q[2]:.6f}, {q[3]:.6f}]")
        print(f"Sensor Z-axis (ECI): [{sensor_z_eci[0]:.6f}, {sensor_z_eci[1]:.6f}, {sensor_z_eci[2]:.6f}]")
        print(f"Target direction (normalized): [{target_dir_norm[0]:.6f}, {target_dir_norm[1]:.6f}, {target_dir_norm[2]:.6f}]")
        print(f"Angle between sensor Z and target: {angle_deg:.2f}°")
        print(f"{'='*80}")

        assert angle_deg < 5.0, (
            f"Quaternion does not point at target! Angle = {angle_deg:.2f}° (expected < 5°)"
        )



class TestQuaternionRoundTrip:
    """Test 2: Validate quaternion calculations produce consistent windows."""

    @pytest.fixture
    def satellite(self) -> Satellite:
        return Satellite(
            tle_line1=ISS_TLE_LINE1,
            tle_line2=ISS_TLE_LINE2,
            apogee_km=420,
            perigee_km=415,
            period_min=92.9,
            inclination_deg=51.64,
        )

    @pytest.fixture
    def target(self) -> Target:
        return Target(latitude_deg=20.0, longitude_deg=139.0, altitude_m=0.0)

    def test_quaternion_round_trip_all_windows(
        self, satellite: Satellite, target: Target
    ):
        """Verify geometric windows and quaternion-recomputed windows match for ALL windows."""
        base_time = datetime(2025, 7, 16, 0, 0, 0, tzinfo=timezone.utc)
        end_time = base_time + timedelta(hours=24)
        time_window = (
            base_time.isoformat().replace("+00:00", "Z"),
            end_time.isoformat().replace("+00:00", "Z"),
        )

        constraints = [ElevationAngleConstraint(minimum_deg=20.0)]

        geometric_windows = compute_accessibility(satellite, target, time_window, constraints)
        assert len(geometric_windows) > 0, "Expected at least one geometric access window"

        print(f"\n{'='*80}")
        print(f"QUATERNION ROUND-TRIP DIAGNOSTIC (BATCHED)")
        print(f"{'='*80}")
        print(f"Time window: {time_window[0]} to {time_window[1]}")
        print(f"Geometric windows found: {len(geometric_windows)}")

        actions: List[Tuple[datetime, datetime, float, float, float]] = []
        for idx, window in enumerate(geometric_windows):
            obs_start = window.start + timedelta(seconds=10)
            obs_end = window.end - timedelta(seconds=10)
            if (obs_end - obs_start).total_seconds() < 20:
                obs_start = window.start
                obs_end = window.end
            actions.append((obs_start, obs_end, target.latitude_deg, target.longitude_deg, target.altitude_m))
            print(f"  Action {idx + 1}: {obs_start.isoformat()} to {obs_end.isoformat()}")

        time_step_sec = 10.0
        time_points: List[datetime] = []
        t = base_time
        while t <= end_time:
            time_points.append(t)
            t += timedelta(seconds=time_step_sec)

        print(f"\nGenerating quaternion series for {len(time_points)} time points...")
        quaternions_eci = calculate_quaternion_series(
            satellite.tle_line1, satellite.tle_line2, actions, [], time_points
        )

        print("Transforming quaternions from ECI to ECEF...")
        epoch = time_points[0]
        unit_quat_series: List[float] = []
        for tp, q_eci in zip(time_points, quaternions_eci):
            q_ecef = quaternion_eci_to_ecef(q_eci, tp)
            t_offset = (tp - epoch).total_seconds()
            unit_quat_series.extend([t_offset, q_ecef[0], q_ecef[1], q_ecef[2], q_ecef[3]])

        sensor_half_angle = 1.0 # very small sensor field of view
        print(f"Computing access with orientation (sensor half-angle: {sensor_half_angle}°)...")

        recomputed_windows = compute_access_with_orientation(
            satellite,
            target,
            time_window,
            orientation_epoch=epoch.isoformat().replace("+00:00", "Z"),
            unit_quaternion_series=unit_quat_series,
            sensor_half_angle_deg=sensor_half_angle,
        )

        print(f"Recomputed windows found: {len(recomputed_windows)}")
        for ri, rw in enumerate(recomputed_windows):
            print(f"  Recomputed[{ri}]: {rw.start.isoformat()} to {rw.end.isoformat()}")

        results = []
        for idx, window in enumerate(geometric_windows):
            obs_start, obs_end = actions[idx][0], actions[idx][1]
            
            print(f"\n--- Geometric Window {idx + 1}/{len(geometric_windows)} ---")
            print(f"  Geometric: {window.start.isoformat()} to {window.end.isoformat()}")
            print(f"  Observation: {obs_start.isoformat()} to {obs_end.isoformat()}")

            best_match = None
            best_overlap = 0.0
            for rw in recomputed_windows:
                overlap_start = max(obs_start, rw.start)
                overlap_end = min(obs_end, rw.end)
                overlap = max(0.0, (overlap_end - overlap_start).total_seconds())
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_match = rw

            if best_match is None:
                print(f"  WARNING: No overlapping recomputed window found!")
                results.append({
                    "window_idx": idx,
                    "obs_start": obs_start,
                    "obs_end": obs_end,
                    "status": "NO_OVERLAP",
                })
                continue

            start_diff = (best_match.start - obs_start).total_seconds()
            end_diff = (best_match.end - obs_end).total_seconds()

            print(f"  Best match: {best_match.start.isoformat()} to {best_match.end.isoformat()}")
            print(f"  Start diff: {start_diff:+.2f}s, End diff: {end_diff:+.2f}s")

            threshold_sec = 30.0
            status = "PASS" if abs(start_diff) < threshold_sec and abs(end_diff) < threshold_sec else "FAIL"
            print(f"  Status: {status}")

            results.append({
                "window_idx": idx,
                "obs_start": obs_start,
                "obs_end": obs_end,
                "recomputed_start": best_match.start,
                "recomputed_end": best_match.end,
                "start_diff": start_diff,
                "end_diff": end_diff,
                "status": status,
            })

        print(f"\n{'='*80}")
        print("SUMMARY")
        print(f"{'='*80}")
        
        passed = sum(1 for r in results if r.get("status") == "PASS")
        failed = sum(1 for r in results if r.get("status") == "FAIL")
        no_match = sum(1 for r in results if r.get("status") in ("NO_MATCH", "NO_OVERLAP"))
        
        print(f"PASSED: {passed}, FAILED: {failed}, NO_MATCH: {no_match}")
        
        for r in results:
            if r.get("status") != "PASS":
                print(f"  Window {r['window_idx']}: {r.get('status', 'ERROR')} | "
                      f"start_diff={r.get('start_diff', 'N/A')}, end_diff={r.get('end_diff', 'N/A')}")

        assert failed == 0 and no_match == 0, (
            f"Quaternion round-trip failed: {failed} failed, {no_match} no match"
        )


class TestGroundTrackPrecision:
    """Test 3: Cross-verify ground track (Astrox+Skyfield) against Skyfield native SGP4."""

    @pytest.fixture
    def satellite(self) -> Satellite:
        return Satellite(
            tle_line1=ISS_TLE_LINE1,
            tle_line2=ISS_TLE_LINE2,
            apogee_km=420,
            perigee_km=415,
            period_min=92.9,
            inclination_deg=51.64,
        )

    def test_ground_track_vs_skyfield_native(self, satellite: Satellite):
        """Cross-verify Astrox SGP4 + Skyfield LLA against Skyfield's native SGP4."""
        from skyfield.api import Loader, wgs84
        from engines.astrox.orbital.ephemeris import compute_ground_track, _get_skyfield_ts
        import os
        from pathlib import Path

        base_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        duration_hours = 2
        step_sec = 60.0
        time_window = (base_time, base_time + timedelta(hours=duration_hours))

        # 1. Compute ground track using our engine (Astrox SGP4 -> Skyfield LLA)
        engine_track = compute_ground_track(satellite, time_window, step_sec=step_sec)
        
        # 2. Compute ground track using Skyfield natively
        ts = _get_skyfield_ts()
        from skyfield.sgp4lib import EarthSatellite
        import numpy as np
        skyfield_sat = EarthSatellite(satellite.tle_line1, satellite.tle_line2, name="ISS", ts=ts)

        t_points = ts.from_datetimes([base_time + timedelta(seconds=i * step_sec) for i in range(int(duration_hours * 3600 / step_sec) + 1)])
        
        geocentric = skyfield_sat.at(t_points)
        subpoints = wgs84.subpoint_of(geocentric)
        
        # Skyfield might return scalars if only one point, but here we expect arrays.
        # Ensure they are at least 1D for iteration.
        lats = np.atleast_1d(subpoints.latitude.degrees)
        lons = np.atleast_1d(subpoints.longitude.degrees)
        
        native_track = []
        for lat, lon in zip(lats, lons):
            native_track.append((lat, lon))

        # 3. Compare
        assert len(engine_track) == len(native_track)
        
        max_lat_diff = 0.0
        max_lon_diff = 0.0
        
        for (e_lat, e_lon, e_time), (n_lat, n_lon) in zip(engine_track, native_track):
            # Coordinates can wrap around -180/180
            lat_diff = abs(e_lat - n_lat)
            lon_diff = abs(e_lon - n_lon)
            if lon_diff > 180:
                lon_diff = 360 - lon_diff
            
            max_lat_diff = max(max_lat_diff, lat_diff)
            max_lon_diff = max(max_lon_diff, lon_diff)

        print(f"\n{'='*80}")
        print("GROUND TRACK PRECISION CROSS-VERIFICATION")
        print(f"{'='*80}")
        print(f"Propagator A: Astrox SGP4")
        print(f"Propagator B: Skyfield Native SGP4")
        print(f"Sample Count: {len(engine_track)}")
        print(f"Max Latitude Diff: {max_lat_diff:.8f}°")
        print(f"Max Longitude Diff: {max_lon_diff:.8f}°")
        print(f"{'='*80}")

        # TLE propagation differences are expected between different SGP4 implementations
        # especially if gravity models or epoch handling vary slightly.
        # 0.01 degrees is ~1km on Earth's surface, which is a reasonable upper bound for cross-version SGP4.
        assert max_lat_diff < 0.01, f"Latitude mismatch too high: {max_lat_diff:.8f}°"
        assert max_lon_diff < 0.01, f"Longitude mismatch too high: {max_lon_diff:.8f}°"

        print(f"\n{'='*80}")
        print("GROUND TRACK PRECISION CROSS-VERIFICATION")
        print(f"{'='*80}")
        print(f"Propagator A: Astrox SGP4")
        print(f"Propagator B: Skyfield Native SGP4")
        print(f"Max Latitude Diff: {max_lat_diff:.8f}°")
        print(f"Max Longitude Diff: {max_lon_diff:.8f}°")
        print(f"{'='*80}")

        # TLE propagation differences are expected between different SGP4 implementations
        # especially if gravity models or epoch handling vary slightly.
        # 0.01 degrees is ~1km on Earth's surface, which is a reasonable upper bound for cross-version SGP4.
        assert max_lat_diff < 0.01, f"Latitude mismatch too high: {max_lat_diff:.8f}°"
        assert max_lon_diff < 0.01, f"Longitude mismatch too high: {max_lon_diff:.8f}°"

