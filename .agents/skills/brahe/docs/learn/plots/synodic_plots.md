# Synodic Frame Trajectory Plots

`plot_synodic_3d` renders 3D trajectories in a synodic (two-body rotating) frame: EMR (Earth-Moon Rotating), SER (Sun-Earth Rotating), GSE (Geocentric Solar Ecliptic), or a generic `ReferenceFrame.Synodic(origin, primary, secondary)`. Each input trajectory is converted to ECI and then transformed per-epoch into the requested frame via `state_frame_to_frame`. The frame's primary and secondary bodies are drawn as textured spheres at a single reference epoch, since a synodic frame keeps both bodies on the x-axis at all times.

`plot_earth_moon_rotating_3d` is an alias for `plot_synodic_3d(trajectories, frame="EMR", ...)`; it accepts the same keyword arguments.

## Input Requirement

`plot_synodic_3d` only accepts `OrbitTrajectory` objects, unlike `plot_trajectory_3d` and brahe's other plotting functions, which also accept propagators or raw arrays. Pass a `KeplerianPropagator`'s or numerical propagator's `.trajectory` attribute directly.

## Frame Selection

The `frame` parameter accepts:

- A frame alias string: `'EMR'`, `'SER'`, or `'GSE'`
- Any other `ReferenceFrame` name string accepted by `ReferenceFrame.from_string`
- A `ReferenceFrame.Synodic(origin, primary, secondary)` instance for a custom two-body pair

See [Synodic Reference Frames](../frames/synodic_frames.md) for the axis construction and physical definition of each frame. Passing a non-synodic frame raises `ValueError`.

## Reference Epoch

`reference_epoch` sets the epoch at which the primary and secondary spheres are placed. It defaults to the first epoch of the first trajectory in `trajectories`, and must be supplied explicitly if `trajectories` is empty.

## Example

The example below propagates a LEO trajectory with a `KeplerianPropagator`, then renders it in the Earth-Moon Rotating frame with `plot_earth_moon_rotating_3d` - the `plot_synodic_3d(..., frame="EMR", ...)` alias described above.


**Plot Source**

```python
#!/usr/bin/env python
# /// script
# dependencies = ["brahe", "plotly", "numpy"]
# FLAGS = ["NETWORK"]
# ///
"""
Synodic Frame Trajectory Plotting Example - Plotly Backend

This script demonstrates how to create an interactive 3D trajectory plot in
the Earth-Moon Rotating (EMR) frame using the plotly backend. Shows a LEO
orbit alongside the Earth and Moon, both fixed on the synodic x-axis.
"""

import os
import pathlib
import sys

import numpy as np

import brahe as bh

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))
from brahe_theme import save_themed_html

# Configuration
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# Initialize EOP data and the DE440s ephemeris the EMR transform needs
bh.initialize_eop()
bh.load_common_spice_kernels()

# LEO orbit (51.6 deg inclination, ~500 km altitude)
epoch = bh.Epoch.from_datetime(2024, 3, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
oe = np.array([bh.R_EARTH + 500e3, 0.001, 51.6, 15.0, 30.0, 45.0])
state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

prop = bh.KeplerianPropagator.from_eci(epoch, state, 60.0)
prop.propagate_to(epoch + bh.orbital_period(oe[0]))

# Create the Earth-Moon Rotating 3D trajectory plot
fig = bh.plot_earth_moon_rotating_3d(
    [{"trajectory": prop.trajectory, "color": "red", "label": "LEO"}],
    backend="plotly",
)

# Save as interactive HTML (small file size, no large textures)
light_path, dark_path = save_themed_html(fig, OUTDIR / SCRIPT_NAME)
print(f"✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")

print("\nSynodic plot generated successfully!")
```

## Additional Bodies

The `bodies` parameter adds extra textured spheres beyond the frame's primary/secondary, each a dict with `position` (meters, in the synodic frame), `radius` (meters), `texture`, and `name` - the same shape as `additional_bodies` in [`plot_trajectory_3d`](3d_trajectory.md).

## Shared Parameters

`units`, `view_azimuth`, `view_elevation`, `view_distance`, `sphere_resolution_lon`, `sphere_resolution_lat`, `backend`, `width`, and `height` behave identically to [`plot_trajectory_3d`](3d_trajectory.md).

Primary/secondary body textures are downloaded on first use from Solar System Scope:

*Body textures: [Solar System Scope](https://www.solarsystemscope.com/textures/), CC BY 4.0.*

---

## See Also

- [3D Trajectory Plots](3d_trajectory.md) - Central-body-centered inertial trajectory plots
- [Synodic Reference Frames](../frames/synodic_frames.md) - EMR, SER, GSE frame definitions
- [Coordinate Systems](../coordinates/index.md) - Understanding reference frames