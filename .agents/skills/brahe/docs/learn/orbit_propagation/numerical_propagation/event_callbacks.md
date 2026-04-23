# Event Callbacks

Event callbacks allow you to respond to detected events during propagation. Callbacks can log information, inspect state, modify the spacecraft state (for impulsive maneuvers), or control propagation flow.

## Callback Function Signature

To define a callback, create a function matching the following signature:


```
def callback(epoch: Epoch, state: np.ndarray) -> tuple[np.ndarray, EventAction]:
    """
    Args:
        epoch: The epoch when the event occurred
        state: The spacecraft state vector at event time [x, y, z, vx, vy, vz]

    Returns:
        tuple: (new_state, action)
            - new_state: Modified state vector (or original if unchanged)
            - action: EventAction.CONTINUE or EventAction.STOP
    """
    # Process event...
    return (state, bh.EventAction.CONTINUE)
```

### EventAction Options

The callback return value includes an `EventAction` that controls propagation behavior:

| Action | Behavior |
|--------|----------|
| `CONTINUE` | Continue propagation after processing the event |
| `STOP` | Halt propagation immediately after the event |

#### When to Use STOP

Use `EventAction.STOP` when:

- A terminal condition has been reached (e.g., re-entry)
- The propagation goal has been achieved
- An error condition is detected
- You want to examine state at a specific event before deciding to continue

#### When to Use CONTINUE

Use `EventAction.CONTINUE` for:

- Logging and monitoring events
- Impulsive maneuvers (state changes but propagation continues)
- Intermediate waypoints
- Data collection triggers


## Defining Callbacks

Callbacks receive the event epoch and state, and return a tuple containing the (possibly modified) state and an action directive.

### Logging Callback

A simple callback that logs event information without modifying state:


```python
import numpy as np
import brahe as bh

# Initialize EOP data
bh.initialize_eop()

# Create initial epoch and state - elliptical orbit
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)
oe = np.array([bh.R_EARTH + 500e3, 0.01, 45.0, 15.0, 30.0, 45.0])
state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

# Track callback invocations
callback_count = 0


# Define a logging callback
def logging_callback(event_epoch, event_state):
    """Log event details without modifying state."""
    global callback_count
    callback_count += 1

    # Compute orbital elements at event time
    koe = bh.state_eci_to_koe(event_state, bh.AngleFormat.DEGREES)
    altitude = koe[0] - bh.R_EARTH

    print(f"  Event #{callback_count}:")
    print(f"    Epoch: {event_epoch}")
    print(f"    Altitude: {altitude / 1e3:.1f} km")
    print(f"    True anomaly: {koe[5]:.1f} deg")

    # Return unchanged state with CONTINUE action
    return (event_state, bh.EventAction.CONTINUE)


# Define a callback that stops propagation
def stop_callback(event_epoch, event_state):
    """Stop propagation when event occurs."""
    print(f"  Stopping at {event_epoch}")
    return (event_state, bh.EventAction.STOP)


# Create propagator
prop = bh.NumericalOrbitPropagator(
    epoch,
    state,
    bh.NumericalPropagationConfig.default(),
    bh.ForceModelConfig.two_body(),
    None,
)

# Create time event with logging callback
event_log = bh.TimeEvent(epoch + 1000.0, "Log Event").with_callback(logging_callback)
prop.add_event_detector(event_log)

# Create another time event
event_log2 = bh.TimeEvent(epoch + 2000.0, "Log Event 2").with_callback(logging_callback)
prop.add_event_detector(event_log2)

# Propagate for half an orbit
orbital_period = bh.orbital_period(oe[0])
print("Propagating with logging callbacks:")
prop.propagate_to(epoch + orbital_period / 2)

print(f"\nCallback invoked {callback_count} times")

# Now demonstrate STOP action
print("\nDemonstrating STOP action:")
prop2 = bh.NumericalOrbitPropagator(
    epoch,
    state,
    bh.NumericalPropagationConfig.default(),
    bh.ForceModelConfig.two_body(),
    None,
)

# Event that stops propagation at t+500s
stop_event = bh.TimeEvent(epoch + 500.0, "Stop Event").with_callback(stop_callback)
prop2.add_event_detector(stop_event)

# Try to propagate for one full orbit
prop2.propagate_to(epoch + orbital_period)

# Check where propagation actually stopped
actual_duration = prop2.current_epoch() - epoch
print(f"  Requested duration: {orbital_period:.1f}s")
print(f"  Actual duration: {actual_duration:.1f}s")
print(f"  Stopped early: {actual_duration < orbital_period}")

# Validate
assert callback_count == 2
assert actual_duration < orbital_period
```


## Attaching Callbacks to Events

Use the `with_callback()` method to attach a callback to any event detector:

```
# Create event
event = bh.TimeEvent(target_epoch, "My Event")

# Attach callback
event_with_callback = event.with_callback(my_callback_function)

# Add to propagator
prop.add_event_detector(event_with_callback)
```

The `with_callback()` method returns a new event detector with the callback attached, allowing method chaining.

## State Modification

Callbacks can modify the spacecraft state by returning a new state vector. This is the mechanism for implementing impulsive maneuvers.

### Modifying State

```
def velocity_change_callback(epoch, state):
    new_state = state.copy()

    # Add delta-v in velocity direction
    v = state[3:6]
    v_hat = v / np.linalg.norm(v)
    delta_v = 100.0  # m/s
    new_state[3:6] += delta_v * v_hat

    return (new_state, bh.EventAction.CONTINUE)
```

### Physical Consistency

When modifying state, ensure physical consistency:

- **Position changes** are unusual except for specific scenarios
- **Velocity changes** should respect momentum conservation for realistic maneuvers
- **Large changes** may cause numerical issues in subsequent integration steps

For complete impulsive maneuver examples, see [Maneuvers](maneuvers.md).

## Multiple Callbacks

Each event detector can have one callback. For multiple actions at the same event, either:

1. Perform all actions within a single callback
2. Create multiple event detectors at the same time/condition

```
# Single callback performing multiple actions
def multi_action_callback(epoch, state):
    log_event(epoch, state)
    record_telemetry(epoch, state)
    new_state = apply_correction(state)
    return (new_state, bh.EventAction.CONTINUE)
```

## Callback Execution Order

When multiple events occur at the same epoch:

1. Events are processed in the order their detectors were added
2. State modifications from earlier callbacks are passed to later callbacks
3. If any callback returns `STOP`, propagation halts after all callbacks execute

---

## See Also

- [Event Detection](event_detection.md) - Event detection fundamentals
- [Premade Events](premade_events.md) - Built-in event types
- [Maneuvers](maneuvers.md) - Using callbacks for orbit maneuvers