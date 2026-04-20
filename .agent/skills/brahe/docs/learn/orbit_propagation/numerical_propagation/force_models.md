# Force Models

The `ForceModelConfig` (Python) / `ForceModelConfig` (Rust) defines which physical forces affect the spacecraft during propagation. Brahe provides preset configurations for common scenarios and allows custom configurations for specific requirements.

For API details, see the [ForceModelConfig API Reference](../../../library_api/propagators/force_model_config.md).

## Full Example

here is a complete example creating a `ForceModelConfig` exercising all available configuration options:


```python
import brahe as bh

# Create a fully-configured force model
force_config = bh.ForceModelConfig(
    # Gravity: Spherical harmonic model (EGM2008, 20x20 degree/order)
    gravity=bh.GravityConfiguration.spherical_harmonic(
        degree=20,
        order=20,
        model_type=bh.GravityModelType.EGM2008_360,
    ),
    # Atmospheric drag: Harris-Priester model with parameter indices
    drag=bh.DragConfiguration(
        model=bh.AtmosphericModel.HARRIS_PRIESTER,
        area=bh.ParameterSource.parameter_index(1),  # Index into parameter vector
        cd=bh.ParameterSource.parameter_index(2),
    ),
    # Solar radiation pressure: Conical eclipse model
    srp=bh.SolarRadiationPressureConfiguration(
        area=bh.ParameterSource.parameter_index(3),
        cr=bh.ParameterSource.parameter_index(4),
        eclipse_model=bh.EclipseModel.CONICAL,
    ),
    # Third-body: Sun and Moon with DE440s ephemeris
    third_body=bh.ThirdBodyConfiguration(
        ephemeris_source=bh.EphemerisSource.DE440s,
        bodies=[bh.ThirdBody.SUN, bh.ThirdBody.MOON],
    ),
    # General relativistic corrections
    relativity=True,
    # Spacecraft mass (can also use parameter_index for estimation)
    mass=bh.ParameterSource.value(1000.0),  # kg
)

print(f"Gravity: {force_config.gravity}")
print(f"Drag: {force_config.drag}")
print(f"SRP: {force_config.srp}")
print(f"Third-body: {force_config.third_body}")
print(f"Relativity: {force_config.relativity}")
print(f"Mass: {force_config.mass}")
```


## Architecture Overview

### Configuration Hierarchy

`ForceModelConfig` is the top-level container that aggregates all force model settings. Each force type has its own configuration struct:

```.no-linenums
ForceModelConfig
├── gravity: GravityConfiguration
│   ├── PointMass
│   └── SphericalHarmonic { source, degree, order }
├── drag: DragConfiguration
│   ├── model: AtmosphericModel
│   ├── area: ParameterSource
│   └── cd: ParameterSource
├── srp: SolarRadiationPressureConfiguration
│   ├── area: ParameterSource
│   ├── cr: ParameterSource
│   └── eclipse_model: EclipseModel
├── third_body: ThirdBodyConfiguration
│   ├── ephemeris_source: EphemerisSource
│   └── bodies: Vec<ThirdBody>
├── relativity: bool
└── mass: ParameterSource
```

Each sub-configuration is optional (`None` disables that force). The configuration is captured at propagator construction time and remains immutable during propagation.

### Parameter Sources

Spacecraft parameters (mass $m$, drag area $A_d$, coefficient of drag $C_d$, SRP area $A_{SRP}$, coefficient of reflectivity $C_r$) can be specified in two ways via `ParameterSource`:

- **`Value(f64)`** - Fixed constant embedded at construction. The value is baked into the dynamics function and cannot change during propagation.

- **`ParameterIndex(usize)`** - Index into an parameter vector. This allows parameters to be varied or estimated as part of orbit determination or sensitivity analysis.

The [Parameter Configuration](#parameter-configuration) section below provides detailed examples of both approaches.

## Force Model Components

### Gravity Configuration

Gravity is the primary force in orbital mechanics. Brahe supports two gravity models:

**Point Mass**: Simple two-body central gravity. Fast but ignores Earth's non-spherical shape.

$$
\mathbf{a} = -\frac{GM}{r^3} \mathbf{r}
$$


```python
import brahe as bh

# Point mass gravity is configured using GravityConfiguration.point_mass()
# This uses only central body gravity (mu/r^2) - no spherical harmonics

# Create point mass gravity configuration
gravity = bh.GravityConfiguration.point_mass()

# Use two_body() preset which includes point mass gravity
force_config = bh.ForceModelConfig.two_body()
```


**Spherical Harmonics**: High-fidelity gravity using EGM2008, GGM05S, or user-defined `.gfc` model. Degree and order control accuracy vs computation time.

$$
\mathbf{a} = -\nabla V, \quad V(r, \phi, \lambda) = \frac{GM}{r} \sum_{n=0}^{N} \sum_{m=0}^{n} \left(\frac{R_E}{r}\right)^n \bar{P}_{nm}(\sin\phi) \left(\bar{C}_{nm}\cos(m\lambda) + \bar{S}_{nm}\sin(m\lambda)\right)
$$


```python
import brahe as bh

# ==============================================================================
# Packaged Gravity Models
# ==============================================================================

# EGM2008 - High-fidelity NGA model (360x360 max)
gravity_egm2008 = bh.GravityConfiguration.spherical_harmonic(
    degree=20, order=20, model_type=bh.GravityModelType.EGM2008_360
)

# GGM05S - GRACE mission model (180x180 max)
gravity_ggm05s = bh.GravityConfiguration.spherical_harmonic(
    degree=20, order=20, model_type=bh.GravityModelType.GGM05S
)

# JGM3 - Legacy model, fast computation (70x70 max)
gravity_jgm3 = bh.GravityConfiguration.spherical_harmonic(
    degree=20, order=20, model_type=bh.GravityModelType.JGM3
)

# ==============================================================================
# Custom Model from File
# ==============================================================================

# Load custom gravity model from GFC format file
# GravityModelType.from_file validates the path exists
custom_model_type = bh.GravityModelType.from_file("data/gravity_models/EGM2008_360.gfc")
gravity_custom = bh.GravityConfiguration.spherical_harmonic(
    degree=20, order=20, model_type=custom_model_type
)
```


### Atmospheric Drag

Atmospheric drag is significant for LEO satellites.

$$
\mathbf{a}_D = -\frac{1}{2} C_D \frac{A}{m} \rho v_{rel}^2 \mathbf{\hat{v}}_{rel}
$$

where $\rho$ is atmospheric density, $v_{rel}$ is velocity relative to the atmosphere, $C_D$ is drag coefficient, and $A/m$ is area-to-mass ratio.

Three atmospheric models are available:

**Harris-Priester**: Fast model with diurnal density variations. Valid 100-1000 km altitude. No space weather data required.


```python
import brahe as bh

# Harris-Priester atmospheric drag configuration
# - Valid for altitudes 100-1000 km
# - Accounts for latitude-dependent diurnal bulge
# - Does not require space weather data (F10.7, Ap)

# Create drag configuration using parameter indices (default layout)
drag_config = bh.DragConfiguration(
    model=bh.AtmosphericModel.HARRIS_PRIESTER,
    area=bh.ParameterSource.parameter_index(1),  # drag_area from params[1]
    cd=bh.ParameterSource.parameter_index(2),  # Cd from params[2]
)
```


**NRLMSISE-00**: High-fidelity empirical model using space weather data. Valid from ground to thermosphere (~1000 km). More computationally intensive.


```python
import brahe as bh

# Initialize space weather data provider
bh.initialize_sw()

# NRLMSISE-00 atmospheric drag configuration
# - Naval Research Laboratory Mass Spectrometer and Incoherent Scatter Radar
# - High-fidelity empirical model
# - Valid from ground to thermospheric heights
# - Uses space weather data (F10.7, Ap) when available
# - More computationally expensive than Harris-Priester

# Create drag configuration with NRLMSISE-00
drag_config = bh.DragConfiguration(
    model=bh.AtmosphericModel.NRLMSISE00,
    area=bh.ParameterSource.parameter_index(1),  # drag_area from params[1]
    cd=bh.ParameterSource.parameter_index(2),  # Cd from params[2]
)
```


**Exponential**: An expontential atmospheric density model defined by which provides a simple approximation that is fast for rough calculations:

$$
\rho(h) = \rho_0 e^{-\frac{h-h_0}{H}}
$$

$\rho_0$ is reference density at altitude $h_0$ and $H$ is scale height.


```python
import brahe as bh

# Create exponential atmospheric model
exp_model = bh.AtmosphericModel.exponential(
    scale_height=53000.0,  # Scale height H in meters (53 km for ~300 km altitude)
    rho0=1.225e-11,  # Reference density at h0 in kg/m^3
    h0=300000.0,  # Reference altitude in meters (300 km)
)

# Create drag configuration with exponential model
drag_config = bh.DragConfiguration(
    model=exp_model,
    area=bh.ParameterSource.parameter_index(1),
    cd=bh.ParameterSource.parameter_index(2),
)
```


### Solar Radiation Pressure

SRP is significant for high-altitude orbits and high area-to-mass ratio spacecraft.

$$
\mathbf{a}_{SRP} = -P_{\odot} C_R \frac{A}{m} \nu \frac{\mathbf{r}_{\odot}}{|\mathbf{r}_{\odot}|}
$$

where $P_{\odot} \approx 4.56 \times 10^{-6}$ N/m² is solar pressure at 1 AU, $C_R$ is reflectivity coefficient, $\nu$ is shadow function (0-1), and $\mathbf{r}_{\odot}$ is the Sun position vector.

Eclipse models determine shadow effects:

- **None**: Always illuminated (fast, inaccurate in shadow)
- **Cylindrical**: Sharp shadow boundary (simple, fast)
- **Conical**: Penumbra and umbra regions (most accurate)


```python
import brahe as bh

# Solar Radiation Pressure configuration
# Parameters:
# - area: Cross-sectional area facing the Sun (m^2)
# - cr: Coefficient of reflectivity (1.0=absorbing to 2.0=perfectly reflecting)
# - eclipse_model: How to handle Earth's shadow

# Option 1: No eclipse model (always illuminated)
# Fast but inaccurate during eclipse periods
srp_cylindrical = bh.SolarRadiationPressureConfiguration(
    area=bh.ParameterSource.parameter_index(3),  # srp_area from params[3]
    cr=bh.ParameterSource.parameter_index(4),  # Cr from params[4]
    eclipse_model=bh.EclipseModel.NONE,
)

# Option 2: Cylindrical shadow model
# Simple and fast, sharp shadow boundary (no penumbra)
srp_cylindrical = bh.SolarRadiationPressureConfiguration(
    area=bh.ParameterSource.parameter_index(3),  # srp_area from params[3]
    cr=bh.ParameterSource.parameter_index(4),  # Cr from params[4]
    eclipse_model=bh.EclipseModel.CYLINDRICAL,
)

# Option 2: Conical shadow model (recommended)
# Accounts for penumbra and umbra regions
srp_conical = bh.SolarRadiationPressureConfiguration(
    area=bh.ParameterSource.parameter_index(3),
    cr=bh.ParameterSource.parameter_index(4),
    eclipse_model=bh.EclipseModel.CONICAL,
)
```


### Third-Body Perturbations

Gravitational attraction from Sun, Moon, and planets causes long-period variations in orbital elements.

$$
\mathbf{a}_{TB} = GM_{b} \left(\frac{\mathbf{r}_b - \mathbf{r}}{|\mathbf{r}_b - \mathbf{r}|^3} - \frac{\mathbf{r}_b}{|\mathbf{r}_b|^3}\right)
$$

where $GM_b$ is the gravitational parameter of the third body, $\mathbf{r}_b$ is its position, and $\mathbf{r}$ is the satellite position.

Ephemeris sources:

- **LowPrecision**: Fast analytical, Sun/Moon only
- **DE440s**: JPL high precision, all planets, 1550-2650 CE
- **DE440**: JPL high precision, all planets, 13200 BCE-17191 CE


```python
import brahe as bh

# Third-body perturbations configuration
# Gravitational attraction from other celestial bodies

# Option 1: Low-precision analytical ephemerides
# Fast but less accurate (~km level errors for Sun/Moon)
# Only Sun and Moon are available
third_body_low = bh.ThirdBodyConfiguration(
    ephemeris_source=bh.EphemerisSource.LowPrecision,
    bodies=[bh.ThirdBody.SUN, bh.ThirdBody.MOON],
)

# Option 2: DE440s high-precision ephemerides (recommended)
# Uses JPL Development Ephemeris 440 (small bodies version)
# ~m level accuracy, valid 1550-2650 CE
# All planets available, ~17 MB file
third_body_de440s = bh.ThirdBodyConfiguration(
    ephemeris_source=bh.EphemerisSource.DE440s,
    bodies=[bh.ThirdBody.SUN, bh.ThirdBody.MOON],
)

# Option 3: DE440 full-precision ephemerides
# Highest accuracy (~mm level), valid 13200 BCE-17191 CE
# All planets available, ~114 MB file
third_body_de440 = bh.ThirdBodyConfiguration(
    ephemeris_source=bh.EphemerisSource.DE440,
    bodies=[bh.ThirdBody.SUN, bh.ThirdBody.MOON],
)

# Option 4: Include all major planets (high-fidelity)
third_body_all_planets = bh.ThirdBodyConfiguration(
    ephemeris_source=bh.EphemerisSource.DE440s,
    bodies=[
        bh.ThirdBody.SUN,
        bh.ThirdBody.MOON,
        bh.ThirdBody.MERCURY,
        bh.ThirdBody.VENUS,
        bh.ThirdBody.MARS,
        bh.ThirdBody.JUPITER,
        bh.ThirdBody.SATURN,
        bh.ThirdBody.URANUS,
        bh.ThirdBody.NEPTUNE,
    ],
)
```


### Relativistic Effects

General relativistic corrections can be enabled via the `relativity` boolean flag. These effects are typically small but can be significant for precision orbit determination.

$$
\mathbf{a} = -\frac{GM}{r^2} \left( \left( 4\frac{GM}{c^2r} - \frac{v^2}{c^2} \right)\mathbf{e}_r + 4\frac{v^2}{c^2}\left(\mathbf{e}_r \cdot \mathbf{e}_v\right)\mathbf{e}_v\right)
$$

where $c$ is the speed of light, $\mathbf{e}_r$ is the radial unit vector, and $\mathbf{e}_v$ is the velocity unit vector.

## Parameter Configuration

Force model parameters (mass, drag area, Cd, etc.) can be specified either as fixed values or as indices into a parameter vector.

### Using Fixed Values

Use `ParameterSource.value()` (Python) / `ParameterSource::Value` (Rust) for parameters that don't change:


```python
import brahe as bh

# ParameterSource.value() creates a fixed constant parameter
# Use when the parameter doesn't change and doesn't need to be estimated

# Example: Fixed drag configuration
# Mass, drag area, and Cd are all constant
drag_config = bh.DragConfiguration(
    model=bh.AtmosphericModel.HARRIS_PRIESTER,
    area=bh.ParameterSource.value(10.0),  # Fixed 10 m^2 drag area
    cd=bh.ParameterSource.value(2.2),  # Fixed Cd of 2.2
)

# Example: Fixed SRP configuration
srp_config = bh.SolarRadiationPressureConfiguration(
    area=bh.ParameterSource.value(15.0),  # Fixed 15 m^2 SRP area
    cr=bh.ParameterSource.value(1.3),  # Fixed Cr of 1.3
    eclipse_model=bh.EclipseModel.CONICAL,
)

# Create force model with all fixed parameters
# Start from two_body preset and add components
force_config = bh.ForceModelConfig.two_body()
force_config.gravity = bh.GravityConfiguration.spherical_harmonic(20, 20)
force_config.drag = drag_config
force_config.srp = srp_config
force_config.third_body = bh.ThirdBodyConfiguration(
    ephemeris_source=bh.EphemerisSource.LowPrecision,
    bodies=[bh.ThirdBody.SUN, bh.ThirdBody.MOON],
)
force_config.mass = bh.ParameterSource.value(500.0)  # Fixed 500 kg mass
```


### Using Parameter Indices

Use `ParameterSource.from_index()` (Python) / `ParameterSource::ParameterIndex` (Rust) for parameters that may be varied or estimated:


```python
import brahe as bh

# ParameterSource.parameter_index() references a value in the parameter vector
# Use when parameters may change or need to be estimated

# Default parameter layout:
# Index 0: mass (kg)
# Index 1: drag_area (m^2)
# Index 2: Cd (dimensionless)
# Index 3: srp_area (m^2)
# Index 4: Cr (dimensionless)

drag_config = bh.DragConfiguration(
    model=bh.AtmosphericModel.HARRIS_PRIESTER,
    area=bh.ParameterSource.parameter_index(1),  # params[1] = drag_area
    cd=bh.ParameterSource.parameter_index(2),  # params[2] = Cd
)

srp_config = bh.SolarRadiationPressureConfiguration(
    area=bh.ParameterSource.parameter_index(3),  # params[3] = srp_area
    cr=bh.ParameterSource.parameter_index(4),  # params[4] = Cr
    eclipse_model=bh.EclipseModel.CONICAL,
)

# Custom parameter layout example
custom_drag = bh.DragConfiguration(
    model=bh.AtmosphericModel.HARRIS_PRIESTER,
    area=bh.ParameterSource.parameter_index(5),  # Custom index
    cd=bh.ParameterSource.parameter_index(10),  # Custom index
)
```


### Default Parameter Layout

When using parameter indices, the default layout is:

| Index | Parameter | Units | Typical Value |
|-----|---------|-----|-------------|
| 0 | mass | kg | 1000.0 |
| 1 | drag_area | m² | 10.0 |
| 2 | Cd | - | 2.2 |
| 3 | srp_area | m² | 10.0 |
| 4 | Cr | - | 1.3 |

## Preset Configurations

Brahe provides preset configurations for common scenarios:

| Preset | Gravity | Drag | SRP | Third-Body | Relativity | Requires Params |
|------|-------|----|---|----------|----------|---------------|
| `two_body()` | PointMass | None | None | None | No | No |
| `earth_gravity()` | 20×20 | None | None | None | No | No |
| `conservative_forces()` | 80×80 | None | None | Sun/Moon (DE440s) | Yes | No |
| `default()` | 20×20 | Harris-Priester | Conical | Sun/Moon (LP) | No | Yes |
| `leo_default()` | 30×30 | NRLMSISE-00 | Conical | Sun/Moon (DE440s) | No | Yes |
| `geo_default()` | 8×8 | None | Conical | Sun/Moon (DE440s) | No | Yes |
| `high_fidelity()` | 120×120 | NRLMSISE-00 | Conical | All planets (DE440s) | Yes | Yes |


```python
import brahe as bh

# Brahe provides several preset configurations for common scenarios

# 1. two_body() - Point mass gravity only
# Use for: Validation, comparison with Keplerian, quick estimates
two_body = bh.ForceModelConfig.two_body()

# 2. earth_gravity() - Spherical harmonic gravity only (20x20)
# Use for: Studying gravity perturbations in isolation
earth_gravity = bh.ForceModelConfig.earth_gravity()

# 3. conservative_forces() - Gravity + third-body + relativity (no drag/SRP)
# Use for: Long-term orbit evolution, conservative dynamics studies
conservative = bh.ForceModelConfig.conservative_forces()

# 4. default() - Balanced configuration for LEO to GEO
# Use for: General mission analysis, initial studies
default = bh.ForceModelConfig.default()

# 5. leo_default() - Optimized for Low Earth Orbit
# Use for: LEO missions where drag is dominant
leo = bh.ForceModelConfig.leo_default()

# 6. geo_default() - Optimized for Geostationary Orbit
# Use for: GEO missions where SRP and third-body dominate
geo = bh.ForceModelConfig.geo_default()

# 7. high_fidelity() - Maximum precision
# Use for: Precision orbit determination, research applications
high_fidelity = bh.ForceModelConfig.high_fidelity()
```


---

## See Also

- [Numerical Propagation Overview](index.md) - Architecture and concepts
- [Integrator Configuration](integrator_configuration.md) - Integration methods
- [ForceModelConfig API Reference](../../../library_api/propagators/force_model_config.md)