# Walker Constellations

Walker constellations are satellite constellations designed for optimal coverage using symmetric orbital plane distributions. Named after John Walker, who formalized the notation in 1984, these patterns are fundamental to modern satellite system design.

## Walker Notation i:T/P/F

Walker constellations use **i:T/P/F** notation where:

- **i** (Inclination) - Orbital inclination in degrees
- **T** (Total) - Total number of satellites in the constellation
- **P** (Planes) - Number of equally-spaced orbital planes
- **F** (Phasing) - Relative phase difference between adjacent planes (0 to P-1)

All satellites share identical:

- Semi-major axis (altitude)
- Eccentricity (typically circular, e ≈ 0)
- Inclination

## Mathematical Formulation

### RAAN Distribution

For **P** orbital planes, the Right Ascension of Ascending Node (RAAN) for plane **k** is:

$$\Omega_k = \Omega_0 + k \cdot \frac{\Delta\Omega_\text{spread}}{P}$$

where:

- $\Omega_0$ is the reference RAAN
- $\Delta\Omega_\text{spread}$ is 360° for Walker Delta, 180° for Walker Star
- $k$ is the plane index (0 to $P-1$)

### Mean Anomaly Distribution

For **S = T/P** satellites per plane, the mean anomaly for satellite **j** in plane **k** is:

$$M_{k,j} = M_0 + j \cdot \frac{360°}{S} + k \cdot F \cdot \frac{360°}{T}$$

where:

- $M_0$ is the reference mean anomaly
- $j$ is the satellite index within the plane (0 to $S-1$)
- $F$ is the phasing factor

### Constraints

- $T$ must be evenly divisible by $P$
- $F$ must be in the range $[0, P-1]$

## Walker Delta vs Walker Star

Brahe supports two Walker patterns:

| Pattern | RAAN Spread | Plane Spacing | Coverage |
|---------|-------------|---------------|----------|
| **Walker Delta** | 360° | $\Delta\Omega = \frac{360°}{P}$ | Global |
| **Walker Star** | 180° | $\Delta\Omega = \frac{180°}{P}$ | Polar |

**Walker Delta** distributes planes around the full 360° of RAAN, providing global coverage. This is the pattern used by GPS, Galileo, and GLONASS.

**Walker Star** distributes planes across only 180° of RAAN, concentrating coverage at polar regions. This pattern is used by Iridium for its polar LEO constellation.

## Generating Walker Constellations

### Basic Walker Delta (GPS-like)


```python
import brahe as bh

bh.initialize_eop()

# Create epoch for constellation
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# Create a GPS-like 24:6:2 Walker Delta constellation
# T:P:F = 24:6:2 means:
#   - T = 24 total satellites
#   - P = 6 orbital planes
#   - F = 2 phasing factor
walker = bh.WalkerConstellationGenerator(
    t=24,
    p=6,
    f=2,
    semi_major_axis=bh.R_EARTH + 20200e3,  # GPS altitude
    eccentricity=0.0,
    inclination=55.0,  # GPS inclination
    argument_of_perigee=0.0,
    reference_raan=0.0,
    reference_mean_anomaly=0.0,
    epoch=epoch,
    angle_format=bh.AngleFormat.DEGREES,
    pattern=bh.WalkerPattern.DELTA,
).with_base_name("GPS")

# Print constellation properties
print(f"Total satellites: {walker.total_satellites}")
print(f"Number of planes: {walker.num_planes}")
print(f"Satellites per plane: {walker.satellites_per_plane}")
print(f"Phasing factor: {walker.phasing}")
print(f"Pattern: {walker.pattern}")

# Get orbital elements for the first satellite in each plane
print("\nFirst satellite in each plane:")
for plane in range(walker.num_planes):
    elements = walker.satellite_elements(plane, 0, bh.AngleFormat.DEGREES)
    print(f"  Plane {plane}: RAAN = {elements[3]:.1f} deg, MA = {elements[5]:.1f} deg")

# Generate Keplerian propagators for all satellites
propagators = walker.as_keplerian_propagators(60.0)  # 60 second step size
print(f"\nGenerated {len(propagators)} Keplerian propagators")
print(f"First propagator name: {propagators[0].get_name()}")
print(f"Last propagator name: {propagators[-1].get_name()}")
```


### Walker Star (Iridium-like)


```python
import brahe as bh

bh.initialize_eop()

# Create epoch for constellation
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# Create an Iridium-like 66:6:2 Walker Star constellation
# Walker Star uses 180 degree RAAN spread (vs 360 for Delta)
walker = bh.WalkerConstellationGenerator(
    t=66,
    p=6,
    f=2,
    semi_major_axis=bh.R_EARTH + 780e3,  # Iridium altitude (~780 km)
    eccentricity=0.0,
    inclination=86.4,  # Near-polar inclination
    argument_of_perigee=0.0,
    reference_raan=0.0,
    reference_mean_anomaly=0.0,
    epoch=epoch,
    angle_format=bh.AngleFormat.DEGREES,
    pattern=bh.WalkerPattern.STAR,  # Star pattern uses 180 deg RAAN spread
).with_base_name("IRIDIUM")

# Print constellation properties
print(f"Total satellites: {walker.total_satellites}")
print(f"Number of planes: {walker.num_planes}")
print(f"Satellites per plane: {walker.satellites_per_plane}")
print(f"Phasing factor: {walker.phasing}")
print(f"Pattern: {walker.pattern}")

# Show RAAN spacing difference from Walker Delta
# Walker Star: 180 / P = 180 / 6 = 30 degree spacing
# Walker Delta: 360 / P = 360 / 6 = 60 degree spacing
print("\nFirst satellite in each plane (Walker Star):")
for plane in range(walker.num_planes):
    elements = walker.satellite_elements(plane, 0, bh.AngleFormat.DEGREES)
    print(f"  Plane {plane}: RAAN = {elements[3]:.1f} deg")

# Compare with what Walker Delta would give
print("\nRemark: Walker Delta with same P=6 would have 60 deg RAAN spacing")
print("Walker Star spreads planes over 180 deg (0-150 deg)")
print("Walker Delta spreads planes over 360 deg (0-300 deg)")

# Generate Keplerian propagators
propagators = walker.as_keplerian_propagators(60.0)
print(f"\nGenerated {len(propagators)} Keplerian propagators")
```


## Using Different Propagators

The `WalkerConstellationGenerator` can create propagators using different propagation methods:

### Keplerian Propagators

For analytical two-body propagation:

```
propagators = walker.as_keplerian_propagators(step_size=60.0)  # 60 second steps
```

### SGP4 Propagators

For TLE-based propagation with perturbations:

```
propagators = walker.as_sgp_propagators(
    step_size=60.0,
    bstar=0.0,      # Drag coefficient
    ndt2=0.0,       # Mean motion derivative / 2
    nddt6=0.0,      # Mean motion 2nd derivative / 6
)
```

### Numerical Propagators

For high-fidelity force-model propagation:

```
prop_config = bh.NumericalPropagationConfig.default()
force_config = bh.ForceModelConfig.earth_gravity()

propagators = walker.as_numerical_propagators(prop_config, force_config)
```

## Visualizing Constellations

### Walker Delta Visualization

The Walker Delta pattern distributes orbital planes evenly around 360° of RAAN:


**Plot Source**

```python
# --8<-- [start:all]
# --8<-- [start:preamble]
import brahe as bh

bh.initialize_eop()
# --8<-- [end:preamble]

# Create epoch for constellation
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# --8<-- [start:create_constellation]
# Create a GPS-like 24:6:2 Walker Delta constellation
walker = bh.WalkerConstellationGenerator(
    t=24,
    p=6,
    f=2,
    semi_major_axis=bh.R_EARTH + 20200e3,  # GPS altitude
    eccentricity=0.0,
    inclination=55.0,  # GPS inclination
    argument_of_perigee=0.0,
    reference_raan=0.0,
    reference_mean_anomaly=0.0,
    epoch=epoch,
    angle_format=bh.AngleFormat.DEGREES,
    pattern=bh.WalkerPattern.DELTA,
).with_base_name("GPS")
# --8<-- [end:create_constellation]

print(f"Created {walker.total_satellites} satellite Walker Delta constellation")
print(f"Orbital planes: {walker.num_planes}")
print(f"RAAN spacing: 360/{walker.num_planes} = {360 / walker.num_planes:.0f} degrees")

# --8<-- [start:propagate]
# Generate Keplerian propagators and propagate for one orbit
propagators = walker.as_keplerian_propagators(60.0)

# Propagate each satellite for one complete orbit
for prop in propagators:
    # Get semi-major axis from Keplerian elements [a, e, i, raan, argp, M]
    koe = prop.state_koe_osc(prop.initial_epoch, bh.AngleFormat.RADIANS)
    orbital_period = bh.orbital_period(koe[0])
    prop.propagate_to(prop.initial_epoch + orbital_period)
# --8<-- [end:propagate]

print(f"\nPropagated all {len(propagators)} satellites for one orbital period")

# --8<-- [start:visualization]
# Create interactive 3D plot with Earth texture
fig = bh.plot_trajectory_3d(
    [
        {
            "trajectory": prop.trajectory,
            "mode": "markers",
            "size": 2,
            "label": prop.get_name(),
        }
        for prop in propagators
    ],
    units="km",
    show_earth=True,
    earth_texture="natural_earth_50m",
    backend="plotly",
    view_azimuth=45.0,
    view_elevation=30.0,
    view_distance=2.0,
)
# --8<-- [end:visualization]
# --8<-- [end:all]

# ============================================================================
# Plot Output Section (for documentation generation)
# ============================================================================

# ruff: noqa: E402
import os
import pathlib
import sys

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "plots"))
from brahe_theme import save_themed_html

# Configuration
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# Save the figure as themed HTML
light_path, dark_path = save_themed_html(fig, OUTDIR / SCRIPT_NAME)
print(f"\n✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")
```

### Walker Star Visualization

The Walker Star pattern concentrates planes over 180° of RAAN for polar coverage:


**Plot Source**

```python
# --8<-- [start:all]
# --8<-- [start:preamble]
import brahe as bh

bh.initialize_eop()
# --8<-- [end:preamble]

# Create epoch for constellation
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# --8<-- [start:create_constellation]
# Create an Iridium-like 66:6:2 Walker Star constellation
walker = bh.WalkerConstellationGenerator(
    t=66,
    p=6,
    f=2,
    semi_major_axis=bh.R_EARTH + 780e3,  # Iridium altitude
    eccentricity=0.0,
    inclination=86.4,  # Near-polar inclination
    argument_of_perigee=0.0,
    reference_raan=0.0,
    reference_mean_anomaly=0.0,
    epoch=epoch,
    angle_format=bh.AngleFormat.DEGREES,
    pattern=bh.WalkerPattern.STAR,  # 180 deg RAAN spread
).with_base_name("IRIDIUM")
# --8<-- [end:create_constellation]

print(f"Created {walker.total_satellites} satellite Walker Star constellation")
print(f"Orbital planes: {walker.num_planes}")
print(f"RAAN spacing: 180/{walker.num_planes} = {180 / walker.num_planes:.0f} degrees")

# --8<-- [start:propagate]
# Generate Keplerian propagators and propagate for one orbit
propagators = walker.as_keplerian_propagators(60.0)

# Propagate each satellite for one complete orbit
for prop in propagators:
    # Get semi-major axis from Keplerian elements [a, e, i, raan, argp, M]
    koe = prop.state_koe_osc(prop.initial_epoch, bh.AngleFormat.RADIANS)
    orbital_period = bh.orbital_period(koe[0])
    prop.propagate_to(prop.initial_epoch + orbital_period)
# --8<-- [end:propagate]

print(f"\nPropagated all {len(propagators)} satellites for one orbital period")

# --8<-- [start:visualization]
# Create interactive 3D plot with Earth texture
fig = bh.plot_trajectory_3d(
    [
        {
            "trajectory": prop.trajectory,
            "mode": "markers",
            "size": 2,
            "label": prop.get_name(),
        }
        for prop in propagators
    ],
    units="km",
    show_earth=True,
    earth_texture="natural_earth_50m",
    backend="plotly",
    view_azimuth=45.0,
    view_elevation=30.0,
    view_distance=2.0,
)
# --8<-- [end:visualization]
# --8<-- [end:all]

# ============================================================================
# Plot Output Section (for documentation generation)
# ============================================================================

# ruff: noqa: E402
import os
import pathlib
import sys

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "plots"))
from brahe_theme import save_themed_html

# Configuration
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# Save the figure as themed HTML
light_path, dark_path = save_themed_html(fig, OUTDIR / SCRIPT_NAME)
print(f"\n✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")
```

---

## See Also

- [Walker Constellations API Reference](../../library_api/orbits/walker.md) - Complete API documentation
- [Keplerian Elements](properties.md) - Orbital element fundamentals
- [SGP4 Propagation](../orbit_propagation/sgp_propagation.md) - TLE-based propagation
- [Numerical Propagation](../orbit_propagation/numerical_propagation/index.md) - High-fidelity propagation
- [3D Trajectory Plotting](../plots/3d_trajectory.md) - Trajectory visualization