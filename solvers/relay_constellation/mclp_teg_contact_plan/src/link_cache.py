"""Precompute feasible links over the routing grid."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

import brahe
import numpy as np

from .case_io import BackboneSatellite, Case, Constraints, GroundEndpoint
from .orbit_library import CandidateSatellite
from .link_geometry import ground_link_feasible, isl_feasible


@dataclass(frozen=True)
class LinkRecord:
    sample_index: int
    node_a: str
    node_b: str
    distance_m: float
    link_type: str  # "ground" or "isl"


def _all_satellite_ids(
    backbone: Iterable[BackboneSatellite],
    candidates: Iterable[CandidateSatellite],
) -> list[str]:
    return [s.satellite_id for s in backbone] + [c.satellite_id for c in candidates]


def build_link_cache(
    case: Case,
    backbone_positions: dict[str, dict[int, np.ndarray]],
    candidate_positions: dict[str, dict[int, np.ndarray]],
) -> tuple[tuple[LinkRecord, ...], dict[str, object]]:
    """Precompute all feasible links and return records plus a summary dict.

    backbone_positions and candidate_positions map satellite_id -> sample_index -> ECEF position.
    """
    constraints = case.manifest.constraints
    endpoints = case.network.ground_endpoints
    num_samples = len(next(iter(backbone_positions.values())))

    records: list[LinkRecord] = []
    summary = {
        "num_samples": num_samples,
        "ground_link_records": 0,
        "isl_link_records": 0,
        "per_sample_ground_counts": [0] * num_samples,
        "per_sample_isl_counts": [0] * num_samples,
    }

    satellite_ids = _all_satellite_ids(case.network.backbone_satellites, ())
    all_sat_positions = {sid: backbone_positions[sid] for sid in satellite_ids}
    for cid, cpos in candidate_positions.items():
        all_sat_positions[cid] = cpos

    # Ground links: every endpoint to every satellite
    for endpoint in endpoints:
        endpoint_ecef = (
            endpoint.latitude_deg,
            endpoint.longitude_deg,
            endpoint.altitude_m,
        )
        endpoint_ecef_arr = np.asarray(
            brahe.position_geodetic_to_ecef(
                [endpoint.longitude_deg, endpoint.latitude_deg, endpoint.altitude_m],
                brahe.AngleFormat.DEGREES,
            ),
            dtype=float,
        )
        for sat_id, positions in all_sat_positions.items():
            for sample_index in range(num_samples):
                is_feasible, distance_m = ground_link_feasible(
                    tuple(endpoint_ecef_arr.tolist()),
                    positions[sample_index],
                    endpoint.min_elevation_deg,
                    constraints.max_ground_range_m,
                )
                if is_feasible:
                    records.append(
                        LinkRecord(
                            sample_index=sample_index,
                            node_a=endpoint.endpoint_id,
                            node_b=sat_id,
                            distance_m=distance_m,
                            link_type="ground",
                        )
                    )
                    summary["ground_link_records"] += 1
                    summary["per_sample_ground_counts"][sample_index] += 1

    # ISLs: all satellite pairs
    sat_id_list = list(all_sat_positions.keys())
    for i in range(len(sat_id_list)):
        for j in range(i + 1, len(sat_id_list)):
            sat_a = sat_id_list[i]
            sat_b = sat_id_list[j]
            pos_a = all_sat_positions[sat_a]
            pos_b = all_sat_positions[sat_b]
            for sample_index in range(num_samples):
                is_feasible, distance_m = isl_feasible(
                    pos_a[sample_index],
                    pos_b[sample_index],
                    constraints.max_isl_range_m,
                )
                if is_feasible:
                    records.append(
                        LinkRecord(
                            sample_index=sample_index,
                            node_a=sat_a,
                            node_b=sat_b,
                            distance_m=distance_m,
                            link_type="isl",
                        )
                    )
                    summary["isl_link_records"] += 1
                    summary["per_sample_isl_counts"][sample_index] += 1

    summary["total_records"] = len(records)
    summary["per_sample_total_counts"] = [
        summary["per_sample_ground_counts"][s] + summary["per_sample_isl_counts"][s]
        for s in range(num_samples)
    ]

    return tuple(records), summary
