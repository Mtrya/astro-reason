# Access Geometry

Access geometry plots visualize satellite visibility from ground stations, showing where satellites appear in the sky and how their elevation changes over time. Brahe provides three complementary views: polar plots showing azimuth and elevation, elevation vs azimuth plots showing the observed horizon, and time-series plots tracking elevation angle during passes.

All plot types support optional **elevation masks** to visualize terrain obstructions, antenna constraints, or other azimuth-dependent visibility limits.

## Polar Access Plot (Azimuth/Elevation)

Polar plots display the satellite's path across the sky in azimuth-elevation coordinates, providing an intuitive "looking up" view from the ground station.

### Interactive Polar Plot (Plotly)


**Plot Source**

```python
"""
Access Polar Plot Example - Plotly Backend

This script demonstrates how to create an interactive polar access plot using the plotly backend.
Shows satellite azimuth and elevation during ground station passes.
"""

import os
import pathlib
import sys
import brahe as bh
import numpy as np

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))
from brahe_theme import save_themed_html

# Configuration
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# Initialize EOP data
bh.initialize_eop()

# ISS TLE for November 3, 2025
tle_line0 = "ISS (ZARYA)"
tle_line1 = "1 25544U 98067A   25306.42331346  .00010070  00000-0  18610-3 0  9999"
tle_line2 = "2 25544  51.6344 342.0717 0004969   8.9436 351.1640 15.49700017536601"

# Create SGP4 propagator
prop = bh.SGPPropagator.from_3le(tle_line0, tle_line1, tle_line2, 60.0)

# Define ground station (Cape Canaveral)
lat = np.radians(28.3922)  # Latitude in radians
lon = np.radians(-80.6077)  # Longitude in radians
alt = 0.0  # Altitude in meters
station = bh.PointLocation(lat, lon, alt).with_name("Cape Canaveral")

# Define time range (one day to capture multiple passes)
epoch = prop.epoch
duration = 24.0 * 3600.0  # 24 hours in seconds

# Compute access windows
constraint = bh.ElevationConstraint(min_elevation_deg=10.0)
accesses = bh.location_accesses([station], [prop], epoch, epoch + duration, constraint)

# Create polar access plot
if len(accesses) > 0:
    # Use first 3 access windows
    num_windows = min(3, len(accesses))
    windows_to_plot = [
        {"access_window": accesses[i], "label": f"Access {i + 1}"}
        for i in range(num_windows)
    ]

    fig = bh.plot_access_polar(
        windows_to_plot,
        prop,  # Propagator for interpolation
        min_elevation=10.0,
        backend="plotly",
    )

    # Save themed HTML files
    light_path, dark_path = save_themed_html(fig, OUTDIR / SCRIPT_NAME)
    print(f"✓ Generated {light_path}")
    print(f"✓ Generated {dark_path}")
else:
    print("No access windows found in the specified time range")
```

### Static Polar Plot (Matplotlib)


**Plot Source**

```python
"""
Access Polar Plot Example - Matplotlib Backend

This script demonstrates how to create a polar access plot using the matplotlib backend.
Shows satellite azimuth and elevation during ground station passes.
"""

import brahe as bh
import numpy as np
import matplotlib.pyplot as plt

# Initialize EOP data
bh.initialize_eop()

# ISS TLE for November 3, 2025
tle_line0 = "ISS (ZARYA)"
tle_line1 = "1 25544U 98067A   25306.42331346  .00010070  00000-0  18610-3 0  9999"
tle_line2 = "2 25544  51.6344 342.0717 0004969   8.9436 351.1640 15.49700017536601"

# Create SGP4 propagator
prop = bh.SGPPropagator.from_3le(tle_line0, tle_line1, tle_line2, 60.0)

# Define ground station (Cape Canaveral)
lat = np.radians(28.3922)  # Latitude in radians
lon = np.radians(-80.6077)  # Longitude in radians
alt = 0.0  # Altitude in meters
station = bh.PointLocation(lat, lon, alt).with_name("Cape Canaveral")

# Define time range (one day to capture multiple passes)
epoch = prop.epoch
duration = 24.0 * 3600.0  # 24 hours in seconds

# Compute access windows
constraint = bh.ElevationConstraint(min_elevation_deg=10.0)
accesses = bh.location_accesses([station], [prop], epoch, epoch + duration, constraint)

# Create polar access plots (light and dark mode)
if len(accesses) > 0:
    # Use first 3 access windows
    num_windows = min(3, len(accesses))
    windows_to_plot = [
        {"access_window": accesses[i], "label": f"Access {i + 1}"}
        for i in range(num_windows)
    ]

    # Light mode
    fig = bh.plot_access_polar(
        windows_to_plot,
        prop,  # Propagator for interpolation
        min_elevation=10.0,
        backend="matplotlib",
    )

    # Save light mode figure
    fig.savefig(
        "docs/figures/plot_access_polar_matplotlib_light.svg",
        dpi=300,
        bbox_inches="tight",
    )
    print(
        "Access polar plot (matplotlib, light mode) saved to: docs/figures/plot_access_polar_matplotlib_light.svg"
    )
    plt.close(fig)

    # Dark mode
    with plt.style.context("dark_background"):
        fig = bh.plot_access_polar(
            windows_to_plot,
            prop,  # Propagator for interpolation
            min_elevation=10.0,
            backend="matplotlib",
        )

        # Set background color to match Plotly dark theme
        fig.patch.set_facecolor("#1c1e24")
        for ax in fig.get_axes():
            ax.set_facecolor("#1c1e24")

        # Save dark mode figure
        fig.savefig(
            "docs/figures/plot_access_polar_matplotlib_dark.svg",
            dpi=300,
            bbox_inches="tight",
        )
        print(
            "Access polar plot (matplotlib, dark mode) saved to: docs/figures/plot_access_polar_matplotlib_dark.svg"
        )
        plt.close(fig)
else:
    print("No access windows found in the specified time range")
```

The polar plot shows:

- **Radial axis**: Elevation angle (0° at edge, 90° at center)
- **Angular axis**: Azimuth (0° = North, 90° = East, 180° = South, 270° = West)
- **Satellite path**: Track showing where the satellite appears in the sky

## Elevation vs Azimuth Plot (Observed Horizon)

Elevation vs azimuth plots show satellite paths across the observed horizon, with azimuth on the X-axis and elevation on the Y-axis. This view is particularly useful for visualizing terrain obstructions and azimuth-dependent visibility constraints using **elevation masks**.

### Interactive Elevation vs Azimuth Plot (Plotly)


**Plot Source**

```python
"""
Access Elevation vs Azimuth Plot Example - Plotly Backend

This script demonstrates how to create an interactive elevation vs azimuth plot using the plotly backend.
Shows the satellite's trajectory across the observed horizon with a sinusoidal elevation mask.
"""

import os
import pathlib
import sys
import brahe as bh
import numpy as np

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))
from brahe_theme import save_themed_html

# Configuration
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# Initialize EOP data
bh.initialize_eop()

# ISS TLE for November 3, 2025
tle_line0 = "ISS (ZARYA)"
tle_line1 = "1 25544U 98067A   25306.42331346  .00010070  00000-0  18610-3 0  9999"
tle_line2 = "2 25544  51.6344 342.0717 0004969   8.9436 351.1640 15.49700017536601"

# Create SGP4 propagator
prop = bh.SGPPropagator.from_3le(tle_line0, tle_line1, tle_line2, 60.0)

# Define ground station (Cape Canaveral)
lat = 28.4740  # Latitude in degrees
lon = -80.5772  # Longitude in degrees
alt = 0.0  # Altitude in meters
station = bh.PointLocation(lon, lat, alt).with_name("Cape Canaveral")

# Define time range (one day to capture multiple passes)
epoch = prop.epoch
duration = 7.0 * 24.0 * 3600.0  # 24 hours in seconds


# Define sinusoidal elevation mask: 15° + 10° * sin(2*azimuth)
# This varies between 5° and 25° around the horizon
def elevation_mask(az):
    return 15.0 + 10.0 * np.sin(np.radians(2 * az)) + 5.0 * np.sin(np.radians(3 * az))


# Create ElevationMaskConstraint from the sinusoidal mask function
# Sample the mask at 36 points around the horizon (every 10 degrees)
mask_azimuths = np.arange(0, 360, 10)
mask_points = [(az, elevation_mask(az)) for az in mask_azimuths]
constraint = bh.ElevationMaskConstraint(mask_points)

# Compute access windows using the elevation mask constraint
accesses = bh.location_accesses([station], [prop], epoch, epoch + duration, constraint)
print(f"Computed {len(accesses)} access windows")

# Filter for passes longer than 5 minutes (300 seconds) to show complete passes
min_duration = 300.0  # seconds
long_passes = [acc for acc in accesses if acc.duration > min_duration]
print(f"Filtered to {len(long_passes)} long passes (> {min_duration} seconds)")

# Create elevation vs azimuth plot
if len(long_passes) > 0:
    # Use first 3 long passes for better visualization
    passes = long_passes[: min(3, len(long_passes))]
    window_configs = [
        {"access_window": passes[i], "label": f"Pass {i + 1}"}
        for i in range(len(passes))
    ]

    fig = bh.plot_access_elevation_azimuth(
        window_configs,
        prop,  # Propagator for interpolation
        elevation_mask=elevation_mask,
        backend="plotly",
    )

    # Save themed HTML files
    light_path, dark_path = save_themed_html(fig, OUTDIR / SCRIPT_NAME)
    print(f"✓ Generated {light_path}")
    print(f"✓ Generated {dark_path}")
else:
    print("No access windows found in the specified time range")
```

### Static Elevation vs Azimuth Plot (Matplotlib)


**Plot Source**

```python
"""
Access Elevation vs Azimuth Plot Example - Matplotlib Backend

This script demonstrates how to create an elevation vs azimuth plot using the matplotlib backend.
Shows the satellite's trajectory across the observed horizon with a sinusoidal elevation mask.
"""

import brahe as bh
import numpy as np
import matplotlib.pyplot as plt

# Initialize EOP data
bh.initialize_eop()

# ISS TLE for November 3, 2025
tle_line0 = "ISS (ZARYA)"
tle_line1 = "1 25544U 98067A   25306.42331346  .00010070  00000-0  18610-3 0  9999"
tle_line2 = "2 25544  51.6344 342.0717 0004969   8.9436 351.1640 15.49700017536601"

# Create SGP4 propagator
prop = bh.SGPPropagator.from_3le(tle_line0, tle_line1, tle_line2, 60.0)

# Define ground station (Cape Canaveral)
lat = 28.4740  # Latitude in degrees
lon = -80.5772  # Longitude in degrees
alt = 0.0  # Altitude in meters
station = bh.PointLocation(lon, lat, alt).with_name("Cape Canaveral")

# Define time range (one day to capture multiple passes)
epoch = prop.epoch
duration = 7.0 * 24.0 * 3600.0  # 24 hours in seconds


# Define sinusoidal elevation mask: 15° + 10° * sin(2*azimuth)
# This varies between 5° and 25° around the horizon
def elevation_mask(az):
    return 15.0 + 10.0 * np.sin(np.radians(2 * az)) + 5.0 * np.sin(np.radians(3 * az))


# Create ElevationMaskConstraint from the sinusoidal mask function
# Sample the mask at 36 points around the horizon (every 10 degrees)
mask_azimuths = np.arange(0, 360, 10)
mask_points = [(az, elevation_mask(az)) for az in mask_azimuths]
constraint = bh.ElevationMaskConstraint(mask_points)

# Compute access windows using the elevation mask constraint
accesses = bh.location_accesses([station], [prop], epoch, epoch + duration, constraint)
print(f"Computed {len(accesses)} access windows")

# Filter for passes longer than 5 minutes (300 seconds) to show complete passes
min_duration = 300.0  # seconds
long_passes = [acc for acc in accesses if acc.duration > min_duration]
print(f"Filtered to {len(long_passes)} long passes (> {min_duration} seconds)")

# Create elevation vs azimuth plots (light and dark mode)
if len(long_passes) > 0:
    # Use first 3 long passes for better visualization
    passes = long_passes[: min(3, len(long_passes))]
    window_configs = [
        {"access_window": passes[i], "label": f"Pass {i + 1}"}
        for i in range(len(passes))
    ]

    # Light mode
    fig = bh.plot_access_elevation_azimuth(
        window_configs,
        prop,  # Propagator for interpolation
        elevation_mask=elevation_mask,
        backend="matplotlib",
    )

    fig.savefig(
        "docs/figures/plot_access_elevation_azimuth_matplotlib_light.svg",
        dpi=300,
        bbox_inches="tight",
    )
    print(
        "Access elevation vs azimuth plot (matplotlib, light mode) saved to: "
        "docs/figures/plot_access_elevation_azimuth_matplotlib_light.svg"
    )
    plt.close(fig)

    # Dark mode
    with plt.style.context("dark_background"):
        fig = bh.plot_access_elevation_azimuth(
            window_configs,
            prop,  # Propagator for interpolation
            elevation_mask=elevation_mask,
            backend="matplotlib",
        )

        # Set background color to match Plotly dark theme
        fig.patch.set_facecolor("#1c1e24")
        for ax in fig.get_axes():
            ax.set_facecolor("#1c1e24")

        fig.savefig(
            "docs/figures/plot_access_elevation_azimuth_matplotlib_dark.svg",
            dpi=300,
            bbox_inches="tight",
        )
        print(
            "Access elevation vs azimuth plot (matplotlib, dark mode) saved to: "
            "docs/figures/plot_access_elevation_azimuth_matplotlib_dark.svg"
        )
        plt.close(fig)
else:
    print("No access windows found in the specified time range")
```

The elevation vs azimuth plot shows:

- **X-axis**: Azimuth angle (0° to 360°, North = 0°/360°)
- **Y-axis**: Elevation angle (0° to 90°)
- **Satellite trajectory**: Path across the sky from observer's perspective
- **Elevation mask** (shaded region): Visibility constraints varying with azimuth
- **Discontinuity handling**: Trajectories crossing 0°/360° azimuth are split to avoid artifacts

### Elevation Masks

Elevation masks define azimuth-dependent minimum elevation constraints. They can represent:

- **Terrain obstructions**: Mountains, buildings, trees
- **Antenna constraints**: Dish beamwidth, gimbal limits
- **Operational requirements**: RF interference avoidance zones

The example above uses a sinusoidal mask: **15° + 10° sin(2×azimuth)**, varying between 5° and 25° around the horizon.

#### Using Elevation Masks

Elevation masks can be specified in three ways:

```
# Constant elevation (simple value)
fig = bh.plot_access_elevation_azimuth(
    windows, prop,
    elevation_mask=10.0,  # 10° everywhere
    backend="matplotlib"
)

# Function of azimuth (variable constraint)
mask_fn = lambda az: 15.0 + 10.0 * np.sin(np.radians(2 * az))
fig = bh.plot_access_elevation_azimuth(
    windows, prop,
    elevation_mask=mask_fn,
    backend="matplotlib"
)

# Array of values (measured terrain profile)
azimuths = np.linspace(0, 360, 361)
elevations = [measured_elevation(az) for az in azimuths]
fig = bh.plot_access_elevation_azimuth(
    windows, prop,
    elevation_mask=elevations,  # Must match azimuth sampling
    backend="matplotlib"
)
```

Elevation masks are also supported in polar plots (`plot_access_polar`) where they appear as shaded regions around the plot edge.

## Elevation vs Time Plot

Time-series plots show how elevation angle changes throughout a satellite pass, useful for link budget analysis and antenna pointing.

### Interactive Elevation Plot (Plotly)


**Plot Source**

```python
"""
Access Elevation Plot Example - Plotly Backend

This script demonstrates how to create an interactive elevation vs time plot using the plotly backend.
Shows satellite elevation angle during a ground station pass.
"""

import os
import pathlib
import sys
import brahe as bh
import numpy as np

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))
from brahe_theme import save_themed_html

# Configuration
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# Initialize EOP data
bh.initialize_eop()

# ISS TLE for November 3, 2025
tle_line0 = "ISS (ZARYA)"
tle_line1 = "1 25544U 98067A   25306.42331346  .00010070  00000-0  18610-3 0  9999"
tle_line2 = "2 25544  51.6344 342.0717 0004969   8.9436 351.1640 15.49700017536601"

# Create SGP4 propagator
prop = bh.SGPPropagator.from_3le(tle_line0, tle_line1, tle_line2, 60.0)

# Define ground station (Cape Canaveral)
lat = np.radians(28.3922)  # Latitude in radians
lon = np.radians(-80.6077)  # Longitude in radians
alt = 0.0  # Altitude in meters
station = bh.PointLocation(lat, lon, alt).with_name("Cape Canaveral")

# Define time range (one day to capture multiple passes)
epoch = prop.epoch
duration = 24.0 * 3600.0  # 24 hours in seconds

# Compute access windows
constraint = bh.ElevationConstraint(min_elevation_deg=10.0)
accesses = bh.location_accesses([station], [prop], epoch, epoch + duration, constraint)

# Create elevation plot
if len(accesses) > 0:
    fig = bh.plot_access_elevation(
        [{"access_window": accesses[0]}],  # Use first access window
        prop,  # Propagator for interpolation
        backend="plotly",
    )

    # Save themed HTML files
    light_path, dark_path = save_themed_html(fig, OUTDIR / SCRIPT_NAME)
    print(f"✓ Generated {light_path}")
    print(f"✓ Generated {dark_path}")
else:
    print("No access windows found in the specified time range")
```

### Static Elevation Plot (Matplotlib)


**Plot Source**


```python
"""
Access Elevation Plot Example - Matplotlib Backend

This script demonstrates how to create an elevation vs time plot using the matplotlib backend.
Shows satellite elevation angle during a ground station pass.
"""

import brahe as bh
import numpy as np
import matplotlib.pyplot as plt

# Initialize EOP data
bh.initialize_eop()

# ISS TLE for November 3, 2025
tle_line0 = "ISS (ZARYA)"
tle_line1 = "1 25544U 98067A   25306.42331346  .00010070  00000-0  18610-3 0  9999"
tle_line2 = "2 25544  51.6344 342.0717 0004969   8.9436 351.1640 15.49700017536601"

# Create SGP4 propagator
prop = bh.SGPPropagator.from_3le(tle_line0, tle_line1, tle_line2, 60.0)

# Define ground station (Cape Canaveral)
lat = np.radians(28.3922)  # Latitude in radians
lon = np.radians(-80.6077)  # Longitude in radians
alt = 0.0  # Altitude in meters
station = bh.PointLocation(lat, lon, alt).with_name("Cape Canaveral")

# Define time range (one day to capture multiple passes)
epoch = prop.epoch
duration = 24.0 * 3600.0  # 24 hours in seconds

# Compute access windows
constraint = bh.ElevationConstraint(min_elevation_deg=10.0)
accesses = bh.location_accesses([station], [prop], epoch, epoch + duration, constraint)

# Create elevation plots (light and dark mode)
if len(accesses) > 0:
    # Light mode
    fig = bh.plot_access_elevation(
        [{"access_window": accesses[0]}],  # Use first access window
        prop,  # Propagator for interpolation
        backend="matplotlib",
    )

    # Save light mode figure
    fig.savefig(
        "docs/figures/plot_access_elevation_matplotlib_light.svg",
        dpi=300,
        bbox_inches="tight",
    )
    print(
        "Access elevation plot (matplotlib, light mode) saved to: docs/figures/plot_access_elevation_matplotlib_light.svg"
    )
    plt.close(fig)

    # Dark mode
    with plt.style.context("dark_background"):
        fig = bh.plot_access_elevation(
            [{"access_window": accesses[0]}],  # Use first access window
            prop,  # Propagator for interpolation
            backend="matplotlib",
        )

        # Set background color to match Plotly dark theme
        fig.patch.set_facecolor("#1c1e24")
        for ax in fig.get_axes():
            ax.set_facecolor("#1c1e24")

        # Save dark mode figure
        fig.savefig(
            "docs/figures/plot_access_elevation_matplotlib_dark.svg",
            dpi=300,
            bbox_inches="tight",
        )
        print(
            "Access elevation plot (matplotlib, dark mode) saved to: docs/figures/plot_access_elevation_matplotlib_dark.svg"
        )
        plt.close(fig)
else:
    print("No access windows found in the specified time range")
```

---

## See Also

- [plot_access_polar API Reference](../../library_api/plots/access_geometry.md)
- [plot_access_elevation_azimuth API Reference](../../library_api/plots/access_geometry.md)
- [plot_access_elevation API Reference](../../library_api/plots/access_geometry.md)
- [location_accesses](../../library_api/access/index.md) - Computing access windows
- [Ground Tracks](ground_tracks.md) - Visualizing coverage on maps
- [Access Constraints](../../library_api/access/constraints.md) - Defining visibility rules