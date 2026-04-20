---
name: brahe
description: Python astrodynamics and satellite dynamics with Brahe. Use for orbital propagation, coordinate transformations, access computation, attitude representations, trajectories, space weather, datasets, and visualization. Triggered by brahe, orbital mechanics, satellite propagation, astrodynamics, TLE, SGP4, Keplerian orbits, ground track, or access windows.
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

| Topic | Reference |
|-------|-----------|
| **Time & EOP** | [docs/learn/time/index.md](docs/learn/time/index.md), [docs/learn/eop/index.md](docs/learn/eop/index.md) |
| **Coordinates** | [docs/learn/coordinates/index.md](docs/learn/coordinates/index.md) |
| **Orbits** | [docs/learn/orbits/index.md](docs/learn/orbits/index.md) |
| **Propagation** | [docs/learn/orbit_propagation/index.md](docs/learn/orbit_propagation/index.md), [docs/learn/orbit_propagation/numerical_propagation/index.md](docs/learn/orbit_propagation/numerical_propagation/index.md) |
| **Dynamics** | [docs/learn/orbital_dynamics/index.md](docs/learn/orbital_dynamics/index.md) |
| **Space Weather** | [docs/learn/space_weather/index.md](docs/learn/space_weather/index.md) |
| **Trajectories** | [docs/learn/trajectories/index.md](docs/learn/trajectories/index.md) |
| **Access** | [docs/learn/access_computation/index.md](docs/learn/access_computation/index.md) |
| **Datasets** | [docs/learn/datasets/index.md](docs/learn/datasets/index.md) |
| **Plots** | [docs/learn/plots/index.md](docs/learn/plots/index.md) |
| **Attitude** | [docs/learn/attitude_representations/index.md](docs/learn/attitude_representations/index.md) |
| **Relative Motion** | [docs/learn/relative_motion/index.md](docs/learn/relative_motion/index.md) |

## Common Patterns

See `docs/learn/index.md` for the full user guide overview.
Linked example guides stay under `docs/examples/`, API docs under `docs/library_api/`, and runnable helpers under `examples/` and `plots/learn/`.

## Official Documentation

- User Guide: https://duncaneddy.github.io/brahe/latest/learn/
- Python API Reference: https://duncaneddy.github.io/brahe/latest/library_api/
- Source Code: https://github.com/duncaneddy/brahe
