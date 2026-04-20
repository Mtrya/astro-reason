# Magnetic Field Models

Brahe computes Earth's geomagnetic field using spherical harmonic models. You provide a geodetic position and an epoch, and get back a three-component magnetic field vector in your choice of output frame. Two models are available: **IGRF-14** for broad historical coverage and **WMMHR-2025** for high spatial resolution near the current epoch.

For a complete listing of all function signatures and parameters, see the [IGRF API Reference](../../library_api/earth_models/igrf.md) and [WMMHR API Reference](../../library_api/earth_models/wmmhr.md).

## Computing the Field

The simplest call takes an epoch, a geodetic position `(longitude, latitude, altitude)`, and an angle format. The result is a three-element vector `[B_east, B_north, B_zenith]` in nanoTesla:

```python
import brahe as bh
import numpy as np

# Compute the IGRF magnetic field at 60 degrees latitude, 400 km altitude
epc = bh.Epoch(2025, 1, 1, 0, 0, 0.0, time_system=bh.UTC)
x_geod = np.array([0.0, 60.0, 400e3])  # lon=0 deg, lat=60 deg, alt=400 km

b_enz = bh.igrf_geodetic_enz(epc, x_geod, bh.AngleFormat.DEGREES)

print("IGRF-14 magnetic field at (lon=0, lat=60, alt=400 km)")
print(f"  B_east:   {b_enz[0]:10.1f} nT")
print(f"  B_north:  {b_enz[1]:10.1f} nT")
print(f"  B_zenith: {b_enz[2]:10.1f} nT")

# Compute derived quantities
b_h = np.sqrt(b_enz[0] ** 2 + b_enz[1] ** 2)  # Horizontal intensity
b_total = np.linalg.norm(b_enz)  # Total intensity
inclination = np.degrees(np.arctan2(-b_enz[2], b_h))  # Positive downward
declination = np.degrees(np.arctan2(b_enz[0], b_enz[1]))

print(f"\n  Horizontal intensity: {b_h:10.1f} nT")
print(f"  Total intensity:     {b_total:10.1f} nT")
print(f"  Inclination:         {inclination:10.2f} deg")
print(f"  Declination:         {declination:10.2f} deg")
```


The output components are:

- **$B_\text{east}$** -- eastward component (positive east)
- **$B_\text{north}$** -- northward component (positive north, tangent to the reference surface)
- **$B_\text{zenith}$** -- vertical component (positive upward, perpendicular to the reference surface)

From these you can derive the standard magnetic elements: horizontal intensity $H = \sqrt{B_e^2 + B_n^2}$, total intensity $F = |B|$, inclination $I = \arctan(-B_z / H)$ (positive when the field dips below horizontal), and declination $D = \arctan(B_e / B_n)$ (the compass deviation from true north).

## Output Frames

Each model offers three output frame variants. All take the same geodetic input -- only the frame of the returned field vector changes.

The **geodetic ENZ** functions (`igrf_geodetic_enz`, `wmmhr_geodetic_enz`) return the field relative to the WGS84 ellipsoid surface. "Zenith" points along the ellipsoid normal. This is the standard frame for geomagnetic applications and matches the convention used by NOAA's magnetic field calculators.

The **geocentric ENZ** functions (`igrf_geocentric_enz`, `wmmhr_geocentric_enz`) return the field relative to a geocentric sphere. "Zenith" points radially outward from Earth's center. At the equator the two frames coincide; at high latitudes they differ by up to ~0.2 degrees due to Earth's oblateness.

The **ECEF** functions (`igrf_ecef`, `wmmhr_ecef`) return the field in the Earth-Centered Earth-Fixed frame. This is useful when you need the field expressed in the same frame as satellite position vectors, for example when computing magnetic torques on a spacecraft.

## IGRF vs WMMHR

**IGRF-14** (International Geomagnetic Reference Field) covers 1900 to 2030. It models spherical harmonic degrees 1 through 13, capturing Earth's core field at ~3000 km spatial resolution. Coefficients are provided every 5 years and interpolated linearly for dates in between. Use IGRF when you need magnetic field values over long time spans or at historical epochs.

**WMMHR-2025** (World Magnetic Model High Resolution) covers approximately 2025 to 2030. It extends to spherical harmonic degree 133, adding crustal magnetic anomalies at ~300 km resolution on top of the core field. Use WMMHR when you need the most accurate current field values, particularly at or near Earth's surface where crustal contributions matter.

```python
import brahe as bh
import numpy as np

epc = bh.Epoch(2025, 1, 1, 0, 0, 0.0, time_system=bh.UTC)
x_geod = np.array([120.0, 0.0, 0.0])  # lon=120 deg, lat=0, alt=0 m (equator)

# Full resolution (degree 133) -- includes crustal field detail
b_full = bh.wmmhr_geodetic_enz(epc, x_geod, bh.AngleFormat.DEGREES)

print("WMMHR-2025 at (lon=120, lat=0, alt=0) -- Full resolution (nmax=133)")
print(f"  B_east:   {b_full[0]:10.1f} nT")
print(f"  B_north:  {b_full[1]:10.1f} nT")
print(f"  B_zenith: {b_full[2]:10.1f} nT")

b_h = np.sqrt(b_full[0] ** 2 + b_full[1] ** 2)
b_total = np.linalg.norm(b_full)
inclination = np.degrees(np.arctan2(-b_full[2], b_h))
declination = np.degrees(np.arctan2(b_full[0], b_full[1]))

print(f"\n  Total intensity: {b_total:10.1f} nT")
print(f"  Inclination:     {inclination:10.2f} deg")
print(f"  Declination:     {declination:10.2f} deg")

# Truncated resolution (degree 13) -- core field only, like standard WMM
b_low = bh.wmmhr_geodetic_enz(epc, x_geod, bh.AngleFormat.DEGREES, nmax=13)
diff = np.linalg.norm(b_full - b_low)

print("\nTruncated resolution (nmax=13):")
print(f"  B_east:   {b_low[0]:10.1f} nT")
print(f"  B_north:  {b_low[1]:10.1f} nT")
print(f"  B_zenith: {b_low[2]:10.1f} nT")
print(f"\n  Difference from full resolution: {diff:.1f} nT")
```


The `nmax` parameter on WMMHR functions controls the maximum spherical harmonic degree. Setting `nmax=13` gives results comparable to standard WMM/IGRF resolution. The default (`None` / `None`) uses the full 133 degrees.

## Using with Satellite ECEF Positions

Satellite positions are often available in ECEF or ECI coordinates rather than geodetic. The typical workflow is: convert the ECEF position to geodetic using `position_ecef_to_geodetic`, then call the magnetic field function with the geodetic result.

```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define a LEO orbit and compute the ECEF state
epc = bh.Epoch(2025, 3, 15, 12, 0, 0.0, time_system=bh.UTC)
oe = np.array([bh.R_EARTH + 500e3, 0.01, 51.6, 45.0, 30.0, 60.0])  # ISS-like orbit
state_eci = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)
state_ecef = bh.state_eci_to_ecef(epc, state_eci)

# Convert ECEF position to geodetic coordinates
x_ecef = state_ecef[0:3]
x_geod = bh.position_ecef_to_geodetic(x_ecef, bh.AngleFormat.DEGREES)

print(f"Epoch: {epc}")
print(
    f"Geodetic position: lon={x_geod[0]:.2f} deg, lat={x_geod[1]:.2f} deg, alt={x_geod[2] / 1e3:.1f} km"
)

# Compute the magnetic field at the satellite location using IGRF
b_enz = bh.igrf_geodetic_enz(epc, x_geod, bh.AngleFormat.DEGREES)
b_total = np.linalg.norm(b_enz)

print("\nIGRF field at satellite:")
print(f"  B_east:   {b_enz[0]:10.1f} nT")
print(f"  B_north:  {b_enz[1]:10.1f} nT")
print(f"  B_zenith: {b_enz[2]:10.1f} nT")
print(f"  |B|:      {b_total:10.1f} nT")

# Get the field in ECEF frame (useful for torque calculations in the body frame)
b_ecef = bh.igrf_ecef(epc, x_geod, bh.AngleFormat.DEGREES)
print("\nIGRF field in ECEF frame:")
print(f"  B_x: {b_ecef[0]:10.1f} nT")
print(f"  B_y: {b_ecef[1]:10.1f} nT")
print(f"  B_z: {b_ecef[2]:10.1f} nT")
```


**info**
The input altitude is always in **meters** (SI), consistent with all other Brahe functions. The models work internally in kilometers but handle the conversion automatically.

## See Also

- [IGRF API Reference](../../library_api/earth_models/igrf.md) -- Full function signatures for IGRF-14
- [WMMHR API Reference](../../library_api/earth_models/wmmhr.md) -- Full function signatures for WMMHR-2025
- [Geodetic Coordinates](../coordinates/geodetic_transformations.md) -- Converting between ECEF and geodetic
- [Reference Frame Transformations](../frames/eci_ecef.md) -- ECI to ECEF conversion for satellite positions