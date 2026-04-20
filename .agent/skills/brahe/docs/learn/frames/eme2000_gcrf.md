# EME2000 ↔ GCRF Transformations

The EME2000 (Earth Mean Equator and Equinox of J2000.0) to GCRF (Geocentric Celestial Reference Frame) transformation accounts for the frame bias between the classical J2000.0 reference frame and the modern ICRS-aligned GCRF.

**When to Use EME2000**
EME2000 should primarily be used when:

- Working with older systems or datasets that use EME2000 coordinates
- Interfacing with software that requires EME2000 input/output
- Comparing results with historical analyses performed in EME2000

For new applications, **use GCRF as your standard inertial frame**. GCRF is the current IAU/IERS standard and provides the most accurate representation of an inertial reference frame.


## Reference Frames

### EME2000 (Earth Mean Equator and Equinox of J2000.0)

EME2000, also known as J2000.0, is the classical inertial reference frame defined by the mean equator and mean equinox of the Earth at the J2000.0 epoch (January 1, 2000, 12:00 TT). This frame was widely used in older astrodynamics systems and is still found in many datasets and applications.

Key characteristics:

- Inertial frame (non-rotating)
- Defined using the mean equator and equinox at J2000.0
- Origin at Earth's center of mass

### Geocentric Celestial Reference Frame (GCRF)

The GCRF is the modern standard inertial reference frame, aligned with the International Celestial Reference System (ICRS). It is realized using observations of distant quasars and represents the current best realization of an inertial frame.

Key characteristics:

- Inertial frame (non-rotating)
- ICRS-aligned (quasi-inertial with respect to distant objects)
- Origin at Earth's center of mass
- Standard frame for modern astrodynamics applications

## Frame Bias

The transformation between EME2000 and GCRF is a **constant frame bias** that does not vary with time. This bias accounts for the small offset between the J2000.0 mean equator/equinox and the ICRS alignment arising from the improved observational data used to define the ICRS.

The bias is very small (on the order of milliarcseconds) but can matter for high-precision applications.

**Time Independence**

Unlike GCRF ↔ ITRF transformations, which are time-dependent and require Earth Orientation Parameters, the EME2000 ↔ GCRF transformation is **constant** and does not require an epoch parameter. The transformation is the same at all times.

## EME2000 to GCRF

Transform coordinates from the EME2000 frame to the modern GCRF.

### State Vector

Transform a complete state vector (position and velocity) from EME2000 to GCRF:


```python
import brahe as bh
import numpy as np

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

# Convert to EME2000 Cartesian state
# Note: state_koe_to_eci produces EME2000 states by default
state_eme2000 = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

print("EME2000 state vector:")
print(
    f"  Position: [{state_eme2000[0]:.3f}, {state_eme2000[1]:.3f}, {state_eme2000[2]:.3f}] m"
)
print(
    f"  Velocity: [{state_eme2000[3]:.6f}, {state_eme2000[4]:.6f}, {state_eme2000[5]:.6f}] m/s\n"
)

# Transform to GCRF (constant transformation, no epoch needed)
state_gcrf = bh.state_eme2000_to_gcrf(state_eme2000)

print("GCRF state vector:")
print(f"  Position: [{state_gcrf[0]:.3f}, {state_gcrf[1]:.3f}, {state_gcrf[2]:.3f}] m")
print(
    f"  Velocity: [{state_gcrf[3]:.6f}, {state_gcrf[4]:.6f}, {state_gcrf[5]:.6f}] m/s\n"
)

# Transform back to EME2000 to verify round-trip
state_eme2000_back = bh.state_gcrf_to_eme2000(state_gcrf)

print("EME2000 state vector (transformed from GCRF):")
print(
    f"  Position: [{state_eme2000_back[0]:.3f}, {state_eme2000_back[1]:.3f}, {state_eme2000_back[2]:.3f}] m"
)
print(
    f"  Velocity: [{state_eme2000_back[3]:.6f}, {state_eme2000_back[4]:.6f}, {state_eme2000_back[5]:.6f}] m/s\n"
)

diff_pos = np.linalg.norm(state_eme2000[0:3] - state_eme2000_back[0:3])
diff_vel = np.linalg.norm(state_eme2000[3:6] - state_eme2000_back[3:6])
print("Round-trip error:")
print(f"  Position: {diff_pos:.6e} m")
print(f"  Velocity: {diff_vel:.6e} m/s")
print("\nNote: Transformation is constant (time-independent, no epoch needed)")
```


**Velocity Transformation**
Because the transformation does not vary with time, velocity vectors are directly rotated without additional correction terms. There is no time-varying rotation rate to account for.

### Position Vector

Transform a position vector from EME2000 to GCRF:


```python
import brahe as bh
import numpy as np

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

# Convert to EME2000 Cartesian state and extract position
state_eme2000 = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)
pos_eme2000 = state_eme2000[0:3]

print("Position in EME2000:")
print(f"  [{pos_eme2000[0]:.3f}, {pos_eme2000[1]:.3f}, {pos_eme2000[2]:.3f}] m\n")

# Transform to GCRF (constant transformation, no epoch needed)
pos_gcrf = bh.position_eme2000_to_gcrf(pos_eme2000)

print("Position in GCRF:")
print(f"  [{pos_gcrf[0]:.3f}, {pos_gcrf[1]:.3f}, {pos_gcrf[2]:.3f}] m\n")

R_eme2000_to_gcrf = bh.rotation_eme2000_to_gcrf()
pos_gcrf_matrix = R_eme2000_to_gcrf @ pos_eme2000

print("Position in GCRF (using rotation matrix):")
print(
    f"  [{pos_gcrf_matrix[0]:.3f}, {pos_gcrf_matrix[1]:.3f}, {pos_gcrf_matrix[2]:.3f}] m\n"
)

diff = np.linalg.norm(pos_gcrf - pos_gcrf_matrix)
print(f"Difference between methods: {diff:.6e} m")
print("\nNote: Transformation is constant (time-independent, no epoch needed)")
```


### Rotation Matrix

Get the constant rotation matrix from EME2000 to GCRF:


```python
import brahe as bh
import numpy as np

# Get constant rotation matrix from EME2000 to GCRF
R_eme2000_to_gcrf = bh.rotation_eme2000_to_gcrf()

print("EME2000 to GCRF rotation matrix:")
print(
    f"  [{R_eme2000_to_gcrf[0, 0]:13.10f}, {R_eme2000_to_gcrf[0, 1]:13.10f}, {R_eme2000_to_gcrf[0, 2]:13.10f}]"
)
print(
    f"  [{R_eme2000_to_gcrf[1, 0]:13.10f}, {R_eme2000_to_gcrf[1, 1]:13.10f}, {R_eme2000_to_gcrf[1, 2]:13.10f}]"
)
print(
    f"  [{R_eme2000_to_gcrf[2, 0]:13.10f}, {R_eme2000_to_gcrf[2, 1]:13.10f}, {R_eme2000_to_gcrf[2, 2]:13.10f}]\n"
)

identity = R_eme2000_to_gcrf @ R_eme2000_to_gcrf.T
print("Verify orthonormality (R @ R^T should be identity):")
print(f"  Max deviation from identity: {np.max(np.abs(identity - np.eye(3))):.2e}\n")

# Define orbital elements for testing transformation
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

# Convert to EME2000 Cartesian state and extract position
state_eme2000 = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)
pos_eme2000 = state_eme2000[0:3]

print("Satellite position in EME2000:")
print(f"  [{pos_eme2000[0]:.3f}, {pos_eme2000[1]:.3f}, {pos_eme2000[2]:.3f}] m\n")

# Transform using rotation matrix
pos_gcrf_matrix = R_eme2000_to_gcrf @ pos_eme2000

print("Satellite position in GCRF (using rotation matrix):")
print(
    f"  [{pos_gcrf_matrix[0]:.3f}, {pos_gcrf_matrix[1]:.3f}, {pos_gcrf_matrix[2]:.3f}] m"
)

pos_gcrf_direct = bh.position_eme2000_to_gcrf(pos_eme2000)
print("\nSatellite position in GCRF (using position_eme2000_to_gcrf):")
print(
    f"  [{pos_gcrf_direct[0]:.3f}, {pos_gcrf_direct[1]:.3f}, {pos_gcrf_direct[2]:.3f}] m"
)

diff = np.linalg.norm(pos_gcrf_matrix - pos_gcrf_direct)
print(f"\nDifference between methods: {diff:.6e} m")
print("\nNote: Frame bias is constant (same at all epochs)")
```


## GCRF to EME2000

Transform coordinates from the modern GCRF to the older EME2000 frame.

### State Vector

Transform a complete state vector (position and velocity) from GCRF to EME2000:


```python
import brahe as bh
import numpy as np

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

# Convert to EME2000 state, then transform to GCRF
# (Starting in EME2000 to get GCRF representation)
state_eme2000_orig = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)
state_gcrf = bh.state_eme2000_to_gcrf(state_eme2000_orig)

print("GCRF state vector:")
print(f"  Position: [{state_gcrf[0]:.3f}, {state_gcrf[1]:.3f}, {state_gcrf[2]:.3f}] m")
print(
    f"  Velocity: [{state_gcrf[3]:.6f}, {state_gcrf[4]:.6f}, {state_gcrf[5]:.6f}] m/s\n"
)

# Transform to EME2000 (constant transformation, no epoch needed)
state_eme2000 = bh.state_gcrf_to_eme2000(state_gcrf)

print("EME2000 state vector:")
print(
    f"  Position: [{state_eme2000[0]:.3f}, {state_eme2000[1]:.3f}, {state_eme2000[2]:.3f}] m"
)
print(
    f"  Velocity: [{state_eme2000[3]:.6f}, {state_eme2000[4]:.6f}, {state_eme2000[5]:.6f}] m/s\n"
)

# Transform back to GCRF to verify round-trip
state_gcrf_back = bh.state_eme2000_to_gcrf(state_eme2000)

print("GCRF state vector (transformed from EME2000):")
print(
    f"  Position: [{state_gcrf_back[0]:.3f}, {state_gcrf_back[1]:.3f}, {state_gcrf_back[2]:.3f}] m"
)
print(
    f"  Velocity: [{state_gcrf_back[3]:.6f}, {state_gcrf_back[4]:.6f}, {state_gcrf_back[5]:.6f}] m/s\n"
)

diff_pos = np.linalg.norm(state_gcrf[0:3] - state_gcrf_back[0:3])
diff_vel = np.linalg.norm(state_gcrf[3:6] - state_gcrf_back[3:6])
print("Round-trip error:")
print(f"  Position: {diff_pos:.6e} m")
print(f"  Velocity: {diff_vel:.6e} m/s")
print("\nNote: Transformation is constant (time-independent, no epoch needed)")
```


### Position Vector

Transform a position vector from GCRF to EME2000:


```python
import brahe as bh
import numpy as np

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

# Convert to EME2000 state, transform to GCRF, and extract position
state_eme2000 = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)
state_gcrf = bh.state_eme2000_to_gcrf(state_eme2000)
pos_gcrf = state_gcrf[0:3]

print("Position in GCRF:")
print(f"  [{pos_gcrf[0]:.3f}, {pos_gcrf[1]:.3f}, {pos_gcrf[2]:.3f}] m\n")

# Transform to EME2000 (constant transformation, no epoch needed)
pos_eme2000 = bh.position_gcrf_to_eme2000(pos_gcrf)

print("Position in EME2000:")
print(f"  [{pos_eme2000[0]:.3f}, {pos_eme2000[1]:.3f}, {pos_eme2000[2]:.3f}] m\n")

R_gcrf_to_eme2000 = bh.rotation_gcrf_to_eme2000()
pos_eme2000_matrix = R_gcrf_to_eme2000 @ pos_gcrf

print("Position in EME2000 (using rotation matrix):")
print(
    f"  [{pos_eme2000_matrix[0]:.3f}, {pos_eme2000_matrix[1]:.3f}, {pos_eme2000_matrix[2]:.3f}] m\n"
)

diff = np.linalg.norm(pos_eme2000 - pos_eme2000_matrix)
print(f"Difference between methods: {diff:.6e} m")
print("\nNote: Transformation is constant (time-independent, no epoch needed)")
```


### Rotation Matrix

Get the constant rotation matrix from GCRF to EME2000:


```python
import brahe as bh
import numpy as np

# Get constant rotation matrix from GCRF to EME2000
R_gcrf_to_eme2000 = bh.rotation_gcrf_to_eme2000()

print("GCRF to EME2000 rotation matrix:")
print(
    f"  [{R_gcrf_to_eme2000[0, 0]:13.10f}, {R_gcrf_to_eme2000[0, 1]:13.10f}, {R_gcrf_to_eme2000[0, 2]:13.10f}]"
)
print(
    f"  [{R_gcrf_to_eme2000[1, 0]:13.10f}, {R_gcrf_to_eme2000[1, 1]:13.10f}, {R_gcrf_to_eme2000[1, 2]:13.10f}]"
)
print(
    f"  [{R_gcrf_to_eme2000[2, 0]:13.10f}, {R_gcrf_to_eme2000[2, 1]:13.10f}, {R_gcrf_to_eme2000[2, 2]:13.10f}]\n"
)

R_eme2000_to_gcrf = bh.rotation_eme2000_to_gcrf()
print("Verification: R_gcrf_to_eme2000 = R_eme2000_to_gcrf^T")
print(
    f"  Max difference: {np.max(np.abs(R_gcrf_to_eme2000 - R_eme2000_to_gcrf.T)):.2e}\n"
)
# Verification: R_gcrf_to_eme2000 = R_eme2000_to_gcrf^T

identity = R_gcrf_to_eme2000 @ R_gcrf_to_eme2000.T
print("Verify orthonormality (R @ R^T should be identity):")
print(f"  Max deviation from identity: {np.max(np.abs(identity - np.eye(3))):.2e}\n")

# Define orbital elements for testing transformation
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

# Convert to EME2000, transform to GCRF, and extract position
state_eme2000 = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)
state_gcrf = bh.state_eme2000_to_gcrf(state_eme2000)
pos_gcrf = state_gcrf[0:3]

print("Satellite position in GCRF:")
print(f"  [{pos_gcrf[0]:.3f}, {pos_gcrf[1]:.3f}, {pos_gcrf[2]:.3f}] m\n")

# Transform using rotation matrix
pos_eme2000_matrix = R_gcrf_to_eme2000 @ pos_gcrf

print("Satellite position in EME2000 (using rotation matrix):")
print(
    f"  [{pos_eme2000_matrix[0]:.3f}, {pos_eme2000_matrix[1]:.3f}, {pos_eme2000_matrix[2]:.3f}] m"
)

pos_eme2000_direct = bh.position_gcrf_to_eme2000(pos_gcrf)
print("\nSatellite position in EME2000 (using position_gcrf_to_eme2000):")
print(
    f"  [{pos_eme2000_direct[0]:.3f}, {pos_eme2000_direct[1]:.3f}, {pos_eme2000_direct[2]:.3f}] m"
)

diff = np.linalg.norm(pos_eme2000_matrix - pos_eme2000_direct)
print(f"\nDifference between methods: {diff:.6e} m")
print("\nNote: Frame bias is constant (same at all epochs)")
```


## Frame Bias Matrix

The underlying frame bias transformation can also be accessed directly:


```python
import brahe as bh

# Get the EME2000 frame bias matrix
B = bh.bias_eme2000()

print("EME2000 frame bias matrix:")
print(f"  [{B[0, 0]:13.10f}, {B[0, 1]:13.10f}, {B[0, 2]:13.10f}]")
print(f"  [{B[1, 0]:13.10f}, {B[1, 1]:13.10f}, {B[1, 2]:13.10f}]")
print(f"  [{B[2, 0]:13.10f}, {B[2, 1]:13.10f}, {B[2, 2]:13.10f}]\n")
```


The bias matrix is identical to `rotation_gcrf_to_eme2000()` and represents the constant transformation from GCRF to EME2000.

## See Also

- [GCRF ↔ ITRF Transformations](gcrf_itrf.md) - Time-dependent transformations between inertial and Earth-fixed frames
- [Reference Frames Overview](index.md) - Complete overview of all reference frames in Brahe