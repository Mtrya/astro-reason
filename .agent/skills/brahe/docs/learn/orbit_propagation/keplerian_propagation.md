# Keplerian Propagation

The `KeplerianPropagator` provides fast, analytical two-body orbital propagation using Kepler's equations. It assumes only gravitational attraction from a central body (Earth) with no perturbations, making it ideal for rapid trajectory generation, high-altitude orbits, or when perturbations are negligible.

For complete API documentation, see the [KeplerianPropagator API Reference](../../library_api/propagators/keplerian_propagator.md).

## Initialization

The `KeplerianPropagator` can be initialized from several state representations.

### From Keplerian Elements

The most direct initialization method uses classical Keplerian orbital elements.


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define initial epoch
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# Define Keplerian elements [a, e, i, Ω, ω, M]
elements = np.array(
    [
        bh.R_EARTH + 500e3,  # Semi-major axis (m)
        0.001,  # Eccentricity
        97.8,  # Inclination (degrees)
        15.0,  # RAAN (degrees)
        30.0,  # Argument of perigee (degrees)
        45.0,  # Mean anomaly (degrees)
    ]
)

# Create propagator with 60-second step size
prop = bh.KeplerianPropagator.from_keplerian(
    epoch, elements, bh.AngleFormat.DEGREES, 60.0
)

print(f"Orbital period: {bh.orbital_period(elements[0]):.1f} seconds")
```


### From ECI Cartesian State

Initialize from position and velocity vectors in the Earth-Centered Inertial (ECI) frame.


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# Define Cartesian state in ECI frame [x, y, z, vx, vy, vz]
# Convert from Keplerian elements for this example
elements = np.array([bh.R_EARTH + 500e3, 0.001, 97.8, 15.0, 30.0, 45.0])
state_eci = bh.state_koe_to_eci(elements, bh.AngleFormat.DEGREES)

# Create propagator from ECI state
prop = bh.KeplerianPropagator.from_eci(epoch, state_eci, 60.0)

print(f"Initial position magnitude: {np.linalg.norm(state_eci[:3]) / 1e3:.1f} km")
```


### From ECEF Cartesian State

Initialize from position and velocity vectors in the Earth-Centered Earth-Fixed (ECEF) frame. The propagator will automatically convert to ECI internally.


```python
import brahe as bh
import numpy as np

bh.initialize_eop()  # Required for ECEF ↔ ECI transformations

epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# Get state in ECI, then convert to ECEF for demonstration
elements = np.array([bh.R_EARTH + 500e3, 0.001, 97.8, 15.0, 30.0, 45.0])
state_eci = bh.state_koe_to_eci(elements, bh.AngleFormat.DEGREES)
state_ecef = bh.state_eci_to_ecef(epoch, state_eci)

# Create propagator from ECEF state
prop = bh.KeplerianPropagator.from_ecef(epoch, state_ecef, 60.0)

print(f"ECEF position magnitude: {np.linalg.norm(state_ecef[:3]) / 1e3:.1f} km")
```


## Stepping Through Time

One of the primary functions of propagators is to step forward in time, generating new states at regular intervals. There are several methods to advance the propagator's internal state. Each stepping operation adds new state(s) to the internal trajectory.

### Single Steps


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Create propagator
epoch = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
elements = np.array([bh.R_EARTH + 500e3, 0.001, 97.8, 15.0, 30.0, 45.0])
prop = bh.KeplerianPropagator.from_keplerian(
    epoch, elements, bh.AngleFormat.DEGREES, 60.0
)

# Take one step (60 seconds)
prop.step()
print(f"After 1 step: {prop.current_epoch()}")

# Step by custom duration (120 seconds)
prop.step_by(120.0)
print(f"After custom step: {prop.current_epoch()}")

# Trajectory now contains 3 states (initial + 2 steps)
print(f"Trajectory length: {len(prop.trajectory)}")
```


### Multiple Steps

The `propagate_steps()` method allows taking multiple fixed-size steps in one call.


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

epoch = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
elements = np.array([bh.R_EARTH + 500e3, 0.001, 97.8, 15.0, 30.0, 45.0])
prop = bh.KeplerianPropagator.from_keplerian(
    epoch, elements, bh.AngleFormat.DEGREES, 60.0
)

# Take 10 steps (10 × 60 = 600 seconds)
prop.propagate_steps(10)
print(f"After 10 steps: {(prop.current_epoch() - epoch):.1f} seconds elapsed")
print(f"Trajectory length: {len(prop.trajectory)}")
```


### Propagate to Target Epoch

For precise time targeting, use `propagate_to()` which adjusts the final step size to exactly reach the target epoch.


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

epoch = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
elements = np.array([bh.R_EARTH + 500e3, 0.001, 97.8, 15.0, 30.0, 45.0])
prop = bh.KeplerianPropagator.from_keplerian(
    epoch, elements, bh.AngleFormat.DEGREES, 60.0
)

# Propagate exactly 500 seconds (not evenly divisible by step size)
target = epoch + 500.0
prop.propagate_to(target)

print(f"Target epoch: {target}")
print(f"Current epoch: {prop.current_epoch()}")
print(f"Difference: {abs(prop.current_epoch() - target):.10f} seconds")
```


## Direct State Queries

The `StateProvider` trait allows computing states at arbitrary epochs without building a trajectory. This is useful for sparse sampling or parallel batch computation.

### Single Epoch Queries

Single epoch queries like `state()`, `state_eci()`, and `state_ecef()` compute the state at a specific epoch on demand.


```python
import brahe as bh
import numpy as np

bh.initialize_eop()  # Required for frame transformations

epoch = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
elements = np.array([bh.R_EARTH + 500e3, 0.001, 97.8, 15.0, 30.0, 45.0])
prop = bh.KeplerianPropagator.from_keplerian(
    epoch, elements, bh.AngleFormat.DEGREES, 60.0
)

# Query state 1 hour later (doesn't add to trajectory)
query_epoch = epoch + 3600.0
state_native = prop.state(
    query_epoch
)  # Native format of propagator internal state (Keplerian)
state_eci = prop.state_eci(query_epoch)  # ECI Cartesian
state_ecef = prop.state_ecef(query_epoch)  # ECEF Cartesian
state_kep = prop.state_koe_osc(query_epoch, bh.AngleFormat.DEGREES)

print(f"Native state (Keplerian): a={state_native[0] / 1e3:.1f} km")
print(f"ECI position magnitude: {np.linalg.norm(state_eci[:3]) / 1e3:.1f} km")
print(f"ECEF position magnitude: {np.linalg.norm(state_ecef[:3]) / 1e3:.1f} km")
```


### Batch Queries

Batch queries like `states()` and `states_eci()` compute states at each epoch in a provided list.


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

epoch = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
elements = np.array([bh.R_EARTH + 500e3, 0.001, 97.8, 15.0, 30.0, 45.0])
prop = bh.KeplerianPropagator.from_keplerian(
    epoch, elements, bh.AngleFormat.DEGREES, 60.0
)

# Generate states at irregular intervals
query_epochs = [epoch + t for t in [0.0, 100.0, 500.0, 1000.0, 3600.0]]
states_eci = prop.states_eci(query_epochs)

print(f"Generated {len(states_eci)} states")
for i, state in enumerate(states_eci):
    print(f"  Epoch {i}: position magnitude = {np.linalg.norm(state[:3]) / 1e3:.1f} km")
```


## Trajectory Management

The propagator stores all stepped states in an internal `OrbitTrajectory`. This trajectory can be accessed, converted, and managed.

### Accessing the Trajectory


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

epoch = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
elements = np.array([bh.R_EARTH + 500e3, 0.001, 97.8, 15.0, 30.0, 45.0])
prop = bh.KeplerianPropagator.from_keplerian(
    epoch, elements, bh.AngleFormat.DEGREES, 60.0
)

# Propagate for several steps
prop.propagate_steps(5)

# Access trajectory
traj = prop.trajectory
print(f"Trajectory contains {len(traj)} states")

# Iterate over epoch-state pairs
for epoch, state in traj:
    print(f"Epoch: {epoch}, semi-major axis: {state[0] / 1e3:.1f} km")
```


### Frame Conversions

You can use the OrbitTrajectory's frame conversion methods to get the trajectory in different reference frames.


```python
import brahe as bh
import numpy as np

bh.initialize_eop()  # Required for ECEF conversions

epoch = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
elements = np.array([bh.R_EARTH + 500e3, 0.001, 97.8, 15.0, 30.0, 45.0])
prop = bh.KeplerianPropagator.from_keplerian(
    epoch, elements, bh.AngleFormat.DEGREES, 60.0
)
prop.propagate_steps(10)

# Convert entire trajectory to different frames
traj_eci = prop.trajectory.to_eci()  # ECI Cartesian
traj_ecef = prop.trajectory.to_ecef()  # ECEF Cartesian
traj_kep = prop.trajectory.to_keplerian(bh.AngleFormat.RADIANS)

print(f"ECI trajectory: {len(traj_eci)} states")
print(f"ECEF trajectory: {len(traj_ecef)} states")
print(f"Keplerian trajectory: {len(traj_kep)} states")
```


### Memory Management

Propagators support trajectory memory management via eviction policies to limit memory usage for long-running applications.


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

epoch = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
elements = np.array([bh.R_EARTH + 500e3, 0.001, 97.8, 15.0, 30.0, 45.0])
prop = bh.KeplerianPropagator.from_keplerian(
    epoch, elements, bh.AngleFormat.DEGREES, 60.0
)

# Keep only 100 most recent states
prop.set_eviction_policy_max_size(100)

# Propagate many steps
prop.propagate_steps(500)
print(f"Trajectory length: {len(prop.trajectory)}")  # Will be 100

# Alternative: Keep only states within 1 hour of current time
prop.reset()
prop.set_eviction_policy_max_age(3600.0)  # 3600 seconds = 1 hour
prop.propagate_steps(500)
print(f"Trajectory length after age policy: {len(prop.trajectory)}")
```


## Configuration and Control

There are several methods to manage and configure the propagator during its lifecycle.

### Resetting the Propagator

You can reset the propagator to its initial conditions using the `reset()` method.


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

epoch = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
elements = np.array([bh.R_EARTH + 500e3, 0.001, 97.8, 15.0, 30.0, 45.0])
prop = bh.KeplerianPropagator.from_keplerian(
    epoch, elements, bh.AngleFormat.DEGREES, 60.0
)

# Propagate forward
prop.propagate_steps(100)
print(f"After propagation: {len(prop.trajectory)} states")

# Reset to initial conditions
prop.reset()
print(f"After reset: {len(prop.trajectory)} states")
print(f"Current epoch: {prop.current_epoch()}")
```


### Changing Step Size

If you need to adjust the default step size during propagation, use the `set_step_size()` method.


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

epoch = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
elements = np.array([bh.R_EARTH + 500e3, 0.001, 97.8, 15.0, 30.0, 45.0])
prop = bh.KeplerianPropagator.from_keplerian(
    epoch, elements, bh.AngleFormat.DEGREES, 60.0
)

print(f"Initial step size: {prop.step_size} seconds")

# Change step size
prop.set_step_size(120.0)
print(f"New step size: {prop.step_size} seconds")

# Subsequent steps use new step size
prop.step()  # Advances 120 seconds
print(f"After step: {(prop.current_epoch() - epoch):.1f} seconds elapsed")
```


## Identity Tracking

Finally, the `IdentifiableStateProvider` trait allows you to set and get identity information for the propagator. This can be useful when managing multiple propagators in an application.

Track propagators with names, IDs, or UUIDs for multi-satellite scenarios.


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

epoch = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
elements = np.array([bh.R_EARTH + 500e3, 0.001, 97.8, 15.0, 30.0, 45.0])

# Create propagator with identity (builder pattern)
prop = (
    bh.KeplerianPropagator.from_keplerian(epoch, elements, bh.AngleFormat.DEGREES, 60.0)
    .with_name("Satellite-A")
    .with_id(12345)
)

print(f"Name: {prop.get_name()}")
print(f"ID: {prop.get_id()}")
print(f"UUID: {prop.get_uuid()}")
```


---

## See Also

- [Orbit Propagation Overview](index.md) - Propagation concepts and trait hierarchy
- [SGP Propagation](sgp_propagation.md) - TLE-based SGP4/SDP4 propagator
- [Trajectories](../trajectories/index.md) - Trajectory storage and operations
- [KeplerianPropagator API Reference](../../library_api/propagators/keplerian_propagator.md)