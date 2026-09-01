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
        model_type=bh.GravityModelType.EGM2008_120,
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
    # Third-body: Sun and Moon with DE440s ephemeris (bare bodies coerce to
    # point-mass entries with the default source)
    third_body=[bh.ThirdBody.SUN, bh.ThirdBody.MOON],
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
│   ├── Zero
│   ├── PointMass
│   ├── SphericalHarmonic { source, degree, order }
│   └── EarthZonal { degree }
├── drag: DragConfiguration
│   ├── model: AtmosphericModel
│   ├── area: ParameterSource
│   ├── cd: ParameterSource
│   └── body: Option<CentralBody>
├── srp: SolarRadiationPressureConfiguration
│   ├── area: ParameterSource
│   ├── cr: ParameterSource
│   └── eclipse_model: EclipseModel
├── third_body: Vec<ThirdBodyConfiguration>
│   └── per entry:
│       ├── body: ThirdBody
│       ├── ephemeris_source: EphemerisSource
│       └── gravity: GravityConfiguration
├── relativity: bool
└── mass: ParameterSource
```

Each sub-configuration is optional (`None` disables that force). The configuration is captured at propagator construction time and remains immutable during propagation.

Each third-body entry carries its own ephemeris source and gravity model (point-mass by default), and drag can name a `body` other than the central body — see [Body Attribution](#body-attribution) below. In Python, `third_body` accepts a single `ThirdBody` or `ThirdBodyConfiguration`, or a list mixing both; bare bodies become point-mass entries with DE440s ephemerides. Serialized configurations deserialize the same shapes.

### Parameter Sources

Spacecraft parameters (mass $m$, drag area $A_d$, coefficient of drag $C_d$, SRP area $A_{SRP}$, coefficient of reflectivity $C_r$) can be specified in two ways via `ParameterSource`:

- **`Value(f64)`** - Fixed constant embedded at construction. The value is baked into the dynamics function and cannot change during propagation.

- **`ParameterIndex(usize)`** - Index into an parameter vector. This allows parameters to be varied or estimated as part of orbit determination or sensitivity analysis.

The [Parameter Configuration](#parameter-configuration) section below provides detailed examples of both approaches.

## Force Model Components

### Gravity Configuration

Gravity is the primary force in orbital mechanics. Brahe supports the following central gravity models (plus `GravityConfiguration.zero()` for barycentric propagation centers, which have no mass of their own and take all gravitational forces from third-body entries):

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


**Spherical Harmonics**: High-fidelity gravity using a packaged model (EGM2008, GGM05S, JGM3), a user-supplied `.gfc` file, or any model fetched from the [ICGEM catalog](../../datasets/icgem.md). Degree and order control accuracy vs computation time.

$$
\mathbf{a} = -\nabla V, \quad V(r, \phi, \lambda) = \frac{GM}{r} \sum_{n=0}^{N} \sum_{m=0}^{n} \left(\frac{R_E}{r}\right)^n \bar{P}_{nm}(\sin\phi) \left(\bar{C}_{nm}\cos(m\lambda) + \bar{S}_{nm}\sin(m\lambda)\right)
$$


```python
import brahe as bh

# ==============================================================================
# Packaged Gravity Models
# ==============================================================================

# EGM2008 - High-fidelity NGA model (120x120 max)
gravity_egm2008 = bh.GravityConfiguration.spherical_harmonic(
    degree=20, order=20, model_type=bh.GravityModelType.EGM2008_120
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
custom_model_type = bh.GravityModelType.from_file("data/gravity_models/EGM2008_120.gfc")
gravity_custom = bh.GravityConfiguration.spherical_harmonic(
    degree=20, order=20, model_type=custom_model_type
)
```


#### Selecting a Gravity Model

`GravityConfiguration.spherical_harmonic(...)` accepts a `model_type` argument
that selects which spherical harmonic field is loaded. Four sources are
available:

| Constructor                                  | Source                                                  |
|----------------------------------------------|---------------------------------------------------------|
| `GravityModelType.EGM2008_120`               | Packaged with Brahe (Earth, 120×120)                    |
| `GravityModelType.GGM05S`                    | Packaged with Brahe (Earth, 180×180)                    |
| `GravityModelType.JGM3`                      | Packaged with Brahe (Earth, 70×70)                      |
| `GravityModelType.from_file("path.gfc")`     | Any `.gfc` file on disk                                 |
| `GravityModelType.icgem(body, name)`         | Any model from the [ICGEM catalog](../../datasets/icgem.md) (downloaded on first use) |

All four are interchangeable at the `GravityConfiguration` boundary. The same
`degree` / `order` truncation rules apply: they must satisfy `degree ≤ model.n_max`
and `order ≤ min(degree, model.m_max)`.

#### Using an ICGEM Gravity Model

`GravityModelType.icgem(body, name)` lets you reference any model from the
[ICGEM catalog](../../datasets/icgem.md) without manually managing the
download. The first time a propagator backed by this configuration is built,
brahe downloads the matching `.gfc` file into
`$BRAHE_CACHE/icgem/models/<body>/` and caches the parsed `GravityModel` in
memory. Subsequent propagators referencing the same model reuse both caches.


```python
import numpy as np

import brahe as bh

# Initialize EOP data (required for any numerical propagation)
bh.initialize_eop()

# Reference an ICGEM Earth model. Use bh.datasets.icgem.list_models("earth")
# to discover the full catalog. Append "-<DEGREE>" to pin a specific variant.
grav_type = bh.GravityModelType.icgem("earth", "JGM3")

gravity_cfg = bh.GravityConfiguration.spherical_harmonic(
    degree=20, order=20, model_type=grav_type
)

# Minimal force model: ICGEM-sourced spherical-harmonic gravity only
force_cfg = bh.ForceModelConfig(gravity=gravity_cfg)

# Build an initial state for a LEO satellite
epoch = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
oe = np.array(
    [
        bh.R_EARTH + 500e3,  # a (m)
        0.001,  # e
        np.radians(97.8),  # i (rad)
        np.radians(15.0),  # RAAN (rad)
        np.radians(30.0),  # arg perigee (rad)
        np.radians(45.0),  # true anomaly (rad)
    ]
)
state0 = bh.state_koe_to_eci(oe, bh.AngleFormat.RADIANS)

# Construct the propagator — this is where the ICGEM model is downloaded
# (if not cached) and loaded into the force evaluator.
prop = bh.NumericalOrbitPropagator.builder(epoch, state0, force_cfg).build()

# Step one minute forward
prop.step_by(60.0)
state1 = prop.current_state()

drift = float(np.linalg.norm(np.asarray(state1[:3]) - np.asarray(state0[:3])))
print(f"Propagated 60 s with JGM3 (ICGEM source); position drift = {drift:.1f} m")
```


**Pre-fetching models for offline runs**
Call `bh.datasets.icgem.download_model(body, name)` once during setup to
warm the cache. Subsequent `GravityModelType.icgem(body, name)` references
then resolve entirely from disk, with no network dependency at propagator
construction time.

**Equality of `ICGEMModel` types**
Two `GravityModelType.icgem(body, name)` instances compare equal only when
both `body` and `name` match. This is what lets the in-process
`GravityModel` cache de-duplicate across configurations — multiple
propagators that request the same ICGEM model share a single parsed
coefficient set in memory.

For the discovery, refresh, and cache mechanics around ICGEM downloads, see
the [ICGEM dataset guide](../../datasets/icgem.md).

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

Gravitational attraction from Sun, Moon, and planets causes long-period variations in orbital elements. Each perturbing body is configured with its own `ThirdBodyConfiguration` entry pairing the body with an ephemeris source and a gravity model.

For the default point-mass model the acceleration is the classical tidal form:

$$
\mathbf{a}_{TB} = GM_{b} \left(\frac{\mathbf{r}_b - \mathbf{r}}{|\mathbf{r}_b - \mathbf{r}|^3} - \frac{\mathbf{r}_b}{|\mathbf{r}_b|^3}\right)
$$

where $GM_b$ is the gravitational parameter of the third body, $\mathbf{r}_b$ is its position, and $\mathbf{r}$ is the satellite position. For barycentric central bodies the indirect term ($-GM_b \mathbf{r}_b/|\mathbf{r}_b|^3$) is omitted for bodies whose motion already defines the barycenter (everything for SSB; Earth and the Moon for EMB).

Ephemeris sources (set per entry):

- **LowPrecision**: Fast analytical, Sun/Moon only
- **DE440s**: JPL high precision, all planets, 1550-2650 CE
- **DE440**: JPL high precision, all planets, 13200 BCE-17191 CE

Planet perturbers come in two flavors: the `*Barycenter` variants (`MarsBarycenter` .. `NeptuneBarycenter`, NAIF IDs 4-8) use the planetary-system barycenter position with the system GM — the classical formulation, resolvable from the DE kernel alone and used by the default Earth force models — while the unqualified variants (`Mars` .. `Neptune`, NAIF IDs 499-899) are planet centers with planet-only GMs, resolved through their satellite-system ephemeris kernels.


```python
import brahe as bh

# Third-body perturbations configuration: one entry per perturbing body,
# each carrying its own ephemeris source and gravity model (point-mass by
# default).

# Option 1: Low-precision analytical ephemerides
# Fast but less accurate (~km level errors for Sun/Moon)
# Only Sun and Moon are available
third_bodies_low = [
    bh.ThirdBodyConfiguration(
        bh.ThirdBody.SUN, ephemeris_source=bh.EphemerisSource.LowPrecision
    ),
    bh.ThirdBodyConfiguration(
        bh.ThirdBody.MOON, ephemeris_source=bh.EphemerisSource.LowPrecision
    ),
]

# Option 2: DE440s high-precision ephemerides (recommended)
# Uses JPL Development Ephemeris 440 (small bodies version)
# ~m level accuracy, valid 1550-2650 CE
# All planets available, ~17 MB file. DE440s is the default source, so bare
# bodies can be passed directly and become point-mass entries.
third_bodies_de440s = [bh.ThirdBody.SUN, bh.ThirdBody.MOON]

# Option 3: DE440 full-precision ephemerides
# Highest accuracy (~mm level), valid 13200 BCE-17191 CE
# All planets available, ~114 MB file
third_bodies_de440 = [
    bh.ThirdBodyConfiguration(
        bh.ThirdBody.SUN, ephemeris_source=bh.EphemerisSource.DE440
    ),
    bh.ThirdBodyConfiguration(
        bh.ThirdBody.MOON, ephemeris_source=bh.EphemerisSource.DE440
    ),
]

# Option 4: Include all major planets (high-fidelity). The *_BARYCENTER
# variants use the planetary-system barycenters with system GMs — the
# classical third-body formulation, resolvable from the DE kernel alone.
third_bodies_all_planets = [
    bh.ThirdBody.SUN,
    bh.ThirdBody.MOON,
    bh.ThirdBody.MERCURY,
    bh.ThirdBody.VENUS,
    bh.ThirdBody.MARS_BARYCENTER,
    bh.ThirdBody.JUPITER_BARYCENTER,
    bh.ThirdBody.SATURN_BARYCENTER,
    bh.ThirdBody.URANUS_BARYCENTER,
    bh.ThirdBody.NEPTUNE_BARYCENTER,
]

# Create force model with Sun/Moon perturbations (common case)
force_config = bh.ForceModelConfig(
    gravity=bh.GravityConfiguration(degree=20, order=20),
    third_body=third_bodies_de440s,
)
print(f"Third bodies: {force_config.third_body}")
```


### Body Attribution

Force models can be attributed to a body other than the propagation's central body. This supports configurations such as an Earth-Moon-barycenter-centered cislunar trajectory that still needs Earth-fidelity forces when passing through low altitudes.

**Extended third-body gravity.** A third-body entry's `gravity` can be `SphericalHarmonic` or `EarthZonal` instead of the default `PointMass`. The field is evaluated at the object's position relative to the perturbing body, oriented by that body's body-fixed frame (ITRF for Earth, LFPA for the Moon, MCMF for Mars, IAU frames for the other planet centers); the indirect term stays point-mass with the field's own GM, so the far-field limit reduces exactly to the tidal form above. `EarthZonal` requires `ThirdBody.EARTH`; `SphericalHarmonic` requires a body with a known body-fixed frame, which excludes the `*Barycenter` variants and `Custom` bodies.

**Attributed drag.** `DragConfiguration.body` names the body whose atmosphere produces the drag (default: the central body). Density and relative wind are evaluated at the object's state relative to that body, and the acceleration applies directly in the propagation frame. The Earth-atmosphere models (`NRLMSISE00`, `HarrisPriester`) require the attributed body to be Earth; the attributed body must have a known radius and spin rate. Drag about a barycentric central body is therefore valid only with an explicit attributed body.

The following example propagates an EMB-centered state through LEO altitudes with an Earth spherical-harmonic field and Earth-attributed NRLMSISE-00 drag:


```python
trajectory passing through LEO altitudes keeps Earth-fidelity forces
while the integration state stays Earth-Moon-barycenter-centered.
"""

import numpy as np

import brahe as bh

# Initialize EOP and space weather data (required for NRLMSISE-00)
bh.initialize_eop()
bh.initialize_sw()

epoch = bh.Epoch.from_datetime(2024, 3, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# EMB-centered force model: no central gravity term (the barycenter has no
# mass of its own); Earth carries a spherical-harmonic field and the
# atmosphere; the Moon and Sun are point-mass perturbers.
force_config = bh.ForceModelConfig.for_body(
    bh.CentralBody.EMB,
    bh.GravityConfiguration.zero(),
    drag=bh.DragConfiguration(
        model=bh.AtmosphericModel.NRLMSISE00,
        area=bh.ParameterSource.value(10.0),
        cd=bh.ParameterSource.value(2.2),
        # Attribute the drag to Earth: density and relative wind are
        # evaluated at the object's state relative to Earth.
        body=bh.CentralBody.Earth,
    ),
    third_body=[
        bh.ThirdBodyConfiguration(
            bh.ThirdBody.EARTH,
            gravity=bh.GravityConfiguration.spherical_harmonic(degree=8, order=8),
        ),
        bh.ThirdBody.MOON,
        bh.ThirdBody.SUN,
    ],
    mass=bh.ParameterSource.value(1000.0),
)
force_config.validate()

# Start from a 500 km Earth orbit, re-expressed about the EMB via the
# ECI->EMBI frame translation.
oe = np.array([bh.R_EARTH + 500e3, 0.001, 51.6, 15.0, 30.0, 45.0])
x_earth = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)
x_emb = bh.state_eci_to_emb(epoch, x_earth)

prop = bh.NumericalOrbitPropagator.builder(epoch, x_emb, force_config).build()

# Propagate for one day
epoch_end = epoch + 86400.0
prop.propagate_to(epoch_end)

x_final = prop.current_state()
print(f"Initial EMB-centered state: {x_emb}")
print(f"Final EMB-centered state:   {x_final}")

# Re-express the final state about Earth for reference
x_final_eci = bh.state_emb_to_eci(epoch_end, x_final)
altitude = np.linalg.norm(x_final_eci[:3]) - bh.R_EARTH
print(f"Final altitude above Earth: {altitude / 1e3:.1f} km")
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
force_config.third_body = [
    bh.ThirdBodyConfiguration(
        bh.ThirdBody.SUN, ephemeris_source=bh.EphemerisSource.LowPrecision
    ),
    bh.ThirdBodyConfiguration(
        bh.ThirdBody.MOON, ephemeris_source=bh.EphemerisSource.LowPrecision
    ),
]
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

| Preset | Gravity | Drag | SRP | Third-Body | Relativity | Solid Tides | Ocean Tides | Requires Params |
|------|-------|----|---|----------|----------|----------|----------|---------------|
| `two_body()` | PointMass | None | None | None | No | No | No | No |
| `earth_gravity()` | 20×20 | None | None | None | No | No | No | No |
| `conservative_forces()` | 80×80 | None | None | Sun/Moon (DE440s) | Yes | No | No | No |
| `default()` | 20×20 | Harris-Priester | Conical | Sun/Moon (LP) | No | No | No | Yes |
| `leo_default()` | 30×30 | NRLMSISE-00 | Conical | Sun/Moon (DE440s) | No | No | No | Yes |
| `geo_default()` | 8×8 | None | Conical | Sun/Moon (DE440s) | No | No | No | Yes |
| `high_fidelity()` | 120×120 | NRLMSISE-00 | Conical | All planets (DE440s) | Yes | Yes | Yes (30×30) | Yes |

`high_fidelity()` enables every tidal correction Brahe supports (solid Earth
tides, both pole tides, and FES2004 ocean tides) — see
[Tidal Corrections](../../orbital_dynamics/tides.md). Its ocean tide
component downloads the FES2004 coefficient file once, the first time a
propagator built from it is constructed; see
[Ocean Tides: Coefficient Download](../../orbital_dynamics/tides.md#coefficient-download).


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