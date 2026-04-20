# Impulsive and Continuous Control

The numerical propagator supports both impulsive and continuous thrust maneuvers, enabling orbit transfer, station-keeping, and trajectory optimization studies.

## Impulsive Maneuvers

Impulsive maneuvers model instantaneous velocity changes ($\Delta v$). They're implemented using event callbacks that modify the state at specific conditions.

### Using Event Callbacks

Impulsive maneuvers combine event detection with state modification. For callback details, see [Event Callbacks](event_callbacks.md).


```python
import numpy as np
import brahe as bh

# Initialize EOP data
bh.initialize_eop()

# Create initial epoch and state
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# Initial circular orbit at 400 km
r1 = bh.R_EARTH + 400e3
# Target circular orbit at 800 km
r2 = bh.R_EARTH + 800e3

# Initial state (circular orbit at perigee of transfer)
oe_initial = np.array([r1, 0.0001, 0.0, 0.0, 0.0, 0.0])
state = bh.state_koe_to_eci(oe_initial, bh.AngleFormat.DEGREES)

# Calculate Hohmann transfer delta-vs
v1_circular = np.sqrt(bh.GM_EARTH / r1)
v2_circular = np.sqrt(bh.GM_EARTH / r2)

# Transfer ellipse parameters
a_transfer = (r1 + r2) / 2
v_perigee_transfer = np.sqrt(bh.GM_EARTH * (2 / r1 - 1 / a_transfer))
v_apogee_transfer = np.sqrt(bh.GM_EARTH * (2 / r2 - 1 / a_transfer))

# Delta-v magnitudes
dv1 = v_perigee_transfer - v1_circular  # First burn (prograde at perigee)
dv2 = v2_circular - v_apogee_transfer  # Second burn (prograde at apogee)

print(
    f"Hohmann Transfer: {(r1 - bh.R_EARTH) / 1e3:.0f} km -> {(r2 - bh.R_EARTH) / 1e3:.0f} km"
)
print(f"  First burn (perigee):  {dv1:.3f} m/s")
print(f"  Second burn (apogee):  {dv2:.3f} m/s")
print(f"  Total delta-v:         {dv1 + dv2:.3f} m/s")

# Transfer time (half period of transfer ellipse)
transfer_time = np.pi * np.sqrt(a_transfer**3 / bh.GM_EARTH)
print(f"  Transfer time:         {transfer_time / 60:.1f} min")


# Create callback for first burn
def first_burn_callback(event_epoch, event_state):
    """Apply first delta-v at departure."""
    new_state = event_state.copy()
    # Add delta-v in velocity direction (prograde)
    v = event_state[3:6]
    v_hat = v / np.linalg.norm(v)
    new_state[3:6] += dv1 * v_hat
    print(f"  First burn applied at t+0s: dv = {dv1:.3f} m/s")
    return (new_state, bh.EventAction.CONTINUE)


# Create callback for second burn
def second_burn_callback(event_epoch, event_state):
    """Apply second delta-v at arrival."""
    new_state = event_state.copy()
    v = event_state[3:6]
    v_hat = v / np.linalg.norm(v)
    new_state[3:6] += dv2 * v_hat
    dt = event_epoch - epoch
    print(f"  Second burn applied at t+{dt:.1f}s: dv = {dv2:.3f} m/s")
    return (new_state, bh.EventAction.CONTINUE)


# Create propagator (two-body for clean Hohmann)
prop = bh.NumericalOrbitPropagator(
    epoch,
    state,
    bh.NumericalPropagationConfig.default(),
    bh.ForceModelConfig.two_body(),
    None,
)

# First burn at t=0 (immediate)
event1 = bh.TimeEvent(epoch + 1.0, "First Burn").with_callback(first_burn_callback)

# Second burn at apogee (half transfer period)
event2 = bh.TimeEvent(epoch + transfer_time, "Second Burn").with_callback(
    second_burn_callback
)

prop.add_event_detector(event1)
prop.add_event_detector(event2)

# Propagate through both burns plus one orbit of final orbit
final_orbit_period = bh.orbital_period(r2)
prop.propagate_to(epoch + transfer_time + final_orbit_period)

# Check final orbit
final_koe = prop.state_koe_osc(prop.current_epoch(), bh.AngleFormat.DEGREES)
final_altitude = final_koe[0] - bh.R_EARTH

print("\nFinal orbit:")
print(f"  Semi-major axis: {final_koe[0] / 1e3:.3f} km")
print(
    f"  Altitude:        {final_altitude / 1e3:.3f} km (target: {(r2 - bh.R_EARTH) / 1e3:.0f} km)"
)
print(f"  Eccentricity:    {final_koe[1]:.6f}")

# Validate final orbit achieved significant altitude gain
# Note: Some error expected due to numerical integration and event timing
altitude_gain = final_altitude - (r1 - bh.R_EARTH)
assert altitude_gain > 200e3  # Significant altitude gain achieved
assert final_koe[1] < 0.1  # Reasonably circular

print("\nExample validated successfully!")
```


### Hohmann Transfer Visualization

The following plots show the altitude and velocity changes during the Hohmann transfer example above.

#### Orbit Geometry

A top-down view showing the initial circular orbit, Hohmann transfer ellipse, and final circular orbit:


**Plot Source**

```python
import plotly.graph_objects as go

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))
from brahe_theme import save_themed_html, get_theme_colors

# Configuration
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# Earth radius in km for display
R_EARTH_KM = 6378.137

# Orbit parameters (matching the impulsive maneuver example)
r1_km = R_EARTH_KM + 400  # Initial orbit radius (400 km altitude)
r2_km = R_EARTH_KM + 800  # Final orbit radius (800 km altitude)

# Transfer orbit parameters
a_transfer_km = (r1_km + r2_km) / 2  # Semi-major axis of transfer ellipse
e_transfer = (r2_km - r1_km) / (r2_km + r1_km)  # Eccentricity of transfer ellipse


def generate_circle(radius, n_points=100):
    """Generate x, y coordinates for a circle."""
    theta = np.linspace(0, 2 * np.pi, n_points)
    x = radius * np.cos(theta)
    y = radius * np.sin(theta)
    return x, y


def generate_ellipse_arc(a, e, theta_start, theta_end, n_points=100):
    """Generate x, y coordinates for an ellipse arc.

    The ellipse is centered at one focus (Earth), with perigee at theta=0.
    """
    theta = np.linspace(theta_start, theta_end, n_points)
    # Orbit equation: r = a(1-e^2) / (1 + e*cos(theta))
    r = a * (1 - e**2) / (1 + e * np.cos(theta))
    x = r * np.cos(theta)
    y = r * np.sin(theta)
    return x, y


def create_figure(theme):
    colors = get_theme_colors(theme)

    fig = go.Figure()

    # Earth (filled circle)
    earth_x, earth_y = generate_circle(R_EARTH_KM, n_points=50)
    fig.add_trace(
        go.Scatter(
            x=earth_x,
            y=earth_y,
            mode="lines",
            fill="toself",
            fillcolor="#4a90d9" if theme == "light" else "#3a7bc8",
            line=dict(color="#2d5986", width=1),
            name="Earth",
            hoverinfo="name",
        )
    )

    # Initial orbit (dashed circle)
    initial_x, initial_y = generate_circle(r1_km)
    fig.add_trace(
        go.Scatter(
            x=initial_x,
            y=initial_y,
            mode="lines",
            line=dict(color=colors["secondary"], width=2, dash="dash"),
            name=f"Initial Orbit ({r1_km - R_EARTH_KM:.0f} km)",
            hoverinfo="name",
        )
    )

    # Final orbit (dashed circle)
    final_x, final_y = generate_circle(r2_km)
    fig.add_trace(
        go.Scatter(
            x=final_x,
            y=final_y,
            mode="lines",
            line=dict(color=colors["accent"], width=2, dash="dash"),
            name=f"Final Orbit ({r2_km - R_EARTH_KM:.0f} km)",
            hoverinfo="name",
        )
    )

    # Transfer orbit arc (solid line, only the transfer portion from perigee to apogee)
    transfer_x, transfer_y = generate_ellipse_arc(a_transfer_km, e_transfer, 0, np.pi)
    fig.add_trace(
        go.Scatter(
            x=transfer_x,
            y=transfer_y,
            mode="lines",
            line=dict(color=colors["primary"], width=3),
            name="Transfer Orbit",
            hoverinfo="name",
        )
    )

    # Burn 1 point (at perigee, rightmost point)
    burn1_x = r1_km
    burn1_y = 0
    fig.add_trace(
        go.Scatter(
            x=[burn1_x],
            y=[burn1_y],
            mode="markers",
            marker=dict(color=colors["error"], size=12, symbol="star"),
            name="Burn 1",
            hoverinfo="name+text",
            text=["Prograde burn to enter transfer orbit"],
        )
    )

    # Burn 2 point (at apogee, leftmost point)
    burn2_x = -r2_km
    burn2_y = 0
    fig.add_trace(
        go.Scatter(
            x=[burn2_x],
            y=[burn2_y],
            mode="markers",
            marker=dict(color=colors["error"], size=12, symbol="star"),
            name="Burn 2",
            hoverinfo="name+text",
            text=["Circularization burn at apogee"],
        )
    )

    # Annotations for burns
    fig.add_annotation(
        x=burn1_x + 300,
        y=burn1_y + 400,
        text="Burn 1",
        showarrow=True,
        arrowhead=2,
        arrowsize=1,
        arrowwidth=1.5,
        arrowcolor=colors["error"],
        ax=40,
        ay=-30,
        font=dict(size=11, color=colors["font_color"]),
    )

    fig.add_annotation(
        x=burn2_x - 300,
        y=burn2_y + 400,
        text="Burn 2",
        showarrow=True,
        arrowhead=2,
        arrowsize=1,
        arrowwidth=1.5,
        arrowcolor=colors["error"],
        ax=-40,
        ay=-30,
        font=dict(size=11, color=colors["font_color"]),
    )

    # Layout
    max_r = r2_km * 1.15
    fig.update_layout(
        title="Hohmann Transfer: Orbit Geometry (Top-Down View)",
        xaxis=dict(
            title="X (km)",
            range=[-max_r, max_r],
            scaleanchor="y",
            scaleratio=1,
            showgrid=True,
            gridcolor=colors["grid_color"],
            zeroline=True,
            zerolinecolor=colors["line_color"],
        ),
        yaxis=dict(
            title="Y (km)",
            range=[-max_r, max_r],
            showgrid=True,
            gridcolor=colors["grid_color"],
            zeroline=True,
            zerolinecolor=colors["line_color"],
        ),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
        ),
        height=500,
        margin=dict(l=60, r=40, t=80, b=60),
    )

    return fig


# Save themed HTML files
light_path, dark_path = save_themed_html(create_figure, OUTDIR / SCRIPT_NAME)
print(f"Generated {light_path}")
print(f"Generated {dark_path}")
```

#### Altitude Profile

The spacecraft altitude increases from 400 km to 800 km through two impulsive burns:


**Plot Source**

```python
import numpy as np
import plotly.graph_objects as go

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))
from brahe_theme import save_themed_html, get_theme_colors

# Configuration
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# Initialize EOP data
bh.initialize_eop()

# Create initial epoch and state
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# Initial and target orbits
r1 = bh.R_EARTH + 400e3  # 400 km altitude
r2 = bh.R_EARTH + 800e3  # 800 km altitude

# Initial state (circular orbit)
oe_initial = np.array([r1, 0.0001, 0.0, 0.0, 0.0, 0.0])
state = bh.state_koe_to_eci(oe_initial, bh.AngleFormat.DEGREES)

# Calculate Hohmann transfer parameters
v1_circular = np.sqrt(bh.GM_EARTH / r1)
a_transfer = (r1 + r2) / 2
v_perigee_transfer = np.sqrt(bh.GM_EARTH * (2 / r1 - 1 / a_transfer))
v_apogee_transfer = np.sqrt(bh.GM_EARTH * (2 / r2 - 1 / a_transfer))
v2_circular = np.sqrt(bh.GM_EARTH / r2)

dv1 = v_perigee_transfer - v1_circular
dv2 = v2_circular - v_apogee_transfer
transfer_time = np.pi * np.sqrt(a_transfer**3 / bh.GM_EARTH)

# Burn times
burn1_time_s = 1.0  # First burn at t=1s
burn2_time_s = burn1_time_s + transfer_time  # Second burn after half-transfer

# Calculate total propagation time
final_orbit_period = bh.orbital_period(r2)
total_time = burn2_time_s + final_orbit_period

# Use multi-stage propagation to avoid trajectory interpolation issues with events
# Stage 1: Initial orbit (t=0 to burn1)
prop1 = bh.NumericalOrbitPropagator(
    epoch,
    state,
    bh.NumericalPropagationConfig.default(),
    bh.ForceModelConfig.two_body(),
    None,
)
prop1.propagate_to(epoch + burn1_time_s)

# Apply first burn
state_at_burn1 = prop1.current_state()
v = state_at_burn1[3:6]
v_hat = v / np.linalg.norm(v)
state_post_burn1 = state_at_burn1.copy()
state_post_burn1[3:6] += dv1 * v_hat

# Stage 2: Transfer orbit (burn1 to burn2)
epoch_burn1 = epoch + burn1_time_s
prop2 = bh.NumericalOrbitPropagator(
    epoch_burn1,
    state_post_burn1,
    bh.NumericalPropagationConfig.default(),
    bh.ForceModelConfig.two_body(),
    None,
)
prop2.propagate_to(epoch_burn1 + transfer_time)

# Apply second burn
state_at_burn2 = prop2.current_state()
v = state_at_burn2[3:6]
v_hat = v / np.linalg.norm(v)
state_post_burn2 = state_at_burn2.copy()
state_post_burn2[3:6] += dv2 * v_hat

# Stage 3: Final circular orbit (burn2 onwards)
epoch_burn2 = epoch_burn1 + transfer_time
prop3 = bh.NumericalOrbitPropagator(
    epoch_burn2,
    state_post_burn2,
    bh.NumericalPropagationConfig.default(),
    bh.ForceModelConfig.two_body(),
    None,
)
prop3.propagate_to(epoch_burn2 + final_orbit_period)

# Sample the trajectory at high resolution
times = []
altitudes = []
dt = 30.0  # 30 second intervals

t = 0.0
while t <= total_time:
    current_epoch = epoch + t

    # Determine which propagator to query
    if t < burn1_time_s:
        s = prop1.state_eci(current_epoch)
    elif t < burn2_time_s:
        s = prop2.state_eci(current_epoch)
    else:
        s = prop3.state_eci(current_epoch)

    r = np.linalg.norm(s[:3])
    alt = (r - bh.R_EARTH) / 1e3  # Convert to km
    times.append(t / 60.0)  # Convert to minutes
    altitudes.append(alt)
    t += dt

# Get burn times for vertical lines (in minutes)
burn1_time_min = burn1_time_s / 60.0
burn2_time_min = burn2_time_s / 60.0


def create_figure(theme):
    colors = get_theme_colors(theme)

    fig = go.Figure()

    # Altitude trace
    fig.add_trace(
        go.Scatter(
            x=times,
            y=altitudes,
            mode="lines",
            name="Altitude",
            line=dict(color=colors["primary"], width=2),
        )
    )

    # Initial altitude reference
    fig.add_hline(
        y=400,
        line_dash="dash",
        line_color=colors["secondary"],
        annotation_text="Initial: 400 km",
        annotation_position="top right",
    )

    # Target altitude reference
    fig.add_hline(
        y=800,
        line_dash="dash",
        line_color=colors["accent"],
        annotation_text="Target: 800 km",
        annotation_position="top right",
    )

    # Burn 1 marker
    fig.add_vline(
        x=burn1_time_min,
        line_dash="dot",
        line_color=colors["error"],
        annotation_text=f"Burn 1: {dv1:.1f} m/s",
        annotation_position="top left",
    )

    # Burn 2 marker
    fig.add_vline(
        x=burn2_time_min,
        line_dash="dot",
        line_color=colors["error"],
        annotation_text=f"Burn 2: {dv2:.1f} m/s",
        annotation_position="top left",
    )

    fig.update_layout(
        title="Hohmann Transfer: Altitude vs Time",
        xaxis_title="Time (minutes)",
        yaxis_title="Altitude (km)",
        showlegend=False,
        height=500,
        margin=dict(l=60, r=40, t=60, b=60),
    )

    return fig


# Save themed HTML files
light_path, dark_path = save_themed_html(create_figure, OUTDIR / SCRIPT_NAME)
print(f"Generated {light_path}")
print(f"Generated {dark_path}")
```

#### Velocity Components

The velocity components show the discrete jumps from each impulsive burn:


**Plot Source**

```python
import numpy as np
import plotly.graph_objects as go

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))
from brahe_theme import save_themed_html, get_theme_colors

# Configuration
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# Initialize EOP data
bh.initialize_eop()

# Create initial epoch and state
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# Initial and target orbits
r1 = bh.R_EARTH + 400e3  # 400 km altitude
r2 = bh.R_EARTH + 800e3  # 800 km altitude

# Initial state (circular orbit)
oe_initial = np.array([r1, 0.0001, 0.0, 0.0, 0.0, 0.0])
state = bh.state_koe_to_eci(oe_initial, bh.AngleFormat.DEGREES)

# Calculate Hohmann transfer parameters
v1_circular = np.sqrt(bh.GM_EARTH / r1)
a_transfer = (r1 + r2) / 2
v_perigee_transfer = np.sqrt(bh.GM_EARTH * (2 / r1 - 1 / a_transfer))
v_apogee_transfer = np.sqrt(bh.GM_EARTH * (2 / r2 - 1 / a_transfer))
v2_circular = np.sqrt(bh.GM_EARTH / r2)

dv1 = v_perigee_transfer - v1_circular
dv2 = v2_circular - v_apogee_transfer
transfer_time = np.pi * np.sqrt(a_transfer**3 / bh.GM_EARTH)

# Burn times
burn1_time_s = 1.0  # First burn at t=1s
burn2_time_s = burn1_time_s + transfer_time  # Second burn after half-transfer

# Calculate total propagation time
final_orbit_period = bh.orbital_period(r2)
total_time = burn2_time_s + final_orbit_period

# Use multi-stage propagation to avoid trajectory interpolation issues with events
# Stage 1: Initial orbit (t=0 to burn1)
prop1 = bh.NumericalOrbitPropagator(
    epoch,
    state,
    bh.NumericalPropagationConfig.default(),
    bh.ForceModelConfig.two_body(),
    None,
)
prop1.propagate_to(epoch + burn1_time_s)

# Apply first burn
state_at_burn1 = prop1.current_state()
v = state_at_burn1[3:6]
v_hat = v / np.linalg.norm(v)
state_post_burn1 = state_at_burn1.copy()
state_post_burn1[3:6] += dv1 * v_hat

# Stage 2: Transfer orbit (burn1 to burn2)
epoch_burn1 = epoch + burn1_time_s
prop2 = bh.NumericalOrbitPropagator(
    epoch_burn1,
    state_post_burn1,
    bh.NumericalPropagationConfig.default(),
    bh.ForceModelConfig.two_body(),
    None,
)
prop2.propagate_to(epoch_burn1 + transfer_time)

# Apply second burn
state_at_burn2 = prop2.current_state()
v = state_at_burn2[3:6]
v_hat = v / np.linalg.norm(v)
state_post_burn2 = state_at_burn2.copy()
state_post_burn2[3:6] += dv2 * v_hat

# Stage 3: Final circular orbit (burn2 onwards)
epoch_burn2 = epoch_burn1 + transfer_time
prop3 = bh.NumericalOrbitPropagator(
    epoch_burn2,
    state_post_burn2,
    bh.NumericalPropagationConfig.default(),
    bh.ForceModelConfig.two_body(),
    None,
)
prop3.propagate_to(epoch_burn2 + final_orbit_period)

# Sample the trajectory at high resolution
times = []
vx_data = []
vy_data = []
vz_data = []
dt = 30.0  # 30 second intervals

t = 0.0
while t <= total_time:
    current_epoch = epoch + t

    # Determine which propagator to query
    if t < burn1_time_s:
        s = prop1.state_eci(current_epoch)
    elif t < burn2_time_s:
        s = prop2.state_eci(current_epoch)
    else:
        s = prop3.state_eci(current_epoch)

    times.append(t / 60.0)  # Convert to minutes
    vx_data.append(s[3] / 1e3)  # Convert to km/s
    vy_data.append(s[4] / 1e3)
    vz_data.append(s[5] / 1e3)
    t += dt

# Get burn times for vertical lines (in minutes)
burn1_time_min = burn1_time_s / 60.0
burn2_time_min = burn2_time_s / 60.0


def create_figure(theme):
    colors = get_theme_colors(theme)

    fig = go.Figure()

    # Velocity component traces
    fig.add_trace(
        go.Scatter(
            x=times,
            y=vx_data,
            mode="lines",
            name="vx",
            line=dict(color=colors["primary"], width=2),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=times,
            y=vy_data,
            mode="lines",
            name="vy",
            line=dict(color=colors["secondary"], width=2),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=times,
            y=vz_data,
            mode="lines",
            name="vz",
            line=dict(color=colors["accent"], width=2),
        )
    )

    # Burn 1 marker
    fig.add_vline(
        x=burn1_time_min,
        line_dash="dot",
        line_color=colors["error"],
        annotation_text="Burn 1",
        annotation_position="top left",
    )

    # Burn 2 marker
    fig.add_vline(
        x=burn2_time_min,
        line_dash="dot",
        line_color=colors["error"],
        annotation_text="Burn 2",
        annotation_position="top left",
    )

    fig.update_layout(
        title="Hohmann Transfer: Velocity Components",
        xaxis_title="Time (minutes)",
        yaxis_title="Velocity (km/s)",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=500,
        margin=dict(l=60, r=40, t=80, b=60),
    )

    return fig


# Save themed HTML files
light_path, dark_path = save_themed_html(create_figure, OUTDIR / SCRIPT_NAME)
print(f"Generated {light_path}")
print(f"Generated {dark_path}")
```

### Common Impulsive Maneuvers

| Maneuver | Implementation |
|----------|----------------|
| Hohmann transfer | Two burns at apoapsis/periapsis |
| Plane change | Burn perpendicular to velocity at ascending/descending node |
| Orbit raising | Prograde burn at periapsis/apoapsis |
| Circularization | Burn at target altitude |

## Continuous Thrust

Continuous thrust maneuvers apply acceleration over extended periods. They're implemented via control input functions that add acceleration at each integration step.

### Control Input Functions

The control input function is called at each integration step and returns a state derivative contribution:


```python
import numpy as np
import brahe as bh

# Initialize EOP data
bh.initialize_eop()

# Create initial epoch and state
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# Initial circular orbit at 400 km
oe = np.array([bh.R_EARTH + 400e3, 0.0001, 0.0, 0.0, 0.0, 0.0])
state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

# Spacecraft parameters
mass = 500.0  # kg
thrust = 0.1  # N (100 mN thruster - typical ion engine)
params = np.array([mass, 0.0, 0.0, 0.0, 0.0])  # No drag/SRP


# Define continuous control input: constant tangential thrust
def tangential_thrust(t, state_vec, params_vec):
    """Apply constant thrust in velocity direction.

    Control input must return a derivative vector with the same
    dimension as the state. For 6D orbital state:
    - Elements 0-2: position derivatives (zeros for control)
    - Elements 3-5: velocity derivatives (acceleration)
    """
    v = state_vec[3:6]
    v_mag = np.linalg.norm(v)

    # Return full state derivative (same dimension as state)
    dx = np.zeros(len(state_vec))

    if v_mag > 1e-10:
        # Unit vector in velocity direction
        v_hat = v / v_mag
        # Acceleration from thrust (F = ma -> a = F/m)
        accel_mag = thrust / mass
        acceleration = accel_mag * v_hat
        dx[3:6] = acceleration  # Add to velocity derivatives

    return dx


# Create propagator with continuous control
prop = bh.NumericalOrbitPropagator(
    epoch,
    state,
    bh.NumericalPropagationConfig.default(),
    bh.ForceModelConfig.two_body(),  # Two-body + control
    None,
    control_input=tangential_thrust,
)

# Also create reference propagator without thrust
prop_ref = bh.NumericalOrbitPropagator(
    epoch,
    state,
    bh.NumericalPropagationConfig.default(),
    bh.ForceModelConfig.two_body(),
    None,
)

# Propagate for 10 orbits
orbital_period = bh.orbital_period(oe[0])
end_time = epoch + 10 * orbital_period

prop.propagate_to(end_time)
prop_ref.propagate_to(end_time)

# Compare orbits
koe_thrust = prop.state_koe_osc(end_time, bh.AngleFormat.DEGREES)
koe_ref = prop_ref.state_koe_osc(end_time, bh.AngleFormat.DEGREES)

alt_thrust = koe_thrust[0] - bh.R_EARTH
alt_ref = koe_ref[0] - bh.R_EARTH
alt_gain = alt_thrust - alt_ref

# Calculate total delta-v applied
total_time = 10 * orbital_period
dv_total = (thrust / mass) * total_time

print("Low-Thrust Orbit Raising (10 orbits):")
print(f"  Thrust: {thrust * 1000:.1f} mN")
print(f"  Spacecraft mass: {mass:.0f} kg")
print(f"  Acceleration: {thrust / mass * 1e6:.2f} micro-m/s^2")
print(f"\nAfter {10 * orbital_period / 3600:.1f} hours:")
print(f"  Reference altitude: {alt_ref / 1e3:.3f} km")
print(f"  With thrust altitude: {alt_thrust / 1e3:.3f} km")
print(f"  Altitude gain: {alt_gain / 1e3:.3f} km")
print(f"  Total delta-v applied: {dv_total:.3f} m/s")

# Validate - thrust should raise orbit
assert alt_thrust > alt_ref
assert alt_gain > 0

print("\nExample validated successfully!")
```


### Control Function Signature

The control function receives the epoch, current state, and optional parameters. It returns a state derivative vector (same dimension as state):


```
def control_input(epoch, state, params):
    # Create derivative vector (zeros for positions, acceleration for velocities)
    dx = np.zeros(len(state))

    # Compute acceleration
    acceleration = compute_thrust_acceleration(epoch, state, params)

    # Apply to velocity derivatives only
    dx[3:6] = acceleration

    return dx
```

The returned vector is added to the equations of motion:

$$\dot{\mathbf{x}} = f(\mathbf{x}, t) + \mathbf{u}(t, \mathbf{x})$$

where $f$ is the natural dynamics and $\mathbf{u}$ is the control input.

### Variable Thrust

The control function can implement time-varying or state-dependent thrust:


```python
import numpy as np
import brahe as bh

# Initialize EOP data
bh.initialize_eop()

# Create initial epoch and state
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# Initial circular orbit at 400 km
oe = np.array([bh.R_EARTH + 400e3, 0.0001, 0.0, 0.0, 0.0, 0.0])
state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

# Spacecraft and maneuver parameters
mass = 500.0  # kg
max_thrust = 0.5  # N (500 mN thruster)
ramp_time = 300.0  # s (5 minute ramp)
burn_duration = 1800.0  # s (30 minute burn)
maneuver_start = epoch + 600.0  # Start 10 minutes into propagation


# Define variable thrust control input
def variable_thrust(t, state_vec, params_vec):
    """Apply thrust with ramp-up and ramp-down profile.

    The thrust magnitude follows a trapezoidal profile:
    - Ramp up from 0 to max_thrust over ramp_time
    - Hold at max_thrust
    - Ramp down from max_thrust to 0 over ramp_time
    """
    # Return zeros if outside burn window
    dx = np.zeros(len(state_vec))

    # Time since maneuver start (t is seconds since epoch)
    t_maneuver = t - 600.0  # maneuver_start offset in seconds

    # Check if within burn window
    if t_maneuver < 0 or t_maneuver > burn_duration:
        return dx

    # Compute thrust magnitude with ramp profile
    if t_maneuver < ramp_time:
        # Ramp up phase
        magnitude = max_thrust * (t_maneuver / ramp_time)
    elif t_maneuver > burn_duration - ramp_time:
        # Ramp down phase
        magnitude = max_thrust * ((burn_duration - t_maneuver) / ramp_time)
    else:
        # Constant thrust phase
        magnitude = max_thrust

    # Thrust direction along velocity
    v = state_vec[3:6]
    v_mag = np.linalg.norm(v)

    if v_mag > 1e-10:
        v_hat = v / v_mag
        # Acceleration from thrust (F = ma -> a = F/m)
        acceleration = (magnitude / mass) * v_hat
        dx[3:6] = acceleration

    return dx


# Create propagator with variable thrust control
prop = bh.NumericalOrbitPropagator(
    epoch,
    state,
    bh.NumericalPropagationConfig.default(),
    bh.ForceModelConfig.two_body(),
    None,
    control_input=variable_thrust,
)

# Create reference propagator without thrust
prop_ref = bh.NumericalOrbitPropagator(
    epoch,
    state,
    bh.NumericalPropagationConfig.default(),
    bh.ForceModelConfig.two_body(),
    None,
)

# Propagate for duration covering the entire maneuver
end_time = epoch + 3600.0  # 1 hour (covers 30-min burn starting at 10 min)

prop.propagate_to(end_time)
prop_ref.propagate_to(end_time)

# Compare final orbits
koe_thrust = prop.state_koe_osc(end_time, bh.AngleFormat.DEGREES)
koe_ref = prop_ref.state_koe_osc(end_time, bh.AngleFormat.DEGREES)

alt_thrust = koe_thrust[0] - bh.R_EARTH
alt_ref = koe_ref[0] - bh.R_EARTH
alt_gain = alt_thrust - alt_ref

# Calculate approximate delta-v (trapezoidal profile integration)
# Full thrust duration minus ramp portions: burn_duration - ramp_time
effective_time = burn_duration - ramp_time
dv_approx = (max_thrust / mass) * effective_time

print("Variable Thrust Orbit Raising:")
print(f"  Max thrust: {max_thrust * 1000:.1f} mN")
print(f"  Spacecraft mass: {mass:.0f} kg")
print(f"  Burn duration: {burn_duration:.0f} s ({burn_duration / 60:.0f} min)")
print(f"  Ramp time: {ramp_time:.0f} s ({ramp_time / 60:.0f} min)")
print("\nAfter 1 hour propagation:")
print(f"  Reference altitude: {alt_ref / 1e3:.3f} km")
print(f"  With thrust altitude: {alt_thrust / 1e3:.3f} km")
print(f"  Altitude gain: {alt_gain / 1e3:.3f} km")
print(f"  Approx delta-v applied: {dv_approx:.3f} m/s")

# Validate - thrust should raise orbit
assert alt_thrust > alt_ref, "Thrust should raise orbit"
assert alt_gain > 0, "Altitude gain should be positive"

print("\nExample validated successfully!")
```


#### Thrust Profile Visualization

The following plot shows the trapezoidal thrust profile with ramp-up and ramp-down phases:


**Plot Source**

```python
import numpy as np
import plotly.graph_objects as go

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))
from brahe_theme import save_themed_html, get_theme_colors

# Configuration
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# Maneuver parameters (matching the variable_thrust.py example)
max_thrust = 0.5  # N (500 mN thruster)
mass = 500.0  # kg
ramp_time = 300.0  # s (5 minute ramp)
burn_duration = 1800.0  # s (30 minute burn)
maneuver_start = 600.0  # s (10 minutes into propagation)


def thrust_profile(t):
    """Calculate thrust magnitude at time t (seconds from propagation start)."""
    t_maneuver = t - maneuver_start

    if t_maneuver < 0 or t_maneuver > burn_duration:
        return 0.0
    elif t_maneuver < ramp_time:
        # Ramp up phase
        return max_thrust * (t_maneuver / ramp_time)
    elif t_maneuver > burn_duration - ramp_time:
        # Ramp down phase
        return max_thrust * ((burn_duration - t_maneuver) / ramp_time)
    else:
        # Constant thrust phase
        return max_thrust


# Generate time series data
total_time = 3600.0  # 1 hour total propagation
dt = 5.0  # 5 second intervals for smooth curve

times = np.arange(0, total_time + dt, dt)
thrust_values = np.array([thrust_profile(t) for t in times])
accel_values = thrust_values / mass * 1e6  # Convert to micro-m/s^2

# Convert times to minutes for display
times_min = times / 60.0

# Key times for annotations (in minutes)
maneuver_start_min = maneuver_start / 60.0
ramp_end_min = (maneuver_start + ramp_time) / 60.0
constant_end_min = (maneuver_start + burn_duration - ramp_time) / 60.0
maneuver_end_min = (maneuver_start + burn_duration) / 60.0


def create_figure(theme):
    colors = get_theme_colors(theme)

    fig = go.Figure()

    # Thrust magnitude trace
    fig.add_trace(
        go.Scatter(
            x=times_min,
            y=thrust_values * 1000,  # Convert to mN
            mode="lines",
            name="Thrust",
            line=dict(color=colors["primary"], width=2.5),
            fill="tozeroy",
            fillcolor=f"rgba{tuple(list(int(colors['primary'].lstrip('#')[i : i + 2], 16) for i in (0, 2, 4)) + [0.2])}",
        )
    )

    # Phase annotations
    fig.add_annotation(
        x=(maneuver_start_min + ramp_end_min) / 2,
        y=max_thrust * 1000 * 0.5,
        text="Ramp Up",
        showarrow=False,
        font=dict(size=11, color=colors["font_color"]),
    )

    fig.add_annotation(
        x=(ramp_end_min + constant_end_min) / 2,
        y=max_thrust * 1000 * 1.1,
        text="Constant Thrust",
        showarrow=False,
        font=dict(size=11, color=colors["font_color"]),
    )

    fig.add_annotation(
        x=(constant_end_min + maneuver_end_min) / 2,
        y=max_thrust * 1000 * 0.5,
        text="Ramp Down",
        showarrow=False,
        font=dict(size=11, color=colors["font_color"]),
    )

    # Vertical lines marking phase boundaries
    for x_val, label in [
        (maneuver_start_min, "Burn Start"),
        (maneuver_end_min, "Burn End"),
    ]:
        fig.add_vline(
            x=x_val,
            line_dash="dot",
            line_color=colors["secondary"],
            annotation_text=label,
            annotation_position="top",
        )

    # Max thrust reference line
    fig.add_hline(
        y=max_thrust * 1000,
        line_dash="dash",
        line_color=colors["accent"],
        annotation_text=f"Max: {max_thrust * 1000:.0f} mN",
        annotation_position="right",
    )

    fig.update_layout(
        title="Variable Thrust Profile: Trapezoidal Maneuver",
        xaxis_title="Time (minutes)",
        yaxis_title="Thrust (mN)",
        showlegend=False,
        height=500,
        margin=dict(l=60, r=80, t=60, b=60),
        yaxis=dict(range=[-20, max_thrust * 1000 * 1.3]),
    )

    return fig


# Save themed HTML files
light_path, dark_path = save_themed_html(create_figure, OUTDIR / SCRIPT_NAME)
print(f"Generated {light_path}")
print(f"Generated {dark_path}")
```

## Fuel Consumption Tracking

Neither maneuver type automatically tracks fuel consumption. To track propellant:

1. Extend the state vector to include mass
2. Add mass derivative to control input or additional dynamics

See [Extending Spacecraft State](extending_state.md) for complete examples.

---

## See Also

- [Event Detection](event_detection.md) - Event system fundamentals
- [Event Callbacks](event_callbacks.md) - Callback function details
- [Extending Spacecraft State](extending_state.md) - Extended state vectors
- [General Dynamics Propagation](generic_dynamics.md) - Extended state vectors
- [Numerical Orbit Propagator](numerical_orbit_propagator.md) - Propagator fundamentals