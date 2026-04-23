# Orbital Properties

The `orbits` module provides functions to compute essential properties of satellite orbits, including orbital period, mean motion, periapsis/apoapsis characteristics, and specialized orbits like sun-synchronous configurations. These properties are fundamental for mission design, orbit determination, and trajectory analysis.

For complete API documentation, see [Orbits API Reference](../../library_api/orbits/index.md).

## Orbital Period

The orbital period $T$ of a satellite is the time it takes to complete one full revolution around the central body. It is related to the semi-major axis $a$ and gravitational parameter $\mu$ by:

$$
T = 2\pi\sqrt{\frac{a^3}{\mu}}
$$

The `orbital_period` function computes the period for Earth-orbiting objects, while `orbital_period_general` accepts an explicit gravitational parameter for any celestial body.


```python
import brahe as bh

bh.initialize_eop()

# Define orbit parameters
a = bh.R_EARTH + 500.0e3  # Semi-major axis (m) - LEO orbit at 500 km altitude

# Compute orbital period for Earth orbit (uses GM_EARTH internally)
period_earth = bh.orbital_period(a)
print(f"Orbital period (Earth): {period_earth:.3f} s")
print(f"Orbital period (Earth): {period_earth / 60:.3f} min")

# Compute orbital period for general body (explicit GM)
period_general = bh.orbital_period_general(a, bh.GM_EARTH)
print(f"Orbital period (general): {period_general:.3f} s")

# Verify they match
print(f"Difference: {abs(period_earth - period_general):.2e} s")

# Example with approximate GEO altitude
a_geo = bh.R_EARTH + 35786e3
period_geo = bh.orbital_period(a_geo)
print(f"\nGEO orbital period: {period_geo / 3600:.3f} hours")
```


The plot below shows how orbital period and velocity vary with altitude for circular Earth orbits:


**Plot Source**

```python
import os
import pathlib
import sys
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import brahe as bh

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from brahe_theme import get_theme_colors, save_themed_html

# Configuration
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))

# Ensure output directory exists
os.makedirs(OUTDIR, exist_ok=True)

# Generate data

# Generate range of altitudes from 0 to 40,000 km in 500 km increments
alt = np.arange(0, 41000 * 1e3, 500 * 1e3)

# Compute velocity over altitude (km/s)
vp = [bh.perigee_velocity(bh.R_EARTH + a, 0.0) / 1e3 for a in alt]

# Compute orbital period over altitude (hours)
period = [bh.orbital_period(bh.R_EARTH + a) / 3600 for a in alt]

# Create figure with theme support


def create_figure(theme):
    """Create figure with theme-specific colors."""
    colors = get_theme_colors(theme)

    # Create subplot with secondary y-axis
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Add velocity trace (primary y-axis)
    fig.add_trace(
        go.Scatter(
            x=alt / 1e6,
            y=vp,
            mode="lines",
            line=dict(color=colors["primary"], width=2),
            name="Velocity",
            showlegend=True,
        ),
        secondary_y=False,
    )

    # Add orbital period trace (secondary y-axis)
    fig.add_trace(
        go.Scatter(
            x=alt / 1e6,
            y=period,
            mode="lines",
            line=dict(color=colors["secondary"], width=2),
            name="Orbital Period",
            showlegend=True,
        ),
        secondary_y=True,
    )

    # Configure primary x-axis
    fig.update_xaxes(
        tickmode="linear",
        tick0=0,
        dtick=5,
        title_text="Satellite Altitude [1000 km]",
        range=[0, 40],
        showgrid=False,
    )

    # Configure primary y-axis (velocity)
    fig.update_yaxes(
        tickmode="linear",
        tick0=0,
        dtick=1,
        title_text="Velocity [km/s]",
        range=[0, 10],
        showgrid=False,
        secondary_y=False,
    )

    # Configure secondary y-axis (period)
    fig.update_yaxes(
        tickmode="linear",
        tick0=0,
        dtick=5,
        title_text="Orbital Period [hours]",
        range=[0, 30],
        showgrid=False,
        secondary_y=True,
    )

    return fig


# Generate and save both themed versions
light_path, dark_path = save_themed_html(create_figure, OUTDIR / SCRIPT_NAME)
print(f"✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")
```

### From State Vector

When orbital elements are unknown but you have a Cartesian state vector, `orbital_period_from_state` computes the period directly from position and velocity:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define orbital elements for a LEO satellite
a = bh.R_EARTH + 500.0e3  # Semi-major axis (m)
e = 0.01  # Eccentricity
i = 97.8  # Inclination (degrees)
raan = 15.0  # Right ascension of ascending node (degrees)
argp = 30.0  # Argument of periapsis (degrees)
nu = 45.0  # True anomaly (degrees)

# Convert to Cartesian state
oe = np.array([a, e, i, raan, argp, nu])
state_eci = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

print("ECI State (position in km, velocity in km/s):")
print(
    f"  r = [{state_eci[0] / 1e3:.3f}, {state_eci[1] / 1e3:.3f}, {state_eci[2] / 1e3:.3f}] km"
)
print(
    f"  v = [{state_eci[3] / 1e3:.3f}, {state_eci[4] / 1e3:.3f}, {state_eci[5] / 1e3:.3f}] km/s"
)

# Compute orbital period from state vector
period = bh.orbital_period_from_state(state_eci, bh.GM_EARTH)
print(f"\nOrbital period from state: {period:.3f} s")
print(f"Orbital period from state: {period / 60:.3f} min")

# Verify against period computed from semi-major axis
period_from_sma = bh.orbital_period(a)
print(f"\nOrbital period from SMA: {period_from_sma:.3f} s")
print(f"Difference: {abs(period - period_from_sma):.2e} s")
```


### Semi-major Axis from Period

The inverse relationship allows computing semi-major axis when orbital period is known (useful for mission design):

$$
a = \sqrt[3]{\frac{\mu T^2}{4\pi^2}}
$$


```python
import brahe as bh

bh.initialize_eop()

# Example 1: LEO satellite with 98-minute period
period_leo = 98 * 60  # 98 minutes in seconds
a_leo = bh.semimajor_axis_from_orbital_period(period_leo)
altitude_leo = a_leo - bh.R_EARTH

print("LEO Satellite (98 min period):")
print(f"  Semi-major axis: {a_leo:.3f} m")
print(f"  Altitude: {altitude_leo / 1e3:.3f} km")

# Example 2: Geosynchronous orbit (24-hour period)
period_geo = 24 * 3600  # 24 hours in seconds
a_geo = bh.semimajor_axis_from_orbital_period(period_geo)
altitude_geo = a_geo - bh.R_EARTH

print("\nGeosynchronous Orbit (24 hour period):")
print(f"  Semi-major axis: {a_geo:.3f} m")
print(f"  Altitude: {altitude_geo / 1e3:.3f} km")

# Example 3: Using general function for Moon orbit
period_moon = 27.3 * 24 * 3600  # 27.3 days in seconds
a_moon = bh.semimajor_axis_from_orbital_period_general(period_moon, bh.GM_EARTH)

print("\nMoon's orbit (27.3 day period):")
print(f"  Semi-major axis: {a_moon / 1e3:.3f} km")

# Verify round-trip conversion
period_verify = bh.orbital_period(a_leo)
print("\nRound-trip verification:")
print(f"  Original period: {period_leo:.3f} s")
print(f"  Computed period: {period_verify:.3f} s")
print(f"  Difference: {abs(period_leo - period_verify):.2e} s")
```


## Mean Motion

A satellite's average angular rate over one orbit is its _mean motion_ $n$, calculated from the semi-major axis and gravitational parameter:

$$
n = \sqrt{\frac{\mu}{a^3}}
$$

The `mean_motion` function computes this for Earth-orbiting objects, while `mean_motion_general` works for any celestial body. Both functions support output in radians or degrees per second via the `angle_format` parameter.


```python
import brahe as bh

bh.initialize_eop()

# Define orbit parameters
a_leo = bh.R_EARTH + 500.0e3  # LEO satellite at 500 km altitude
a_geo = bh.R_EARTH + 35786e3  # GEO satellite

# Compute mean motion in radians/s (Earth-specific)
n_leo_rad = bh.mean_motion(a_leo, bh.AngleFormat.RADIANS)
n_geo_rad = bh.mean_motion(a_geo, bh.AngleFormat.RADIANS)

print("Mean Motion in radians/second:")
print(f"  LEO (500 km): {n_leo_rad:.6f} rad/s")
print(f"  GEO:          {n_geo_rad:.6f} rad/s")

# Compute mean motion in degrees/s
n_leo_deg = bh.mean_motion(a_leo, bh.AngleFormat.DEGREES)
n_geo_deg = bh.mean_motion(a_geo, bh.AngleFormat.DEGREES)

print("\nMean Motion in degrees/second:")
print(f"  LEO (500 km): {n_leo_deg:.6f} deg/s")
print(f"  GEO:          {n_geo_deg:.6f} deg/s")

# Convert to degrees/day (common unit for TLEs)
print("\nMean Motion in degrees/day:")
print(f"  LEO (500 km): {n_leo_deg * 86400:.3f} deg/day")
print(f"  GEO:          {n_geo_deg * 86400:.3f} deg/day")

# Verify using general function
n_leo_general = bh.mean_motion_general(a_leo, bh.GM_EARTH, bh.AngleFormat.RADIANS)
print(f"\nVerification (general function): {n_leo_general:.6f} rad/s")
print(f"Difference: {abs(n_leo_rad - n_leo_general):.2e} rad/s")
```


### Semi-major Axis from Mean Motion

Since orbital data formats like TLEs specify mean motion instead of semi-major axis, the inverse computation is essential:

$$
a = \sqrt[3]{\frac{\mu}{n^2}}
$$


```python
import brahe as bh

bh.initialize_eop()

# Example 1: ISS-like orbit with ~15.5 revolutions per day
n_iss = 15.5 * 360.0 / 86400.0  # Convert revs/day to deg/s
a_iss = bh.semimajor_axis(n_iss, bh.AngleFormat.DEGREES)
altitude_iss = a_iss - bh.R_EARTH

print("ISS-like Orbit (15.5 revs/day):")
print(f"  Mean motion: {n_iss:.6f} deg/s")
print(f"  Semi-major axis: {a_iss:.3f} m")
print(f"  Altitude: {altitude_iss / 1e3:.3f} km")

# Example 2: Geosynchronous orbit (1 revolution per day)
n_geo = 1.0 * 360.0 / 86400.0  # 1 rev/day in deg/s
a_geo = bh.semimajor_axis(n_geo, bh.AngleFormat.DEGREES)
altitude_geo = a_geo - bh.R_EARTH

print("\nGeosynchronous Orbit (1 rev/day):")
print(f"  Mean motion: {n_geo:.6f} deg/s")
print(f"  Semi-major axis: {a_geo:.3f} m")
print(f"  Altitude: {altitude_geo / 1e3:.3f} km")

# Example 3: Using radians
n_leo_rad = 0.001  # rad/s
a_leo = bh.semimajor_axis(n_leo_rad, bh.AngleFormat.RADIANS)

print("\nLEO from radians/s:")
print(f"  Mean motion: {n_leo_rad:.6f} rad/s")
print(f"  Semi-major axis: {a_leo:.3f} m")
print(f"  Altitude: {(a_leo - bh.R_EARTH) / 1e3:.3f} km")

# Verify round-trip conversion
n_verify = bh.mean_motion(a_iss, bh.AngleFormat.DEGREES)
print("\nRound-trip verification:")
print(f"  Original mean motion: {n_iss:.6f} deg/s")
print(f"  Computed mean motion: {n_verify:.6f} deg/s")
print(f"  Difference: {abs(n_iss - n_verify):.2e} deg/s")
```


## Periapsis Properties

The periapsis is the point of closest approach to the central body, where orbital velocity is greatest.

???+ info

    The word _**periapsis**_ is formed by combination of the Greek words "_peri-_" (meaning around, about) and "_apsis_" (meaning "arch or vault"). An apsis is the farthest or nearest point in the orbit of a planetary body about its primary body.

    Therefore _periapsis_ is the point of closest approach of the orbiting body with respect to its central body. The suffix can be modified to indicate the closest approach to a specific celestial body: _perigee_ for Earth, _perihelion_ for the Sun.

Brahe provides functions to compute periapsis velocity, distance, and altitude based on orbital elements.

### Velocity

The periapsis velocity is given by:

$$
v_{p} = \sqrt{\frac{\mu}{a}}\sqrt{\frac{1+e}{1-e}}
$$

where $\mu$ is the gravitational parameter, $a$ is the semi-major axis, and $e$ is the eccentricity.

### Distance

The periapsis distance from the center of the central body is (from Vallado[^1] Equation 2-75):

$$
r_p = \frac{a(1-e^2)}{1+e} = a(1-e)
$$

### Altitude

The periapsis altitude is the height above the surface of the central body:

$$
h_p = r_p - R_{body} = a(1-e) - R_{body}
$$

where $R_{body}$ is the radius of the central body. For Earth orbits, the `perigee_altitude` function provides a convenient wrapper using $R_{\oplus}$.

### Code Example


```python
import brahe as bh

bh.initialize_eop()

# Define orbit parameters
a = bh.R_EARTH + 500.0e3  # Semi-major axis (m)
e = 0.01  # Eccentricity

# Compute periapsis velocity (generic)
periapsis_velocity = bh.periapsis_velocity(a, e, gm=bh.GM_EARTH)
print(f"Periapsis velocity: {periapsis_velocity:.3f} m/s")

# Compute as a perigee velocity (Earth-specific)
perigee_velocity = bh.perigee_velocity(a, e)
print(f"Perigee velocity:   {perigee_velocity:.3f} m/s")

# Compute periapsis distance
periapsis_distance = bh.periapsis_distance(a, e)
print(f"Periapsis distance: {periapsis_distance / 1e3:.3f} km")

# Compute periapsis altitude (generic)
periapsis_altitude = bh.periapsis_altitude(a, e, r_body=bh.R_EARTH)
print(f"Periapsis altitude: {periapsis_altitude / 1e3:.3f} km")

# Compute as a perigee altitude (Earth-specific)
perigee_altitude = bh.perigee_altitude(a, e)
print(f"Perigee altitude:   {perigee_altitude / 1e3:.3f} km")
```


## Apoapsis Properties

The apoapsis is the farthest point from the central body, where orbital velocity is lowest.

???+ info

    The word _**apoapsis**_ is formed by combination of the Greek words "_apo-_" (meaning away from, separate, or apart from) and "_apsis_".

    Therefore _apoapsis_ is the farthest point of an orbiting body with respect to its central body. The suffix can be modified to indicate the farthest point from a specific celestial body: _apogee_ for Earth, _aphelion_ for the Sun.

Brahe provides functions to compute apoapsis velocity, distance, and altitude based on orbital elements.

**warning**

Apoapsis position, velocity, and altitude are only defined for elliptic and circular orbits. For parabolic and hyperbolic orbits, these quantities are undefined.

### Velocity

The apoapsis velocity is given by:

$$
v_{a} = \sqrt{\frac{\mu}{a}}\sqrt{\frac{1-e}{1+e}}
$$

### Distance

The apoapsis distance from the center of the central body is:

$$
r_a = \frac{a(1-e^2)}{1-e} = a(1+e)
$$

### Altitude

The apoapsis altitude is the height above the surface of the central body:

$$
h_a = r_a - R_{body} = a(1+e) - R_{body}
$$

where $R_{body}$ is the radius of the central body. For Earth orbits, the `apogee_altitude` function provides a convenient wrapper using $R_{\oplus}$.


### Code Example


```python
import brahe as bh

bh.initialize_eop()

# Define orbit parameters
a = bh.R_EARTH + 500.0e3  # Semi-major axis (m)
e = 0.01  # Eccentricity

# Compute apoapsis velocity (generic)
apoapsis_velocity = bh.apoapsis_velocity(a, e, gm=bh.GM_EARTH)
print(f"Apoapsis velocity: {apoapsis_velocity:.3f} m/s")

# Compute as an apogee velocity (Earth-specific)
apogee_velocity = bh.apogee_velocity(a, e)
print(f"Apogee velocity:   {apogee_velocity:.3f} m/s")

# Compute apoapsis distance
apoapsis_distance = bh.apoapsis_distance(a, e)
print(f"Apoapsis distance: {apoapsis_distance / 1e3:.3f} km")

# Compute apoapsis altitude (generic)
apoapsis_altitude = bh.apoapsis_altitude(a, e, r_body=bh.R_EARTH)
print(f"Apoapsis altitude: {apoapsis_altitude / 1e3:.3f} km")

# Compute as an apogee altitude (Earth-specific)
apogee_altitude = bh.apogee_altitude(a, e)
print(f"Apogee altitude:   {apogee_altitude / 1e3:.3f} km")
```


## Sun-Synchronous Inclination

A _**sun-synchronous**_ orbit maintains a constant angle relative to the Sun by matching its nodal precession rate to Earth's annual revolution. The right ascension of the ascending node ($\Omega$) advances at the same rate as the Sun's apparent motion: approximately 0.9856°/day. This configuration is highly valuable for Earth observation satellites requiring consistent illumination conditions—a sun-synchronous satellite crosses the equator at the same local time on each pass (e.g., always at 2 PM).

Earth's oblateness, characterized by the $J_2$ zonal harmonic, causes secular drift in $\Omega$:

$$
\dot{\Omega} = -\frac{3nR^2_EJ_2}{2a^2(1-e^2)^2}\cos{i}
$$

For sun-synchronicity, this must equal:

$$
\dot{\Omega}_{ss} = \frac{360°}{1 \text{ year}} = 0.9856473598°/\text{day}
$$

Solving for inclination as a function of semi-major axis and eccentricity:

$$
i = \arccos{\left(-\frac{2a^{7/2}\dot{\Omega}_{ss}(1-e^2)^2}{3R^2_EJ_2\sqrt{\mu}}\right)}
$$

The `sun_synchronous_inclination` function computes this required inclination:


```python
"""

import brahe as bh

bh.initialize_eop()

# Example 1: Typical sun-synchronous LEO at 800 km altitude
a_leo = bh.R_EARTH + 800e3  # Semi-major axis
e_leo = 0.0  # Circular orbit

inc_leo_deg = bh.sun_synchronous_inclination(
    a_leo, e_leo, angle_format=bh.AngleFormat.DEGREES
)
inc_leo_rad = bh.sun_synchronous_inclination(
    a_leo, e_leo, angle_format=bh.AngleFormat.RADIANS
)

print("Sun-synchronous LEO (800 km, circular):")
print(f"  Inclination: {inc_leo_deg:.3f} degrees")
print(f"  Inclination: {inc_leo_rad:.6f} radians")

# Example 2: Different altitudes
altitudes = [500, 600, 700, 800, 900, 1000]  # km
print("\nSun-synchronous inclination vs altitude (circular orbits):")
for alt_km in altitudes:
    a = bh.R_EARTH + alt_km * 1e3
    inc = bh.sun_synchronous_inclination(a, 0.0, angle_format=bh.AngleFormat.DEGREES)
    print(f"  {alt_km:4d} km: {inc:.3f} deg")

# Example 3: Effect of eccentricity
a_fixed = bh.R_EARTH + 700e3
eccentricities = [0.0, 0.001, 0.005, 0.01, 0.02]

print("\nSun-synchronous inclination vs eccentricity (700 km orbit):")
for e in eccentricities:
    inc = bh.sun_synchronous_inclination(
        a_fixed, e, angle_format=bh.AngleFormat.DEGREES
    )
    print(f"  e = {e:.3f}: {inc:.3f} deg")

# Example 4: Practical mission example (Landsat-like)
a_landsat = bh.R_EARTH + 705e3
e_landsat = 0.0001
inc_landsat = bh.sun_synchronous_inclination(
    a_landsat, e_landsat, angle_format=bh.AngleFormat.DEGREES
)

print("\nLandsat-like orbit (705 km, nearly circular):")
print(f"  Inclination: {inc_landsat:.3f} deg")
print(f"  Period: {bh.orbital_period(a_landsat) / 60:.3f} min")
```


The plot below shows how the required inclination varies with altitude for sun-synchronous orbits:


**Plot Source**

```python
import os
import pathlib
import sys
import numpy as np
import plotly.graph_objects as go
import brahe as bh

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from brahe_theme import get_theme_colors, save_themed_html

# Configuration
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))

# Ensure output directory exists
os.makedirs(OUTDIR, exist_ok=True)

# Generate data

# Generate range of altitudes from 300 to 1000 km in 1 km increments
alt = np.arange(300e3, 1000e3, 1e3)

# Compute sun-synchronous inclination for range of eccentricities
eccentricities = [0.0, 0.1, 0.3, 0.5]
ssi_data = {}
for e in eccentricities:
    ssi_data[e] = [
        bh.sun_synchronous_inclination(
            bh.R_EARTH + a, e, angle_format=bh.AngleFormat.DEGREES
        )
        for a in alt
    ]

# Create figure with theme support


def create_figure(theme):
    """Create figure with theme-specific colors."""
    colors = get_theme_colors(theme)

    fig = go.Figure()

    # Color palette for different eccentricities
    color_palette = [
        colors["primary"],
        colors["secondary"],
        colors["accent"],
        colors["error"],
    ]

    # Add traces for each eccentricity
    for i, e in enumerate(eccentricities):
        fig.add_trace(
            go.Scatter(
                x=alt / 1e3,
                y=ssi_data[e],
                mode="lines",
                line=dict(color=color_palette[i % len(color_palette)], width=2),
                name=f"e = {e:.1f}",
                showlegend=True,
            )
        )

    # Configure axes
    fig.update_xaxes(
        tickmode="linear",
        tick0=300,
        dtick=100,
        title_text="Satellite Altitude [km]",
        range=[300, 1000],
        showgrid=False,
    )

    fig.update_yaxes(
        tickmode="linear",
        title_text="Inclination [deg]",
        showgrid=False,
    )

    return fig


# Generate and save both themed versions
light_path, dark_path = save_themed_html(create_figure, OUTDIR / SCRIPT_NAME)
print(f"✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")
```

Most sun-synchronous Earth observation missions operate at altitudes between 500-1000 km with near-zero eccentricity. The launch provider selects the precise inclination based on the above equation to achieve the desired sun-synchronous behavior.

---

---

## See Also

- [Orbits API Reference](../../library_api/orbits/index.md) - Complete Python API documentation
- [Anomaly Conversions](anomalies.md) - Converting between true, eccentric, and mean anomaly

[^1]: D. Vallado, *Fundamentals of Astrodynamics and Applications (4th Ed.)*, 2010