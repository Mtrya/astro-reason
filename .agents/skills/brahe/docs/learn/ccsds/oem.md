# OEM — Orbit Ephemeris Message

An Orbit Ephemeris Message (OEM) carries time-ordered state vectors for spacecraft ephemeris exchange. The typical workflow is to parse an OEM file and convert it into an `OrbitTrajectory` for interpolation and analysis, or to generate an OEM from a propagator for distribution.

## Parse and Access

Parse from file or string, then access header properties, segment metadata, and state vectors:

```python
import brahe as bh
from brahe.ccsds import OEM

bh.initialize_eop()

# Parse from file (auto-detects KVN, XML, or JSON format)
oem = OEM.from_file("test_assets/ccsds/oem/OEMExample1.txt")

# Header properties
print(f"Format version: {oem.format_version}")
print(f"Originator:     {oem.originator}")
print(f"Classification: {oem.classification}")
print(f"Creation date:  {oem.creation_date}")

# Segments — OEM can contain multiple trajectory arcs
print(f"\nNumber of segments: {len(oem.segments)}")

# Access segment metadata
seg = oem.segments[0]
print("\nSegment 0:")
print(f"  Object name:   {seg.object_name}")
print(f"  Object ID:     {seg.object_id}")
print(f"  Center name:   {seg.center_name}")
print(f"  Ref frame:     {seg.ref_frame}")
print(f"  Time system:   {seg.time_system}")
print(f"  Start time:    {seg.start_time}")
print(f"  Stop time:     {seg.stop_time}")
print(f"  Interpolation: {seg.interpolation}")
print(f"  States:        {seg.num_states}")
print(f"  Covariances:   {seg.num_covariances}")

# Access individual state vectors
sv = seg.states[0]
print("\nFirst state vector:")
print(f"  Epoch:    {sv.epoch}")
print(
    f"  Position: [{sv.position[0]:.3f}, {sv.position[1]:.3f}, {sv.position[2]:.3f}] m"
)
print(
    f"  Velocity: [{sv.velocity[0]:.5f}, {sv.velocity[1]:.5f}, {sv.velocity[2]:.5f}] m/s"
)

# Iterate over all states in a segment
print("\nAll states in segment 0:")
for i, sv in enumerate(seg.states):
    print(
        f"  [{i}] {sv.epoch}  pos=({sv.position[0] / 1e3:.3f}, {sv.position[1] / 1e3:.3f}, {sv.position[2] / 1e3:.3f}) km"
    )

# Serialization
kvn = oem.to_string("KVN")
print(f"\nKVN output length: {len(kvn)} characters")
d = oem.to_dict()
print(f"Dict keys: {list(d.keys())}")
```


## Converting to OrbitTrajectory

The primary interoperability point for OEM data is conversion to brahe's `OrbitTrajectory`. Each OEM segment maps to a trajectory object, giving you Hermite interpolation at arbitrary epochs within the covered time span:

```python
import brahe as bh
from brahe.ccsds import OEM

bh.initialize_eop()

# Parse an OEM file
oem = OEM.from_file("test_assets/ccsds/oem/OEMExample5.txt")
seg = oem.segments[0]
print(f"Segment: {seg.object_name}, {seg.num_states} states, frame={seg.ref_frame}")

# Convert segment 0 to an OrbitTrajectory
traj = oem.segment_to_trajectory(0)
print(f"\nTrajectory: {len(traj)} states")
print(f"  Frame: {traj.frame}")
print(f"  Start: {traj.start_epoch()}")
print(f"  End:   {traj.end_epoch()}")
print(f"  Span:  {traj.timespan():.0f} seconds")

# Access states by index
epc, state = traj.get(0)
print("\nFirst state:")
print(f"  Epoch: {epc}")
print(
    f"  Position: [{state[0] / 1e3:.3f}, {state[1] / 1e3:.3f}, {state[2] / 1e3:.3f}] km"
)
print(f"  Velocity: [{state[3]:.3f}, {state[4]:.3f}, {state[5]:.3f}] m/s")

# Interpolate at an arbitrary epoch between states
epc0, _ = traj.get(0)
epc1, _ = traj.get(1)
mid_epoch = epc0 + (epc1 - epc0) / 2.0
interp_state = traj.interpolate(mid_epoch)
print(f"\nInterpolated state at {mid_epoch}:")
print(
    f"  Position: [{interp_state[0] / 1e3:.3f}, {interp_state[1] / 1e3:.3f}, {interp_state[2] / 1e3:.3f}] km"
)

# Convert all segments at once
oem_multi = OEM.from_file("test_assets/ccsds/oem/OEMExample1.txt")
trajs = oem_multi.to_trajectories()
print(f"\nMulti-segment OEM: {len(trajs)} trajectories")
for i, t in enumerate(trajs):
    print(f"  [{i}] {len(t)} states, span={t.timespan():.0f}s")
```


## How OEM Messages Are Organized

An OEM message begins with a **header** that records the format version, creation date, and originator. The bulk of the data lives in one or more **segments**, each of which has its own metadata block and a sequence of state vectors.

Multiple segments exist because a single file may need to cover different trajectory arcs. A maneuver boundary, a change in reference frame, or a gap in tracking data each warrant a new segment. Within a segment, the metadata block records the object identity, center body, reference frame, time system, time span, and interpolation settings. The state vectors follow — each line provides an epoch plus position and velocity (and optionally acceleration). If covariance data is available, it appears as one or more 6$\times$6 symmetric matrices attached to the segment, each with its own epoch and optional reference frame override.

## Creating and Writing OEMs

Build an OEM programmatically by defining a header, adding segments with metadata, and populating state vectors. The resulting message can be serialized to KVN, XML, or JSON:

```python
import brahe as bh
import numpy as np
from brahe.ccsds import OEM

bh.initialize_eop()

# Create a new OEM with header info
oem = OEM(originator="BRAHE_EXAMPLE")
oem.classification = "unclassified"
oem.message_id = "OEM-2024-001"

# Define a LEO orbit and propagate with KeplerianPropagator (two-body)
epoch = bh.Epoch.from_datetime(2024, 6, 15, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
oe = np.array([bh.R_EARTH + 500e3, 0.001, 51.6, 15.0, 30.0, 0.0])
prop = bh.KeplerianPropagator.from_keplerian(epoch, oe, bh.AngleFormat.DEGREES, 60.0)

# Add a segment with metadata
step = 60.0  # 60-second spacing
n_states = 5
stop_epoch = epoch + step * (n_states - 1)

seg_idx = oem.add_segment(
    object_name="LEO SAT",
    object_id="2024-100A",
    center_name="EARTH",
    ref_frame="EME2000",
    time_system="UTC",
    start_time=epoch,
    stop_time=stop_epoch,
    interpolation="LAGRANGE",
    interpolation_degree=7,
)

# Propagate to build trajectory, then bulk-add states to segment
prop.propagate_to(stop_epoch)
seg = oem.segments[seg_idx]
seg.add_trajectory(prop.trajectory)

print(f"Created OEM with {len(oem.segments)} segment, {seg.num_states} states")

# Write to KVN string
kvn = oem.to_string("KVN")
print(f"\nKVN output ({len(kvn)} chars):")
print(kvn[:500])

# Write to file
oem.to_file("/tmp/brahe_example_oem.txt", "KVN")
print("\nWritten to /tmp/brahe_example_oem.txt")

# Verify round-trip
oem2 = OEM.from_file("/tmp/brahe_example_oem.txt")
print(f"Round-trip: {len(oem2.segments)} segment, {oem2.segments[0].num_states} states")
```


**Round-Trip Fidelity**
Writing and re-parsing an OEM preserves all metadata, state vectors, and covariance data. Numeric precision may vary slightly due to floating-point formatting, but values are preserved within the precision of the output format.

## Generating from a Propagator

Propagate an orbit numerically, extract the trajectory, and build an OEM for distribution:

```python
import brahe as bh
import numpy as np
from brahe.ccsds import OEM

bh.initialize_eop()
bh.initialize_sw()

# Define initial state
epoch = bh.Epoch.from_datetime(2024, 6, 15, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
oe = np.array([bh.R_EARTH + 500e3, 0.001, 51.6, 15.0, 30.0, 45.0])
state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)
params = np.array([500.0, 2.0, 2.2, 2.0, 1.3])

# Create propagator with default force model
prop = bh.NumericalOrbitPropagator(
    epoch,
    state,
    bh.NumericalPropagationConfig.default(),
    bh.ForceModelConfig.default(),
    params,
)

# Propagate for 90 minutes
target_epoch = epoch + 5400.0
prop.propagate_to(target_epoch)
print(f"Propagated from {epoch} to {prop.current_epoch()}")

# Get the accumulated trajectory
traj = prop.trajectory
print(f"Trajectory: {len(traj)} states, span={traj.timespan():.0f}s")

# Build an OEM from the trajectory states using the trajectory kwarg
oem = OEM(originator="BRAHE_PROP")
stop_epoch = prop.current_epoch()
seg_idx = oem.add_segment(
    object_name="LEO SAT",
    object_id="2024-100A",
    center_name="EARTH",
    ref_frame="EME2000",
    time_system="UTC",
    start_time=epoch,
    stop_time=stop_epoch,
    interpolation="LAGRANGE",
    interpolation_degree=7,
    trajectory=traj,
)
seg = oem.segments[seg_idx]

print(f"\nOEM: {len(oem.segments)} segment, {seg.num_states} states")

# Write to KVN
kvn = oem.to_string("KVN")
print(f"KVN output: {len(kvn)} characters")

# Verify by re-parsing
oem2 = OEM.from_str(kvn)
print(f"Round-trip: {oem2.segments[0].num_states} states")
```


## KVN Format Example

A minimal OEM KVN file looks like:

```
CCSDS_OEM_VERS = 3.0
CREATION_DATE = 2024-01-15T00:00:00
ORIGINATOR = BRAHE

META_START
OBJECT_NAME = MY SATELLITE
OBJECT_ID = 2024-001A
CENTER_NAME = EARTH
REF_FRAME = EME2000
TIME_SYSTEM = UTC
START_TIME = 2024-01-15T00:00:00
STOP_TIME = 2024-01-15T01:00:00
META_STOP

2024-01-15T00:00:00  6878.137  0.000  0.000  0.000  7.612  0.000
2024-01-15T00:30:00  -3439.068  5957.355  0.000  -6.593  -3.806  0.000
2024-01-15T01:00:00  -3439.068  -5957.355  0.000  6.593  -3.806  0.000
```

The data lines contain epoch followed by position (km) and velocity (km/s), space-separated.

---

## See Also

- [API Reference — OEM](../../library_api/ccsds/oem.md)
- [CCSDS Data Formats](index.md) — Overview of all message types
- [Trajectories](../trajectories/index.md) — Brahe trajectory containers