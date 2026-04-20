# Jacobian Computation

Jacobian matrices are fundamental to many advanced astrodynamics computations. This guide explains how to compute and use Jacobians in Brahe for both analytical and numerical approaches.

## Understanding Jacobians

A Jacobian matrix describes how a function's outputs change with respect to changes in its inputs. For a vector function $\mathbf{f}: \mathbb{R}^n \rightarrow \mathbb{R}^n$ that maps state $\mathbf{x}$ to derivative $\dot{\mathbf{x}}$:

$$\dot{\mathbf{x}} = \mathbf{f}(t, \mathbf{x})$$

The Jacobian matrix $\mathbf{J}$ is:

$$J_{ij} = \frac{\partial f_i}{\partial x_j}$$

$\mathbf{J}$ is a real-valued $n \times n$ matrix ($J \in \mathbb{R}^{n \times n}$). In astrodynamics, this describes how the rate of change of each state component depends on all other state components.

In astrodynamics, Jacobians are crucial for:

- **State Transition Matrices**: Describing how small changes in initial conditions affect future states
- **Orbit Determination**: Propagating covariance matrices and computing measurement sensitivities
- **Trajectory Optimization**: Computing gradients for optimization algorithms
- **Uncertainty Propagation**: Tracking how uncertainties (covariances) evolve over time

### Analytical vs. Numerical Jacobians

Brahe supports both analytical and numerical Jacobian computation. Analytical Jacobians, represented by the `AnalyticJacobian` class require you to provide closed-form derivative expressions, while numerical Jacobians, provided by `NumericalJacobian` use finite difference methods to approximate derivatives automatically when given only the dynamics function.

## Analytical Jacobians

When you know the closed-form derivatives $\frac{\partial f_i}{\partial x_j}$, analytical Jacobians provide the most accurate and efficient computation.

### Simple Harmonic Oscillator Example

For a simple example, let's consider a 2D harmonic oscillator with state vector $\mathbf{x} = \begin{bmatrix} x \\ v \end{bmatrix}$ where $x$ is position and $v$ is velocity. The dynamics are:

$$\begin{bmatrix}
\dot{x} \\
\dot{v}
\end{bmatrix} = \begin{bmatrix}
v \\
-x
\end{bmatrix}$$

The analytical Jacobian is:

$$\mathbf{J} = \begin{bmatrix}
0 & 1 \\
-1 & 0
\end{bmatrix}$$

We can implement this analytical Jacobian in Brahe as follows:


```python
import brahe as bh
import numpy as np


# Define dynamics: Simple harmonic oscillator
# State: [position, velocity]
# Dynamics: dx/dt = v, dv/dt = -x
def dynamics(t, state):
    return np.array([state[1], -state[0]])


# Define analytical Jacobian
# J = [[0,  1],
#      [-1, 0]]
def jacobian_func(t, state):
    return np.array([[0.0, 1.0], [-1.0, 0.0]])


# Create analytical Jacobian provider
jacobian = bh.AnalyticJacobian(jacobian_func)

# Compute Jacobian at a specific state
t = 0.0
state = np.array([1.0, 0.0])
J = jacobian.compute(t, state)

print("Analytical Jacobian:")
print(J)
t2 = 10.0
state2 = np.array([0.5, 0.866])
J2 = jacobian.compute(t2, state2)

print("\nJacobian at different time and state:")
print(J2)
# Should be identical for linear system

print("\nJacobians are equal:", np.allclose(J, J2))
```


### When to Use Analytical Jacobians

- Derivatives are simple to compute (e.g., linear systems, Keplerian dynamics)
- Maximum accuracy is required (no finite difference errors)
- Jacobian will be evaluated many times (performance critical)
- Working with well-studied systems (two-body problem, etc.)

## Numerical Jacobians

Numerical Jacobians use finite differences to approximate derivatives automatically. This is essential when analytical derivatives are complex or unknown. Brahe supports three difference methods: forward, central, and backward differences.

#### Forward Difference

The forward difference method approximates the derivative by perturbing the input state positively along each dimension $e_j$ and measuring the change in output, as follows:

$$
J_{ij} \approx \frac{f_i(\mathbf{x} + h \cdot \mathbf{e}_j) - f_i(\mathbf{x})}{h}
$$

Forward differences have first-order accuracy with an error on the order of $O(h)$, where $h$ is the perturbation size. This method requires $n + 1$ function evaluations for an $n$-dimensional state vector.

#### Central Difference

The central difference method improves accuracy by perturbing the input state both positively and negatively along each dimension $e_j$:

$$
J_{ij} \approx \frac{f_i(\mathbf{x} + h \cdot \mathbf{e}_j) - f_i(\mathbf{x} - h \cdot \mathbf{e}_j)}{2h}
$$

Central differences have second-order accuracy with an error on the order of $O(h^2)$. This method requires $2n$ function evaluations for an $n$-dimensional state vector.

**Recommendation**
Use central differences unless computational cost is prohibitive. The ~2x increase in function evaluations is usually worth the improved accuracy.

#### Backward Difference

Finally, the backward difference method approximates the derivative by perturbing the input state negatively along each dimension:

$$
J_{ij} \approx \frac{f_i(\mathbf{x}) - f_i(\mathbf{x} - h \cdot \mathbf{e}_j)}{h}
$$

Similar to forward differences, backward differences have first-order accuracy with an error on the order of $O(h)$ and require $n + 1$ function evaluations. They are less commonly used but implemented for completeness.

### Basic Numerical Jacobian

We can implement the same 2D harmonic oscillator example using a numerical Jacobian with central differences:


```python
import brahe as bh
import numpy as np


# Define dynamics: Simple harmonic oscillator
def dynamics(t, state):
    return np.array([state[1], -state[0]])


# Create numerical Jacobian with default settings (central differences)
jacobian = bh.NumericalJacobian(dynamics)

# Compute Jacobian at a specific state
t = 0.0
state = np.array([1.0, 0.0])
J_numerical = jacobian.compute(t, state)

print("Numerical Jacobian (central differences):")
print(J_numerical)

# Compare with analytical solution
J_analytical = np.array([[0.0, 1.0], [-1.0, 0.0]])

error = np.linalg.norm(J_numerical - J_analytical)
print(f"\nError vs analytical: {error:.2e}")

# Verify accuracy at different state
state2 = np.array([0.5, 0.866])
J_numerical2 = jacobian.compute(t, state2)

print("\nNumerical Jacobian at different state:")
print(J_numerical2)

error2 = np.linalg.norm(J_numerical2 - J_analytical)
print(f"Error vs analytical: {error2:.2e}")
```


## Comparing Methods


```python
import brahe as bh
import numpy as np


# Define two-body gravity dynamics: state = [x, y, z, vx, vy, vz]
def gravity_dynamics(t, state):
    r = state[0:3]  # Position
    v = state[3:6]  # Velocity
    r_norm = np.linalg.norm(r)

    # Acceleration from two-body gravity: a = -mu * r / |r|^3
    a = -bh.GM_EARTH * r / r_norm**3

    return np.concatenate([v, a])


# Analytical Jacobian for two-body gravity
def analytical_jacobian(state):
    r = state[0:3]
    r_norm = np.linalg.norm(r)
    r3 = r_norm**3
    r5 = r_norm**5

    # Top-left: zeros (3x3)
    # Top-right: identity (3x3)
    # Bottom-left: gravity gradient (3x3)
    # Bottom-right: zeros (3x3)
    J = np.zeros((6, 6))
    J[0:3, 3:6] = np.eye(3)  # Velocity contribution to position derivative

    # Gravity gradient term - Motenbruck Eqn 7.56
    J[3:6, 0:3] = -bh.GM_EARTH * (np.eye(3) / r3 - 3 * np.outer(r, r) / r5)

    return J


# Create numerical Jacobians with different methods
jacobian_forward = bh.NumericalJacobian.forward(gravity_dynamics)
jacobian_central = bh.NumericalJacobian.central(gravity_dynamics)
jacobian_backward = bh.NumericalJacobian.backward(gravity_dynamics)

# Test state: Low Earth Orbit position and velocity
t = 0.0
state = np.array([bh.R_EARTH + 500e3, 0.0, 0.0, 0.0, 7500.0, 0.0])  # Circular orbit

# Compute analytical Jacobian
J_analytical = analytical_jacobian(state)

# Compute Jacobians with each method
J_forward = jacobian_forward.compute(t, state)
J_central = jacobian_central.compute(t, state)
J_backward = jacobian_backward.compute(t, state)

print("Forward Difference Jacobian:")
for row in J_forward:
    print("[" + "  ".join(f"{val: .2e}" for val in row) + "]")
error_forward = np.linalg.norm(J_forward - J_analytical)
print(f"Error: {error_forward:.2e}\n")

print("Central Difference Jacobian:")
for row in J_central:
    print("[" + "  ".join(f"{val: .2e}" for val in row) + "]")
error_central = np.linalg.norm(J_central - J_analytical)
print(f"Error: {error_central:.2e}\n")

print("Backward Difference Jacobian:")
for row in J_backward:
    print("[" + "  ".join(f"{val: .2e}" for val in row) + "]")
error_backward = np.linalg.norm(J_backward - J_analytical)
print(f"Error: {error_backward:.2e}\n")

# Summary
print("Accuracy Comparison:")
print(f"  Forward:  {error_forward:.2e} (O(h))")
print(f"  Central:  {error_central:.2e} (O(h²))")
print(f"  Backward: {error_backward:.2e} (O(h))")
print(f"\nCentral is {error_forward / error_central:.1f}x more accurate than forward")
print(f"Central is {error_backward / error_central:.1f}x more accurate than backward")
```


## Perturbation Strategies

The choice of perturbation size $h$ significantly affects numerical Jacobian accuracy. Too large does not provide an accurate approximation of the local derivative; too small causes roundoff errors. Brahe provides several perturbation strategies to provide options for choosing $h$. However it is ultimately up to the user to select the best strategy for their specific application.

### Fixed Perturbation

One simple approach is to use a fixed perturbation size for all state components. This generally works well when all state components have similar magnitudes.

$$
h = \text{constant}
$$

```
jacobian = bh.NumericalJacobian.central(dynamics) \\
    .with_fixed_offset(1e-6)
```

### Percentage Perturbation

Another approach is to use a percentage of each state component's magnitude as the perturbation size.

$$
h_j = \text{percentage} \times |x_j|
$$

```
jacobian = bh.NumericalJacobian.central(dynamics) \\
    .with_percentage(1e-5)  # 0.001% perturbation
```

### Adaptive Perturbation

The adaptive perturbation strategy combines both absolute and relative scaling to choose an appropriate perturbation size for each state component. It multiples the component scale factor $s$ by $\sqrt(\epsilon)$ where $\espilon$ is machine epsilon for double precision ($\approx 2.22e-16$) and enforces a minimum value $h_{min}$ to avoid excessively small perturbations.

$$
h_j = s \times \sqrt(\epsilon) \times \max(|x_j|, h_{min})
$$

```
jacobian = bh.NumericalJacobian.central(dynamics) \\
    .with_adaptive(scale_factor=1e-8, min_value=1e-6)
```

**Recommendation**
Adaptive perturbation is will generally best choice for most applications, as it balances accuracy and robustness across a wide range of state magnitudes, but percentage-based perturbations can also work well without much tuning.

### Comparing Strategies


```python
import brahe as bh
import numpy as np


# Define dynamics with mixed-scale state
# State: [large_position (km), small_velocity (km/s)]
def dynamics(t, state):
    # Simple dynamics with different scales
    x, v = state
    return np.array([v, -x * 1e-6])  # Different scales


# Analytical Jacobian
def analytical_jacobian(t, state):
    return np.array([[0.0, 1.0], [-1e-6, 0.0]])


# Test state with very different magnitudes
state = np.array([7000.0, 7.5])  # Position in km, velocity in km/s
t = 0.0

J_analytical = analytical_jacobian(t, state)

print("Testing perturbation strategies on mixed-scale state:")
print(f"State: position={state[0]} km, velocity={state[1]} km/s\n")

# Strategy 1: Fixed perturbation
print("1. Fixed Perturbation (h = 1e-6)")
jacobian_fixed = bh.NumericalJacobian.central(dynamics).with_fixed_offset(1e-6)
J_fixed = jacobian_fixed.compute(t, state)
error_fixed = np.linalg.norm(J_fixed - J_analytical)
print(f"   Error: {error_fixed:.2e}\n")

# Strategy 2: Percentage perturbation
print("2. Percentage Perturbation (0.001%)")
jacobian_pct = bh.NumericalJacobian.central(dynamics).with_percentage(1e-5)
J_pct = jacobian_pct.compute(t, state)
error_pct = np.linalg.norm(J_pct - J_analytical)
print(f"   Error: {error_pct:.2e}\n")

# Strategy 3: Adaptive perturbation (recommended)
print("3. Adaptive Perturbation (scale=1.0, min=1.0)")
jacobian_adaptive = bh.NumericalJacobian.central(dynamics).with_adaptive(
    scale_factor=1.0, min_value=1.0
)
J_adaptive = jacobian_adaptive.compute(t, state)
error_adaptive = np.linalg.norm(J_adaptive - J_analytical)
print(f"   Error: {error_adaptive:.2e}\n")

# Summary
print("Strategy Comparison:")
print(f"  Fixed:      {error_fixed:.2e}")
print(f"  Percentage: {error_pct:.2e}")
print(f"  Adaptive:   {error_adaptive:.2e}")
print("\nBest strategy: Adaptive (handles mixed scales robustly)")

# Test with state component near zero
print("\n" + "=" * 60)
print("Testing with component near zero:")
state_zero = np.array([7000.0, 1e-9])  # Very small velocity
print(f"State: position={state_zero[0]} km, velocity={state_zero[1]} km/s\n")

J_analytical_zero = analytical_jacobian(t, state_zero)

# Percentage fails when component is near zero
try:
    J_pct_zero = jacobian_pct.compute(t, state_zero)
    error_pct_zero = np.linalg.norm(J_pct_zero - J_analytical_zero)
    print(f"Percentage: Error = {error_pct_zero:.2e}")
except ZeroDivisionError:
    print("Percentage: FAILED (division by near-zero)")

# Adaptive handles it gracefully
J_adaptive_zero = jacobian_adaptive.compute(t, state_zero)
error_adaptive_zero = np.linalg.norm(J_adaptive_zero - J_analytical_zero)
print(f"Adaptive:   Error = {error_adaptive_zero:.2e}")

print("\nConclusion: Adaptive perturbation is most robust")
```


## Using with Integrators

Jacobians are primarily used with numerical integrators for variational equation propagation see the [Numerical Integration](../integrators/index.md) guide for more details.

## See Also

- **[Mathematics Module](index.md)** - Mathematics module overview
- **[Jacobian API Reference](../../library_api/mathematics/jacobian.md)** - Complete API documentation
- **[Numerical Integration](../integrators/index.md)** - Using Jacobians with integrators