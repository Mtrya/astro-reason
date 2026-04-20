# Numerical Integration

Numerical integration is fundamental to spacecraft trajectory propagation, orbit determination, and mission planning. Brahe provides multiple integration methods optimized for different accuracy and performance requirements.

**Experimental Feature**
The integrators module is currently experimental. While the core functionality should be stable, the API may change in future **MINOR** releases as we refine the design and add features.

## What is Numerical Integration?

Numerical integration solves ordinary differential equations (ODEs) of the form:

$$\dot{\mathbf{x}} = \mathbf{f}(t, \mathbf{x})$$

$\mathbf{x}$ is the state vector, typically position and velocity $\mathbf{x} = \begin{bmatrix} \mathbf{p} \\ \mathbf{v} \end{bmatrix}$, and $\mathbf{f}$ defines the dynamics (gravity, perturbations, thrust, etc.). The integrator advances the state forward in time from an initial condition $\mathbf{x}_0$ at time $t_0$ to $\mathbf{x}(t)$ at some future time $t$.

In an ideal world, we would have closed-form analytical solutions for these equations. However, real-world dynamics are often too complex for exact solutions, necessitating numerical methods that approximate the solution. It is often much easier to write down the equations for the dynamics (force models) than to derive analytical solutions for them. Numerical integrators provide a way to compute these approximations efficiently and accurately.

## Available Integrators

Brahe provides four integration methods with different accuracy and performance characteristics:

| Integrator | Order | Type | Stages |
|------------|-------|------|--------|
| **RK4** | 4 | Fixed | 4 |
| **RKF45** | 4(5) | Adaptive | 6 |
| **DP54** | 5(4) | Adaptive | 7 (6 effective) |
| **RKN1210** | 12(10) | Adaptive | 17 |

## Common Interfaces

All integrators implement a consistent interface, making it easy to switch between methods.

### Core Types

**`IntegratorConfig`**: Configuration controlling integration behavior

- `abs_tol`, `rel_tol`: Error tolerances (adaptive mode)
- `min_step`, `max_step`: Step size bounds
- `step_safety_factor`: Conservative factor for step size adjustment (default 0.9)

**`AdaptiveStepResult`**: Result from adaptive integration step

- `state`: New state vector after integration
- `dt_used`: Actual time step taken (may differ from requested)
- `error_estimate`: Estimated error in the step
- `dt_next`: Recommended step size for next integration

### Dynamics Function Signature

## Control Input Function Signature

The control input function must follow specific signatures depending on the language:


```
def dynamics_fn(t: float, state: np.ndarray, params: np.ndarray) -> np.ndarray:
    """
    Args:
        t: Current time
        state: Current state vector
        params: Fixed auxiliary parameters

    Returns:
        d_state: Derivative of state vector
    """
    pass
```

### Integration Methods

All integrators provide these methods:

**`step(t, state, dt)`**: Advance state by one time step

- For fixed-step integrators: Returns new state
- For adaptive integrators: Returns `AdaptiveStepResult`

**`step_with_varmat(t, state, phi, dt)`**: Advance state and state transition matrix

- Propagates both state and variational equations
- Requires a Jacobian provider
- Essential for orbit determination and uncertainty propagation

## Comparing Integrator Accuracy

The plot below shows position error vs. time for different integrators propagating a highly elliptical orbit (HEO) compared to analytical Keplerian propagation. All adaptive integrators use the same tolerances (abs_tol=1e-10, rel_tol=1e-9). In the figure, we can see that after one orbit, RKN1210 achieves sub-millimeter accuracy, while DP54 and RKF45 reach meter-level accuracy. The fixed-step RK4 with a 60s step has the most error, reaching about 1000m after one orbit.


**Plot Source**

```python
import os
import pathlib
import sys
import plotly.graph_objects as go
import numpy as np
import brahe as bh

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from brahe_theme import save_themed_html, get_color_sequence

# Configuration
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))

# Ensure output directory exists
os.makedirs(OUTDIR, exist_ok=True)

# Initialize Brahe
bh.initialize_eop()

# Define Molniya-type HEO orbit
# Semi-major axis for 12-hour period
a = 26554e3  # meters
e = 0.74  # eccentricity
i = np.radians(63.4)  # inclination (critical inclination)
omega = 0.0  # argument of perigee
Omega = 0.0  # RAAN
M0 = 0.0  # mean anomaly

# Convert to Cartesian state
oe = np.array([a, e, i, Omega, omega, M0])
initial_state = bh.state_koe_to_eci(oe, bh.AngleFormat.RADIANS)

# Orbital period
period = 2 * np.pi * np.sqrt(a**3 / bh.GM_EARTH)


# Define two-body dynamics
def two_body_dynamics(t, state):
    """Simple two-body dynamics for integration."""
    mu = bh.GM_EARTH
    r = state[0:3]
    v = state[3:6]
    r_norm = np.linalg.norm(r)
    a = -mu / r_norm**3 * r
    return np.concatenate([v, a])


# Analytical solution using Keplerian propagation
def analytical_solution(t):
    """Compute analytical Keplerian state at time t."""
    # Mean motion
    n = np.sqrt(bh.GM_EARTH / a**3)
    # Mean anomaly at time t
    M = M0 + n * t
    # Convert back to Cartesian
    oe_t = np.array([a, e, i, Omega, omega, M])
    return bh.state_koe_to_eci(oe_t, bh.AngleFormat.RADIANS)


# Integration parameters
t_start = 0.0
t_end = period  # One orbital period
output_interval = 60.0  # Output every 60 seconds

# Common configuration for adaptive integrators
abs_tol = 1e-10
rel_tol = 1e-9

# Create integrators
config_rk4 = bh.IntegratorConfig.fixed_step(step_size=60.0)
config_adaptive = bh.IntegratorConfig.adaptive(abs_tol=abs_tol, rel_tol=rel_tol)

integrator_rk4 = bh.RK4Integrator(6, two_body_dynamics, config=config_rk4)
integrator_rkf45 = bh.RKF45Integrator(6, two_body_dynamics, config=config_adaptive)
integrator_dp54 = bh.DP54Integrator(6, two_body_dynamics, config=config_adaptive)
integrator_rkn1210 = bh.RKN1210Integrator(6, two_body_dynamics, config=config_adaptive)


# Propagate with each integrator
def propagate(integrator, is_adaptive=True):
    """Propagate orbit and record states at output intervals."""
    times = []
    states = []
    errors = []

    t = t_start
    state = initial_state.copy()
    dt = 60.0  # Initial step guess
    next_output = 0.0

    while t < t_end:
        # Check if we should save output
        if t >= next_output:
            times.append(t)
            states.append(state.copy())

            # Compute error vs analytical solution
            analytical = analytical_solution(t)
            pos_error = np.linalg.norm(state[0:3] - analytical[0:3])
            errors.append(pos_error)

            next_output += output_interval

        # Integrate one step
        if is_adaptive:
            result = integrator.step(t, state, min(dt, t_end - t))
            t += result.dt_used
            state = result.state
            dt = result.dt_next
        else:
            # Fixed step
            dt_actual = min(dt, t_end - t)
            new_state = integrator.step(t, state, dt_actual)
            t += dt_actual
            state = new_state

    # Final output
    if t >= t_end - 1e-6:  # Handle floating point comparison
        times.append(t_end)
        analytical = analytical_solution(t_end)
        pos_error = np.linalg.norm(state[0:3] - analytical[0:3])
        errors.append(pos_error)

    return np.array(times), np.array(errors)


print("Propagating with RK4...")
times_rk4, errors_rk4 = propagate(integrator_rk4, is_adaptive=False)

print("Propagating with RKF45...")
times_rkf45, errors_rkf45 = propagate(integrator_rkf45, is_adaptive=True)

print("Propagating with DP54...")
times_dp54, errors_dp54 = propagate(integrator_dp54, is_adaptive=True)

print("Propagating with RKN1210...")
times_rkn1210, errors_rkn1210 = propagate(integrator_rkn1210, is_adaptive=True)


# Create figure with theme support
def create_figure(theme):
    """Create figure with theme-specific colors."""
    colors = get_color_sequence(theme, num_colors=4)

    fig = go.Figure()

    # Add traces for each integrator with custom hover templates
    # First trace includes time at top, others don't to avoid duplication
    fig.add_trace(
        go.Scatter(
            x=times_rk4 / 3600,  # Convert to hours
            y=errors_rk4,
            name="RK4 (Fixed, dt=60s)",
            mode="lines",
            line=dict(color=colors[0], width=2),
            hovertemplate="t=%{x:.2f} hours<br><b>RK4</b><br>Error: %{y:.2e} m<extra></extra>",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=times_rkf45 / 3600,
            y=errors_rkf45,
            name="RKF45 (Adaptive)",
            mode="lines",
            line=dict(color=colors[1], width=2),
            hovertemplate="<b>RKF45</b><br>Error: %{y:.2e} m<extra></extra>",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=times_dp54 / 3600,
            y=errors_dp54,
            name="DP54 (Adaptive)",
            mode="lines",
            line=dict(color=colors[2], width=2),
            hovertemplate="<b>DP54</b><br>Error: %{y:.2e} m<extra></extra>",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=times_rkn1210 / 3600,
            y=errors_rkn1210,
            name="RKN1210 (Adaptive)",
            mode="lines",
            line=dict(color=colors[3], width=2),
            hovertemplate="<b>RKN1210</b><br>Error: %{y:.2e} m<extra></extra>",
        )
    )

    # Configure layout
    fig.update_layout(
        title="Integrator Accuracy Comparison: HEO Orbit",
        xaxis_title="Time (hours)",
        yaxis_title="Position Error (m)",
        yaxis_type="log",
        hovermode="x unified",
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
    )

    # Configure axes - hide default x-value in hover since we show it in first trace
    fig.update_xaxes(title_text="Time (hours)", unifiedhovertitle=dict(text=""))
    fig.update_yaxes(title_text="Position Error (m)", type="log")

    return fig


# Generate and save both themed versions
light_path, dark_path = save_themed_html(create_figure, OUTDIR / SCRIPT_NAME)
print(f"✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")
```

## Basic Usage Patterns

### Fixed-Step Integration

To use a fixed-step integrator like RK4, you create an instance with the desired step size and call `step` in a loop:


```python
import brahe as bh
import numpy as np


def dynamics(t, state):
    """Exponential decay dynamics: dx/dt = -k*x"""
    k = 0.1
    return np.array([-k * state[0]])


# Create fixed-step integrator
config = bh.IntegratorConfig.fixed_step(step_size=10.0)
integrator = bh.RK4Integrator(1, dynamics, config=config)

# Integrate one step
t = 0.0
initial_state = np.array([1.0])
new_state = integrator.step(t, initial_state, dt=10.0)

print(f"Initial state: {initial_state[0]:.6f}")
print(f"State after 10s: {new_state[0]:.6f}")
print(f"Analytical: {initial_state[0] * np.exp(-0.1 * 10.0):.6f}")
```


### Adaptive Integration

To use an adaptive-step integrator like RKF45, you create it with an `IntegratorConfig` specifying tolerances, then call `step`. The adaptive integrator returns an [`AdaptiveStepResult`](../../library_api/integrators/config.md) containing the new state and recommended next step size.



```python
import brahe as bh
import numpy as np


def dynamics(t, state):
    """Exponential decay dynamics: dx/dt = -k*x"""
    k = 0.1
    return np.array([-k * state[0]])


# Create adaptive integrator
config = bh.IntegratorConfig.adaptive(abs_tol=1e-10, rel_tol=1e-9)
integrator = bh.DP54Integrator(1, dynamics, config=config)

# Integrate with automatic step control
t = 0.0
initial_state = np.array([1.0])
dt = 60.0  # Initial guess

result = integrator.step(t, initial_state, dt)

print(f"Initial state: {initial_state[0]:.6f}")
print(f"State after step: {result.state[0]:.6f}")
print(f"Step used: {result.dt_used:.2f}s")
print(f"Recommended next step: {result.dt_next:.2f}s")
print(f"Error estimate: {result.error_estimate:.2e}")
```


To take multiple steps until a final time, you can use a loop that updates the time and state based on the `dt_used` and `dt_next` values from the result.


```python
import brahe as bh
import numpy as np


def dynamics(t, state):
    """Exponential decay dynamics: dx/dt = -k*x"""
    k = 0.1
    return np.array([-k * state[0]])


# Create adaptive integrator
config = bh.IntegratorConfig.adaptive(abs_tol=1e-10, rel_tol=1e-9)
integrator = bh.DP54Integrator(1, dynamics, config=config)

# --8<-- [start:snippet]
# Propagate from t=0 to t_end
t = 0.0
t_end = 86400.0  # One day
state = np.array([1.0])
dt = 60.0

step_count = 0
while t < t_end:
    result = integrator.step(t, state, min(dt, t_end - t))
    t += result.dt_used
    state = result.state
    dt = result.dt_next
    step_count += 1
# --8<-- [end:snippet]

print(f"Propagated from 0 to {t_end}s in {step_count} steps")
print(f"Final state: {state[0]:.6e}")
print(f"Analytical: {np.exp(-0.1 * t_end):.6e}")
print(f"Error: {abs(state[0] - np.exp(-0.1 * t_end)):.2e}")
```


## State Transition Matrix Propagation

For orbit determination and covariance propagation, you often need to propagate the state transition matrix (STM) alongside the state. The STM $\Phi(t, t_0)$ maps perturbations in initial state to perturbations in final state:

$$\delta\mathbf{x}(t) = \Phi(t, t_0) \cdot \delta\mathbf{x}(t_0)$$

State transition matrices are needed for a few key aspects of astrodynamics including:

- **Covariance propagation**: $P(t) = \Phi(t, t_0) P(t_0) \Phi(t, t_0)^T$
- **Sensitivity analysis**: How errors in initial conditions affect trajectory
- **Orbit determination**: Computing measurement sensitivities

They can be propagated by integrating the variational equations alongside the state, which requires computing the Jacobian of the dynamics. Brahe's integrators support this via the `step_with_varmat` method. You can learn more about defining Jacobians in the [Jacobian Computation](../mathematics/jacobian.md) guide.


```python
import brahe as bh
import numpy as np


def dynamics(t, state):
    """Exponential decay dynamics: dx/dt = -k*x"""
    k = 0.1
    return np.array([-k * state[0]])


# Create Jacobian for variational equations
jacobian = bh.NumericalJacobian.central(dynamics).with_adaptive(
    scale_factor=1e-8, min_value=1e-6
)

# Create integrator with Jacobian
config = bh.IntegratorConfig.adaptive(abs_tol=1e-12, rel_tol=1e-11)
integrator = bh.DP54Integrator(1, dynamics, jacobian=jacobian, config=config)

# Propagate state and STM
t = 0.0
state = np.array([1.0])
phi = np.eye(1)  # Identity matrix
dt = 60.0

new_state, new_phi, dt_used, error_est, dt_next = integrator.step_with_varmat(
    t, state, phi, dt
)

print(f"Initial state: {state[0]:.6f}")
print(f"State after {dt_used:.2f}s: {new_state[0]:.6f}")
print("State transition matrix:")
print(f"  Φ = {new_phi[0, 0]:.6f}")
print(f"  (Analytical Φ = {np.exp(-0.1 * dt_used):.6f})")
```


## Module Contents

- **[Fixed-Step Integrators](fixed_step.md)** - RK4 and fixed-step integration
- **[Adaptive-Step Integrators](adaptive_step.md)** - RKF45, DP54, and RKN1210
- **[Variational Equations](variational_equations.md)** - State Transition Matrix propagation and theory
- **[Configuration Guide](configuration.md)** - Choosing tolerances and tuning parameters

## See Also

- **[Comparing Integrator Performance](../../examples/using_different_integrators.md)** - Complete example comparing all integrators on a 7-day orbit propagation
- **[Integrators API Reference](../../library_api/integrators/index.md)** - Complete API documentation
- **[Jacobian Computation](../mathematics/jacobian.md)** - Required for variational equations
- **[Keplerian Propagation](../orbit_propagation/keplerian_propagation.md)** - Analytical propagation alternative