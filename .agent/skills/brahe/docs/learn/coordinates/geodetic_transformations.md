# Geodetic Transformations

Geodetic longitude, latitude, altitude coordinates represent positions relative to the WGS84 ellipsoidal Earth model. These coordinates can be converted to and from Earth-Centered Earth-Fixed (ECEF) Cartesian coordinates. This coordinate system is more accurate than the geocentric system for near-surface applications because it accounts for Earth's equatorial bulge.

For complete API details, see the [Geodetic Coordinates API Reference](../../library_api/coordinates/geodetic.md).

## Geodetic Coordinate System

Geodetic coordinates represent a position using:

- **Longitude** ($\lambda$): East-west angle from the prime meridian, in degrees [-180°, +180°] or radians $[-\pi, +\pi]$
- **Latitude** ($\varphi$): North-south angle from the equatorial plane, measured perpendicular to the ellipsoid surface, in degrees [-90°, +90°] or radians [$-\frac{\pi}{2}$, $+\frac{\pi}{2}$]
- **Altitude** ($h$): Height above the WGS84 ellipsoid surface, in meters

Combined as: `[longitude, latitude, altitude]`, often abbreviated as `[lon, lat, alt]`.

**info**
Geodetic latitude is measured perpendicular to the ellipsoid surface, not from Earth's center. This differs from geocentric latitude, which is measured from the center. For a point on the surface, these can differ by up to 11 arcminutes (about 0.2°).

### WGS84 Ellipsoid Model

The key difference between geodetic and geocentric coordinates is the Earth model:

- **Geodetic**: Earth is an ellipsoid (oblate spheroid) with parameters:
    - Semi-major axis: `WGS84_A = 6378137.0` meters (equatorial radius)
    - Flattening: `WGS84_F = 1/298.257223563`
- **Geocentric**: Earth is a perfect sphere of radius `WGS84_A`

The difference between equatorial and polar radii is approximately 21 km, which significantly affects position calculations near Earth's surface.

## Converting Geodetic to ECEF

Earth-Centered Earth-Fixed (ECEF) is a Cartesian coordinate system with:

- Origin at Earth's center of mass
- X-axis through the intersection of the prime meridian and equator
- Z-axis through the North Pole
- Y-axis completing a right-handed system

You can convert geodetic coordinates to ECEF Cartesian coordinates using the following:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define a location in geodetic coordinates (WGS84 ellipsoid model)
# Boulder, Colorado (approximately)
lon = -122.4194  # Longitude (deg)
lat = 37.7749  # Latitude (deg)
alt = 16.0  # Altitude above WGS84 ellipsoid (m)

print("Geodetic coordinates (WGS84 ellipsoid model):")
print(f"Longitude: {lon:.4f}° = {np.radians(lon):.6f} rad")
print(f"Latitude:  {lat:.4f}° = {np.radians(lat):.6f} rad")
print(f"Altitude:  {alt:.1f} m\n")

# Convert geodetic to ECEF Cartesian
geodetic = np.array([lon, lat, alt])
ecef = bh.position_geodetic_to_ecef(geodetic, bh.AngleFormat.DEGREES)

print("ECEF Cartesian coordinates:")
print(f"x = {ecef[0]:.3f} m")
print(f"y = {ecef[1]:.3f} m")
print(f"z = {ecef[2]:.3f} m")
print(f"Distance from Earth center: {np.linalg.norm(ecef):.3f} m\n")
```


**info**
The conversion from geodetic to ECEF accounts for the ellipsoidal shape using the radius of curvature in the prime vertical and the first eccentricity of the ellipsoid.

## Converting ECEF to Geodetic

The reverse transformation converts Cartesian ECEF coordinates back to geodetic coordinates. This requires an iterative algorithm due to the ellipsoidal geometry:


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

# Convert ECEF Cartesian to geodetic position
ecef_pos = state_ecef[0:3]
geodetic = bh.position_ecef_to_geodetic(ecef_pos, bh.AngleFormat.DEGREES)
print("Geodetic coordinates (WGS84 ellipsoid model):")
print(f"Longitude: {geodetic[0]:.4f}° = {np.radians(geodetic[0]):.6f} rad")
print(f"Latitude:  {geodetic[1]:.4f}° = {np.radians(geodetic[1]):.6f} rad")
print(f"Altitude:  {geodetic[2]:.1f} m")
```


**info**
The ECEF to geodetic conversion uses an iterative algorithm that typically converges in 3-5 iterations to sub-millimeter precision.

## Geodetic vs Geocentric Accuracy

For the same longitude, latitude, and altitude values, geodetic and geocentric coordinates produce different ECEF positions. The difference is smallest near the equator and largest near the poles.

For most applications, it's best to use geodetic coordinates since any computational overhead is negligible compared to the improved accuracy near Earth's surface.

---

## See Also

- [Geodetic Coordinates API Reference](../../library_api/coordinates/geodetic.md) - Complete function documentation
- [Geocentric Transformations](geocentric_transformations.md) - Simpler spherical Earth model
- [Topocentric Transformations](topocentric_transformations.md) - Local horizon coordinate systems