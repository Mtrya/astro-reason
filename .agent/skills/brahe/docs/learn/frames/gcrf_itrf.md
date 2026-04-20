# GCRF ↔ ITRF Transformations

The Geocentric Celestial Reference Frame (GCRF) and International Terrestrial Reference Frame (ITRF) are the modern IAU/IERS standard reference frames for Earth-orbiting satellite applications. 

## Reference Frames

### Geocentric Celestial Reference Frame (GCRF)

The Geocentric Celestial Reference Frame is the standard modern inertial reference frame for Earth-orbiting satellites. It is aligned with the International Celestial Reference Frame (ICRF) and realized using the positions of distant quasars. The GCRF has its origin at the Earth's center of mass and its axes are fixed with respect to distant stars.

The GCRF is an Earth-centered inertial (ECI) frame, meaning it does not rotate with the Earth.

### International Terrestrial Reference Frame (ITRF)

The International Terrestrial Reference Frame is the standard Earth-fixed reference frame maintained by the International Earth Rotation and Reference Systems Service (IERS). The ITRF rotates with the Earth and its axes are aligned with the Earth's geographic coordinate system (polar axis and Greenwich meridian).

The ITRF is an Earth-centered Earth-fixed (ECEF) frame, meaning it rotates with the Earth.

## Transformation Model

Brahe implements the IAU 2006/2000A precession-nutation model with Celestial Intermediate Origin (CIO) based transformation, following IERS conventions. The transformation is accomplished using the IAU 2006/2000A, CIO-based theory using classical angles. The method as described in section 5.5 of the [SOFA C transformation cookbook](https://www.iausofa.org/s/sofa_pn_c.pdf). The transformation accounts for:

- **Precession and nutation** of Earth's rotation axis
- **Earth's rotation** about its instantaneous spin axis
- **Polar motion** and UT1-UTC corrections

These transformations are **time-dependent** and require Earth Orientation Parameters (EOP) for high accuracy. The transformations will use the currently loaded Earth orientation data provider to obtain the necessary parameters automatically. See [Earth Orientation Data](../eop/index.md) for more details.

## GCRF to ITRF

Transform coordinates from the inertial GCRF to the Earth-fixed ITRF.

### State Vector

Transform a complete state vector (position and velocity) from GCRF to ITRF:


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

# Convert to GCRF Cartesian state
state_gcrf = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

print("GCRF state vector:")
print(f"  Position: [{state_gcrf[0]:.3f}, {state_gcrf[1]:.3f}, {state_gcrf[2]:.3f}] m")
print(
    f"  Velocity: [{state_gcrf[3]:.6f}, {state_gcrf[4]:.6f}, {state_gcrf[5]:.6f}] m/s\n"
)

# Transform to ITRF at specific epoch
state_itrf = bh.state_gcrf_to_itrf(epc, state_gcrf)

print("\nITRF state vector:")
print(f"  Position: [{state_itrf[0]:.3f}, {state_itrf[1]:.3f}, {state_itrf[2]:.3f}] m")
print(
    f"  Velocity: [{state_itrf[3]:.6f}, {state_itrf[4]:.6f}, {state_itrf[5]:.6f}] m/s"
)
```


**Velocity Transformation**
Simply rotating velocity vectors will not yield correct velocity components in the ITRF frame due to the Earth's rotation. State vector transformation functions properly account for observed velocity changes in the ITRF frame due to Earth's rotation.

### Rotation Matrix

Get the rotation matrix from GCRF to ITRF:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define epoch
epc = bh.Epoch(2024, 1, 1, 12, 0, 0.0, time_system=bh.UTC)

# Get rotation matrix from GCRF to ITRF
R_gcrf_to_itrf = bh.rotation_gcrf_to_itrf(epc)

print(f"Epoch: {epc}")  # Epoch: 2024-01-01 12:00:00 UTC
print("\nGCRF to ITRF rotation matrix:")
print(
    f"  [{R_gcrf_to_itrf[0, 0]:10.7f}, {R_gcrf_to_itrf[0, 1]:10.7f}, {R_gcrf_to_itrf[0, 2]:10.7f}]"
)
print(
    f"  [{R_gcrf_to_itrf[1, 0]:10.7f}, {R_gcrf_to_itrf[1, 1]:10.7f}, {R_gcrf_to_itrf[1, 2]:10.7f}]"
)
print(
    f"  [{R_gcrf_to_itrf[2, 0]:10.7f}, {R_gcrf_to_itrf[2, 1]:10.7f}, {R_gcrf_to_itrf[2, 2]:10.7f}]\n"
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

# Convert to GCRF Cartesian state and extract position
state_gcrf = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)
pos_gcrf = state_gcrf[0:3]

print("Position in GCRF:")
print(f"  [{pos_gcrf[0]:.3f}, {pos_gcrf[1]:.3f}, {pos_gcrf[2]:.3f}] m\n")

# Transform position using rotation matrix
pos_itrf = R_gcrf_to_itrf @ pos_gcrf

print("Position in ITRF (using rotation matrix):")
print(f"  [{pos_itrf[0]:.3f}, {pos_itrf[1]:.3f}, {pos_itrf[2]:.3f}] m")

pos_itrf_direct = bh.position_gcrf_to_itrf(epc, pos_gcrf)
print("\nPosition in ITRF (using position_gcrf_to_itrf):")
print(
    f"  [{pos_itrf_direct[0]:.3f}, {pos_itrf_direct[1]:.3f}, {pos_itrf_direct[2]:.3f}] m"
)
```


## ITRF to GCRF

Transform coordinates from the Earth-fixed ITRF to the inertial GCRF.

### State Vector

Transform a complete state vector (position and velocity) from ITRF to GCRF:


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

# Convert to GCRF Cartesian state
state_gcrf = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

# Define epoch
epc = bh.Epoch(2024, 1, 1, 12, 0, 0.0, time_system=bh.UTC)
print(f"Epoch: {epc}")
print("GCRF state vector:")
print(f"  Position: [{state_gcrf[0]:.3f}, {state_gcrf[1]:.3f}, {state_gcrf[2]:.3f}] m")
print(
    f"  Velocity: [{state_gcrf[3]:.6f}, {state_gcrf[4]:.6f}, {state_gcrf[5]:.6f}] m/s\n"
)

# Transform to ITRF
state_itrf = bh.state_gcrf_to_itrf(epc, state_gcrf)

print("ITRF state vector:")
print(f"  Position: [{state_itrf[0]:.3f}, {state_itrf[1]:.3f}, {state_itrf[2]:.3f}] m")
print(
    f"  Velocity: [{state_itrf[3]:.6f}, {state_itrf[4]:.6f}, {state_itrf[5]:.6f}] m/s\n"
)

# Transform back to GCRF
state_gcrf_back = bh.state_itrf_to_gcrf(epc, state_itrf)

print("\nGCRF state vector (transformed from ITRF):")
print(
    f"  Position: [{state_gcrf_back[0]:.3f}, {state_gcrf_back[1]:.3f}, {state_gcrf_back[2]:.3f}] m"
)
print(
    f"  Velocity: [{state_gcrf_back[3]:.6f}, {state_gcrf_back[4]:.6f}, {state_gcrf_back[5]:.6f}] m/s"
)

diff_pos = np.linalg.norm(state_gcrf[0:3] - state_gcrf_back[0:3])
diff_vel = np.linalg.norm(state_gcrf[3:6] - state_gcrf_back[3:6])
print("\nRound-trip error:")
print(f"  Position: {diff_pos:.6e} m")
print(f"  Velocity: {diff_vel:.6e} m/s")
```


**Velocity Transformation**
Simply rotating velocity vectors will not yield correct velocity components in the GCRF frame due to the Earth's rotation. State vector transformation functions properly account for observed velocity changes when transforming from the rotating ITRF frame.

### Rotation Matrix

Get the rotation matrix from ITRF to GCRF:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define epoch
epc = bh.Epoch(2024, 1, 1, 12, 0, 0.0, time_system=bh.UTC)

# Get rotation matrix from ITRF to GCRF
R_itrf_to_gcrf = bh.rotation_itrf_to_gcrf(epc)

print(f"Epoch: {epc.to_datetime()}")
print("\nITRF to GCRF rotation matrix:")
print(
    f"  [{R_itrf_to_gcrf[0, 0]:10.7f}, {R_itrf_to_gcrf[0, 1]:10.7f}, {R_itrf_to_gcrf[0, 2]:10.7f}]"
)
print(
    f"  [{R_itrf_to_gcrf[1, 0]:10.7f}, {R_itrf_to_gcrf[1, 1]:10.7f}, {R_itrf_to_gcrf[1, 2]:10.7f}]"
)
print(
    f"  [{R_itrf_to_gcrf[2, 0]:10.7f}, {R_itrf_to_gcrf[2, 1]:10.7f}, {R_itrf_to_gcrf[2, 2]:10.7f}]\n"
)

R_gcrf_to_itrf = bh.rotation_gcrf_to_itrf(epc)
print("Verification: R_itrf_to_gcrf = R_gcrf_to_itrf^T")
print(f"  Max difference: {np.max(np.abs(R_itrf_to_gcrf - R_gcrf_to_itrf.T)):.2e}\n")

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

# Convert to GCRF Cartesian state and extract position
state_gcrf = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

# Transform to ITRF
pos_itrf = bh.position_gcrf_to_itrf(epc, state_gcrf[0:3])

print("Satellite position in ITRF:")
print(f"  [{pos_itrf[0]:.3f}, {pos_itrf[1]:.3f}, {pos_itrf[2]:.3f}] m\n")

# Transform back to GCRF using rotation matrix
pos_gcrf = R_itrf_to_gcrf @ pos_itrf

print("Satellite position in GCRF (using rotation matrix):")
print(f"  [{pos_gcrf[0]:.3f}, {pos_gcrf[1]:.3f}, {pos_gcrf[2]:.3f}] m")

pos_gcrf_direct = bh.position_itrf_to_gcrf(epc, pos_itrf)
print("\nSatellite position in GCRF (using position_itrf_to_gcrf):")
print(
    f"  [{pos_gcrf_direct[0]:.3f}, {pos_gcrf_direct[1]:.3f}, {pos_gcrf_direct[2]:.3f}] m"
)
```


## Intermediate Rotation Matrices

The full GCRF to ITRF transformation is composed of three sequential rotations. Brahe provides access to these intermediate rotation matrices for advanced applications or for understanding the transformation components.

The complete transformation chain is:

```
GCRF ↔ CIRS ↔ TIRS ↔ ITRF
      (BPN)   (ER)   (PM)
```

where:

- **BPN** = Bias-Precession-Nutation: Accounts for Earth's precession and nutation
- **ER** = Earth Rotation: Accounts for Earth's daily rotation
- **PM** = Polar Motion: Accounts for polar motion and UT1-UTC corrections

### Bias-Precession-Nutation Matrix

Get the bias-precession-nutation matrix (GCRF to CIRS):


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define epoch
epc = bh.Epoch(2024, 1, 1, 12, 0, 0.0, time_system=bh.UTC)

# Get BPN matrix (GCRF to CIRS transformation)
R_bpn = bh.bias_precession_nutation(epc)

print(f"Epoch: {epc.to_datetime()}")
print("\nBias-Precession-Nutation (BPN) matrix:")
print("Transforms from GCRF to CIRS")
print(f"  [{R_bpn[0, 0]:10.7f}, {R_bpn[0, 1]:10.7f}, {R_bpn[0, 2]:10.7f}]")
print(f"  [{R_bpn[1, 0]:10.7f}, {R_bpn[1, 1]:10.7f}, {R_bpn[1, 2]:10.7f}]")
print(f"  [{R_bpn[2, 0]:10.7f}, {R_bpn[2, 1]:10.7f}, {R_bpn[2, 2]:10.7f}]\n")

# Define orbital elements in degrees
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

# Convert to GCRF (ECI) position
state_gcrf = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)
pos_gcrf = state_gcrf[0:3]

print("Satellite position in GCRF:")
print(f"  [{pos_gcrf[0]:.3f}, {pos_gcrf[1]:.3f}, {pos_gcrf[2]:.3f}] m\n")

# Transform to CIRS using BPN matrix
pos_cirs = R_bpn @ pos_gcrf

print("Satellite position in CIRS:")
print(f"  [{pos_cirs[0]:.3f}, {pos_cirs[1]:.3f}, {pos_cirs[2]:.3f}] m")

# Calculate the magnitude of the change
diff = np.linalg.norm(pos_gcrf - pos_cirs)
print(f"\nPosition change magnitude: {diff:.3f} m")
```


### Earth Rotation Matrix

Get the Earth rotation matrix (CIRS to TIRS):


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define epoch
epc = bh.Epoch(2024, 1, 1, 12, 0, 0.0, time_system=bh.UTC)

# Get Earth rotation matrix (CIRS to TIRS transformation)
R_er = bh.earth_rotation(epc)

print(f"Epoch: {epc.to_datetime()}")
print("\nEarth Rotation matrix:")
print("Transforms from CIRS to TIRS")
print(f"  [{R_er[0, 0]:10.7f}, {R_er[0, 1]:10.7f}, {R_er[0, 2]:10.7f}]")
print(f"  [{R_er[1, 0]:10.7f}, {R_er[1, 1]:10.7f}, {R_er[1, 2]:10.7f}]")
print(f"  [{R_er[2, 0]:10.7f}, {R_er[2, 1]:10.7f}, {R_er[2, 2]:10.7f}]\n")

# Define orbital elements in degrees
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

# Convert to GCRF and then to CIRS
state_gcrf = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)
pos_gcrf = state_gcrf[0:3]
R_bpn = bh.bias_precession_nutation(epc)
pos_cirs = R_bpn @ pos_gcrf

print("Satellite position in CIRS:")
print(f"  [{pos_cirs[0]:.3f}, {pos_cirs[1]:.3f}, {pos_cirs[2]:.3f}] m\n")

# Apply Earth rotation to get TIRS
pos_tirs = R_er @ pos_cirs

print("Satellite position in TIRS:")
print(f"  [{pos_tirs[0]:.3f}, {pos_tirs[1]:.3f}, {pos_tirs[2]:.3f}] m")

# Calculate the magnitude of the change
diff = np.linalg.norm(pos_cirs - pos_tirs)
print(f"\nPosition change magnitude: {diff:.3f} m")
print("Note: Earth rotation causes large position changes (km scale)")
print(f"      due to ~{np.degrees(bh.OMEGA_EARTH * 3600):.3f}° rotation per hour")
```


### Polar Motion Matrix

Get the polar motion matrix (TIRS to ITRF):


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define epoch
epc = bh.Epoch(2024, 1, 1, 12, 0, 0.0, time_system=bh.UTC)

# Get polar motion matrix (TIRS to ITRF transformation)
R_pm = bh.polar_motion(epc)

print(f"Epoch: {epc.to_datetime()}")
print("\nPolar Motion matrix:")
print("Transforms from TIRS to ITRF")
print(f"  [{R_pm[0, 0]:10.7f}, {R_pm[0, 1]:10.7f}, {R_pm[0, 2]:10.7f}]")
print(f"  [{R_pm[1, 0]:10.7f}, {R_pm[1, 1]:10.7f}, {R_pm[1, 2]:10.7f}]")
print(f"  [{R_pm[2, 0]:10.7f}, {R_pm[2, 1]:10.7f}, {R_pm[2, 2]:10.7f}]\n")

# Define orbital elements in degrees
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

# Convert through the full chain: GCRF → CIRS → TIRS
state_gcrf = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)
pos_gcrf = state_gcrf[0:3]
R_bpn = bh.bias_precession_nutation(epc)
R_er = bh.earth_rotation(epc)
pos_tirs = R_er @ R_bpn @ pos_gcrf

print("Satellite position in TIRS:")
print(f"  [{pos_tirs[0]:.3f}, {pos_tirs[1]:.3f}, {pos_tirs[2]:.3f}] m\n")

# Apply polar motion to get ITRF
pos_itrf = R_pm @ pos_tirs

print("Satellite position in ITRF:")
print(f"  [{pos_itrf[0]:.3f}, {pos_itrf[1]:.3f}, {pos_itrf[2]:.3f}] m")

# Calculate the magnitude of the change
diff = np.linalg.norm(pos_tirs - pos_itrf)
print(f"\nPosition change magnitude: {diff:.3f} m")
print("Note: Polar motion effects are typically centimeters to meters")

pos_itrf_direct = bh.position_gcrf_to_itrf(epc, pos_gcrf)
print("\nVerification using position_gcrf_to_itrf:")
print(
    f"  [{pos_itrf_direct[0]:.3f}, {pos_itrf_direct[1]:.3f}, {pos_itrf_direct[2]:.3f}] m"
)
print(f"  Max difference: {np.max(np.abs(pos_itrf - pos_itrf_direct)):.2e} m")
```


**note**
For most applications, use the combined `rotation_gcrf_to_itrf` or `state_gcrf_to_itrf` functions rather than computing intermediate matrices separately. The intermediate matrices are provided for educational purposes and specialized applications.

## See Also

- [ECI ↔ ECEF Naming Convention](eci_ecef.md) - Legacy naming convention that maps to GCRF/ITRF
- [Reference Frames Overview](index.md) - Complete overview of all reference frames in Brahe