# Third-Body Perturbations

Third-body perturbations are gravitational effects caused by celestial bodies other than the primary (Earth). The most significant third bodies affecting Earth satellites are the Sun and Moon, but planetary perturbations can also be important for high-precision applications or long-term orbit evolution.

## Physical Principle

The third-body perturbation is not the direct gravitational attraction of the perturbing body on the satellite, but rather the *differential* acceleration - the difference between the gravitational pull on the satellite and on Earth's center.

For a satellite at position $\mathbf{r}$ and a third body at position $\mathbf{r}_b$:

$$
\mathbf{a}_{3} = GM_{b} \left(\frac{\mathbf{r}_b - \mathbf{r}}{|\mathbf{r}_b - \mathbf{r}|^3} - \frac{\mathbf{r}_b}{|\mathbf{r}_b|^3}\right)
$$

where $GM_b$ is the gravitational parameter of the third body.

## Key Third Bodies

### Sun

The Sun is the most massive third body, but its large distance reduces its effect. Solar perturbations are particularly important for:

- Geostationary satellites (resonance effects)
- High eccentricity orbits
- Long-term orbit evolution

Typical acceleration magnitude: ~10⁻⁷ m/s² for LEO, increasing with altitude.

### Moon

Despite being less massive than the Sun, the Moon's proximity makes it a significant perturber. Lunar perturbations affect:

- Medium Earth orbit satellites (especially GPS-like orbits)
- Geostationary satellites
- Frozen orbit design

The Moon's acceleration on satellites is comparable to or larger than the Sun's at most altitudes.

### Planets

Planetary perturbations (Venus, Jupiter, Mars, etc.) are generally small but can accumulate over long time scales. They become relevant for:

- Long-term orbit propagation (years to decades)
- Precise orbit determination
- Special resonance conditions

## Modeling Approaches

Brahe provides two methods for computing third-body positions and perturbations:

### Analytical Models

Simplified analytical expressions provide approximate positions of the Sun and Moon based on time. These models are computationally efficient and suitable for many applications. They also don't require external data files.

### DE440s Ephemerides

For high-precision applications, Brahe supports using JPL's DE440s ephemerides with data provided by NASA JPL's [Naviation and Ancillary Information Facility](https://naif.jpl.nasa.gov/naif/index.html) and computations implemented using the excellent [Anise](https://github.com/nyx-space/anise) library.

The Development Ephemeris 440s (DE440s) provides high-precision positions of all major solar system bodies using numerical integration over the time span of 1849 to 2150. They provide meter-level accuracy or better for planetary positions, but require downloading and managing SPICE kernel data files. Brahe generally will download and cache these files automatically on first use.

## Usage Examples

### Sun and Moon Perturbations

Compute the combined gravitational acceleration from the Sun and Moon on a satellite.


```
import brahe as bh
import numpy as np

bh.initialize_eop()

# Create an epoch
epoch = bh.Epoch.from_datetime(2024, 6, 21, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# Define satellite position (GPS-like MEO satellite at ~20,000 km altitude)
a = bh.R_EARTH + 20180e3  # Semi-major axis (m)
e = 0.01  # Eccentricity
i = 55.0  # Inclination (deg)
raan = 120.0  # RAAN (deg)
argp = 45.0  # Argument of perigee (deg)
nu = 90.0  # True anomaly (deg)

# Convert to Cartesian state
oe = np.array([a, e, i, raan, argp, nu])
state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)
r_sat = state[0:3]  # Position vector (m)

print("Satellite position (ECI, m):")
print(f"  x = {r_sat[0] / 1e3:.1f} km")
print(f"  y = {r_sat[1] / 1e3:.1f} km")
print(f"  z = {r_sat[2] / 1e3:.1f} km")
print(f"  Altitude: {(np.linalg.norm(r_sat) - bh.R_EARTH) / 1e3:.1f} km")

# Compute Sun perturbation using analytical model
accel_sun = bh.accel_third_body_sun(epoch, r_sat)

print("\nSun third-body acceleration (analytical):")
print(f"  ax = {accel_sun[0]:.12f} m/s²")
print(f"  ay = {accel_sun[1]:.12f} m/s²")
print(f"  az = {accel_sun[2]:.12f} m/s²")
print(f"  Magnitude: {np.linalg.norm(accel_sun):.12f} m/s²")

# Compute Moon perturbation using analytical model
accel_moon = bh.accel_third_body_moon(epoch, r_sat)

print("\nMoon third-body acceleration (analytical):")
print(f"  ax = {accel_moon[0]:.12f} m/s²")
print(f"  ay = {accel_moon[1]:.12f} m/s²")
print(f"  az = {accel_moon[2]:.12f} m/s²")
print(f"  Magnitude: {np.linalg.norm(accel_moon):.12f} m/s²")

# Compute combined Sun + Moon acceleration
accel_combined = accel_sun + accel_moon

print("\nCombined Sun + Moon acceleration:")
print(f"  ax = {accel_combined[0]:.12f} m/s²")
print(f"  ay = {accel_combined[1]:.12f} m/s²")
print(f"  az = {accel_combined[2]:.12f} m/s²")
print(f"  Magnitude: {np.linalg.norm(accel_combined):.12f} m/s²")

# Compare Sun vs Moon relative magnitude
ratio = np.linalg.norm(accel_sun) / np.linalg.norm(accel_moon)
print(f"\nSun/Moon acceleration ratio: {ratio:.3f}")
```


## See Also

- [Library API Reference: Third-Body](../../library_api/orbit_dynamics/third_body.md)
- [Datasets: NAIF](../datasets/naif.md) - DE440s ephemeris data
- [Orbital Dynamics Overview](index.md)

## References

Montenbruck, O., & Gill, E. (2000). *Satellite Orbits: Models, Methods, and Applications*. Springer. Section 3.3: Gravitational Perturbations.