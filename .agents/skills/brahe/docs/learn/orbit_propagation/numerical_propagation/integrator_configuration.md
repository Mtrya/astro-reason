# Integrator Configuration

The `NumericalPropagationConfig` controls the numerical integration method, step sizes, and error tolerances. Brahe provides preset configurations for common scenarios and allows custom configurations for specific requirements.

For API details, see the [NumericalPropagationConfig API Reference](../../../library_api/propagators/numerical_propagation_config.md). For detailed information about integrator theory and low-level usage, see the [Numerical Integration](../../integrators/index.md) guide.

## Full Example

Here is a complete example creating a `NumericalPropagationConfig` exercising all available configuration options:


```python
import brahe as bh

# Create a fully-configured integrator configuration
config = bh.NumericalPropagationConfig(
    # Integration method: Dormand-Prince 5(4)
    bh.IntegrationMethod.DP54,
    # Integrator settings: tolerances and step control
    bh.IntegratorConfig(
        abs_tol=1e-9,
        rel_tol=1e-6,
        initial_step=60.0,  # 60 second initial step
        min_step=1e-6,  # Minimum step size
        max_step=300.0,  # Maximum step size (5 minutes)
        step_safety_factor=0.9,  # Safety margin for step control
        min_step_scale_factor=0.2,  # Minimum step reduction
        max_step_scale_factor=10.0,  # Maximum step growth
        max_step_attempts=10,  # Max attempts per step
    ),
    # Variational configuration: STM and sensitivity settings
    bh.VariationalConfig(
        enable_stm=True,
        enable_sensitivity=False,
        store_stm_history=True,
        store_sensitivity_history=False,
    ),
)

print(f"Method: {config.method}")
print(f"abs_tol: {config.abs_tol}")
print(f"rel_tol: {config.rel_tol}")
print(f"Variational: {config.variational}")
```


## Architecture Overview

### Configuration Hierarchy

`NumericalPropagationConfig` is the top-level container that aggregates all integrator settings. Each component has its own configuration struct:

```.no-linenums
NumericalPropagationConfig
├── method: IntegratorMethod
│   ├── RK4 (fixed step)
│   ├── RKF45 (adaptive)
│   ├── DP54 (adaptive, default)
│   └── RKN1210 (adaptive, high precision)
├── integrator: IntegratorConfig
│   ├── abs_tol, rel_tol
│   ├── initial_step, min_step, max_step
│   ├── step_safety_factor
│   ├── min/max_step_scale_factor
│   └── fixed_step_size (for RK4)
└── variational: VariationalConfig
    ├── enable_stm, enable_sensitivity
    ├── store_stm_history, store_sensitivity_history
    └── jacobian_method, sensitivity_method
```

The configuration is captured at propagator construction time and remains immutable during propagation.

## Integration Methods

Four integration methods are available:

| Method | Order | Adaptive | Function Evals | Description |
|------|-----|--------|--------------|-----------|
| RK4 | 4 | No | 4 | Classic fixed-step Runge-Kutta |
| RKF45 | 4(5) | Yes | 6 | Runge-Kutta-Fehlberg adaptive |
| DP54 | 5(4) | Yes | 6-7 | Dormand-Prince (MATLAB ode45) |
| RKN1210 | 12(10) | Yes | 17 | High-precision Runge-Kutta-Nystrom |

### RK4 (Fixed Step)

Classic 4th-order Runge-Kutta with fixed step size. No error control - requires careful step size selection.


```python
import brahe as bh

# RK4: Fixed-step 4th-order Runge-Kutta
config = bh.NumericalPropagationConfig(
    bh.IntegrationMethod.RK4,
    bh.IntegratorConfig.fixed_step(60.0),  # 60 second fixed steps
    bh.VariationalConfig(),
)

print(f"Method: {config.method}")
```


### DP54 (Default)

Dormand-Prince 5(4) adaptive method. Uses FSAL (First-Same-As-Last) optimization for efficiency. MATLAB's `ode45` uses this method.


```python
import brahe as bh

# DP54: Dormand-Prince 5(4) - the default integrator
config = bh.NumericalPropagationConfig.default()

# Customize tolerances using builder pattern
config_tight = (
    bh.NumericalPropagationConfig.default().with_abs_tol(1e-9).with_rel_tol(1e-6)
)

print(f"Method: {config.method}")
print(f"abs_tol: {config.abs_tol}")
print(f"rel_tol: {config.rel_tol}")
```


### RKN1210 (High Precision)

12th-order Runge-Kutta-Nystrom optimized for second-order ODEs like orbital mechanics. Achieves extreme accuracy with tight tolerances.


```python
import brahe as bh

# RKN1210: High-order adaptive integrator for maximum precision
config = bh.NumericalPropagationConfig.high_precision()

# Or manually configure with custom tolerances
config_custom = (
    bh.NumericalPropagationConfig.with_method(bh.IntegrationMethod.RKN1210)
    .with_abs_tol(1e-12)
    .with_rel_tol(1e-10)
)

print(f"Method: {config.method}")
print(f"abs_tol: {config.abs_tol}")
print(f"rel_tol: {config.rel_tol}")
```


## Error Tolerances

Adaptive integrators adjust step size to keep error within:

$$
\text{error} < \text{abs\_tol} + \text{rel\_tol} \times |\text{state}|
$$

- **`abs_tol`**: Bounds error when state components are small (default: 1e-6)
- **`rel_tol`**: Bounds error proportional to state magnitude (default: 1e-3)


```python
import brahe as bh

# Different tolerance levels for various use cases
config_quick = (
    bh.NumericalPropagationConfig.default().with_abs_tol(1e-3).with_rel_tol(1e-1)
)
config_standard = bh.NumericalPropagationConfig.default()  # abs=1e-6, rel=1e-3
config_precision = (
    bh.NumericalPropagationConfig.default().with_abs_tol(1e-9).with_rel_tol(1e-6)
)
config_maximum = bh.NumericalPropagationConfig.high_precision()  # abs=1e-10, rel=1e-8

print(f"Quick:     abs={config_quick.abs_tol}, rel={config_quick.rel_tol}")
print(f"Standard:  abs={config_standard.abs_tol}, rel={config_standard.rel_tol}")
print(f"Precision: abs={config_precision.abs_tol}, rel={config_precision.rel_tol}")
print(f"Maximum:   abs={config_maximum.abs_tol}, rel={config_maximum.rel_tol}")
```


## Customizing Configuration

### Python Builder Pattern

Python supports method chaining to customize from a preset:


```python
import brahe as bh

# Chain with_* methods to customize from a preset
config = (
    bh.NumericalPropagationConfig.default()
    .with_abs_tol(1e-9)
    .with_rel_tol(1e-6)
    .with_max_step(300.0)
    .with_initial_step(60.0)
)

print(f"Method: {config.method}")
print(f"abs_tol: {config.abs_tol}")
print(f"rel_tol: {config.rel_tol}")
```

### Rust Struct Syntax

In Rust, use struct update syntax (`..`) to customize from defaults:


## Preset Configurations

Brahe provides preset configurations for common use cases:

| Preset | Method | abs_tol | rel_tol | Description |
|------|------|-------|-------|-----------|
| `default()` | DP54 | 1e-6 | 1e-3 | General purpose |
| `high_precision()` | RKN1210 | 1e-10 | 1e-8 | Maximum accuracy |
| `with_method(M)` | M | 1e-6 | 1e-3 | Custom method with defaults |


```python
import brahe as bh

# Preset configurations for common use cases
default = bh.NumericalPropagationConfig.default()
high_precision = bh.NumericalPropagationConfig.high_precision()
rkf45 = bh.NumericalPropagationConfig.with_method(bh.IntegrationMethod.RKF45)
rk4 = bh.NumericalPropagationConfig.with_method(bh.IntegrationMethod.RK4)

print(f"default():        {default.method}")
print(f"high_precision(): {high_precision.method}")
print(f"with_method(RKF45): {rkf45.method}")
print(f"with_method(RK4):   {rk4.method}")
```


## Variational Equations

The propagator can optionally integrate variational equations to compute the State Transition Matrix (STM) and sensitivity matrices. This is enabled via `VariationalConfig`:

- **`enable_stm`**: Compute the State Transition Matrix
- **`enable_sensitivity`**: Compute parameter sensitivity matrix
- **`store_*_history`**: Store matrices at output times in trajectory
- **`jacobian_method`/`sensitivity_method`**: Finite difference method (Forward, Backward, Central)

The STM maps initial state perturbations to final state perturbations: $\delta\mathbf{x}(t) = \Phi(t, t_0) \cdot \delta\mathbf{x}(t_0)$

See [Covariance and Sensitivity](covariance_sensitivity.md) for detailed usage.

---

## See Also

- [Numerical Propagation Overview](index.md) - Architecture and concepts
- [Force Models](force_models.md) - Configuring force models
- [Covariance and Sensitivity](covariance_sensitivity.md) - Variational equations
- [Integrators](../../integrators/index.md) - Detailed integrator documentation
- [NumericalPropagationConfig API Reference](../../../library_api/propagators/numerical_propagation_config.md)