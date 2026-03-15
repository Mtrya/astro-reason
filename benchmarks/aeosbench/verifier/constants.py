"""Physical and simulation constants for AEOS-Bench verifier_bsk.

This mirrors constellation/constants.py + constellation/environments/basilisk/constants.py
"""

import math

# Simulation parameters
TIMESTAMP = '20190101000000'
INTERVAL = 1.0
MAX_TIME_STEP = 3600
NUM_TIMESTEPS = 3601  # 0..3600 inclusive

# Earth model (spherical, NOT WGS84)
RADIUS_EARTH = 6378136.6
MU_EARTH = 398600436000000.0
ECCENTRICITY_EARTH = 0.0

# Common constants used by Basilisk modules
IDENTITY_MATRIX_3 = [1, 0, 0, 0, 1, 0, 0, 0, 1]
UNIT_VECTOR_Z = [0, 0, 1]

# Unit conversions
RPM_TO_RAD_PER_SEC = 2.0 * math.pi / 60.0
