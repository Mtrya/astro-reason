# Gabbard Diagrams

A Gabbard diagram plots orbital period versus apogee and perigee altitude, providing a unique visualization for analyzing debris clouds, satellite breakups, and orbital constellations. Each object appears as two points: one for apogee altitude and one for perigee altitude, both at the same orbital period. This creates a characteristic pattern that reveals the distribution and evolution of orbital populations.

## Interactive Gabbard Diagram (Plotly)

The plotly backend allows you to zoom into specific regions and hover over points to see exact values.


**Plot Source**

```python
"""
Gabbard Diagram Example - Plotly Backend

This script demonstrates how to create an interactive Gabbard diagram using the plotly backend.
A Gabbard diagram plots orbital period vs apogee/perigee altitude, useful for analyzing
debris clouds or satellite constellations.
"""

import os
import pathlib
import sys
import brahe as bh

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))
from brahe_theme import save_themed_html

# Configuration
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# Initialize EOP data
bh.initialize_eop()

# Get Ephemeris and debris for major events:
client = bh.celestrak.CelestrakClient()

cosmos_1408_records = client.get_gp(group="cosmos-1408-debris")
cosmos_1408_debris = [r.to_sgp_propagator(60.0) for r in cosmos_1408_records]

fengyun_records = client.get_gp(group="fengyun-1c-debris")
fengyun_debris = [r.to_sgp_propagator(60.0) for r in fengyun_records]

iridium_records = client.get_gp(group="iridium-33-debris")
iridium_debris = [r.to_sgp_propagator(60.0) for r in iridium_records]

cosmos_2251_records = client.get_gp(group="cosmos-2251-debris")
cosmos_2251_debris = [r.to_sgp_propagator(60.0) for r in cosmos_2251_records]

all_debris = cosmos_1408_debris + fengyun_debris + iridium_debris + cosmos_2251_debris

print(f"Cosmos 1408 debris objects: {len(cosmos_1408_debris)}")
print(f"Fengyun-1C debris objects: {len(fengyun_debris)}")
print(f"Iridium 33 debris objects: {len(iridium_debris)}")
print(f"Cosmos 2251 debris objects: {len(cosmos_2251_debris)}")
print(f"Total debris objects loaded: {len(all_debris)}")

# Get epoch of first debris object
epoch = all_debris[0].epoch

# Get ISS ephemeris for reference altitude line
iss = client.get_sgp_propagator(catnr=25544, step_size=60.0)
iss_state = iss.state_eci(epoch)
iss_oe = bh.state_eci_to_koe(iss_state, bh.AngleFormat.RADIANS)
iss_altitude_km = (iss_oe[0] - bh.R_EARTH) / 1e3  # Convert to km

print(f"ISS altitude at epoch: {iss_altitude_km:.1f} km")

# Create Gabbard diagram
fig = bh.plot_gabbard_diagram(all_debris, epoch, backend="plotly")

# Add ISS altitude reference line
fig.add_hline(
    y=iss_altitude_km,
    line_dash="dash",
    line_color="orange",
    line_width=2,
    annotation_text=f"ISS Altitude ({iss_altitude_km:.1f} km)",
    annotation_position="right",
)

# Save themed HTML files
light_path, dark_path = save_themed_html(fig, OUTDIR / SCRIPT_NAME)
print(f"✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")
```

## Static Gabbard Diagram (Matplotlib)

The matplotlib backend produces publication-quality figures for research papers and technical reports.


**Plot Source**

```python
"""
Gabbard Diagram Example - Matplotlib Backend

This script demonstrates how to create a Gabbard diagram using the matplotlib backend.
A Gabbard diagram plots orbital period vs apogee/perigee altitude, useful for analyzing
debris clouds or satellite constellations.
"""

import os
import pathlib
import brahe as bh
import matplotlib.pyplot as plt

# Configuration
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# Initialize EOP data
bh.initialize_eop()

# Get Ephemeris and debris for major events:
client = bh.celestrak.CelestrakClient()

cosmos_1408_records = client.get_gp(group="cosmos-1408-debris")
cosmos_1408_debris = [r.to_sgp_propagator(60.0) for r in cosmos_1408_records]

fengyun_records = client.get_gp(group="fengyun-1c-debris")
fengyun_debris = [r.to_sgp_propagator(60.0) for r in fengyun_records]

iridium_records = client.get_gp(group="iridium-33-debris")
iridium_debris = [r.to_sgp_propagator(60.0) for r in iridium_records]

cosmos_2251_records = client.get_gp(group="cosmos-2251-debris")
cosmos_2251_debris = [r.to_sgp_propagator(60.0) for r in cosmos_2251_records]

all_debris = cosmos_1408_debris + fengyun_debris + iridium_debris + cosmos_2251_debris

print(f"Cosmos 1408 debris objects: {len(cosmos_1408_debris)}")
print(f"Fengyun-1C debris objects: {len(fengyun_debris)}")
print(f"Iridium 33 debris objects: {len(iridium_debris)}")
print(f"Cosmos 2251 debris objects: {len(cosmos_2251_debris)}")
print(f"Total debris objects loaded: {len(all_debris)}")

# Get epoch of first debris object
epoch = all_debris[0].epoch

# Get ISS ephemeris for reference altitude line
iss = client.get_sgp_propagator(catnr=25544, step_size=60.0)
iss_state = iss.state_eci(epoch)
iss_oe = bh.state_eci_to_koe(iss_state, bh.AngleFormat.RADIANS)
iss_altitude_km = (iss_oe[0] - bh.R_EARTH) / 1e3  # Convert to km

print(f"ISS altitude at epoch: {iss_altitude_km:.1f} km")

# Create Gabbard diagram in light mode
fig = bh.plot_gabbard_diagram(all_debris, epoch, backend="matplotlib")

# Add ISS altitude reference line
ax = fig.get_axes()[0]
ax.axhline(
    y=iss_altitude_km,
    color="green",
    linestyle="--",
    linewidth=2,
    label=f"ISS Altitude ({iss_altitude_km:.1f} km)",
)
ax.legend()

# Save light mode figure
light_path = OUTDIR / f"{SCRIPT_NAME}_light.svg"
fig.savefig(light_path, dpi=300, bbox_inches="tight")
print(f"✓ Generated {light_path}")
plt.close(fig)

# Create Gabbard diagram in dark mode
with plt.style.context("dark_background"):
    fig = bh.plot_gabbard_diagram(all_debris, epoch, backend="matplotlib")

    # Set background color to match Plotly dark theme
    fig.patch.set_facecolor("#1c1e24")
    for ax in fig.get_axes():
        ax.set_facecolor("#1c1e24")

    # Add ISS altitude reference line
    ax = fig.get_axes()[0]
    ax.axhline(
        y=iss_altitude_km,
        color="orange",
        linestyle="--",
        linewidth=2,
        label=f"ISS Altitude ({iss_altitude_km:.1f} km)",
    )
    ax.legend()

    # Save dark mode figure
    dark_path = OUTDIR / f"{SCRIPT_NAME}_dark.svg"
    fig.savefig(dark_path, dpi=300, bbox_inches="tight")
    print(f"✓ Generated {dark_path}")
    plt.close(fig)
```

## Understanding the Diagram

### Reading the Plot

- **X-axis**: Orbital period (minutes or hours)
- **Y-axis**: Altitude (km)
- **Each object creates TWO points**:
    - Upper point: Apogee altitude
    - Lower point: Perigee altitude

### Interpreting Patterns

**Tight vertical pairs**: Low eccentricity (near-circular orbits)

**Wide vertical separation**: High eccentricity (elliptical orbits)

## Tips

- Use `backend="plotly"` to identify outliers and explore specific objects interactively
- Add reference lines for altitude constraints (e.g., ISS orbit, debris-heavy regions)

---

## See Also

- [Keplerian Elements](../orbits/index.md) - Understanding orbital parameters
- [Propagators](../../library_api/propagators/index.md) - Creating propagators from TLEs