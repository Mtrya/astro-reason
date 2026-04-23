# Sensitivity Matrix

The sensitivity matrix extends variational equations to include the effect of uncertain parameters on the state. While the State Transition Matrix (STM) maps initial state uncertainties to final state uncertainties, the sensitivity matrix maps parameter uncertainties to state uncertainties.

## What is the Sensitivity Matrix?

For a dynamical system that depends on both state and parameters:

$$\dot{\mathbf{x}} = \mathbf{f}(t, \mathbf{x}, \mathbf{p})$$

where $\mathbf{p}$ is a vector of "consider parameters" (parameters that affect dynamics but aren't estimated), the sensitivity matrix $\mathbf{S}$ describes how state evolves with respect to parameter changes:

$$\mathbf{S}(t) = \frac{\partial \mathbf{x}(t)}{\partial \mathbf{p}}$$

The sensitivity matrix satisfies the differential equation:

$$\dot{\mathbf{S}} = \frac{\partial \mathbf{f}(t, \mathbf{x}, \mathbf{p})}{\partial \mathbf{x}} \mathbf{S} + \frac{\partial \mathbf{f}(t, \mathbf{x}, \mathbf{p})}{\partial \mathbf{p}}$$

Sensitivity matrices are essential for accounting for parameter uncertainties in orbit determination.

## Relationship to STM

The sensitivity matrix and STM serve related but distinct purposes:

| Matrix | Equation | Maps |
|--------|----------|------|
| STM $\Phi$ | $\dot{\Phi} = \mathbf{A}\Phi$ | Initial state → Final state |
| Sensitivity $\mathbf{S}$ | $\dot{\mathbf{S}} = \mathbf{A}\mathbf{S} + \mathbf{B}$ | Parameters → Final state |

## Propagating the Sensitivity Matrix

Brahe integrators provide `step_with_sensmat()` for propagating the sensitivity matrix alongside the state:

```
// Result: (new_state, new_sensitivity, dt_used, error, dt_next)
let (state, sens, dt_used, error, dt_next) =
    integrator.step_with_sensmat(t, state, sensitivity, &params, dt);
```

For combined STM and sensitivity propagation:

```
// Result: (new_state, new_stm, new_sensitivity, dt_used, error, dt_next)
let (state, phi, sens, dt_used, error, dt_next) =
    integrator.step_with_varmat_sensmat(t, state, phi, sensitivity, &params, dt);
```

## Using Sensitivity Providers

Brahe provides two approaches for computing the sensitivity matrix $\partial \mathbf{f}/\partial \mathbf{p}$---`NumericalSensitivity` and `AnalyticSensitivity` classes. The `NumericalSensitivity` provider computes sensitivities automatically by perturbing parameters, while `AnalyticSensitivity` allows you to supply analytical derivatives for better performance. When you know the analytical form of $\partial \mathbf{f}/\partial \mathbf{p}$, use `AnalyticSensitivity` for better accuracy and performance. The example files below demonstrate both numerical and analytical approaches.


```python
import brahe as bh
import numpy as np


def dynamics_with_params(t, state, params):
    """Orbital dynamics with consider parameters.

    Args:
        t: Time
        state: [x, y, z, vx, vy, vz]
        params: [cd_area_m] - drag coefficient * area / mass
    """
    # Extract parameter
    cd_area_m = params[0]

    # Gravitational dynamics
    r = state[:3]
    v = state[3:]
    r_norm = np.linalg.norm(r)
    a_grav = -bh.GM_EARTH / (r_norm**3) * r

    # Atmospheric drag (simplified exponential model)
    h = r_norm - bh.R_EARTH
    rho0 = 1.225  # kg/m^3 at sea level
    H = 8500.0  # Scale height in meters
    rho = rho0 * np.exp(-h / H)

    v_norm = np.linalg.norm(v)
    a_drag = -0.5 * rho * cd_area_m * v_norm * v

    return np.concatenate([v, a_grav + a_drag])


def analytical_sensitivity(t, state, params):
    """Analytical sensitivity ∂f/∂p for drag parameter.

    Args:
        t: Time
        state: [x, y, z, vx, vy, vz]
        params: [cd_area_m]

    Returns:
        6x1 sensitivity matrix
    """
    r = state[:3]
    v = state[3:]
    r_norm = np.linalg.norm(r)

    # Atmospheric density
    h = r_norm - bh.R_EARTH
    rho0 = 1.225
    H = 8500.0
    rho = rho0 * np.exp(-h / H)

    v_norm = np.linalg.norm(v)

    # ∂(state_dot)/∂(cd_area_m)
    sens = np.zeros((6, 1))
    if v_norm > 0:
        # ∂(a_drag)/∂(cd_area_m) = -0.5 * rho * v_norm * v
        sens[3:6, 0] = -0.5 * rho * v_norm * v

    return sens


# Initial state (400 km LEO circular orbit)
oe = np.array([bh.R_EARTH + 250e3, 0.001, 51.6, 0.0, 0.0, 0.0])
state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

# Consider parameters
params = np.array([0.044])  # cd_area_m = Cd*A/m = 2.2*10/500

# Create numerical sensitivity provider (use class directly as constructor)
numerical_sens = bh.NumericalSensitivity(dynamics_with_params)

# Compute sensitivity matrix numerically
sens_numerical = numerical_sens.compute(0.0, state, params)

print("Numerical sensitivity (∂f/∂p):")
print(
    f"  Position rates: [{sens_numerical[0, 0]}, {sens_numerical[1, 0]}, {sens_numerical[2, 0]}]"
)
print(
    f"  Velocity rates: [{sens_numerical[3, 0]}, {sens_numerical[4, 0]}, {sens_numerical[5, 0]}]"
)

# Create analytical sensitivity provider
analytic_sens = bh.AnalyticSensitivity(analytical_sensitivity)

# Compute sensitivity matrix analytically
sens_analytical = analytic_sens.compute(0.0, state, params)

print("\nAnalytical sensitivity (∂f/∂p):")
print(
    f"  Position rates: [{sens_analytical[0, 0]}, {sens_analytical[1, 0]}, {sens_analytical[2, 0]}]"
)
print(
    f"  Velocity rates: [{sens_analytical[3, 0]}, {sens_analytical[4, 0]}, {sens_analytical[5, 0]}]"
)

# Compare numerical and analytical
diff = np.abs(sens_numerical - sens_analytical)
print(f"\nMax difference: {np.max(diff):.3e}")
```


### When to Use Analytical Sensitivity

Use analytical sensitivity when:

- Derivatives $\partial \mathbf{f}/\partial \mathbf{p}$ are simple to derive (e.g., drag coefficient, solar radiation pressure coefficient)
- Maximum accuracy is required (no finite difference errors)
- Sensitivity will be computed many times (performance critical)
- Working with well-understood parameter dependencies

**Recommendation**
For common parameters like atmospheric drag coefficient or solar radiation pressure coefficient, the analytical derivatives are often straightforward. When analytical forms are available, they provide better accuracy and performance than numerical approximations.

### Perturbation Strategies

The `NumericalSensitivity` provider uses the same perturbation strategies as `NumericalJacobian`:

- **Fixed perturbation**: Constant step size for all parameters
- **Percentage perturbation**: Scale by parameter magnitude
- **Adaptive perturbation**: Balance accuracy and robustness

See the [Jacobian Computation](../mathematics/jacobian.md#perturbation-strategies) guide for detailed information on configuring perturbation strategies.


## Integrating Sensitivity Matrices


```python
"""

import brahe as bh
import numpy as np


def dynamics_with_params(t, state, params):
    """Orbital dynamics with atmospheric drag.

    Args:
        t: Time
        state: [x, y, z, vx, vy, vz]
        params: [cd_area_m] - drag coefficient * area / mass
    """
    cd_area_m = params[0]

    r = state[:3]
    v = state[3:]
    r_norm = np.linalg.norm(r)
    a_grav = -bh.GM_EARTH / (r_norm**3) * r

    # Atmospheric drag (simplified exponential model)
    h = r_norm - bh.R_EARTH
    rho0 = 1.225  # kg/m^3 at sea level
    H = 8500.0  # Scale height in meters
    rho = rho0 * np.exp(-h / H)

    v_norm = np.linalg.norm(v)
    a_drag = -0.5 * rho * cd_area_m * v_norm * v

    return np.concatenate([v, a_grav + a_drag])


# Consider parameters
cd_area_m = 2.2 * 10.0 / 500.0  # Cd=2.2, A=10m^2, m=500kg
params = np.array([cd_area_m])
num_params = len(params)

# Create sensitivity provider using NumericalSensitivity
sensitivity_provider = bh.NumericalSensitivity.central(dynamics_with_params)

# Create Jacobian provider using NumericalJacobian
jacobian_provider = bh.NumericalJacobian.central(
    lambda t, s: dynamics_with_params(t, s, params)
)


def augmented_dynamics(t, aug_state):
    """Augmented dynamics for state + sensitivity matrix propagation.

    Propagates:
        dx/dt = f(t, x, p)
        dΦ/dt = (∂f/∂x) * Φ + (∂f/∂p)

    Args:
        t: Time
        aug_state: [state (6), vec(Φ) (6*num_params)]
    """
    state = aug_state[:6]
    phi = aug_state[6:].reshape(6, num_params)

    # State derivative
    state_dot = dynamics_with_params(t, state, params)

    # Compute Jacobian ∂f/∂x
    jacobian = jacobian_provider.compute(t, state)

    # Compute sensitivity ∂f/∂p
    sensitivity = sensitivity_provider.compute(t, state, params)

    # Sensitivity matrix derivative: dΦ/dt = J*Φ + S
    phi_dot = jacobian @ phi + sensitivity

    return np.concatenate([state_dot, phi_dot.flatten()])


# Initial state (200 km LEO for significant drag effects)
oe = np.array([bh.R_EARTH + 200e3, 0.001, 51.6, 0.0, 0.0, 0.0])
state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

# Initial sensitivity matrix (identity would mean we start with unit sensitivity,
# but we start with zero since we're interested in how sensitivity develops)
phi0 = np.zeros((6, num_params))

# Augmented initial state
aug_state = np.concatenate([state, phi0.flatten()])

# Create integrator for augmented system
# Using fixed step RK4 for simplicity and exact parity with Rust
aug_dim = 6 + 6 * num_params
config = bh.IntegratorConfig.fixed_step(1.0)
integrator = bh.RK4Integrator(aug_dim, augmented_dynamics, config=config)

# Propagate for 1 hour
t = 0.0
dt = 1.0
t_final = 3600.0

while t < t_final:
    aug_state = integrator.step(t, aug_state, dt)
    t += dt

# Extract final state and sensitivity matrix
final_state = aug_state[:6]
final_phi = aug_state[6:].reshape(6, num_params)

print(f"Final position after {t_final / 60:.0f} minutes:")
print(f"  x: {final_state[0] / 1000:.3f} km")
print(f"  y: {final_state[1] / 1000:.3f} km")
print(f"  z: {final_state[2] / 1000:.3f} km")

print("\nSensitivity matrix Φ = ∂x/∂p (position per unit Cd*A/m):")
print(f"  dx/dp: {final_phi[0, 0]:.3f} m/(m²/kg)")
print(f"  dy/dp: {final_phi[1, 0]:.3f} m/(m²/kg)")
print(f"  dz/dp: {final_phi[2, 0]:.3f} m/(m²/kg)")

print("\nSensitivity matrix Φ = ∂x/∂p (velocity per unit Cd*A/m):")
print(f"  dvx/dp: {final_phi[3, 0]:.6f} m/s/(m²/kg)")
print(f"  dvy/dp: {final_phi[4, 0]:.6f} m/s/(m²/kg)")
print(f"  dvz/dp: {final_phi[5, 0]:.6f} m/s/(m²/kg)")

# Interpret: If we have 10% uncertainty in Cd*A/m (0.1 * 0.044 = 0.0044),
# the position uncertainty after 1 hour would be:
delta_p = 0.1 * cd_area_m
pos_uncertainty = np.linalg.norm(final_phi[:3, 0]) * delta_p
print(f"\nPosition uncertainty for 10% parameter uncertainty: {pos_uncertainty:.1f} m")
```


## See Also

- [Variational Equations](variational_equations.md) - State Transition Matrix theory
- [Configuration Guide](configuration.md) - Integrator tuning
- [Jacobian Computation](../mathematics/jacobian.md) - Computing the A matrix