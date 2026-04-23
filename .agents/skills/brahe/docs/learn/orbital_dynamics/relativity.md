# Relativistic Effects

While Newtonian mechanics is sufficient for most satellite orbit calculations, general relativistic effects become measurable with modern precision orbit determination systems. These corrections are particularly important for:

- Global Navigation Satellite Systems (GPS, Galileo, GLONASS, BeiDou)
- Fundamental physics experiments in space
- Ultra-precise orbit determination (cm-level accuracy)
- Long-term orbit propagation

## Physical Basis

General relativity modifies Newton's law of gravitation by accounting for the curvature of spacetime caused by mass. Mntenbruck & Gill (2000) provide the post-Newtonian correction of the acceleration due to Earth's gravity as:

$$
\mathbf{a} = -\frac{GM}{r^2} \left( \left( 4\frac{GM}{c^2r} - \frac{v^2}{c^2} \right)\mathbf{e}_r + 4\frac{v^2}{c^2}\left(\mathbf{e}_r \cdot \mathbf{e}_v\right)\mathbf{e}_v\right)
$$

where:

- $GM$ is Earth's gravitational parameter (m³/s²)
- $c$ is the speed of light (299,792,458 m/s)
- $r$ is the satellite position magnitude (m)
- $v$ is the satellite velocity magnitude (m/s)
- $\mathbf{e}_r = \frac{\mathbf{r}}{r}$ is the radial unit vector
- $\mathbf{e}_v = \frac{\mathbf{v}}{v}$ is the velocity unit vector

## Usage Examples

### Computing Relativistic Acceleration

Calculate the general relativistic correction to a satellite's acceleration.


```
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define GPS satellite state (MEO orbit where relativity is measurable)
a = bh.R_EARTH + 20180e3  # Semi-major axis (m)
e = 0.01  # Eccentricity
i = np.radians(55.0)  # Inclination (rad)
raan = np.radians(30.0)  # RAAN (rad)
argp = np.radians(45.0)  # Argument of perigee (rad)
nu = np.radians(90.0)  # True anomaly (rad)

# Convert to Cartesian state
oe = np.array([a, e, i, raan, argp, nu])
state = bh.state_koe_to_eci(oe, bh.AngleFormat.RADIANS)

print("GPS Satellite state (ECI):")
print(
    f"  Position: [{state[0] / 1e3:.1f}, {state[1] / 1e3:.1f}, {state[2] / 1e3:.1f}] km"
)
print(
    f"  Velocity: [{state[3] / 1e3:.3f}, {state[4] / 1e3:.3f}, {state[5] / 1e3:.3f}] km/s"
)
r_mag = np.linalg.norm(state[0:3])
v_mag = np.linalg.norm(state[3:6])
print(f"  Altitude: {(r_mag - bh.R_EARTH) / 1e3:.1f} km")
print(f"  Speed: {v_mag / 1e3:.3f} km/s")

# Compute relativistic acceleration
accel_rel = bh.accel_relativity(state)

print("\nRelativistic acceleration (m/s²):")
print(f"  ax = {accel_rel[0]:.15f}")
print(f"  ay = {accel_rel[1]:.15f}")
print(f"  az = {accel_rel[2]:.15f}")
print(f"  Magnitude: {np.linalg.norm(accel_rel):.15e} m/s²")

# Compare to Newtonian point-mass gravity
accel_newton = bh.accel_point_mass_gravity(
    state[0:3], np.array([0.0, 0.0, 0.0]), bh.GM_EARTH
)
accel_newton_mag = np.linalg.norm(accel_newton)

print(f"\nNewtonian gravity magnitude: {accel_newton_mag:.9f} m/s²")
print(
    f"Relativistic/Newtonian ratio: {np.linalg.norm(accel_rel) / accel_newton_mag:.6e}"
)

# Estimate accumulated position error if relativity is ignored
# Using simple approximation: Δr ≈ 0.5 * a * t²
# For 1 day propagation
one_day = 86400.0  # seconds
pos_error_1day = 0.5 * np.linalg.norm(accel_rel) * one_day**2

print("\nApproximate position error if relativity ignored:")
print(f"  After 1 day: {pos_error_1day:.3f} m")
print(f"  After 1 week: {pos_error_1day * 7:.1f} m")

# Compare to other perturbations at this altitude
# J2 magnitude (approximate)
j2 = 1.08263e-3
accel_j2_approx = 1.5 * j2 * bh.GM_EARTH * (bh.R_EARTH / r_mag) ** 2 / r_mag**2

# Third-body (Sun, approximate)
accel_sun_approx = 5e-8  # Typical value for GPS altitude

print("\nRelative magnitude of perturbations at GPS altitude:")
print(f"  J2: ~{accel_j2_approx:.6e} m/s²")
print(f"  Sun: ~{accel_sun_approx:.6e} m/s²")
print(f"  Relativity: {np.linalg.norm(accel_rel):.6e} m/s²")
print(f"  Relativity/J2 ratio: {np.linalg.norm(accel_rel) / accel_j2_approx:.6e}")
```


## See Also

- [Library API Reference: Relativity](../../library_api/orbit_dynamics/relativity.md)
- [Orbital Dynamics Overview](index.md)

## References

Montenbruck, O., & Gill, E. (2000). *Satellite Orbits: Models, Methods, and Applications*. Springer. Section 3.7: Relativistic Effects.