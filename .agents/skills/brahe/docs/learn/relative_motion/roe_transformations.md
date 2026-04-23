# Relative Orbital Elements (ROE) Transformations

Relative Orbital Elements (ROE) provide a quasi-nonsingular mean description of the relative motion between two satellites in close proximity. ROE are particularly useful for formation flying and proximity operations, where maintaining specific relative geometries is important.

Unlike instantaneous Cartesian relative states (like RTN coordinates), ROE describe the relative orbit using orbital elements, meaning that only a single element, the relative longitude $d\lambda$, is quickly changing over time. This makes ROE ideal for long-term formation design and control.

## ROE Definition

The ROE vector contains six dimensionless or angular elements that are constructed from the classical orbital elements of the chief and deputy satellites:

$$
\begin{align*}
\delta a & = \frac{a_d - a_c}{a_c} \\
\delta \lambda & = (M_d + \omega_d) - (M_c + \omega_c) + (\Omega_d - \Omega_c) \cos i_c \\
\delta e_x & = e_d \cos \omega_d - e_c \cos \omega_c \\
\delta e_y & = e_d \sin \omega_d - e_c \sin \omega_c \\
\delta i_x & = i_d - i_c \\
\delta i_y & = (\Omega_d - \Omega_c) \sin i_c
\end{align*}
$$

The elements are:
- $\delta a$ - relative semi-major axis (dimensionless)
- $\delta \lambda$ - relative mean longitude (radians)
- $\delta e_x$, $\delta e_y$ - components of the relative eccentricity vector (dimensionless)
- $\delta i_x$, $\delta i_y$ - components of the relative inclination vector (radians)

## Key Properties

**Nonsingularity**: ROE remain well-defined for circular and near-circular orbits, unlike classical orbital elements which become singular as eccentricity approaches zero.

**Periodic Orbits**: Specific ROE configurations produce periodic or quasi-periodic relative orbits:

- Setting $\delta a = 0$ prevents along-track drift
- The eccentricity vector components ($\delta e_x$, $\delta e_y$) control in-plane motion
- The inclination vector components ($\delta i_x$, $\delta i_y$) control cross-track motion

## Converting Orbital Elements to ROE

The `state_oe_to_roe` function converts the classical orbital elements of a chief and deputy satellite into ROE. This is useful when you have two satellite orbits and want to analyze their relative motion characteristics.


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
# This creates a quasi-periodic relative orbit
oe_deputy = np.array(
    [
        bh.R_EARTH + 701e3,  # 1 km higher semi-major axis
        0.0015,  # Slightly higher eccentricity
        97.85,  # 0.05° higher inclination
        15.05,  # Small RAAN difference
        30.05,  # Small argument of perigee difference
        45.05,  # Small mean anomaly difference
    ]
)

# Convert to Relative Orbital Elements (ROE)
roe = bh.state_oe_to_roe(oe_chief, oe_deputy, bh.AngleFormat.DEGREES)

print("Relative Orbital Elements (ROE):")
print(f"da (relative SMA):        {roe[0]:.6e}")
print(f"dλ (relative mean long):  {roe[1]:.6f}°")
print(f"dex (rel ecc x-comp):     {roe[2]:.6e}")
print(f"dey (rel ecc y-comp):     {roe[3]:.6e}")
print(f"dix (rel inc x-comp):     {roe[4]:.6f}°")
print(f"diy (rel inc y-comp):     {roe[5]:.6f}°")
```


## Converting ROE to Deputy Orbital Elements

The `state_roe_to_oe` function performs the inverse operation: given the chief's orbital elements and the desired ROE, it computes the deputy's orbital elements. This is essential for:

- Initializing formation flying missions with desired relative geometries
- Retargeting maneuvers to achieve new relative configurations
- Propagating relative orbits using element-based propagators


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

# Define Relative Orbital Elements (ROE)
# These describe a quasi-periodic relative orbit
roe = np.array(
    [
        1.412801e-4,  # da: Relative semi-major axis
        0.093214,  # dλ: Relative mean longitude (deg)
        4.323577e-4,  # dex: x-component of relative eccentricity vector
        2.511333e-4,  # dey: y-component of relative eccentricity vector
        0.050000,  # dix: x-component of relative inclination vector (deg)
        0.049537,  # diy: y-component of relative inclination vector (deg)
    ]
)

# Convert to deputy satellite orbital elements
oe_deputy = bh.state_roe_to_oe(oe_chief, roe, bh.AngleFormat.DEGREES)

print("Deputy Satellite Orbital Elements:")
print(
    f"Semi-major axis: {oe_deputy[0]:.3f} m ({(oe_deputy[0] - bh.R_EARTH) / 1000:.1f} km alt)"
)
print(f"Eccentricity:    {oe_deputy[1]:.6f}")
print(f"Inclination:     {oe_deputy[2]:.4f}°")
print(f"RAAN:            {oe_deputy[3]:.4f}°")
print(f"Arg of perigee:  {oe_deputy[4]:.4f}°")
print(f"Mean anomaly:    {oe_deputy[5]:.4f}°")
```


## Direct ECI State to ROE Conversion

In many practical applications, satellite states are available as Cartesian ECI vectors rather than orbital elements. The `state_eci_to_roe` function provides a convenient way to compute ROE directly from the ECI states of the chief and deputy satellites, internally handling the conversion to orbital elements.


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
# This creates a quasi-periodic relative orbit
oe_deputy = np.array(
    [
        bh.R_EARTH + 701e3,  # 1 km higher semi-major axis
        0.0015,  # Slightly higher eccentricity
        97.85,  # 0.05 deg higher inclination
        15.05,  # Small RAAN difference
        30.05,  # Small argument of perigee difference
        45.05,  # Small mean anomaly difference
    ]
)

# Convert orbital elements to ECI state vectors
x_chief = bh.state_koe_to_eci(oe_chief, bh.AngleFormat.DEGREES)
x_deputy = bh.state_koe_to_eci(oe_deputy, bh.AngleFormat.DEGREES)

print("Chief ECI State:")
print(f"  Position: [{x_chief[0]:.3f}, {x_chief[1]:.3f}, {x_chief[2]:.3f}] m")
print(f"  Velocity: [{x_chief[3]:.3f}, {x_chief[4]:.3f}, {x_chief[5]:.3f}] m/s")

print("\nDeputy ECI State:")
print(f"  Position: [{x_deputy[0]:.3f}, {x_deputy[1]:.3f}, {x_deputy[2]:.3f}] m")
print(f"  Velocity: [{x_deputy[3]:.3f}, {x_deputy[4]:.3f}, {x_deputy[5]:.3f}] m/s")

# Convert ECI states directly to Relative Orbital Elements (ROE)
roe = bh.state_eci_to_roe(x_chief, x_deputy, bh.AngleFormat.DEGREES)

print("\nRelative Orbital Elements (ROE):")
print(f"  da (relative SMA):        {roe[0]:.6e}")
print(f"  d_lambda (relative mean long):  {roe[1]:.6f} deg")
print(f"  dex (rel ecc x-comp):     {roe[2]:.6e}")
print(f"  dey (rel ecc y-comp):     {roe[3]:.6e}")
print(f"  dix (rel inc x-comp):     {roe[4]:.6f} deg")
print(f"  diy (rel inc y-comp):     {roe[5]:.6f} deg")
```


## Converting ROE to Deputy ECI State

The inverse operation, `state_roe_to_eci`, computes the deputy satellite's ECI state from the chief's ECI state and the ROE.


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

# Convert chief orbital elements to ECI state
x_chief = bh.state_koe_to_eci(oe_chief, bh.AngleFormat.DEGREES)

print("Chief ECI State:")
print(f"  Position: [{x_chief[0]:.3f}, {x_chief[1]:.3f}, {x_chief[2]:.3f}] m")
print(f"  Velocity: [{x_chief[3]:.3f}, {x_chief[4]:.3f}, {x_chief[5]:.3f}] m/s")

# Define Relative Orbital Elements (ROE)
# This defines a small relative orbit around the chief
roe = np.array(
    [
        1.413e-4,  # da: relative semi-major axis (dimensionless)
        0.093,  # d_lambda: relative mean longitude (deg)
        4.324e-4,  # dex: relative eccentricity x-component
        2.511e-4,  # dey: relative eccentricity y-component
        0.05,  # dix: relative inclination x-component (deg)
        0.05,  # diy: relative inclination y-component (deg)
    ]
)

print("\nRelative Orbital Elements (ROE):")
print(f"  da (relative SMA):        {roe[0]:.6e}")
print(f"  d_lambda (relative mean long):  {roe[1]:.6f} deg")
print(f"  dex (rel ecc x-comp):     {roe[2]:.6e}")
print(f"  dey (rel ecc y-comp):     {roe[3]:.6e}")
print(f"  dix (rel inc x-comp):     {roe[4]:.6f} deg")
print(f"  diy (rel inc y-comp):     {roe[5]:.6f} deg")

# Convert chief ECI state and ROE to deputy ECI state
x_deputy = bh.state_roe_to_eci(x_chief, roe, bh.AngleFormat.DEGREES)

print("\nDeputy ECI State (computed from ROE):")
print(f"  Position: [{x_deputy[0]:.3f}, {x_deputy[1]:.3f}, {x_deputy[2]:.3f}] m")
print(f"  Velocity: [{x_deputy[3]:.3f}, {x_deputy[4]:.3f}, {x_deputy[5]:.3f}] m/s")

# Compute relative distance
rel_pos = x_deputy[:3] - x_chief[:3]
rel_dist = np.linalg.norm(rel_pos)
print(f"\nRelative distance: {rel_dist:.1f} m")
```


## References

1. [Sullivan, J. (2020). "Nonlinear Angles-Only Orbit Estimation for Autonomous Distributed Space Systems"](https://searchworks.stanford.edu/view/13680835)