"""Visibility matrix generation over time, slots, and targets."""

from __future__ import annotations

from dataclasses import dataclass
import math

import brahe
import numpy as np

from .case_io import RevisitCase, Target
from .propagation import datetime_to_epoch, ensure_brahe_ready, force_model_config
from .slot_library import OrbitSlot
from .time_grid import TimeSample


NUMERICAL_EPS = 1.0e-9


@dataclass(frozen=True)
class VisibilityMatrix:
    shape: tuple[int, int, int]
    visible: frozenset[tuple[int, int, int]]

    @property
    def visible_count(self) -> int:
        return len(self.visible)

    @property
    def density(self) -> float:
        total = self.shape[0] * self.shape[1] * self.shape[2]
        return 0.0 if total == 0 else self.visible_count / total

    def is_visible(self, time_index: int, slot_index: int, target_index: int) -> bool:
        return (time_index, slot_index, target_index) in self.visible


def _angle_between_deg(vector_a: np.ndarray, vector_b: np.ndarray) -> float:
    norm_a = np.linalg.norm(vector_a)
    norm_b = np.linalg.norm(vector_b)
    if norm_a < NUMERICAL_EPS or norm_b < NUMERICAL_EPS:
        return 0.0
    cosine = float(np.dot(vector_a, vector_b) / (norm_a * norm_b))
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def _observation_geometry_ok(
    case: RevisitCase,
    target: Target,
    state_eci_m_mps: np.ndarray,
    state_ecef_m_mps: np.ndarray,
    epoch: brahe.Epoch,
) -> bool:
    sensor = case.satellite_model.sensor
    target_ecef_m = np.asarray(target.ecef_position_m, dtype=float)
    relative_enz = np.asarray(
        brahe.relative_position_ecef_to_enz(
            target_ecef_m,
            state_ecef_m_mps[:3],
            brahe.EllipsoidalConversionType.GEODETIC,
        ),
        dtype=float,
    )
    azelr = np.asarray(
        brahe.position_enz_to_azel(relative_enz, brahe.AngleFormat.DEGREES),
        dtype=float,
    )
    elevation_deg = float(azelr[1])
    slant_range_m = float(azelr[2])
    if elevation_deg < target.min_elevation_deg - NUMERICAL_EPS:
        return False
    if slant_range_m > target.max_slant_range_m + NUMERICAL_EPS:
        return False
    if slant_range_m > sensor.max_range_m + NUMERICAL_EPS:
        return False

    target_eci_m = np.asarray(brahe.position_ecef_to_eci(epoch, target_ecef_m), dtype=float)
    line_of_sight = target_eci_m - state_eci_m_mps[:3]
    nadir = -state_eci_m_mps[:3]
    off_nadir_deg = _angle_between_deg(nadir, line_of_sight)
    return off_nadir_deg <= sensor.max_off_nadir_angle_deg + NUMERICAL_EPS


def build_visibility_matrix(
    case: RevisitCase,
    slots: tuple[OrbitSlot, ...],
    samples: tuple[TimeSample, ...],
) -> VisibilityMatrix:
    ensure_brahe_ready()
    start_epoch = datetime_to_epoch(case.horizon_start)
    end_epoch = datetime_to_epoch(case.horizon_end)
    config = force_model_config()
    visible: set[tuple[int, int, int]] = set()
    targets = case.targets

    for slot_index, slot in enumerate(slots):
        propagator = brahe.NumericalOrbitPropagator.from_eci(
            start_epoch,
            np.asarray(slot.state_eci_m_mps, dtype=float),
            force_config=config,
        )
        propagator.propagate_to(end_epoch)
        for sample in samples:
            epoch = datetime_to_epoch(sample.instant)
            state_eci = np.asarray(propagator.state_eci(epoch), dtype=float)
            state_ecef = np.asarray(propagator.state_ecef(epoch), dtype=float)
            for target_index, target in enumerate(targets):
                if _observation_geometry_ok(case, target, state_eci, state_ecef, epoch):
                    visible.add((sample.index, slot_index, target_index))

    return VisibilityMatrix(
        shape=(len(samples), len(slots), len(targets)),
        visible=frozenset(visible),
    )


def visibility_to_sparse_records(matrix: VisibilityMatrix) -> dict[str, object]:
    return {
        "shape": list(matrix.shape),
        "visible_count": matrix.visible_count,
        "density": matrix.density,
        "entries": [
            {"time_index": t, "slot_index": j, "target_index": p}
            for t, j, p in sorted(matrix.visible)
        ],
    }


def target_visibility_counts(
    matrix: VisibilityMatrix, targets: tuple[Target, ...]
) -> dict[str, int]:
    counts = {target.target_id: 0 for target in targets}
    for _, _, target_index in matrix.visible:
        counts[targets[target_index].target_id] += 1
    return counts

