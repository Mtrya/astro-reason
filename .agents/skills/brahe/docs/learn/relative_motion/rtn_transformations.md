# RTN Transformations

The RTN (Radial-Tangential-Normal) frame is an orbital reference frame that moves
with the satellite. It is commonly used for relative motion analysis and formation
flying applications.

The RTN frame is defined as:

- **R (Radial)**: Points from the Earth's center to the satellite's position
- **T (Tangential)**: Along-track direction, perpendicular to R in the orbital plane
- **N (Normal)**: Cross-track direction, perpendicular to the orbital plane (angular momentum direction)

## Coordinate System Definition

The RTN frame is a **right-handed coordinate system** where:

- The R axis points from the center of the Earth to the satellite's position vector
- The N axis is parallel to the angular momentum vector (cross product of position and velocity)
- The T axis completes the right-handed system (it is the cross product of N and R)

This frame is useful for:

- Describing relative positions between satellites in close proximity
- Designing proximity operations and rendezvous maneuvers
- Expressing thrust directions for orbital maneuvers

## Rotation Matrices

Brahe provides functions to compute rotation matrices between the ECI (Earth-Centered
Inertial) frame and the RTN frame. These rotation matrices transform can transform
vectors between the two frames.


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define a satellite in LEO orbit
# 700 km altitude, nearly circular, sun-synchronous inclination
oe = np.array(
    [
        bh.R_EARTH + 700e3,  # Semi-major axis (m)
        0.001,  # Eccentricity
        97.8,  # Inclination (deg)
        15.0,  # Right ascension of ascending node (deg)
        30.0,  # Argument of perigee (deg)
        45.0,  # Mean anomaly (deg)
    ]
)

# Convert to Cartesian ECI state
x_eci = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

# Compute rotation matrices
R_rtn_to_eci = bh.rotation_rtn_to_eci(x_eci)
R_eci_to_rtn = bh.rotation_eci_to_rtn(x_eci)

print("RTN-to-ECI rotation matrix:")
print(
    f"  [{R_rtn_to_eci[0, 0]:8.5f}, {R_rtn_to_eci[0, 1]:8.5f}, {R_rtn_to_eci[0, 2]:8.5f}]"
)
print(
    f"  [{R_rtn_to_eci[1, 0]:8.5f}, {R_rtn_to_eci[1, 1]:8.5f}, {R_rtn_to_eci[1, 2]:8.5f}]"
)
print(
    f"  [{R_rtn_to_eci[2, 0]:8.5f}, {R_rtn_to_eci[2, 1]:8.5f}, {R_rtn_to_eci[2, 2]:8.5f}]\n"
)

# Verify orthogonality: R^T × R = I
identity = R_rtn_to_eci.T @ R_rtn_to_eci
print("Orthogonality check (R^T × R):")
print(f"  [{identity[0, 0]:8.5f}, {identity[0, 1]:8.5f}, {identity[0, 2]:8.5f}]")
print(f"  [{identity[1, 0]:8.5f}, {identity[1, 1]:8.5f}, {identity[1, 2]:8.5f}]")
print(f"  [{identity[2, 0]:8.5f}, {identity[2, 1]:8.5f}, {identity[2, 2]:8.5f}]")
print(f"Difference from identity: {np.linalg.norm(identity - np.eye(3)):.15f}\n")

# Verify determinant = +1 (proper rotation matrix)
det = np.linalg.det(R_rtn_to_eci)
print(f"Determinant (should be +1): {det:.15f}\n")

# Verify ECI-to-RTN is the transpose of RTN-to-ECI
print("Transpose relationship check:")
print(
    f"||R_eci_to_rtn - R_rtn_to_eci^T||: {np.linalg.norm(R_eci_to_rtn - R_rtn_to_eci.T):.15f}\n"
)

# Example: Transform a vector from RTN to ECI
v_rtn = np.array([1.0, 0.0, 0.0])  # Radial unit vector in RTN frame
v_eci = R_rtn_to_eci @ v_rtn

print("Example transformation:")
print(f"Vector in RTN frame: [{v_rtn[0]:.3f}, {v_rtn[1]:.3f}, {v_rtn[2]:.3f}]")
print(f"Vector in ECI frame: [{v_eci[0]:.5f}, {v_eci[1]:.5f}, {v_eci[2]:.5f}]")
print(f"ECI vector magnitude: {np.linalg.norm(v_eci):.15f}")
```


## State Transformations

For relative motion analysis between two satellites (often called "chief" and "deputy"),
Brahe provides functions to transform between absolute ECI states and relative RTN states.

### ECI to RTN (Absolute to Relative)

The `state_eci_to_rtn` function transforms the absolute states of two satellites from
the ECI frame to the relative state of the deputy with respect to the chief in the
RTN frame. This accounts for the rotating nature of the RTN frame.

The resulting relative state vector contains six components:

- Position: $[\rho_R, \rho_T, \rho_N]$ - relative position in RTN frame (m)
- Velocity: $[\dot{\rho}_R, \dot{\rho}_T, \dot{\rho}_N]$ - relative velocity in RTN frame (m/s)


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define chief satellite orbital elements
# LEO orbit: 700 km altitude, nearly circular, sun-synchronous inclination
oe_chief = np.array(
    [
        bh.R_EARTH + 700e3,  # Semi-major axis (m)
        0.001,  # Eccentricity
        97.8,  # Inclination (deg)
        15.0,  # Right ascension of ascending node (deg)
        30.0,  # Argument of perigee (deg)
        45.0,  # Mean anomaly (deg)
    ]
)

# Define deputy satellite with small orbital element differences
oe_deputy = np.array(
    [
        bh.R_EARTH + 701e3,  # 1 km higher semi-major axis
        0.0015,  # Slightly higher eccentricity
        97.85,  # 0.05° higher inclination
        15.05,  # Small RAAN difference
        30.05,  # Small argument of perigee difference
        45.00,  # Same mean anomaly
    ]
)

# Convert to Cartesian ECI states
x_chief = bh.state_koe_to_eci(oe_chief, bh.AngleFormat.DEGREES)
x_deputy = bh.state_koe_to_eci(oe_deputy, bh.AngleFormat.DEGREES)

# Transform to relative RTN state
x_rel_rtn = bh.state_eci_to_rtn(x_chief, x_deputy)

print("Relative state in RTN frame:")
print(f"Radial (R):      {x_rel_rtn[0]:.3f} m")
print(f"Along-track (T): {x_rel_rtn[1]:.3f} m")
print(f"Cross-track (N): {x_rel_rtn[2]:.3f} m")
print(f"Velocity R:      {x_rel_rtn[3]:.6f} m/s")
print(f"Velocity T:      {x_rel_rtn[4]:.6f} m/s")
print(f"Velocity N:      {x_rel_rtn[5]:.6f} m/s\n")
# Calculate total relative distance
relative_distance = np.linalg.norm(x_rel_rtn[:3])
print(f"Total relative distance: {relative_distance:.3f} m")
```


### RTN to ECI (Relative to Absolute)

The `state_rtn_to_eci` function performs the inverse operation: it transforms the
relative state of a deputy satellite (in the RTN frame of the chief) back to the
absolute ECI state of the deputy. This is useful for propagating relative states
or computing deputy trajectories from relative motion plans.


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define chief satellite orbital elements
# LEO orbit: 700 km altitude, nearly circular, sun-synchronous inclination
oe_chief = np.array(
    [
        bh.R_EARTH + 700e3,  # Semi-major axis (m)
        0.001,  # Eccentricity
        97.8,  # Inclination (deg)
        15.0,  # Right ascension of ascending node (deg)
        30.0,  # Argument of perigee (deg)
        45.0,  # Mean anomaly (deg)
    ]
)

# Convert to Cartesian ECI state
x_chief = bh.state_koe_to_eci(oe_chief, bh.AngleFormat.DEGREES)

print("Chief ECI state:")
print(
    f"Position:  [{x_chief[0] / 1e3:.3f}, {x_chief[1] / 1e3:.3f}, {x_chief[2] / 1e3:.3f}] km"
)
print(
    f"Velocity:  [{x_chief[3] / 1e3:.6f}, {x_chief[4] / 1e3:.6f}, {x_chief[5] / 1e3:.6f}] km/s\n"
)

# Define relative state in RTN frame
# Deputy is 1 km radial, 500 m along-track, -300 m cross-track
# with small relative velocity
x_rel_rtn = np.array(
    [
        1000.0,  # Radial offset (m)
        500.0,  # Along-track offset (m)
        -300.0,  # Cross-track offset (m)
        0.1,  # Radial velocity (m/s)
        -0.05,  # Along-track velocity (m/s)
        0.02,  # Cross-track velocity (m/s)
    ]
)

print("Relative state in RTN frame:")
print(f"Radial (R):      {x_rel_rtn[0]:.3f} m")
print(f"Along-track (T): {x_rel_rtn[1]:.3f} m")
print(f"Cross-track (N): {x_rel_rtn[2]:.3f} m")
print(f"Velocity R:      {x_rel_rtn[3]:.3f} m/s")
print(f"Velocity T:      {x_rel_rtn[4]:.3f} m/s")
print(f"Velocity N:      {x_rel_rtn[5]:.3f} m/s\n")

# Transform to absolute deputy ECI state
x_deputy = bh.state_rtn_to_eci(x_chief, x_rel_rtn)

print("Deputy ECI state:")
print(
    f"Position:  [{x_deputy[0] / 1e3:.3f}, {x_deputy[1] / 1e3:.3f}, {x_deputy[2] / 1e3:.3f}] km"
)
print(
    f"Velocity:  [{x_deputy[3] / 1e3:.6f}, {x_deputy[4] / 1e3:.6f}, {x_deputy[5] / 1e3:.6f}] km/s\n"
)

# Verify by transforming back to RTN
x_rel_rtn_verify = bh.state_eci_to_rtn(x_chief, x_deputy)

print("Round-trip verification (RTN -> ECI -> RTN):")
print(f"Original RTN:  [{x_rel_rtn[0]:.3f}, {x_rel_rtn[1]:.3f}, {x_rel_rtn[2]:.3f}] m")
print(
    f"Recovered RTN: [{x_rel_rtn_verify[0]:.3f}, {x_rel_rtn_verify[1]:.3f}, {x_rel_rtn_verify[2]:.3f}] m"
)
print(f"Difference:    {np.linalg.norm(x_rel_rtn - x_rel_rtn_verify):.9f} m")
```
