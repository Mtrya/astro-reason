# Solar Radiation Pressure

Solar radiation pressure (SRP) is the force exerted by photons emitted by the sun when they strike a satellite's surface. While small compared to gravitational forces, SRP can become a significant perturbations for satellites at higher altitude, particularly for those large solar panels or lightweight structures.

## Physical Principle

Photons carry momentum, and when they strike a surface, they transfer that momentum. The acceleration due to solar radiation pressure is:

$$
\mathbf{a}_{SRP} = -P_{\odot} C_R \frac{A}{m} \nu \frac{\mathbf{r}_{\odot}}{|\mathbf{r}_{\odot}|}
$$

where:

- $P_{\odot}$ is the solar radiation pressure at 1 AU (≈ 4.56 × 10⁻⁶ N/m²)
- $C_R$ is the radiation pressure coefficient (dimensionless, typically 1.0-1.5)
- $A$ is the effective cross-sectional area perpendicular to Sun (m²)
- $m$ is the satellite mass (kg)
- $\nu$ is the shadow function (0 = full shadow, 1 = full sunlight)
- $\mathbf{r}_{\odot}$ is the Sun position vector relative to satellite

The pressure varies as $1/r^2$ with distance from the Sun but is essentially constant for Earth-orbiting satellites due to the comparatively small variation in distance around the orbit compared to the Earth-Sun distance.

### Computing SRP Acceleration

Calculate the solar radiation pressure acceleration on a satellite, accounting for Earth's shadow.


```
import brahe as bh
import numpy as np

bh.initialize_eop()

# Create an epoch (summer solstice for interesting Sun geometry)
epoch = bh.Epoch.from_datetime(2024, 6, 21, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# Define satellite position (GEO satellite)
a = bh.R_EARTH + 35786e3  # Semi-major axis (m) - geostationary
e = 0.0001  # Near-circular
i = np.radians(0.1)  # Near-equatorial
raan = np.radians(0.0)  # RAAN (rad)
argp = np.radians(0.0)  # Argument of perigee (rad)
nu = np.radians(0.0)  # True anomaly (rad)

# Convert to Cartesian state
oe = np.array([a, e, i, raan, argp, nu])
state = bh.state_koe_to_eci(oe, bh.AngleFormat.RADIANS)
r_sat = state[0:3]  # Position vector (m)

print("Satellite position (ECI, m):")
print(f"  x = {r_sat[0] / 1e3:.1f} km")
print(f"  y = {r_sat[1] / 1e3:.1f} km")
print(f"  z = {r_sat[2] / 1e3:.1f} km")
print(f"  Altitude: {(np.linalg.norm(r_sat) - bh.R_EARTH) / 1e3:.1f} km")

# Get Sun position
r_sun = bh.sun_position(epoch)

print("\nSun position (ECI, AU):")
print(f"  x = {r_sun[0] / 1.496e11:.6f} AU")
print(f"  y = {r_sun[1] / 1.496e11:.6f} AU")
print(f"  z = {r_sun[2] / 1.496e11:.6f} AU")

# Eclipse condition - check shadow using both models
nu_conical = bh.eclipse_conical(r_sat, r_sun)
nu_cylindrical = bh.eclipse_cylindrical(r_sat, r_sun)

print("\nEclipse status:")
print(f"  Conical model: {nu_conical:.6f}")
print(f"  Cylindrical model: {nu_cylindrical:.6f}")

if nu_conical == 0.0:
    print("  Status: Full shadow (umbra)")
elif nu_conical == 1.0:
    print("  Status: Full sunlight")
else:
    print(f"  Status: Penumbra ({nu_conical * 100:.1f}% illuminated)")

# Define satellite SRP properties
mass = 1500.0  # kg (typical GEO satellite)
cr = 1.3  # Radiation pressure coefficient
area = 20.0  # m² (effective area - solar panels + body)
p0 = 4.56e-6  # Solar radiation pressure at 1 AU (N/m²)

print("\nSatellite SRP properties:")
print(f"  Mass: {mass:.1f} kg")
print(f"  Area: {area:.1f} m²")
print(f"  Cr coefficient: {cr:.1f}")
print(f"  Area/mass ratio: {area / mass:.6f} m²/kg")

# Compute solar radiation pressure acceleration
accel_srp = bh.accel_solar_radiation_pressure(r_sat, r_sun, mass, cr, area, p0)

print("\nSolar radiation pressure acceleration (ECI, m/s²):")
print(f"  ax = {accel_srp[0]:.12f}")
print(f"  ay = {accel_srp[1]:.12f}")
print(f"  az = {accel_srp[2]:.12f}")
print(f"  Magnitude: {np.linalg.norm(accel_srp):.12f} m/s²")

# Theoretical maximum (no eclipse)
accel_max = p0 * cr * area / mass
print(f"\nTheoretical maximum (full sun): {accel_max:.12f} m/s²")
print(f"Actual/Maximum ratio: {np.linalg.norm(accel_srp) / accel_max:.6f}")

# Compare to other forces at GEO
r_mag = np.linalg.norm(r_sat)
accel_gravity = bh.GM_EARTH / r_mag**2
print("\nFor comparison at GEO altitude:")
print(f"  Point-mass gravity: {accel_gravity:.9f} m/s²")
print(f"  SRP/Gravity ratio: {np.linalg.norm(accel_srp) / accel_gravity:.2e}")
```


## Earth Eclipse (Earth Shadowing)

Satellites in Earth orbit periodically pass through Earth's shadow, where SRP is absent. The amount of light reaching the satellite is modeled using a shadow function $\nu$ that varies between 0 (full shadow) and 1 (full sunlight). This function accounts for:

- Earth's finite size (not a point)
- Sun's finite angular diameter (not a point source)
- Atmospheric refraction and absorption

Brahe provides two shadow models with different fidelity levels:

#### Conical (Penumbral) Model

The conical shadow model accounts for the finite size of both Earth and Sun, modeling the penumbra region. It defines:

- **Umbra** $\left(\nu = 0\right)$: Region of total shadow (Sun completely blocked)
- **Penumbra** $\left(0 < \nu < 1\right)$: Region of partial shadow (Sun partially blocked)
- **Sunlight** $\left(\nu = 1\right)$: No shadow

This model provides accurate illumination fractions and is implemented in `eclipse_conical()`.

#### Cylindrical Model

The cylindrical shadow model assumes Earth casts a cylindrical shadow parallel to the Sun-Earth line. This is computationally efficient and provides a binary output of $\nu \in \{0, 1\}$. It does not model the penumbra region. The model is efficient but less accurate for satellites near the shadow boundary.

This model is implemented in `eclipse_cylindrical()`.

For many applications, the penumbra region is small enough that the cylindrical model provides sufficient accuracy with improved computational performance.

### Eclipse Detection

Determine if a satellite is in Earth's shadow using either the conical or cylindrical model:


```
import brahe as bh
import numpy as np

# Initialize EOP data
bh.initialize_eop()

# Define satellite position and get Sun position
epc = bh.Epoch.from_date(2024, 1, 1, bh.TimeSystem.UTC)
r_sat = np.array([bh.R_EARTH + 400e3, 0.0, 0.0])
r_sun = bh.sun_position(epc)

# Check eclipse using conical model (accounts for penumbra)
nu_conical = bh.eclipse_conical(r_sat, r_sun)
print(f"Conical illumination fraction: {nu_conical:.4f}")

# Check eclipse using cylindrical model (binary: 0 or 1)
nu_cyl = bh.eclipse_cylindrical(r_sat, r_sun)
print(f"Cylindrical illumination: {nu_cyl:.1f}")

if nu_conical == 0.0:
    print("Satellite in full shadow (umbra)")
elif nu_conical == 1.0:
    print("Satellite in full sunlight")
else:
    print(f"Satellite in penumbra ({nu_conical * 100:.1f}% illuminated)")
```


## See Also

- [Library API Reference: Solar Radiation Pressure](../../library_api/orbit_dynamics/solar_radiation_pressure.md)
- [Third-Body Perturbations](third_body.md) - For Sun position calculation
- [Orbital Dynamics Overview](index.md)

## References

Montenbruck, O., & Gill, E. (2000). *Satellite Orbits: Models, Methods, and Applications*. Springer. Section 3.5: Solar Radiation Pressure.