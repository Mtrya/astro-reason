"""Canonical v3 stereo_imaging dataset generation."""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from . import sources as sources_module
from .lookup_tables import ELEVATION_GRID, LOOKUP_TABLE_VERSION, SCENE_GRID
from .normalize import load_celestrak_csv, load_world_cities

# -----------------------------------------------------------------------------
# Canonical release parameters
# -----------------------------------------------------------------------------

CANONICAL_SEED = 20260406
DEFAULT_HORIZON_DURATION_S = 172800  # 48 h

NUM_CANONICAL_CASES = 5
MIN_SATELLITES_PER_CASE = 2
MAX_SATELLITES_PER_CASE = 4
MIN_TARGETS_PER_CASE = 24
MAX_TARGETS_PER_CASE = 48

LOOKUP_GRID_RESOLUTION_DEG = 1.0
LOOKUP_LAT_MIN = -89
LOOKUP_LAT_MAX = 90
LOOKUP_LON_MIN = -179
LOOKUP_LON_MAX = 180

MIN_URBAN_POPULATION = 100_000
NON_URBAN_JITTER_DEG = 0.48

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


def _passes_feasibility(
    lat: float,
    lon: float,
    inclinations_deg: list[float],
) -> bool:
    """Lightweight conservative filter: latitude within inclination band and non-polar."""
    del lon
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


def _round_half_away_from_zero(value: float) -> int:
    if value >= 0:
        return int(math.floor(value + 0.5))
    return int(math.ceil(value - 0.5))


def _clamp_target_coordinates(lat: float, lon: float) -> tuple[float, float]:
    clamped_lat = min(max(lat, LOOKUP_LAT_MIN), LOOKUP_LAT_MAX)
    clamped_lon = min(max(lon, LOOKUP_LON_MIN), LOOKUP_LON_MAX)
    return clamped_lat, clamped_lon


def lookup_scene_type(
    lat: float,
    lon: float,
    *,
    scene_grid: dict[tuple[int, int], str] | None = None,
) -> str:
    """Return the nearest-cell scene label or raise when the point maps to ocean/invalid terrain."""
    lat, lon = _clamp_target_coordinates(lat, lon)
    grid = SCENE_GRID if scene_grid is None else scene_grid
    key = (_round_half_away_from_zero(lat), _round_half_away_from_zero(lon))
    try:
        return grid[key]
    except KeyError as exc:
        raise ValueError(f"Target ({lat}, {lon}) maps to an invalid scene cell") from exc


def bilinear_elevation_m(
    lat: float,
    lon: float,
    *,
    elevation_grid: dict[tuple[int, int], float] | None = None,
) -> float:
    """Bilinear interpolation over the four surrounding 1-degree cell centers."""
    lat, lon = _clamp_target_coordinates(lat, lon)
    grid = ELEVATION_GRID if elevation_grid is None else elevation_grid

    lat0 = max(LOOKUP_LAT_MIN, min(int(math.floor(lat)), LOOKUP_LAT_MAX))
    lon0 = max(LOOKUP_LON_MIN, min(int(math.floor(lon)), LOOKUP_LON_MAX))
    lat1 = min(lat0 + 1, LOOKUP_LAT_MAX)
    lon1 = min(lon0 + 1, LOOKUP_LON_MAX)

    corners = {
        (lat0, lon0): grid.get((lat0, lon0)),
        (lat1, lon0): grid.get((lat1, lon0)),
        (lat0, lon1): grid.get((lat0, lon1)),
        (lat1, lon1): grid.get((lat1, lon1)),
    }
    if all(value is None for value in corners.values()):
        raise ValueError(f"Target ({lat}, {lon}) falls in an ocean cell")

    fy = 0.0 if lat1 == lat0 else lat - lat0
    fx = 0.0 if lon1 == lon0 else lon - lon0

    v00 = float(corners[(lat0, lon0)] or 0.0)
    v10 = float(corners[(lat1, lon0)] or 0.0)
    v01 = float(corners[(lat0, lon1)] or 0.0)
    v11 = float(corners[(lat1, lon1)] or 0.0)

    return (
        v00 * (1.0 - fy) * (1.0 - fx)
        + v10 * fy * (1.0 - fx)
        + v01 * (1.0 - fy) * fx
        + v11 * fy * fx
    )


def _lookup_metadata_payload() -> dict[str, Any]:
    elevation_items = [
        [lat_idx, lon_idx, round(float(value), 6)]
        for (lat_idx, lon_idx), value in sorted(ELEVATION_GRID.items())
    ]
    scene_items = [
        [lat_idx, lon_idx, scene]
        for (lat_idx, lon_idx), scene in sorted(SCENE_GRID.items())
    ]
    return {
        "version": LOOKUP_TABLE_VERSION,
        "resolution_deg": LOOKUP_GRID_RESOLUTION_DEG,
        "elevation_cell_count": len(ELEVATION_GRID),
        "scene_cell_count": len(SCENE_GRID),
        "elevation_items": elevation_items,
        "scene_items": scene_items,
    }


@lru_cache(maxsize=1)
def lookup_table_metadata() -> dict[str, Any]:
    payload = _lookup_metadata_payload()
    digest_source = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    lookup_hash = hashlib.sha256(digest_source).hexdigest()
    return {
        "version": payload["version"],
        "resolution_deg": payload["resolution_deg"],
        "elevation_cell_count": payload["elevation_cell_count"],
        "scene_cell_count": payload["scene_cell_count"],
        "sha256": lookup_hash,
    }


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


def _city_slug(name: str) -> str:
    slug = name.lower().replace(" ", "_").replace("`", "").replace("'", "")
    return slug[:24]


def _sample_urban_targets(
    cities: list[dict[str, Any]],
    rng: random.Random,
    count: int,
    used: set[tuple[float, float]],
    inclinations_deg: list[float],
) -> list[dict[str, Any]]:
    """Sample city targets from the reproducible world-cities source."""
    pool = [c for c in cities if c.get("population", 0) >= MIN_URBAN_POPULATION]
    rng.shuffle(pool)
    out: list[dict[str, Any]] = []
    idx = 0
    while len(out) < count and idx < len(pool) * 3:
        city = pool[idx % len(pool)]
        idx += 1
        lat = float(city["latitude_deg"])
        lon = float(city["longitude_deg"])
        lat, lon = _clamp_target_coordinates(lat, lon)
        key = (round(lat, 2), round(lon, 2))
        if key in used:
            continue
        if not _passes_feasibility(lat, lon, inclinations_deg):
            continue
        try:
            bilinear_elevation_m(lat, lon)
        except ValueError:
            continue
        used.add(key)
        cid = f"urban_{_city_slug(str(city['name']))}_{len(out):02d}"
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


def _candidate_cells_by_scene(inclinations_deg: list[float]) -> dict[str, list[tuple[int, int]]]:
    candidates: dict[str, list[tuple[int, int]]] = {
        "vegetated": [],
        "rugged": [],
        "open": [],
    }
    for cell, scene in SCENE_GRID.items():
        if scene not in candidates:
            continue
        lat_idx, lon_idx = cell
        if not _passes_feasibility(float(lat_idx), float(lon_idx), inclinations_deg):
            continue
        candidates[scene].append(cell)
    return candidates


def _cell_area_weight(cell: tuple[int, int]) -> float:
    lat_idx, _lon_idx = cell
    # One-degree cells shrink with latitude, so sampling uniformly over cell indices
    # overweights the Arctic/Antarctic. Use a cosine proxy for relative surface area.
    return max(math.cos(math.radians(abs(lat_idx))), 1.0e-3)


def _weighted_cell_order(
    cells: list[tuple[int, int]],
    rng: random.Random,
) -> list[tuple[int, int]]:
    ranked: list[tuple[float, tuple[int, int]]] = []
    for cell in cells:
        u = max(rng.random(), 1.0e-12)
        key = math.log(u) / _cell_area_weight(cell)
        ranked.append((key, cell))
    ranked.sort(reverse=True)
    return [cell for _key, cell in ranked]


def _jitter_point_inside_cell(
    rng: random.Random,
    cell: tuple[int, int],
    *,
    scene: str,
) -> tuple[float, float]:
    lat_idx, lon_idx = cell
    for _ in range(10):
        lat = lat_idx + rng.uniform(-NON_URBAN_JITTER_DEG, NON_URBAN_JITTER_DEG)
        lon = lon_idx + rng.uniform(-NON_URBAN_JITTER_DEG, NON_URBAN_JITTER_DEG)
        if lookup_scene_type(lat, lon) != scene:
            continue
        bilinear_elevation_m(lat, lon)
        return lat, lon
    raise RuntimeError(f"Could not sample a stable point inside scene cell {cell} ({scene})")


def _sample_non_urban_targets(
    rng: random.Random,
    count: int,
    used: set[tuple[float, float]],
    inclinations_deg: list[float],
) -> list[dict[str, Any]]:
    """Sample non-urban targets from committed lookup-table cells."""
    n_veg, n_rug, n_open = _split_three_way(count)
    remaining = {
        "vegetated": n_veg,
        "rugged": n_rug,
        "open": n_open,
    }
    candidates = _candidate_cells_by_scene(inclinations_deg)
    for scene, cells in candidates.items():
        candidates[scene] = _weighted_cell_order(cells, rng)

    used_cells: set[tuple[int, int]] = set()
    targets: list[dict[str, Any]] = []
    for scene in ("vegetated", "rugged", "open"):
        for cell in candidates[scene]:
            if remaining[scene] <= 0:
                break
            if cell in used_cells:
                continue
            lat, lon = _jitter_point_inside_cell(rng, cell, scene=scene)
            key = (round(lat, 2), round(lon, 2))
            if key in used:
                continue
            used.add(key)
            used_cells.add(cell)
            remaining[scene] -= 1
            targets.append(
                {
                    "id": f"{scene}_{len(targets):03d}",
                    "latitude_deg": lat,
                    "longitude_deg": lon,
                    "scene_type": scene,
                }
            )

    if sum(remaining.values()) > 0:
        raise RuntimeError(f"Non-urban sampling incomplete; remaining={remaining}")

    return targets


def _finalize_targets(
    raw: list[dict[str, Any]],
    rng: random.Random,
) -> list[dict[str, Any]]:
    """Add AOI radius and elevation from vendored lookup tables."""
    out: list[dict[str, Any]] = []
    for target in raw:
        lat = float(target["latitude_deg"])
        lon = float(target["longitude_deg"])
        elevation_m = float(bilinear_elevation_m(lat, lon))
        aoi_radius_m = round(rng.uniform(2500.0, 7500.0), 1)
        out.append(
            {
                "id": target["id"],
                "latitude_deg": lat,
                "longitude_deg": lon,
                "aoi_radius_m": aoi_radius_m,
                "elevation_ref_m": elevation_m,
                "scene_type": target["scene_type"],
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
    """Minimal valid v3 actions for verifier smoke tests (not a quality baseline)."""
    del horizon_starts
    sol: dict[str, Any] = {}
    for bc in cases:
        sol[bc.case_id] = {"actions": []}
    return sol


def generate_dataset(
    source_dir: Path,
    output_dir: Path,
    seed: int = CANONICAL_SEED,
    *,
    git_revision: str | None = None,
) -> dict[str, Any]:
    """
    Build canonical v3 cases under output_dir plus index.json and example_solution.json.

    Expects normalized runtime source data under source_dir and vendored lookup tables in this package.
    """
    cele_path = source_dir / "celestrak" / sources_module.CELESTRAK_CSV_NAME
    cities_path = source_dir / "world_cities" / sources_module.WORLD_CITIES_FILENAME
    prov_path = source_dir / "provenance.json"

    if not cele_path.is_file():
        raise FileNotFoundError(f"Missing CelesTrak CSV: {cele_path}")
    if not cities_path.is_file():
        raise FileNotFoundError(f"Missing world cities CSV: {cities_path}")
    if not ELEVATION_GRID or not SCENE_GRID:
        raise RuntimeError("Vendored lookup tables are empty; regenerate generator/lookup_tables.py")

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

    for case_index in range(NUM_CANONICAL_CASES):
        case_id = f"case_{case_index + 1:04d}"
        rng = random.Random(seed + case_index * 10007)
        norad_list, n_targets = _sample_case_satellites_and_target_count(rng, pool_norads)
        inclinations = [
            _inclination_deg_from_tle_line2(celestrak_by_norad[n]["tle_line2"]) for n in norad_list
        ]

        satellites = [_build_satellite_dict(celestrak_by_norad, n) for n in norad_list]
        sat_ids = [sat["id"] for sat in satellites]

        n_urban = n_targets // 4
        used_coords: set[tuple[float, float]] = set()

        urban = _sample_urban_targets(
            cities,
            rng,
            n_urban,
            used_coords,
            inclinations,
        )
        non_urban = _sample_non_urban_targets(
            rng,
            n_targets - n_urban,
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
        targets = _finalize_targets(raw_targets, rng)

        horizon_start, horizon_end = _horizon_for_case(seed, case_index)
        horizon_starts[case_id] = horizon_start

        case_dir = cases_root / case_id
        _write_yaml(case_dir / "satellites.yaml", satellites)
        _write_yaml(case_dir / "targets.yaml", targets)
        _write_yaml(case_dir / "mission.yaml", _mission_template(horizon_start, horizon_end))

        cases_out.append(
            BuiltCase(
                case_id=case_id,
                num_satellites=len(satellites),
                num_targets=len(targets),
                norad_catalog_ids=list(norad_list),
                satellite_ids=sat_ids,
                target_ids=[target["id"] for target in targets],
                horizon_start=horizon_start,
                horizon_end=horizon_end,
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
    "LOOKUP_TABLE_VERSION",
    "lookup_scene_type",
    "bilinear_elevation_m",
    "lookup_table_metadata",
    "generate_dataset",
    "build_example_solution",
]
