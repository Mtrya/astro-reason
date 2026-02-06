"""Orbit propagation using brahe's numerical propagator.

Uses point-mass Earth gravity + Sun third-body perturbation with RK4 at 1-second fixed steps.
"""

from __future__ import annotations

import numpy as np
import brahe as bh

from .constants import EPOCH_YEAR, EPOCH_MONTH, EPOCH_DAY, NUM_TIMESTEPS
from .models import Constellation, Satellite


def _init_eop():
    """Initialize Earth Orientation Parameters (required for brahe frame rotations)."""
    try:
        eop = bh.FileEOPProvider.from_default_standard(True, "Hold")
        bh.set_global_eop_provider_from_file_provider(eop)
    except Exception:
        pass  # already initialized


def make_epoch() -> bh.Epoch:
    """Create the simulation epoch (2019-01-01 00:00:00 UTC)."""
    return bh.Epoch(EPOCH_YEAR, EPOCH_MONTH, EPOCH_DAY, 0, 0, 0)


def _make_force_config() -> bh.ForceModelConfig:
    """Create force model: point-mass Earth + Sun third-body perturbation.

    Matches Basilisk's configuration:
        grav_body_factory.createEarth()  # point-mass gravity
        grav_body_factory.createSun()     # third-body perturbation
        grav_body_factory.addBodiesTo(spacecraft)
    """
    fc = bh.ForceModelConfig.two_body()
    fc.third_body = bh.ThirdBodyConfiguration(
        bh.EphemerisSource.DE440s, [bh.ThirdBody.SUN]
    )
    return fc


def _make_prop_config() -> bh.NumericalPropagationConfig:
    """Create propagation config: RK4 with 1-second fixed steps.

    Matches Basilisk's default integrator (RK4) with the simulation's
    INTERVAL = 1.0 second task timestep.
    """
    return (
        bh.NumericalPropagationConfig.default()
        .with_method(bh.IntegrationMethod.RK4)
        .with_initial_step(1.0)
        .with_max_step(1.0)
    )


def satellite_initial_eci(sat: Satellite, orbit_elements: dict) -> np.ndarray:
    """Compute initial ECI state [x,y,z,vx,vy,vz] for a satellite.

    Args:
        sat: Satellite dataclass
        orbit_elements: dict with keys: semi_major_axis, eccentricity, inclination,
                        raan, argument_of_perigee (all in degrees for angles)

    Returns:
        numpy array of shape (6,) — [x, y, z, vx, vy, vz] in meters and m/s
    """
    a = orbit_elements["semi_major_axis"]
    e = orbit_elements["eccentricity"]
    inc = orbit_elements["inclination"]
    raan = orbit_elements["raan"]
    argp = orbit_elements["argument_of_perigee"]
    nu = sat.true_anomaly  # degrees

    # Convert true anomaly to mean anomaly
    mean_anom = bh.anomaly_true_to_mean(nu, e, angle_format=bh.AngleFormat.DEGREES)

    # Build Keplerian elements [a, e, i, RAAN, omega, M] in radians
    oe = np.array([
        a, e,
        np.radians(inc),
        np.radians(raan),
        np.radians(argp),
        np.radians(mean_anom),
    ])

    return bh.state_koe_to_eci(oe, bh.AngleFormat.RADIANS)


def propagate_constellation(
    constellation: Constellation,
) -> dict[int, np.ndarray]:
    """Propagate all satellites for 3602 states at 1-second intervals.

    Uses point-mass Earth + Sun third-body with RK4 fixed 1s steps.

    Produces states at epoch+0, epoch+1, ..., epoch+3601.
    - For the simulation loop at step t, visibility uses state[t] (before propagation).

    Returns:
        dict mapping satellite ID to ndarray of shape (3602, 6) with
        [x, y, z, vx, vy, vz] at each time instant.
    """
    _init_eop()
    epoch = make_epoch()
    fc = _make_force_config()
    pc = _make_prop_config()

    # Build orbit lookup
    orbit_map = {}
    for orb in constellation.orbits:
        orbit_map[orb.id] = {
            "semi_major_axis": orb.semi_major_axis,
            "eccentricity": orb.eccentricity,
            "inclination": orb.inclination,
            "raan": orb.raan,
            "argument_of_perigee": orb.argument_of_perigee,
        }

    n_states = NUM_TIMESTEPS + 1  # 3602: epoch+0 through epoch+3601

    results = {}
    for sat in constellation.satellites:
        orb_data = orbit_map[sat.orbit_id]
        state0 = satellite_initial_eci(sat, orb_data)

        # Create numerical propagator with RK4 1s steps
        prop = bh.NumericalOrbitPropagator(epoch, state0, pc, fc)

        # Propagate to epoch+3601
        end_epoch = epoch + float(n_states - 1)
        prop.propagate_to(end_epoch)

        # Extract trajectory states as ECI numpy array
        states_eci = prop.trajectory.to_eci().to_matrix()

        if states_eci.shape[0] != n_states:
            raise RuntimeError(
                f"Satellite {sat.id}: expected {n_states} states, "
                f"got {states_eci.shape[0]}"
            )

        results[sat.id] = states_eci

    return results
