# OrbitTrajectory

`OrbitTrajectory` is a specialized trajectory container for orbital mechanics that tracks reference frames (ECI/ECEF) and orbital representations (Cartesian/Keplerian). Unlike `Trajectory` which store frame-agnostic data, `OrbitTrajectory` understands orbital mechanics and enables automatic conversions between reference frames and representations.

Use `OrbitTrajectory` when:

- Working with orbital mechanics applications
- Need to convert between ECI and ECEF frames
- Need to convert between Cartesian and Keplerian representations
- Want frame/representation metadata tracked automatically
- Working with propagators that output orbital trajectories

`OrbitTrajectory` implements the `OrbitalTrajectory` trait in addition to `Trajectory` and `Interpolatable`, providing orbital-specific functionality on top of the standard trajectory interface.

## Initialization

### Empty Trajectory - Cartesian Representation 

For cartesian representation, the frame can be `ECI` or `ECEF`. The `AngleFormat` **must** be `None` for Cartesian representations


```python
import brahe as bh

bh.initialize_eop()

# Create trajectory in ECI frame, Cartesian representation
traj_eci = bh.OrbitTrajectory(
    6,  # State dimension (position + velocity)
    bh.OrbitFrame.ECI,
    bh.OrbitRepresentation.CARTESIAN,
    None,  # No angle format for Cartesian
)
print(f"Frame (str): {traj_eci.frame}")  # Output: ECI
print(
    f"Frame (repr): {repr(traj_eci.frame)}"
)  # Output: OrbitFrame(Earth-Centered Inertial)
print(f"Representation (str): {traj_eci.representation}")  # Output: Cartesian
print(
    f"Representation (repr): {repr(traj_eci.representation)}"
)  # Output: OrbitRepresentation(Cartesian)

# Create trajectory in ECEF frame, Cartesian representation
traj_ecef = bh.OrbitTrajectory(
    6, bh.OrbitFrame.ECEF, bh.OrbitRepresentation.CARTESIAN, None
)
print(f"Frame (str): {traj_ecef.frame}")  # Output: ECEF
print(
    f"Frame (repr): {repr(traj_ecef.frame)}"
)  # Output: OrbitFrame(Earth-Centered Earth-Fixed)
```


### Empty Trajectory - Keplerian Elements

To create an empty trajectory in Keplerian representation you **must** specify the frame as `ECI` and provide an `AngleFormat`.


```python
import brahe as bh

bh.initialize_eop()

# Create trajectory in ECI frame, Keplerian representation with radians
traj_kep_rad = bh.OrbitTrajectory(
    6,  # State dimension (6 orbital elements)
    bh.OrbitFrame.ECI,
    bh.OrbitRepresentation.KEPLERIAN,
    bh.AngleFormat.RADIANS,  # Required for Keplerian
)

# Create trajectory in ECI frame, Keplerian representation with degrees
traj_kep_deg = bh.OrbitTrajectory(
    6, bh.OrbitFrame.ECI, bh.OrbitRepresentation.KEPLERIAN, bh.AngleFormat.DEGREES
)
```


### From Existing Data

You can also initialize an `OrbitTrajectory` from existing epoch and state data:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Create epochs
epoch0 = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
epoch1 = epoch0 + 60.0
epoch2 = epoch0 + 120.0

# Create Cartesian states in ECI
state0 = np.array([bh.R_EARTH + 500e3, 0.0, 0.0, 0.0, 7600.0, 0.0])
state1 = np.array([bh.R_EARTH + 500e3, 456000.0, 0.0, -7600.0, 0.0, 0.0])
state2 = np.array([bh.R_EARTH + 500e3, 0.0, 0.0, 0.0, -7600.0, 0.0])

# Create trajectory from data
epochs = [epoch0, epoch1, epoch2]
states = np.array([state0, state1, state2])  # Flattened array
traj = bh.OrbitTrajectory.from_orbital_data(
    epochs, states, bh.OrbitFrame.ECI, bh.OrbitRepresentation.CARTESIAN, None
)

print(f"Trajectory length: {len(traj)}")
```


### From Propagator

The most common way to get an `OrbitTrajectory` from a propagator. All orbit propagators in Brahe have a `*.trajectory` attribute which is an `OrbitTrajectory`.

See the [Propagators](../orbit_propagation/index.md) section for more details on propagators.


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Define orbital elements for a 500 km circular orbit
a = bh.R_EARTH + 500e3
e = 0.001
i = 97.8  # Sun-synchronous
raan = 15.0
argp = 30.0
M = 0.0
oe = np.array([a, e, i, raan, argp, M])

# Create epoch and propagator
epoch = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
propagator = bh.KeplerianPropagator.from_keplerian(
    epoch, oe, bh.AngleFormat.DEGREES, 60.0
)

# Propagate for several steps
propagator.propagate_steps(10)

# Access the trajectory
traj = propagator.trajectory
print(f"Trajectory length: {len(traj)}")  # Output: 11 (initial + 10 steps)
print(f"Frame: {traj.frame}")  # Output: OrbitFrame.ECI
print(f"Representation: {traj.representation}")  # Output: Keplerian
```


## Frame Conversions

The key feature of `OrbitTrajectory` is automatic frame conversions of the trajectory data to different reference frames and representations. In particular, with a single method call you can convert between ECI and ECEF frames, and between Cartesian and Keplerian representations.

### Converting ECI to ECEF

Convert a trajectory from Earth-Centered Inertial (ECI) to Earth-Centered Earth-Fixed (ECEF):


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Create trajectory in ECI frame
traj_eci = bh.OrbitTrajectory(
    6, bh.OrbitFrame.ECI, bh.OrbitRepresentation.CARTESIAN, None
)

# Add states in ECI
epoch0 = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
for i in range(5):
    epoch = epoch0 + i * 60.0
    # Define state at epoch
    state_eci = np.array([bh.R_EARTH + 500e3, i * 100e3, 0.0, 0.0, 7600.0, 0.0])
    traj_eci.add(epoch, state_eci)

print(f"Original frame: {traj_eci.frame}")
print(f"Original representation: {traj_eci.representation}")

# Convert all states in trajectory to ECEF
traj_ecef = traj_eci.to_ecef()

print(f"\nConverted frame: {traj_ecef.frame}")
print(f"Converted representation: {traj_ecef.representation}")
print(f"Same number of states: {len(traj_ecef)}")

# Compare first states
_, state_eci = traj_eci.first()
_, state_ecef = traj_ecef.first()
print(
    f"\nFirst ECI state: [{state_eci[0]:.2f}, {state_eci[1]:.2f}, {state_eci[2]:.2f}] m"
)
print(
    f"First ECEF state: [{state_ecef[0]:.2f}, {state_ecef[1]:.2f}, {state_ecef[2]:.2f}] m"
)
```


### Converting ECEF to ECI

Convert from ECEF back to ECI:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Create trajectory in ECEF frame
traj_ecef = bh.OrbitTrajectory(
    6, bh.OrbitFrame.ECEF, bh.OrbitRepresentation.CARTESIAN, None
)

# Add dummy states in ECEF
epoch0 = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
for i in range(3):
    epoch = epoch0 + i * 60.0
    # Define state at epoch
    state_ecef = np.array([bh.R_EARTH + 500e3, 0.0, 0.0, 0.0, 0.0, 7600.0])
    traj_ecef.add(epoch, state_ecef)

print(f"Original frame: {traj_ecef.frame}")  # Output: OrbitFrame.ECEF

# Convert to ECI
traj_eci = traj_ecef.to_eci()

print(f"Converted frame: {traj_eci.frame}")  # Output: OrbitFrame.ECI
print(f"Trajectory length: {len(traj_eci)}")  # Output: 3

# Iterate over converted states
for epoch, state_eci in traj_eci:
    pos_mag = np.linalg.norm(state_eci[0:3])
    vel_mag = np.linalg.norm(state_eci[3:6])
    print(f"Epoch: {epoch}")
    print(f"  Position magnitude: {pos_mag / 1e3:.2f} km")
    print(f"  Velocity magnitude: {vel_mag:.2f} m/s")
```


### Round-Trip Frame Conversion

Convert from ECI to ECEF and back to verify consistency:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Create trajectory in ECI
traj_eci_original = bh.OrbitTrajectory(
    6, bh.OrbitFrame.ECI, bh.OrbitRepresentation.CARTESIAN, None
)

# Add a state
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)
state_original = np.array([bh.R_EARTH + 500e3, 0.0, 0.0, 0.0, 7600.0, 0.0])
traj_eci_original.add(epoch, state_original)

# Convert to ECEF and back to ECI
traj_ecef = traj_eci_original.to_ecef()
traj_eci_roundtrip = traj_ecef.to_eci()

# Compare original and round-trip states
_, state_roundtrip = traj_eci_roundtrip.first()
diff = np.abs(state_original - state_roundtrip)

print(f"Position difference: {np.linalg.norm(diff[0:3]):.6e} m")
print(f"Velocity difference: {np.linalg.norm(diff[3:6]):.6e} m/s")
```


### Converting Cartesian to Keplerian

Convert from Cartesian position/velocity to Keplerian orbital elements:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Create trajectory in ECI Cartesian
traj_cart = bh.OrbitTrajectory(
    6, bh.OrbitFrame.ECI, bh.OrbitRepresentation.CARTESIAN, None
)

# Add Cartesian states
epoch0 = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
for i in range(3):
    epoch = epoch0 + i * 300.0  # 5-minute intervals
    # Use orbital elements to create realistic Cartesian states
    oe = np.array([bh.R_EARTH + 500e3, 0.001, 97.8, 15.0, 30.0, i * 10.0])
    state_cart = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)
    traj_cart.add(epoch, state_cart)

print(f"Original representation: {traj_cart.representation}")

# Convert to Keplerian with degrees
traj_kep = traj_cart.to_keplerian(bh.AngleFormat.DEGREES)

print(f"Converted representation: {traj_kep.representation}")
print(f"Angle format: {traj_kep.angle_format}")

# Examine Keplerian elements
for epoch, oe in traj_kep:
    print(f"\nEpoch: {epoch}")
    print(f"  Semi-major axis: {oe[0] / 1e3:.2f} km")
    print(f"  Eccentricity: {oe[1]:.6f}")
    print(f"  Inclination: {oe[2]:.2f}°")
    print(f"  RAAN: {oe[3]:.2f}°")
    print(f"  Argument of perigee: {oe[4]:.2f}°")
    print(f"  Mean anomaly: {oe[5]:.2f}°")
```


### Converting with Different Angle Formats

Convert to Keplerian with different angle formats:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Create trajectory in ECI Cartesian
traj_cart = bh.OrbitTrajectory(
    6, bh.OrbitFrame.ECI, bh.OrbitRepresentation.CARTESIAN, None
)

# Add a state
epoch = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
oe = np.array([bh.R_EARTH + 500e3, 0.001, 0.9, 1.0, 0.5, 0.0])
state_cart = bh.state_koe_to_eci(oe, bh.AngleFormat.RADIANS)
traj_cart.add(epoch, state_cart)

# Convert to Keplerian with radians
traj_kep_rad = traj_cart.to_keplerian(bh.AngleFormat.RADIANS)
_, oe_rad = traj_kep_rad.first()

# Convert to Keplerian with degrees
traj_kep_deg = traj_cart.to_keplerian(bh.AngleFormat.DEGREES)
_, oe_deg = traj_kep_deg.first()

print("Radians version:")
print(f"  Inclination: {oe_rad[2]:.6f} rad = {np.degrees(oe_rad[2]):.2f}°")

print("\nDegrees version:")
print(f"  Inclination: {oe_deg[2]:.2f}°")
```


## Combined Frame and Representation Conversions

Every conversion method returns a new `OrbitTrajectory` instance, so you can chain conversions together if desired:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Start with ECI Cartesian trajectory
traj_eci_cart = bh.OrbitTrajectory(
    6, bh.OrbitFrame.ECI, bh.OrbitRepresentation.CARTESIAN, None
)

# Add states
epoch = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
oe = np.array([bh.R_EARTH + 500e3, 0.001, 0.9, 1.0, 0.5, 0.0])
state_cart = bh.state_koe_to_eci(oe, bh.AngleFormat.RADIANS)
traj_eci_cart.add(epoch, state_cart)

print("Original:")
print(f"  Frame: {traj_eci_cart.frame}")
print(f"  Representation: {traj_eci_cart.representation}")

# Convert to ECEF frame (stays Cartesian)
traj_ecef_cart = traj_eci_cart.to_ecef()
print("\nAfter to_ecef():")
print(f"  Frame: {traj_ecef_cart.frame}")
print(f"  Representation: {traj_ecef_cart.representation}")

# Convert back to ECI
traj_eci_cart2 = traj_ecef_cart.to_eci()
print("\nAfter to_eci():")
print(f"  Frame: {traj_eci_cart2.frame}")
print(f"  Representation: {traj_eci_cart2.representation}")

# Convert to Keplerian (in ECI frame)
traj_eci_kep = traj_eci_cart2.to_keplerian(bh.AngleFormat.DEGREES)
print("\nAfter to_keplerian():")
print(f"  Frame: {traj_eci_kep.frame}")
print(f"  Representation: {traj_eci_kep.representation}")
print(f"  Angle format: {traj_eci_kep.angle_format}")
```


## Standard Trajectory Operations

`OrbitTrajectory` supports all standard trajectory operations since it implements the `Trajectory` and `Interpolatable` traits:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Create trajectory
traj = bh.OrbitTrajectory(6, bh.OrbitFrame.ECI, bh.OrbitRepresentation.CARTESIAN, None)

# Add states
epoch0 = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
for i in range(10):
    epoch = epoch0 + i * 60.0
    oe = np.array([bh.R_EARTH + 500e3, 0.001, 0.9, 1.0, 0.5, i * 0.1])
    state = bh.state_koe_to_eci(oe, bh.AngleFormat.RADIANS)
    traj.add(epoch, state)

# Query properties
print(f"Length: {len(traj)}")
print(f"Timespan: {traj.timespan():.1f} seconds")
print(f"Start epoch: {traj.start_epoch()}")
print(f"End epoch: {traj.end_epoch()}")

# Interpolate at intermediate time
interp_epoch = epoch0 + 45.0
interp_state = traj.interpolate(interp_epoch)
print(f"\nInterpolated state at {interp_epoch}:")
print(f"  Position (km): {interp_state[0:3] / 1e3}")
print(f"  Velocity (m/s): {interp_state[3:6]}")

# Iterate over states
for i, (epoch, state) in enumerate(traj):
    if i < 2:  # Just show first two
        print(
            f"State {i}: Epoch={epoch}, Position magnitude={np.linalg.norm(state[0:3]) / 1e3:.2f} km"
        )
```


## Practical Workflow Example

A complete example showing propagation, frame conversion, and analysis:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# 1. Define orbit and create propagator
a = bh.R_EARTH + 500e3  # 500 km altitude
e = 0.001  # Nearly circular
i = 97.8  # Sun-synchronous
raan = 15.0
argp = 30.0
M = 0.0
oe = np.array([a, e, i, raan, argp, M])

epoch = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
propagator = bh.KeplerianPropagator.from_keplerian(
    epoch, oe, bh.AngleFormat.DEGREES, 60.0
)

# 2. Propagate for one orbit period
period = bh.orbital_period(a)
end_epoch = epoch + period
propagator.propagate_to(end_epoch)

# 3. Get trajectory in ECI Cartesian
traj_eci = propagator.trajectory
print(f"Propagated {len(traj_eci)} states over {traj_eci.timespan() / 60:.1f} minutes")

# 4. Convert to ECEF to analyze ground track
traj_ecef = traj_eci.to_ecef()
print("\nGround track in ECEF frame:")
for i, (epoch, state_ecef) in enumerate(traj_ecef):
    if i % 10 == 0:  # Sample every 10 states
        # Convert ECEF to geodetic for latitude/longitude
        lat, lon, alt = bh.position_ecef_to_geodetic(
            state_ecef[0:3], bh.AngleFormat.DEGREES
        )
        print(f"  {epoch}: Lat={lat:6.2f}°, Lon={lon:7.2f}°, Alt={alt / 1e3:6.2f} km")

# 5. Convert to Keplerian to analyze orbital evolution
traj_kep = traj_eci.to_keplerian(bh.AngleFormat.DEGREES)
first_oe = traj_kep.state_at_idx(0)
last_oe = traj_kep.state_at_idx(len(traj_kep) - 1)

print("\nOrbital element evolution:")
print(f"  Semi-major axis: {first_oe[0] / 1e3:.2f} km → {last_oe[0] / 1e3:.2f} km")
print(f"  Eccentricity: {first_oe[1]:.6f} → {last_oe[1]:.6f}")
print(f"  Inclination: {first_oe[2]:.2f}° → {last_oe[2]:.2f}°")
print(f"  True anomaly: {first_oe[5]:.2f}° → {last_oe[5]:.2f}°")
```


---

## See Also

- [Trajectories Overview](index.md) - Trait hierarchy and implementation guide
- [Trajectory](trajectory.md) - Dynamic-dimension trajectory
- [OrbitTrajectory API Reference](../../library_api/trajectories/orbit_trajectory.md)