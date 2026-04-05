"""Canonical v3 stereo_imaging dataset generation (Phase 1.B)."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import yaml
from rasterio.windows import Window

from . import sources as sources_module
from .normalize import (
    load_celestrak_csv,
    load_world_cities,
    query_worldcover_class,
    worldcover_tile_filename,
)

# -----------------------------------------------------------------------------
# Canonical release parameters
# -----------------------------------------------------------------------------

CANONICAL_SEED = 20260406
DEFAULT_HORIZON_DURATION_S = 172800  # 48 h

# Canonical release: fixed number of cases; per-case satellite set and target count are sampled from the seed.
NUM_CANONICAL_CASES = 5
MIN_SATELLITES_PER_CASE = 2
MAX_SATELLITES_PER_CASE = 4
MIN_TARGETS_PER_CASE = 24
MAX_TARGETS_PER_CASE = 48

# Curated optical Earth-observation satellites present in CelesTrak earth-resources.
# v3 public fields only; NORAD IDs must exist in normalized CelesTrak CSV.
SATELLITE_CATALOG: dict[int, dict[str, Any]] = {
    38755: {
        "id": "sat_spot_6",
        "pixel_ifov_deg": 0.00012,
        "cross_track_pixels": 12000,
        "max_off_nadir_deg": 30.0,
        "max_slew_velocity_deg_per_s": 2.35,
        "max_slew_acceleration_deg_per_s2": 1.15,
        "settling_time_s": 1.35,
        "min_obs_duration_s": 2.0,
        "max_obs_duration_s": 60.0,
    },
    40053: {
        "id": "sat_spot_7",
        "pixel_ifov_deg": 0.00012,
        "cross_track_pixels": 12000,
        "max_off_nadir_deg": 30.0,
        "max_slew_velocity_deg_per_s": 2.35,
        "max_slew_acceleration_deg_per_s2": 1.15,
        "settling_time_s": 1.35,
        "min_obs_duration_s": 2.0,
        "max_obs_duration_s": 60.0,
    },
    40013: {
        "id": "sat_deimos_2",
        "pixel_ifov_deg": 0.00022,
        "cross_track_pixels": 12000,
        "max_off_nadir_deg": 30.0,
        "max_slew_velocity_deg_per_s": 1.95,
        "max_slew_acceleration_deg_per_s2": 0.95,
        "settling_time_s": 1.9,
        "min_obs_duration_s": 2.0,
        "max_obs_duration_s": 60.0,
    },
    40118: {
        "id": "sat_gaofen_2",
        "pixel_ifov_deg": 0.000065,
        "cross_track_pixels": 12000,
        "max_off_nadir_deg": 25.0,
        "max_slew_velocity_deg_per_s": 0.55,
        "max_slew_acceleration_deg_per_s2": 0.065,
        "settling_time_s": 3.0,
        "min_obs_duration_s": 2.0,
        "max_obs_duration_s": 60.0,
    },
    41556: {
        "id": "sat_ziyuan_3_02",
        "pixel_ifov_deg": 0.00017,
        "cross_track_pixels": 6000,
        "max_off_nadir_deg": 25.0,
        "max_slew_velocity_deg_per_s": 0.78,
        "max_slew_acceleration_deg_per_s2": 0.08,
        "settling_time_s": 2.5,
        "min_obs_duration_s": 2.0,
        "max_obs_duration_s": 60.0,
    },
    38012: {
        "id": "sat_pleiades_1a",
        "pixel_ifov_deg": 0.00004,
        "cross_track_pixels": 20000,
        "max_off_nadir_deg": 30.0,
        "max_slew_velocity_deg_per_s": 1.95,
        "max_slew_acceleration_deg_per_s2": 0.95,
        "settling_time_s": 1.9,
        "min_obs_duration_s": 2.0,
        "max_obs_duration_s": 60.0,
    },
}

WORLDCOVER_VEGETATED = {10, 20, 30, 40}
# ESA v200: 50 built-up, 60 bare/sparse, 70 snow/ice, 80 permanent water, 90 herbaceous wetland, 95 mangroves, 100 moss/lichen
# 80 is ocean/inland water — never treat as land targets; excluded from "open" land.
WORLDCOVER_PERMANENT_WATER = 80
WORLDCOVER_OPEN_LAND = {60, 70, 90, 95, 100}
RUGGED_STD_THRESHOLD_M = 200.0

# ETOPO surface elevation: ocean cells are bathymetry (negative below sea level); land is
# typically > 0. Without a land mask, random lat/lon hits open ocean and yields ~-5 km refs.
LAND_MIN_ELEVATION_REF_M = 0.0


class _EtopoReader:
    """Single open ETOPO dataset with windowed reads (avoids full-raster loads per query)."""

    def __init__(self, path: Path):
        self._path = path
        self._ds = rasterio.open(path)
        self._nodata = self._ds.nodata

    def close(self) -> None:
        self._ds.close()

    def __enter__(self) -> _EtopoReader:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def elevation_m(self, lat: float, lon: float) -> float:
        row, col = self._ds.index(lon, lat)
        ir, ic = int(row), int(col)
        win = Window(ic, ir, 1, 1)
        val = float(self._ds.read(1, window=win)[0, 0])
        if self._nodata is not None and val == self._nodata:
            return float("nan")
        return val

    def neighborhood_std_m(self, lat: float, lon: float, half: int = 2) -> float:
        row, col = self._ds.index(lon, lat)
        ir, ic = int(row), int(col)
        h, wdim = self._ds.height, self._ds.width
        r0 = max(0, ir - half)
        r1 = min(h, ir + half + 1)
        c0 = max(0, ic - half)
        c1 = min(wdim, ic + half + 1)
        win = Window(c0, r0, c1 - c0, r1 - r0)
        patch = self._ds.read(1, window=win).astype(np.float64)
        if self._nodata is not None:
            patch = np.where(patch == self._nodata, np.nan, patch)
        if np.all(np.isnan(patch)):
            return 0.0
        return float(np.nanstd(patch))


def _sample_case_satellites_and_target_count(
    rng: random.Random,
    pool_norads: list[int],
) -> tuple[list[int], int]:
    """Deterministic random: satellite count in [2,4], target count in [24,48], distinct NORAD ids."""
    n_sat = rng.randint(MIN_SATELLITES_PER_CASE, MAX_SATELLITES_PER_CASE)
    n_targ = rng.randint(MIN_TARGETS_PER_CASE, MAX_TARGETS_PER_CASE)
    n_sat = min(n_sat, len(pool_norads))
    pool = pool_norads.copy()
    rng.shuffle(pool)
    norad_ids = pool[:n_sat]
    return norad_ids, n_targ


def _inclination_deg_from_tle_line2(line2: str) -> float:
    if len(line2) < 16:
        return 98.0
    return float(line2[8:16].strip())


def _parse_iso_utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _horizon_for_case(seed: int, case_index: int) -> tuple[str, str]:
    """Deterministic mission horizon per case (48 h)."""
    base = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    offset_hours = (seed % 1000) + case_index * 6
    start = base + timedelta(hours=offset_hours)
    end = start + timedelta(seconds=DEFAULT_HORIZON_DURATION_S)
    return _utc_iso(start), _utc_iso(end)


def _etopo_is_land(elevation_m: float) -> bool:
    """True if ETOPO sample is land (not deep/shallow ocean bathymetry)."""
    if elevation_m != elevation_m:  # NaN
        return False
    return elevation_m > LAND_MIN_ELEVATION_REF_M


def _location_is_land_target(
    lat: float,
    lon: float,
    etopo: _EtopoReader,
    wc_dir: Path,
) -> bool:
    """Exclude ocean ETOPO cells and WorldCover permanent water (class 80)."""
    el = float(etopo.elevation_m(lat, lon))
    if not _etopo_is_land(el):
        return False
    wc = _worldcover_class_if_available(wc_dir, lat, lon)
    if wc is not None and wc == WORLDCOVER_PERMANENT_WATER:
        return False
    return True


def _passes_feasibility(
    lat: float,
    lon: float,
    inclinations_deg: list[float],
) -> bool:
    """Lightweight conservative filter: latitude within inclination band and non-polar."""
    if abs(lat) > 85.0:
        return False
    max_inc = max(inclinations_deg) if inclinations_deg else 98.0
    margin = 3.0
    if abs(lat) > max_inc - margin:
        return False
    return True


def _mission_template(horizon_start: str, horizon_end: str) -> dict[str, Any]:
    return {
        "mission": {
            "horizon_start": horizon_start,
            "horizon_end": horizon_end,
            "allow_cross_satellite_stereo": False,
            "allow_cross_date_stereo": False,
            "validity_thresholds": {
                "min_overlap_fraction": 0.80,
                "min_convergence_deg": 5.0,
                "max_convergence_deg": 45.0,
                "max_pixel_scale_ratio": 1.5,
                "min_solar_elevation_deg": 10.0,
                "near_nadir_anchor_max_off_nadir_deg": 10.0,
            },
            "quality_model": {
                "pair_weights": {
                    "geometry": 0.50,
                    "overlap": 0.35,
                    "resolution": 0.15,
                },
                "tri_stereo_bonus_by_scene": {
                    "urban_structured": 0.12,
                    "rugged": 0.10,
                    "vegetated": 0.08,
                    "open": 0.05,
                },
            },
        }
    }


def _build_satellite_dict(
    celestrak_by_norad: dict[int, dict[str, Any]],
    norad_id: int,
) -> dict[str, Any]:
    cat = SATELLITE_CATALOG[norad_id]
    row = celestrak_by_norad[norad_id]
    return {
        "id": cat["id"],
        "norad_catalog_id": norad_id,
        "tle_line1": row["tle_line1"],
        "tle_line2": row["tle_line2"],
        "pixel_ifov_deg": cat["pixel_ifov_deg"],
        "cross_track_pixels": cat["cross_track_pixels"],
        "max_off_nadir_deg": cat["max_off_nadir_deg"],
        "max_slew_velocity_deg_per_s": cat["max_slew_velocity_deg_per_s"],
        "max_slew_acceleration_deg_per_s2": cat["max_slew_acceleration_deg_per_s2"],
        "settling_time_s": cat["settling_time_s"],
        "min_obs_duration_s": cat["min_obs_duration_s"],
        "max_obs_duration_s": cat["max_obs_duration_s"],
    }


def _worldcover_class_if_available(wc_dir: Path, lat: float, lon: float) -> int | None:
    fname = worldcover_tile_filename(lat, lon)
    if not (wc_dir / fname).is_file():
        return None
    try:
        return query_worldcover_class(wc_dir, lat, lon)
    except (OSError, ValueError):
        return None


def _classify_non_urban(
    lat: float,
    lon: float,
    etopo: _EtopoReader,
    wc_dir: Path,
) -> tuple[str, float]:
    """Assign scene_type and elevation_ref_m for a non-urban candidate."""
    std_m = etopo.neighborhood_std_m(lat, lon)
    el = float(etopo.elevation_m(lat, lon))
    wc = _worldcover_class_if_available(wc_dir, lat, lon)

    if std_m >= RUGGED_STD_THRESHOLD_M:
        return "rugged", el

    if wc is not None:
        if wc in WORLDCOVER_VEGETATED:
            return "vegetated", el
        if wc in WORLDCOVER_OPEN_LAND:
            return "open", el

    # Heuristic when tile missing or class ambiguous
    alat = abs(lat)
    if 35.0 <= alat <= 55.0 and std_m < 80.0:
        return "vegetated", el
    if std_m < 50.0 and alat < 40.0:
        return "open", el
    return "open", el


@dataclass
class BuiltCase:
    case_id: str
    num_satellites: int
    num_targets: int
    norad_catalog_ids: list[int]
    satellite_ids: list[str]
    target_ids: list[str]
    horizon_start: str
    horizon_end: str


def _sample_urban_targets(
    cities: list[dict[str, Any]],
    rng: random.Random,
    count: int,
    used: set[tuple[float, float]],
    inclinations_deg: list[float],
    etopo: _EtopoReader,
    wc_dir: Path,
) -> list[dict[str, Any]]:
    """Sample cities with population floor and geographic spread."""
    pool = [c for c in cities if c.get("population", 0) >= 100_000]
    rng.shuffle(pool)
    out: list[dict[str, Any]] = []
    idx = 0
    while len(out) < count and idx < len(pool) * 3:
        c = pool[idx % len(pool)]
        idx += 1
        lat = float(c["latitude_deg"])
        lon = float(c["longitude_deg"])
        key = (round(lat, 2), round(lon, 2))
        if key in used:
            continue
        if not _passes_feasibility(lat, lon, inclinations_deg):
            continue
        if not _location_is_land_target(lat, lon, etopo, wc_dir):
            continue
        used.add(key)
        slug = (
            str(c["name"])
            .lower()
            .replace(" ", "_")
            .replace("`", "")
            .replace("'", "")
        )[:24]
        cid = f"urban_{slug}_{len(out):02d}"
        out.append(
            {
                "id": cid,
                "latitude_deg": lat,
                "longitude_deg": lon,
                "scene_type": "urban_structured",
            }
        )
    return out


def _split_three_way(n: int) -> tuple[int, int, int]:
    """Split n into three nonnegative integers (vegetated, rugged, open)."""
    a = n // 3
    r = n % 3
    return (
        a + (1 if r > 0 else 0),
        a + (1 if r > 1 else 0),
        a + (1 if r > 2 else 0),
    )


def _sample_non_urban_targets(
    rng: random.Random,
    count: int,
    etopo: _EtopoReader,
    wc_dir: Path,
    used: set[tuple[float, float]],
    inclinations_deg: list[float],
) -> list[dict[str, Any]]:
    """Rejection sample lat/lon until each scene bucket is filled."""
    n_veg, n_rug, n_open = _split_three_way(count)
    need: dict[str, int] = {
        "vegetated": n_veg,
        "rugged": n_rug,
        "open": n_open,
    }
    targets: list[dict[str, Any]] = []
    attempts = 0
    max_attempts = 80000

    while sum(need.values()) > 0 and attempts < max_attempts:
        attempts += 1
        lat = rng.uniform(-60.0, 60.0)
        lon = rng.uniform(-180.0, 180.0)
        key = (round(lat, 2), round(lon, 2))
        if key in used:
            continue
        if not _passes_feasibility(lat, lon, inclinations_deg):
            continue
        if not _location_is_land_target(lat, lon, etopo, wc_dir):
            continue

        scene, _el = _classify_non_urban(lat, lon, etopo, wc_dir)
        if need.get(scene, 0) <= 0:
            continue

        used.add(key)
        need[scene] -= 1
        tid = f"{scene}_{len(targets):03d}"
        targets.append(
            {
                "id": tid,
                "latitude_deg": lat,
                "longitude_deg": lon,
                "scene_type": scene,
            }
        )

    # Relax: assign remaining quota to whichever scene still classifies
    while sum(need.values()) > 0:
        attempts += 1
        if attempts > max_attempts + 50000:
            break
        lat = rng.uniform(-55.0, 55.0)
        lon = rng.uniform(-180.0, 180.0)
        key = (round(lat, 2), round(lon, 2))
        if key in used:
            continue
        if not _passes_feasibility(lat, lon, inclinations_deg):
            continue
        if not _location_is_land_target(lat, lon, etopo, wc_dir):
            continue
        scene, _el = _classify_non_urban(lat, lon, etopo, wc_dir)
        if need.get(scene, 0) <= 0:
            # Force into a bucket that still needs fills
            for k in ("open", "vegetated", "rugged"):
                if need.get(k, 0) > 0:
                    scene = k
                    break
            else:
                continue
        used.add(key)
        need[scene] -= 1
        tid = f"{scene}_{len(targets):03d}"
        targets.append(
            {
                "id": tid,
                "latitude_deg": lat,
                "longitude_deg": lon,
                "scene_type": scene,
            }
        )

    if sum(need.values()) > 0:
        raise RuntimeError(
            f"Non-urban sampling incomplete after {attempts} attempts; remaining={need}"
        )

    return targets


def _finalize_targets(
    raw: list[dict[str, Any]],
    etopo: _EtopoReader,
    wc_dir: Path,
    rng: random.Random,
) -> list[dict[str, Any]]:
    """Add aoi_radius_m and elevation_ref_m (land-only; ocean/water grids rejected)."""
    out: list[dict[str, Any]] = []
    for t in raw:
        lat = t["latitude_deg"]
        lon = t["longitude_deg"]
        if not _location_is_land_target(lat, lon, etopo, wc_dir):
            raise ValueError(
                f"Non-land target slipped through sampling: ({lat}, {lon}). "
                "Ocean and WorldCover permanent-water cells must be excluded."
            )
        el = float(etopo.elevation_m(lat, lon))
        aoi = round(rng.uniform(2500.0, 7500.0), 1)
        out.append(
            {
                "id": t["id"],
                "latitude_deg": lat,
                "longitude_deg": lon,
                "aoi_radius_m": aoi,
                "elevation_ref_m": el,
                "scene_type": t["scene_type"],
            }
        )
    return out


def _write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(
        data,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )
    path.write_text(text, encoding="utf-8")


def build_example_solution(
    cases: list[BuiltCase],
    horizon_starts: dict[str, str],
) -> dict[str, Any]:
    """Minimal v3 actions for verifier smoke tests (not a quality baseline)."""
    sol: dict[str, Any] = {}
    for bc in cases:
        start = horizon_starts[bc.case_id]
        t0 = _parse_iso_utc(start)
        # Three short observations: two on first satellite, one on second if present
        sat0 = bc.satellite_ids[0]
        sat1 = bc.satellite_ids[1] if len(bc.satellite_ids) > 1 else sat0
        tgt0 = bc.target_ids[0]
        tgt1 = bc.target_ids[1] if len(bc.target_ids) > 1 else tgt0
        actions = [
            {
                "type": "observation",
                "satellite_id": sat0,
                "target_id": tgt0,
                "start_time": _utc_iso(t0 + timedelta(seconds=3600)),
                "end_time": _utc_iso(t0 + timedelta(seconds=3615)),
                "off_nadir_along_deg": 0.0,
                "off_nadir_across_deg": 5.0,
            },
            {
                "type": "observation",
                "satellite_id": sat0,
                "target_id": tgt1,
                "start_time": _utc_iso(t0 + timedelta(seconds=7200)),
                "end_time": _utc_iso(t0 + timedelta(seconds=7220)),
                "off_nadir_along_deg": 2.0,
                "off_nadir_across_deg": 4.0,
            },
            {
                "type": "observation",
                "satellite_id": sat1,
                "target_id": tgt0,
                "start_time": _utc_iso(t0 + timedelta(seconds=10800)),
                "end_time": _utc_iso(t0 + timedelta(seconds=10818)),
                "off_nadir_along_deg": -1.0,
                "off_nadir_across_deg": 6.0,
            },
        ]
        sol[bc.case_id] = {"actions": actions}
    return sol


def generate_dataset(
    source_dir: Path,
    output_dir: Path,
    seed: int = CANONICAL_SEED,
    *,
    git_revision: str | None = None,
) -> dict[str, Any]:
    """
    Build canonical v3 cases under output_dir/dataset/cases/ plus index.json and example_solution.json.

    Expects normalized source_data under source_dir (CelesTrak CSV, ETOPO GeoTIFF, world cities CSV,
    optional WorldCover tiles).
    """
    cele_path = source_dir / "celestrak" / sources_module.CELESTRAK_CSV_NAME
    cities_path = source_dir / "world_cities" / sources_module.WORLD_CITIES_FILENAME
    etopo_path = source_dir / "etopo" / sources_module.ETOPO_LOCAL_FILENAME
    wc_dir = source_dir / "worldcover"
    prov_path = source_dir / "provenance.json"

    if not cele_path.is_file():
        raise FileNotFoundError(f"Missing CelesTrak CSV: {cele_path}")
    if not cities_path.is_file():
        raise FileNotFoundError(f"Missing world cities CSV: {cities_path}")
    if not etopo_path.is_file():
        raise FileNotFoundError(f"Missing ETOPO GeoTIFF: {etopo_path}")

    cele_rows = load_celestrak_csv(cele_path)
    celestrak_by_norad: dict[int, dict[str, Any]] = {}
    for row in cele_rows:
        nid = int(row["norad_catalog_id"])
        celestrak_by_norad[nid] = row

    for norad in SATELLITE_CATALOG:
        if norad not in celestrak_by_norad:
            raise KeyError(
                f"Catalog NORAD {norad} not in CelesTrak CSV; "
                "refresh source data or adjust SATELLITE_CATALOG."
            )

    cities = load_world_cities(cities_path)

    provenance: dict[str, Any] = {}
    if prov_path.is_file():
        provenance = json.loads(prov_path.read_text(encoding="utf-8"))

    cases_out: list[BuiltCase] = []
    horizon_starts: dict[str, str] = {}

    dataset_root = output_dir
    cases_root = dataset_root / "cases"

    pool_norads = sorted(SATELLITE_CATALOG.keys())
    with _EtopoReader(etopo_path) as etopo:
        for case_index in range(NUM_CANONICAL_CASES):
            case_id = f"case_{case_index + 1:04d}"
            rng = random.Random(seed + case_index * 10007)
            norad_list, n_targets = _sample_case_satellites_and_target_count(rng, pool_norads)
            inclinations = [
                _inclination_deg_from_tle_line2(celestrak_by_norad[n]["tle_line2"]) for n in norad_list
            ]

            satellites = [_build_satellite_dict(celestrak_by_norad, n) for n in norad_list]
            sat_ids = [s["id"] for s in satellites]

            n_urban = n_targets // 4
            used_coords: set[tuple[float, float]] = set()

            urban = _sample_urban_targets(
                cities,
                rng,
                n_urban,
                used_coords,
                inclinations,
                etopo,
                wc_dir,
            )
            non_urban = _sample_non_urban_targets(
                rng,
                n_targets - n_urban,
                etopo,
                wc_dir,
                used_coords,
                inclinations,
            )
            raw_targets = urban + non_urban
            rng.shuffle(raw_targets)
            if len(raw_targets) < n_targets:
                raise RuntimeError(
                    f"Could not sample enough targets for {case_id} (got {len(raw_targets)})."
                )
            raw_targets = raw_targets[:n_targets]
            targets = _finalize_targets(raw_targets, etopo, wc_dir, rng)

            h_start, h_end = _horizon_for_case(seed, case_index)
            horizon_starts[case_id] = h_start

            case_dir = cases_root / case_id
            _write_yaml(case_dir / "satellites.yaml", satellites)
            _write_yaml(case_dir / "targets.yaml", targets)
            _write_yaml(case_dir / "mission.yaml", _mission_template(h_start, h_end))

            cases_out.append(
                BuiltCase(
                    case_id=case_id,
                    num_satellites=len(satellites),
                    num_targets=len(targets),
                    norad_catalog_ids=list(norad_list),
                    satellite_ids=sat_ids,
                    target_ids=[t["id"] for t in targets],
                    horizon_start=h_start,
                    horizon_end=h_end,
                )
            )

    example_map = build_example_solution(cases_out, horizon_starts)
    example_path = dataset_root / "example_solution.json"
    example_path.write_text(
        json.dumps(example_map, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    index_doc: dict[str, Any] = {
        "benchmark": "stereo_imaging",
        "spec_version": "v3",
        "canonical_seed": seed,
        "generator_revision": git_revision,
        "horizon_duration_s": DEFAULT_HORIZON_DURATION_S,
        "source_provenance": provenance,
        "cases": [
            {
                "case_id": bc.case_id,
                "num_satellites": bc.num_satellites,
                "num_targets": bc.num_targets,
                "norad_catalog_ids": bc.norad_catalog_ids,
                "satellite_ids": bc.satellite_ids,
                "horizon_start": bc.horizon_start,
                "horizon_end": bc.horizon_end,
            }
            for bc in cases_out
        ],
        "selected_norad_catalog_ids": sorted(SATELLITE_CATALOG.keys()),
    }
    (dataset_root / "index.json").write_text(
        json.dumps(index_doc, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return index_doc


__all__ = [
    "CANONICAL_SEED",
    "NUM_CANONICAL_CASES",
    "SATELLITE_CATALOG",
    "generate_dataset",
    "build_example_solution",
]
