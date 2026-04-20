# Constraints

Constraints define the criteria that must be satisfied for satellite access to ground locations. Brahe provides a comprehensive constraint system with built-in geometric constraints, logical composition operators, and support for custom user-defined constraints.

A constraint evaluates to `true` when access conditions are met and `false` otherwise. During access computation, the algorithm searches for continuous time periods where constraints remain `true`, identifying these as access windows.

## Built-in Constraints

### Elevation Constraint

The most common constraint - requires satellites to be above a minimum elevation angle. This accounts for terrain obstructions, atmospheric effects, and antenna pointing limits.

**Basic elevation constraint:**


```python
import brahe as bh

# Require satellite to be at least 10 degrees above horizon
constraint = bh.ElevationConstraint(min_elevation_deg=10.0)

print(f"Created: {constraint}")
```


**With maximum elevation:**


```python
import brahe as bh

# Side-looking sensor with elevation range
constraint = bh.ElevationConstraint(min_elevation_deg=10.0, max_elevation_deg=80.0)

print(f"Created: {constraint}")
```


### Elevation Mask Constraint

Models azimuth-dependent elevation masks for terrain profiles, mountains, or buildings blocking low-elevation views in specific directions.


```python
import brahe as bh

# Define elevation mask: [(azimuth_deg, elevation_deg), ...]
# Azimuth clockwise from North (0-360)
mask_points = [
    (0.0, 5.0),  # North: 5° minimum
    (90.0, 15.0),  # East: 15° minimum (mountains)
    (180.0, 8.0),  # South: 8° minimum
    (270.0, 10.0),  # West: 10° minimum
    (360.0, 5.0),  # Back to North
]

constraint = bh.ElevationMaskConstraint(mask_points)

print(f"Created: {constraint}")
```


### Off-Nadir Constraint

Limits the off-nadir viewing angle for imaging satellites. Off-nadir angle is measured from the satellite's nadir (straight down) to the target location.

**Imaging payload:**


```python
import brahe as bh

# Imaging payload with 30° maximum off-nadir
constraint = bh.OffNadirConstraint(max_off_nadir_deg=30.0)

print(f"Created: {constraint}")
```


**Side-looking radar:**


```python
import brahe as bh

# Side-looking radar requiring specific geometry
constraint = bh.OffNadirConstraint(min_off_nadir_deg=20.0, max_off_nadir_deg=45.0)

print(f"Created: {constraint}")
```


### Local Time Constraint

Filters access windows by local solar time at the ground location. Useful for daylight-only imaging or night-time astronomy observations.

**Single time window:**


```python
import brahe as bh

# Daylight imaging: 8:00 AM to 6:00 PM local solar time
# Times in military format: HHMM
constraint = bh.LocalTimeConstraint(time_windows=[(800, 1800)])

print(f"Created: {constraint}")
```


**Multiple time windows:**


```python
import brahe as bh

# Multiple windows: dawn and dusk passes
constraint = bh.LocalTimeConstraint(time_windows=[(600, 800), (1800, 2000)])

print(f"Created: {constraint}")
```


**Using decimal hours:**


```python
import brahe as bh

# Alternative: specify in decimal hours
constraint = bh.LocalTimeConstraint.from_hours(time_windows=[(8.0, 18.0)])

print(f"Created: {constraint}")
```


**Local Solar Time**

Local solar time is based on the Sun's position relative to the location, not clock time zones. Noon (1200) is when the Sun is highest in the sky.

### Look Direction Constraint

Requires the satellite to look in a specific direction relative to its velocity vector - left, right, or either side.

**Left-looking:**


```python
import brahe as bh
from brahe import LookDirection

# Require left-looking geometry
constraint = bh.LookDirectionConstraint(allowed=LookDirection.LEFT)

print(f"Created: {constraint}")
```


### Ascending-Descending Constraint

Filters passes by whether the satellite is ascending (moving south-to-north) or descending (north-to-south) over the location.

**Ascending passes:**


```python
import brahe as bh
from brahe import AscDsc

# Only ascending passes
constraint = bh.AscDscConstraint(allowed=AscDsc.ASCENDING)

print(f"Created: {constraint}")
```


## Constraint Composition

Combine constraints using Boolean logic to express complex requirements.

### ConstraintAll (AND Logic)

All child constraints must be satisfied simultaneously:


```python
import brahe as bh

# Elevation > 10° AND daylight hours
elev = bh.ElevationConstraint(min_elevation_deg=10.0)
daytime = bh.LocalTimeConstraint(time_windows=[(800, 1800)])

constraint = bh.ConstraintAll(constraints=[elev, daytime])

print(f"Created: {constraint}")
```


### ConstraintAny (OR Logic)

At least one child constraint must be satisfied:


```python
import brahe as bh

# High elevation OR right-looking geometry
high_elev = bh.ElevationConstraint(min_elevation_deg=60.0)
right_look = bh.LookDirectionConstraint(allowed=bh.LookDirection.RIGHT)

constraint = bh.ConstraintAny(constraints=[high_elev, right_look])

print(f"Created: {constraint}")
```


### ConstraintNot (Negation)

Inverts a constraint - access occurs when the child constraint is NOT satisfied:


```python
import brahe as bh

# Avoid daylight (e.g., for night-time astronomy)
daytime = bh.LocalTimeConstraint(time_windows=[(600, 2000)])
night_only = bh.ConstraintNot(constraint=daytime)

print(f"Created: {night_only}")
```


### Complex Composition

Build complex logic by combining multiple constraints:


```python
import brahe as bh

# Complex constraint: (High elevation AND daylight)
# Note: Python API currently supports single-level composition
# For nested constraints, use Rust API with Box<dyn AccessConstraint>

# High elevation AND daylight
high_elev = bh.ElevationConstraint(min_elevation_deg=60.0)
daytime = bh.LocalTimeConstraint(time_windows=[(800, 1800)])
look_right = bh.LookDirectionConstraint(allowed=bh.LookDirection.RIGHT)

# Combine multiple constraints with AND
constraint = bh.ConstraintAll(constraints=[high_elev, daytime, look_right])

print(f"Created: {constraint}")
```


## Custom Constraints (Python)

Python users can create fully custom constraints by implementing the `AccessConstraintComputer` interface:

```python
import brahe as bh
import numpy as np


class MaxRangeConstraint(bh.AccessConstraintComputer):
    """Limit access to satellites within a maximum range."""

    def __init__(self):
        self.max_range_m = 2000.0 * 1000.0  # 2000 km in meters

    def evaluate(self, epoch, satellite_state_ecef, location_ecef):
        """Return True when constraint is satisfied"""
        # Compute range vector from location to satellite
        range_vec = satellite_state_ecef[:3] - location_ecef
        range_m = np.linalg.norm(range_vec)

        return range_m <= self.max_range_m

    def name(self):
        return f"MaxRange({self.max_range_m / 1000:.0f}km)"


# Use custom constraint
constraint = MaxRangeConstraint()

print(f"Created: {constraint.name()}")
```

**Custom Constraints in Rust**
Rust users implement the `AccessConstraint` trait directly. This provides maximum performance but requires recompiling the library.

---

## See Also

- [Locations](locations.md) - Ground location types
- [Computation](computation.md) - How constraints are evaluated during access search
- [API Reference: Constraints](../../library_api/access/constraints.md)
- [Example: Predicting Ground Contacts](../../examples/ground_contacts.md)
- [Example: Computing Imaging Opportunities](../../examples/imaging_opportunities.md)