# SGP Propagation

The `SGPPropagator` implements the SGP4/SDP4 propagation models for orbital prediction. SGP4 is a standard method for satellite tracking and includes simplified perturbations from Earth oblateness and atmospheric drag, making it suitable for operational satellite tracking and near-Earth orbit propagation. It is widely used with Two-Line Element (TLE) data provided by NORAD and other space tracking organizations.

For complete API documentation, see the [SGPPropagator API Reference](../../library_api/propagators/sgp_propagator.md).

## TLE Format Support

SGP4 propagation is based on Two-Line Element (TLE) sets, a compact data format for orbital elements. Brahe supports both traditional and modern TLE formats:

- **Classic Format**: Traditional numeric NORAD catalog numbers (5 digits, up to 99999)
- **Alpha-5 Format**: Extended alphanumeric catalog numbers for satellites beyond 99999

The initialization automatically detects and handles both formats.

## From Ephemeris Data Sources

Rather than hard-coding TLE strings, you can query live satellite data from CelesTrak or Space-Track and get a ready-to-use propagator in a single call. This is the most common workflow for operational satellite tracking:

```python
This example shows how to query a satellite from CelesTrak and convert it
to a propagator in a few steps, which is the most common use case.
"""

import brahe as bh

# Initialize EOP data
bh.initialize_eop()

# Get an SGP4 propagator for the ISS directly from CelesTrak
client = bh.celestrak.CelestrakClient()
iss_prop = client.get_sgp_propagator(catnr=25544, step_size=60.0)

print(f"Created propagator: {iss_prop.get_name()}")
print(f"Epoch: {iss_prop.epoch}")

# Propagate forward 1 orbit period (~93 minutes for ISS)
iss_prop.propagate_to(iss_prop.epoch + bh.orbital_period(iss_prop.semi_major_axis))
state = iss_prop.current_state()

print("\nState after 1 orbit:")
print(f"  Position: [{state[0]:.1f}, {state[1]:.1f}, {state[2]:.1f}] m")
print(f"  Velocity: [{state[3]:.1f}, {state[4]:.1f}, {state[5]:.1f}] m/s")
```


For details on querying satellite data, see [Ephemeris Data Sources](../ephemeris/index.md).

## Initialization

The `SGPPropagator` can also be initialized directly from TLE data. The TLE lines contain all orbital parameters needed for propagation.

### From Two Line Elements (TLE)

The most common initialization uses two lines of TLE data.


```python
import brahe as bh
import numpy as np

bh.initialize_eop()  # Required for accurate frame transformations

# ISS TLE data (example)
line1 = "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927"
line2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537"

# Create propagator with 60-second step size
prop = bh.SGPPropagator.from_tle(line1, line2, 60.0)

print(f"NORAD ID: {prop.norad_id}")
print(f"TLE epoch: {prop.epoch}")
print(
    f"Initial position magnitude: {np.linalg.norm(prop.initial_state()[:3]) / 1e3:.1f} km"
)
```


### From 3-Line Elements (3LE)

Three-line TLE format includes an optional satellite name on the first line.


```python
import brahe as bh

bh.initialize_eop()

# 3-line TLE with satellite name
name = "ISS (ZARYA)"
line1 = "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927"
line2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537"

# Create propagator with satellite name
prop = bh.SGPPropagator.from_3le(name, line1, line2, 60.0)

print(f"Satellite name: {prop.satellite_name}")
print(f"NORAD ID: {prop.norad_id}")
```


### Configuring Output Format

By default, SGP4 outputs states in ECI Cartesian coordinates. Use `with_output_format()` to configure the output frame and representation.


```python
import brahe as bh

bh.initialize_eop()

line1 = "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927"
line2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537"

# Create with ECEF Cartesian output
prop_ecef = bh.SGPPropagator.from_tle(line1, line2, 60.0)
prop_ecef.set_output_format(bh.OrbitFrame.ECEF, bh.OrbitRepresentation.CARTESIAN, None)

# Or with Keplerian output (ECI only)
prop_kep = bh.SGPPropagator.from_tle(line1, line2, 60.0)
prop_kep.set_output_format(
    bh.OrbitFrame.ECI, bh.OrbitRepresentation.KEPLERIAN, bh.AngleFormat.DEGREES
)

# Propagate to 1 hour after epoch
dt = 3600.0
prop_ecef.propagate_to(prop_ecef.epoch + dt)
prop_kep.propagate_to(prop_kep.epoch + dt)
print(f"ECEF position (km): {prop_ecef.current_state()[:3] / 1e3}")
state_kep = prop_kep.current_state()
print(
    f"Keplerian elements: [{state_kep[0]:.1f} km, {state_kep[1]:.4f}, {state_kep[2]:.4f}, "
    f"{state_kep[3]:.4f} deg, {state_kep[4]:.4f} deg, {state_kep[5]:.4f} deg]"
)
```


## Stepping Through Time

The SGP propagator uses the same stepping interface as other propagators through the `OrbitPropagator` trait.

### Single and Multiple Steps


```python
import brahe as bh

bh.initialize_eop()

line1 = "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927"
line2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537"
prop = bh.SGPPropagator.from_tle(line1, line2, 60.0)

# Single step (60 seconds)
prop.step()
print(f"After 1 step: {prop.current_epoch()}")

# Multiple steps
prop.propagate_steps(10)
print(f"After 11 total steps: {len(prop.trajectory)} states")

# Step by custom duration
prop.step_by(120.0)
print(f"After custom step: {prop.current_epoch()}")
```


### Propagate to Target Epoch


```python
import brahe as bh

bh.initialize_eop()

line1 = "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927"
line2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537"
prop = bh.SGPPropagator.from_tle(line1, line2, 60.0)

# Propagate to specific epoch
target = prop.epoch + 7200.0  # 2 hours later
prop.propagate_to(target)

print(f"Target epoch: {target}")
print(f"Current epoch: {prop.current_epoch()}")
print(f"Trajectory contains {len(prop.trajectory)} states")
```


## Direct State Queries

The SGP propagator implements the `StateProvider` trait, allowing direct state computation at arbitrary epochs without stepping. Because SGP4 uses closed-form solutions, state queries are efficient and do not require building a trajectory.

### Single Epoch Queries


```python
import brahe as bh

bh.initialize_eop()

line1 = "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927"
line2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537"
prop = bh.SGPPropagator.from_tle(line1, line2, 60.0)

# Query state 1 orbit later (doesn't add to trajectory)
query_epoch = prop.epoch + 5400.0  # ~90 minutes

state_eci = prop.state_eci(query_epoch)  # ECI Cartesian
state_ecef = prop.state_ecef(query_epoch)  # ECEF Cartesian
state_kep = prop.state_koe_osc(
    query_epoch, bh.AngleFormat.DEGREES
)  # Osculating Keplerian

print(
    f"ECI position: [{state_eci[0] / 1e3:.1f}, {state_eci[1] / 1e3:.1f}, "
    f"{state_eci[2] / 1e3:.1f}] km"
)
print(f"Osculating semi-major axis: {state_kep[0] / 1e3:.1f} km")
```


### Batch Queries


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

line1 = "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927"
line2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537"
prop = bh.SGPPropagator.from_tle(line1, line2, 60.0)

# Generate states for multiple orbits
orbital_period = 5400.0  # Approximate ISS period (seconds)
query_epochs = [prop.epoch + i * orbital_period for i in range(5)]
states_eci = prop.states_eci(query_epochs)

print(f"Generated {len(states_eci)} states over {len(query_epochs)} orbits")
for i, state in enumerate(states_eci):
    altitude = (np.linalg.norm(state[:3]) - bh.R_EARTH) / 1e3
    print(f"  Orbit {i}: altitude = {altitude:.1f} km")
```


### Special: PEF Frame

SGP4 natively outputs states in the TEME (True Equator Mean Equinox) frame. For specialized applications, you can access states in the intermediate PEF (Pseudo-Earth-Fixed) frame:


```python
import brahe as bh

bh.initialize_eop()

line1 = "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927"
line2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537"
prop = bh.SGPPropagator.from_tle(line1, line2, 60.0)

# Get state in PEF frame (TEME rotated by GMST)
state_pef = prop.state_pef(prop.epoch)
print(f"PEF position: {state_pef[:3] / 1e3}")
```


## Extracting Orbital Elements from TLE

The propagator can extract Keplerian orbital elements directly from the TLE data:


```python
import brahe as bh

bh.initialize_eop()

line1 = "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927"
line2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537"
prop = bh.SGPPropagator.from_tle(line1, line2, 60.0)

# Extract Keplerian elements from TLE
elements_deg = prop.get_elements(bh.AngleFormat.DEGREES)
elements_rad = prop.get_elements(bh.AngleFormat.RADIANS)

print(f"Semi-major axis: {elements_deg[0] / 1e3:.1f} km")
print(f"Eccentricity: {elements_deg[1]:.6f}")
print(f"Inclination: {elements_deg[2]:.4f} degrees")
print(f"RAAN: {elements_deg[3]:.4f} degrees")
print(f"Argument of perigee: {elements_deg[4]:.4f} degrees")
print(f"Mean anomaly: {elements_deg[5]:.4f} degrees")
```


## Trajectory Management

SGP propagators support the same trajectory management as Keplerian propagators, including frame conversions and memory management.

### Memory Management


```python
import brahe as bh

bh.initialize_eop()

line1 = "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927"
line2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537"
prop = bh.SGPPropagator.from_tle(line1, line2, 60.0)

# Keep only 50 most recent states for memory efficiency
prop.set_eviction_policy_max_size(50)

# Propagate many steps
prop.propagate_steps(200)
print(f"Trajectory length: {len(prop.trajectory)}")  # Will be 50

# Alternative: Keep states within 30 minutes of current
prop.reset()
prop.set_eviction_policy_max_age(1800.0)  # 1800 seconds = 30 minutes
prop.propagate_steps(200)
print(f"Trajectory length with age policy: {len(prop.trajectory)}")
```


## Limitations and Considerations

### Immutable Initial Conditions

Unlike the Keplerian propagator, SGP4 initial conditions are derived from the TLE and **cannot be changed**. Attempting to call `set_initial_conditions()` will result in a panic:


```
import brahe as bh
import numpy as np

line1 = "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927"
line2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537"
prop = bh.SGPPropagator.from_tle(line1, line2, 60.0)

# This will raise an error - SGP initial conditions come from TLE
# prop.set_initial_conditions(...)  # Don't do this!

# To use different orbital elements, create a KeplerianPropagator instead
```

## Identity Tracking

Like Keplerian propagators, SGP propagators support identity tracking:


```python
import brahe as bh

bh.initialize_eop()

line0 = "ISS (ZARYA)"
line1 = "1 25544U 98067A   08264.51782528 -.00002182  00000-0 -11606-4 0  2927"
line2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391563537"

# Create propagator and set identity
prop = bh.SGPPropagator.from_3le(line0, line1, line2, 60.0)

print(f"Name: {prop.get_name()}")
print(f"ID: {prop.get_id()}")
print(f"NORAD ID from TLE: {prop.norad_id}")
```


---

## See Also

- [Orbit Propagation Overview](index.md) - Propagation concepts and trait hierarchy
- [Keplerian Propagation](keplerian_propagation.md) - Analytical two-body propagator
- [Trajectories](../trajectories/index.md) - Trajectory storage and operations
- [Two-Line Elements](../orbits/two_line_elements.md) - Working with TLE data
- [Ephemeris Data Sources](../ephemeris/index.md) - Querying live satellite data from CelesTrak and Space-Track
- [SGPPropagator API Reference](../../library_api/propagators/sgp_propagator.md)