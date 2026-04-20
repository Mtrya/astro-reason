# Premade Events

Brahe provides built-in event detectors for common orbital conditions. These premade events handle the underlying value function implementation, making it easy to detect frequently-needed conditions without writing custom detection logic.

## Event Categories

Premade events fall into four categories based on what they detect:

| Category | What They Detect | Event Type |
|----------|------------------|------------|
| **Orbital Elements** | value crossings of Keplerian elements | Value |
| **State-Derived** | Altitude, speed, geodetic position | Value |
| **Eclipse/Shadow** | Shadow transitions (umbra, penumbra, sunlit) | Binary |
| **Node Crossings** | Equatorial plane crossings | Value |

The distinction between **value events** and **binary events** is important:

- **Value events** detect when a continuously-varying quantity crosses a value (e.g., altitude = 400 km)
- **Binary events** detect when a boolean condition changes state (e.g., enters shadow)

## Orbital Element Events

Orbital element events detect when Keplerian elements cross value values. These are value events with configurable values and directions.

### Available Events

| Event | Element | Units |
|-------|---------|-------|
| `SemiMajorAxisEvent` | $a$ | meters |
| `EccentricityEvent` | $e$ | dimensionless |
| `InclinationEvent` | $i$ | degrees or radians |
| `ArgumentOfPerigeeEvent` | $\omega$ | degrees or radians |
| `MeanAnomalyEvent` | $M$ | degrees or radians |
| `EccentricAnomalyEvent` | $E$ | degrees or radians |
| `TrueAnomalyEvent` | $\nu$ | degrees or radians |
| `ArgumentOfLatitudeEvent` | $u = \omega + \nu$ | degrees or radians |

### Configuration

Orbital element events take up to four parameters:

- `value` - Target value to detect
- `name` - Identifier for the event in the event log
- `direction` - Which crossings to detect (`INCREASING`, `DECREASING`, or `ANY`)
- `angle_format` - For angle-based events: `AngleFormat.DEGREES` or `AngleFormat.RADIANS`

Non-angle events (`SemiMajorAxisEvent`, `EccentricityEvent`) omit the `angle_format` parameter.

### Example


```python
import numpy as np
import brahe as bh

# Initialize EOP and space weather data (required for NRLMSISE-00 drag model)
bh.initialize_eop()
bh.initialize_sw()

# Create initial epoch and state - orbit with inclination near value
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)
# SSO-like orbit
oe = np.array([bh.R_EARTH + 600e3, 0.001, 97.8, 0.0, 0.0, 0.0])
state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)
params = np.array([500.0, 2.0, 2.2, 2.0, 1.3])

# Create propagator
prop = bh.NumericalOrbitPropagator(
    epoch,
    state,
    bh.NumericalPropagationConfig.default(),
    bh.ForceModelConfig.default(),
    params,
)

# Add orbital element events
# Detect when inclination crosses 97.79 degrees (monitoring for stability)
inc_event = bh.InclinationEvent(
    97.79,  # value in degrees
    "Inc value",
    bh.EventDirection.ANY,
    bh.AngleFormat.DEGREES,
)

# Detect semi-major axis value (orbit decay monitoring)
sma_event = bh.SemiMajorAxisEvent(
    bh.R_EARTH + 599.5e3,  # value in meters
    "SMA value",
    bh.EventDirection.DECREASING,
)

prop.add_event_detector(inc_event)
prop.add_event_detector(sma_event)

# Propagate for 3 orbits
orbital_period = bh.orbital_period(oe[0])
prop.propagate_to(epoch + 3 * orbital_period)

# Check detected events
events = prop.event_log()
print(f"Detected {len(events)} orbital element events:")

for event in events:
    dt = event.window_open - epoch
    # Get current orbital elements
    r = event.entry_state[:3]
    v = event.entry_state[3:]
    alt = np.linalg.norm(r) - bh.R_EARTH
    print(f"  '{event.name}' at t+{dt:.1f}s (altitude: {alt / 1e3:.1f} km)")

# Count events by type
inc_events = [e for e in events if "Inc" in e.name]
sma_events = [e for e in events if "SMA" in e.name]

print(f"\nInclination value crossings: {len(inc_events)}")
print(f"SMA value crossings: {len(sma_events)}")

# The J2 perturbation causes slow variations - we may or may not cross values
# depending on the exact parameters, so we just validate the events work
print("\nExample completed successfully!")
```


### Applications

| Event | Use Cases |
|-------|-----------|
| `TrueAnomalyEvent` | Apoapsis detection ($\nu = 180°$), periapsis detection ($\nu = 0°$) |
| `SemiMajorAxisEvent` | Orbit decay monitoring, altitude maintenance |
| `EccentricityEvent` | Circularization detection, orbit stability |
| `InclinationEvent` | Plane change monitoring, SSO maintenance |

## State-Derived Events

State-derived events compute quantities from the instantaneous state vector rather than orbital elements.

### Available Events

| Event | Quantity | Units |
|-------|----------|-------|
| `AltitudeEvent` | Geodetic altitude (WGS84) | meters |
| `SpeedEvent` | Velocity magnitude | m/s |
| `LongitudeEvent` | Geodetic longitude | degrees or radians |
| `LatitudeEvent` | Geodetic latitude | degrees or radians |

### Configuration

State-derived events follow the same pattern as orbital element events:

- `value` - Target value to detect
- `name` - Identifier for the event in the event log
- `direction` - Which crossings to detect (`INCREASING`, `DECREASING`, or `ANY`)
- `angle_format` - For geodetic events: `AngleFormat.DEGREES` or `AngleFormat.RADIANS`

### Example: Altitude Event

The `AltitudeEvent` is one of the most commonly used premade events. It detects when a spacecraft crosses a specified geodetic altitude.


```python
import numpy as np
import brahe as bh

# Initialize EOP and space weather data (required for NRLMSISE-00 drag model)
bh.initialize_eop()
bh.initialize_sw()

# Create initial epoch and state - elliptical orbit
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)
# Elliptical orbit: 300 km perigee, 800 km apogee
oe = np.array([bh.R_EARTH + 550e3, 0.036, 45.0, 0.0, 0.0, 0.0])
state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)
params = np.array([500.0, 2.0, 2.2, 2.0, 1.3])

# Create propagator
prop = bh.NumericalOrbitPropagator(
    epoch,
    state,
    bh.NumericalPropagationConfig.default(),
    bh.ForceModelConfig.default(),
    params,
)

# Add altitude events
# Detect when crossing 500 km altitude (both directions)
event_500km = bh.AltitudeEvent(
    500e3,  # value altitude in meters
    "500km crossing",
    bh.EventDirection.ANY,  # Detect both increasing and decreasing
)

# Detect only when ascending through 600 km
event_600km_up = bh.AltitudeEvent(
    600e3,
    "600km ascending",
    bh.EventDirection.INCREASING,
)

prop.add_event_detector(event_500km)
prop.add_event_detector(event_600km_up)

# Propagate for 2 orbits
orbital_period = bh.orbital_period(oe[0])
prop.propagate_to(epoch + 2 * orbital_period)

# Check detected events
events = prop.event_log()
print(f"Detected {len(events)} altitude events:")

for event in events:
    dt = event.window_open - epoch
    alt = np.linalg.norm(event.entry_state[:3]) - bh.R_EARTH
    print(f"  '{event.name}' at t+{dt:.1f}s (altitude: {alt / 1e3:.1f} km)")

# Count events by type
crossings_500 = [e for e in events if "500km" in e.name]
crossings_600 = [e for e in events if "600km" in e.name]

print(f"\n500 km crossings (any direction): {len(crossings_500)}")
print(f"600 km ascending crossings: {len(crossings_600)}")

# Validate
assert len(crossings_500) >= 4  # At least 2 per orbit, 2 orbits
assert len(crossings_600) >= 2  # At least 1 per orbit (ascending only)

print("\nExample validated successfully!")
```


### Applications

| Use Case | Configuration |
|----------|---------------|
| Atmospheric interface detection | `AltitudeEvent(100e3, "Karman line", DECREASING)` |
| Re-entry monitoring | `AltitudeEvent(100e3, "Re-entry", DECREASING)` |
| Orbit raising trigger | `AltitudeEvent(target_alt, "Target", DECREASING)` |
| Perigee passage | `AltitudeEvent(perigee_alt, "Perigee", ANY)` |

## Eclipse/Shadow Events

Eclipse events detect shadow conditions using the conical shadow model. These are binary events that trigger on state transitions.

### Available Events

| Event | Condition | `RISING_EDGE` | `FALLING_EDGE` |
|-------|-----------|---------------|----------------|
| `EclipseEvent` | Any shadow (illumination < 1) | Enter eclipse | Exit eclipse |
| `UmbraEvent` | Full shadow (illumination = 0) | Enter umbra | Exit umbra |
| `PenumbraEvent` | Partial shadow (0 < illumination < 1) | Enter penumbra | Exit penumbra |
| `SunlitEvent` | Full sunlight (illumination = 1) | Exit eclipse | Enter eclipse |

### Configuration

Eclipse events take three parameters:

- `name` - Identifier for the event in the event log
- `edge_type` - Which transition to detect (`RISING_EDGE`, `FALLING_EDGE`, or `ANY_EDGE`)
- `ephemeris_source` - Sun position source (`None` for analytical, or `EphemerisSource.DE440s`/`DE440`)

### Example


```python
import numpy as np
import brahe as bh

# Initialize EOP and space weather data (required for NRLMSISE-00 drag model)
bh.initialize_eop()
bh.initialize_sw()

# Create initial epoch and state - LEO orbit
epoch = bh.Epoch.from_datetime(2024, 6, 21, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)
# LEO orbit with some inclination
oe = np.array([bh.R_EARTH + 500e3, 0.01, 45.0, 15.0, 30.0, 45.0])
state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)
params = np.array([500.0, 2.0, 2.2, 2.0, 1.3])

# Create propagator
prop = bh.NumericalOrbitPropagator(
    epoch,
    state,
    bh.NumericalPropagationConfig.default(),
    bh.ForceModelConfig.default(),
    params,
)

# Add eclipse events with different edge types
# Detect entry into eclipse (any shadow - umbra or penumbra)
eclipse_entry = bh.EclipseEvent("Eclipse Entry", bh.EdgeType.RISING_EDGE, None)

# Detect exit from eclipse
eclipse_exit = bh.EclipseEvent("Eclipse Exit", bh.EdgeType.FALLING_EDGE, None)

prop.add_event_detector(eclipse_entry)
prop.add_event_detector(eclipse_exit)

# Propagate for 5 orbits
orbital_period = bh.orbital_period(oe[0])
prop.propagate_to(epoch + 5 * orbital_period)

# Check detected events
events = prop.event_log()
print(f"Detected {len(events)} eclipse events:")

for event in events:
    dt = event.window_open - epoch
    print(f"  '{event.name}' at t+{dt:.1f}s")

# Count events by type
entries = [e for e in events if "Entry" in e.name]
exits = [e for e in events if "Exit" in e.name]

print(f"\nEclipse entries: {len(entries)}")
print(f"Eclipse exits: {len(exits)}")

# Calculate eclipse durations
if len(entries) > 0 and len(exits) > 0:
    # Find pairs of entry/exit events
    durations = []
    for i, entry in enumerate(entries):
        # Find next exit after this entry
        for exit_event in exits:
            if exit_event.window_open > entry.window_open:
                duration = exit_event.window_open - entry.window_open
                durations.append(duration)
                break

    if durations:
        avg_duration = sum(durations) / len(durations)
        print(
            f"\nAverage eclipse duration: {avg_duration:.1f}s ({avg_duration / 60:.1f} min)"
        )

# Validate - should have roughly equal entries and exits
assert abs(len(entries) - len(exits)) <= 1, "Entry/exit count mismatch"
assert len(entries) >= 4, "Expected at least 4 eclipse entries in 5 orbits"

print("\nExample validated successfully!")
```


### Ephemeris Sources

| Source | Description |
|--------|-------------|
| `LowPrecision` | Analytical approximation (fastest) |
| `DE440s` | JPL DE440s ephemeris (short-term, high precision) |
| `DE440` | JPL DE440 ephemeris (long-term, high precision) |

## Node Crossing Events

Node crossing events detect when a spacecraft passes through the equatorial plane. These are specialized value events with fixed values.

### Available Events

| Event | Trigger Condition | Direction |
|-------|-------------------|-----------|
| `AscendingNodeEvent` | Argument of latitude = 0 (northward crossing) | Increasing |
| `DescendingNodeEvent` | Argument of latitude = $\pi$ or $180$ (southward crossing) | Increasing |

### Configuration

Node events take only a name parameter:

```
asc_event = bh.AscendingNodeEvent("Ascending Node")
desc_event = bh.DescendingNodeEvent("Descending Node")
```

### Example


```python
import numpy as np
import brahe as bh

# Initialize EOP and space weather data (required for NRLMSISE-00 drag model)
bh.initialize_eop()
bh.initialize_sw()

# Create initial epoch and state - inclined orbit
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)
# Inclined orbit for clear node crossings
oe = np.array([bh.R_EARTH + 500e3, 0.01, 45.0, 15.0, 30.0, 45.0])
state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)
params = np.array([500.0, 2.0, 2.2, 2.0, 1.3])

# Create propagator
prop = bh.NumericalOrbitPropagator(
    epoch,
    state,
    bh.NumericalPropagationConfig.default(),
    bh.ForceModelConfig.default(),
    params,
)

# Add node crossing events
# Ascending node: spacecraft crosses equator heading north (argument of latitude = 0)
asc_event = bh.AscendingNodeEvent("Ascending Node")

# Descending node: spacecraft crosses equator heading south (argument of latitude = 180 deg)
desc_event = bh.DescendingNodeEvent("Descending Node")

prop.add_event_detector(asc_event)
prop.add_event_detector(desc_event)

# Propagate for 3 orbits
orbital_period = bh.orbital_period(oe[0])
prop.propagate_to(epoch + 3 * orbital_period)

# Check detected events
events = prop.event_log()
print(f"Detected {len(events)} node crossing events:")

for event in events:
    dt = event.window_open - epoch
    # Compute geodetic latitude at event
    r_eci = event.entry_state[:3]
    r_ecef = bh.position_eci_to_ecef(event.window_open, r_eci)
    geodetic = bh.position_ecef_to_geodetic(r_ecef, bh.AngleFormat.DEGREES)
    lat = geodetic[1]
    print(f"  '{event.name}' at t+{dt:.1f}s (latitude: {lat:.2f} deg)")

# Count events by type
ascending = [e for e in events if "Ascending" in e.name]
descending = [e for e in events if "Descending" in e.name]

print(f"\nAscending node crossings: {len(ascending)}")
print(f"Descending node crossings: {len(descending)}")

# Validate
assert len(ascending) >= 3  # At least 3 ascending in 3 orbits
assert len(descending) >= 3  # At least 3 descending in 3 orbits
```


### Applications

- Ground track analysis
- Orbit determination campaigns
- RAAN drift monitoring
- Conjunction screening at nodes

## Quick Reference

### All Premade Events

| Category | Event | Parameters |
|----------|-------|------------|
| **Eclipse/Shadow** | `EclipseEvent` | name, edge_type, ephemeris_source |
| | `UmbraEvent` | name, edge_type, ephemeris_source |
| | `PenumbraEvent` | name, edge_type, ephemeris_source |
| | `SunlitEvent` | name, edge_type, ephemeris_source |
| **Node Crossings** | `AscendingNodeEvent` | name |
| | `DescendingNodeEvent` | name |
| **Orbital Elements** | `SemiMajorAxisEvent` | value (m), name, direction |
| | `EccentricityEvent` | value, name, direction |
| | `InclinationEvent` | value, name, direction, angle_format |
| | `ArgumentOfPerigeeEvent` | value, name, direction, angle_format |
| | `MeanAnomalyEvent` | value, name, direction, angle_format |
| | `EccentricAnomalyEvent` | value, name, direction, angle_format |
| | `TrueAnomalyEvent` | value, name, direction, angle_format |
| | `ArgumentOfLatitudeEvent` | value, name, direction, angle_format |
| **State-Derived** | `AltitudeEvent` | value (m), name, direction |
| | `SpeedEvent` | value (m/s), name, direction |
| | `LongitudeEvent` | value, name, direction, angle_format |
| | `LatitudeEvent` | value, name, direction, angle_format |

### Parameter Types

**Value Events** (value crossing):

- `direction`: `EventDirection.INCREASING`, `EventDirection.DECREASING`, or `EventDirection.ANY`
- `angle_format`: `AngleFormat.DEGREES` or `AngleFormat.RADIANS` (angle-based events only)

**Binary Events** (boolean condition transitions):

- `edge_type`: `EdgeType.RISING_EDGE`, `EdgeType.FALLING_EDGE`, or `EdgeType.ANY_EDGE`
- `ephemeris_source`: `None` (low precision), `EphemerisSource.DE440s`, or `EphemerisSource.DE440`

---

## See Also

- [Event Detection](event_detection.md) - Core event detection concepts
- [Event Callbacks](event_callbacks.md) - Responding to detected events
- [Maneuvers](maneuvers.md) - Using events for orbit maneuvers