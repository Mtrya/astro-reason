# Adaptive-Step Integrators

Adaptive-step integrators automatically adjust their step size to maintain a specified error tolerance. This makes them efficient and reliable for problems where the optimal step size isn't known in advance or varies during integration. They are particularly useful for orbital mechanics, where dynamics can change rapidly due to close encounters or perturbations. In elliptical orbits, for example, smaller steps are needed near periapsis to capture rapid motion, while taking larger steps near apoapsis is acceptable and saves computation.

## How Adaptive Stepping Works

Adaptive methods estimate the local truncation error at each step by computing two solutions of different orders:

1. **Higher-order solution** (order $p$): More accurate, used for propagation
2. **Lower-order solution** (order $p-1$): Less accurate, used for error estimation

The **error estimate** is the difference between these solutions:

$$
\varepsilon \approx \|\mathbf{x}_p - \mathbf{x}_{p-1}\|
$$

This is compared against a **tolerance**:

$$
\text{tol} = \text{abs\_tol} + \text{rel\_tol} \times \|\mathbf{x}\|
$$

- **If $\varepsilon < \text{tol}$**: Step accepted, state advances
- **If $\varepsilon \geq \text{tol}$**: Step rejected, retry with smaller $h$

## Available Adaptive Integrators

### RKF45: Runge-Kutta-Fehlberg 4(5)

An embedded Runge-Kutta method using 5th-order solution for propagation and 4th-order solution for error estimation.

### DP54: Dormand-Prince 5(4)

An embedded Runge-Kutta method widely used in scientific computing (e.g., MATLAB's `ode45`).

### RKN1210: Runge-Kutta-Nyström 12(10)

A high-order method specialized for second-order differential equations, particularly well-suited to orbital mechanics.

**Requirements:**

- State dimension must be even (position and velocity components)
- Best suited for problems naturally expressed as second-order systems (e.g., $\mathbf{F} = m\mathbf{a}$)

## Basic Usage


```python
import brahe as bh
import numpy as np

# Define dynamics: Van der Pol oscillator (stiff for large mu)
mu = 1.0


def dynamics(t, state):
    x, v = state
    return np.array([v, mu * (1 - x**2) * v - x])


# Initial conditions
t0 = 0.0
state0 = np.array([2.0, 0.0])
t_end = 10.0

# Create adaptive integrator
abs_tol = 1e-8
rel_tol = 1e-7
config = bh.IntegratorConfig.adaptive(abs_tol=abs_tol, rel_tol=rel_tol)
integrator = bh.DP54Integrator(2, dynamics, config=config)

print(f"Adaptive integration of Van der Pol oscillator (μ={mu})")
print(f"Tolerances: abs_tol={abs_tol}, rel_tol={rel_tol}")
print(f"Integration time: 0 to {t_end} seconds\n")

# Integrate with adaptive stepping
t = t0
state = state0.copy()
dt = 0.1  # Initial guess
steps = 0
min_dt = float("inf")
max_dt = 0.0

print("   Time    State              Step Size   Error Est")
print("-" * 65)

while t < t_end:
    result = integrator.step(t, state, min(dt, t_end - t))

    # Track step size statistics
    min_dt = min(min_dt, result.dt_used)
    max_dt = max(max_dt, result.dt_used)

    # Update state
    t += result.dt_used
    state = result.state
    dt = result.dt_next
    steps += 1

    # Print progress
    if steps % 10 == 1:
        print(
            f"{t:7.3f}    [{state[0]:6.3f}, {state[1]:6.3f}]    {result.dt_used:7.4f}     {result.error_estimate:.2e}"
        )

print("\nIntegration complete!")
print(f"Total steps: {steps}")
print(f"Min step size: {min_dt:.6f} s")
print(f"Max step size: {max_dt:.6f} s")
print(f"Average step: {t_end / steps:.6f} s")
print("\nAdaptive stepping automatically adjusted step size")
print(f"by {max_dt / min_dt:.1f}x during integration")
```


## Step Size Control Algorithm

After computing error estimate $\varepsilon$, the integrator calculates a new step size:

$$h_{\text{new}} = \text{safety\_factor} \times h \times \left(\frac{\text{tol}}{\varepsilon}\right)^{1/p}$$

where:
- **safety_factor**: Conservative multiplier (default 0.9)
- **$p$**: Order of error estimate
- **$h$**: Current step size

This is clamped to reasonable bounds:

$$h_{\text{new}} = \text{clip}(h_{\text{new}}, \text{min\_scale} \times h, \text{max\_scale} \times h)$$

and absolute limits:

$$h_{\text{new}} = \text{clip}(h_{\text{new}}, h_{\text{min}}, h_{\text{max}})$$

### Control Parameters

From `IntegratorConfig`:

- `abs_tol`: Absolute error tolerance (default 1e-10)
- `rel_tol`: Relative error tolerance (default 1e-9)
- `min_step`: Minimum allowed step size (default 1e-12 s)
- `max_step`: Maximum allowed step size (default 900 s)
- `step_safety_factor`: Safety margin (default 0.9)
- `min_step_scale_factor`: Min step change ratio (default 0.2)
- `max_step_scale_factor`: Max step change ratio (default 10.0)
- `max_step_attempts`: Max tries before error (default 10)

## Highly Elliptical Orbit Example

The following example demonstrates propagating a highly elliptical orbit (HEO) using the RKN1210 adaptive-step integrator with tight tolerances for high precision.


```python
import brahe as bh
import numpy as np

# Initialize EOP data
bh.initialize_eop()

# Define HEO orbit (Molniya-type)
a = 26554e3  # Semi-major axis (m)
e = 0.74  # Eccentricity
i = 63.4  # Inclination

# Convert to Cartesian state
oe = np.array([a, e, i, 0.0, 0.0, 0.0])
state0 = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

# Orbital period
period = bh.orbital_period(a)


# Two-body dynamics
def dynamics(t, state):
    mu = bh.GM_EARTH
    r = state[0:3]
    v = state[3:6]
    r_norm = np.linalg.norm(r)
    a = -mu / r_norm**3 * r
    return np.concatenate([v, a])


print("High-Precision HEO Orbit Propagation")
print(f"Semi-major axis: {a / 1e3:.1f} km")
print(f"Eccentricity: {e}")
print(f"Period: {period / 3600:.2f} hours\n")

# Create RKN1210 integrator with very tight tolerances
abs_tol = 1e-14
rel_tol = 1e-13
config = bh.IntegratorConfig.adaptive(abs_tol=abs_tol, rel_tol=rel_tol)
integrator = bh.RKN1210Integrator(6, dynamics, config=config)

print(f"Using RKN1210 with tol={abs_tol:.0e}")
print("Propagating for one orbital period...\n")

# Propagate for one orbit
t = 0.0
state = state0.copy()
dt = 60.0
steps = 0
total_error = 0.0

while t < period:
    result = integrator.step(t, state, min(dt, period - t))

    t += result.dt_used
    state = result.state
    dt = result.dt_next
    steps += 1
    total_error += result.error_estimate

    # Print at apogee and perigee
    r_norm = np.linalg.norm(state[0:3])
    if steps % 10 == 1:
        print(
            f"t={t / 3600:6.2f}h  r={r_norm / 1e3:8.1f}km  dt={result.dt_used:6.1f}s  err={result.error_estimate:.2e}"
        )

print("\nPropagation complete!")
print(f"Total steps: {steps}")
print(f"Average step: {period / steps:.1f} s")
print(f"Cumulative error estimate: {total_error:.2e}")

# Verify orbit closure (should return close to initial state)
final_oe = bh.state_eci_to_koe(state, bh.AngleFormat.DEGREES)
initial_oe = bh.state_eci_to_koe(state0, bh.AngleFormat.DEGREES)

print("\nOrbit element errors after one period:")
print(f"  Semi-major axis: {abs(final_oe[0] - initial_oe[0]):.3e} m")
print(f"  Eccentricity:    {abs(final_oe[1] - initial_oe[1]):.3e}")
```


## See Also

- **[Configuration Guide](configuration.md)** - Detailed parameter tuning
- **[Fixed-Step Integrators](fixed_step.md)** - For comparison
- **[RKF45 API Reference](../../library_api/integrators/rkf45.md)** - RKF45 documentation
- **[DP54 API Reference](../../library_api/integrators/dp54.md)** - DP54 documentation
- **[RKN1210 API Reference](../../library_api/integrators/rkn1210.md)** - RKN1210 documentation
- **[Integrators Overview](index.md)** - Comparison of all integrators