# Cartesian ↔ Orbital Element Transformations

The functions described here convert between Keplerian orbital elements and Cartesian state vectors. While these transformations are part of the "coordinates" module, they specifically deal with orbital mechanics - converting between two different coordinate representations of a satellite's orbit.

Understanding both representations is essential: Keplerian elements provide intuitive orbital parameters like size, shape, and orientation, while Cartesian states are necessary for numerical orbit propagation and applying perturbations.

For complete API details, see the [Cartesian Coordinates API Reference](../../library_api/coordinates/cartesian.md).

## Orbital Representations

### Keplerian Orbital Elements

Keplerian elements describe an orbit using six classical parameters:

- $a$: Semi-major axis (meters) - defines the orbit's size
- $e$: Eccentricity (dimensionless) - defines the orbit's shape (0 = circular, 0 < e < 1 = elliptical)
- $i$: Inclination (radians or degrees) - tilt of orbital plane relative to equator
- $\Omega$: Right ascension of ascending node (radians or degrees) - where orbit crosses equator going north
- $\omega$: Argument of periapsis (radians or degrees) - where orbit is closest to Earth
- $M$: Mean anomaly (radians or degrees) - position of satellite along orbit

In brahe, the combined vector has ordering `[a, e, i, Ω, ω, M]`

**info**
Brahe uses **mean anomaly** as the default anomaly representation for Keplerian elements. Other anomaly types (eccentric, true) can be converted using the anomaly conversion functions in the [Orbits module](../../library_api/orbits/index.md).

### Cartesian State Vectors

Cartesian states represent position and velocity in three-dimensional space:

- **Position**: $[p_x, p_y, p_z]$ in meters
- **Velocity**: $[v_x, v_y, v_z]$ in meters per second

In brahe, the state vector is combined as `[p_x, p_y, p_z, v_x, v_y, v_z]`

Cartesian states are typically expressed in an inertial reference frame like Earth-Centered Inertial (ECI), where the axes are fixed with respect to the stars rather than rotating with Earth.

**info**
All position and velocity components in Cartesian states are in SI base units (meters and meters per second).

They **must** be in SI base units for inputs and are always returned in SI base units.

## Converting Orbital Elements to Cartesian

The most common workflow is to start with intuitive orbital parameters and convert them to Cartesian states for propagation.

### Using Degrees

When working with human-readable orbital parameters, degrees are more intuitive:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define orbital elements [a, e, i, Ω, ω, M] in meters and degrees
# LEO satellite: 500 km altitude, 97.8° inclination (~sun-synchronous)
oe_deg = np.array(
    [
        bh.R_EARTH + 500e3,  # Semi-major axis (m)
        0.01,  # Eccentricity
        97.8,  # Inclination (deg)
        15.0,  # Right ascension of ascending node (deg)
        30.0,  # Argument of periapsis (deg)
        45.0,  # Mean anomaly (deg)
    ]
)

# Convert orbital elements to Cartesian state using degrees
state = bh.state_koe_to_eci(oe_deg, bh.AngleFormat.DEGREES)
print("Cartesian state [x, y, z, vx, vy, vz] (m, m/s):")
print(f"Position: [{state[0]:.3f}, {state[1]:.3f}, {state[2]:.3f}]")
print(f"Velocity: [{state[3]:.6f}, {state[4]:.6f}, {state[5]:.6f}]")
```


### Using Radians

For mathematical consistency or when working with data already in radians:


```python
import brahe as bh
import numpy as np
from math import pi

bh.initialize_eop()

# Define orbital elements [a, e, i, Ω, ω, M] in meters and degrees
# LEO satellite: 500 km altitude, 97.8° inclination (~sun-synchronous)
oe_deg = np.array(
    [
        bh.R_EARTH + 500e3,  # Semi-major axis (m)
        0.01,  # Eccentricity
        pi / 4,  # Inclination (rad)
        pi / 8,  # Right ascension of ascending node (rad)
        pi / 2,  # Argument of periapsis (rad)
        3 * pi / 4,  # Mean anomaly (rad)
    ]
)

# Convert orbital elements to Cartesian state using degrees
state = bh.state_koe_to_eci(oe_deg, bh.AngleFormat.RADIANS)
print("Cartesian state [x, y, z, vx, vy, vz] (m, m/s):")
print(f"Position: [{state[0]:.3f}, {state[1]:.3f}, {state[2]:.3f}]")
print(f"Velocity: [{state[3]:.6f}, {state[4]:.6f}, {state[5]:.6f}]")
```


**info**
The `AngleFormat` parameter only affects the three angular elements (i, Ω, ω, M). Semi-major axis is always in meters, and eccentricity is always dimensionless.

## Converting Cartesian to Orbital Elements

After propagating or receiving Cartesian state data, you often want to convert back to orbital elements for interpretation and analysis.


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define Cartesian state vector [px, py, pz, vx, vy, vz] in meters and meters per second
state = np.array(
    [1848964.106, -434937.468, 6560410.530, -7098.379734, -2173.344867, 1913.333385]
)

# Convert orbital elements to Cartesian state using degrees
oe_deg = bh.state_eci_to_koe(state, bh.AngleFormat.DEGREES)
print("Osculating state [a, e, i, Ω, ω, M] (deg):")
print(f"Semi-major axis (m): {oe_deg[0]:.3f}")
print(f"Eccentricity: {oe_deg[1]:.6f}")
print(f"Inclination (deg): {oe_deg[2]:.6f}")
print(f"RA of ascending node (deg): {oe_deg[3]:.6f}")
print(f"Argument of periapsis (deg): {oe_deg[4]:.6f}")
print(f"Mean anomaly (deg): {oe_deg[5]:.6f}")

# You can also convert using radians
oe_rad = bh.state_eci_to_koe(state, bh.AngleFormat.RADIANS)
print("\nOsculating state [a, e, i, Ω, ω, M] (rad):")
print(f"Semi-major axis (m): {oe_rad[0]:.3f}")
print(f"Eccentricity: {oe_rad[1]:.6f}")
print(f"Inclination (rad): {oe_rad[2]:.6f}")
print(f"RA of ascending node (rad): {oe_rad[3]:.6f}")
print(f"Argument of periapsis (rad): {oe_rad[4]:.6f}")
print(f"Mean anomaly (rad): {oe_rad[5]:.6f}")
```


---

## See Also

- [Cartesian Coordinates API Reference](../../library_api/coordinates/cartesian.md) - Complete function documentation
- [Orbital Mechanics](../../library_api/orbits/index.md) - Related orbital mechanics functions
- Anomaly Conversions - Converting between mean, eccentric, and true anomaly