# General Dynamics Propagation

The `NumericalPropagator` provides a general-purpose numerical integrator for arbitrary ordinary differential equations (ODEs). Unlike `NumericalOrbitPropagator` which has built-in orbital force models, the generic propagator accepts user-defined dynamics functions for any dynamical system.

For API details, see the [NumericalPropagator API Reference](../../../library_api/propagators/numerical_propagator.md).

## When to Use General Dynamics

Use `NumericalPropagator` when:

- Propagating non-orbital systems (simple harmonic oscillators, population models, etc.)
- Implementing custom force models not available in `NumericalOrbitPropagator`
- Integrating coupled systems (orbit + attitude, multiple bodies, etc.)
- Prototyping custom dynamics before committing to the orbital framework

For orbital mechanics with extended state (mass, battery, temperature tracking), prefer `NumericalOrbitPropagator` with `additional_dynamics`. See [Extending Spacecraft State](extending_state.md).

## Full Example

The following example demonstrates propagating a simple harmonic oscillator (SHO), a canonical test case for numerical integrators:


```python
import numpy as np
import brahe as bh

# Initialize EOP data (needed for epoch operations)
bh.initialize_eop()

# Create initial epoch
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# Simple Harmonic Oscillator (SHO)
# State: [x, v] where x is position and v is velocity
# Dynamics: dx/dt = v, dv/dt = -omega^2 * x
omega = 2.0 * np.pi  # 1 Hz oscillation frequency

# Initial state: displaced from equilibrium
x0 = 1.0  # 1 meter displacement
v0 = 0.0  # Starting from rest
initial_state = np.array([x0, v0])


def sho_dynamics(t, state, params):
    """Simple harmonic oscillator dynamics."""
    x, v = state[0], state[1]
    omega_sq = params[0] if params is not None else omega**2
    return np.array([v, -omega_sq * x])


# Parameters (omega^2)
params = np.array([omega**2])

# Create generic numerical propagator
prop = bh.NumericalPropagator(
    epoch,
    initial_state,
    sho_dynamics,
    bh.NumericalPropagationConfig.default(),
    params,
)

# Propagate for several periods
period = 2 * np.pi / omega  # Period = 2*pi/omega = 1 second
prop.propagate_to(epoch + 5 * period)

# Sample trajectory
print("Simple Harmonic Oscillator Trajectory:")
print("  omega = 2*pi rad/s (1 Hz)")
print("  x0 = 1.0 m, v0 = 0.0 m/s")
print("\nTime (s)  Position (m)  Velocity (m/s)  Analytical x")
print("-" * 55)

for i in range(11):
    t = i * period / 2  # Sample at half-period intervals
    state = prop.state(epoch + t)
    # Analytical solution: x(t) = x0*cos(omega*t), v(t) = -x0*omega*sin(omega*t)
    x_analytical = x0 * np.cos(omega * t)
    print(
        f"  {t:.2f}      {state[0]:+.6f}      {state[1]:+.6f}      {x_analytical:+.6f}"
    )

# Validate - after full period should return to initial
final_state = prop.state(epoch + 5 * period)
error_x = abs(final_state[0] - x0)
error_v = abs(final_state[1] - v0)

print("\nAfter 5 periods:")
print(f"  Position error: {error_x:.2e} m")
print(f"  Velocity error: {error_v:.2e} m/s")

assert error_x < 0.01  # Within 1 cm
assert error_v < 0.1  # Within 10 cm/s

print("\nExample validated successfully!")
```


### SHO Visualization

The following plot shows the position and velocity of the SHO over 3 periods, comparing numerical and analytical solutions:


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

# Create initial epoch
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# Simple Harmonic Oscillator parameters
omega = 2.0 * np.pi  # 1 Hz oscillation frequency
x0 = 1.0  # 1 meter initial displacement
v0 = 0.0  # Starting from rest
initial_state = np.array([x0, v0])


def sho_dynamics(t, state, params):
    """Simple harmonic oscillator dynamics."""
    x, v = state[0], state[1]
    omega_sq = params[0] if params is not None else omega**2
    return np.array([v, -omega_sq * x])


# Parameters (omega^2)
params = np.array([omega**2])

# Create propagator
prop = bh.NumericalPropagator(
    epoch,
    initial_state,
    sho_dynamics,
    bh.NumericalPropagationConfig.default(),
    params,
)

# Propagate for 3 periods
period = 2 * np.pi / omega  # Period = 1 second
total_time = 3 * period
prop.propagate_to(epoch + total_time)

# Sample trajectory at high resolution
dt = 0.01  # 10 ms intervals
times = []
positions = []
velocities = []
positions_analytical = []
velocities_analytical = []

t = 0.0
while t <= total_time:
    state = prop.state(epoch + t)
    times.append(t)
    positions.append(state[0])
    velocities.append(state[1])

    # Analytical solution: x(t) = x0*cos(omega*t), v(t) = -x0*omega*sin(omega*t)
    positions_analytical.append(x0 * np.cos(omega * t))
    velocities_analytical.append(-x0 * omega * np.sin(omega * t))

    t += dt


def create_figure(theme):
    colors = get_theme_colors(theme)

    # Create subplot with 2 rows
    fig = make_subplots(
        rows=2,
        cols=1,
        subplot_titles=("Position vs Time", "Velocity vs Time"),
        vertical_spacing=0.15,
    )

    # Position trace (numerical)
    fig.add_trace(
        go.Scatter(
            x=times,
            y=positions,
            mode="lines",
            name="Numerical",
            line=dict(color=colors["primary"], width=2),
            legendgroup="numerical",
        ),
        row=1,
        col=1,
    )

    # Position trace (analytical) - dashed
    fig.add_trace(
        go.Scatter(
            x=times,
            y=positions_analytical,
            mode="lines",
            name="Analytical",
            line=dict(color=colors["secondary"], width=2, dash="dash"),
            legendgroup="analytical",
        ),
        row=1,
        col=1,
    )

    # Velocity trace (numerical)
    fig.add_trace(
        go.Scatter(
            x=times,
            y=velocities,
            mode="lines",
            name="Numerical",
            line=dict(color=colors["primary"], width=2),
            legendgroup="numerical",
            showlegend=False,
        ),
        row=2,
        col=1,
    )

    # Velocity trace (analytical) - dashed
    fig.add_trace(
        go.Scatter(
            x=times,
            y=velocities_analytical,
            mode="lines",
            name="Analytical",
            line=dict(color=colors["secondary"], width=2, dash="dash"),
            legendgroup="analytical",
            showlegend=False,
        ),
        row=2,
        col=1,
    )

    # Update layout
    fig.update_layout(
        title="Simple Harmonic Oscillator (ω = 2π rad/s)",
        height=600,
        margin=dict(l=60, r=40, t=80, b=60),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
        ),
    )

    # Update x-axes
    fig.update_xaxes(title_text="Time (s)", row=2, col=1)

    # Update y-axes
    fig.update_yaxes(title_text="Position (m)", row=1, col=1)
    fig.update_yaxes(title_text="Velocity (m/s)", row=2, col=1)

    return fig


# Save themed HTML files
light_path, dark_path = save_themed_html(create_figure, OUTDIR / SCRIPT_NAME)
print(f"Generated {light_path}")
print(f"Generated {dark_path}")
```

## Architecture Overview

### NumericalPropagator vs NumericalOrbitPropagator

| Feature | NumericalOrbitPropagator | NumericalPropagator |
|---------|-------------------------|---------------------|
| Orbital dynamics | Built-in via ForceModelConfig | Must implement in dynamics_fn |
| State dimension | 6+ (orbital + extended) | Any dimension |
| Extended state | Via `additional_dynamics` | Include in dynamics_fn |
| Control | Via `control_input` | Via `control_input` |
| Trajectory type | `(D)OrbitTrajectory` with interpolation | `(D)Trajectory` |
| Use case | Orbital mechanics | Any ODE system |

## Dynamics Function

The dynamics function defines the system's equations of motion. It receives the current time (seconds from epoch), state vector, and optional parameters, returning the state derivative.

### Function Signature


```
def dynamics(t: float, state: np.ndarray, params: np.ndarray | None) -> np.ndarray:
    """
    Compute state derivative for given time and state.

    Args:
        t: Time in seconds from reference epoch
        state: Current state vector (N-dimensional)
        params: Optional parameter vector

    Returns:
        State derivative vector (same dimension as state)
    """
    dstate = np.zeros(len(state))
    # Compute derivatives based on your equations of motion
    # ...
    return dstate
```

### Mathematical Form

For a general system, the dynamics function computes:

$$\dot{\mathbf{x}} = f(t, \mathbf{x}, \mathbf{p})$$

where $\mathbf{x}$ is the state vector, $t$ is time, and $\mathbf{p}$ is the parameter vector.

For orbital mechanics, the standard 6-element state is:

$$\mathbf{x} = [x, y, z, v_x, v_y, v_z]^T$$

With derivative:

$$\dot{\mathbf{x}} = [v_x, v_y, v_z, a_x, a_y, a_z]^T$$

## Parameter Handling

Parameters allow passing constants to the dynamics function without hardcoding them:


```
# Define parameters
params = np.array([omega**2, damping_coeff, mass])

# Access in dynamics function
def dynamics(t, state, params):
    omega_sq = params[0]
    damping = params[1]
    mass = params[2]
    # Use parameters in computation
    ...

# Create propagator with parameters
prop = bh.NumericalPropagator(
    epoch, initial_state, dynamics,
    bh.NumericalPropagationConfig.default(),
    params  # Pass parameters here
)
```

## Control Inputs

`NumericalPropagator` supports a separate `control_input` function that adds control contributions to the state derivative at each integration step. This separates the natural dynamics from control logic, making it easier to enable/disable control or swap control strategies.

The following example shows a damped harmonic oscillator where damping is implemented via `control_input`:


```python
import numpy as np
import brahe as bh

# Initialize EOP data (needed for epoch operations)
bh.initialize_eop()

# Create initial epoch
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# Simple Harmonic Oscillator with damping control
# State: [x, v] where x is position and v is velocity
# Natural dynamics: dx/dt = v, dv/dt = -omega^2 * x
# Control adds damping: u = -c * v
omega = 2.0 * np.pi  # 1 Hz natural frequency
damping_ratio = 0.1  # Damping ratio (zeta)
damping_coeff = 2 * damping_ratio * omega  # c = 2*zeta*omega

# Initial state: displaced from equilibrium
x0 = 1.0  # 1 meter displacement
v0 = 0.0  # Starting from rest
initial_state = np.array([x0, v0])


def sho_dynamics(t, state, params):
    """Simple harmonic oscillator dynamics (undamped).

    This function defines only the natural dynamics.
    Control is added separately via control_input.
    """
    x, v = state[0], state[1]
    omega_sq = params[0] if params is not None else omega**2
    return np.array([v, -omega_sq * x])


def damping_control(t, state, params):
    """Damping control input: u = -c * v (opposes velocity).

    The control_input function returns a state derivative contribution
    that is added to the dynamics output at each integration step.
    """
    dx = np.zeros(len(state))
    v = state[1]
    # Control adds acceleration that opposes velocity
    dx[1] = -damping_coeff * v
    return dx


# Parameters (omega^2)
params = np.array([omega**2])

# Create propagator with dynamics AND control_input
prop_damped = bh.NumericalPropagator(
    epoch,
    initial_state,
    sho_dynamics,
    bh.NumericalPropagationConfig.default(),
    params,
    control_input=damping_control,  # Separate control function
)

# Create undamped propagator for comparison (no control_input)
prop_undamped = bh.NumericalPropagator(
    epoch,
    initial_state,
    sho_dynamics,
    bh.NumericalPropagationConfig.default(),
    params,
)

# Propagate for several periods
period = 2 * np.pi / omega  # Period = 1 second
prop_damped.propagate_to(epoch + 10 * period)
prop_undamped.propagate_to(epoch + 10 * period)

# Sample trajectory and compare
print("Damped vs Undamped Harmonic Oscillator:")
print(f"  Natural frequency: {omega / (2 * np.pi):.1f} Hz")
print(f"  Damping ratio: {damping_ratio}")
print(f"  Damping coefficient: {damping_coeff:.3f} /s")
print("\nTime (s)  Damped x    Undamped x  Amplitude ratio")
print("-" * 55)

for i in range(11):
    t = i * period  # Sample at period intervals
    state_damped = prop_damped.state(epoch + t)
    state_undamped = prop_undamped.state(epoch + t)
    ratio = abs(state_damped[0]) / max(abs(state_undamped[0]), 1e-10)
    print(
        f"  {t:.1f}       {state_damped[0]:+.4f}      {state_undamped[0]:+.4f}       {ratio:.3f}"
    )

# Validate - damped oscillator should decay
final_damped = prop_damped.state(epoch + 10 * period)
final_undamped = prop_undamped.state(epoch + 10 * period)

# Expected decay: amplitude ~ exp(-zeta*omega*t) = exp(-0.1 * 2*pi * 10) ~ 0.002
expected_ratio = np.exp(-damping_ratio * omega * 10 * period)
actual_ratio = abs(final_damped[0]) / abs(x0)

print("\nAfter 10 periods:")
print(f"  Damped amplitude: {abs(final_damped[0]):.4f} m")
print(f"  Undamped amplitude: {abs(final_undamped[0]):.4f} m")
print(f"  Expected decay ratio: {expected_ratio:.4f}")
print(f"  Actual decay ratio: {actual_ratio:.4f}")

assert abs(final_damped[0]) < abs(final_undamped[0])  # Damped has smaller amplitude
assert actual_ratio < 0.1  # Should decay significantly

print("\nExample validated successfully!")
```


## Event Detection

The generic propagator supports the same event detection system as `NumericalOrbitPropagator`. Events can detect when computed quantities cross threshold values:


```python
import numpy as np
import brahe as bh

# Initialize EOP data (needed for epoch operations)
bh.initialize_eop()

# Create initial epoch
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# Simple Harmonic Oscillator
# State: [x, v] where x is position and v is velocity
omega = 2.0 * np.pi  # 1 Hz oscillation frequency

# Initial state: displaced from equilibrium
x0 = 1.0  # 1 meter displacement
v0 = 0.0  # Starting from rest
initial_state = np.array([x0, v0])


def sho_dynamics(t, state, params):
    """Simple harmonic oscillator dynamics."""
    x, v = state[0], state[1]
    omega_sq = params[0] if params is not None else omega**2
    return np.array([v, -omega_sq * x])


# Parameters (omega^2)
params = np.array([omega**2])

# Create propagator
prop = bh.NumericalPropagator(
    epoch,
    initial_state,
    sho_dynamics,
    bh.NumericalPropagationConfig.default(),
    params,
)


# Define value function for zero crossing detection
# ValueEvent receives (epoch, state) and returns a scalar
def position_value(current_epoch, state):
    """Return position component for event detection."""
    return state[0]


# Create ValueEvent to detect position zero crossings
# INCREASING: x goes from negative to positive (moving right through origin)
positive_crossing = bh.ValueEvent(
    "Positive Crossing",
    position_value,
    0.0,  # Target value
    bh.EventDirection.INCREASING,
)

# DECREASING: x goes from positive to negative (moving left through origin)
negative_crossing = bh.ValueEvent(
    "Negative Crossing",
    position_value,
    0.0,
    bh.EventDirection.DECREASING,
)

# Add event detectors to propagator
prop.add_event_detector(positive_crossing)
prop.add_event_detector(negative_crossing)

# Propagate for 5 periods
period = 2 * np.pi / omega  # Period = 1 second
prop.propagate_to(epoch + 5 * period)

# Get event log
events = prop.event_log()

print("Simple Harmonic Oscillator Zero Crossings:")
print(f"  omega = {omega:.4f} rad/s (1 Hz)")
print(f"  Period = {period:.4f} s")
print("  Expected crossings per period: 2 (one each direction)")
print()

positive_events = [e for e in events if "Positive" in e.name]
negative_events = [e for e in events if "Negative" in e.name]

print(f"Total events detected: {len(events)}")
print(f"  Positive crossings: {len(positive_events)}")
print(f"  Negative crossings: {len(negative_events)}")
print()

print("Event details:")
print("  Time (s)   Type               Position     Velocity")
print("-" * 60)

for event in events[:10]:  # Show first 10 events
    t = event.window_open - epoch
    x = event.entry_state[0]
    v = event.entry_state[1]
    print(f"  {t:.4f}     {event.name:<18} {x:+.6f}   {v:+.6f}")

# Validate
# In 5 periods, we should have 5 positive crossings and 5 negative crossings
assert len(positive_events) == 5, (
    f"Expected 5 positive crossings, got {len(positive_events)}"
)
assert len(negative_events) == 5, (
    f"Expected 5 negative crossings, got {len(negative_events)}"
)

# Check timing: crossings should occur at quarter periods
# Starting from x=1, v=0: oscillator moves left first (cosine motion)
# Negative crossing (moving left) at T/4, 5T/4, 9T/4, ...
# Positive crossing (moving right) at 3T/4, 7T/4, 11T/4, ...
expected_negative_times = [(0.25 + i) * period for i in range(5)]
expected_positive_times = [(0.75 + i) * period for i in range(5)]

for i, event in enumerate(negative_events):
    t = event.window_open - epoch
    expected = expected_negative_times[i]
    error = abs(t - expected)
    assert error < 0.02, (
        f"Negative crossing {i}: expected t={expected:.4f}, got t={t:.4f}"
    )

for i, event in enumerate(positive_events):
    t = event.window_open - epoch
    expected = expected_positive_times[i]
    error = abs(t - expected)
    assert error < 0.02, (
        f"Positive crossing {i}: expected t={expected:.4f}, got t={t:.4f}"
    )

print("\nTiming verified: all crossings within 0.02s of expected times")

print("\nExample validated successfully!")
```


## Extended State Vectors

The generic propagator supports arbitrary state dimensions. The following pseudocode illustrates common extensions:

**Illustrative Pseudocode**
The examples below are simplified pseudocode to illustrate the concepts. For complete, runnable examples of extended state propagation, see [Extending Spacecraft State](extending_state.md).

### Attitude Dynamics

Include quaternion and angular velocity for 6-DOF simulation (13-element state):


```
def six_dof_dynamics(t, state, params):
    # State: [pos(3), vel(3), quat(4), omega(3)] = 13 elements
    pos = state[:3]
    vel = state[3:6]
    quat = state[6:10]   # [q0, q1, q2, q3]
    omega = state[10:13]  # Angular velocity [rad/s]

    # Translational dynamics (two-body gravity)
    r = np.linalg.norm(pos)
    acc = -bh.GM_EARTH * pos / r**3

    # Attitude kinematics (quaternion derivative)
    omega_quat = np.array([0, omega[0], omega[1], omega[2]])
    q_dot = 0.5 * quaternion_multiply(quat, omega_quat)

    # Angular dynamics (Euler's equations)
    I = np.diag(params[:3])  # Inertia tensor diagonal [kg*m^2]
    torque = np.zeros(3)     # External torques [N*m]
    omega_dot = np.linalg.inv(I) @ (torque - np.cross(omega, I @ omega))

    return np.concatenate([vel, acc, q_dot, omega_dot])
```

### Relative Motion (Hill-Clohessy-Wiltshire)

Propagate relative position/velocity for formation flying in the Hill frame:


```
def hill_clohessy_wiltshire(t, state, params):
    # State: [x, y, z, vx, vy, vz] in Hill frame (RTN)
    x, y, z, vx, vy, vz = state
    n = params[0]  # Mean motion of reference orbit [rad/s]

    # HCW equations (linearized relative motion)
    ax = 3*n**2*x + 2*n*vy
    ay = -2*n*vx
    az = -n**2*z

    return np.array([vx, vy, vz, ax, ay, az])
```

## Quick Reference

### NumericalPropagator Constructor Parameters

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `epoch` | Epoch | Initial epoch | Yes |
| `initial_state` | DVector / ndarray | Initial state vector (N-dimensional) | Yes |
| `dynamics_fn` | Closure / Callable | State derivative function | Yes |
| `config` | NumericalPropagationConfig | Integrator settings | Yes |
| `params` | DVector / ndarray | Optional parameter vector | No |
| `control_input` | Closure / Callable | Optional control input function | No |
| `initial_covariance` | DMatrix / ndarray | Optional initial covariance (enables STM) | No |

## Performance Considerations

Custom dynamics functions are called at every integration step, so efficiency matters:

1. **Minimize function calls**: Cache expensive computations
2. **Avoid allocations**: Reuse arrays where possible
3. **Use NumPy vectorization**: Avoid Python loops for numerical operations
4. **Profile your dynamics**: The dynamics function dominates runtime

For Rust, ensure the dynamics closure captures minimal state and avoids unnecessary cloning.

---

## See Also

- [Numerical Propagation Overview](index.md) - Architecture and concepts
- [Extending Spacecraft State](extending_state.md) - Extended state for orbital propagation
- [Maneuvers](maneuvers.md) - Control inputs for thrust
- [Event Detection](event_detection.md) - Detecting conditions
- [NumericalPropagator API Reference](../../../library_api/propagators/numerical_propagator.md)