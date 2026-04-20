# Plotting & Visualization

Brahe provides quick and convenient plotting functions for visualizing orbital trajectories, ground tracks, access windows, and other astrodynamics data. The plotting module is designed to make it easy to generate publication-quality figures with minimal code while offering flexibility for customization.

**Experimental API**
The plotting API in brahe is currently experimental and may undergo significant changes in future releases. While we strive to maintain backward compatibility, functions, parameters, or behaviors may change as we refine the plotting capabilities based on user feedback and evolving best practices in data visualization. These changes may occur in minor or patch releases.

## Dual Backend System

All plotting functions in brahe support two rendering backends, allowing you to choose the best tool for your workflow:

### Matplotlib Backend

The **matplotlib** backend generates static, publication-ready figures. This is the default backend and is ideal for academic papers and technical reports.

```
import brahe as bh

# Use matplotlib backend (default)
fig = bh.plot_groundtrack(
    trajectories=[{"trajectory": traj}],
    backend="matplotlib"
)
fig.savefig("groundtrack.png", dpi=300)
```

#### Science Plots Styling

Brahe integrates with the [`scienceplots`](https://github.com/garrettj403/SciencePlots) package to provide publication-quality matplotlib styling. When `scienceplots` is installed, brahe automatically applies clean, professional styling to matplotlib plots.

To enable science plots styling either install brahe with all optional dependencies:

```
pip install brahe[all]
```

Or install `scienceplots` separately:

```
pip install scienceplots
```

To take full advantage of science plots styling, you can need a $\LaTeX$ installation on your system, as `scienceplots` uses LaTeX for rendering text in plots. See the [scienceplots documentation](https://github.com/garrettj403/SciencePlots/wiki/FAQ#installing-latex) for guidance on setting up LaTeX.

If `scienceplots` is not installed, brahe falls back to standard matplotlib styling.

### Plotly Backend

The **plotly** backend creates interactive HTML figures that can be explored in a web browser. This backend is perfect for interactive exploration of data or sharing results via web pages or notebooks.

```
import brahe as bh

# Use plotly backend for interactive plots
fig = bh.plot_groundtrack(
    trajectories=[{"trajectory": traj}],
    backend="plotly"
)
fig.write_html("groundtrack.html")
fig.show()  # Opens in browser
```

Both backends use the same function signatures and parameters, making it trivial to switch between static and interactive outputs.

## Available Plot Types

Brahe provides specialized plotting functions for common astrodynamics visualization tasks:

### [Ground Track Plots](ground_tracks.md)

Visualize satellite ground tracks on a world map with ground stations and communication coverage zones.

```
fig = bh.plot_groundtrack(
    trajectories=[{"trajectory": orbit_traj}],
    ground_stations=[{"stations": [station1, station2]}]
)
```

### [3D Trajectory Plots](3d_trajectory.md)

Visualize orbital trajectories in 3D space with an optional Earth sphere.

```
fig = bh.plot_trajectory_3d(
    [{"trajectory": traj, "label": "LEO Orbit"}],
    show_earth=True
)
```

### [Access Geometry Plots](access_geometry.md)

Visualize satellite visibility from ground stations using polar plots (azimuth/elevation) or elevation profiles over time.

```
# Polar plot showing satellite path in sky
fig = bh.plot_access_polar(access_window)

# Elevation angle over time
fig = bh.plot_access_elevation(access_window)
```

### [Orbital Element Plots](orbital_trajectories.md)

Track how orbital elements evolve over time in both Cartesian and Keplerian representations.

```
# Plot position and velocity components
fig = bh.plot_cartesian_trajectory([{"trajectory": traj}])

# Plot Keplerian elements (a, e, i, Ω, ω, ν)
fig = bh.plot_keplerian_trajectory([{"trajectory": traj}])
```

### [Gabbard Diagrams](gabbard_plot.md)

Analyze debris clouds or satellite constellations by plotting orbital period versus apogee/perigee altitude.

```
fig = bh.plot_gabbard_diagram(
    propagators=[prop1, prop2, prop3],
    epoch=epoch
)
```

### [Estimation Plots](estimation.md)

Visualize estimation filter performance with state error grids, covariance bounds, measurement residuals, and marginal distributions.

```
fig = bh.plot_estimator_state_error_grid(
    solvers=[ekf], true_trajectory=truth_traj, sigma=3
)
```

## Common Features

All plotting functions share consistent design patterns:

- **Grouped plotting**: Plot multiple trajectories, stations, or objects with different colors and labels
- **Flexible inputs**: Accept propagators, trajectories, or raw numpy arrays
- **Unit conversion**: Automatic handling of meters/kilometers, radians/degrees, etc.
- **Time filtering**: Optional time range filtering for all trajectory plots
- **Customization**: Control colors, line widths, markers, and other visual properties

## Quick Start Example

This example shows how to create a simple LEO orbit and visualize it in 3D. It demonstrates the core plotting workflow: define an orbit, propagate it, and visualize the results. Both plotly and matplotlib backends are shown.

**Matplotlib 3D Visualization Limitations**
The matplotlib 3D backend does not have a true 3D perspective camera model. Instead is uses a 2D layering system where entire objects (e.g., the entire orbit line, the entire sphere surface) are drawn one on top of the other based on a single, fixed `zorder` value. 

This can lead to visual artifacts where parts of objects that should be behind other objects are incorrectly drawn in front. For example, the far side of an orbit may appear in front of the Earth sphere.

### Interactive Plot (Plotly)


???+ "Plot Source"
```python
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# Initialize EOP data
bh.initialize_eop()

# Create a simple LEO orbit
epoch = bh.Epoch.from_datetime(2025, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
oe = np.array([bh.R_EARTH + 500e3, 0.01, 97.8, 0.0, 0.0, 0.0])

# Create propagator and generate trajectory
prop = bh.KeplerianPropagator.from_keplerian(epoch, oe, bh.AngleFormat.DEGREES, 5.0)
prop.propagate_to(epoch + bh.orbital_period(oe[0]))
traj = prop.trajectory

# Create an interactive 3D plot
fig = bh.plot_trajectory_3d(
    [{"trajectory": traj, "color": "red", "label": "LEO"}],
    show_earth=True,
    backend="plotly",
)

# Save themed HTML files
light_path, dark_path = save_themed_html(fig, OUTDIR / SCRIPT_NAME)
print(f"✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")
```

### Static Plot (Matplotlib)


???+  "Plot Source"
```python
import brahe as bh
import numpy as np
import matplotlib.pyplot as plt

# Initialize EOP data
bh.initialize_eop()

# Create a simple LEO orbit
epoch = bh.Epoch.from_datetime(2025, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
oe = np.array([bh.R_EARTH + 500e3, 0.01, 97.8, 0.0, 0.0, 0.0])
state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

# Create propagator and generate trajectory
prop = bh.KeplerianPropagator.from_eci(epoch, state, 60.0)
prop.propagate_to(epoch + bh.orbital_period(oe[0]))
traj = prop.trajectory

# Create a 3D plot in light mode
fig = bh.plot_trajectory_3d(
    [{"trajectory": traj, "color": "red", "label": "LEO"}],
    show_earth=True,
    backend="matplotlib",
)

# Save light mode figure
fig.savefig(
    "docs/figures/plot_quickstart_example_matplotlib_light.svg",
    dpi=300,
    bbox_inches="tight",
)
print(
    "Quick start example plot (matplotlib, light mode) saved to: docs/figures/plot_quickstart_example_matplotlib_light.svg"
)
plt.close(fig)

# Create a 3D plot in dark mode
with plt.style.context("dark_background"):
    fig = bh.plot_trajectory_3d(
        [{"trajectory": traj, "color": "red", "label": "LEO"}],
        show_earth=True,
        backend="matplotlib",
    )

    # Set background color to match Plotly dark theme
    fig.patch.set_facecolor("#1c1e24")
    for ax in fig.get_axes():
        ax.set_facecolor("#1c1e24")

    # Save dark mode figure
    fig.savefig(
        "docs/figures/plot_quickstart_example_matplotlib_dark.svg",
        dpi=300,
        bbox_inches="tight",
    )
    print(
        "Quick start example plot (matplotlib, dark mode) saved to: docs/figures/plot_quickstart_example_matplotlib_dark.svg"
    )
    plt.close(fig)
```

---

## See Also

- [Ground Track Plotting](ground_tracks.md) - Satellite ground tracks and coverage
- [Gabbard Diagrams](gabbard_plot.md) - Debris cloud analysis
- [3D Trajectories](3d_trajectory.md) - Orbital paths in 3D space
- [Access Geometry](access_geometry.md) - Ground station visibility
- [Orbital Elements](orbital_trajectories.md) - Element evolution over time
- [API Reference](../../library_api/plots/index.md) - Complete function documentation