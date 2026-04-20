# ECI ↔ ECEF Transformations

The ECI (Earth-Centered Inertial) and ECEF (Earth-Centered Earth-Fixed) naming convention is a traditional and widely-used terminology in the astrodynamics community.

**Naming Convention**

Brahe provides two sets of function names for frame transformations, both currently mapping to the same underlying implementations:

- **ECI/ECEF naming**: Common coordinate system names (e.g., `rotation_eci_to_ecef`, `state_eci_to_ecef`)
- **GCRF/ITRF naming**: Explicit reference frame names (e.g., `rotation_gcrf_to_itrf`, `state_gcrf_to_itrf`)

The ECI/ECEF naming will always use the "best" available transformations in Brahe, while the GCRF/ITRF naming ensures consistent use of specific reference frame implementations.


## Reference Frames

### ECI (Earth-Centered Inertial)

- A non-rotating frame fixed with respect to distant stars
- Inertial frame suitable for integration of equations of motion
- **Current Realization**: GCRF (Geocentric Celestial Reference Frame)

### ECEF (Earth-Centered Earth-Fixed)

- A rotating frame fixed to the Earth's surface
- Ideal for computing positions and motions relative to terrestrial locations and observers
- **Current Realization**: ITRF (International Terrestrial Reference Frame)

## ECI to ECEF

Converting from ECI to ECEF accounts for the Earth's rotation, polar motion, and precession-nutation effects. These transformations are time-dependent and require Earth Orientation Parameters (EOP) for high accuracy. The transformations will use the currently loaded Earth orientation data provider to obtain the necessary parameters automatically. See [Earth Orientation Data](../eop/index.md) for more details.

### State Vector

Transform a complete state vector (position and velocity) from ECI to ECEF:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define orbital elements in degrees
# LEO satellite: 500 km altitude, sun-synchronous orbit
oe = np.array(
    [
        bh.R_EARTH + 500e3,  # Semi-major axis (m)
        0.01,  # Eccentricity
        97.8,  # Inclination (deg)
        15.0,  # Right ascension of ascending node (deg)
        30.0,  # Argument of periapsis (deg)
        45.0,  # Mean anomaly (deg)
    ]
)

print("Orbital elements (degrees):")
print(f"  a    = {oe[0]:.3f} m = {(oe[0] - bh.R_EARTH) / 1e3:.1f} km altitude")
print(f"  e    = {oe[1]:.4f}")
print(f"  i    = {oe[2]:.4f}°")
print(f"  Ω    = {oe[3]:.4f}°")
print(f"  ω    = {oe[4]:.4f}°")
print(f"  M    = {oe[5]:.4f}°\n")

epc = bh.Epoch(2024, 1, 1, 12, 0, 0.0, time_system=bh.UTC)
print(f"Epoch: {epc}")

# Convert to ECI Cartesian state
state_eci = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

print("ECI state vector:")
print(f"  Position: [{state_eci[0]:.3f}, {state_eci[1]:.3f}, {state_eci[2]:.3f}] m")
print(f"  Velocity: [{state_eci[3]:.6f}, {state_eci[4]:.6f}, {state_eci[5]:.6f}] m/s\n")

# Transform to ECEF at specific epoch
state_ecef = bh.state_eci_to_ecef(epc, state_eci)

print("\nECEF state vector:")
print(f"  Position: [{state_ecef[0]:.3f}, {state_ecef[1]:.3f}, {state_ecef[2]:.3f}] m")
print(
    f"  Velocity: [{state_ecef[3]:.6f}, {state_ecef[4]:.6f}, {state_ecef[5]:.6f}] m/s"
)
```


**Velocity Transformation**
Simply rotating velocity vectors will not yield correct velocity components in the ECEF frame due to the Earth's rotation. State vector transformation functions properly account for observed velocity changes in the ECEF frame due to Earth's rotation.

### Rotation Matrix

Get the rotation matrix from ECI to ECEF:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define epoch
epc = bh.Epoch(2024, 1, 1, 12, 0, 0.0, time_system=bh.UTC)

# Get rotation matrix from ECI to ECEF
R_eci_to_ecef = bh.rotation_eci_to_ecef(epc)

print(f"Epoch: {epc}")
print("\nECI to ECEF rotation matrix:")
print(
    f"  [{R_eci_to_ecef[0, 0]:10.7f}, {R_eci_to_ecef[0, 1]:10.7f}, {R_eci_to_ecef[0, 2]:10.7f}]"
)
print(
    f"  [{R_eci_to_ecef[1, 0]:10.7f}, {R_eci_to_ecef[1, 1]:10.7f}, {R_eci_to_ecef[1, 2]:10.7f}]"
)
print(
    f"  [{R_eci_to_ecef[2, 0]:10.7f}, {R_eci_to_ecef[2, 1]:10.7f}, {R_eci_to_ecef[2, 2]:10.7f}]\n"
)

# Define orbital elements in degrees for satellite position
oe = np.array(
    [
        bh.R_EARTH + 500e3,  # Semi-major axis (m)
        0.01,  # Eccentricity
        97.8,  # Inclination (deg)
        15.0,  # RAAN (deg)
        30.0,  # Argument of periapsis (deg)
        45.0,  # Mean anomaly (deg)
    ]
)

# Convert to ECI Cartesian state and extract position
state_eci = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)
pos_eci = state_eci[0:3]

print("Position in ECI:")
print(f"  [{pos_eci[0]:.3f}, {pos_eci[1]:.3f}, {pos_eci[2]:.3f}] m\n")

# Transform position using rotation matrix
pos_ecef = R_eci_to_ecef @ pos_eci

print("Position in ECEF (using rotation matrix):")
print(f"  [{pos_ecef[0]:.3f}, {pos_ecef[1]:.3f}, {pos_ecef[2]:.3f}] m")

pos_ecef_direct = bh.position_eci_to_ecef(epc, pos_eci)
print("\nPosition in ECEF (using position_eci_to_ecef):")
print(
    f"  [{pos_ecef_direct[0]:.3f}, {pos_ecef_direct[1]:.3f}, {pos_ecef_direct[2]:.3f}] m"
)
```


## ECEF to ECI

Converting from ECEF to ECI reverses the transformation, converting Earth-fixed coordinates back to the inertial frame.

### State Vector

Transform a complete state vector (position and velocity) from ECEF to ECI:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define orbital elements in degrees
# LEO satellite: 500 km altitude, sun-synchronous orbit
oe = np.array(
    [
        bh.R_EARTH + 500e3,  # Semi-major axis (m)
        0.01,  # Eccentricity
        97.8,  # Inclination (deg)
        15.0,  # Right ascension of ascending node (deg)
        30.0,  # Argument of periapsis (deg)
        45.0,  # Mean anomaly (deg)
    ]
)

print("Orbital elements (degrees):")
print(f"  a    = {oe[0]:.3f} m = {(oe[0] - bh.R_EARTH) / 1e3:.1f} km altitude")
print(f"  e    = {oe[1]:.4f}")
print(f"  i    = {oe[2]:.4f}°")
print(f"  Ω    = {oe[3]:.4f}°")
print(f"  ω    = {oe[4]:.4f}°")
print(f"  M    = {oe[5]:.4f}°\n")

# Convert to ECI Cartesian state
state_eci = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

# Define epoch
epc = bh.Epoch(2024, 1, 1, 12, 0, 0.0, time_system=bh.UTC)
print(f"Epoch: {epc}")
print("ECI state vector:")
print(f"  Position: [{state_eci[0]:.3f}, {state_eci[1]:.3f}, {state_eci[2]:.3f}] m")
print(f"  Velocity: [{state_eci[3]:.6f}, {state_eci[4]:.6f}, {state_eci[5]:.6f}] m/s\n")

# Transform to ECEF
state_ecef = bh.state_eci_to_ecef(epc, state_eci)

print("ECEF state vector:")
print(f"  Position: [{state_ecef[0]:.3f}, {state_ecef[1]:.3f}, {state_ecef[2]:.3f}] m")
print(
    f"  Velocity: [{state_ecef[3]:.6f}, {state_ecef[4]:.6f}, {state_ecef[5]:.6f}] m/s\n"
)

# Transform back to ECI
state_eci_back = bh.state_ecef_to_eci(epc, state_ecef)

print("\nECI state vector (transformed from ECEF):")
print(
    f"  Position: [{state_eci_back[0]:.3f}, {state_eci_back[1]:.3f}, {state_eci_back[2]:.3f}] m"
)
print(
    f"  Velocity: [{state_eci_back[3]:.6f}, {state_eci_back[4]:.6f}, {state_eci_back[5]:.6f}] m/s"
)

diff_pos = np.linalg.norm(state_eci[0:3] - state_eci_back[0:3])
diff_vel = np.linalg.norm(state_eci[3:6] - state_eci_back[3:6])
print("\nRound-trip error:")
print(f"  Position: {diff_pos:.6e} m")
print(f"  Velocity: {diff_vel:.6e} m/s")
```


**Velocity Transformation**
Simply rotating velocity vectors will not yield correct velocity components in the ECI frame due to the Earth's rotation. State vector transformation functions properly account for observed velocity changes when transforming from the rotating ECEF frame.

### Rotation Matrix

Get the rotation matrix from ECEF to ECI:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define epoch
epc = bh.Epoch(2024, 1, 1, 12, 0, 0.0, time_system=bh.UTC)

# Get rotation matrix from ECEF to ECI
R_ecef_to_eci = bh.rotation_ecef_to_eci(epc)

print(f"Epoch: {epc.to_datetime()}")
print("\nECEF to ECI rotation matrix:")
print(
    f"  [{R_ecef_to_eci[0, 0]:10.7f}, {R_ecef_to_eci[0, 1]:10.7f}, {R_ecef_to_eci[0, 2]:10.7f}]"
)
print(
    f"  [{R_ecef_to_eci[1, 0]:10.7f}, {R_ecef_to_eci[1, 1]:10.7f}, {R_ecef_to_eci[1, 2]:10.7f}]"
)
print(
    f"  [{R_ecef_to_eci[2, 0]:10.7f}, {R_ecef_to_eci[2, 1]:10.7f}, {R_ecef_to_eci[2, 2]:10.7f}]\n"
)

R_eci_to_ecef = bh.rotation_eci_to_ecef(epc)
print("Verification: R_ecef_to_eci = R_eci_to_ecef^T")
print(f"  Max difference: {np.max(np.abs(R_ecef_to_eci - R_eci_to_ecef.T)):.2e}\n")

# Define orbital elements in degrees for satellite position
oe = np.array(
    [
        bh.R_EARTH + 500e3,  # Semi-major axis (m)
        0.01,  # Eccentricity
        97.8,  # Inclination (deg)
        15.0,  # RAAN (deg)
        30.0,  # Argument of periapsis (deg)
        45.0,  # Mean anomaly (deg)
    ]
)

# Convert to ECI Cartesian state and extract position
state_eci = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

# Transform to ECEF
pos_ecef = bh.position_eci_to_ecef(epc, state_eci[0:3])

print("Satellite position in ECEF:")
print(f"  [{pos_ecef[0]:.3f}, {pos_ecef[1]:.3f}, {pos_ecef[2]:.3f}] m\n")

# Transform back to ECI using rotation matrix
pos_eci = R_ecef_to_eci @ pos_ecef

print("Satellite position in ECI (using rotation matrix):")
print(f"  [{pos_eci[0]:.3f}, {pos_eci[1]:.3f}, {pos_eci[2]:.3f}] m")

pos_eci_direct = bh.position_ecef_to_eci(epc, pos_ecef)
print("\nSatellite position in ECI (using position_ecef_to_eci):")
print(
    f"  [{pos_eci_direct[0]:.3f}, {pos_eci_direct[1]:.3f}, {pos_eci_direct[2]:.3f}] m"
)
```


## See Also

- [GCRF ↔ ITRF Transformations](gcrf_itrf.md) - Detailed documentation of the underlying reference frame implementations
- [Reference Frames Overview](index.md) - Complete overview of all reference frames in Brahe