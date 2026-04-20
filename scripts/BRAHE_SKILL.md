---
name: brahe
description: |
  Python astrodynamics and satellite dynamics with Brahe. Use for orbital propagation,
  coordinate transformations, access computation, attitude representations, trajectories,
  space weather, datasets, and visualization. Triggered by brahe, orbital mechanics,
  satellite propagation, astrodynamics, TLE, SGP4, Keplerian orbits, ground track,
  or access windows.
---

# Brahe Skill

Curated documentation and runnable examples for the Brahe Python library.

## Quick Start

To do something fun like calculating the orbital-period of a satellite in low Earth orbit:

```python
import brahe as bh

# Define the semi-major axis of a low Earth orbit (in meters)
a = bh.constants.R_EARTH + 400e3 # 400 km altitude

# Calculate the orbital period
T = bh.orbital_period(a)

print(f"Orbital Period: {T / 60:.2f} minutes")
# Outputs:
# Orbital Period: 92.56 minutes
```

or find when the ISS will next pass overhead:

```python
import brahe as bh

bh.initialize_eop()

# Download ISS TLE and create a propagator
client = bh.celestrak.CelestrakClient()
iss = client.get_sgp_propagator(catnr=25544, step_size=60.0)

# Propagate for 24 hours
epoch_start = iss.epoch
epoch_end = epoch_start + 24 * 3600.0
iss.propagate_to(epoch_end)

# Compute upcoming passes over San Francisco
passes = bh.location_accesses(
    bh.PointLocation(-122.4194, 37.7749, 0.0),  # San Francisco
    iss,
    epoch_start,
    epoch_end,
    bh.ElevationConstraint(min_elevation_deg=10.0),
)
print(f"Number of passes in next 24 hours: {len(passes)}")
# Example Output: Number of passes in next 24 hours: 5
```

## Module Map

See more examples and documents on how to use brahe:

| Topic | Reference | Key Scripts |
|-------|-----------|-------------|
| **Time & EOP** | [references/time/index.md](references/time/index.md), [references/eop/index.md](references/eop/index.md) | `scripts/time/`, `scripts/eop/` |
| **Coordinates** | [references/coordinates/index.md](references/coordinates/index.md) | `scripts/coordinates/` |
| **Orbits** | [references/orbits/index.md](references/orbits/index.md) | `scripts/orbits/` |
| **Propagation** | [references/orbit_propagation/index.md](references/orbit_propagation/index.md), [references/orbit_propagation/numerical_propagation/index.md](references/orbit_propagation/numerical_propagation/index.md) | `scripts/orbit_propagation/`, `scripts/numerical_propagation/` |
| **Dynamics** | [references/orbital_dynamics/index.md](references/orbital_dynamics/index.md) | `scripts/orbit_dynamics/` |
| **Space Weather** | [references/space_weather/index.md](references/space_weather/index.md) | `scripts/space_weather/` |
| **Trajectories** | [references/trajectories/index.md](references/trajectories/index.md) | `scripts/trajectories/` |
| **Access** | [references/access_computation/index.md](references/access_computation/index.md) | `scripts/access/` |
| **Datasets** | [references/datasets/index.md](references/datasets/index.md) | `scripts/datasets/` |
| **Plots** | [references/plots/index.md](references/plots/index.md) | `scripts/plots/` |
| **Attitude** | [references/attitude_representations/index.md](references/attitude_representations/index.md) | `scripts/attitude/` |
| **Relative Motion** | [references/relative_motion/index.md](references/relative_motion/index.md) | `scripts/relative_motion/` |

## Common Patterns

See `references/index.md` for the full user guide overview.

## Official Documentation

- User Guide: https://duncaneddy.github.io/brahe/latest/learn/
- Python API Reference: https://duncaneddy.github.io/brahe/latest/library_api/
- Source Code: https://github.com/duncaneddy/brahe
