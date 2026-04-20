# Access Properties

Access properties are geometric and temporal measurements computed for each access window. Brahe automatically calculates core properties during access searches, and provides both built-in and custom property computers for mission-specific analysis.

## Core Properties

Brahe automatically computes these temporal and geometric properties for every access window:

| Name | Type | Description |
|------|------|-------------|
| `window_open` | [`Epoch`](../../library_api/time/epoch.md) | UTC time when access window starts |
| `window_close` | [`Epoch`](../../library_api/time/epoch.md) | UTC time when access window ends |
| `duration` | `float` | Total duration of access window in seconds |
| `midtime` | [`Epoch`](../../library_api/time/epoch.md) | UTC time at midpoint of access window |
| `azimuth_open` | `float` | Azimuth angle from location to satellite at window start (degrees) |
| `azimuth_close` | `float` | Azimuth angle from location to satellite at window end (degrees) |
| `elevation_min` | `float` | Minimum elevation angle during access window (degrees) |
| `elevation_max` | `float` | Maximum elevation angle during access window (degrees) |
| `local_time` | `float` | Local solar time at window midpoint in seconds $\left[0, 86400\right)$ |
| `look_direction` | [`LookDirection`](../../library_api/access/enums.md#lookdirection) | Satellite look direction relative to velocity |
| `asc_dsc` | [`AscDsc`](../../library_api/access/enums.md#ascdsc) | Pass classification based on satellite motion |

Core properties are attributes of the `AccessWindow` object returned by access computations and can be accessed directly like `window.window_open` or `window.elevation_max`.

Below are examples of accessing core properties in Python and Rust.


```python
import brahe as bh

bh.initialize_eop()

# Create location (San Francisco area)
location = bh.PointLocation(-122.4194, 37.7749, 0.0)

# Create propagator from TLE (ISS example)
tle_line1 = "1 25544U 98067A   25306.42331346  .00010070  00000-0  18610-3 0  9999"
tle_line2 = "2 25544  51.6344 342.0717 0004969   8.9436 351.1640 15.49700017536601"
propagator = bh.SGPPropagator.from_tle(tle_line1, tle_line2, 60.0)

# Define time period (24 hours from epoch)
epoch_start = bh.Epoch.from_datetime(2025, 11, 2, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
epoch_end = epoch_start + 86400.0

# Create elevation constraint
constraint = bh.ElevationConstraint(min_elevation_deg=10.0)

# Compute access windows
windows = bh.location_accesses(
    [location], [propagator], epoch_start, epoch_end, constraint
)

# Access core properties from first window
if windows:
    window = windows[0]
    props = window.properties

    print("Window ")
    t_start = window.window_open
    t_end = window.window_close
    print(f"  Start: {t_start}")
    print(f"  End:   {t_end}")
    print(f"  Duration: {window.duration:.1f} seconds")
    print(f"  Midtime: {window.midtime}")

    print("\nProperties:")

    # Azimuth values (open and close)
    az_open = props.azimuth_open
    az_close = props.azimuth_close
    print(f"  Azimuth - Min: {az_open:.1f}°, Max: {az_close:.1f}°")

    # Elevation range (min and max)
    elev_min = props.elevation_min
    elev_max = props.elevation_max
    print(f"  Elevation - Min: {elev_min:.1f}°, Max: {elev_max:.1f}°")

    # Off-nadir range (min and max)
    off_nadir_min = props.off_nadir_min
    off_nadir_max = props.off_nadir_max
    print(f"  Off-nadir - Min: {off_nadir_min:.1f}°, Max: {off_nadir_max:.1f}°")

    # Local solar time at midpoint
    local_time = props.local_time
    hours = int(local_time // 3600)
    minutes = (local_time - hours * 3600) / 60
    print(f"  Local time: {hours:02d}:{minutes:02.2f}")

    # Look direction
    look = props.look_direction
    print(f"  Look direction: {look}")

    # Ascending/Descending
    asc_dsc = props.asc_dsc
    print(f"  Ascending/Descending: {asc_dsc}")
```


## Property Computers

Property computers allow users to extend the access computation system to define and compute custom properties for each access window beyond the core set. These computations are performed after access windows are identified and refined. 

Python users can implement property computers by subclassing [`AccessPropertyComputer`](../../library_api/access/properties.md#accesspropertycomputer), while in Rust you implement the `AccessPropertyComputer` trait. These traits require the implementation of the `sampling_config` and `compute` methods. `sampling_config` defines how satellite states are sampled during the access window, and `compute` performs the actual property calculation using those sampled states.

Brahe defines a few built-in property computers for common use cases, and users can create custom property computers for application-specific needs.

## Sampling Configuration

Property computers use [`SamplingConfig`](../../library_api/access/properties.md#samplingconfig) to determine when satellite states are sampled within the access window. That is, what `epoch, state` pairs are provided to the computer for its calculations.

You can choose from several sampling modes:

- `relative_points([0.0, 0.5, 1.0])` - Samples at specified fractions of the window duration with 0.0 being the start and 1.0 being the end
- `fixed_count(n)` - Samples a fixed number of evenly spaced points within the window
- `fixed_interval(interval, offset)` - Samples at regular time intervals (defined by seconds between samples) throughout the window with an optional offset
- `midpoint` - Samples only at the midpoint of the window

This allows you to compute time-series data at specific intervals or points.

### Sampling Modes


```python
import brahe as bh

# Single sample at window midpoint (default)
config = bh.SamplingConfig.midpoint()
print(f"Midpoint: {config}")

# Specific relative points [0.0, 1.0] from window start to end
config = bh.SamplingConfig.relative_points([0.0, 0.25, 0.5, 0.75, 1.0])
print(f"Relative points: {config}")

# Fixed time interval in seconds
config = bh.SamplingConfig.fixed_interval(1.0, offset=0.0)  # 1 second
print(f"Fixed interval (1s): {config}")

# Fixed number of evenly-spaced points
config = bh.SamplingConfig.fixed_count(50)
print(f"Fixed count (50): {config}")
```


## Built-in Property Computers

Brahe provides three commonly-used property computers optimized in Rust:

### DopplerComputer

Computes Doppler frequency shifts for uplink and/or downlink communications:


```python
import brahe as bh

bh.initialize_eop()

# S-band downlink only (8.4 GHz)
doppler = bh.DopplerComputer(
    uplink_frequency=None,
    downlink_frequency=8.4e9,
    sampling_config=bh.SamplingConfig.fixed_interval(0.1, 0.0),  # 0.1 seconds
)
print(f"Downlink only: {doppler}")

# Both uplink (2.0 GHz) and downlink (8.4 GHz)
doppler = bh.DopplerComputer(
    uplink_frequency=2.0e9,
    downlink_frequency=8.4e9,
    sampling_config=bh.SamplingConfig.fixed_count(100),
)
print(f"Both frequencies: {doppler}")

# Create a simple scenario to demonstrate usage
# ISS orbit
tle_line1 = "1 25544U 98067A   25306.42331346  .00010070  00000-0  18610-3 0  9999"
tle_line2 = "2 25544  51.6344 342.0717 0004969   8.9436 351.1640 15.49700017536601"
propagator = bh.SGPPropagator.from_tle(tle_line1, tle_line2, 60.0).with_name("ISS")

epoch_start = propagator.epoch
epoch_end = epoch_start + 24 * 3600.0  # 24 hours

# Ground station (lon, lat, alt)
location = bh.PointLocation(-74.0060, 40.7128, 0.0)

# Compute accesses with Doppler
constraint = bh.ElevationConstraint(min_elevation_deg=10.0)
windows = bh.location_accesses(
    location,
    propagator,
    epoch_start,
    epoch_end,
    constraint,
    property_computers=[doppler],
)

# Access computed properties
window = windows[0]
doppler_data = window.properties.additional["doppler_downlink"]
times = doppler_data["times"]  # Seconds from window start
values = doppler_data["values"]  # Hz
print(
    f"\nFirst pass downlink Doppler shift range: {min(values):.1f} to {max(values):.1f} Hz"
)
```


**Doppler Physics:**

- **Uplink**: $\Delta f = f_0\frac{v_{los}}{c - v_{los}}$ - Ground station pre-compensates transmit frequency
- **Downlink**: $\Delta f = -f_0\frac{v_{los}}{c}$ - Ground station adjusts receive frequency
- Where $v_{los}$ is the velocity of the object along the line of sight from the observer. With $v_{los} < 0$ when approaching and $v_{los} > 0$ when receding.

### RangeComputer

Computes slant range (distance) from the location to the satellite:


```python
import brahe as bh

bh.initialize_eop()

# Compute range at 50 evenly-spaced points
range_comp = bh.RangeComputer(sampling_config=bh.SamplingConfig.fixed_count(50))
print(f"Range computer: {range_comp}")


# Create a simple scenario to demonstrate usage
# ISS orbit
tle_line1 = "1 25544U 98067A   25306.42331346  .00010070  00000-0  18610-3 0  9999"
tle_line2 = "2 25544  51.6344 342.0717 0004969   8.9436 351.1640 15.49700017536601"
propagator = bh.SGPPropagator.from_tle(tle_line1, tle_line2, 60.0).with_name("ISS")

epoch_start = propagator.epoch
epoch_end = epoch_start + 24 * 3600.0  # 24 hours

# Ground station
location = bh.PointLocation(-74.0060, 40.7128, 0.0)

# Compute accesses with range
constraint = bh.ElevationConstraint(min_elevation_deg=10.0)
windows = bh.location_accesses(
    location,
    propagator,
    epoch_start,
    epoch_end,
    constraint,
    property_computers=[range_comp],
)

# Access computed properties
window = windows[0]
range_data = window.properties.additional["range"]
distances_m = range_data["values"]  # meters
distances_km = [d / 1000.0 for d in distances_m]
print(f"\nRange varies from {min(distances_km):.1f} to {max(distances_km):.1f} km")
```


### RangeRateComputer

Computes line-of-sight velocity (range rate) with the convention that positive values indicate increasing range (satellite receding) and negative values indicate decreasing range (satellite approaching):


```python
import brahe as bh

bh.initialize_eop()

# Compute range rate every 0.5 seconds
range_rate = bh.RangeRateComputer(
    sampling_config=bh.SamplingConfig.fixed_interval(0.5, 0.0)  # 0.5 seconds
)
print(f"Range rate computer: {range_rate}")

# Create a simple scenario to demonstrate usage
# ISS orbit
tle_line1 = "1 25544U 98067A   25306.42331346  .00010070  00000-0  18610-3 0  9999"
tle_line2 = "2 25544  51.6344 342.0717 0004969   8.9436 351.1640 15.49700017536601"
propagator = bh.SGPPropagator.from_tle(tle_line1, tle_line2, 60.0).with_name("ISS")

epoch_start = propagator.epoch
epoch_end = epoch_start + 24 * 3600.0  # 24 hours

# Ground station
location = bh.PointLocation(-74.0060, 40.7128, 0.0)

# Compute accesses with range rate
constraint = bh.ElevationConstraint(min_elevation_deg=10.0)
windows = bh.location_accesses(
    location,
    propagator,
    epoch_start,
    epoch_end,
    constraint,
    property_computers=[range_rate],
)

# Access computed properties
window = windows[0]
rr_data = window.properties.additional["range_rate"]
velocities_mps = rr_data["values"]  # m/s (positive=receding)
print(
    f"\nRange rate varies from {min(velocities_mps):.1f} to {max(velocities_mps):.1f} m/s"
)
print("Negative = approaching (decreasing distance)")
print("Positive = receding (increasing distance)")
```


## Custom Property Computers

You can also create your own property computer to compute application-specific properties values. The system will pre-sample the satellite state at the specified times defined by your [`SamplingConfig`](../../library_api/access/properties.md#samplingconfig), so you don't need to manually propagate the trajectory.

This section provides examples of custom property computers in both Python and Rust.

### Python Implementation

In python you subclass [`AccessPropertyComputer`](../../library_api/access/properties.md#accesspropertycomputer) and implement three methods:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()


class MaxSpeedComputer(bh.AccessPropertyComputer):
    """Computes maximum ground speed during access."""

    def sampling_config(self):
        # Sample every 0.5 seconds
        return bh.SamplingConfig.fixed_interval(0.5, 0.0)

    def compute(
        self, window, sample_times, sample_states_ecef, location_ecef, location_geodetic
    ):
        # Extract velocities from states
        velocities = sample_states_ecef[:, 3:6]
        speeds = np.linalg.norm(velocities, axis=1)
        max_speed = np.max(speeds)

        # Single value -> returns as scalar
        return {
            "max_ground_speed": max_speed,  # Will be stored as Scalar
        }

    def property_names(self):
        return ["max_ground_speed"]


# ISS orbit
tle_line1 = "1 25544U 98067A   25306.42331346  .00010070  00000-0  18610-3 0  9999"
tle_line2 = "2 25544  51.6344 342.0717 0004969   8.9436 351.1640 15.49700017536601"
propagator = bh.SGPPropagator.from_tle(tle_line1, tle_line2, 60.0).with_name("ISS")

epoch_start = propagator.epoch
epoch_end = epoch_start + 24 * 3600.0  # 24 hours

# Ground station
location = bh.PointLocation(-74.0060, 40.7128, 0.0)

# Compute with custom property
max_speed = MaxSpeedComputer()
constraint = bh.ElevationConstraint(min_elevation_deg=10.0)
windows = bh.location_accesses(
    location,
    propagator,
    epoch_start,
    epoch_end,
    constraint,
    property_computers=[max_speed],
)

for window in windows:
    speed = window.properties.additional["max_ground_speed"]
    print(f"Max speed: {speed:.1f} m/s")
```

### Combining Multiple Computers

Pass multiple computers to compute different properties simultaneously:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()


class MaxSpeedComputer(bh.AccessPropertyComputer):
    """Computes maximum ground speed during access."""

    def sampling_config(self):
        return bh.SamplingConfig.fixed_interval(0.5, 0.0)

    def compute(
        self, window, sample_times, sample_states_ecef, location_ecef, location_geodetic
    ):
        velocities = sample_states_ecef[:, 3:6]
        speeds = np.linalg.norm(velocities, axis=1)
        max_speed = np.max(speeds)
        return {"max_ground_speed": max_speed}

    def property_names(self):
        return ["max_ground_speed"]


# Mix built-in and custom computers
doppler = bh.DopplerComputer(
    uplink_frequency=None,
    downlink_frequency=2.2e9,
    sampling_config=bh.SamplingConfig.fixed_interval(0.1, 0.0),
)

range_comp = bh.RangeComputer(sampling_config=bh.SamplingConfig.midpoint())

custom_comp = MaxSpeedComputer()

# Setup scenario
# ISS orbit
tle_line1 = "1 25544U 98067A   25306.42331346  .00010070  00000-0  18610-3 0  9999"
tle_line2 = "2 25544  51.6344 342.0717 0004969   8.9436 351.1640 15.49700017536601"
propagator = bh.SGPPropagator.from_tle(tle_line1, tle_line2, 60.0).with_name("ISS")

epoch_start = propagator.epoch
epoch_end = epoch_start + 24 * 3600.0  # 24 hours

# Ground station
location = bh.PointLocation(-74.0060, 40.7128, 0.0)

# Compute with all property computers
constraint = bh.ElevationConstraint(min_elevation_deg=10.0)
windows = bh.location_accesses(
    location,
    propagator,
    epoch_start,
    epoch_end,
    constraint,
    property_computers=[doppler, range_comp, custom_comp],
)

# All properties available in results
window = windows[0]
props = window.properties.additional

doppler_data = props["doppler_downlink"]
range_data = props["range"]
max_speed = props["max_ground_speed"]

print(f"Doppler: {len(doppler_data['values'])} samples")
print(f"Range: {range_data / 1000:.1f} km")
print(f"Max speed: {max_speed:.1f} m/s")
```

### Rust Implementation

To implement a custom property computer in Rust, create a struct that implements the `AccessPropertyComputer` trait by defining the `sampling_config` and `compute` methods.


---

## See Also

- [Access Computation Overview](index.md)
- [Constraints](constraints.md)
- [Locations](locations.md)
- [Computation Configuration](computation.md)