# Event Detection

The numerical propagator includes an event detection system that identifies specific orbital conditions during propagation. Events are defined by user-configurable detectors that monitor the spacecraft state and trigger when certain criteria are met. They can also be coupled with event callbacks to respond to detected events in real-time.

When an event is detected, the propagator uses a bisection algorithm to precisely locate the event time within a specified tolerance. The detected events are logged and can be accessed after propagation. Users can also configure how an event will affect the propagation, such as stopping propagation or continuing without interruption.

Events provide an extensible mechanism for implementing complex mission scenarios, such as maneuver execution, autonomous operations, and other condition-based actions.

The library also provides a set of premade event detectors for common scenarios, which can be used directly or serve as templates for custom detectors. You can find more details about premade events in the [Premade Events](premade_events.md) documentation with a complete list of available types in the library API docuementation at [Premade Event Detectors](../../../library_api/events/premade.md).

## Event Types

Brahe provides three event fundamental event detector types:

| Type | Trigger Condition |
|------|-------------------|
| `TimeEvent` | Specific epoch reached |
| `ValueEvent` | Computed quantity crosses a given value |
| `BinaryEvent` | Boolean condition changes |


## Adding Event Detectors

Event detectors are added to the propagator before propagation:

```
prop = bh.NumericalOrbitPropagator(...)
prop.add_event_detector(event1)
prop.add_event_detector(event2)
prop.propagate_to(end_epoch)
```

Multiple detectors can be active simultaneously.

## Accessing Event Results

After propagation, detected events are available via the event log:

```
events = prop.event_log()
for event in events:
    print(f"Event '{event.name}' at {event.window_open}")
    print(f"  State: {event.entry_state}")
```

Each event record contains:

| Field | Description |
|-------|-------------|
| `name` | Event detector name |
| `window_open` | Epoch when event occurred |
| `window_close` | Same as window_open for instantaneous events |
| `entry_state` | State vector at event time |


## Time Events

Time events trigger at specific epochs. They're useful for scheduled operations like data collection windows, communication passes, or timed maneuvers.


```python
import numpy as np
import brahe as bh

# Initialize EOP and space weather data (required for NRLMSISE-00 drag model)
bh.initialize_eop()
bh.initialize_sw()

# Create initial epoch and state
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)
oe = np.array([bh.R_EARTH + 500e3, 0.001, 97.8, 15.0, 30.0, 45.0])
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

# Add time events at specific epochs
event_30min = bh.TimeEvent(epoch + 1800.0, "30-minute mark")
event_1hr = bh.TimeEvent(epoch + 3600.0, "1-hour mark")

# Add a terminal event that stops propagation
event_terminal = bh.TimeEvent(epoch + 5400.0, "90-minute stop").set_terminal()

prop.add_event_detector(event_30min)
prop.add_event_detector(event_1hr)
prop.add_event_detector(event_terminal)

# Propagate for 2 hours (will stop at 90 minutes due to terminal event)
prop.propagate_to(epoch + 7200.0)

# Check detected events
events = prop.event_log()
print(f"Detected {len(events)} events:")
for event in events:
    dt = event.window_open - epoch
    print(f"  '{event.name}' at t+{dt:.1f}s")

# Verify propagation stopped at terminal event
final_time = prop.current_epoch() - epoch
print(f"\nPropagation stopped at: t+{final_time:.1f}s (requested: t+7200s)")

# Validate
assert len(events) == 3  # All three events detected
assert abs(final_time - 5400.0) < 1.0  # Stopped at 90 min

print("\nExample validated successfully!")
```


## Value Events

Value events trigger when a user-defined function crosses a value value. This is the most flexible event type, enabling detection of arbitrary orbital conditions.

Value events are defined with a value function which accepts the current epoch and state vector, returning a scalar value.

### Event Direction

Value events can detect:

- `INCREASING` - Value crosses value from below
- `DECREASING` - Value crosses value from above
- `ANY` - Any value crossing

### Custom Value Functions

The value function receives the current epoch and state vector, returning a scalar value:


```python
import numpy as np
import brahe as bh

# Initialize EOP and space weather data (required for NRLMSISE-00 drag model)
bh.initialize_eop()
bh.initialize_sw()

# Create initial epoch and state
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)
oe = np.array([bh.R_EARTH + 500e3, 0.01, 45.0, 15.0, 30.0, 1.0])
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


# Define custom value function: detect when z-component crosses zero
# This detects equator crossings (ascending and descending node)
def z_position(epoch, state):
    """Return z-component of position (meters)."""
    return state[2]


# Create ValueEvent: detect when z crosses 0 (equator crossing)
# Ascending node: z goes from negative to positive (INCREASING)
ascending_node = bh.ValueEvent(
    "Ascending Node",
    z_position,
    0.0,  # target value
    bh.EventDirection.INCREASING,
)

# Descending node: z goes from positive to negative (DECREASING)
descending_node = bh.ValueEvent(
    "Descending Node",
    z_position,
    0.0,
    bh.EventDirection.DECREASING,
)

prop.add_event_detector(ascending_node)
prop.add_event_detector(descending_node)

# Propagate for 3 orbits
orbital_period = bh.orbital_period(oe[0])
prop.propagate_to(epoch + 3 * orbital_period)

# Check detected events
events = prop.event_log()
ascending = [e for e in events if "Ascending" in e.name]
descending = [e for e in events if "Descending" in e.name]

print("Equator crossings over 3 orbits:")
print(f"  Ascending nodes: {len(ascending)}")
print(f"  Descending nodes: {len(descending)}")

for event in events[:6]:  # Show first 6
    dt = event.window_open - epoch
    z = event.entry_state[2]
    print(f"  '{event.name}' at t+{dt:.1f}s (z={z:.1f} m)")

# Validate
assert len(ascending) == 3  # One per orbit
assert len(descending) == 3  # One per orbit

print("\nExample validated successfully!")
```


## Binary Events

Binary events detect when a boolean condition transitions between true and false. They use `EdgeType` to specify which transition to detect:

- `RISING_EDGE` - Condition becomes true (false → true)
- `FALLING_EDGE` - Condition becomes false (true → false)
- `ANY_EDGE` - Either transition

The binary condition function receives the current epoch and state vector, returning a boolean value.


```python
import numpy as np
import brahe as bh

# Initialize EOP data
bh.initialize_eop()

# Create initial epoch and state
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)
oe = np.array([bh.R_EARTH + 500e3, 0.01, 45.0, 15.0, 30.0, 45.0])
state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)


# Define condition function: check if spacecraft is in northern hemisphere
def in_northern_hemisphere(epoch, state):
    """Returns True if z-position is positive (northern hemisphere)."""
    return state[2] > 0


# Create binary events for hemisphere crossings
# Rising edge: false → true (entering northern hemisphere)
enter_north = bh.BinaryEvent(
    "Enter Northern",
    in_northern_hemisphere,
    bh.EdgeType.RISING_EDGE,
)

# Falling edge: true → false (exiting northern hemisphere)
exit_north = bh.BinaryEvent(
    "Exit Northern",
    in_northern_hemisphere,
    bh.EdgeType.FALLING_EDGE,
)

# Create propagator
prop = bh.NumericalOrbitPropagator(
    epoch,
    state,
    bh.NumericalPropagationConfig.default(),
    bh.ForceModelConfig.two_body(),
    None,
)

prop.add_event_detector(enter_north)
prop.add_event_detector(exit_north)

# Propagate for 2 orbits
orbital_period = bh.orbital_period(oe[0])
prop.propagate_to(epoch + 2 * orbital_period)

# Check detected events
events = prop.event_log()
enters = [e for e in events if "Enter" in e.name]
exits = [e for e in events if "Exit" in e.name]

print("Hemisphere crossings over 2 orbits:")
print(f"  Entered northern: {len(enters)} times")
print(f"  Exited northern:  {len(exits)} times")

print("\nEvent timeline:")
for event in events[:8]:  # First 8 events
    dt = event.window_open - epoch
    z_km = event.entry_state[2] / 1e3
    print(f"  t+{dt:7.1f}s: {event.name:16} (z = {z_km:+.1f} km)")

# Validate
assert len(enters) == 2  # Once per orbit
assert len(exits) == 2  # Once per orbit

print("\nExample validated successfully!")
```


---

## See Also

- [Numerical Propagation Overview](index.md) - Architecture and concepts
- [Premade Events](premade_events.md) - Built-in event types
- [Event Callbacks](event_callbacks.md) - Responding to detected events
- [Maneuvers](maneuvers.md) - Using events for orbit maneuvers
- [Numerical Orbit Propagator](numerical_orbit_propagator.md) - Propagator fundamentals