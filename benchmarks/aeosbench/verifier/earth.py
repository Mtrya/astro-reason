"""Earth rotation matrices for ECI↔ECEF conversion.

Computes rotation matrices at each timestep using brahe's IAU reduction.
"""

from __future__ import annotations

import numpy as np
import brahe as bh

from .constants import NUM_TIMESTEPS
from .orbit import make_epoch, _init_eop


def compute_ecef_to_eci_rotations() -> np.ndarray:
    """Compute ECEF-to-ECI rotation matrices for all 3601 timesteps.

    Returns:
        ndarray of shape (3601, 3, 3) where R[t] transforms ECEF → ECI.
    """
    _init_eop()
    epoch = make_epoch()

    rotations = np.empty((NUM_TIMESTEPS, 3, 3), dtype=np.float64)
    for t in range(NUM_TIMESTEPS):
        ep = epoch + float(t)
        # brahe returns ECI→ECEF; transpose for ECEF→ECI
        r_eci_to_ecef = bh.rotation_eci_to_ecef(ep)
        rotations[t] = r_eci_to_ecef.T

    return rotations
