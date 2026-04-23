# Integrator Configuration

Proper integrator configuration is essential for balancing accuracy, performance, and reliability. This guide explains all configuration parameters and how to choose appropriate values.

## IntegratorConfig Class

The [`IntegratorConfig`](../../library_api/integrators/config.md) class encapsulates all settings for adaptive-step integrators. Key parameters include:

- **Error Tolerances**: `abs_tol`, `rel_tol`
- **Step Size Limits**: `min_step`, `max_step`
- **Step Size Control**: `step_safety_factor`, `min_step_scale_factor`, `max_step_scale_factor`
- **Maximum Step Attempts**: `max_step_attempts`

## Configuration Parameters

### Error Tolerances

**`abs_tol`** (float): Absolute error tolerance

- Controls maximum absolute error allowed per step
- Units match state units (meters for position, m/s for velocity)
- Prevents excessively small steps when state approaches zero

**`rel_tol`** (float): Relative error tolerance

- Controls maximum relative error as fraction of state magnitude
- Dimensionless
- Scales with state magnitude

**Combined tolerance:**

$$\text{tol}_i = \text{abs\_tol} + \text{rel\_tol} \times |x_i|$$

### Step Size Limits

**`min_step`** (float): Minimum allowed step size (seconds)

- Safety limit preventing infinitesimally small steps
- If integrator hits this limit repeatedly, tolerances may be too tight

**`max_step`** (float): Maximum allowed step size (seconds)

- Prevents missing important dynamics by taking too-large steps
- Critical for problems with events or discontinuities

### Step Size Control

**`step_safety_factor`** (float): Safety margin for step size adjustment

- Multiplier applied to calculated optimal step size
- Makes step size more conservative
- Default: 0.9 (use 90% of optimal)
- Range: 0.8 to 0.95

**Formula:**

$$
h_{\text{new}} = \text{safety\_factor} \times h \times \left(\frac{\text{tol}}{\varepsilon}\right)^{1/p}
$$

Decreasing the safety factor results in smaller steps and higher accuracy but more function evaluations. Increasing it yields larger steps and faster performance but risks exceeding error tolerances and more rejections, which in turn results in wasted computation.

**`min_step_scale_factor`** (float): Minimum step size change ratio

- Prevents dramatic step size reductions
- Ensures step doesn't shrink too rapidly
- Default: 0.2 (can shrink to 20% of current)

**`max_step_scale_factor`** (float): Maximum step size change ratio

- Prevents dramatic step size increases
- Ensures gradual adaptation
- Default: 10.0 (can grow to 10× current)

**Why limit step changes:**
- Prevents oscillating step sizes
- Smooths adaptation

### Step Attempts

**`max_step_attempts`** (int): Maximum retry attempts before error

- If step rejected more than this many times, raise error
- Prevents infinite loops with pathological problems
- Default: 10

**Typical causes of many rejections:**
1. Tolerances too tight for integrator order
2. Stiff differential equations
3. Discontinuity in dynamics
4. Bug in dynamics function

## Configuration Examples

These examples illustrate different parameter combinations representing different points on the accuracy-performance spectrum:

### Conservative Configuration

Tight tolerances and restrictive step size controls:


```python
# /// script
# dependencies = ["brahe", "numpy"]
# ///
"""
Examples of different integrator configurations for various scenarios.

This example shows how to configure integrators for different accuracy,
performance, and reliability requirements.
"""

import brahe as bh
import numpy as np

# Initialize EOP
bh.initialize_eop()


# Define orbital dynamics
def dynamics(t, state):
    mu = bh.GM_EARTH
    r = state[0:3]
    v = state[3:6]
    r_norm = np.linalg.norm(r)
    a = -mu / r_norm**3 * r
    return np.concatenate([v, a])


# LEO orbit initial state
r0 = np.array([bh.R_EARTH + 600e3, 0.0, 0.0])
v0 = np.array([0.0, 7.5e3, 0.0])
state0 = np.concatenate([r0, v0])
period = 2 * np.pi * np.sqrt(np.linalg.norm(r0) ** 3 / bh.GM_EARTH)

print("Integrator Configuration Examples\n")
print("=" * 70)

# Example 1: Conservative (High Reliability)
print("\n1. CONSERVATIVE Configuration (Mission-Critical)")
print("-" * 70)

# --8<-- [start:conservative]
conservative_config = bh.IntegratorConfig(
    abs_tol=1e-12,
    rel_tol=1e-11,
    min_step=0.01,
    max_step=100.0,
    step_safety_factor=0.85,  # More conservative
    min_step_scale_factor=0.3,
    max_step_scale_factor=5.0,  # Limit step growth
    max_step_attempts=15,
)
# --8<-- [end:conservative]

print(f"  abs_tol: {conservative_config.abs_tol:.0e}")
print(f"  rel_tol: {conservative_config.rel_tol:.0e}")
print(f"  max_step: {conservative_config.max_step:.0f} s")
print(f"  safety_factor: {conservative_config.step_safety_factor}")
print("  Use case: Critical operations, high-precision ephemeris")

# Example 2: Balanced (Recommended Default)
print("\n2. BALANCED Configuration (Recommended)")
print("-" * 70)
# --8<-- [start:balanced]
balanced_config = bh.IntegratorConfig.adaptive(abs_tol=1e-10, rel_tol=1e-9)
# --8<-- [end:balanced]

print(f"  abs_tol: {balanced_config.abs_tol:.0e}")
print(f"  rel_tol: {balanced_config.rel_tol:.0e}")
print(f"  max_step: {balanced_config.max_step:.0e} s")
print(f"  safety_factor: {balanced_config.step_safety_factor}")
print("  Use case: Most applications, ~1-10m accuracy")

# Example 3: Aggressive (High Performance)
print("\n3. AGGRESSIVE Configuration (Fast Computation)")
print("-" * 70)
# --8<-- [start:aggressive]
aggressive_config = bh.IntegratorConfig(
    abs_tol=1e-8,
    rel_tol=1e-7,
    initial_step=60.0,
    min_step=1.0,
    max_step=1000.0,  # Large steps allowed
    step_safety_factor=0.95,  # Less conservative
    min_step_scale_factor=0.1,
    max_step_scale_factor=15.0,  # Allow rapid growth
    max_step_attempts=8,
)
# --8<-- [end:aggressive]

print(f"  abs_tol: {aggressive_config.abs_tol:.0e}")
print(f"  rel_tol: {aggressive_config.rel_tol:.0e}")
print(f"  max_step: {aggressive_config.max_step:.0f} s")
print(f"  safety_factor: {aggressive_config.step_safety_factor}")
print("  Use case: Fast trajectory analysis, ~10-100m accuracy")

# Example 4: High Precision (RKN1210)
print("\n4. HIGH PRECISION Configuration (Sub-meter)")
print("-" * 70)
# --8<-- [start:high_precision_config]
high_precision_config = bh.IntegratorConfig(
    abs_tol=1e-14,
    rel_tol=1e-13,
    min_step=0.001,
    max_step=200.0,
    step_safety_factor=0.9,
    min_step_scale_factor=0.2,
    max_step_scale_factor=10.0,
    max_step_attempts=12,
)
# --8<-- [end:high_precision_config]

print(f"  abs_tol: {high_precision_config.abs_tol:.0e}")
print(f"  rel_tol: {high_precision_config.rel_tol:.0e}")
print(f"  max_step: {high_precision_config.max_step:.0f} s")
print(f"  safety_factor: {high_precision_config.step_safety_factor}")
print("  Use case: High-precision orbit determination, <1m accuracy")
print("  Requires: RKN1210 integrator")

# Example 5: Fixed-Step Configuration
print("\n5. FIXED-STEP Configuration")
print("-" * 70)
fixed_config = bh.IntegratorConfig.fixed_step(step_size=60.0)

print(f"  step_size: {60.0} s")
print("  Note: Step size can be overridden with dt parameter in integrator.step()")
print("  Use case: Regular output intervals, predictable cost")

print("\n" + "=" * 70)
print("\nRecommendations:")
print("• Start with BALANCED for most applications")
print("• Use CONSERVATIVE for mission-critical operations")
print("• Use AGGRESSIVE only when accuracy can be sacrificed for speed")
print("• Use HIGH PRECISION with RKN1210 for sub-meter accuracy")
print("• Use FIXED-STEP when regular output intervals are required")
```

### Balanced Configuration

Moderate settings suitable for many applications:


```python
# /// script
# dependencies = ["brahe", "numpy"]
# ///
"""
Examples of different integrator configurations for various scenarios.

This example shows how to configure integrators for different accuracy,
performance, and reliability requirements.
"""

import brahe as bh
import numpy as np

# Initialize EOP
bh.initialize_eop()


# Define orbital dynamics
def dynamics(t, state):
    mu = bh.GM_EARTH
    r = state[0:3]
    v = state[3:6]
    r_norm = np.linalg.norm(r)
    a = -mu / r_norm**3 * r
    return np.concatenate([v, a])


# LEO orbit initial state
r0 = np.array([bh.R_EARTH + 600e3, 0.0, 0.0])
v0 = np.array([0.0, 7.5e3, 0.0])
state0 = np.concatenate([r0, v0])
period = 2 * np.pi * np.sqrt(np.linalg.norm(r0) ** 3 / bh.GM_EARTH)

print("Integrator Configuration Examples\n")
print("=" * 70)

# Example 1: Conservative (High Reliability)
print("\n1. CONSERVATIVE Configuration (Mission-Critical)")
print("-" * 70)

# --8<-- [start:conservative]
conservative_config = bh.IntegratorConfig(
    abs_tol=1e-12,
    rel_tol=1e-11,
    min_step=0.01,
    max_step=100.0,
    step_safety_factor=0.85,  # More conservative
    min_step_scale_factor=0.3,
    max_step_scale_factor=5.0,  # Limit step growth
    max_step_attempts=15,
)
# --8<-- [end:conservative]

print(f"  abs_tol: {conservative_config.abs_tol:.0e}")
print(f"  rel_tol: {conservative_config.rel_tol:.0e}")
print(f"  max_step: {conservative_config.max_step:.0f} s")
print(f"  safety_factor: {conservative_config.step_safety_factor}")
print("  Use case: Critical operations, high-precision ephemeris")

# Example 2: Balanced (Recommended Default)
print("\n2. BALANCED Configuration (Recommended)")
print("-" * 70)
# --8<-- [start:balanced]
balanced_config = bh.IntegratorConfig.adaptive(abs_tol=1e-10, rel_tol=1e-9)
# --8<-- [end:balanced]

print(f"  abs_tol: {balanced_config.abs_tol:.0e}")
print(f"  rel_tol: {balanced_config.rel_tol:.0e}")
print(f"  max_step: {balanced_config.max_step:.0e} s")
print(f"  safety_factor: {balanced_config.step_safety_factor}")
print("  Use case: Most applications, ~1-10m accuracy")

# Example 3: Aggressive (High Performance)
print("\n3. AGGRESSIVE Configuration (Fast Computation)")
print("-" * 70)
# --8<-- [start:aggressive]
aggressive_config = bh.IntegratorConfig(
    abs_tol=1e-8,
    rel_tol=1e-7,
    initial_step=60.0,
    min_step=1.0,
    max_step=1000.0,  # Large steps allowed
    step_safety_factor=0.95,  # Less conservative
    min_step_scale_factor=0.1,
    max_step_scale_factor=15.0,  # Allow rapid growth
    max_step_attempts=8,
)
# --8<-- [end:aggressive]

print(f"  abs_tol: {aggressive_config.abs_tol:.0e}")
print(f"  rel_tol: {aggressive_config.rel_tol:.0e}")
print(f"  max_step: {aggressive_config.max_step:.0f} s")
print(f"  safety_factor: {aggressive_config.step_safety_factor}")
print("  Use case: Fast trajectory analysis, ~10-100m accuracy")

# Example 4: High Precision (RKN1210)
print("\n4. HIGH PRECISION Configuration (Sub-meter)")
print("-" * 70)
# --8<-- [start:high_precision_config]
high_precision_config = bh.IntegratorConfig(
    abs_tol=1e-14,
    rel_tol=1e-13,
    min_step=0.001,
    max_step=200.0,
    step_safety_factor=0.9,
    min_step_scale_factor=0.2,
    max_step_scale_factor=10.0,
    max_step_attempts=12,
)
# --8<-- [end:high_precision_config]

print(f"  abs_tol: {high_precision_config.abs_tol:.0e}")
print(f"  rel_tol: {high_precision_config.rel_tol:.0e}")
print(f"  max_step: {high_precision_config.max_step:.0f} s")
print(f"  safety_factor: {high_precision_config.step_safety_factor}")
print("  Use case: High-precision orbit determination, <1m accuracy")
print("  Requires: RKN1210 integrator")

# Example 5: Fixed-Step Configuration
print("\n5. FIXED-STEP Configuration")
print("-" * 70)
fixed_config = bh.IntegratorConfig.fixed_step(step_size=60.0)

print(f"  step_size: {60.0} s")
print("  Note: Step size can be overridden with dt parameter in integrator.step()")
print("  Use case: Regular output intervals, predictable cost")

print("\n" + "=" * 70)
print("\nRecommendations:")
print("• Start with BALANCED for most applications")
print("• Use CONSERVATIVE for mission-critical operations")
print("• Use AGGRESSIVE only when accuracy can be sacrificed for speed")
print("• Use HIGH PRECISION with RKN1210 for sub-meter accuracy")
print("• Use FIXED-STEP when regular output intervals are required")
```

### Aggressive Configuration

Relaxed tolerances for faster computation:


```python
# /// script
# dependencies = ["brahe", "numpy"]
# ///
"""
Examples of different integrator configurations for various scenarios.

This example shows how to configure integrators for different accuracy,
performance, and reliability requirements.
"""

import brahe as bh
import numpy as np

# Initialize EOP
bh.initialize_eop()


# Define orbital dynamics
def dynamics(t, state):
    mu = bh.GM_EARTH
    r = state[0:3]
    v = state[3:6]
    r_norm = np.linalg.norm(r)
    a = -mu / r_norm**3 * r
    return np.concatenate([v, a])


# LEO orbit initial state
r0 = np.array([bh.R_EARTH + 600e3, 0.0, 0.0])
v0 = np.array([0.0, 7.5e3, 0.0])
state0 = np.concatenate([r0, v0])
period = 2 * np.pi * np.sqrt(np.linalg.norm(r0) ** 3 / bh.GM_EARTH)

print("Integrator Configuration Examples\n")
print("=" * 70)

# Example 1: Conservative (High Reliability)
print("\n1. CONSERVATIVE Configuration (Mission-Critical)")
print("-" * 70)

# --8<-- [start:conservative]
conservative_config = bh.IntegratorConfig(
    abs_tol=1e-12,
    rel_tol=1e-11,
    min_step=0.01,
    max_step=100.0,
    step_safety_factor=0.85,  # More conservative
    min_step_scale_factor=0.3,
    max_step_scale_factor=5.0,  # Limit step growth
    max_step_attempts=15,
)
# --8<-- [end:conservative]

print(f"  abs_tol: {conservative_config.abs_tol:.0e}")
print(f"  rel_tol: {conservative_config.rel_tol:.0e}")
print(f"  max_step: {conservative_config.max_step:.0f} s")
print(f"  safety_factor: {conservative_config.step_safety_factor}")
print("  Use case: Critical operations, high-precision ephemeris")

# Example 2: Balanced (Recommended Default)
print("\n2. BALANCED Configuration (Recommended)")
print("-" * 70)
# --8<-- [start:balanced]
balanced_config = bh.IntegratorConfig.adaptive(abs_tol=1e-10, rel_tol=1e-9)
# --8<-- [end:balanced]

print(f"  abs_tol: {balanced_config.abs_tol:.0e}")
print(f"  rel_tol: {balanced_config.rel_tol:.0e}")
print(f"  max_step: {balanced_config.max_step:.0e} s")
print(f"  safety_factor: {balanced_config.step_safety_factor}")
print("  Use case: Most applications, ~1-10m accuracy")

# Example 3: Aggressive (High Performance)
print("\n3. AGGRESSIVE Configuration (Fast Computation)")
print("-" * 70)
# --8<-- [start:aggressive]
aggressive_config = bh.IntegratorConfig(
    abs_tol=1e-8,
    rel_tol=1e-7,
    initial_step=60.0,
    min_step=1.0,
    max_step=1000.0,  # Large steps allowed
    step_safety_factor=0.95,  # Less conservative
    min_step_scale_factor=0.1,
    max_step_scale_factor=15.0,  # Allow rapid growth
    max_step_attempts=8,
)
# --8<-- [end:aggressive]

print(f"  abs_tol: {aggressive_config.abs_tol:.0e}")
print(f"  rel_tol: {aggressive_config.rel_tol:.0e}")
print(f"  max_step: {aggressive_config.max_step:.0f} s")
print(f"  safety_factor: {aggressive_config.step_safety_factor}")
print("  Use case: Fast trajectory analysis, ~10-100m accuracy")

# Example 4: High Precision (RKN1210)
print("\n4. HIGH PRECISION Configuration (Sub-meter)")
print("-" * 70)
# --8<-- [start:high_precision_config]
high_precision_config = bh.IntegratorConfig(
    abs_tol=1e-14,
    rel_tol=1e-13,
    min_step=0.001,
    max_step=200.0,
    step_safety_factor=0.9,
    min_step_scale_factor=0.2,
    max_step_scale_factor=10.0,
    max_step_attempts=12,
)
# --8<-- [end:high_precision_config]

print(f"  abs_tol: {high_precision_config.abs_tol:.0e}")
print(f"  rel_tol: {high_precision_config.rel_tol:.0e}")
print(f"  max_step: {high_precision_config.max_step:.0f} s")
print(f"  safety_factor: {high_precision_config.step_safety_factor}")
print("  Use case: High-precision orbit determination, <1m accuracy")
print("  Requires: RKN1210 integrator")

# Example 5: Fixed-Step Configuration
print("\n5. FIXED-STEP Configuration")
print("-" * 70)
fixed_config = bh.IntegratorConfig.fixed_step(step_size=60.0)

print(f"  step_size: {60.0} s")
print("  Note: Step size can be overridden with dt parameter in integrator.step()")
print("  Use case: Regular output intervals, predictable cost")

print("\n" + "=" * 70)
print("\nRecommendations:")
print("• Start with BALANCED for most applications")
print("• Use CONSERVATIVE for mission-critical operations")
print("• Use AGGRESSIVE only when accuracy can be sacrificed for speed")
print("• Use HIGH PRECISION with RKN1210 for sub-meter accuracy")
print("• Use FIXED-STEP when regular output intervals are required")
```

### High-Precision Configuration

Very tight tolerances for high-accuracy needs:


```python
# /// script
# dependencies = ["brahe", "numpy"]
# ///
"""
Examples of different integrator configurations for various scenarios.

This example shows how to configure integrators for different accuracy,
performance, and reliability requirements.
"""

import brahe as bh
import numpy as np

# Initialize EOP
bh.initialize_eop()


# Define orbital dynamics
def dynamics(t, state):
    mu = bh.GM_EARTH
    r = state[0:3]
    v = state[3:6]
    r_norm = np.linalg.norm(r)
    a = -mu / r_norm**3 * r
    return np.concatenate([v, a])


# LEO orbit initial state
r0 = np.array([bh.R_EARTH + 600e3, 0.0, 0.0])
v0 = np.array([0.0, 7.5e3, 0.0])
state0 = np.concatenate([r0, v0])
period = 2 * np.pi * np.sqrt(np.linalg.norm(r0) ** 3 / bh.GM_EARTH)

print("Integrator Configuration Examples\n")
print("=" * 70)

# Example 1: Conservative (High Reliability)
print("\n1. CONSERVATIVE Configuration (Mission-Critical)")
print("-" * 70)

# --8<-- [start:conservative]
conservative_config = bh.IntegratorConfig(
    abs_tol=1e-12,
    rel_tol=1e-11,
    min_step=0.01,
    max_step=100.0,
    step_safety_factor=0.85,  # More conservative
    min_step_scale_factor=0.3,
    max_step_scale_factor=5.0,  # Limit step growth
    max_step_attempts=15,
)
# --8<-- [end:conservative]

print(f"  abs_tol: {conservative_config.abs_tol:.0e}")
print(f"  rel_tol: {conservative_config.rel_tol:.0e}")
print(f"  max_step: {conservative_config.max_step:.0f} s")
print(f"  safety_factor: {conservative_config.step_safety_factor}")
print("  Use case: Critical operations, high-precision ephemeris")

# Example 2: Balanced (Recommended Default)
print("\n2. BALANCED Configuration (Recommended)")
print("-" * 70)
# --8<-- [start:balanced]
balanced_config = bh.IntegratorConfig.adaptive(abs_tol=1e-10, rel_tol=1e-9)
# --8<-- [end:balanced]

print(f"  abs_tol: {balanced_config.abs_tol:.0e}")
print(f"  rel_tol: {balanced_config.rel_tol:.0e}")
print(f"  max_step: {balanced_config.max_step:.0e} s")
print(f"  safety_factor: {balanced_config.step_safety_factor}")
print("  Use case: Most applications, ~1-10m accuracy")

# Example 3: Aggressive (High Performance)
print("\n3. AGGRESSIVE Configuration (Fast Computation)")
print("-" * 70)
# --8<-- [start:aggressive]
aggressive_config = bh.IntegratorConfig(
    abs_tol=1e-8,
    rel_tol=1e-7,
    initial_step=60.0,
    min_step=1.0,
    max_step=1000.0,  # Large steps allowed
    step_safety_factor=0.95,  # Less conservative
    min_step_scale_factor=0.1,
    max_step_scale_factor=15.0,  # Allow rapid growth
    max_step_attempts=8,
)
# --8<-- [end:aggressive]

print(f"  abs_tol: {aggressive_config.abs_tol:.0e}")
print(f"  rel_tol: {aggressive_config.rel_tol:.0e}")
print(f"  max_step: {aggressive_config.max_step:.0f} s")
print(f"  safety_factor: {aggressive_config.step_safety_factor}")
print("  Use case: Fast trajectory analysis, ~10-100m accuracy")

# Example 4: High Precision (RKN1210)
print("\n4. HIGH PRECISION Configuration (Sub-meter)")
print("-" * 70)
# --8<-- [start:high_precision_config]
high_precision_config = bh.IntegratorConfig(
    abs_tol=1e-14,
    rel_tol=1e-13,
    min_step=0.001,
    max_step=200.0,
    step_safety_factor=0.9,
    min_step_scale_factor=0.2,
    max_step_scale_factor=10.0,
    max_step_attempts=12,
)
# --8<-- [end:high_precision_config]

print(f"  abs_tol: {high_precision_config.abs_tol:.0e}")
print(f"  rel_tol: {high_precision_config.rel_tol:.0e}")
print(f"  max_step: {high_precision_config.max_step:.0f} s")
print(f"  safety_factor: {high_precision_config.step_safety_factor}")
print("  Use case: High-precision orbit determination, <1m accuracy")
print("  Requires: RKN1210 integrator")

# Example 5: Fixed-Step Configuration
print("\n5. FIXED-STEP Configuration")
print("-" * 70)
fixed_config = bh.IntegratorConfig.fixed_step(step_size=60.0)

print(f"  step_size: {60.0} s")
print("  Note: Step size can be overridden with dt parameter in integrator.step()")
print("  Use case: Regular output intervals, predictable cost")

print("\n" + "=" * 70)
print("\nRecommendations:")
print("• Start with BALANCED for most applications")
print("• Use CONSERVATIVE for mission-critical operations")
print("• Use AGGRESSIVE only when accuracy can be sacrificed for speed")
print("• Use HIGH PRECISION with RKN1210 for sub-meter accuracy")
print("• Use FIXED-STEP when regular output intervals are required")
```

## Tuning Strategy

### 1. Start with Defaults

```
config = bh.IntegratorConfig.adaptive(abs_tol=1e-10, rel_tol=1e-9)
integrator = bh.DP54Integrator(dynamics, config)
```

### 2. Assess Performance

Run test integration and monitor:
- Number of steps taken
- Number of rejected steps (should be < 1%)
- Error estimates
- Step size variation

### 3. Adjust Based on Observations

**If steps too small:**
```
# Relax tolerances by 10×
config.abs_tol = 1e-9
config.rel_tol = 1e-8
```

**If missing features:**
```
# Reduce max step
config.max_step = orbital_period / 50
```

**If many rejections:**
```
# Decrease safety factor
config.step_safety_factor = 0.7

# Or reduce step scale factors
config.max_step_scale_factor = 5.0
```

**If hitting min_step:**
```
# Switch to higher-order integrator or relax tolerances
integrator = bh.RKN1210Integrator(dynamics, config)
```

### 4. Validate

Compare against:

- Analytical solution (if available)
- Same integration with 10× tighter tolerances
- Energy/momentum conservation
- Independent integration software

### 5. Document

Record final configuration with rationale:
```
# Configuration tuned for LEO orbit propagation
# - Tolerances provide ~5m position accuracy over 1 day
# - Max step prevents missing station-keeping maneuvers
# - Validated against analytical two-body solution
config = bh.IntegratorConfig.adaptive(
    abs_tol=1e-11,
    rel_tol=1e-10,
    max_step=300.0  # 5 minutes
)
```

## See Also

- **[Adaptive-Step Integrators](adaptive_step.md)** - How adaptive integration works
- **[Fixed-Step Integrators](fixed_step.md)** - Fixed-step integration guide
- **[Configuration API Reference](../../library_api/integrators/config.md)** - Complete API documentation
- **[Integrators Overview](index.md)** - Comparison of all integrators