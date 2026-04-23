# Topocentric Coordinate Transformations

Topocentric coordinate systems are local horizon-based reference frames centered on an observer, such as a ground station or radar site. These coordinate systems are essential for satellite tracking, visibility analysis, and determining where to point antennas or telescopes.

Unlike global coordinate systems (ECEF, ECI), topocentric systems define positions relative to a specific location on Earth, making it easy to determine whether a satellite is visible and where to look in the sky.

For complete API details, see the [Topocentric Coordinates API Reference](../../library_api/coordinates/topocentric.md).

## Topocentric Coordinate Systems

Brahe supports two local horizon coordinate systems:

### ENZ (East-North-Zenith)

- **East** (E): Positive toward geographic east
- **North** (N): Positive toward geographic north
- **Zenith** (Z): Positive upward (toward the sky)

This is the most common topocentric system for satellite tracking and is aligned with geographic directions.

### SEZ (South-East-Zenith)

- **South** (S): Positive toward geographic south
- **East** (E): Positive toward geographic east
- **Zenith** (Z): Positive upward (toward the sky)

The SEZ system is sometimes used in radar and missile tracking applications. The main difference from ENZ is that the first two axes are rotated 180° around the zenith axis.

**info**
Both ENZ and SEZ use a right-handed coordinate system with the zenith axis pointing up. The choice between them is typically driven by convention in your specific field or application.

## Station Location Interpretation

When specifying the observer (ground station) location, you must choose whether the coordinates represent:

- **Geodetic** (`EllipsoidalConversionType.GEODETIC`): Station coordinates use WGS84 ellipsoid (recommended for accuracy)
- **Geocentric** (`EllipsoidalConversionType.GEOCENTRIC`): Station coordinates use spherical Earth model

For ground stations, geodetic interpretation is almost always preferred for accuracy.

## ENZ Transformations

### Converting ECEF to ENZ

To get the position of an object relative to a location, you need to convert the object's ECEF position to the local ENZ frame centered on the location:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define ground station location in geodetic coordinates
# Stanford University: (lon=-122.17329°, lat=37.42692°, alt=32.0m)
lon_deg = -122.17329
lat_deg = 37.42692
alt_m = 32.0

print("Ground Station (Stanford):")
print(f"Longitude: {lon_deg:.5f}° = {np.radians(lon_deg):.6f} rad")
print(f"Latitude:  {lat_deg:.5f}° = {np.radians(lat_deg):.6f} rad")
print(f"Altitude:  {alt_m:.1f} m\n")

# Convert ground station to ECEF
geodetic_station = np.array([lon_deg, lat_deg, alt_m])
station_ecef = bh.position_geodetic_to_ecef(geodetic_station, bh.AngleFormat.DEGREES)

print("Ground Station ECEF:")
print(f"x = {station_ecef[0]:.3f} m")
print(f"y = {station_ecef[1]:.3f} m")
print(f"z = {station_ecef[2]:.3f} m\n")

# Define satellite in sun-synchronous orbit at 500 km altitude
# SSO orbit passes over Stanford at approximately 10:30 AM local time
oe = np.array([bh.R_EARTH + 500e3, 0.001, 97.8, 240.0, 0.0, 90.0])

# Define epoch when satellite passes near Stanford (Jan 1, 2024, 17:05 UTC)
epoch = bh.Epoch.from_datetime(2024, 1, 1, 17, 5, 0.0, 0.0, bh.TimeSystem.UTC)

# Convert orbital elements to ECI state
sat_state_eci = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

# Convert ECI state to ECEF at the given epoch
sat_state_ecef = bh.state_eci_to_ecef(epoch, sat_state_eci)
sat_ecef = sat_state_ecef[0:3]  # Extract position only

year, month, day, hour, minute, second, ns = epoch.to_datetime()
print(f"Epoch: {year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:06.3f} UTC")
print("Satellite ECEF:")
print(f"x = {sat_ecef[0]:.3f} m")
print(f"y = {sat_ecef[1]:.3f} m")
print(f"z = {sat_ecef[2]:.3f} m\n")

# Convert satellite position to ENZ coordinates relative to ground station
enz = bh.relative_position_ecef_to_enz(
    station_ecef, sat_ecef, bh.EllipsoidalConversionType.GEODETIC
)

print("Satellite position in ENZ frame (relative to Stanford):")
print(f"East:   {enz[0] / 1000:.3f} km")
print(f"North:  {enz[1] / 1000:.3f} km")
print(f"Zenith: {enz[2] / 1000:.3f} km")
print(f"Range:  {np.linalg.norm(enz) / 1000:.3f} km")
```


### Converting ENZ to ECEF

The reverse transformation converts a relative ENZ position back to an absolute ECEF position:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define ground station location in geodetic coordinates
# Stanford University: (lon=-122.17329°, lat=37.42692°, alt=32.0m)
lon_deg = -122.17329
lat_deg = 37.42692
alt_m = 32.0

print("Ground Station (Stanford):")
print(f"Longitude: {lon_deg:.5f}° = {np.radians(lon_deg):.6f} rad")
print(f"Latitude:  {lat_deg:.5f}° = {np.radians(lat_deg):.6f} rad")
print(f"Altitude:  {alt_m:.1f} m\n")

# Convert ground station to ECEF
geodetic_station = np.array([lon_deg, lat_deg, alt_m])
station_ecef = bh.position_geodetic_to_ecef(geodetic_station, bh.AngleFormat.DEGREES)

print("Ground Station ECEF:")
print(f"x = {station_ecef[0]:.3f} m")
print(f"y = {station_ecef[1]:.3f} m")
print(f"z = {station_ecef[2]:.3f} m\n")

# Define relative position in ENZ coordinates
# Example: 50 km East, 100 km North, 200 km Up from station
enz = np.array([50e3, 100e3, 200e3])

print("Relative position in ENZ frame:")
print(f"East:   {enz[0] / 1000:.1f} km")
print(f"North:  {enz[1] / 1000:.1f} km")
print(f"Zenith: {enz[2] / 1000:.1f} km\n")

# Convert ENZ relative position to absolute ECEF position
target_ecef = bh.relative_position_enz_to_ecef(
    station_ecef, enz, bh.EllipsoidalConversionType.GEODETIC
)

print("Target position in ECEF:")
print(f"x = {target_ecef[0]:.3f} m")
print(f"y = {target_ecef[1]:.3f} m")
print(f"z = {target_ecef[2]:.3f} m")
print(f"Distance from Earth center: {np.linalg.norm(target_ecef) / 1000:.3f} km")
```


## SEZ Transformations

### Converting ECEF to SEZ

Similar to ENZ, you can convert ECEF positions to the SEZ frame:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define ground station location in geodetic coordinates
# Stanford University: (lon=-122.17329°, lat=37.42692°, alt=32.0m)
lon_deg = -122.17329
lat_deg = 37.42692
alt_m = 32.0

print("Ground Station (Stanford):")
print(f"Longitude: {lon_deg:.5f}° = {np.radians(lon_deg):.6f} rad")
print(f"Latitude:  {lat_deg:.5f}° = {np.radians(lat_deg):.6f} rad")
print(f"Altitude:  {alt_m:.1f} m\n")

# Convert ground station to ECEF
geodetic_station = np.array([lon_deg, lat_deg, alt_m])
station_ecef = bh.position_geodetic_to_ecef(geodetic_station, bh.AngleFormat.DEGREES)

print("Ground Station ECEF:")
print(f"x = {station_ecef[0]:.3f} m")
print(f"y = {station_ecef[1]:.3f} m")
print(f"z = {station_ecef[2]:.3f} m\n")

# Define satellite in sun-synchronous orbit at 500 km altitude
# SSO orbit passes over Stanford at approximately 10:30 AM local time
oe = np.array([bh.R_EARTH + 500e3, 0.001, 97.8, 240.0, 0.0, 90.0])

# Define epoch when satellite passes near Stanford (Jan 1, 2024, 17:05 UTC)
epoch = bh.Epoch.from_datetime(2024, 1, 1, 17, 5, 0.0, 0.0, bh.TimeSystem.UTC)

# Convert orbital elements to ECI state
sat_state_eci = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

# Convert ECI state to ECEF at the given epoch
sat_state_ecef = bh.state_eci_to_ecef(epoch, sat_state_eci)
sat_ecef = sat_state_ecef[0:3]  # Extract position only

year, month, day, hour, minute, second, ns = epoch.to_datetime()
print(f"Epoch: {year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:06.3f} UTC")
print("Satellite ECEF:")
print(f"x = {sat_ecef[0]:.3f} m")
print(f"y = {sat_ecef[1]:.3f} m")
print(f"z = {sat_ecef[2]:.3f} m\n")

# Convert satellite position to SEZ coordinates relative to ground station
sez = bh.relative_position_ecef_to_sez(
    station_ecef, sat_ecef, bh.EllipsoidalConversionType.GEODETIC
)

print("Satellite position in SEZ frame (relative to Stanford):")
print(f"South:  {sez[0] / 1000:.3f} km")
print(f"East:   {sez[1] / 1000:.3f} km")
print(f"Zenith: {sez[2] / 1000:.3f} km")
print(f"Range:  {np.linalg.norm(sez) / 1000:.3f} km")
```


### Converting SEZ to ECEF

The reverse transformation converts a relative SEZ position back to an absolute ECEF position:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define ground station location in geodetic coordinates
# Stanford University: (lon=-122.17329°, lat=37.42692°, alt=32.0m)
lon_deg = -122.17329
lat_deg = 37.42692
alt_m = 32.0

print("Ground Station (Stanford):")
print(f"Longitude: {lon_deg:.5f}° = {np.radians(lon_deg):.6f} rad")
print(f"Latitude:  {lat_deg:.5f}° = {np.radians(lat_deg):.6f} rad")
print(f"Altitude:  {alt_m:.1f} m\n")

# Convert ground station to ECEF
geodetic_station = np.array([lon_deg, lat_deg, alt_m])
station_ecef = bh.position_geodetic_to_ecef(geodetic_station, bh.AngleFormat.DEGREES)

print("Ground Station ECEF:")
print(f"x = {station_ecef[0]:.3f} m")
print(f"y = {station_ecef[1]:.3f} m")
print(f"z = {station_ecef[2]:.3f} m\n")

# Define relative position in SEZ coordinates
# Example: 30 km South, 50 km East, 100 km Up from station
sez = np.array([30e3, 50e3, 100e3])

print("Relative position in SEZ frame:")
print(f"South:  {sez[0] / 1000:.1f} km")
print(f"East:   {sez[1] / 1000:.1f} km")
print(f"Zenith: {sez[2] / 1000:.1f} km\n")

# Convert SEZ relative position to absolute ECEF position
target_ecef = bh.relative_position_sez_to_ecef(
    station_ecef, sez, bh.EllipsoidalConversionType.GEODETIC
)

print("Target position in ECEF:")
print(f"x = {target_ecef[0]:.3f} m")
print(f"y = {target_ecef[1]:.3f} m")
print(f"z = {target_ecef[2]:.3f} m")
print(f"Distance from Earth center: {np.linalg.norm(target_ecef) / 1000:.3f} km")
```


## Azimuth and Elevation from Topocentric Coordinates

For object tracking, it's often more intuitive to work with azimuth (compass direction) and elevation (angle above the horizon) rather than Cartesian ENZ or SEZ coordinates. Both ENZ and SEZ topocentric systems can be converted to azimuth-elevation-range format.

### From ENZ Coordinates

Convert ENZ positions to azimuth (measured clockwise from North), elevation (angle above horizon), and range:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define several relative positions in ENZ coordinates
test_cases = [
    ("Directly overhead", np.array([0.0, 0.0, 100e3])),
    ("North horizon", np.array([0.0, 100e3, 0.0])),
    ("East horizon", np.array([100e3, 0.0, 0.0])),
    ("South horizon", np.array([0.0, -100e3, 0.0])),
    ("West horizon", np.array([-100e3, 0.0, 0.0])),
    ("Northeast at 45° elevation", np.array([50e3, 50e3, 70.7e3])),
]

print("Converting ENZ coordinates to Azimuth-Elevation-Range:\n")

for name, enz in test_cases:
    # Convert to azimuth-elevation-range
    azel = bh.position_enz_to_azel(enz, bh.AngleFormat.DEGREES)

    print(f"{name}:")
    print(
        f"  ENZ:   E={enz[0] / 1000:.1f}km, N={enz[1] / 1000:.1f}km, Z={enz[2] / 1000:.1f}km"
    )
    print(
        f"  Az/El: Az={azel[0]:.1f}°, El={azel[1]:.1f}°, Range={azel[2] / 1000:.1f}km\n"
    )
```


**info**
Azimuth is measured clockwise from North (0° = North, 90° = East, 180° = South, 270° = West). Elevation is the angle above the horizon (0° = horizon, 90° = directly overhead).

### From SEZ Coordinates

The same conversion is available from SEZ coordinates:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define several relative positions in SEZ coordinates
test_cases = [
    ("Directly overhead", np.array([0.0, 0.0, 100e3])),
    ("North horizon", np.array([-100e3, 0.0, 0.0])),
    ("East horizon", np.array([0.0, 100e3, 0.0])),
    ("South horizon", np.array([100e3, 0.0, 0.0])),
    ("West horizon", np.array([0.0, -100e3, 0.0])),
    ("Northeast at 45° elevation", np.array([-50e3, 50e3, 70.7e3])),
]

print("Converting SEZ coordinates to Azimuth-Elevation-Range:\n")

for name, sez in test_cases:
    # Convert to azimuth-elevation-range
    azel = bh.position_sez_to_azel(sez, bh.AngleFormat.DEGREES)

    print(f"{name}:")
    print(
        f"  SEZ:   S={sez[0] / 1000:.1f}km, E={sez[1] / 1000:.1f}km, Z={sez[2] / 1000:.1f}km"
    )
    print(
        f"  Az/El: Az={azel[0]:.1f}°, El={azel[1]:.1f}°, Range={azel[2] / 1000:.1f}km\n"
    )
```


**info**
Both ENZ and SEZ produce identical azimuth-elevation-range results for the same physical position. The choice between them is purely a matter of intermediate representation.

---

## See Also

- [Topocentric Coordinates API Reference](../../library_api/coordinates/topocentric.md) - Complete function documentation
- [Geodetic Transformations](geodetic_transformations.md) - Converting station locations to ECEF
- [Frame Transformations](../../library_api/frames/index.md) - Converting satellite positions from ECI to ECEF
- Access Analysis - Higher-level tools for computing satellite visibility windows