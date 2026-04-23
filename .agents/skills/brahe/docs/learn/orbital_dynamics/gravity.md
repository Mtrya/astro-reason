# Gravity Models

Earth's gravitational field is the dominant force acting on satellites and space debris. While a simple point-mass model provides a useful first approximation, the real Earth's non-spherical mass distribution creates additional gravitational effects that must be modeled for accurate orbit prediction.

## Point-Mass Gravity

The simplest model treats Earth (or any celestial body) as a point mass with all mass concentrated at its center. The gravitational acceleration is:

$$
\mathbf{a} = -\frac{GM}{r^3} \mathbf{r}
$$

where:

- $GM$ is the gravitational parameter (m³/s²)
- $\mathbf{r}$ is the position vector from the central body's center (m)
- $r = |\mathbf{r}|$ is the distance

This model for gravity is computationally efficient and works well for modeling the effect of third-body perturbations from other planets and moons. This is discussed further in the [Third-Body Perturbations](third_body.md) section.

## Spherical Harmonic Expansion

Newton's law is excellent since it allows us to analytically solve the two-body problem. However, for Earth-orbiting satellites, the point-mass assumption is insufficient due to the planet's non-uniform shape and mass distribution. The Earth's equatorial bulge, polar flattening, and irregular mass distribution cause the gravitational attraction to vary with location. These variations are modeled using spherical harmonics - a mathematical expansion in terms of Legendre polynomials.

### Geopotential

The gravitational potential at a point outside Earth can be expressed as:

$$
V(r, \phi, \lambda) = \frac{GM}{r} \sum_{n=0}^{\infty} \sum_{m=0}^{n} \left(\frac{R_E}{r}\right)^n \bar{P}_{nm}(\sin\phi) \left(\bar{C}_{nm}\cos(m\lambda) + \bar{S}_{nm}\sin(m\lambda)\right)
$$

where:

- $r, \phi, \lambda$ are spherical coordinates (radius, latitude, longitude)
- $R_E$ is Earth's equatorial radius
- $\bar{P}_{nm}$ are normalized associated Legendre polynomials
- $\bar{C}_{nm}, \bar{S}_{nm}$ are normalized geopotential coefficients
- $n$ is the degree, $m$ is the order

The acceleration is computed as the gradient of this potential, yielding:

$$
\mathbf{a} = -\nabla \frac{GM}{r} \sum_{n=0}^{\infty} \sum_{m=0}^{n} \left(\frac{R_E}{r}\right)^n \bar{P}_{nm}(\sin\phi) \left(\bar{C}_{nm}\cos(m\lambda) + \bar{S}_{nm}\sin(m\lambda)\right)
$$

### Dominant Terms

The most significant non-spherical terms are:

- $\mathbf{J}_2$ (the $C_{2,0}\right$ harmonic) models Earth's oblateness and is ~1000× larger than any other term. It causes orbital precession, that is regression of the ascending node and rotation of the argument of perigee, which make sun-synchronous orbits possible.

- $\mathbf{J}_{2,2}$ (the $C_{2,2}, S_{2,2}\right$ harmonics) model Earth's ellipticity (difference between equatorial radii). Creates tesseral perturbations.

- **Higher-order terms**: Become important for precise orbit determination and long-term propagation, especially for low Earth orbit satellites.

### Gravity Models

Brahe includes several standard geopotential models with different degrees and orders of expansion:

- **EGM2008**: Earth Gravitational Model 2008, high-fidelity model to degree/order 360
- **GGM05S**: GRACE Gravity Model, degree/order 180
- **JGM3**: Joint Gravity Model 3, degree/order 70

Higher degree/order models provide more accuracy but require more computation. For most applications:

- **Low Earth Orbit**: Degree/order 10-20 sufficient for short-term propagation
- **Medium/Geostationary Orbit**: Degree/order 4-8 usually adequate
- **High-precision applications**: Degree/order 50+ may be needed

Additional gravity models (`.gfc` files) can be downloaded from the [International Centre for Global Earth Models (ICGEM)](https://icgem.gfz-potsdam.de/tom_longtime) repository and used with Brahe.

## Computational Considerations

Spherical harmonic evaluation involves recursive computation of Legendre polynomials and requires rotation between Earth-fixed and inertial frames. The computational cost scales as O(n²) where n is the maximum degree.

For real-time applications or long propagations with many time steps, limiting the degree and order to only what's necessary for the required accuracy is important for performance.

## Usage Examples

### Point-Mass Gravity

The point-mass gravity model can be used for any celestial body by providing its gravitational parameter and position.


```
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define satellite position in ECI frame (LEO satellite at 500 km altitude)
# Using Keplerian elements and converting to Cartesian
a = bh.R_EARTH + 500e3  # Semi-major axis (m)
e = 0.001  # Eccentricity
i = 97.8  # Inclination (deg)
raan = 0.0  # RAAN (deg)
argp = 0.0  # Argument of perigee (deg)
nu = 0.0  # True anomaly (deg)

# Convert to Cartesian state
oe = np.array([a, e, i, raan, argp, nu])
state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)
r_sat = state[0:3]  # Position vector (m)

print("Satellite position (ECI, m):")
print(f"  x = {r_sat[0]:.3f}")
print(f"  y = {r_sat[1]:.3f}")
print(f"  z = {r_sat[2]:.3f}")

# Compute point-mass gravitational acceleration
# For Earth-centered case, central body is at origin
r_earth = np.array([0.0, 0.0, 0.0])
accel = bh.accel_point_mass_gravity(r_sat, r_earth, bh.GM_EARTH)

print("\nPoint-mass gravity acceleration (m/s²):")
print(f"  ax = {accel[0]:.6f}")
print(f"  ay = {accel[1]:.6f}")
print(f"  az = {accel[2]:.6f}")

# Compute magnitude
accel_mag = np.linalg.norm(accel)
print(f"\nAcceleration magnitude: {accel_mag:.6f} m/s²")

# Compare to theoretical value: GM/r²
r_mag = np.linalg.norm(r_sat)
accel_theoretical = bh.GM_EARTH / (r_mag**2)
print(f"Theoretical magnitude: {accel_theoretical:.6f} m/s²")
```


### Spherical Harmonics

For high-fidelity Earth gravity modeling, use the spherical harmonic expansion with an appropriate geopotential model.


```
import brahe as bh
import numpy as np

bh.initialize_eop()

# Create an epoch for frame transformations
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# Define satellite position in ECI frame (LEO satellite at 500 km altitude)
a = bh.R_EARTH + 500e3  # Semi-major axis (m)
e = 0.001  # Eccentricity
i = 97.8  # Inclination (deg)
raan = 45.0  # RAAN (deg)
argp = 30.0  # Argument of perigee (deg)
nu = 60.0  # True anomaly (deg)

# Convert to Cartesian state
oe = np.array([a, e, i, raan, argp, nu])
state_eci = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)
r_eci = state_eci[0:3]  # Position vector (m)

print("Satellite position (ECI, m):")
print(f"  x = {r_eci[0]:.3f}")
print(f"  y = {r_eci[1]:.3f}")
print(f"  z = {r_eci[2]:.3f}")

# Load gravity model (GGM05S - degree/order 180)
gravity_model = bh.GravityModel.from_model_type(bh.GravityModelType.GGM05S)
print(
    f"\nGravity model: GGM05S (max degree {gravity_model.n_max}, max order {gravity_model.m_max})"
)

# For spherical harmonics, we need the ECI to body-fixed rotation matrix
# This rotates from ECI (inertial) to ECEF (Earth-fixed) frame
R_eci_ecef = bh.rotation_eci_to_ecef(epoch)

# Compute spherical harmonic acceleration (degree 10, order 10)
n_max = 10
m_max = 10
accel_sh = bh.accel_gravity_spherical_harmonics(
    r_eci, R_eci_ecef, gravity_model, n_max, m_max
)

print(f"\nSpherical harmonic acceleration (degree {n_max}, order {m_max}):")
print(f"  ax = {accel_sh[0]:.9f} m/s²")
print(f"  ay = {accel_sh[1]:.9f} m/s²")
print(f"  az = {accel_sh[2]:.9f} m/s²")

# Compute point-mass for comparison
accel_pm = bh.accel_point_mass_gravity(r_eci, np.array([0.0, 0.0, 0.0]), bh.GM_EARTH)

print("\nPoint-mass acceleration:")
print(f"  ax = {accel_pm[0]:.9f} m/s²")
print(f"  ay = {accel_pm[1]:.9f} m/s²")
print(f"  az = {accel_pm[2]:.9f} m/s²")

# Compute difference (perturbation due to non-spherical Earth)
accel_pert = accel_sh - accel_pm

print("\nPerturbation (spherical harmonics - point mass):")
print(f"  Δax = {accel_pert[0]:.9f} m/s²")
print(f"  Δay = {accel_pert[1]:.9f} m/s²")
print(f"  Δaz = {accel_pert[2]:.9f} m/s²")
print(f"  Magnitude: {np.linalg.norm(accel_pert):.9f} m/s²")
```


## See Also

- [Library API Reference: Gravity](../../library_api/orbit_dynamics/gravity.md)
- [Orbital Dynamics Overview](index.md)
- [Constants: Physical Parameters](../constants.md#physical-constants)

## References

Montenbruck, O., & Gill, E. (2000). *Satellite Orbits: Models, Methods, and Applications*. Springer. Section 3.2: The Geopotential.