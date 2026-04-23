# Numerical Propagation

Numerical propagation solves equations of motion through numerical integration, enabling high-fidelity dynamics modeling with arbitrary force models. Unlike analytical propagators that use closed-form solutions, numerical propagators step through time, computing accelerations at each step and integrating to get the next state. This approach allows for complex perturbations, control input modeling, covariance propagation, sensitivity analysis, and event detection.

For orbital mechanics, Brahe provides the [`NumericalOrbitPropagator`](../../../library_api/propagators/numerical_orbit_propagator.md) class built, which provides a fast way to propagate satellite orbits using the force models defined and discussed in [Orbital Dynamics](../../orbital_dynamics/index.md). The NumericalOrbitPropagator supports a variety of integrators, including fixed-step and adaptive methods, and can model perturbations such as atmospheric drag, solar radiation pressure, third-body effects, and relativistic corrections. It also supports covariance propagation and sensitivity analysis for orbit determination and parameter estimation. Finally, it supports event detection for orbital events like eclipses, node crossings, and altitude values. Event detection is covered in more detail in the [Event Detection](event_detection.md) section, and premade event types are documented in [Premade Events](premade_events.md).

Brahe also includes a more general [`NumericalPropagator`](../../../library_api/propagators/numerical_propagator.md) class for propagating arbitrary dynamical system systems. This class allows users to integrate equations of motion for non-orbital dynamical systems. This capability is discussed in more depth in [General Dynamics Propagation](generic_dynamics.md). 

**Experimental Feature**
The numerical propagation system is one of the newer parts of Brahe and is still considered experimental. While the core functionality has been tested and verified, it is one of the most complex features so the design needs further testing and use before finalization. Users are encouraged to provide feedback and report any issues they encounter.

## Architecture Overview

The numerical propagation system consists of several configurable components:

### Force Model Configuration

The [`ForceModelConfig`](../../../library_api/propagators/force_model_config.md) is a data structure that specifies which physical perturbations to include in the dynamics and their parameters. Supported force include:

- **Gravity**: Point-mass or spherical harmonics (EGMS2008, GGM05S, or user-defined)
- **Atmospheric Drag**: NRLMSISE-00, Harris-Priester, or exponential atmosphere models
- **Solar Radiation Pressure**: Cannonball model with conical or cylindrical eclipse
- **Third-Body**: Sun and Moon gravitational perturbations with analytic or DE440 ephemerides 
- **Relativistic Effects**: Special and general relativistic corrections

### Integrator Configuration

The [`NumericalPropagationConfig`](../../../library_api/propagators/numerical_propagation_config.md) specifies the integration method, integrator configuration, and variational equations settings:

- **Integrator**: Fixed-step (e.g., Runge-Kutta 4) or adaptive (e.g., Dormand-Prince 8(5,3)) methods
- **Integrator Settings**: Step size, error tolerances, and maximum step constraints
- **Variational Equations**: Enable/disable covariance and sensitivity propagation, with settings for state transition matrix and sensitivity matrix computation

### Event Detection

The numerical propagator supports event detection through configurable event detectors. Brahe includes several premade event types (detailed in [Premade Events](premade_events.md)):

- **Time Events**: Trigger at specific epochs
- **Value Events**: Trigger when a computed quantity crosses a value
- **Binary Events**: Trigger on boolean state changes
- **Altitude Events**: Trigger at specific altitudes

Events can be configured to execute callbacks for impulsive maneuvers.

### Trajectory Storage

All propagators maintain an internal [`OrbitTrajectory`](../../../library_api/trajectories/orbit_trajectory.md) storing propagated states, covariances, state transition matricies, and sensitivities.

## Quick Start

The simplest way to create a numerical propagator uses default configurations:


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


---

## Section Contents

- [Numerical Orbit Propagator](numerical_orbit_propagator.md) - Getting started with numerical propagation
- [Force Models](force_models.md) - Configuring physical force models
- [Integrator Configuration](integrator_configuration.md) - Choosing integration methods
- [Event Detection](event_detection.md) - Detecting orbital events
- [Premade Events](premade_events.md) - Built-in event types
- [Event Callbacks](event_callbacks.md) - Responding to detected events
- [Maneuvers](maneuvers.md) - Impulsive and continuous thrust
- [Covariance and Sensitivity](covariance_sensitivity.md) - Uncertainty propagation
- [Extending Spacecraft State](extending_state.md) - Additional state variables
- [General Dynamics Propagation](generic_dynamics.md) - Propagating arbitrary ODEs

## See Also

- [NumericalOrbitPropagator API Reference](../../../library_api/propagators/numerical_orbit_propagator.md)
- [NumericalPropagator API Reference](../../../library_api/propagators/numerical_propagator.md)