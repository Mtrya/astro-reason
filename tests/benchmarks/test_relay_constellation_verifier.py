"""Small sanity checks for the relay_constellation verifier."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import math
from pathlib import Path

import brahe
import numpy as np

from benchmarks.relay_constellation.verifier import verify_solution
from benchmarks.relay_constellation.verifier.engine import (
    _datetime_to_epoch,
    _ground_link_feasible,
)
from benchmarks.relay_constellation.verifier.models import RelayEndpoint


_BRAHE_EOP_INITIALIZED = False


def _ensure_brahe_ready() -> None:
    global _BRAHE_EOP_INITIALIZED
    if _BRAHE_EOP_INITIALIZED:
        return
    brahe.set_global_eop_provider_from_static_provider(
        brahe.StaticEOPProvider.from_zero()
    )
    _BRAHE_EOP_INITIALIZED = True


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _wrap_longitude(longitude_deg: float) -> float:
    return ((longitude_deg + 180.0) % 360.0) - 180.0


def _base_manifest(
    *,
    case_id: str,
    epoch: datetime,
    max_added_satellites: int = 2,
    max_links_per_satellite: int = 3,
    max_links_per_endpoint: int = 1,
) -> dict[str, object]:
    return {
        "benchmark": "relay_constellation",
        "case_id": case_id,
        "constraints": {
            "max_added_satellites": max_added_satellites,
            "max_altitude_m": 1_500_000.0,
            "max_eccentricity": 0.02,
            "max_inclination_deg": 85.0,
            "max_isl_range_m": 20_000_000.0,
            "max_links_per_endpoint": max_links_per_endpoint,
            "max_links_per_satellite": max_links_per_satellite,
            "min_altitude_m": 500_000.0,
            "min_inclination_deg": 0.0,
        },
        "epoch": epoch.isoformat().replace("+00:00", "Z"),
        "horizon_end": (epoch + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
        "horizon_start": epoch.isoformat().replace("+00:00", "Z"),
        "propagation": {
            "earth_fixed_frame": "itrf",
            "frame": "gcrf",
            "model": "j2",
        },
        "routing_step_s": 60,
        "scoring": {
            "primary_metric": "service_fraction",
            "secondary_metric": "latency_p95_ms",
        },
        "seed": 123,
    }


def _endpoint_payload(
    endpoint_id: str,
    *,
    latitude_deg: float,
    longitude_deg: float,
    altitude_m: float = 0.0,
    min_elevation_deg: float = 5.0,
) -> dict[str, object]:
    return {
        "endpoint_id": endpoint_id,
        "latitude_deg": latitude_deg,
        "longitude_deg": longitude_deg,
        "altitude_m": altitude_m,
        "min_elevation_deg": min_elevation_deg,
    }


def _endpoint_object(payload: dict[str, object]) -> RelayEndpoint:
    longitude_deg = float(payload["longitude_deg"])
    latitude_deg = float(payload["latitude_deg"])
    altitude_m = float(payload["altitude_m"])
    return RelayEndpoint(
        endpoint_id=str(payload["endpoint_id"]),
        latitude_deg=latitude_deg,
        longitude_deg=longitude_deg,
        altitude_m=altitude_m,
        min_elevation_deg=float(payload["min_elevation_deg"]),
        ecef_position_m=np.asarray(
            brahe.position_geodetic_to_ecef(
                [longitude_deg, latitude_deg, altitude_m],
                brahe.AngleFormat.DEGREES,
            ),
            dtype=float,
        ),
    )


def _equatorial_state_eci(epoch: datetime, *, altitude_m: float) -> np.ndarray:
    _ensure_brahe_ready()
    epoch_brahe = _datetime_to_epoch(epoch)
    semi_major_axis_m = float(brahe.R_EARTH) + altitude_m
    state_eci = np.asarray(
        brahe.state_koe_to_eci(
            np.asarray(
                [semi_major_axis_m, 0.0, 0.0, 0.0, 0.0, 0.0],
                dtype=float,
            ),
            brahe.AngleFormat.DEGREES,
        ),
        dtype=float,
    )
    _ = epoch_brahe
    return state_eci


def _visible_endpoints_for_single_satellite(
    *,
    epoch: datetime,
    state_eci_m_mps: np.ndarray,
    endpoint_ids: tuple[str, ...],
) -> tuple[list[dict[str, object]], list[float]]:
    _ensure_brahe_ready()
    epoch_brahe = _datetime_to_epoch(epoch)
    satellite_position_ecef_m = np.asarray(
        brahe.position_eci_to_ecef(epoch_brahe, state_eci_m_mps[:3]),
        dtype=float,
    )
    sat_lon_deg, sat_lat_deg, _ = brahe.position_ecef_to_geodetic(
        satellite_position_ecef_m,
        brahe.AngleFormat.DEGREES,
    )

    for offset_deg in (1.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 15.0, 18.0):
        candidate_payloads: list[dict[str, object]]
        if len(endpoint_ids) == 2:
            candidate_payloads = [
                _endpoint_payload(
                    endpoint_ids[0],
                    latitude_deg=float(sat_lat_deg),
                    longitude_deg=_wrap_longitude(float(sat_lon_deg) - offset_deg),
                ),
                _endpoint_payload(
                    endpoint_ids[1],
                    latitude_deg=float(sat_lat_deg),
                    longitude_deg=_wrap_longitude(float(sat_lon_deg) + offset_deg),
                ),
            ]
        else:
            candidate_payloads = [
                _endpoint_payload(
                    endpoint_ids[0],
                    latitude_deg=float(sat_lat_deg),
                    longitude_deg=float(sat_lon_deg),
                ),
                _endpoint_payload(
                    endpoint_ids[1],
                    latitude_deg=float(sat_lat_deg),
                    longitude_deg=_wrap_longitude(float(sat_lon_deg) - offset_deg),
                ),
                _endpoint_payload(
                    endpoint_ids[2],
                    latitude_deg=float(sat_lat_deg),
                    longitude_deg=_wrap_longitude(float(sat_lon_deg) + offset_deg),
                ),
            ]
        distances: list[float] = []
        for payload in candidate_payloads:
            endpoint = _endpoint_object(payload)
            is_visible, distance_m = _ground_link_feasible(
                endpoint,
                satellite_position_ecef_m,
                max_ground_range_m=None,
            )
            if not is_visible:
                break
            distances.append(distance_m)
        else:
            return candidate_payloads, distances
    raise AssertionError("Failed to build a visibly connected tiny relay case")


def _single_satellite_case(
    tmp_path: Path,
    *,
    case_id: str,
    endpoint_ids: tuple[str, ...],
    demands_payload: list[dict[str, object]],
    max_links_per_satellite: int = 3,
) -> tuple[Path, np.ndarray, list[dict[str, object]], list[float]]:
    epoch = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    state_eci_m_mps = _equatorial_state_eci(epoch, altitude_m=20_000_000.0)
    endpoints_payload, distances = _visible_endpoints_for_single_satellite(
        epoch=epoch,
        state_eci_m_mps=state_eci_m_mps,
        endpoint_ids=endpoint_ids,
    )
    case_dir = tmp_path / case_id
    _write_json(
        case_dir / "manifest.json",
        _base_manifest(
            case_id=case_id,
            epoch=epoch,
            max_links_per_satellite=max_links_per_satellite,
        ),
    )
    _write_json(
        case_dir / "network.json",
        {
            "backbone_satellites": [
                {
                    "satellite_id": "backbone_001",
                    "x_m": float(state_eci_m_mps[0]),
                    "y_m": float(state_eci_m_mps[1]),
                    "z_m": float(state_eci_m_mps[2]),
                    "vx_m_s": float(state_eci_m_mps[3]),
                    "vy_m_s": float(state_eci_m_mps[4]),
                    "vz_m_s": float(state_eci_m_mps[5]),
                }
            ],
            "ground_endpoints": endpoints_payload,
        },
    )
    _write_json(case_dir / "demands.json", {"demanded_windows": demands_payload})
    return case_dir, state_eci_m_mps, endpoints_payload, distances


def _solution_path(tmp_path: Path, payload: dict[str, object], name: str = "solution.json") -> Path:
    solution_path = tmp_path / name
    _write_json(solution_path, payload)
    return solution_path


def test_verify_solution_rejects_malformed_solution(tmp_path: Path) -> None:
    case_dir, _, _, _ = _single_satellite_case(
        tmp_path,
        case_id="case_malformed",
        endpoint_ids=("ground_001", "ground_002"),
        demands_payload=[
            {
                "demand_id": "demand_001",
                "source_endpoint_id": "ground_001",
                "destination_endpoint_id": "ground_002",
                "start_time": "2026-01-01T00:00:00Z",
                "end_time": "2026-01-01T00:01:00Z",
                "weight": 1.0,
            }
        ],
    )
    solution_path = _solution_path(tmp_path, [], name="malformed.json")

    result = verify_solution(case_dir, solution_path)

    assert result.valid is False
    assert "solution.json must be a JSON object" in result.violations[0]


def test_verify_solution_rejects_invalid_added_orbit(tmp_path: Path) -> None:
    case_dir, _, _, _ = _single_satellite_case(
        tmp_path,
        case_id="case_invalid_orbit",
        endpoint_ids=("ground_001", "ground_002"),
        demands_payload=[],
    )
    low_orbit_state = np.asarray(
        brahe.state_koe_to_eci(
            np.asarray(
                [float(brahe.R_EARTH) + 100_000.0, 0.0, 45.0, 0.0, 0.0, 0.0],
                dtype=float,
            ),
            brahe.AngleFormat.DEGREES,
        ),
        dtype=float,
    )
    solution_path = _solution_path(
        tmp_path,
        {
            "added_satellites": [
                {
                    "satellite_id": "added_001",
                    "x_m": float(low_orbit_state[0]),
                    "y_m": float(low_orbit_state[1]),
                    "z_m": float(low_orbit_state[2]),
                    "vx_m_s": float(low_orbit_state[3]),
                    "vy_m_s": float(low_orbit_state[4]),
                    "vz_m_s": float(low_orbit_state[5]),
                }
            ],
            "actions": [],
        },
        name="invalid_orbit_solution.json",
    )

    result = verify_solution(case_dir, solution_path)

    assert result.valid is False
    assert any("below min_altitude_m" in violation for violation in result.violations)


def test_verify_solution_rejects_off_grid_action(tmp_path: Path) -> None:
    case_dir, _, _, _ = _single_satellite_case(
        tmp_path,
        case_id="case_off_grid",
        endpoint_ids=("ground_001", "ground_002"),
        demands_payload=[
            {
                "demand_id": "demand_001",
                "source_endpoint_id": "ground_001",
                "destination_endpoint_id": "ground_002",
                "start_time": "2026-01-01T00:00:00Z",
                "end_time": "2026-01-01T00:01:00Z",
                "weight": 1.0,
            }
        ],
    )
    solution_path = _solution_path(
        tmp_path,
        {
            "added_satellites": [],
            "actions": [
                {
                    "action_type": "ground_link",
                    "endpoint_id": "ground_001",
                    "satellite_id": "backbone_001",
                    "start_time": "2026-01-01T00:00:30Z",
                    "end_time": "2026-01-01T00:01:00Z",
                }
            ],
        },
        name="off_grid_solution.json",
    )

    result = verify_solution(case_dir, solution_path)

    assert result.valid is False
    assert any("routing_step_s grid" in violation for violation in result.violations)


def test_verify_solution_rejects_concurrency_violation(tmp_path: Path) -> None:
    case_dir, _, _, _ = _single_satellite_case(
        tmp_path,
        case_id="case_concurrency",
        endpoint_ids=("ground_001", "ground_002"),
        demands_payload=[
            {
                "demand_id": "demand_001",
                "source_endpoint_id": "ground_001",
                "destination_endpoint_id": "ground_002",
                "start_time": "2026-01-01T00:00:00Z",
                "end_time": "2026-01-01T00:01:00Z",
                "weight": 1.0,
            }
        ],
        max_links_per_satellite=1,
    )
    solution_path = _solution_path(
        tmp_path,
        {
            "added_satellites": [],
            "actions": [
                {
                    "action_type": "ground_link",
                    "endpoint_id": "ground_001",
                    "satellite_id": "backbone_001",
                    "start_time": "2026-01-01T00:00:00Z",
                    "end_time": "2026-01-01T00:01:00Z",
                },
                {
                    "action_type": "ground_link",
                    "endpoint_id": "ground_002",
                    "satellite_id": "backbone_001",
                    "start_time": "2026-01-01T00:00:00Z",
                    "end_time": "2026-01-01T00:01:00Z",
                },
            ],
        },
        name="concurrency_solution.json",
    )

    result = verify_solution(case_dir, solution_path)

    assert result.valid is False
    assert any("max_links_per_satellite=1" in violation for violation in result.violations)


def test_verify_solution_example_smoke_case_reports_zero_service() -> None:
    dataset_dir = Path("benchmarks/relay_constellation/dataset")
    index_payload = json.loads((dataset_dir / "index.json").read_text(encoding="utf-8"))
    case_dir = dataset_dir / "cases" / index_payload["example_smoke_case_id"]
    solution_path = dataset_dir / "example_solution.json"

    result = verify_solution(case_dir, solution_path)

    assert result.valid is True
    assert result.metrics["service_fraction"] == 0.0
    assert result.metrics["worst_demand_service_fraction"] == 0.0
    assert result.metrics["num_demanded_windows"] > 0
    assert result.metrics["mean_latency_ms"] is None


def test_verify_solution_serves_single_demand_and_scores_latency(tmp_path: Path) -> None:
    case_dir, state_eci_m_mps, endpoints_payload, distances = _single_satellite_case(
        tmp_path,
        case_id="case_positive",
        endpoint_ids=("ground_001", "ground_002"),
        demands_payload=[
            {
                "demand_id": "demand_001",
                "source_endpoint_id": "ground_001",
                "destination_endpoint_id": "ground_002",
                "start_time": "2026-01-01T00:00:00Z",
                "end_time": "2026-01-01T00:01:00Z",
                "weight": 1.0,
            }
        ],
    )
    solution_path = _solution_path(
        tmp_path,
        {
            "added_satellites": [],
            "actions": [
                {
                    "action_type": "ground_link",
                    "endpoint_id": "ground_001",
                    "satellite_id": "backbone_001",
                    "start_time": "2026-01-01T00:00:00Z",
                    "end_time": "2026-01-01T00:01:00Z",
                },
                {
                    "action_type": "ground_link",
                    "endpoint_id": "ground_002",
                    "satellite_id": "backbone_001",
                    "start_time": "2026-01-01T00:00:00Z",
                    "end_time": "2026-01-01T00:01:00Z",
                },
            ],
        },
        name="positive_solution.json",
    )

    result = verify_solution(case_dir, solution_path)

    assert result.valid is True
    assert result.metrics["service_fraction"] == 1.0
    assert result.metrics["worst_demand_service_fraction"] == 1.0
    assert result.metrics["per_demand"]["demand_001"]["served_sample_count"] == 1

    epoch_brahe = _datetime_to_epoch(datetime(2026, 1, 1, 0, 0, tzinfo=UTC))
    satellite_position_ecef_m = np.asarray(
        brahe.position_eci_to_ecef(epoch_brahe, state_eci_m_mps[:3]),
        dtype=float,
    )
    expected_distance_m = 0.0
    for payload in endpoints_payload:
        endpoint = _endpoint_object(payload)
        is_visible, distance_m = _ground_link_feasible(
            endpoint,
            satellite_position_ecef_m,
            max_ground_range_m=None,
        )
        assert is_visible is True
        expected_distance_m += distance_m
    expected_latency_ms = 1000.0 * expected_distance_m / 299_792_458.0
    assert math.isclose(result.metrics["mean_latency_ms"], expected_latency_ms, rel_tol=1e-9)
    assert math.isclose(result.metrics["latency_p95_ms"], expected_latency_ms, rel_tol=1e-9)


def test_verify_solution_allocates_under_edge_contention(tmp_path: Path) -> None:
    case_dir, _, _, _ = _single_satellite_case(
        tmp_path,
        case_id="case_contention",
        endpoint_ids=("ground_001", "ground_002", "ground_003"),
        demands_payload=[
            {
                "demand_id": "demand_001",
                "source_endpoint_id": "ground_001",
                "destination_endpoint_id": "ground_002",
                "start_time": "2026-01-01T00:00:00Z",
                "end_time": "2026-01-01T00:01:00Z",
                "weight": 1.0,
            },
            {
                "demand_id": "demand_002",
                "source_endpoint_id": "ground_001",
                "destination_endpoint_id": "ground_003",
                "start_time": "2026-01-01T00:00:00Z",
                "end_time": "2026-01-01T00:01:00Z",
                "weight": 1.0,
            },
        ],
    )
    solution_path = _solution_path(
        tmp_path,
        {
            "added_satellites": [],
            "actions": [
                {
                    "action_type": "ground_link",
                    "endpoint_id": "ground_001",
                    "satellite_id": "backbone_001",
                    "start_time": "2026-01-01T00:00:00Z",
                    "end_time": "2026-01-01T00:01:00Z",
                },
                {
                    "action_type": "ground_link",
                    "endpoint_id": "ground_002",
                    "satellite_id": "backbone_001",
                    "start_time": "2026-01-01T00:00:00Z",
                    "end_time": "2026-01-01T00:01:00Z",
                },
                {
                    "action_type": "ground_link",
                    "endpoint_id": "ground_003",
                    "satellite_id": "backbone_001",
                    "start_time": "2026-01-01T00:00:00Z",
                    "end_time": "2026-01-01T00:01:00Z",
                },
            ],
        },
        name="contention_solution.json",
    )

    result = verify_solution(case_dir, solution_path)

    assert result.valid is True
    assert result.metrics["service_fraction"] == 0.5
    assert result.metrics["worst_demand_service_fraction"] == 0.0
    assert result.metrics["per_demand"]["demand_001"]["served_sample_count"] == 1
    assert result.metrics["per_demand"]["demand_002"]["served_sample_count"] == 0
