# Variational Equations and State Transition Matrix

Variational equations enable propagating not just the statye dynamics, but also how small perturbations would affect the state over time. They help relate how changes in state at one time map to changes at a later time which is critical for orbit determination and control.

## What are Variational Equations?

For a dynamical system $\dot{\mathbf{x}} = \mathbf{f}(t, \mathbf{x})$, variational equations describe how small deviations from the nominal trajectory evolve. Consider two nearby initial conditions:

- Nominal: $\mathbf{x}_0$
- Perturbed: $\mathbf{x}_0 + \delta\mathbf{x}_0$

The difference in trajectories can be approximated by the **State Transition Matrix** (STM) $\Phi(t, t_0)$:

$$\delta\mathbf{x}(t) \approx \Phi(t, t_0) \cdot \delta\mathbf{x}_0$$

This relationship is exact for linear systems and accurate for nonlinear systems when $||\delta\mathbf{x}_0||$ is small.

## The State Transition Matrix

The State Transition Matrix (STM) satisfies the **matrix differential equation**:

$$\dot{\Phi}(t, t_0) = \mathbf{J}(t, \mathbf{x}(t)) \cdot \Phi(t, t_0)$$

where $\mathbf{J}$ is the **Jacobian matrix** of the dynamics:

$$\mathbf{J}_{ij} = \frac{\partial f_i}{\partial x_j}$$

The STM has a few key properites. First, the intial condition of the STM is always the indentity matrix. That is:

$\Phi(t_0, t_0) = \mathbf{I}$ (identity matrix)

For linear systems: $\Phi(t, t_0)$ is the matrix exponential $e^{\mathbf{A}(t-t_0)}$.

## STM Propagation in Brahe

Brahe integrators can propagate the state and STM simultaneously using `step_with_varmat()`. What happens under the hood is:

1. The integrator advances both the state ($\mathbf{x}$) and the STM ($\Phi$) using the same time step
2. At each stage of the Runge-Kutta method, the Jacobian is evaluated at the current state
3. The variational equations $\dot{\Phi} = \mathbf{J} \cdot \Phi$ are integrated alongside the state equations
<!-- 4. Both are subject to the same error control and step size selection -->


```python
import brahe as bh
import numpy as np

# Initialize EOP
bh.initialize_eop()


# Define two-body dynamics
def dynamics(t, state):
    mu = bh.GM_EARTH
    r = state[0:3]
    v = state[3:6]
    r_norm = np.linalg.norm(r)
    a = -mu / r_norm**3 * r
    return np.concatenate([v, a])


# Create numerical Jacobian for variational equations
jacobian = bh.NumericalJacobian.central(dynamics).with_adaptive(
    scale_factor=1.0, min_value=1e-6
)

# Initial orbit (LEO)
r0 = np.array([bh.R_EARTH + 600e3, 0.0, 0.0])
v0 = np.array([0.0, 7.5e3, 0.0])
state0 = np.concatenate([r0, v0])

# Initial state transition matrix (identity)
phi0 = np.eye(6)

print("Integration with State Transition Matrix")
print(f"Initial orbit: {r0[0] / 1e3:.1f} km altitude")

# Create integrator with Jacobian
config = bh.IntegratorConfig.adaptive(abs_tol=1e-12, rel_tol=1e-11)
integrator = bh.DP54Integrator(6, dynamics, jacobian=jacobian, config=config)

# Propagate for one orbit period
t = 0.0
state = state0.copy()
phi = phi0.copy()
dt = 60.0

# Approximate orbital period
period = bh.orbital_period(np.linalg.norm(r0))

print("Time   Position STM[0,0]  Velocity STM[3,3]  Det(STM)")
print("-" * 60)

steps = 0
while t < period:
    # Propagate state and STM together (adaptive integrator returns 5-tuple)
    new_state, new_phi, dt_used, error_est, dt_next = integrator.step_with_varmat(
        t, state, phi, min(dt, period - t)
    )

    t += dt_used
    state = new_state
    phi = new_phi
    dt = dt_next
    steps += 1

    # Print progress
    if steps % 20 == 1:
        det_phi = np.linalg.det(phi)
        print(
            f"{t:6.0f}s    {phi[0, 0]:8.4f}      {phi[3, 3]:8.4f}        {det_phi:8.4f}"
        )

print(f"\nPropagation complete! ({steps} steps)")

# Example: Map initial position uncertainty to final uncertainty
print("\nExample: Uncertainty Propagation")
dx = 100.0
print(f"Initial position uncertainty: ±{dx} m in each direction")
delta_r0 = np.array([dx, dx, dx, 0.0, 0.0, 0.0])
delta_rf = phi @ delta_r0
print(
    f"Final position uncertainty: [{delta_rf[0]:.1f}, {delta_rf[1]:.1f}, {delta_rf[2]:.1f}] m"
)
print(
    f"Uncertainty growth: {np.linalg.norm(delta_rf[0:3]) / np.linalg.norm(delta_r0[0:3]):.1f}x"
)
```


## Equivalence to Direct Perturbation

The power of the STM is that it allows predicting many perturbed trajectories efficiently. Instead of integrating each perturbed initial condition separately, we can integrate the nominal trajectory once (with STM) and map any initial perturbation through the STM.

The following example demonstrates this equivalence:


```python
import brahe as bh
import numpy as np

# Initialize EOP
bh.initialize_eop()


# Define two-body orbital dynamics
def dynamics(t, state):
    """Two-body point-mass dynamics with Earth gravity."""
    mu = bh.GM_EARTH
    r = state[0:3]
    v = state[3:6]
    r_norm = np.linalg.norm(r)
    a = -mu / r_norm**3 * r
    return np.concatenate([v, a])


# Create numerical Jacobian for variational equations
jacobian = bh.NumericalJacobian.central(dynamics).with_fixed_offset(0.1)

# Configuration for high accuracy
config = bh.IntegratorConfig.adaptive(abs_tol=1e-12, rel_tol=1e-10)

# Create two integrators:
# 1. With Jacobian - propagates STM alongside state
integrator_nominal = bh.RKN1210Integrator(6, dynamics, jacobian=jacobian, config=config)

# 2. Without Jacobian - for direct perturbation integration
integrator_pert = bh.RKN1210Integrator(6, dynamics, config=config)

# Initial state: circular orbit at 500 km altitude
oe0 = np.array([bh.R_EARTH + 500e3, 0.0, 0.0, 0.0, 0.0, 0.0])
state0 = bh.state_koe_to_eci(oe0, bh.AngleFormat.DEGREES)

# Apply 10-meter perturbation in X direction
perturbation = np.array([10.0, 0.0, 0.0, 0.0, 0.0, 0.0])

# Integration parameters
total_time = 100.0  # Total propagation time (seconds)
num_steps = 10  # Number of steps
dt = total_time / num_steps

# Initialize states
state_nominal = state0.copy()
phi = np.eye(6)  # State Transition Matrix starts as identity
state_pert = state0 + perturbation

print("STM vs Direct Perturbation Comparison")
print("=" * 70)
print(f"Initial orbit: {(oe0[0] - bh.R_EARTH) / 1e3:.1f} km altitude (circular)")
print(f"Perturbation: {perturbation[0]:.1f} m in X direction")
print(f"Propagating for {total_time:.0f} seconds in {num_steps} steps\n")
print("Theory: For small δx₀, the perturbed state should satisfy:")
print("        x_pert(t) ≈ x_nominal(t) + Φ(t,t₀)·δx₀\n")
print("Step   Time(s)  ||Error||(m)  Max Component(m)  Relative Error")
print("-" * 70)

t = 0.0
for step in range(num_steps):
    # Propagate nominal trajectory with STM
    new_state_nominal, new_phi, dt_used, _, _ = integrator_nominal.step_with_varmat(
        t, state_nominal, phi, dt
    )

    # Propagate perturbed trajectory directly
    result_pert = integrator_pert.step(t, state_pert, dt)

    # Predict perturbed state using STM: x_pert ≈ x_nominal + Φ·δx₀
    state_pert_predicted = new_state_nominal + new_phi @ perturbation

    # Compute error between STM prediction and direct integration
    error = result_pert.state - state_pert_predicted
    error_norm = np.linalg.norm(error)
    error_max = np.max(np.abs(error))

    # Relative error compared to perturbation magnitude
    relative_error = error_norm / np.linalg.norm(perturbation)

    print(
        f"{step + 1:4d}  {t + dt_used:7.1f}  {error_norm:12.6f}  {error_max:16.6f}  {relative_error:13.6f}"
    )

    # Update for next step
    state_nominal = new_state_nominal
    phi = new_phi
    state_pert = result_pert.state
    t += dt_used
```


## See Also

- [Fixed Step Integration](fixed_step.md) - Constant time step methods
- [Adaptive Step Integration](adaptive_step.md) - Automatic step size control
- [Mathematics: Jacobian](../../library_api/mathematics/jacobian.md) - Jacobian provider API reference