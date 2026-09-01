# Visualizing GPS Satellite Orbits

In this example we'll show how to visualize the orbits of GPS satellites using Brahe. We'll download the latest TLE data for the GPS constellation from CelesTrak, propagate each satellite for one orbit, and create an interactive 3D plot showing their trajectories around Earth.

---

## Initialize Earth Orientation Parameters

Before starting, we need to import brahe and ensure that we have Earth orientation parameters initialized. We'll use `initialize_eop()`, which provides a [CachingEOPProvider](../library_api/eop/caching_provider.md) to deliver up-to-date Earth orientation parameters.

```python
#!/usr/bin/env python
# /// script
# dependencies = ["brahe", "plotly"]
# FLAGS = ["CI-ONLY"]
# TIMEOUT = 300
# ///

"""
Downloading TLE Data and Visualizing GPS Satellites

This example demonstrates how to:
1. Download TLE data from CelesTrak for the GPS Satellites
2. Create SGP4 propagators for all satellites
3. Propagate satellites to current epoch
4. Visualize the constellation in 3D space

The example shows the complete workflow from data download to visualization.
"""

# --8<-- [start:all]
# --8<-- [start:preamble]
import time

import brahe as bh

bh.initialize_eop()
# --8<-- [end:preamble]

# Download GP data for all GPS satellites from CelesTrak
# Uses CelestrakClient to query the "gps-ops" group, then converts
# each GP record into an SGP4 propagator with a 60-second step size
print("Downloading GPS GP records from CelesTrak...")
start_time = time.time()
# --8<-- [start:download_gps]
client = bh.celestrak.CelestrakClient()
records = client.get_gp(group="gps-ops")
propagators = [r.to_sgp_propagator(60.0) for r in records]
# --8<-- [end:download_gps]
elapsed = time.time() - start_time
print(
    f"Initialized propagators for {len(propagators)} GPS satellites in {elapsed:.2f} seconds."
)

ts = time.time()
# --8<-- [start:propagate_gps]
# Propagate each satellite one orbit
for prop in propagators:
    # --8<-- [start:compute_orbital_period]
    orbital_period = bh.orbital_period(prop.semi_major_axis)
    # --8<-- [end:compute_orbital_period]
    prop.propagate_to(prop.epoch + orbital_period)
# --8<-- [end:propagate_gps]
te = time.time() - ts
print(f"Propagated all satellites to one orbit in {te:.2f} seconds.")

# Create interactive 3D plot with Earth texture
print("\nCreating 3D visualization of satellites...")
ts = time.time()
# --8<-- [start:orbit_visualization]
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
    show_body=True,
    texture="natural_earth_50m",
    backend="plotly",
    view_azimuth=45.0,
    view_elevation=30.0,
    view_distance=2.0,
)
# --8<-- [end:orbit_visualization]
te = time.time() - ts
print(f"Created base 3D plot in {te:.2f} seconds.")
# --8<-- [end:all]

# ============================================================================
# Plot Output Section (for documentation generation)
# ============================================================================

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

## Download GPS TLEs

We'll use the [CelesTrak client](../library_api/ephemeris/celestrak.md) to fetch the latest GP data for all GPS satellites, then convert each record into an SGP4 propagator:

```python
#!/usr/bin/env python
# /// script
# dependencies = ["brahe", "plotly"]
# FLAGS = ["CI-ONLY"]
# TIMEOUT = 300
# ///

"""
Downloading TLE Data and Visualizing GPS Satellites

This example demonstrates how to:
1. Download TLE data from CelesTrak for the GPS Satellites
2. Create SGP4 propagators for all satellites
3. Propagate satellites to current epoch
4. Visualize the constellation in 3D space

The example shows the complete workflow from data download to visualization.
"""

# --8<-- [start:all]
# --8<-- [start:preamble]
import time

import brahe as bh

bh.initialize_eop()
# --8<-- [end:preamble]

# Download GP data for all GPS satellites from CelesTrak
# Uses CelestrakClient to query the "gps-ops" group, then converts
# each GP record into an SGP4 propagator with a 60-second step size
print("Downloading GPS GP records from CelesTrak...")
start_time = time.time()
# --8<-- [start:download_gps]
client = bh.celestrak.CelestrakClient()
records = client.get_gp(group="gps-ops")
propagators = [r.to_sgp_propagator(60.0) for r in records]
# --8<-- [end:download_gps]
elapsed = time.time() - start_time
print(
    f"Initialized propagators for {len(propagators)} GPS satellites in {elapsed:.2f} seconds."
)

ts = time.time()
# --8<-- [start:propagate_gps]
# Propagate each satellite one orbit
for prop in propagators:
    # --8<-- [start:compute_orbital_period]
    orbital_period = bh.orbital_period(prop.semi_major_axis)
    # --8<-- [end:compute_orbital_period]
    prop.propagate_to(prop.epoch + orbital_period)
# --8<-- [end:propagate_gps]
te = time.time() - ts
print(f"Propagated all satellites to one orbit in {te:.2f} seconds.")

# Create interactive 3D plot with Earth texture
print("\nCreating 3D visualization of satellites...")
ts = time.time()
# --8<-- [start:orbit_visualization]
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
    show_body=True,
    texture="natural_earth_50m",
    backend="plotly",
    view_azimuth=45.0,
    view_elevation=30.0,
    view_distance=2.0,
)
# --8<-- [end:orbit_visualization]
te = time.time() - ts
print(f"Created base 3D plot in {te:.2f} seconds.")
# --8<-- [end:all]

# ============================================================================
# Plot Output Section (for documentation generation)
# ============================================================================

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

## Propagate orbits

Next, we'll propagate each satellite for one full orbit based on its semi-major axis:

```python
#!/usr/bin/env python
# /// script
# dependencies = ["brahe", "plotly"]
# FLAGS = ["CI-ONLY"]
# TIMEOUT = 300
# ///

"""
Downloading TLE Data and Visualizing GPS Satellites

This example demonstrates how to:
1. Download TLE data from CelesTrak for the GPS Satellites
2. Create SGP4 propagators for all satellites
3. Propagate satellites to current epoch
4. Visualize the constellation in 3D space

The example shows the complete workflow from data download to visualization.
"""

# --8<-- [start:all]
# --8<-- [start:preamble]
import time

import brahe as bh

bh.initialize_eop()
# --8<-- [end:preamble]

# Download GP data for all GPS satellites from CelesTrak
# Uses CelestrakClient to query the "gps-ops" group, then converts
# each GP record into an SGP4 propagator with a 60-second step size
print("Downloading GPS GP records from CelesTrak...")
start_time = time.time()
# --8<-- [start:download_gps]
client = bh.celestrak.CelestrakClient()
records = client.get_gp(group="gps-ops")
propagators = [r.to_sgp_propagator(60.0) for r in records]
# --8<-- [end:download_gps]
elapsed = time.time() - start_time
print(
    f"Initialized propagators for {len(propagators)} GPS satellites in {elapsed:.2f} seconds."
)

ts = time.time()
# --8<-- [start:propagate_gps]
# Propagate each satellite one orbit
for prop in propagators:
    # --8<-- [start:compute_orbital_period]
    orbital_period = bh.orbital_period(prop.semi_major_axis)
    # --8<-- [end:compute_orbital_period]
    prop.propagate_to(prop.epoch + orbital_period)
# --8<-- [end:propagate_gps]
te = time.time() - ts
print(f"Propagated all satellites to one orbit in {te:.2f} seconds.")

# Create interactive 3D plot with Earth texture
print("\nCreating 3D visualization of satellites...")
ts = time.time()
# --8<-- [start:orbit_visualization]
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
    show_body=True,
    texture="natural_earth_50m",
    backend="plotly",
    view_azimuth=45.0,
    view_elevation=30.0,
    view_distance=2.0,
)
# --8<-- [end:orbit_visualization]
te = time.time() - ts
print(f"Created base 3D plot in {te:.2f} seconds.")
# --8<-- [end:all]

# ============================================================================
# Plot Output Section (for documentation generation)
# ============================================================================

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

The line 
```python
#!/usr/bin/env python
# /// script
# dependencies = ["brahe", "plotly"]
# FLAGS = ["CI-ONLY"]
# TIMEOUT = 300
# ///

"""
Downloading TLE Data and Visualizing GPS Satellites

This example demonstrates how to:
1. Download TLE data from CelesTrak for the GPS Satellites
2. Create SGP4 propagators for all satellites
3. Propagate satellites to current epoch
4. Visualize the constellation in 3D space

The example shows the complete workflow from data download to visualization.
"""

# --8<-- [start:all]
# --8<-- [start:preamble]
import time

import brahe as bh

bh.initialize_eop()
# --8<-- [end:preamble]

# Download GP data for all GPS satellites from CelesTrak
# Uses CelestrakClient to query the "gps-ops" group, then converts
# each GP record into an SGP4 propagator with a 60-second step size
print("Downloading GPS GP records from CelesTrak...")
start_time = time.time()
# --8<-- [start:download_gps]
client = bh.celestrak.CelestrakClient()
records = client.get_gp(group="gps-ops")
propagators = [r.to_sgp_propagator(60.0) for r in records]
# --8<-- [end:download_gps]
elapsed = time.time() - start_time
print(
    f"Initialized propagators for {len(propagators)} GPS satellites in {elapsed:.2f} seconds."
)

ts = time.time()
# --8<-- [start:propagate_gps]
# Propagate each satellite one orbit
for prop in propagators:
    # --8<-- [start:compute_orbital_period]
    orbital_period = bh.orbital_period(prop.semi_major_axis)
    # --8<-- [end:compute_orbital_period]
    prop.propagate_to(prop.epoch + orbital_period)
# --8<-- [end:propagate_gps]
te = time.time() - ts
print(f"Propagated all satellites to one orbit in {te:.2f} seconds.")

# Create interactive 3D plot with Earth texture
print("\nCreating 3D visualization of satellites...")
ts = time.time()
# --8<-- [start:orbit_visualization]
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
    show_body=True,
    texture="natural_earth_50m",
    backend="plotly",
    view_azimuth=45.0,
    view_elevation=30.0,
    view_distance=2.0,
)
# --8<-- [end:orbit_visualization]
te = time.time() - ts
print(f"Created base 3D plot in {te:.2f} seconds.")
# --8<-- [end:all]

# ============================================================================
# Plot Output Section (for documentation generation)
# ============================================================================

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
computes the or orbital period of the satellite by converting the semi-major axis associated with the `SGP4Propagator` into an orbital period using Brahe's `orbital_period` function.

It then propagates the satellite to one full orbit past its epoch using the `propagate_to` method to ensure that the trajectory contains position data for one complete orbit.

**to_sgp_propagator builds a propagator without TLE round-tripping**
[`GPRecord.to_sgp_propagator`](../learn/ephemeris/celestrak.md)
([API](../library_api/ephemeris/shared_types.md#brahe.GPRecord.to_sgp_propagator))
constructs an [`SGPPropagator`](../library_api/propagators/sgp_propagator.md)
directly from the record's OMM orbital elements rather than serializing
them through fixed-width TLE text first, so no numeric precision is lost
to the TLE format. Its argument is the propagator step size in seconds
(60 s here), which sets the spacing of the recorded trajectory states -
the markers the 3D plot below draws. Each propagator is initialized at
its own record's epoch, and GP epochs differ across a constellation, so
"one orbital period past `prop.epoch`" is a slightly different absolute
time span for every satellite. Propagate all satellites to a shared epoch
first for any analysis that compares the constellation at one instant.

## Visualize in 3D

We'll create an interactive 3D visualization of the entire GPS constellation using Plotly. We'll use the Natural Earth 50m texture for a realistic Earth representation:

```python
#!/usr/bin/env python
# /// script
# dependencies = ["brahe", "plotly"]
# FLAGS = ["CI-ONLY"]
# TIMEOUT = 300
# ///

"""
Downloading TLE Data and Visualizing GPS Satellites

This example demonstrates how to:
1. Download TLE data from CelesTrak for the GPS Satellites
2. Create SGP4 propagators for all satellites
3. Propagate satellites to current epoch
4. Visualize the constellation in 3D space

The example shows the complete workflow from data download to visualization.
"""

# --8<-- [start:all]
# --8<-- [start:preamble]
import time

import brahe as bh

bh.initialize_eop()
# --8<-- [end:preamble]

# Download GP data for all GPS satellites from CelesTrak
# Uses CelestrakClient to query the "gps-ops" group, then converts
# each GP record into an SGP4 propagator with a 60-second step size
print("Downloading GPS GP records from CelesTrak...")
start_time = time.time()
# --8<-- [start:download_gps]
client = bh.celestrak.CelestrakClient()
records = client.get_gp(group="gps-ops")
propagators = [r.to_sgp_propagator(60.0) for r in records]
# --8<-- [end:download_gps]
elapsed = time.time() - start_time
print(
    f"Initialized propagators for {len(propagators)} GPS satellites in {elapsed:.2f} seconds."
)

ts = time.time()
# --8<-- [start:propagate_gps]
# Propagate each satellite one orbit
for prop in propagators:
    # --8<-- [start:compute_orbital_period]
    orbital_period = bh.orbital_period(prop.semi_major_axis)
    # --8<-- [end:compute_orbital_period]
    prop.propagate_to(prop.epoch + orbital_period)
# --8<-- [end:propagate_gps]
te = time.time() - ts
print(f"Propagated all satellites to one orbit in {te:.2f} seconds.")

# Create interactive 3D plot with Earth texture
print("\nCreating 3D visualization of satellites...")
ts = time.time()
# --8<-- [start:orbit_visualization]
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
    show_body=True,
    texture="natural_earth_50m",
    backend="plotly",
    view_azimuth=45.0,
    view_elevation=30.0,
    view_distance=2.0,
)
# --8<-- [end:orbit_visualization]
te = time.time() - ts
print(f"Created base 3D plot in {te:.2f} seconds.")
# --8<-- [end:all]

# ============================================================================
# Plot Output Section (for documentation generation)
# ============================================================================

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

The resulting plot shows the complete GPS constellation orbiting Earth. The interactive visualization allows you to rotate, zoom, and pan to explore the satellite positions from different angles.


## Full Code Example

**Full Code**

```
#!/usr/bin/env python
# /// script
# dependencies = ["brahe", "plotly"]
# FLAGS = ["CI-ONLY"]
# TIMEOUT = 300
# ///

"""
Downloading TLE Data and Visualizing GPS Satellites

This example demonstrates how to:
1. Download TLE data from CelesTrak for the GPS Satellites
2. Create SGP4 propagators for all satellites
3. Propagate satellites to current epoch
4. Visualize the constellation in 3D space

The example shows the complete workflow from data download to visualization.
"""

# --8<-- [start:all]
# --8<-- [start:preamble]
import time

import brahe as bh

bh.initialize_eop()
# --8<-- [end:preamble]

# Download GP data for all GPS satellites from CelesTrak
# Uses CelestrakClient to query the "gps-ops" group, then converts
# each GP record into an SGP4 propagator with a 60-second step size
print("Downloading GPS GP records from CelesTrak...")
start_time = time.time()
# --8<-- [start:download_gps]
client = bh.celestrak.CelestrakClient()
records = client.get_gp(group="gps-ops")
propagators = [r.to_sgp_propagator(60.0) for r in records]
# --8<-- [end:download_gps]
elapsed = time.time() - start_time
print(
    f"Initialized propagators for {len(propagators)} GPS satellites in {elapsed:.2f} seconds."
)

ts = time.time()
# --8<-- [start:propagate_gps]
# Propagate each satellite one orbit
for prop in propagators:
    # --8<-- [start:compute_orbital_period]
    orbital_period = bh.orbital_period(prop.semi_major_axis)
    # --8<-- [end:compute_orbital_period]
    prop.propagate_to(prop.epoch + orbital_period)
# --8<-- [end:propagate_gps]
te = time.time() - ts
print(f"Propagated all satellites to one orbit in {te:.2f} seconds.")

# Create interactive 3D plot with Earth texture
print("\nCreating 3D visualization of satellites...")
ts = time.time()
# --8<-- [start:orbit_visualization]
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
    show_body=True,
    texture="natural_earth_50m",
    backend="plotly",
    view_azimuth=45.0,
    view_elevation=30.0,
    view_distance=2.0,
)
# --8<-- [end:orbit_visualization]
te = time.time() - ts
print(f"Created base 3D plot in {te:.2f} seconds.")
# --8<-- [end:all]

# ============================================================================
# Plot Output Section (for documentation generation)
# ============================================================================

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

- [CelesTrak Dataset](../learn/ephemeris/celestrak.md) - More details on using CelesTrak datasets
- [Two-Line Elements](../learn/orbits/two_line_elements.md) - Understanding TLE format and usage
- [SGP4 Propagator](../learn/orbit_propagation/sgp_propagation.md) - How SGP4 works for orbit propagation
- [3D Trajectory Plotting](../learn/plots/3d_trajectory.md) - Advanced options for trajectory visualization