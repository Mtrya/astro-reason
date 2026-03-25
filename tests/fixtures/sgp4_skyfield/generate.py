#!/usr/bin/env python3
"""Fixture generator and validator for tests/fixtures/sgp4_skyfield/.

Usage:
    python generate.py generate-all [--overwrite] [--quiet]
    python generate.py generate-case CASE_ID [--overwrite]
    python generate.py validate-all [--strict]
    python generate.py validate-case CASE_ID [--strict]
    python generate.py summary

Options:
    --root PATH     Alternate fixture root directory
    --overwrite     Replace existing JSON outputs
    --strict        Fail on any warning-level irregularity
    --quiet         Suppress per-case progress logs
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from skyfield.api import EarthSatellite, Loader, wgs84

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FIXTURE_ROOT = Path(__file__).parent
CASE_GLOB = "case_[0-9][0-9][0-9][0-9]"
EARTH_RADIUS_M = 6_371_000.0
BOUNDARY_TOL_SEC = 1
JSON_INDENT = 2
HORIZON_START = "2025-07-17T12:00:00Z"
HORIZON_END = "2025-07-18T12:00:00Z"
SAMPLE_STEP_SEC = 1800

GENERATOR_PATH = "tests/fixtures/sgp4_skyfield/generate.py"
SKYFIELD_VERSION = pkg_version("skyfield")
SKYFIELD_EPHEMERIS = "de421.bsp"
SKYFIELD_DATA_DIR = FIXTURE_ROOT / ".skyfield-data"
SKYFIELD_LOADER = Loader(str(SKYFIELD_DATA_DIR))

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class SatelliteInput:
    id: str
    tle_line1: str
    tle_line2: str


@dataclass
class TargetInput:
    id: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    min_elevation_deg: float
    max_slant_range_m: float | None


@dataclass
class CaseInput:
    case_id: str
    case_dir: Path
    satellites: list[SatelliteInput]
    targets: list[TargetInput]


@dataclass
class TimeGrid:
    horizon_start_utc: str
    horizon_end_utc: str
    sample_step_sec: int
    timestamps_utc: list[str]
    offsets_sec: list[int]

    @property
    def sample_count(self) -> int:
        return len(self.timestamps_utc)

    @property
    def datetimes(self) -> list[datetime]:
        return [_parse_utc(ts) for ts in self.timestamps_utc]


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def _parse_utc(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _fmt_utc(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_float(v: Any) -> float:
    return float(v)


def _to_float_list(arr: Any) -> list[float]:
    return [float(x) for x in arr]


def _to_float_list2d(arr: Any) -> list[list[float]]:
    """Convert shape (3, N) ndarray to N-length list of [x, y, z] lists."""
    return [[float(arr[0, i]), float(arr[1, i]), float(arr[2, i])]
            for i in range(arr.shape[1])]


# ---------------------------------------------------------------------------
# Case discovery and loading
# ---------------------------------------------------------------------------


def discover_case_dirs(root: Path) -> list[Path]:
    return sorted(p for p in root.glob(CASE_GLOB) if p.is_dir())


def _require_fields(path: Path, rec: dict, fields: list[str]) -> None:
    for f in fields:
        if f not in rec:
            raise ValueError(
                f"{path}: entry '{rec.get('id', '?')}' missing required field '{f}'"
            )


def load_satellites(path: Path) -> list[SatelliteInput]:
    with open(path) as fh:
        records = yaml.safe_load(fh)
    if not isinstance(records, list):
        raise ValueError(f"{path}: expected top-level YAML list")
    result = []
    for rec in records:
        _require_fields(path, rec, ["id", "tle_line1", "tle_line2"])
        result.append(SatelliteInput(
            id=str(rec["id"]),
            tle_line1=str(rec["tle_line1"]),
            tle_line2=str(rec["tle_line2"]),
        ))
    return result


def load_targets(path: Path) -> list[TargetInput]:
    with open(path) as fh:
        records = yaml.safe_load(fh)
    if not isinstance(records, list):
        raise ValueError(f"{path}: expected top-level YAML list")
    required = ["id", "latitude_deg", "longitude_deg", "altitude_m",
                "min_elevation_deg", "max_slant_range_m"]
    result = []
    for rec in records:
        _require_fields(path, rec, required)
        result.append(TargetInput(
            id=str(rec["id"]),
            latitude_deg=float(rec["latitude_deg"]),
            longitude_deg=float(rec["longitude_deg"]),
            altitude_m=float(rec["altitude_m"]),
            min_elevation_deg=float(rec["min_elevation_deg"]),
            max_slant_range_m=(
                None if rec["max_slant_range_m"] is None
                else float(rec["max_slant_range_m"])
            ),
        ))
    return result


def load_case(case_dir: Path) -> CaseInput:
    return CaseInput(
        case_id=case_dir.name,
        case_dir=case_dir,
        satellites=load_satellites(case_dir / "satellites.yaml"),
        targets=load_targets(case_dir / "targets.yaml"),
    )


def validate_case_inputs(case: CaseInput) -> None:
    sat_ids: set[str] = set()
    for sat in case.satellites:
        if sat.id in sat_ids:
            raise ValueError(
                f"{case.case_id} satellites.yaml: duplicate satellite id '{sat.id}'"
            )
        sat_ids.add(sat.id)
        if not sat.tle_line1.startswith("1 "):
            raise ValueError(
                f"{case.case_id} satellites.yaml: '{sat.id}' tle_line1 must start with '1 '"
            )
        if not sat.tle_line2.startswith("2 "):
            raise ValueError(
                f"{case.case_id} satellites.yaml: '{sat.id}' tle_line2 must start with '2 '"
            )

    tgt_ids: set[str] = set()
    for tgt in case.targets:
        if tgt.id in tgt_ids:
            raise ValueError(
                f"{case.case_id} targets.yaml: duplicate target id '{tgt.id}'"
            )
        tgt_ids.add(tgt.id)
        if not (-90.0 <= tgt.latitude_deg <= 90.0):
            raise ValueError(
                f"{case.case_id} targets.yaml: '{tgt.id}' latitude_deg out of range"
            )
        if not (-180.0 <= tgt.longitude_deg <= 180.0):
            raise ValueError(
                f"{case.case_id} targets.yaml: '{tgt.id}' longitude_deg out of range"
            )
        if not (0.0 <= tgt.min_elevation_deg <= 90.0):
            raise ValueError(
                f"{case.case_id} targets.yaml: '{tgt.id}' min_elevation_deg out of [0, 90]"
            )
        if tgt.max_slant_range_m is not None and tgt.max_slant_range_m <= 0.0:
            raise ValueError(
                f"{case.case_id} targets.yaml: '{tgt.id}' max_slant_range_m must be > 0"
            )

    overlap = sat_ids & tgt_ids
    if overlap:
        raise ValueError(
            f"{case.case_id}: IDs shared between satellites and targets: {overlap}"
        )
    if not case.satellites:
        raise ValueError(f"{case.case_id}: no satellites defined")


# ---------------------------------------------------------------------------
# Time grid
# ---------------------------------------------------------------------------


def build_time_grid(case_id: str) -> TimeGrid:  # noqa: ARG001
    """Return the shared default time grid. All cases use the same grid."""
    start_dt = _parse_utc(HORIZON_START)
    end_dt = _parse_utc(HORIZON_END)
    step = timedelta(seconds=SAMPLE_STEP_SEC)

    timestamps: list[str] = []
    offsets: list[int] = []
    current = start_dt
    while current <= end_dt:
        timestamps.append(_fmt_utc(current))
        offsets.append(int((current - start_dt).total_seconds()))
        current += step

    # Ensure exact horizon end is included if not already the last sample
    if timestamps[-1] != _fmt_utc(end_dt):
        timestamps.append(_fmt_utc(end_dt))
        offsets.append(int((end_dt - start_dt).total_seconds()))

    return TimeGrid(
        horizon_start_utc=HORIZON_START,
        horizon_end_utc=HORIZON_END,
        sample_step_sec=SAMPLE_STEP_SEC,
        timestamps_utc=timestamps,
        offsets_sec=offsets,
    )


# ---------------------------------------------------------------------------
# Orbital state generation
# ---------------------------------------------------------------------------


def compute_orbital_states(case: CaseInput, grid: TimeGrid, ts: Any) -> dict:
    dts = grid.datetimes
    t_batch = ts.from_datetimes(dts)

    satellite_payloads = []
    for sat_input in case.satellites:
        sf_sat = EarthSatellite(sat_input.tle_line1, sat_input.tle_line2,
                                name=sat_input.id, ts=ts)
        geocentric = sf_sat.at(t_batch)

        pos_m = geocentric.position.km * 1000.0     # (3, N) → metres
        vel_mps = geocentric.velocity.km_per_s * 1000.0  # (3, N) → m/s
        subpt = wgs84.subpoint(geocentric)
        lat_deg = subpt.latitude.degrees           # (N,)
        lon_deg = subpt.longitude.degrees          # (N,)
        alt_m = subpt.elevation.km * 1000.0        # (N,) → metres
        dist_m = np.linalg.norm(pos_m, axis=0)    # (N,)

        satellite_payloads.append({
            "id": sat_input.id,
            "position_gcrs_m": _to_float_list2d(pos_m),
            "velocity_gcrs_m_per_s": _to_float_list2d(vel_mps),
            "subpoint_latitude_deg": _to_float_list(lat_deg),
            "subpoint_longitude_deg": _to_float_list(lon_deg),
            "subpoint_altitude_m": _to_float_list(alt_m),
            "geocentric_distance_m": _to_float_list(dist_m),
        })

    return {
        "metadata": {
            "case_id": case.case_id,
            "generator": GENERATOR_PATH,
            "generator_library": "skyfield",
            "generator_library_version": SKYFIELD_VERSION,
            "time_system": "UTC",
            "state_frame": "GCRS",
            "position_unit": "m",
            "velocity_unit": "m_per_s",
            "subpoint_altitude_unit": "m",
            "horizon_start_utc": grid.horizon_start_utc,
            "horizon_end_utc": grid.horizon_end_utc,
            "sample_step_sec": grid.sample_step_sec,
            "sample_count": grid.sample_count,
            "timestamp_inclusion": "sample timestamps are exact sample instants",
            "satellite_ids": [s.id for s in case.satellites],
        },
        "timestamps_utc": grid.timestamps_utc,
        "offsets_sec": grid.offsets_sec,
        "satellites": satellite_payloads,
    }


# ---------------------------------------------------------------------------
# Boundary refinement helpers
# ---------------------------------------------------------------------------


def _refine_start(pred_fn, t_false: datetime, t_true: datetime,
                  tol_sec: int = BOUNDARY_TOL_SEC) -> datetime:
    """Binary search: find first True in (t_false, t_true]."""
    lo, hi = t_false, t_true
    while (hi - lo).total_seconds() > tol_sec:
        mid = lo + (hi - lo) / 2
        if pred_fn(mid):
            hi = mid
        else:
            lo = mid
    return hi


def _refine_end(pred_fn, t_true: datetime, t_false: datetime,
                tol_sec: int = BOUNDARY_TOL_SEC) -> datetime:
    """Binary search: find first False in (t_true, t_false] (exclusive end)."""
    lo, hi = t_true, t_false
    while (hi - lo).total_seconds() > tol_sec:
        mid = lo + (hi - lo) / 2
        if pred_fn(mid):
            lo = mid
        else:
            hi = mid
    return hi


# ---------------------------------------------------------------------------
# Satellite-to-target visibility
# ---------------------------------------------------------------------------


def _build_target_pred(sf_sat: Any, observer: Any, tgt: TargetInput, ts: Any):
    def predicate(dt: datetime) -> bool:
        t = ts.from_datetime(dt)
        topo = (sf_sat - observer).at(t)
        alt, _az, dist = topo.altaz()
        if alt.degrees < tgt.min_elevation_deg:
            return False
        if tgt.max_slant_range_m is not None and dist.km * 1000.0 > tgt.max_slant_range_m:
            return False
        return True
    return predicate


def _windows_from_mask_target(
    mask: np.ndarray,
    dts: list[datetime],
    timestamps_utc: list[str],
    elev: np.ndarray,
    slant: np.ndarray,
    pred_fn,
) -> list[dict]:
    N = len(mask)
    windows = []
    i = 0
    while i < N:
        if not mask[i]:
            i += 1
            continue
        start_idx = i
        while i < N and mask[i]:
            i += 1
        end_idx = i - 1  # last True sample

        start_dt = (dts[0] if start_idx == 0
                    else _refine_start(pred_fn, dts[start_idx - 1], dts[start_idx]))
        end_dt = (dts[-1] if end_idx == N - 1
                  else _refine_end(pred_fn, dts[end_idx], dts[end_idx + 1]))

        dur = (end_dt - start_dt).total_seconds()
        if dur <= 0:
            continue

        win_elev = elev[start_idx:end_idx + 1]
        win_slant = slant[start_idx:end_idx + 1]
        max_elev_rel = int(np.argmax(win_elev))

        windows.append({
            "start_utc": _fmt_utc(start_dt),
            "end_utc": _fmt_utc(end_dt),
            "duration_sec": round(dur),
            "time_of_max_elevation_utc": timestamps_utc[start_idx + max_elev_rel],
            "max_elevation_deg": _to_float(np.max(win_elev)),
            "min_slant_range_m": _to_float(np.min(win_slant)),
            "max_slant_range_m": _to_float(np.max(win_slant)),
        })
    return windows


def compute_satellite_to_target_windows(case: CaseInput, grid: TimeGrid,
                                        ts: Any) -> list[dict]:
    dts = grid.datetimes
    t_batch = ts.from_datetimes(dts)
    records = []

    for sat_input in sorted(case.satellites, key=lambda s: s.id):
        sf_sat = EarthSatellite(sat_input.tle_line1, sat_input.tle_line2,
                                name=sat_input.id, ts=ts)
        for tgt in sorted(case.targets, key=lambda t: t.id):
            observer = wgs84.latlon(tgt.latitude_deg, tgt.longitude_deg,
                                    elevation_m=tgt.altitude_m)
            topo = (sf_sat - observer).at(t_batch)
            alt_arr, _az_arr, dist_arr = topo.altaz()
            elev = alt_arr.degrees              # (N,)
            slant = dist_arr.km * 1000.0        # (N,) → metres

            vis = elev >= tgt.min_elevation_deg
            if tgt.max_slant_range_m is not None:
                vis = vis & (slant <= tgt.max_slant_range_m)

            pred_fn = _build_target_pred(sf_sat, observer, tgt, ts)
            windows = _windows_from_mask_target(vis, dts, grid.timestamps_utc,
                                                elev, slant, pred_fn)
            records.append({
                "satellite_id": sat_input.id,
                "target_id": tgt.id,
                "constraints": {
                    "min_elevation_deg": tgt.min_elevation_deg,
                    "max_slant_range_m": tgt.max_slant_range_m,
                },
                "windows": windows,
            })
    return records


# ---------------------------------------------------------------------------
# Satellite-to-satellite visibility
# ---------------------------------------------------------------------------


def _los_clear_batch(pos_a: np.ndarray, pos_b: np.ndarray) -> np.ndarray:
    """Vectorised LOS clearance. pos_a, pos_b: (3, N) in metres."""
    d = pos_b - pos_a
    t_num = -np.sum(pos_a * d, axis=0)
    t_den = np.sum(d * d, axis=0)
    safe_den = np.where(t_den > 0, t_den, 1.0)
    t_star = np.clip(t_num / safe_den, 0.0, 1.0)
    closest = pos_a + t_star[np.newaxis, :] * d
    return np.linalg.norm(closest, axis=0) >= EARTH_RADIUS_M


def _build_pair_pred(sf_a: Any, sf_b: Any, ts: Any):
    def predicate(dt: datetime) -> bool:
        t = ts.from_datetime(dt)
        p_a = sf_a.at(t).position.km * 1000.0
        p_b = sf_b.at(t).position.km * 1000.0
        d = p_b - p_a
        t_den = float(np.dot(d, d))
        if t_den == 0.0:
            return True
        t_star = float(np.clip(-np.dot(p_a, d) / t_den, 0.0, 1.0))
        closest = p_a + t_star * d
        return float(np.linalg.norm(closest)) >= EARTH_RADIUS_M
    return predicate


def _windows_from_mask_pair(
    mask: np.ndarray,
    dts: list[datetime],
    range_m: np.ndarray,
    pred_fn,
) -> list[dict]:
    N = len(mask)
    windows = []
    i = 0
    while i < N:
        if not mask[i]:
            i += 1
            continue
        start_idx = i
        while i < N and mask[i]:
            i += 1
        end_idx = i - 1

        start_dt = (dts[0] if start_idx == 0
                    else _refine_start(pred_fn, dts[start_idx - 1], dts[start_idx]))
        end_dt = (dts[-1] if end_idx == N - 1
                  else _refine_end(pred_fn, dts[end_idx], dts[end_idx + 1]))

        dur = (end_dt - start_dt).total_seconds()
        if dur <= 0:
            continue

        win_range = range_m[start_idx:end_idx + 1]
        windows.append({
            "start_utc": _fmt_utc(start_dt),
            "end_utc": _fmt_utc(end_dt),
            "duration_sec": round(dur),
            "min_range_m": _to_float(np.min(win_range)),
            "max_range_m": _to_float(np.max(win_range)),
        })
    return windows


def compute_satellite_to_satellite_windows(case: CaseInput, grid: TimeGrid,
                                           ts: Any) -> list[dict]:
    if len(case.satellites) < 2:
        return []

    dts = grid.datetimes
    t_batch = ts.from_datetimes(dts)

    positions: dict[str, np.ndarray] = {}
    sf_sats: dict[str, Any] = {}
    for sat_input in case.satellites:
        sf_sat = EarthSatellite(sat_input.tle_line1, sat_input.tle_line2,
                                name=sat_input.id, ts=ts)
        sf_sats[sat_input.id] = sf_sat
        positions[sat_input.id] = sf_sat.at(t_batch).position.km * 1000.0

    sat_ids_sorted = sorted(s.id for s in case.satellites)
    records = []

    for i, id_a in enumerate(sat_ids_sorted):
        for id_b in sat_ids_sorted[i + 1:]:
            pos_a = positions[id_a]
            pos_b = positions[id_b]

            los_mask = _los_clear_batch(pos_a, pos_b)
            range_m = np.linalg.norm(pos_b - pos_a, axis=0)

            pred_fn = _build_pair_pred(sf_sats[id_a], sf_sats[id_b], ts)
            windows = _windows_from_mask_pair(los_mask, dts, range_m, pred_fn)

            records.append({
                "satellite_id": id_a,
                "other_satellite_id": id_b,
                "constraints": {
                    "line_of_sight_required": True,
                    "max_range_m": None,
                },
                "windows": windows,
            })
    return records


def compute_visibility_windows(case: CaseInput, grid: TimeGrid, ts: Any) -> dict:
    sat_to_tgt = compute_satellite_to_target_windows(case, grid, ts)
    sat_to_sat = compute_satellite_to_satellite_windows(case, grid, ts)
    return {
        "metadata": {
            "case_id": case.case_id,
            "generator": GENERATOR_PATH,
            "generator_library": "skyfield",
            "generator_library_version": SKYFIELD_VERSION,
            "time_system": "UTC",
            "angle_unit": "deg",
            "distance_unit": "m",
            "duration_unit": "sec",
            "horizon_start_utc": grid.horizon_start_utc,
            "horizon_end_utc": grid.horizon_end_utc,
            "sample_step_sec": grid.sample_step_sec,
            "boundary_tolerance_sec": BOUNDARY_TOL_SEC,
            "timestamp_inclusion": "start inclusive, end exclusive",
            "ground_visibility_model": (
                "topocentric line of sight with target-defined minimum elevation"
                " and optional maximum slant range"
            ),
            "inter_satellite_visibility_model": "geometric line of sight above Earth limb",
            "inter_satellite_constraints": {
                "line_of_sight_required": True,
                "max_range_m": None,
            },
            "target_ids": sorted(t.id for t in case.targets),
            "satellite_ids": [s.id for s in case.satellites],
            "earth_occlusion_model": "line segment clearance against spherical Earth",
            "earth_radius_m": EARTH_RADIUS_M,
        },
        "satellite_to_target": sat_to_tgt,
        "satellite_to_satellite": sat_to_sat,
    }


# ---------------------------------------------------------------------------
# Illumination windows
# ---------------------------------------------------------------------------


def _build_illum_pred(sf_sat: Any, ts: Any, eph: Any):
    def predicate(dt: datetime) -> bool:
        t = ts.from_datetime(dt)
        return bool(sf_sat.at(t).is_sunlit(eph))
    return predicate


def _build_illumination_record(
    sat_id: str,
    states: list[str],
    dts: list[datetime],
    pred_fn,
    horizon_start: str,
    horizon_end: str,
) -> dict:
    N = len(states)
    sunlit_windows: list[dict] = []
    eclipse_windows: list[dict] = []
    transitions: list[dict] = []

    win_start_dt = _parse_utc(horizon_start)
    current_state = states[0]

    for i in range(1, N):
        if states[i] == states[i - 1]:
            continue

        if states[i - 1] == "eclipse":
            # eclipse → sunlit: pred_fn (sunlit) flips from False to True
            transition_dt = _refine_start(pred_fn, dts[i - 1], dts[i])
            from_state, to_state = "eclipse", "sunlit"
        else:
            # sunlit → eclipse: pred_fn (sunlit) flips from True to False
            def eclipse_pred(dt: datetime, _p=pred_fn) -> bool:
                return not _p(dt)
            transition_dt = _refine_start(eclipse_pred, dts[i - 1], dts[i])
            from_state, to_state = "sunlit", "eclipse"

        dur = (transition_dt - win_start_dt).total_seconds()
        win = {
            "start_utc": _fmt_utc(win_start_dt),
            "end_utc": _fmt_utc(transition_dt),
            "duration_sec": round(dur),
        }
        if current_state == "sunlit":
            sunlit_windows.append(win)
        else:
            eclipse_windows.append(win)

        transitions.append({
            "timestamp_utc": _fmt_utc(transition_dt),
            "from_state": from_state,
            "to_state": to_state,
        })
        win_start_dt = transition_dt
        current_state = to_state

    # Close final window at horizon end
    horizon_end_dt = _parse_utc(horizon_end)
    dur = (horizon_end_dt - win_start_dt).total_seconds()
    final_win = {
        "start_utc": _fmt_utc(win_start_dt),
        "end_utc": _fmt_utc(horizon_end_dt),
        "duration_sec": round(dur),
    }
    if current_state == "sunlit":
        sunlit_windows.append(final_win)
    else:
        eclipse_windows.append(final_win)

    return {
        "satellite_id": sat_id,
        "initial_state": states[0],
        "final_state": states[-1],
        "sunlit_windows": sunlit_windows,
        "eclipse_windows": eclipse_windows,
        "transitions": transitions,
    }


def compute_illumination_windows(case: CaseInput, grid: TimeGrid, ts: Any,
                                 eph: Any) -> dict:
    dts = grid.datetimes
    t_batch = ts.from_datetimes(dts)

    satellite_records = []
    for sat_input in case.satellites:
        sf_sat = EarthSatellite(sat_input.tle_line1, sat_input.tle_line2,
                                name=sat_input.id, ts=ts)
        is_sunlit = sf_sat.at(t_batch).is_sunlit(eph)

        states: list[str] = []
        for i in range(grid.sample_count):
            states.append("sunlit" if bool(is_sunlit[i]) else "eclipse")

        pred_fn = _build_illum_pred(sf_sat, ts, eph)
        record = _build_illumination_record(
            sat_input.id, states, dts, pred_fn,
            grid.horizon_start_utc, grid.horizon_end_utc,
        )
        satellite_records.append(record)

    return {
        "metadata": {
            "case_id": case.case_id,
            "generator": GENERATOR_PATH,
            "generator_library": "skyfield",
            "generator_library_version": SKYFIELD_VERSION,
            "time_system": "UTC",
            "duration_unit": "sec",
            "distance_unit": "m",
            "illumination_source": "skyfield",
            "illumination_model": (
                f"skyfield ICRF.is_sunlit with JPL {SKYFIELD_EPHEMERIS} ephemeris"
            ),
            "horizon_start_utc": grid.horizon_start_utc,
            "horizon_end_utc": grid.horizon_end_utc,
            "sample_step_sec": grid.sample_step_sec,
            "boundary_tolerance_sec": BOUNDARY_TOL_SEC,
            "timestamp_inclusion": "start inclusive, end exclusive",
            "satellite_ids": [s.id for s in case.satellites],
        },
        "satellites": satellite_records,
    }


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------


def write_json(path: Path, payload: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=JSON_INDENT, ensure_ascii=False)
        fh.write("\n")


# ---------------------------------------------------------------------------
# Output validation
# ---------------------------------------------------------------------------


def validate_orbital_states(payload: dict, case: CaseInput) -> None:
    meta = payload["metadata"]
    n = meta["sample_count"]
    ts_list = payload["timestamps_utc"]
    off_list = payload["offsets_sec"]
    if len(ts_list) != n:
        raise AssertionError(
            f"{case.case_id} orbital_states: sample_count={n} but timestamps length={len(ts_list)}"
        )
    if len(off_list) != n:
        raise AssertionError(f"{case.case_id} orbital_states: offsets length mismatch")
    if off_list[0] != 0:
        raise AssertionError(f"{case.case_id} orbital_states: first offset must be 0")
    for i in range(1, n):
        if ts_list[i] <= ts_list[i - 1]:
            raise AssertionError(
                f"{case.case_id} orbital_states: timestamps not strictly ascending at {i}"
            )
    sat_ids_yaml = {s.id for s in case.satellites}
    for sat_rec in payload["satellites"]:
        sid = sat_rec["id"]
        if sid not in sat_ids_yaml:
            raise AssertionError(
                f"{case.case_id} orbital_states: unknown satellite id '{sid}'"
            )
        for key in ["position_gcrs_m", "velocity_gcrs_m_per_s"]:
            arr = sat_rec[key]
            if len(arr) != n:
                raise AssertionError(
                    f"{case.case_id} orbital_states: {key} length mismatch for {sid}"
                )
            for row in arr:
                if len(row) != 3:
                    raise AssertionError(
                        f"{case.case_id} orbital_states: {key} row not length 3"
                    )
                for v in row:
                    if not math.isfinite(v):
                        raise AssertionError(
                            f"{case.case_id} orbital_states: non-finite in {key} for {sid}"
                        )
        for key in ["subpoint_latitude_deg", "subpoint_longitude_deg",
                    "subpoint_altitude_m", "geocentric_distance_m"]:
            arr = sat_rec[key]
            if len(arr) != n:
                raise AssertionError(
                    f"{case.case_id} orbital_states: {key} length mismatch for {sid}"
                )
            for v in arr:
                if not math.isfinite(v):
                    raise AssertionError(
                        f"{case.case_id} orbital_states: non-finite in {key} for {sid}"
                    )


def validate_visibility(payload: dict, case: CaseInput) -> None:
    meta = payload["metadata"]
    h_start = meta["horizon_start_utc"]
    h_end = meta["horizon_end_utc"]
    sat_ids = {s.id for s in case.satellites}
    tgt_ids = {t.id for t in case.targets}

    for rec in payload["satellite_to_target"]:
        sid, tid = rec["satellite_id"], rec["target_id"]
        if sid not in sat_ids:
            raise AssertionError(
                f"{case.case_id}: unknown satellite '{sid}' in satellite_to_target"
            )
        if tid not in tgt_ids:
            raise AssertionError(
                f"{case.case_id}: unknown target '{tid}' in satellite_to_target"
            )
        prev_end = None
        for win in rec["windows"]:
            if win["start_utc"] < h_start or win["end_utc"] > h_end:
                raise AssertionError(
                    f"{case.case_id}: window outside horizon for {sid}/{tid}"
                )
            if win["duration_sec"] <= 0:
                raise AssertionError(
                    f"{case.case_id}: non-positive window duration for {sid}/{tid}"
                )
            if win["end_utc"] <= win["start_utc"]:
                raise AssertionError(
                    f"{case.case_id}: window end <= start for {sid}/{tid}"
                )
            if win["max_elevation_deg"] < rec["constraints"]["min_elevation_deg"]:
                raise AssertionError(
                    f"{case.case_id}: max_elevation < min_elevation_deg for {sid}/{tid}"
                )
            if prev_end is not None and win["start_utc"] < prev_end:
                raise AssertionError(
                    f"{case.case_id}: overlapping windows for {sid}/{tid}"
                )
            prev_end = win["end_utc"]

    seen_pairs: set[tuple[str, str]] = set()
    for rec in payload["satellite_to_satellite"]:
        sid, oid = rec["satellite_id"], rec["other_satellite_id"]
        if sid not in sat_ids:
            raise AssertionError(
                f"{case.case_id}: unknown satellite '{sid}' in satellite_to_satellite"
            )
        if oid not in sat_ids:
            raise AssertionError(
                f"{case.case_id}: unknown satellite '{oid}' in satellite_to_satellite"
            )
        if sid >= oid:
            raise AssertionError(
                f"{case.case_id}: pair not in canonical order: ({sid}, {oid})"
            )
        pair = (sid, oid)
        if pair in seen_pairs:
            raise AssertionError(f"{case.case_id}: duplicate pair {pair}")
        seen_pairs.add(pair)
        prev_end = None
        for win in rec["windows"]:
            if win["duration_sec"] <= 0:
                raise AssertionError(
                    f"{case.case_id}: non-positive ISL window duration for {pair}"
                )
            if prev_end is not None and win["start_utc"] < prev_end:
                raise AssertionError(
                    f"{case.case_id}: overlapping ISL windows for {pair}"
                )
            prev_end = win["end_utc"]


def validate_illumination(payload: dict, case: CaseInput) -> None:
    sat_ids = {s.id for s in case.satellites}
    for rec in payload["satellites"]:
        sid = rec["satellite_id"]
        if sid not in sat_ids:
            raise AssertionError(
                f"{case.case_id}: unknown satellite '{sid}' in illumination"
            )
        for win_list in [rec["sunlit_windows"], rec["eclipse_windows"]]:
            prev_end = None
            for win in win_list:
                if win["duration_sec"] <= 0:
                    raise AssertionError(
                        f"{case.case_id}: non-positive illumination window for {sid}"
                    )
                if prev_end is not None and win["start_utc"] < prev_end:
                    raise AssertionError(
                        f"{case.case_id}: overlapping illumination windows for {sid}"
                    )
                prev_end = win["end_utc"]
        transitions = rec["transitions"]
        for i in range(1, len(transitions)):
            if transitions[i]["from_state"] != transitions[i - 1]["to_state"]:
                raise AssertionError(
                    f"{case.case_id}: non-alternating transitions for {sid}"
                )
            if transitions[i]["timestamp_utc"] <= transitions[i - 1]["timestamp_utc"]:
                raise AssertionError(
                    f"{case.case_id}: transitions not strictly sorted for {sid}"
                )


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def _print_summary(case_id: str, orbital: dict, visibility: dict,
                   illumination: dict) -> None:
    n_sats = len(orbital["satellites"])
    n_tgts = len(visibility["metadata"]["target_ids"])
    n_samples = orbital["metadata"]["sample_count"]
    n_st = sum(len(r["windows"]) for r in visibility["satellite_to_target"])
    n_ss = sum(len(r["windows"]) for r in visibility["satellite_to_satellite"])
    n_tr = sum(len(r["transitions"]) for r in illumination["satellites"])
    print(f"{case_id}: {n_sats} satellites, {n_tgts} targets, {n_samples} samples, "
          f"{n_st} sat-target windows, {n_ss} sat-sat windows, "
          f"{n_tr} illumination transitions")


def generate_case(case: CaseInput, grid: TimeGrid, ts: Any,
                  eph: Any,
                  overwrite: bool = False, quiet: bool = False) -> None:
    for fname in ["orbital_states.json", "visibility_windows.json",
                  "illumination_windows.json"]:
        out_path = case.case_dir / fname
        if out_path.exists() and not overwrite:
            raise FileExistsError(
                f"{out_path} already exists. Use --overwrite to replace."
            )

    if not quiet:
        print(f"[{case.case_id}] generating orbital states ...", flush=True)
    orbital = compute_orbital_states(case, grid, ts)
    write_json(case.case_dir / "orbital_states.json", orbital)
    validate_orbital_states(orbital, case)

    if not quiet:
        print(f"[{case.case_id}] generating visibility windows ...", flush=True)
    visibility = compute_visibility_windows(case, grid, ts)
    write_json(case.case_dir / "visibility_windows.json", visibility)
    validate_visibility(visibility, case)

    if not quiet:
        print(f"[{case.case_id}] generating illumination windows ...", flush=True)
    illumination = compute_illumination_windows(case, grid, ts, eph)
    write_json(case.case_dir / "illumination_windows.json", illumination)
    validate_illumination(illumination, case)

    if not quiet:
        _print_summary(case.case_id, orbital, visibility, illumination)


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


def _validate_case_outputs(case_dir: Path, case: CaseInput) -> None:
    for fname, validator in [
        ("orbital_states.json", validate_orbital_states),
        ("visibility_windows.json", validate_visibility),
        ("illumination_windows.json", validate_illumination),
    ]:
        path = case_dir / fname
        if not path.exists():
            raise FileNotFoundError(f"{path} does not exist")
        with open(path) as fh:
            payload = json.load(fh)
        validator(payload, case)


def cmd_generate_all(root: Path, overwrite: bool, quiet: bool) -> int:
    ts = SKYFIELD_LOADER.timescale()
    eph = SKYFIELD_LOADER(SKYFIELD_EPHEMERIS)
    cases = discover_case_dirs(root)
    if not cases:
        print(f"No case directories found under {root}", file=sys.stderr)
        return 1
    errors = []
    for case_dir in cases:
        try:
            case = load_case(case_dir)
            validate_case_inputs(case)
            grid = build_time_grid(case.case_id)
            generate_case(case, grid, ts, eph, overwrite=overwrite, quiet=quiet)
        except Exception as exc:
            print(f"ERROR [{case_dir.name}]: {exc}", file=sys.stderr)
            errors.append(case_dir.name)
    if errors:
        print(f"\nFailed: {errors}", file=sys.stderr)
        return 1
    return 0


def cmd_generate_case(root: Path, case_id: str, overwrite: bool) -> int:
    ts = SKYFIELD_LOADER.timescale()
    eph = SKYFIELD_LOADER(SKYFIELD_EPHEMERIS)
    case_dir = root / case_id
    if not case_dir.is_dir():
        print(f"ERROR: case directory not found: {case_dir}", file=sys.stderr)
        return 1
    try:
        case = load_case(case_dir)
        validate_case_inputs(case)
        grid = build_time_grid(case.case_id)
        generate_case(case, grid, ts, eph, overwrite=overwrite, quiet=False)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_validate_all(root: Path) -> int:
    errors = []
    for case_dir in discover_case_dirs(root):
        try:
            case = load_case(case_dir)
            validate_case_inputs(case)
            _validate_case_outputs(case_dir, case)
            print(f"[{case_dir.name}] OK")
        except Exception as exc:
            print(f"ERROR [{case_dir.name}]: {exc}", file=sys.stderr)
            errors.append(case_dir.name)
    if errors:
        print(f"\nFailed: {errors}", file=sys.stderr)
        return 1
    return 0


def cmd_validate_case(root: Path, case_id: str) -> int:
    case_dir = root / case_id
    if not case_dir.is_dir():
        print(f"ERROR: case directory not found: {case_dir}", file=sys.stderr)
        return 1
    try:
        case = load_case(case_dir)
        validate_case_inputs(case)
        _validate_case_outputs(case_dir, case)
        print(f"[{case_id}] OK")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_summary(root: Path) -> int:
    for case_dir in discover_case_dirs(root):
        op = case_dir / "orbital_states.json"
        vp = case_dir / "visibility_windows.json"
        ip = case_dir / "illumination_windows.json"
        if not (op.exists() and vp.exists() and ip.exists()):
            print(f"{case_dir.name}: [not yet generated]")
            continue
        try:
            with open(op) as fh:
                orbital = json.load(fh)
            with open(vp) as fh:
                visibility = json.load(fh)
            with open(ip) as fh:
                illumination = json.load(fh)
            _print_summary(case_dir.name, orbital, visibility, illumination)
        except Exception as exc:
            print(f"{case_dir.name}: ERROR: {exc}", file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SGP4 Skyfield fixture generator and validator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--root", type=Path, default=FIXTURE_ROOT,
                        help="Fixture root directory (default: script directory)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("generate-all", help="Generate JSON outputs for all cases")
    p.add_argument("--overwrite", action="store_true",
                   help="Replace existing JSON outputs")
    p.add_argument("--quiet", action="store_true", help="Suppress progress logs")

    p = sub.add_parser("generate-case", help="Generate JSON outputs for one case")
    p.add_argument("case_id", help="Case directory name, e.g. case_0002")
    p.add_argument("--overwrite", action="store_true")

    p = sub.add_parser("validate-all", help="Validate inputs and all JSON outputs")
    p.add_argument("--strict", action="store_true")

    p = sub.add_parser("validate-case", help="Validate inputs and JSON outputs for one case")
    p.add_argument("case_id")
    p.add_argument("--strict", action="store_true")

    sub.add_parser("summary", help="Print one-line summary per case")

    args = parser.parse_args()
    root: Path = args.root

    if args.command == "generate-all":
        return cmd_generate_all(root, args.overwrite, args.quiet)
    if args.command == "generate-case":
        return cmd_generate_case(root, args.case_id, args.overwrite)
    if args.command == "validate-all":
        return cmd_validate_all(root)
    if args.command == "validate-case":
        return cmd_validate_case(root, args.case_id)
    if args.command == "summary":
        return cmd_summary(root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
