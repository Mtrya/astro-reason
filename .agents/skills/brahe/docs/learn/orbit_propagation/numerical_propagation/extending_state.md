# Extending Spacecraft State

The `NumericalOrbitPropagator` supports extending state vectors beyond the standard 6-element orbital state, enabling modeling of additional state variables and dynamics like propellant mass, battery charge, or attiude alongside orbital dynamics. This is achieved through the `additional_dynamics` function.

## State Extension Approach

To extend the state vector with `NumericalOrbitPropagator`:

1. Define an extended state vector (e.g., 7 elements: `[pos, vel, mass]`)
2. Implement an `additional_dynamics` function that returns a full state-sized derivative vector, where the first 6 elements are zeros (orbital dynamics handled by the force model) and the remaining elements contain derivatives for the extended state
3. Optionally provide a `control_input` function for thrust accelerations
4. Create the propagator with these functions

The key advantage of using `NumericalOrbitPropagator` is that orbital dynamics (gravity, drag, SRP, etc.) are handled automatically by the force model configuration, while your `additional_dynamics` function adds derivatives for the extended state elements.

To showcase how to extend the spacecraft state, we present an example of tracking propellant mass during a thrust maneuver below.

## Mass Tracking Example

One common extension is tracking propellant mass during the mission. To model propelant mass we augment the state vector from 6 to 7 elements, by adding mass $m$ as the 7th element:

$$\mathbf{x} = [x, y, z, v_x, v_y, v_z, m]^T$$

### Mass Flow Dynamics

We model mass flow rate during thrust as:

$$\dot{m} = -\frac{F}{I_{sp} \cdot g_0}$$

where:

- $F$ is thrust force (N)
- $I_{sp}$ is specific impulse (s)
- $g_0$ is standard gravity (9.80665 m/s²)

### Implementation with NumericalOrbitPropagator

Both `additional_dynamics` and `control_input` functions return full state-sized vectors. The propagator adds these to the orbital dynamics computed from the force model.

The `additional_dynamics` function returns a state-sized vector with derivatives for extended elements:


```
def additional_dynamics(t, state, params):
    """Return full state-sized vector with mass rate."""
    dx = np.zeros(len(state))  # Full state size
    if burn_start <= t < burn_end:
        dx[6] = -mass_flow_rate  # dm/dt = -F/(Isp*g0)
    return dx
```

The `control_input` function returns a state-sized vector with acceleration in indices 3-5:


```
def control_input(t, state, params):
    """Return full state-sized vector with thrust acceleration."""
    dx = np.zeros(len(state))
    if burn_start <= t < burn_end:
        mass = state[6]  # Access mass from extended state
        vel = state[3:6]
        v_hat = vel / np.linalg.norm(vel)  # Prograde direction
        acc = (thrust_force / mass) * v_hat
        dx[3:6] = acc  # Add to velocity derivatives
    return dx
```

### Complete Example


```python
import numpy as np
import brahe as bh

# Initialize EOP data
bh.initialize_eop()

# Create initial epoch
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# Initial orbital elements and state
oe = np.array([bh.R_EARTH + 500e3, 0.01, 45.0, 15.0, 30.0, 45.0])
orbital_state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

# Extended state: [x, y, z, vx, vy, vz, mass]
initial_mass = 1000.0  # kg
initial_state = np.concatenate([orbital_state, [initial_mass]])

# Thruster parameters
thrust_force = 10.0  # N
specific_impulse = 300.0  # s
g0 = 9.80665  # m/s^2
mass_flow_rate = thrust_force / (specific_impulse * g0)  # kg/s

# Timing parameters
pre_burn_coast = 300.0  # 5 minutes coast before burn
burn_duration = 600.0  # 10 minutes burn
post_burn_coast = 600.0  # 10 minutes coast after burn
burn_start = pre_burn_coast
burn_end = pre_burn_coast + burn_duration
total_time = pre_burn_coast + burn_duration + post_burn_coast

# Spacecraft parameters for force model [mass, drag_area, Cd, srp_area, Cr]
params = np.array([initial_mass, 2.0, 2.2, 2.0, 1.3])

print("Thruster parameters:")
print(f"  Thrust: {thrust_force} N")
print(f"  Isp: {specific_impulse} s")
print(f"  Mass flow rate: {mass_flow_rate * 1000:.2f} g/s")
print(f"  Burn duration: {burn_duration} s")
print(f"  Burn window: {burn_start} - {burn_end} s")
print(f"  Expected fuel consumption: {mass_flow_rate * burn_duration:.2f} kg")


# Define additional dynamics for mass tracking
def additional_dynamics(t, state, params):
    """
    Return full state derivative vector with contributions for extended state.
    State: [x, y, z, vx, vy, vz, mass] - return same-sized vector.
    Elements 0-5 should be zero (orbital dynamics handled by force model).
    """
    dx = np.zeros(len(state))
    if burn_start <= t < burn_end:
        dx[6] = -mass_flow_rate  # dm/dt = -F/(Isp*g0)
    return dx


# Define control input for thrust acceleration
def control_input(t, state, params):
    """
    Return full state derivative with acceleration contributions.
    Returns state-sized vector with acceleration in indices 3-5.
    """
    dx = np.zeros(len(state))
    if burn_start <= t < burn_end:
        mass = state[6]  # Access mass from extended state
        vel = state[3:6]
        v_hat = vel / np.linalg.norm(vel)  # Prograde direction
        acc = (thrust_force / mass) * v_hat  # Thrust acceleration
        dx[3:6] = acc  # Add to velocity derivatives
    return dx


# Create propagator with two-body dynamics (no drag/SRP for clean mass tracking)
force_config = bh.ForceModelConfig.two_body()
prop_config = bh.NumericalPropagationConfig.default()

prop = bh.NumericalOrbitPropagator(
    epoch,
    initial_state,
    prop_config,
    force_config,
    params=params,
    additional_dynamics=additional_dynamics,
    control_input=control_input,
)

print("\nInitial state:")
print(f"  Mass: {initial_mass:.1f} kg")
print(f"  Semi-major axis: {oe[0] / 1e3:.1f} km")

# Propagate through pre-burn coast, burn, and post-burn coast
prop.propagate_to(epoch + total_time)

# Check final state
final_state = prop.current_state()
final_mass = final_state[6]
fuel_consumed = initial_mass - final_mass

# Compute final orbital elements
final_orbital_state = final_state[:6]
final_koe = bh.state_eci_to_koe(final_orbital_state, bh.AngleFormat.DEGREES)

print("\nFinal state:")
print(f"  Mass: {final_mass:.1f} kg")
print(f"  Fuel consumed: {fuel_consumed:.2f} kg")
print(f"  Semi-major axis: {final_koe[0] / 1e3:.1f} km")
print(f"  Delta-a: {(final_koe[0] - oe[0]) / 1e3:.1f} km")

# Verify Tsiolkovsky equation
delta_v_expected = specific_impulse * g0 * np.log(initial_mass / final_mass)
print("\nTsiolkovsky verification:")
print(f"  Expected delta-v: {delta_v_expected:.1f} m/s")

# Validate
expected_fuel = mass_flow_rate * burn_duration
assert abs(fuel_consumed - expected_fuel) < 0.1  # Within 0.1 kg
assert final_mass < initial_mass
assert final_koe[0] > oe[0]  # Orbit raised

print("\nExample validated successfully!")
```


### Orbital Elements Evolution

The following plot shows how orbital elements evolve during the thrust maneuver:


**Plot Source**

```python
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

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
oe = np.array([bh.R_EARTH + 500e3, 0.01, 45.0, 15.0, 30.0, 45.0])
orbital_state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

# Extended state: [x, y, z, vx, vy, vz, mass]
initial_mass = 1000.0  # kg
initial_state = np.concatenate([orbital_state, [initial_mass]])

# Thruster parameters
thrust_force = 10.0  # N
specific_impulse = 300.0  # s
g0 = 9.80665  # m/s^2
mass_flow_rate = thrust_force / (specific_impulse * g0)  # kg/s

# Timing parameters
pre_burn_coast = 300.0  # 5 minutes coast before burn
burn_duration = 600.0  # 10 minutes burn
post_burn_coast = 600.0  # 10 minutes coast after burn
burn_start = pre_burn_coast
burn_end = pre_burn_coast + burn_duration
total_time = pre_burn_coast + burn_duration + post_burn_coast

# Spacecraft parameters for force model
params = np.array([initial_mass, 2.0, 2.2, 2.0, 1.3])


# Define additional dynamics for mass tracking
def additional_dynamics(t, state, params):
    dx = np.zeros(len(state))
    if burn_start <= t < burn_end:
        dx[6] = -mass_flow_rate
    return dx


# Define control input for thrust acceleration
def control_input(t, state, params):
    dx = np.zeros(len(state))
    if burn_start <= t < burn_end:
        mass = state[6]
        vel = state[3:6]
        v_hat = vel / np.linalg.norm(vel)
        acc = (thrust_force / mass) * v_hat
        dx[3:6] = acc
    return dx


# Create propagator with two-body dynamics
force_config = bh.ForceModelConfig.two_body()
prop_config = bh.NumericalPropagationConfig.default()

prop = bh.NumericalOrbitPropagator(
    epoch,
    initial_state,
    prop_config,
    force_config,
    params=params,
    additional_dynamics=additional_dynamics,
    control_input=control_input,
)

# Propagate and collect orbital elements over time
prop.propagate_to(epoch + total_time)

# Sample trajectory using trajectory interpolation
traj = prop.trajectory
times = []
a_vals = []  # Semi-major axis (km)
e_vals = []  # Eccentricity
i_vals = []  # Inclination (deg)
raan_vals = []  # RAAN (deg)
argp_vals = []  # Argument of periapsis (deg)
ma_vals = []  # Mean anomaly (deg)

dt = 10.0  # 10 second samples
t = 0.0
while t <= total_time:
    current_epoch = epoch + t
    try:
        state = traj.interpolate(current_epoch)
        # Convert to orbital elements
        orbital_state_6d = state[:6]
        koe = bh.state_eci_to_koe(orbital_state_6d, bh.AngleFormat.DEGREES)

        times.append(t / 60.0)  # Convert to minutes
        a_vals.append((koe[0] - bh.R_EARTH) / 1e3)  # Altitude in km
        e_vals.append(koe[1])
        i_vals.append(koe[2])
        raan_vals.append(koe[3])
        argp_vals.append(koe[4])
        ma_vals.append(koe[5])  # Mean anomaly (koe[5] is mean anomaly)
    except RuntimeError:
        pass  # Skip if interpolation fails

    t += dt


def create_figure(theme):
    colors = get_theme_colors(theme)

    # Create 2x3 subplots
    fig = make_subplots(
        rows=2,
        cols=3,
        subplot_titles=(
            "Semi-major Axis (Altitude)",
            "Eccentricity",
            "Inclination",
            "RAAN",
            "Arg. Periapsis",
            "Mean Anomaly",
        ),
        vertical_spacing=0.15,
        horizontal_spacing=0.08,
    )

    # Semi-major axis (altitude)
    fig.add_trace(
        go.Scatter(
            x=times, y=a_vals, mode="lines", line=dict(color=colors["primary"], width=2)
        ),
        row=1,
        col=1,
    )
    fig.update_yaxes(title_text="Altitude (km)", row=1, col=1)

    # Eccentricity
    fig.add_trace(
        go.Scatter(
            x=times,
            y=e_vals,
            mode="lines",
            line=dict(color=colors["secondary"], width=2),
        ),
        row=1,
        col=2,
    )
    fig.update_yaxes(title_text="e", range=[0, 0.1], row=1, col=2)

    # Inclination
    fig.add_trace(
        go.Scatter(
            x=times, y=i_vals, mode="lines", line=dict(color=colors["accent"], width=2)
        ),
        row=1,
        col=3,
    )
    fig.update_yaxes(title_text="i (deg)", range=[0, 90], row=1, col=3)

    # RAAN
    fig.add_trace(
        go.Scatter(
            x=times,
            y=raan_vals,
            mode="lines",
            line=dict(color=colors["primary"], width=2),
        ),
        row=2,
        col=1,
    )
    fig.update_yaxes(title_text="RAAN (deg)", range=[0, 360], row=2, col=1)

    # Argument of periapsis
    fig.add_trace(
        go.Scatter(
            x=times,
            y=argp_vals,
            mode="lines",
            line=dict(color=colors["secondary"], width=2),
        ),
        row=2,
        col=2,
    )
    fig.update_yaxes(title_text="\u03c9 (deg)", range=[0, 360], row=2, col=2)

    # Mean anomaly
    fig.add_trace(
        go.Scatter(
            x=times,
            y=ma_vals,
            mode="lines",
            line=dict(color=colors["accent"], width=2),
        ),
        row=2,
        col=3,
    )
    fig.update_yaxes(title_text="M (deg)", range=[0, 360], row=2, col=3)

    # Add burn start and end indicators to all subplots
    burn_start_min = burn_start / 60.0
    burn_end_min = burn_end / 60.0
    for row in [1, 2]:
        for col in [1, 2, 3]:
            # Burn start indicator
            fig.add_vline(
                x=burn_start_min,
                line_dash="dot",
                line_color=colors["accent"],
                line_width=1,
                row=row,
                col=col,
            )
            # Burn end indicator
            fig.add_vline(
                x=burn_end_min,
                line_dash="dot",
                line_color=colors["error"],
                line_width=1,
                row=row,
                col=col,
            )

    # Update x-axis labels for bottom row
    for col in [1, 2, 3]:
        fig.update_xaxes(title_text="Time (min)", row=2, col=col)

    fig.update_layout(
        title="Orbital Elements During Prograde Thrust (10 N, 10 min burn)",
        showlegend=False,
        height=500,
        margin=dict(l=60, r=40, t=80, b=60),
    )

    return fig


# Save themed HTML files
light_path, dark_path = save_themed_html(create_figure, OUTDIR / SCRIPT_NAME)
print(f"Generated {light_path}")
print(f"Generated {dark_path}")
```

### Mass Depletion Profile

The mass decreases linearly during the thrust phase:


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
oe = np.array([bh.R_EARTH + 500e3, 0.01, 45.0, 15.0, 30.0, 45.0])
orbital_state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

# Extended state: [x, y, z, vx, vy, vz, mass]
initial_mass = 1000.0  # kg
initial_state = np.concatenate([orbital_state, [initial_mass]])

# Thruster parameters
thrust_force = 10.0  # N
specific_impulse = 300.0  # s
g0 = 9.80665  # m/s^2
mass_flow_rate = thrust_force / (specific_impulse * g0)  # kg/s

# Timing parameters
pre_burn_coast = 300.0  # 5 minutes coast before burn
burn_duration = 600.0  # 10 minutes burn
post_burn_coast = 600.0  # 10 minutes coast after burn
burn_start = pre_burn_coast
burn_end = pre_burn_coast + burn_duration
total_time = pre_burn_coast + burn_duration + post_burn_coast

# Spacecraft parameters for force model
params = np.array([initial_mass, 2.0, 2.2, 2.0, 1.3])


# Define additional dynamics for mass tracking
def additional_dynamics(t, state, params):
    dx = np.zeros(len(state))
    if burn_start <= t < burn_end:
        dx[6] = -mass_flow_rate
    return dx


# Define control input for thrust acceleration
def control_input(t, state, params):
    dx = np.zeros(len(state))
    if burn_start <= t < burn_end:
        mass = state[6]
        vel = state[3:6]
        v_hat = vel / np.linalg.norm(vel)
        acc = (thrust_force / mass) * v_hat
        dx[3:6] = acc
    return dx


# Create propagator with two-body dynamics
force_config = bh.ForceModelConfig.two_body()
prop_config = bh.NumericalPropagationConfig.default()

prop = bh.NumericalOrbitPropagator(
    epoch,
    initial_state,
    prop_config,
    force_config,
    params=params,
    additional_dynamics=additional_dynamics,
    control_input=control_input,
)

# Propagate and collect mass over time
prop.propagate_to(epoch + total_time)

# Sample trajectory using trajectory interpolation
traj = prop.trajectory
times = []
mass_vals = []
thrust_active = []

dt = 5.0  # 5 second samples
t = 0.0
while t <= total_time:
    current_epoch = epoch + t
    try:
        state = traj.interpolate(current_epoch)
        times.append(t / 60.0)  # Convert to minutes
        mass_vals.append(state[6])
        thrust_active.append(1 if burn_start <= t < burn_end else 0)
    except RuntimeError:
        pass  # Skip if interpolation fails

    t += dt

# Compute expected values
expected_fuel = mass_flow_rate * burn_duration
final_mass_expected = initial_mass - expected_fuel
delta_v_expected = specific_impulse * g0 * np.log(initial_mass / final_mass_expected)


def create_figure(theme):
    colors = get_theme_colors(theme)

    fig = go.Figure()

    # Mass profile
    fig.add_trace(
        go.Scatter(
            x=times,
            y=mass_vals,
            mode="lines",
            name="Spacecraft Mass",
            line=dict(color=colors["primary"], width=3),
        )
    )

    # Initial mass reference
    fig.add_hline(
        y=initial_mass,
        line_dash="dot",
        line_color="gray",
        annotation_text=f"Initial: {initial_mass:.0f} kg",
        annotation_position="top right",
    )

    # Final mass reference
    fig.add_hline(
        y=final_mass_expected,
        line_dash="dot",
        line_color="gray",
        annotation_text=f"Final: {final_mass_expected:.1f} kg",
        annotation_position="bottom right",
    )

    # Thrust phase shading
    burn_start_min = burn_start / 60.0
    burn_end_min = burn_end / 60.0
    fig.add_vrect(
        x0=burn_start_min,
        x1=burn_end_min,
        fillcolor=colors["secondary"],
        opacity=0.1,
        layer="below",
        line_width=0,
        annotation_text="Thrust On",
        annotation_position="top left",
    )

    # Burn start indicator
    fig.add_vline(
        x=burn_start_min,
        line_dash="dash",
        line_color=colors["accent"],
        line_width=2,
        annotation_text="Burn Start",
        annotation_position="top left",
    )

    # Burn end indicator
    fig.add_vline(
        x=burn_end_min,
        line_dash="dash",
        line_color=colors["error"],
        line_width=2,
        annotation_text="Burn End",
        annotation_position="top right",
    )

    fig.update_layout(
        title=f"Mass Depletion Profile (F={thrust_force} N, Isp={specific_impulse} s)",
        xaxis_title="Time (min)",
        yaxis_title="Mass (kg)",
        showlegend=False,
        height=500,
        margin=dict(l=60, r=40, t=80, b=60),
    )

    # Add annotation with summary
    summary_text = (
        f"Fuel consumed: {expected_fuel:.2f} kg<br>"
        f"Mass flow rate: {mass_flow_rate * 1000:.2f} g/s<br>"
        f"Expected \u0394v: {delta_v_expected:.1f} m/s"
    )
    fig.add_annotation(
        x=0.98,
        y=0.5,
        xref="paper",
        yref="paper",
        text=summary_text,
        showarrow=False,
        font=dict(size=11),
        align="right",
        bordercolor="gray",
        borderwidth=1,
        borderpad=4,
        bgcolor="white" if theme == "light" else "#1e1e1e",
        opacity=0.9,
    )

    return fig


# Save themed HTML files
light_path, dark_path = save_themed_html(create_figure, OUTDIR / SCRIPT_NAME)
print(f"Generated {light_path}")
print(f"Generated {dark_path}")
```

### Tsiolkovsky Verification

The mass ratio determines achievable $\Delta v$:

$$\Delta v = I_{sp} \cdot g_0 \cdot \ln\left(\frac{m_0}{m_f}\right)$$

This provides a useful validation check for mass tracking implementations.

## Battery Tracking Example

Another common extension is tracking battery state of charge during eclipse and sunlit periods. This models solar panel charging using the conical shadow model for accurate illumination calculation.

We augment the state vector with battery energy $E_{bat}$ in Watt-hours:

$$\mathbf{x} = [x, y, z, v_x, v_y, v_z, E_{bat}]^T$$

### Power Balance Dynamics

The battery state of charge changes based on the power balance:

$$\dot{E}_{bat} = \nu \cdot P_{solar} - P_{load}$$

where:

- $\nu$ is the illumination fraction (0 = full shadow, 1 = full sunlight)
- $P_{solar}$ is the solar panel output when fully illuminated (W)
- $P_{load}$ is the spacecraft power consumption (W)

### Implementation

The `additional_dynamics` function computes the illumination at each timestep using `eclipse_conical`:


```
def additional_dynamics(t, state, params):
    """Battery dynamics with eclipse-aware solar charging."""
    dx = np.zeros(len(state))
    r_eci = state[:3]

    # Get sun position at current epoch
    current_epoch = epoch + t
    r_sun = bh.sun_position(current_epoch)

    # Get illumination fraction (0 = umbra, 0-1 = penumbra, 1 = sunlit)
    illumination = bh.eclipse_conical(r_eci, r_sun)

    # Battery dynamics (Wh/s = W / 3600)
    power_in = illumination * solar_panel_power  # W
    power_out = load_power  # W
    dx[6] = (power_in - power_out) / 3600.0  # Wh/s

    return dx
```

### Complete Example


```python
import numpy as np
import brahe as bh

# Initialize EOP data
bh.initialize_eop()

# Create initial epoch
epoch = bh.Epoch.from_datetime(2024, 6, 21, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# Initial orbital elements and state - LEO orbit
oe = np.array([bh.R_EARTH + 500e3, 0.01, 45.0, 15.0, 30.0, 45.0])
orbital_state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

# Extended state: [x, y, z, vx, vy, vz, battery_charge]
battery_capacity = 100.0  # Wh
initial_charge = 80.0  # Wh (80% SOC)
initial_state = np.concatenate([orbital_state, [initial_charge]])

# Power system parameters
solar_panel_power = 50.0  # W (when fully illuminated)
load_power = 30.0  # W (continuous consumption)

print("Power system parameters:")
print(f"  Battery capacity: {battery_capacity} Wh")
print(
    f"  Initial charge: {initial_charge} Wh ({100 * initial_charge / battery_capacity:.0f}% SOC)"
)
print(f"  Solar panel power: {solar_panel_power} W")
print(f"  Load power: {load_power} W")
print(f"  Net charging rate (sunlit): {solar_panel_power - load_power} W")
print(f"  Net discharge rate (eclipse): {load_power} W")

# Spacecraft parameters for force model [mass, drag_area, Cd, srp_area, Cr]
params = np.array([500.0, 2.0, 2.2, 2.0, 1.3])


# Define additional dynamics for battery tracking
def additional_dynamics(t, state, params):
    """
    Return full state derivative vector with battery charge dynamics.
    State: [x, y, z, vx, vy, vz, battery_charge] - return same-sized vector.
    Elements 0-5 should be zero (orbital dynamics handled by force model).
    """
    dx = np.zeros(len(state))
    r_eci = state[:3]

    # Get sun position at current epoch
    current_epoch = epoch + t
    r_sun = bh.sun_position(current_epoch)

    # Get illumination fraction (0 = umbra, 0-1 = penumbra, 1 = sunlit)
    illumination = bh.eclipse_conical(r_eci, r_sun)

    # Battery dynamics (Wh/s = W / 3600)
    power_in = illumination * solar_panel_power  # W
    power_out = load_power  # W
    charge_rate = (power_in - power_out) / 3600.0  # Wh/s

    # Apply battery limits (0 to capacity)
    charge = state[6]
    if charge >= battery_capacity and charge_rate > 0:
        charge_rate = 0.0  # Battery full
    elif charge <= 0 and charge_rate < 0:
        charge_rate = 0.0  # Battery empty

    dx[6] = charge_rate
    return dx


# Create propagator with two-body dynamics
force_config = bh.ForceModelConfig.two_body()
prop_config = bh.NumericalPropagationConfig.default()

prop = bh.NumericalOrbitPropagator(
    epoch,
    initial_state,
    prop_config,
    force_config,
    params=params,
    additional_dynamics=additional_dynamics,
)

# Calculate orbital period and propagate for 3 orbits
orbital_period = bh.orbital_period(oe[0])
num_orbits = 3
total_time = num_orbits * orbital_period

print(f"\nOrbital period: {orbital_period:.1f} s ({orbital_period / 60:.1f} min)")
print(f"Propagating for {num_orbits} orbits ({total_time / 60:.1f} min)")

# Propagate
prop.propagate_to(epoch + total_time)

# Check final state
final_state = prop.current_state()
final_charge = final_state[6]
charge_change = final_charge - initial_charge

print("\nFinal battery state:")
print(
    f"  Final charge: {final_charge:.2f} Wh ({100 * final_charge / battery_capacity:.1f}% SOC)"
)
print(f"  Charge change: {charge_change:+.2f} Wh")

# Sample trajectory to find eclipse statistics
traj = prop.trajectory
dt = 30.0  # 30 second samples
t = 0.0
eclipse_time = 0.0
sunlit_time = 0.0

while t <= total_time:
    current_epoch = epoch + t
    try:
        state = traj.interpolate(current_epoch)
        r_eci = state[:3]
        r_sun = bh.sun_position(current_epoch)
        illumination = bh.eclipse_conical(r_eci, r_sun)

        if illumination < 0.01:  # In eclipse (< 1% illumination)
            eclipse_time += dt
        else:
            sunlit_time += dt
    except RuntimeError:
        pass
    t += dt

eclipse_fraction = eclipse_time / (eclipse_time + sunlit_time)
print("\nEclipse statistics:")
print(
    f"  Sunlit time: {sunlit_time / 60:.1f} min ({100 * (1 - eclipse_fraction):.1f}%)"
)
print(f"  Eclipse time: {eclipse_time / 60:.1f} min ({100 * eclipse_fraction:.1f}%)")

# Validate
assert final_charge > 0, "Battery should not be depleted"
assert final_charge <= battery_capacity, "Battery should not exceed capacity"
assert eclipse_time > 0, "Should have some eclipse periods"
assert sunlit_time > 0, "Should have some sunlit periods"

print("\nExample validated successfully!")
```


### Battery Charge and Illumination Profile

The following plot shows battery state of charge over 3 orbits, with illumination fraction and eclipse periods clearly visible:


**Plot Source**

```python
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))
from brahe_theme import save_themed_html, get_theme_colors

# Configuration
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# Initialize EOP data
bh.initialize_eop()

# Create initial epoch and state - LEO orbit
epoch = bh.Epoch.from_datetime(2024, 6, 21, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)
oe = np.array([bh.R_EARTH + 500e3, 0.01, 45.0, 15.0, 30.0, 45.0])
orbital_state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

# Extended state: [x, y, z, vx, vy, vz, battery_charge]
battery_capacity = 100.0  # Wh
initial_charge = 80.0  # Wh (80% SOC)
initial_state = np.concatenate([orbital_state, [initial_charge]])

# Power system parameters
solar_panel_power = 50.0  # W (when fully illuminated)
load_power = 30.0  # W (continuous consumption)

# Spacecraft parameters for force model
params = np.array([500.0, 2.0, 2.2, 2.0, 1.3])


# Define additional dynamics for battery tracking
def additional_dynamics(t, state, params):
    dx = np.zeros(len(state))
    r_eci = state[:3]

    # Get sun position at current epoch
    current_epoch = epoch + t
    r_sun = bh.sun_position(current_epoch)

    # Get illumination fraction (0 = umbra, 0-1 = penumbra, 1 = sunlit)
    illumination = bh.eclipse_conical(r_eci, r_sun)

    # Battery dynamics (Wh/s = W / 3600)
    power_in = illumination * solar_panel_power
    power_out = load_power
    charge_rate = (power_in - power_out) / 3600.0

    # Apply battery limits
    charge = state[6]
    if charge >= battery_capacity and charge_rate > 0:
        charge_rate = 0.0
    elif charge <= 0 and charge_rate < 0:
        charge_rate = 0.0

    dx[6] = charge_rate
    return dx


# Create propagator with two-body dynamics
force_config = bh.ForceModelConfig.two_body()
prop_config = bh.NumericalPropagationConfig.default()

prop = bh.NumericalOrbitPropagator(
    epoch,
    initial_state,
    prop_config,
    force_config,
    params=params,
    additional_dynamics=additional_dynamics,
)

# Propagate for 3 orbits
orbital_period = bh.orbital_period(oe[0])
num_orbits = 3
total_time = num_orbits * orbital_period

prop.propagate_to(epoch + total_time)

# Sample trajectory for plotting
traj = prop.trajectory
times = []
charge_vals = []
illumination_vals = []

dt = 10.0  # 10 second samples
t = 0.0
while t <= total_time:
    current_epoch = epoch + t
    try:
        state = traj.interpolate(current_epoch)
        r_eci = state[:3]
        r_sun = bh.sun_position(current_epoch)
        illumination = bh.eclipse_conical(r_eci, r_sun)

        times.append(t / 60.0)  # Convert to minutes
        charge_vals.append(state[6])
        illumination_vals.append(illumination)
    except RuntimeError:
        pass

    t += dt

# Find eclipse regions for shading
eclipse_starts = []
eclipse_ends = []
in_eclipse = False
eclipse_threshold = 0.01  # Consider <1% illumination as eclipse

for i, illum in enumerate(illumination_vals):
    if illum < eclipse_threshold and not in_eclipse:
        eclipse_starts.append(times[i])
        in_eclipse = True
    elif illum >= eclipse_threshold and in_eclipse:
        eclipse_ends.append(times[i])
        in_eclipse = False

# Close last eclipse if still in eclipse at end
if in_eclipse and len(eclipse_starts) > len(eclipse_ends):
    eclipse_ends.append(times[-1])

# Calculate statistics
final_charge = charge_vals[-1]
charge_change = final_charge - initial_charge
sunlit_time = sum(1 for i in illumination_vals if i > eclipse_threshold) * dt / 60.0
eclipse_time = len(times) * dt / 60.0 - sunlit_time


def create_figure(theme):
    colors = get_theme_colors(theme)

    # Create figure with secondary y-axis
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Battery charge (primary y-axis)
    fig.add_trace(
        go.Scatter(
            x=times,
            y=charge_vals,
            mode="lines",
            name="Battery Charge",
            line=dict(color=colors["primary"], width=3),
        ),
        secondary_y=False,
    )

    # Illumination fraction (secondary y-axis) as filled area
    fig.add_trace(
        go.Scatter(
            x=times,
            y=illumination_vals,
            mode="lines",
            name="Illumination",
            line=dict(color=colors["secondary"], width=1),
            fill="tozeroy",
            fillcolor="rgba(255, 165, 0, 0.15)"
            if theme == "light"
            else "rgba(255, 170, 68, 0.15)",
        ),
        secondary_y=True,
    )

    # Add eclipse shading
    for start, end in zip(eclipse_starts, eclipse_ends):
        fig.add_vrect(
            x0=start,
            x1=end,
            fillcolor="rgba(100, 100, 100, 0.2)"
            if theme == "light"
            else "rgba(50, 50, 50, 0.4)",
            layer="below",
            line_width=0,
        )

    # Add reference lines
    fig.add_hline(
        y=initial_charge,
        line_dash="dot",
        line_color="gray",
        annotation_text=f"Initial: {initial_charge:.0f} Wh",
        annotation_position="top right",
        secondary_y=False,
    )

    fig.add_hline(
        y=battery_capacity,
        line_dash="dot",
        line_color=colors["accent"],
        annotation_text=f"Capacity: {battery_capacity:.0f} Wh",
        annotation_position="bottom right",
        secondary_y=False,
    )

    # Update layout
    fig.update_layout(
        title=f"Battery Charge with Eclipse Cycles (LEO, {num_orbits} orbits)",
        xaxis_title="Time (min)",
        height=500,
        margin=dict(l=60, r=80, t=80, b=60),
        legend=dict(
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01,
            bgcolor="rgba(255,255,255,0.8)"
            if theme == "light"
            else "rgba(30,30,30,0.8)",
        ),
    )

    # Update y-axes
    fig.update_yaxes(
        title_text="Battery Charge (Wh)",
        range=[60, 105],
        secondary_y=False,
    )
    fig.update_yaxes(
        title_text="Illumination Fraction",
        range=[0, 1.1],
        secondary_y=True,
    )

    # Add summary annotation
    summary_text = (
        f"Charge change: {charge_change:+.2f} Wh<br>"
        f"Final SOC: {100 * final_charge / battery_capacity:.1f}%<br>"
        f"Eclipse: {eclipse_time:.1f} min ({100 * eclipse_time / (eclipse_time + sunlit_time):.0f}%)"
    )
    fig.add_annotation(
        x=0.98,
        y=0.02,
        xref="paper",
        yref="paper",
        text=summary_text,
        showarrow=False,
        font=dict(size=11),
        align="right",
        bordercolor="gray",
        borderwidth=1,
        borderpad=4,
        bgcolor="white" if theme == "light" else "#1e1e1e",
        opacity=0.9,
    )

    # Add "Eclipse" label to first eclipse region
    if eclipse_starts:
        mid_eclipse = (eclipse_starts[0] + eclipse_ends[0]) / 2
        fig.add_annotation(
            x=mid_eclipse,
            y=0.95,
            xref="x",
            yref="paper",
            text="Eclipse",
            showarrow=False,
            font=dict(size=10, color=colors["font_color"]),
        )

    return fig


# Save themed HTML files
light_path, dark_path = save_themed_html(create_figure, OUTDIR / SCRIPT_NAME)
print(f"Generated {light_path}")
print(f"Generated {dark_path}")
```

The battery charges during sunlit periods (illumination = 1) and discharges during eclipse (illumination = 0). The penumbra regions show gradual transitions in illumination.

## Other Common Extensions

### Attitude Dynamics

Track spacecraft attitude alongside orbital motion. This example shows quaternion attitude propagation:


```
# State: [pos(3), vel(3), q0, q1, q2, q3, wx, wy, wz] = 13 elements
# Quaternion [q0, q1, q2, q3] + angular velocity [wx, wy, wz]
def additional_dynamics_attitude(t, state, params):
    """Attitude dynamics only - orbital handled by force model."""
    dx = np.zeros(len(state))

    # Extract quaternion and angular velocity
    q = state[6:10]  # [q0, q1, q2, q3]
    omega = state[10:13]  # [wx, wy, wz] rad/s

    # Quaternion kinematics: dq/dt = 0.5 * Omega(omega) * q
    omega_matrix = np.array([
        [0, -omega[0], -omega[1], -omega[2]],
        [omega[0], 0, omega[2], -omega[1]],
        [omega[1], -omega[2], 0, omega[0]],
        [omega[2], omega[1], -omega[0], 0]
    ])
    dq = 0.5 * omega_matrix @ q
    dx[6:10] = dq

    # Angular velocity dynamics: I * domega/dt = -omega x (I * omega) + torque
    I = np.diag([10.0, 12.0, 8.0])  # Inertia tensor (kg*m^2)
    torque = np.zeros(3)  # External torques
    domega = np.linalg.solve(I, -np.cross(omega, I @ omega) + torque)
    dx[10:13] = domega

    return dx
```

### Thermal State

Track spacecraft temperature:


```
# State: [pos(3), vel(3), temperature]
def additional_dynamics_thermal(t, state, params):
    """Thermal dynamics only - orbital handled by force model."""
    dx = np.zeros(len(state))
    temp = state[6]

    # Simplified radiation balance
    q_solar = solar_flux_absorbed(state[:3])
    q_radiated = emissivity * stefan_boltzmann * temp**4 * area
    dx[6] = (q_solar - q_radiated) / (mass * specific_heat)

    return dx
```

### Multiple Extensions

State vectors can include multiple extensions:


```
# State: [pos(3), vel(3), mass, battery, temperature] = 9 elements
initial_state = np.array([
    *orbital_state,  # Position and velocity (6)
    1000.0,          # Mass (kg)
    100.0,           # Battery (Wh)
    293.0,           # Temperature (K)
])

def additional_dynamics_multi(t, state, params):
    """Return full state-sized vector with derivatives for extended elements."""
    dx = np.zeros(len(state))
    mass = state[6]
    charge = state[7]
    temp = state[8]

    dx[6] = -mass_flow_rate if thrusting else 0.0
    dx[7] = solar_input - power_consumption if is_sunlit(state[:3]) else -power_consumption
    dx[8] = (q_solar - q_radiated) / (mass * specific_heat)

    return dx
```

## Implementation Notes

Another way to implement extended state propagation is to use `NumericalPropagator`, which requires implementing the full dynamics function including orbital and extended state dynamics. However, using `NumericalOrbitPropagator` with `additional_dynamics` is often more convenient for orbital applications, as it handles standard orbital perturbations automatically. See the [Generic Dynamics Propagation](generic_dynamics.md) guide for details on using `NumericalPropagator` which may be preferable for highly customized dynamics.

## See Also

- [General Dynamics Propagation](generic_dynamics.md) - Using `NumericalPropagator` for custom dynamics
- [Impulsive and Continuous Control](maneuvers.md) - Thrust implementation
- [Numerical Orbit Propagator](numerical_orbit_propagator.md) - Standard 6-DOF propagation