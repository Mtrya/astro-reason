# Fixed-Step Integrators

Fixed-step integrators use a constant time step throughout the integration. Unlike adaptive methods, they don't automatically adjust step size based on error estimates. They are simpler to implement and have predictable computational costs, but require careful step size selection to ensure accuracy. They provide regular output at fixed intervals, making them suitable for applications needing uniform sampling.

## RK4: Classical Runge-Kutta

Brahe implements the classical 4th-order Runge-Kutta (RK4) method as it's primary fixed-step integrator. The 4th-order Runge-Kutta method (RK4) is the most popular fixed-step integrator, offering an excellent balance of accuracy and simplicity.

### Algorithm

For $\dot{\mathbf{x}} = \mathbf{f}(t, \mathbf{x})$, the RK4 method computes:

$$\begin{align}
\mathbf{k}_1 &= \mathbf{f}(t, \mathbf{x}) \\
\mathbf{k}_2 &= \mathbf{f}(t + h/2, \mathbf{x} + h\mathbf{k}_1/2) \\
\mathbf{k}_3 &= \mathbf{f}(t + h/2, \mathbf{x} + h\mathbf{k}_2/2) \\
\mathbf{k}_4 &= \mathbf{f}(t + h, \mathbf{x} + h\mathbf{k}_3)
\end{align}$$

The next state is then given by:

$$\mathbf{x}(t + h) = \mathbf{x}(t) + \frac{h}{6}(\mathbf{k}_1 + 2\mathbf{k}_2 + 2\mathbf{k}_3 + \mathbf{k}_4)$$

## Choosing Step Size

The step size h must balance accuracy and computational cost. Too large causes unacceptable errors; too small wastes computation. A decent starting point is to relate h to the characteristic time scale of the dynamics. For orbital dynamics, a common heuristic is 

$$
h \approx \frac{T}{100 \text{ \textemdash } 1000}
$$

where T is the orbital period.

Since fixed-step methods lack automatic error control, it is critical to validate that the step-size choice achieves the desired level of accuracy. Common validation approaches include:

1. **Analytical solution**: Compare against closed-form solution (when available)
2. **Step Size Comparison**: Run with both $h$ and $h/2$, compare results to confirm convergence
3. **Energy/momentum conservation**: If you have a conserative system (in astrodynamics, this would be a gravitional-only system), check that total energy and angular momentum remain constant over time.
4. **Reference integrator**: Compare against adaptive integrator with tight tolerances

### Basic Integration Example

The following example demonstrates using the RK4 fixed-step integrator to  integrate a simple harmonic oscillator.


```python
import brahe as bh
import numpy as np

# Define simple harmonic oscillator
omega = 1.0


def dynamics(t, state):
    x, v = state
    return np.array([v, -(omega**2) * x])


# Analytical solution
def analytical(t, x0=1.0, v0=0.0):
    x = x0 * np.cos(omega * t) + (v0 / omega) * np.sin(omega * t)
    v = -omega * x0 * np.sin(omega * t) + v0 * np.cos(omega * t)
    return np.array([x, v])


# Initial conditions
state0 = np.array([1.0, 0.0])
t_end = 4 * np.pi  # Two periods

print("RK4 Fixed-Step Integration Demonstration")
print("System: Simple Harmonic Oscillator (ω=1.0)")
print(f"Integration time: 0 to {t_end:.2f} (2 periods)\n")

# Test different step sizes
step_sizes = [0.5, 0.2, 0.1, 0.05]

for dt in step_sizes:
    config = bh.IntegratorConfig.fixed_step(step_size=dt)
    integrator = bh.RK4Integrator(2, dynamics, config=config)

    t = 0.0
    state = state0.copy()
    steps = 0

    # Integrate to end
    while t < t_end - 1e-10:
        state = integrator.step(t, state, dt)
        t += dt
        steps += 1

    # Compare with analytical solution
    exact = analytical(t)
    error = np.linalg.norm(state - exact)

    print(f"Step size dt={dt:5.2f}:")
    print(f"  Steps:      {steps}")
    print(f"  Final state: [{state[0]:.6f}, {state[1]:.6f}]")
    print(f"  Exact:       [{exact[0]:.6f}, {exact[1]:.6f}]")
    print(f"  Error:       {error:.2e}")
    print()
```


## See Also

- **[Adaptive-Step Integrators](adaptive_step.md)** - For automatic error control
- **[Configuration Guide](configuration.md)** - Detailed configuration options
- **[RK4 API Reference](../../library_api/integrators/rk4.md)** - Complete RK4 documentation
- **[Integrators Overview](index.md)** - Comparison of all integrators