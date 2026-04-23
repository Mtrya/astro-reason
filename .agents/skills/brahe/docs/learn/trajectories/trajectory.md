# Trajectory

`Trajectory` is a dynamically sized trajectory container that stores time-series state data with runtime-determined dimensions. Unlike static trajectory types, `Trajectory` allows you to specify the state vector dimension at creation time, making it ideal for applications where the dimension varies or is not known at compile time.

Use `Trajectory` when:

- State dimension is determined at runtime
- You need flexibility to work with different dimensions in the same codebase
- State vectors are non-standard (not 3D or 6D)
- Flexibility is prioritized over maximum performance

## Initialization

### Empty Trajectory

Create an empty trajectory by specifying the state dimension. The default dimension is 6 (suitable for position + velocity states):


```python
import brahe as bh

bh.initialize_eop()

# Create 6D trajectory (default)
traj = bh.Trajectory()
print(f"Dimension: {traj.dimension()}")

# Create 3D trajectory (position only)
traj_3d = bh.Trajectory(3)
print(f"Dimension: {traj_3d.dimension()}")

# Create 12D trajectory (custom)
traj_12d = bh.Trajectory(12)
print(f"Dimension: {traj_12d.dimension()}")
```


### From Existing Data

Create a trajectory from existing epochs and states:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Create epochs
epoch0 = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
epoch1 = epoch0 + 60.0  # 1 minute later
epoch2 = epoch0 + 120.0  # 2 minutes later

# Create states (6D: position + velocity)
state0 = np.array([bh.R_EARTH + 500e3, 0.0, 0.0, 0.0, 7600.0, 0.0])
state1 = np.array([bh.R_EARTH + 500e3, 456000.0, 0.0, -7600.0, 0.0, 0.0])
state2 = np.array([bh.R_EARTH + 500e3, 0.0, 0.0, 0.0, -7600.0, 0.0])

# Create trajectory from data
epochs = [epoch0, epoch1, epoch2]
states = np.array([state0, state1, state2])
traj = bh.Trajectory.from_data(epochs, states)

print(f"Trajectory length: {len(traj)}")
```


## Adding and Accessing States

### Adding States

Add states to a trajectory one at a time:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Create empty trajectory
traj = bh.Trajectory(6)

# Add states
epoch0 = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
state0 = np.array([bh.R_EARTH + 500e3, 0.0, 0.0, 0.0, 7600.0, 0.0])
traj.add(epoch0, state0)

print(f"Trajectory length: {len(traj)}")

epoch1 = epoch0 + 60.0
state1 = np.array([bh.R_EARTH + 500e3, 456000.0, 0.0, -7600.0, 0.0, 0.0])
traj.add(epoch1, state1)

print(f"Trajectory length: {len(traj)}")
```


### Accessing by Index

Retrieve states and epochs by their index:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Create and populate trajectory
traj = bh.Trajectory(6)
epoch0 = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
state0 = np.array([bh.R_EARTH + 500e3, 0.0, 0.0, 0.0, 7600.0, 0.0])
traj.add(epoch0, state0)

epoch1 = epoch0 + 60.0
state1 = np.array([bh.R_EARTH + 600e3, 456000.0, 0.0, -7600.0, 0.0, 0.0])
traj.add(epoch1, state1)

epoch2 = epoch0 + 120.0
state2 = np.array([bh.R_EARTH + 700e3, 0.0, 0.0, 0.0, -7600.0, 0.0])
traj.add(epoch2, state2)

# Access by index
retrieved_epoch = traj.epoch_at_idx(1)
retrieved_state = traj.state_at_idx(1)

print(f"Epoch: {retrieved_epoch}")
print(f"Altitude: {retrieved_state[0] - bh.R_EARTH:.2f} m")
```


### Accessing by Epoch

Get states at or near specific epochs:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Create trajectory with multiple states
traj = bh.Trajectory(6)
epoch0 = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)

for i in range(5):
    epoch = epoch0 + i * 60.0
    state = np.array([bh.R_EARTH + 500e3 + i * 1000, 0.0, 0.0, 0.0, 7600.0, 0.0])
    traj.add(epoch, state)

# Get nearest state to a specific epoch
query_epoch = epoch0 + 120.0  # 2 minutes after start
nearest_epoch, nearest_state = traj.nearest_state(query_epoch)
print(
    f"Nearest state at t+120s altitude: {(nearest_state[0] - bh.R_EARTH) / 1e3:.2f} km"
)

# Get nearest state between stored epochs
query_epoch = epoch0 + 125.0  # Between stored epochs
nearest_epoch, nearest_state = traj.nearest_state(query_epoch)
print(
    f"Nearest state at t+125s altitude: {(nearest_state[0] - bh.R_EARTH) / 1e3:.2f} km"
)
```


## Querying Trajectory Properties

### Time Span and Bounds

Query the temporal extent of a trajectory:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Create trajectory spanning 5 minutes
traj = bh.Trajectory(6)
epoch0 = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)

for i in range(6):
    epoch = epoch0 + i * 60.0
    state = np.array([bh.R_EARTH + 500e3, 0.0, 0.0, 0.0, 7600.0, 0.0])
    traj.add(epoch, state)

# Query properties
print(f"Number of states: {len(traj)}")
print(f"Start epoch: {traj.start_epoch()}")
print(f"End epoch: {traj.end_epoch()}")
print(f"Timespan: {traj.timespan():.1f} seconds")
print(f"Is empty: {traj.is_empty()}")

# Access first and last states
first_epoch, first_state = traj.first()
last_epoch, last_state = traj.last()
print(f"First epoch: {first_epoch}")
print(f"Last epoch: {last_epoch}")
```


## Interpolation

Trajectory supports linear interpolation to estimate states at arbitrary epochs between stored data points:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Create trajectory with sparse data
traj = bh.Trajectory(6)
epoch0 = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# Add states every 60 seconds
for i in range(3):
    epoch = epoch0 + i * 60.0
    # Simplified motion: position changes linearly with time
    state = np.array([bh.R_EARTH + 500e3 + i * 10000, 0.0, 0.0, 0.0, 7600.0, 0.0])
    traj.add(epoch, state)

# Interpolate state at intermediate time
query_epoch = epoch0 + 30.0  # Halfway between first two states
interpolated_state = traj.interpolate(query_epoch)

print(f"Interpolated altitude: {(interpolated_state[0] - bh.R_EARTH) / 1e3:.2f} km")
```


## Memory Management

Trajectory supports eviction policies to automatically manage memory in long-running applications:

### Maximum Size Policy

Keep only the N most recent states:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Create trajectory with max size limit
traj = bh.Trajectory(6).with_eviction_policy_max_size(3)

epoch0 = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# Add 5 states
for i in range(5):
    epoch = epoch0 + i * 60.0
    state = np.array([bh.R_EARTH + 500e3 + i * 1000, 0.0, 0.0, 0.0, 7600.0, 0.0])
    traj.add(epoch, state)

# Only the 3 most recent states are kept
print(f"Trajectory length: {len(traj)}")
print(f"Start epoch: {traj.start_epoch()}")
print(f"Start altitude: {(traj.state_at_idx(0)[0] - bh.R_EARTH) / 1e3:.2f} km")
```


### Maximum Age Policy

Keep only states within a time window:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Keep only states within last 2 minutes (120 seconds)
traj = bh.Trajectory(6).with_eviction_policy_max_age(120.0)

epoch0 = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# Add states spanning 4 minutes
for i in range(5):
    epoch = epoch0 + i * 60.0
    state = np.array([bh.R_EARTH + 500e3, 0.0, 0.0, 0.0, 7600.0, 0.0])
    traj.add(epoch, state)

# Only states within 120 seconds of the most recent are kept
print(f"Trajectory length: {len(traj)}")
print(f"Timespan: {traj.timespan():.1f} seconds")
```


## Iteration

Trajectories can be iterated to process all epoch-state pairs:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Create and populate trajectory
traj = bh.Trajectory(6)
epoch0 = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)

for i in range(3):
    epoch = epoch0 + i * 60.0
    state = np.array([bh.R_EARTH + 500e3 + i * 1000, 0.0, 0.0, 0.0, 7600.0, 0.0])
    traj.add(epoch, state)

# Iterate over all states
for epoch, state in traj:
    altitude = (state[0] - bh.R_EARTH) / 1e3
    print(f"Epoch: {epoch}, Altitude: {altitude:.2f} km")
```


## Matrix Export

Convert trajectory data to matrix format for analysis or export:


```python
import brahe as bh
import numpy as np

bh.initialize_eop()

# Create trajectory
traj = bh.Trajectory(6)
epoch0 = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)

for i in range(3):
    epoch = epoch0 + i * 60.0
    state = np.array([bh.R_EARTH + 500e3, 0.0, 0.0, 0.0, 7600.0 + i * 10, 0.0])
    traj.add(epoch, state)

# Convert to matrix (rows are states, columns are dimensions)
matrix = traj.to_matrix()
print(f"Matrix type: {type(matrix)}")
print(f"Matrix shape: {matrix.shape}")
print(f"First state velocity: {matrix[0, 4]:.1f} m/s")
```


---

## See Also

- [Trajectories Overview](index.md) - Trait hierarchy and implementation guide
- [OrbitTrajectory](orbit_trajectory.md) - Orbital trajectory with frame conversions
- [Trajectory API Reference](../../library_api/trajectories/trajectory.md)