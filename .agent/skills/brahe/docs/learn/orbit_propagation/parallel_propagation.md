# Parallel Orbit Propagation

When working with multiple satellites (constellations, Monte Carlo simulations, etc.), propagating each satellite sequentially can be slow. The `par_propagate_to` function enables efficient parallel propagation by utilizing multiple CPU cores. The parallel propagation function uses Rayon's work-stealing thread pool, configured via `brahe.set_num_threads()`.

**When to Use Parallel Propagation**

- Propagating constellations (10s to 1000s of satellites)
- Running Monte Carlo simulations
- Batch processing orbital predictions
- You have multiple CPU cores available

See the [threading documentation](../utilities/threading.md) for more details on configuring threading in Brahe.

## Basic Example

This example creates a constellation of 10 satellites and propagates them 24 hours forward in parallel:

```
import brahe as bh
import numpy as np
import time

bh.initialize_eop()

# Create initial epoch
epoch = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# Create multiple propagators for a constellation
num_sats = 10
propagators = []

for i in range(num_sats):
    # Vary semi-major axis slightly for each satellite
    a = bh.R_EARTH + 500e3 + i * 10e3
    oe = np.array([a, 0.001, 98.0, i * 36.0, 0.0, i * 36.0])
    state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)
    prop = bh.KeplerianPropagator.from_eci(epoch, state, 60.0)
    propagators.append(prop)

# Target epoch: 24 hours later
target = epoch + 86400.0

# Propagate all satellites in parallel
start = time.time()
bh.par_propagate_to(propagators, target)
parallel_time = time.time() - start

print(f"Propagated {num_sats} satellites in parallel: {parallel_time:.4f} seconds")
print("\nFinal states:")
for i, prop in enumerate(propagators):
    state = prop.current_state()
    print(f"  Satellite {i}: r = {np.linalg.norm(state[:3]) / 1e3:.1f} km")
```


## Mixing Propagator Types

All propagators in the list must be the same type (either all `KeplerianPropagator` or all `SGPPropagator`). Mixing types will raise a `TypeError`:

```
import brahe as bh

# Example propgator intiailization
kep_prop = bh.KeplerianPropagator.from_eci(epoch, state, 60.0)
sgp_prop = bh.SGPPropagator.from_tle(line1, line2, 60.0)

# This will raise TypeError
bh.par_propagate_to([kep_prop, sgp_prop], target)
```

## Memory Considerations

The parallel function clones each propagator before propagation, then updates the originals with final states. Memory usage scales linearly with the number of propagators.

For very large constellations (1000s of satellites), consider processing in batches and monitoring memory usage to avoid crashes from memory exhaustion.

## Error Handling

If any propagator fails during parallel propagation, the function will panic (Rust) or raise an exception (Python). This can occur with SGP4 propagators when satellites decay below Earth's surface.

## See Also

- [Keplerian Propagator](../../library_api/propagators/keplerian_propagator.md) - Two-body orbital propagation
- [SGP4 Propagator](../../library_api/propagators/sgp_propagator.md) - TLE-based propagation
- [API Reference: par_propagate_to](../../library_api/propagators/functions.md#par_propagate_to)