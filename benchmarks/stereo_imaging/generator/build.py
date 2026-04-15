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

LOOKUP_GRID_RESOLUTION_DEG = 1.0
LOOKUP_LAT_MIN = -89
LOOKUP_LAT_MAX = 90
LOOKUP_LON_MIN = -179
LOOKUP_LON_MAX = 180


def _validate_path_segment(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "/" in value or "\\" in value:
        raise ValueError(f"{label} must be a non-empty single path segment")
    return value


def _require_mapping(mapping: object, label: str) -> dict[str, Any]:
    if not isinstance(mapping, dict):
        raise ValueError(f"{label} must be a mapping")
    return mapping


def _require_sequence(values: object, label: str) -> list[Any]:
    if not isinstance(values, list) or not values:
        raise ValueError(f"{label} must be a non-empty list")
    return values


def _require_int(mapping: dict[str, Any], key: str, label: str) -> int:
    value = mapping.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label}.{key} must be an integer")
    return value


def _require_float(mapping: dict[str, Any], key: str, label: str) -> float:
    value = mapping.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{label}.{key} must be numeric")
    return float(value)


def load_generator_config(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"missing required splits config: {path}") from exc
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"failed to load splits config {path}: {exc}") from exc

    config = _require_mapping(payload, "splits config")
    source = _require_mapping(config.get("source"), "source")
    celestrak = _require_mapping(source.get("celestrak"), "source.celestrak")
    snapshot_epoch_utc = str(celestrak.get("snapshot_epoch_utc"))
    if snapshot_epoch_utc != sources_module.CELESTRAK_SNAPSHOT_EPOCH_UTC:
        raise ValueError(
            "stereo_imaging only supports the cached CelesTrak snapshot epoch "
            f"{sources_module.CELESTRAK_SNAPSHOT_EPOCH_UTC}; got {snapshot_epoch_utc!r}"
        )

    splits = _require_mapping(config.get("splits"), "splits")
    if not splits:
        raise ValueError("splits config must contain a non-empty top-level 'splits' mapping")
    for split_name, split_config in splits.items():
        _validate_path_segment(split_name, "split name")
        split_payload = _require_mapping(split_config, f"splits.{split_name}")
        case_count = _require_int(split_payload, "case_count", f"splits.{split_name}")
        if case_count <= 0:
            raise ValueError(f"splits.{split_name}.case_count must be positive")
        _require_int(split_payload, "seed", f"splits.{split_name}")

    smoke_case = config.get("example_smoke_case")
    if not isinstance(smoke_case, str) or not smoke_case:
        raise ValueError("splits config must include example_smoke_case")
    parts = smoke_case.split("/")
    if len(parts) != 2:
        raise ValueError("example_smoke_case must be formatted as <split>/<case_id>")
    smoke_split = _validate_path_segment(parts[0], "example_smoke_case split")
    smoke_case_id = _validate_path_segment(parts[1], "example_smoke_case case_id")
    smoke_split_config = _require_mapping(splits.get(smoke_split), f"splits.{smoke_split}")
    case_count = _require_int(smoke_split_config, "case_count", f"splits.{smoke_split}")
    try:
        smoke_case_number = int(smoke_case_id.removeprefix("case_"))
    except ValueError as exc:
        raise ValueError("example_smoke_case case_id must look like case_0001") from exc
    if smoke_case_number < 1 or smoke_case_number > case_count:
        raise ValueError(f"example_smoke_case {smoke_case} is outside the configured case_count")
    return config


def _sample_case_satellites_and_target_count(
    rng: random.Random,
    pool_norads: list[int],
    *,
    split_config: dict[str, Any],
) -> tuple[list[int], int]:
    """Deterministic random: satellite count in [2,4], target count in [24,48], distinct NORAD ids."""
    satellites_config = _require_mapping(split_config.get("satellites"), "satellites")
    targets_config = _require_mapping(split_config.get("targets"), "targets")
    n_sat = rng.randint(
        _require_int(satellites_config, "min_per_case", "satellites"),
        _require_int(satellites_config, "max_per_case", "satellites"),
    )
    n_targ = rng.randint(
        _require_int(targets_config, "min_count", "targets"),
        _require_int(targets_config, "max_count", "targets"),
    )
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


def _horizon_for_case(seed: int, case_index: int, *, split_config: dict[str, Any]) -> tuple[str, str]:
    """Deterministic mission horizon per case (48 h)."""
    mission = _require_mapping(split_config.get("mission"), "mission")
    base = _parse_iso_utc(str(mission["base_horizon_start"])).astimezone(timezone.utc)
    offset_hours = (seed % 1000) + case_index * _require_int(
        mission,
        "case_start_spacing_hours",
        "mission",
    )
    start = base + timedelta(hours=offset_hours)
    end = start + timedelta(seconds=_require_int(mission, "horizon_duration_s", "mission"))
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


def _mission_template(
    horizon_start: str,
    horizon_end: str,
    *,
    mission_config: dict[str, Any],
) -> dict[str, Any]:
    validity_thresholds = _require_mapping(
        mission_config.get("validity_thresholds"),
        "mission.validity_thresholds",
    )
    quality_model = _require_mapping(mission_config.get("quality_model"), "mission.quality_model")
    return {
        "mission": {
            "horizon_start": horizon_start,
            "horizon_end": horizon_end,
            "allow_cross_satellite_stereo": bool(mission_config["allow_cross_satellite_stereo"]),
            "allow_cross_date_stereo": bool(mission_config["allow_cross_date_stereo"]),
            "validity_thresholds": validity_thresholds,
            "quality_model": quality_model,
        }
    }


def _build_satellite_dict(
    celestrak_by_norad: dict[int, dict[str, Any]],
    norad_id: int,
    satellite_catalog: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    cat = satellite_catalog[norad_id]
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
    *,
    min_urban_population: int,
) -> list[dict[str, Any]]:
    """Sample city targets from the reproducible world-cities source."""
    pool = [c for c in cities if c.get("population", 0) >= min_urban_population]
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
    non_urban_jitter_deg: float,
) -> tuple[float, float]:
    lat_idx, lon_idx = cell
    for _ in range(10):
        lat = lat_idx + rng.uniform(-non_urban_jitter_deg, non_urban_jitter_deg)
        lon = lon_idx + rng.uniform(-non_urban_jitter_deg, non_urban_jitter_deg)
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
    *,
    non_urban_jitter_deg: float,
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
            lat, lon = _jitter_point_inside_cell(
                rng,
                cell,
                scene=scene,
                non_urban_jitter_deg=non_urban_jitter_deg,
            )
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
    *,
    aoi_radius_min_m: float,
    aoi_radius_max_m: float,
) -> list[dict[str, Any]]:
    """Add AOI radius and elevation from vendored lookup tables."""
    out: list[dict[str, Any]] = []
    for target in raw:
        lat = float(target["latitude_deg"])
        lon = float(target["longitude_deg"])
        elevation_m = float(bilinear_elevation_m(lat, lon))
        aoi_radius_m = round(rng.uniform(aoi_radius_min_m, aoi_radius_max_m), 1)
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


def _source_provenance_for_index(raw: dict[str, Any]) -> dict[str, Any]:
    """Drop volatile fields so `dataset/index.json` is stable for reproducibility hashing.

    Removes timestamps and cache-run flags (e.g. whether world-cities was a cache hit).
    """
    if not raw:
        return {}
    cleaned = json.loads(json.dumps(raw))
    cleaned.pop("generated_at_utc", None)
    _VOLATILE_SUBKEYS = frozenset({"retrieval_timestamp_utc", "skipped_cached"})
    for key in ("celestrak", "world_cities"):
        sub = cleaned.get(key)
        if isinstance(sub, dict):
            for vk in _VOLATILE_SUBKEYS:
                sub.pop(vk, None)
    return cleaned


def build_example_solution(
    cases: list[BuiltCase],
    horizon_starts: dict[str, str],
) -> dict[str, Any]:
    """Minimal valid v3 solution for verifier smoke tests (not a quality baseline).

    Single per-case shape matching real solutions; aligned with the first canonical case.
    """
    del horizon_starts
    return {"actions": []}


def generate_dataset(
    source_dir: Path,
    output_dir: Path,
    *,
    split_configs: dict[str, dict[str, Any]],
    example_smoke_case: str,
    source_config: dict[str, Any],
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

    cities = load_world_cities(cities_path)

    provenance: dict[str, Any] = {}
    if prov_path.is_file():
        provenance = json.loads(prov_path.read_text(encoding="utf-8"))

    cases_out: list[tuple[str, BuiltCase]] = []
    horizon_starts: dict[str, str] = {}

    dataset_root = output_dir
    cases_root = dataset_root / "cases"
    smoke_split, smoke_case_id = example_smoke_case.split("/")
    smoke_found = False
    selected_norad_catalog_ids: set[int] = set()

    for split_name, split_config_obj in split_configs.items():
        split_config = _require_mapping(split_config_obj, f"splits.{split_name}")
        seed = _require_int(split_config, "seed", f"splits.{split_name}")
        case_count = _require_int(split_config, "case_count", f"splits.{split_name}")
        case_seed_stride = _require_int(split_config, "case_seed_stride", f"splits.{split_name}")
        satellites_config = _require_mapping(split_config.get("satellites"), f"splits.{split_name}.satellites")
        targets_config = _require_mapping(split_config.get("targets"), f"splits.{split_name}.targets")
        mission_config = _require_mapping(split_config.get("mission"), f"splits.{split_name}.mission")
        satellite_catalog = {
            int(norad): _require_mapping(spec, f"splits.{split_name}.satellites.catalog.{norad}")
            for norad, spec in _require_mapping(
                satellites_config.get("catalog"),
                f"splits.{split_name}.satellites.catalog",
            ).items()
        }
        for norad in satellite_catalog:
            if norad not in celestrak_by_norad:
                raise KeyError(
                    f"Catalog NORAD {norad} not in CelesTrak CSV; "
                    "refresh source data or update splits.yaml."
                )
        pool_norads = sorted(satellite_catalog.keys())
        selected_norad_catalog_ids.update(pool_norads)

        for case_index in range(case_count):
            case_id = f"case_{case_index + 1:04d}"
            rng = random.Random(seed + case_index * case_seed_stride)
            norad_list, n_targets = _sample_case_satellites_and_target_count(
                rng,
                pool_norads,
                split_config=split_config,
            )
            inclinations = [
                _inclination_deg_from_tle_line2(celestrak_by_norad[n]["tle_line2"]) for n in norad_list
            ]

            satellites = [
                _build_satellite_dict(celestrak_by_norad, n, satellite_catalog) for n in norad_list
            ]
            sat_ids = [sat["id"] for sat in satellites]

            urban_divisor = _require_int(targets_config, "urban_target_divisor", "targets")
            n_urban = n_targets // urban_divisor
            used_coords: set[tuple[float, float]] = set()

            urban = _sample_urban_targets(
                cities,
                rng,
                n_urban,
                used_coords,
                inclinations,
                min_urban_population=_require_int(
                    targets_config,
                    "min_urban_population",
                    "targets",
                ),
            )
            non_urban = _sample_non_urban_targets(
                rng,
                n_targets - n_urban,
                used_coords,
                inclinations,
                non_urban_jitter_deg=_require_float(
                    targets_config,
                    "non_urban_jitter_deg",
                    "targets",
                ),
            )
            raw_targets = urban + non_urban
            rng.shuffle(raw_targets)
            if len(raw_targets) < n_targets:
                raise RuntimeError(
                    f"Could not sample enough targets for {case_id} (got {len(raw_targets)})."
                )
            raw_targets = raw_targets[:n_targets]
            targets = _finalize_targets(
                raw_targets,
                rng,
                aoi_radius_min_m=_require_float(targets_config, "aoi_radius_min_m", "targets"),
                aoi_radius_max_m=_require_float(targets_config, "aoi_radius_max_m", "targets"),
            )

            horizon_start, horizon_end = _horizon_for_case(seed, case_index, split_config=split_config)
            horizon_starts[case_id] = horizon_start

            case_dir = cases_root / split_name / case_id
            _write_yaml(case_dir / "satellites.yaml", satellites)
            _write_yaml(case_dir / "targets.yaml", targets)
            _write_yaml(
                case_dir / "mission.yaml",
                _mission_template(horizon_start, horizon_end, mission_config=mission_config),
            )

            built_case = BuiltCase(
                case_id=case_id,
                num_satellites=len(satellites),
                num_targets=len(targets),
                norad_catalog_ids=list(norad_list),
                satellite_ids=sat_ids,
                target_ids=[target["id"] for target in targets],
                horizon_start=horizon_start,
                horizon_end=horizon_end,
            )
            cases_out.append((split_name, built_case))
            if split_name == smoke_split and case_id == smoke_case_id:
                smoke_found = True

    if not smoke_found:
        raise ValueError(f"example_smoke_case {example_smoke_case} was not generated")

    example_obj = build_example_solution([built_case for _split, built_case in cases_out], horizon_starts)
    example_path = dataset_root / "example_solution.json"
    example_path.write_text(
        json.dumps(example_obj, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    index_doc: dict[str, Any] = {
        "benchmark": "stereo_imaging",
        "spec_version": "v3",
        "source": {
            **source_config,
            "runtime_provenance": _source_provenance_for_index(provenance),
        },
        "example_smoke_case": example_smoke_case,
        "cases": [
            {
                "split": split_name,
                "case_id": bc.case_id,
                "path": f"cases/{split_name}/{bc.case_id}",
                "num_satellites": bc.num_satellites,
                "num_targets": bc.num_targets,
                "norad_catalog_ids": bc.norad_catalog_ids,
                "satellite_ids": bc.satellite_ids,
                "horizon_start": bc.horizon_start,
                "horizon_end": bc.horizon_end,
            }
            for split_name, bc in cases_out
        ],
        "selected_norad_catalog_ids": sorted(selected_norad_catalog_ids),
    }
    unique_seeds = {
        _require_int(_require_mapping(split_config, f"splits.{split_name}"), "seed", f"splits.{split_name}")
        for split_name, split_config in split_configs.items()
    }
    if len(unique_seeds) == 1:
        index_doc["generator_seed"] = next(iter(unique_seeds))
        index_doc["canonical_seed"] = next(iter(unique_seeds))
    first_split_name = next(iter(split_configs))
    first_mission = _require_mapping(split_configs[first_split_name].get("mission"), f"splits.{first_split_name}.mission")
    index_doc["horizon_duration_s"] = _require_int(first_mission, "horizon_duration_s", "mission")
    (dataset_root / "index.json").write_text(
        json.dumps(index_doc, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return index_doc


__all__ = [
    "LOOKUP_TABLE_VERSION",
    "lookup_scene_type",
    "bilinear_elevation_m",
    "lookup_table_metadata",
    "load_generator_config",
    "generate_dataset",
    "build_example_solution",
]
