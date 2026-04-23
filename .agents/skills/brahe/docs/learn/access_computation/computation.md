# Access Computation

Access computation finds time windows when satellites can observe or communicate with ground locations, subject to geometric and operational constraints. Brahe provides the `location_accesses()` function as the primary function for finding accesses, with optional search configuration parameters to tune performance and accuracy.

## Basic Workflow

The simplest access computation requires: a location, a propagator, time bounds, and a constraint.


```python
import brahe as bh

# Initialize Earth orientation data
bh.initialize_eop()

# Define ground location (San Francisco, CA)
location = bh.PointLocation(-122.4194, 37.7749, 0.0).with_name("San Francisco")

# Create propagator from TLE (example for ISS)
tle_line1 = "1 25544U 98067A   25306.42331346  .00010070  00000-0  18610-3 0  9999"
tle_line2 = "2 25544  51.6344 342.0717 0004969   8.9436 351.1640 15.49700017536601"
propagator = bh.SGPPropagator.from_tle(tle_line1, tle_line2, 60.0).with_name("ISS")

# Define time window (7 days starting from epoch)
epoch_start = bh.Epoch(2025, 11, 2, 0, 0, 0.0, 0.0)
epoch_end = epoch_start + 7 * 86400.0

# Define constraint (minimum 10° elevation)
constraint = bh.ElevationConstraint(min_elevation_deg=10.0)

# Compute access windows
windows = bh.location_accesses(location, propagator, epoch_start, epoch_end, constraint)

# Process results
print(f"Found {len(windows)} access windows")
for i, window in enumerate(windows[:3], 1):
    duration_min = window.duration / 60.0
    print(f"\nWindow {i}:")
    print(f"  Start: {window.window_open}")
    print(f"  End:   {window.window_close}")
    print(f"  Duration: {duration_min:.2f} minutes")

    # Access computed properties
    elev_max = window.properties.elevation_max
    print(f"  Max elevation: {elev_max:.1f}°")
```


## Multiple Locations and Satellites

Compute access for multiple locations and satellites simultaneously:


```python
import brahe as bh
from collections import defaultdict

bh.initialize_eop()

# Define multiple ground stations
locations = [
    bh.PointLocation(-122.4194, 37.7749, 0.0).with_name("San Francisco"),
    bh.PointLocation(-71.0589, 42.3601, 0.0).with_name("Boston"),
    bh.PointLocation(15.4038, 78.2232, 458.0).with_name("Svalbard"),
]

# Define multiple satellites (from TLEs, epoch: 2024-01-01)
tle_data = [
    # ISS - LEO, 51.6° inclination
    (
        "1 25544U 98067A   25306.42331346  .00010070  00000-0  18610-3 0  9999",
        "2 25544  51.6344 342.0717 0004969   8.9436 351.1640 15.49700017536601",
        "ISS",
    ),
    # Tiangong - LEO, 41.5° inclination
    (
        "1 48274U 21035A   25306.17586037  .00031797  00000-0  38131-3 0  9995",
        "2 48274  41.4666 263.0710 0006682 308.7013  51.3228 15.60215133257694",
        "Tiangong",
    ),
]

propagators = [
    bh.SGPPropagator.from_tle(line1, line2, 60.0).with_name(name)
    for line1, line2, name in tle_data
]

# Compute all location-satellite pairs (24 hours from TLE epoch)
epoch_start = bh.Epoch(2024, 1, 1, 12, 0, 0.0, 0.0)
epoch_end = epoch_start + 86400.0  # 24 hours
constraint = bh.ElevationConstraint(min_elevation_deg=10.0)

windows = bh.location_accesses(
    locations, propagators, epoch_start, epoch_end, constraint
)

# Results include windows for all location-satellite combinations
print(f"Total windows: {len(windows)}")

# Group by location
by_location = defaultdict(list)
for window in windows:
    by_location[window.location_name].append(window)

for loc_name, loc_windows in by_location.items():
    print(f"\n{loc_name}: {len(loc_windows)} windows")
```


## Algorithm Explanation

Brahe uses a two-step search algorithm to balance accuracy and performance:

### Phase 1: Coarse Search

The algorithm evaluates the constraint at regular time intervals (`initial_time_step`) across the entire search period. When the constraint transitions from `false` to `true`, a candidate access window has been found. This phase identifies periods of potential access quickly.

Optionally, adaptive stepping can be enabled to speed up the search by increasing by increasing the first step after an access window is found. The step size is based on a fraction of the satellite's orbital period (`adaptive_fraction`). For LEO satellites, this can significantly reduce the number of evaluations needed, as at most one access window occurs per orbit.

**Example:** With a 60-second time step over 24 hours, the algorithm performs ~1,440 constraint evaluations to identify candidate windows.

### Phase 2: Refinement

For each candidate window, the algorithm uses binary search to precisely locate the boundary times:

1. Start at the coarse boundary estimate
2. Take steps backward/forward at half the previous step size until the constraint changes
3. Evaluate constraint at each step
4. When constraint changes, reduce step size, change direction, and repeat
5. Continue until boundary is located to desired precision

## Configuration

The `AccessSearchConfig` struct controls algorithm behavior:


```python
import brahe as bh

bh.initialize_eop()

# Create custom configuration
config = bh.AccessSearchConfig(
    initial_time_step=60.0,  # Coarse search: 60-second steps
    adaptive_step=True,  # Enable adaptive refinement
    adaptive_fraction=0.75,  # Each step is 75% of orbital period
    parallel=True,  # Enable parallel processing
    num_threads=0,  # Auto-detect thread count
)

# Use custom config with location and propagator
location = bh.PointLocation(-122.4194, 37.7749, 0.0).with_name("San Francisco")
tle_line1 = "1 25544U 98067A   25306.42331346  .00010070  00000-0  18610-3 0  9999"
tle_line2 = "2 25544  51.6344 342.0717 0004969   8.9436 351.1640 15.49700017536601"
propagator = bh.SGPPropagator.from_tle(tle_line1, tle_line2, 60.0).with_name("ISS")

epoch_start = bh.Epoch(2025, 11, 2, 0, 0, 0.0, 0.0)
epoch_end = epoch_start + 86400.0  # 24 hours
constraint = bh.ElevationConstraint(min_elevation_deg=10.0)

windows = bh.location_accesses(
    location, propagator, epoch_start, epoch_end, constraint, config=config
)

print(f"Found {len(windows)} access windows with custom configuration")
print(
    f"Configuration: {config.initial_time_step}s time step, adaptive={config.adaptive_step}"
)
```


### Parameter Guidance

**`initial_time_step`** - Coarse search step size (seconds)

- **Smaller values** (10-60s): More accurate, slower, for complex constraints or short windows
- **Larger values** (60-180s): Faster, risk missing brief access windows
- **Rule of thumb**: Use 1/10th of expected minimum window duration

**`adaptive_step`** - Enable adaptive stepping to speed up coarse search

- **`true`**: Enabled, faster for LEO satellites with regular orbits
- **`false`**: Disabled, standard fixed-step search

**`adaptive_fraction`** - Fraction of orbital period for adaptive step size

- **Smaller values** (0.3-0.6): Smaller adaptive step, less risk of missing windows
- **Larger values** (0.6-0.8): Larger adaptive step, faster but riskier
- **Recommended**: 0.5-0.75 for LEO satellites

**`parallel`** - Enable parallel processing

- **`true`**: Process location-satellite pairs in parallel (recommended)
- **`false`**: Sequential processing, lower memory usage

**`num_threads`** - Thread pool size

- **0**: Auto-detect CPU cores (recommended)
- **N > 0**: Use exactly N threads for parallel work

---

## See Also

- [Locations](locations.md) - Ground location types and properties
- [Constraints](constraints.md) - Constraint system and composition
- [Tessellation](tessellation.md) - Dividing areas into satellite imaging tiles
- [Access Computation Index](index.md) - Overview and usage examples
- [Example: Predicting Ground Contacts](../../examples/ground_contacts.md) - Complete workflow
- [API Reference: Access Module](../../library_api/access/index.md) - Complete API documentation