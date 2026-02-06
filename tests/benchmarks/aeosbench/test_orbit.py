"""Tests for AEOS-Bench orbit propagation against Basilisk ground-truth fixtures.

Verifies that brahe's NumericalOrbitPropagator (point-mass Earth + Sun third-body,
RK4 1s fixed step) reproduces Basilisk's orbit propagation to high accuracy.

Residual error (~0.2m position) is expected and comes from Basilisk integrating
coupled translational+rotational+reaction-wheel dynamics as one system, while we
propagate translational dynamics independently. This is architecturally inherent
and negligible for visibility computation (0.2m at ~7000km ≈ 0.002 arcsec).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from benchmarks.aeosbench.verifier.models import load_constellation
from benchmarks.aeosbench.verifier.orbit import propagate_constellation

FIXTURES = Path("tests/fixtures/aeosbench_fixtures")

# Load all case IDs from index
with open(FIXTURES / "index.json") as f:
    _INDEX = json.load(f)
    ALL_CASE_IDS = [str(f["case_id"]) for f in _INDEX["fixtures"]]

# Tolerances
# Position: ~0.2m residual from coupled dynamics mismatch (see module docstring)
POS_MAX_TOL = 0.5    # meters — max error over full 3601 timesteps
POS_MEAN_TOL = 0.2   # meters — mean error over full 3601 timesteps
VEL_MAX_TOL = 0.001  # m/s
VEL_MEAN_TOL = 0.001 # m/s


def _case_id_to_dir(case_id: str) -> str:
    """Convert case ID (e.g., '157') to directory name (e.g., '00157')."""
    return case_id.zfill(5)


@pytest.fixture(scope="module")
def case_157_constellation():
    return load_constellation(FIXTURES / "cases" / "00157" / "constellation.json")


@pytest.fixture(scope="module")
def case_157_states(case_157_constellation):
    return propagate_constellation(case_157_constellation)


@pytest.fixture(scope="module")
def case_157_curves():
    with open(FIXTURES / "curves" / "00157.json") as f:
        return json.load(f)


class TestOrbitPropagationShape:
    """Verify basic shape and structure of propagated states."""

    def test_all_satellites_propagated(self, case_157_constellation, case_157_states):
        expected_ids = {sat.id for sat in case_157_constellation.satellites}
        assert set(case_157_states.keys()) == expected_ids

    def test_state_shape(self, case_157_states):
        for sid, states in case_157_states.items():
            assert states.shape == (3602, 6), (
                f"Sat {sid}: expected (3602, 6), got {states.shape}"
            )

    def test_initial_position_magnitude(self, case_157_constellation, case_157_states):
        """Satellites should be in LEO: altitude 500-2000 km above Earth surface."""
        R_EARTH = 6_378_136.6
        for sat in case_157_constellation.satellites:
            pos = case_157_states[sat.id][0, :3]
            r = np.linalg.norm(pos)
            alt = r - R_EARTH
            assert 400_000 < alt < 2_000_000, (
                f"Sat {sat.id}: altitude {alt/1e3:.0f} km outside LEO range"
            )


class TestOrbitPropagationAccuracy:
    """Compare propagated states against Basilisk ground-truth curves.

    Fixture curves[t] records state AFTER propagation at step t,
    which corresponds to our states[t+1] (state at epoch + t + 1).
    """

    def test_position_accuracy_all_satellites(
        self, case_157_constellation, case_157_states, case_157_curves
    ):
        for sat in case_157_constellation.satellites:
            sid = sat.id
            gt_pos = np.array(case_157_curves["satellites"][str(sid)]["position_eci"])
            sim_pos = case_157_states[sid][1:, :3]  # states[1:] aligns with curves[0:]

            pos_errors = np.linalg.norm(sim_pos - gt_pos, axis=1)

            assert pos_errors.max() < POS_MAX_TOL, (
                f"Sat {sid}: max position error {pos_errors.max():.4f} m "
                f"exceeds {POS_MAX_TOL} m (at t={pos_errors.argmax()})"
            )
            assert pos_errors.mean() < POS_MEAN_TOL, (
                f"Sat {sid}: mean position error {pos_errors.mean():.4f} m "
                f"exceeds {POS_MEAN_TOL} m"
            )

    def test_velocity_accuracy_all_satellites(
        self, case_157_constellation, case_157_states, case_157_curves
    ):
        for sat in case_157_constellation.satellites:
            sid = sat.id
            gt_vel = np.array(case_157_curves["satellites"][str(sid)]["velocity_eci"])
            sim_vel = case_157_states[sid][1:, 3:]

            vel_errors = np.linalg.norm(sim_vel - gt_vel, axis=1)

            assert vel_errors.max() < VEL_MAX_TOL, (
                f"Sat {sid}: max velocity error {vel_errors.max():.6f} m/s "
                f"exceeds {VEL_MAX_TOL} m/s"
            )

    def test_initial_state_near_exact(
        self, case_157_constellation, case_157_states, case_157_curves
    ):
        """At t=0 (curves[0] = states[1]), error should be sub-millimeter."""
        for sat in case_157_constellation.satellites:
            sid = sat.id
            gt_pos_0 = np.array(case_157_curves["satellites"][str(sid)]["position_eci"][0])
            sim_pos_1 = case_157_states[sid][1, :3]
            err = np.linalg.norm(sim_pos_1 - gt_pos_0)
            assert err < 0.001, (
                f"Sat {sid}: initial position error {err:.6f} m should be < 1 mm"
            )

    def test_error_does_not_grow_rapidly(
        self, case_157_constellation, case_157_states, case_157_curves
    ):
        """Error at t=3600 should not be drastically larger than at t=1800.

        Without Sun perturbation, error grew ~4m (almost linearly). With Sun, residual
        is ~0.2m and grows much slower. Check that end error < 3x mid error.
        """
        for sat in case_157_constellation.satellites:
            sid = sat.id
            gt_pos = np.array(case_157_curves["satellites"][str(sid)]["position_eci"])
            sim_pos = case_157_states[sid][1:, :3]
            pos_errors = np.linalg.norm(sim_pos - gt_pos, axis=1)

            err_mid = pos_errors[1800]
            err_end = pos_errors[3600]
            assert err_end < 3 * max(err_mid, 0.01), (
                f"Sat {sid}: error at t=3600 ({err_end:.4f} m) is >{3}x "
                f"error at t=1800 ({err_mid:.4f} m) — rapid growth detected"
            )


# ============================================================================
# Parameterized tests for ALL fixtures (20 cases)
# ============================================================================

@pytest.mark.slow
@pytest.mark.parametrize("case_id", ALL_CASE_IDS)
class TestAllCasesOrbitPropagation:
    """Run orbit propagation tests against all 20 fixture cases."""

    @pytest.fixture
    def constellation(self, case_id):
        case_dir = _case_id_to_dir(case_id)
        return load_constellation(FIXTURES / "cases" / case_dir / "constellation.json")

    @pytest.fixture
    def states(self, constellation):
        return propagate_constellation(constellation)

    @pytest.fixture
    def curves(self, case_id):
        case_file = _case_id_to_dir(case_id) + ".json"
        with open(FIXTURES / "curves" / case_file) as f:
            return json.load(f)

    def test_propagation_succeeds(self, states, constellation):
        """All satellites should have states array of correct shape."""
        for sat in constellation.satellites:
            assert sat.id in states
            assert states[sat.id].shape == (3602, 6)

    def test_position_accuracy(self, states, curves, constellation):
        """Position error should be within tolerance for all satellites."""
        for sat in constellation.satellites:
            sid = str(sat.id)
            gt_pos = np.array(curves["satellites"][sid]["position_eci"])
            sim_pos = states[sat.id][1:, :3]

            pos_errors = np.linalg.norm(sim_pos - gt_pos, axis=1)

            assert pos_errors.max() < POS_MAX_TOL, (
                f"Case {constellation.case_id}, Sat {sid}: "
                f"max position error {pos_errors.max():.4f} m exceeds {POS_MAX_TOL} m"
            )

    def test_velocity_accuracy(self, states, curves, constellation):
        """Velocity error should be within tolerance for all satellites."""
        for sat in constellation.satellites:
            sid = str(sat.id)
            gt_vel = np.array(curves["satellites"][sid]["velocity_eci"])
            sim_vel = states[sat.id][1:, 3:]

            vel_errors = np.linalg.norm(sim_vel - gt_vel, axis=1)

            assert vel_errors.max() < VEL_MAX_TOL, (
                f"Case {constellation.case_id}, Sat {sid}: "
                f"max velocity error {vel_errors.max():.6f} m/s exceeds {VEL_MAX_TOL} m/s"
            )

    def test_position_leo_range(self, states, constellation):
        """All satellites should be in LEO altitude range."""
        R_EARTH = 6_378_136.6
        for sat in constellation.satellites:
            pos = states[sat.id][0, :3]
            r = np.linalg.norm(pos)
            alt = r - R_EARTH
            assert 400_000 < alt < 2_000_000, (
                f"Case {constellation.case_id}, Sat {sat.id}: "
                f"altitude {alt/1e3:.0f} km outside LEO range"
            )
