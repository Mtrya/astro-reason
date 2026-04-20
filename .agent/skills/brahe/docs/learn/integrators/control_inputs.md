# Control Inputs

Control inputs allow you to add external forcing functions to your dynamics without modifying the core dynamics function. This separation is useful for modeling thrust, drag, or other perturbations that can be toggled on and off.

## What are Control Inputs?

In control theory, a dynamical system with control inputs is written as:

$$\dot{\mathbf{x}} = \mathbf{f}(t, \mathbf{x}) + \mathbf{u}(t, \mathbf{x})$$

where:

- $\mathbf{f}(t, \mathbf{x})$ is the nominal dynamics (e.g., gravitational acceleration)
- $\mathbf{u}(t, \mathbf{x})$ is the control input (e.g., thrust acceleration)

The control input function $\mathbf{u}$ takes the current time and state and returns a vector that is added to the state derivative. This additive structure makes it easy to:

- Switch control on/off without changing the dynamics function
- Combine different control strategies
- Test different control laws with the same dynamics


## Control Input Function Signature

The control input function must follow specific signatures depending on the language:


```
def control_function(t: float, state: np.ndarray, params: np.ndarray) -> np.ndarray:
    """
    Args:
        t: Current time
        state: Current state vector
        params: Additional parameters

    Returns:
        Control vector of same dimension as state
    """
    pass
```

The function receives:
- Current time as a scalar
- Current state vector
- Additional parameters as a vector

And returns a control vector of the same dimension as the state, which is added to the derivative computed by the dynamics function. The additional parameters can be ignored if not needed, but the signature must be maintained.

## Using Control Inputs

Control inputs are passed as a separate parameter to the integrator constructor. The dynamics function computes the nominal state derivative, and the control function computes the perturbation that is added to it.


```python
def dynamics(t, state):
    """Orbital dynamics (gravity only).

    Args:
        t: Time
        state: [x, y, z, vx, vy, vz]
    """
    r = state[:3]
    v = state[3:]
    r_norm = np.linalg.norm(r)
    a_grav = -bh.GM_EARTH / (r_norm**3) * r
    return np.concatenate([v, a_grav])


def control_input(t, state):
    """Control input: constant low thrust in velocity direction.

    Args:
        t: Time
        state: [x, y, z, vx, vy, vz]

    Returns:
        Control vector added to state derivative
    """
    v = state[3:]
    v_norm = np.linalg.norm(v)

    control = np.zeros(6)
    if v_norm > 0:
        thrust_magnitude = 0.001  # m/s^2
        control[3:] = thrust_magnitude * v / v_norm

    return control


# Initial LEO state (500 km altitude, circular orbit)
sma = bh.R_EARTH + 500e3
state_initial = np.array([sma, 0.0, 0.0, 0.0, 7612.6, 0.0])

# Orbital period
period = bh.orbital_period(sma)

# Create integrator WITH control input parameter
config = bh.IntegratorConfig.adaptive(abs_tol=1e-10, rel_tol=1e-8)
integrator_thrust = bh.DP54Integrator(
    6, dynamics, jacobian=None, control_fn=control_input, config=config
)

# Create integrator without control (for comparison)
integrator_coast = bh.DP54Integrator(6, dynamics, config=config)

# Propagate with thrust for one orbit
state_thrust = state_initial.copy()
t = 0.0
dt = 60.0

while t < period:
    result = integrator_thrust.step(t, state_thrust, dt)
    state_thrust = result.state
    t += result.dt_used
    dt = result.dt_next

# Propagate without thrust for comparison
state_coast = state_initial.copy()
t = 0.0
dt = 60.0

while t < period:
    result = integrator_coast.step(t, state_coast, dt)
    state_coast = result.state
    t += result.dt_used
    dt = result.dt_next

# Results
r_initial = np.linalg.norm(state_initial[:3])
r_thrust = np.linalg.norm(state_thrust[:3])
r_coast = np.linalg.norm(state_coast[:3])

print(f"Initial radius: {r_initial / 1000:.3f} km")
print(f"Orbital period: {period / 3600:.2f} hours")
print("\nAfter one orbit:")
print(
    f"  With thrust: {r_thrust / 1000:.3f} km (delta_r = {(r_thrust - r_initial) / 1000:.3f} km)"
)
print(
    f"  Coast only:  {r_coast / 1000:.3f} km (delta_r = {(r_coast - r_initial) / 1000:.3f} km)"
)
```


## Applications

Control inputs are particularly useful for:

- **Orbit raising/lowering**: Frequent thrusting to get to desired orbit
- **Station keeping**: Small corrections to maintain orbit and compensate for drag
- **Redezvous and Proximity Operations**: Relative motion control between satellites
- **Spacecraft Collision Avoidance**: Maneuvering to avoid debris

## See Also

- [Adaptive Step Integration](adaptive_step.md) - Recommended for control problems
- [Variational Equations](variational_equations.md) - For control sensitivity analysis
- [Configuration Guide](configuration.md) - Tuning integrator parameters