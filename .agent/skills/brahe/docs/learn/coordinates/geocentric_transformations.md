# Geocentric Transformations

Geocentric longitude, latitude, altitude coordinates represent positions relative to a spherical Earth's surface. These coordinates can be converted to and from Earth-Centered Earth-Fixed (ECEF) Cartesian coordinates. This coordinate system is simpler and computationally faster than the geodetic system, but less accurate for near-surface applications because it assumes Earth is a perfect sphere.

For complete API details, see the [Geocentric Coordinates API Reference](../../library_api/coordinates/geodetic.md#geocentric-conversions).

## Geocentric Coordinate System

Geocentric coordinates represent a position using:

- **Longitude** ($\lambda$): East-west angle from the prime meridian, in degrees [-180°, +180°] or radians $[-\pi, +\pi]$
- **Latitude** ($\varphi$): North-south angle from the equatorial plane, in degrees [-90°, +90°] or radians $[-\frac{\pi}{2}, +\frac{\pi}{2}]$
- **Altitude** ($h$): Height above the spherical Earth surface, in meters

Combined as: `[longitude, latitude, altitude]`, often abbreviated as `[lon, lat, alt]`.

**info**
The spherical Earth model uses an Earth radius of `6378137.0` meters, which is the WGS84 semi-major axis. This means the geocentric "surface" is a sphere with Earth's equatorial radius.

### Spherical vs Ellipsoidal Earth

The key difference between geocentric and geodetic coordinates is the Earth model:

- **Geocentric**: Earth is a perfect sphere of radius `WGS84_A`
- **Geodetic**: Earth is an ellipsoid (oblate spheroid) with equatorial bulge

## Converting Geocentric to ECEF

Earth-Centered Earth-Fixed (ECEF) is a Cartesian coordinate system with:

- Origin at Earth's center of mass
- X-axis through the intersection of the prime meridian and equator
- Z-axis through the North Pole
- Y-axis completing a right-handed system

You can convert geocentric spherical coordinates to ECEF Cartesian coordinates using following:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define a location in geocentric coordinates (spherical Earth model)
# Boulder, Colorado (approximately)
lon = -122.4194  # Longitude (deg)
lat = 37.7749  # Latitude (deg)
alt = 13.8  # Altitude above spherical Earth surface (m)

print("Geocentric coordinates (spherical Earth model):")
print(f"Longitude: {lon:.4f}° = {np.radians(lon):.6f} rad")
print(f"Latitude:  {lat:.4f}° = {np.radians(lat):.6f} rad")
print(f"Altitude:  {alt:.1f} m\n")

# Convert geocentric to ECEF Cartesian
geocentric = np.array([lon, lat, alt])
ecef = bh.position_geocentric_to_ecef(geocentric, bh.AngleFormat.DEGREES)

print("ECEF Cartesian coordinates:")
print(f"x = {ecef[0]:.3f} m")
print(f"y = {ecef[1]:.3f} m")
print(f"z = {ecef[2]:.3f} m")
print(f"Distance from Earth center: {np.linalg.norm(ecef):.3f} m\n")
```


## Converting ECEF to Geocentric

The reverse transformation converts Cartesian ECEF coordinates back to geocentric spherical coordinates:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define a satellite state (convert orbital elements to ECEF state)
epc = bh.Epoch(2024, 1, 1, 0, 0, 0.0, time_system=bh.UTC)
state_oe = np.array(
    [
        bh.R_EARTH + 500e3,  # Semi-major axis (m)
        0.0,  # Eccentricity
        97.8,  # Inclination (deg)
        15.0,  # Right ascension of ascending node (deg)
        30.0,  # Argument of periapsis (deg)
        45.0,  # Mean anomaly (deg)
    ]
)
state_ecef = bh.state_eci_to_ecef(
    epc, bh.state_koe_to_eci(state_oe, bh.AngleFormat.DEGREES)
)
print("ECEF Cartesian state [x, y, z, vx, vy, vz] (m, m/s):")
print(f"Position: [{state_ecef[0]:.3f}, {state_ecef[1]:.3f}, {state_ecef[2]:.3f}]")
print(f"Velocity: [{state_ecef[3]:.6f}, {state_ecef[4]:.6f}, {state_ecef[5]:.6f}]\n")

# Convert ECEF Cartesian to geocentric position
ecef_pos = state_ecef[0:3]
geocentric = bh.position_ecef_to_geocentric(ecef_pos, bh.AngleFormat.DEGREES)
print("Geocentric coordinates (spherical Earth model):")
print(f"Longitude: {geocentric[0]:.4f}° = {np.radians(geocentric[0]):.6f} rad")
print(f"Latitude:  {geocentric[1]:.4f}° = {np.radians(geocentric[1]):.6f} rad")
print(f"Altitude:  {geocentric[2]:.1f} m")
```


**info**
Latitude values are automatically constrained to the valid range [-90°, +90°] or [$-\frac{\pi}{2}$, $+\frac{\pi}{2}$] during conversion.

---

## See Also

- [Geocentric Coordinates API Reference](../../library_api/coordinates/geodetic.md#geocentric-conversions) - Complete function documentation
- [Geodetic Transformations](geodetic_transformations.md) - More accurate WGS84 ellipsoid model
- [Topocentric Transformations](topocentric_transformations.md) - Local horizon coordinate systems