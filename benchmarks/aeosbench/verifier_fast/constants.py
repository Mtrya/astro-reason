"""Physical and simulation constants for AEOS-Bench verifier.

The simulation uses a spherical Earth model.
"""

import math

# Earth model (spherical, NOT WGS84)
RADIUS_EARTH = 6_378_136.6  # meters
ECCENTRICITY_EARTH = 0.0  # spherical Earth
MU_EARTH = 3.986004360e14  # m³/s² (gravitational parameter)

# Simulation parameters
INTERVAL = 1.0  # seconds between timesteps
MAX_TIME_STEP = 3600  # last timestep index (0-indexed), total = 3601 timesteps
NUM_TIMESTEPS = MAX_TIME_STEP + 1  # 3601

# Epoch: 2019-01-01 00:00:00 UTC
EPOCH_YEAR = 2019
EPOCH_MONTH = 1
EPOCH_DAY = 1
EPOCH_HOUR = 0
EPOCH_MINUTE = 0
EPOCH_SECOND = 0

# Unit conversions
RPM_TO_RAD_PER_SEC = 2.0 * math.pi / 60.0
