"""Vectorized link feasibility checks. Pure NumPy, no benchmark imports."""

from __future__ import annotations

import numpy as np

from .case_io import Manifest, Endpoint


def _segment_clear_of_earth_batch(
    point_a: np.ndarray,  # (N, 3)
    point_b: np.ndarray,  # (N, 3)
) -> np.ndarray:
    """Vectorized Earth-occlusion check for line segments.

    Returns boolean array of shape (N,) indicating whether each segment
    is clear of the Earth.
    """
    import brahe

    segment = point_b - point_a  # (N, 3)
    denom = np.einsum("ij,ij->i", segment, segment)  # (N,)
    # For zero-length segments, just check if the point is above surface
    zero_mask = denom <= 1e-9
    t = np.empty_like(denom)
    t[~zero_mask] = -np.einsum("ij,ij->i", point_a[~zero_mask], segment[~zero_mask]) / denom[~zero_mask]
    t = np.clip(t, 0.0, 1.0)
    closest = point_a + t[:, np.newaxis] * segment  # (N, 3)
    clear = np.linalg.norm(closest, axis=1) > float(brahe.R_EARTH) + 1.0
    clear[zero_mask] = np.linalg.norm(point_a[zero_mask], axis=1) > float(brahe.R_EARTH)
    return clear


def ground_links_feasible(
    manifest: Manifest,
    endpoints: dict[str, Endpoint],
    positions_ecef: dict[str, np.ndarray],
) -> tuple[dict[str, dict[str, np.ndarray]], dict[str, dict[str, np.ndarray]]]:
    """Compute ground-link feasibility and slant ranges for all endpoint-satellite pairs.

    Parameters
    ----------
    positions_ecef : dict[str, np.ndarray]
        Maps satellite_id -> array of shape (n_samples, 3).

    Returns
    -------
    (feasible, distances_m)
        Each is dict[endpoint_id][satellite_id] -> np.ndarray bool/float of shape (n_samples,).
    """
    satellite_ids = sorted(positions_ecef.keys())

    # Stack all satellite positions: (n_satellites, n_samples, 3)
    sat_positions = np.stack([positions_ecef[sid] for sid in satellite_ids], axis=0)

    feasible_result: dict[str, dict[str, np.ndarray]] = {}
    distances_result: dict[str, dict[str, np.ndarray]] = {}

    for endpoint_id, endpoint in endpoints.items():
        ecef = endpoint.ecef_position_m  # (3,)
        zenith = ecef / np.linalg.norm(ecef)  # (3,)

        diff = sat_positions - ecef  # (n_satellites, n_samples, 3)
        slant_range = np.linalg.norm(diff, axis=2)  # (n_satellites, n_samples)

        # diff: (n_satellites, n_samples, 3); zenith: (3,)
        # Compute dot product over the last axis
        dot_product = np.tensordot(diff, zenith, axes=([2], [0]))  # (n_satellites, n_samples)
        sin_elevation = dot_product / (slant_range + 1e-12)
        sin_elevation = np.clip(sin_elevation, -1.0, 1.0)
        elevation_deg = np.degrees(np.arcsin(sin_elevation))

        feasible = elevation_deg >= endpoint.min_elevation_deg
        if manifest.max_ground_range_m is not None:
            feasible = feasible & (slant_range <= manifest.max_ground_range_m)

        feasible_result[endpoint_id] = {
            sid: feasible[i] for i, sid in enumerate(satellite_ids)
        }
        distances_result[endpoint_id] = {
            sid: slant_range[i] for i, sid in enumerate(satellite_ids)
        }

    return feasible_result, distances_result


def isl_links_feasible(
    manifest: Manifest,
    positions_ecef: dict[str, np.ndarray],
) -> tuple[dict[str, dict[str, np.ndarray]], dict[str, dict[str, np.ndarray]]]:
    """Compute ISL feasibility and distances for all satellite-satellite pairs.

    Returns
    -------
    (feasible, distances_m)
        Each is dict[satellite_id_1][satellite_id_2] -> np.ndarray bool/float of shape (n_samples,).
        Only i < j pairs are populated; the dict is symmetric.
    """
    satellite_ids = sorted(positions_ecef.keys())
    n_satellites = len(satellite_ids)

    # Stack positions: (n_satellites, n_samples, 3)
    sat_positions = np.stack([positions_ecef[sid] for sid in satellite_ids], axis=0)

    feasible_result: dict[str, dict[str, np.ndarray]] = {
        sid: {} for sid in satellite_ids
    }
    distances_result: dict[str, dict[str, np.ndarray]] = {
        sid: {} for sid in satellite_ids
    }

    for i in range(n_satellites):
        sid_i = satellite_ids[i]
        pos_i = sat_positions[i]  # (n_samples, 3)
        for j in range(i + 1, n_satellites):
            sid_j = satellite_ids[j]
            pos_j = sat_positions[j]  # (n_samples, 3)

            diff = pos_j - pos_i  # (n_samples, 3)
            distance = np.linalg.norm(diff, axis=1)  # (n_samples,)

            range_feasible = distance <= manifest.max_isl_range_m
            clear = _segment_clear_of_earth_batch(pos_i, pos_j)
            feasible = range_feasible & clear

            feasible_result[sid_i][sid_j] = feasible
            feasible_result[sid_j][sid_i] = feasible
            distances_result[sid_i][sid_j] = distance
            distances_result[sid_j][sid_i] = distance

    return feasible_result, distances_result
