# Numerical Orbit Propagator

This guide covers the fundamental operations of the `NumericalOrbitPropagator`: creating propagators, stepping through time, accessing states, and managing trajectories.

For API details, see the [NumericalOrbitPropagator API Reference](../../../library_api/propagators/numerical_orbit_propagator.md).

## Creating a Propagator

The `NumericalOrbitPropagator` requires an initial epoch, state, propagation configuration, force model configuration, and optional parameters. The propagator state vector follows a standard layout with the 6D orbital state in the first elements:

```
State Vector (6+ elements)
├── [0] x  - Position X (m, ECI)
├── [1] y  - Position Y (m, ECI)
├── [2] z  - Position Z (m, ECI)
├── [3] vx - Velocity X (m/s, ECI)
├── [4] vy - Velocity Y (m/s, ECI)
├── [5] vz - Velocity Z (m/s, ECI)
└── [6+]   - Extended state (optional, if user-defined additional_dynamics set)
```

All force models read from the first 6 elements and contribute accelerations to indices 3-5. Extended state elements (index 6+) are available for user-defined dynamics such as mass depletion, battery state, attitude dynamics, or other user-defined states.

### Minimal Setup

The simplest setup uses default configurations:


```python
import numpy as np
import brahe as bh

# Initialize EOP and space weather data (required for NRLMSISE-00 drag model)
bh.initialize_eop()
bh.initialize_sw()

# Create initial epoch
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# Define orbital elements: [a, e, i, raan, argp, M] in SI units
# LEO satellite: 500 km altitude, near-circular, sun-synchronous inclination
oe = np.array([bh.R_EARTH + 500e3, 0.001, 97.8, 15.0, 30.0, 45.0])
state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

# Parameters: [mass, drag_area, Cd, srp_area, Cr]
params = np.array([500.0, 2.0, 2.2, 2.0, 1.3])

# Create propagator with default configuration
prop = bh.NumericalOrbitPropagator(
    epoch,
    state,
    bh.NumericalPropagationConfig.default(),
    bh.ForceModelConfig.default(),
    params,
)

# Propagate for 1 hour
prop.propagate_to(epoch + 3600.0)

# Get final state
final_epoch = prop.current_epoch()
final_state = prop.current_state()

# Validate propagation completed
assert final_epoch == epoch + 3600.0
assert len(final_state) == 6
assert np.linalg.norm(final_state[:3]) > bh.R_EARTH  # Still in orbit

print(f"Initial epoch: {epoch}")
print(f"Final epoch:   {final_epoch}")
print(
    f"Position (km): [{final_state[0] / 1e3:.3f}, {final_state[1] / 1e3:.3f}, {final_state[2] / 1e3:.3f}]"
)
print(
    f"Velocity (m/s): [{final_state[3]:.3f}, {final_state[4]:.3f}, {final_state[5]:.3f}]"
)
print("Example validated successfully!")
```


## Stepping Through Time

The propagator provides several methods for advancing through time, following the same interface as analytical propagators.

### Single Steps

- `step()` - Advance by the integrator's current step size
- `step_by(dt)` - Advance by a specific duration (seconds)
- `step_past(epoch)` - Step until past a target epoch

### Multiple Steps

- `propagate_steps(n)` - Take N steps
- `propagate_to(epoch)` - Propagate exactly to a target epoch

The `propagate_to()` method is the most commonly used, as it handles step-size adjustment to reach the exact target epoch.

## Accessing State

### Current State

After propagation, access the current state using:

- `current_epoch()` - Returns the propagator's current epoch
- `current_state()` - Returns the current state vector (Cartesian ECI)

### State at Arbitrary Epochs

The `StateProvider` trait enables state queries at any epoch:

- `state(epoch)` - State in the propagator's native format
- `state_eci(epoch)` - Cartesian state in ECI frame
- `state_ecef(epoch)` - Cartesian state in ECEF frame
- `state_koe_osc(epoch, angle_format)` - Keplerian orbital elements

**Propagator Advancement and State Queries**
When querying states at epochs beyond the current propagated time, the propagator **MUST** have already been advanced to at least that epoch using one of the propagation methods, such as `propagate_to()` or `step_past()`, before calling the state query methods otherwise an error will be raised.

For epochs within the propagated trajectory, interpolation is used. For epochs beyond the trajectory, the propagator advances to that epoch.

### Batch Queries

For multiple epochs, use the batch query methods:

- `states(epochs)` - States at multiple epochs
- `states_eci(epochs)` - ECI states at multiple epochs
- `states_koe(epochs, angle_format)` - Keplerian elements at multiple epochs

## Trajectory Management

The propagator maintains an internal `OrbitTrajectory` containing all propagated states.

### Accessing the Trajectory

Access the trajectory directly via the `trajectory` property. The trajectory provides:

- `len()` - Number of stored states
- `epochs()` - List of all epoch times
- `states()` - Array of all state vectors
- `state_at_epoch(epoch)` - Interpolated state at any epoch within the trajectory

### Memory Management

For long propagations, use eviction policies to limit memory:

- `set_eviction_policy_max_size(n)` - Keep only the N most recent states
- `set_eviction_policy_max_age(duration)` - Keep only states within a time window

### Resetting

Use `reset()` to return the propagator to its initial conditions, clearing the trajectory.

## Propagator Parameters

Some force models require additional parameters. These are provided as a parameter vector during construction:

| Index | Parameter | Units | Description |
|-------|-----------|-------|-------------|
| 0 | mass | kg | Spacecraft mass |
| 1 | drag_area | m$^2$ | Cross-sectional area for drag |
| 2 | Cd | - | Drag coefficient |
| 3 | srp_area | m$^2$ | Cross-sectional area for SRP |
| 4 | Cr | - | Reflectivity coefficient |

The `ForceModelConfig.requires_params()` method indicates whether parameters are needed.

## Identity Tracking

For applications such as [access computation](../../access_computation/index.md) that can identify events based on the satellite, propagators can be identified by name, ID, or UUID:

```
prop = bh.NumericalOrbitPropagator(...)
prop = prop.with_name("ISS")
prop = prop.with_id(25544)
```

This enables tracking propagators in access computation, conjunction analysis, and other multi-object scenarios.


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
- [Force Models](force_models.md) - Configuring force models
- [Integrator Configuration](integrator_configuration.md) - Integration method selection
- [NumericalOrbitPropagator API Reference](../../../library_api/propagators/numerical_orbit_propagator.md)