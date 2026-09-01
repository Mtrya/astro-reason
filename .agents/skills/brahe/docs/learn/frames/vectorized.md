# Vectorized Transformations

Frame transformation functions accept a batch of vectors in a single call. Passing a two-dimensional array such as `(n, 6)` to `state_eci_to_ecef` transforms every row and returns an array of the same shape; the loop, the Earth-orientation lookups, and the thread scheduling all happen inside the Rust core. A batch that shares one epoch runs hundreds of times faster than a Python loop over the scalar function because the IAU 2006/2000A rotation matrices are computed once and applied to every vector.

## Batch Input

A vectorized function is the same function as the scalar one. It decides how to evaluate based on the shape of its inputs:

| Input | Behavior |
|---|---|
| 1-D vector, single `Epoch` | Scalar transformation, unchanged output shape `(3,)` or `(6,)` |
| Array with the components along `axis` (default `-1`), single `Epoch` | Every vector is transformed with one shared epoch; the output keeps the input layout |
| 1-D vector, sequence of `n` epochs | The vector is transformed at each epoch; the output has shape `(n, k)` (or `(k, n)` with `axis=0`) |
| Array of `n` vectors, sequence of `n` epochs | Vector `i` is transformed at epoch `i`; the output keeps the input layout |

`axis` names the array dimension that holds the vector components, following the numpy convention used by functions such as `np.linalg.norm`. The default `-1` matches the common `(n, 6)` layout where each row is a state; `axis=0` selects a `(6, n)` layout where each column is a state. Any number of leading batch dimensions is accepted, so a `(2, 3, 6)` array is transformed element by element and returned as `(2, 3, 6)`.

Epoch arguments accept an `Epoch` or any sequence of `Epoch` objects (list, tuple, or object array). The epoch count must be `1` or equal to the number of vectors; other combinations raise `ValueError`.

Rotation-matrix functions such as `rotation_eci_to_ecef` accept a sequence of epochs and return an `(n, 3, 3)` array.

The same rules apply to every frame family: ECI/ECEF and GCRF/ITRF, EME2000, the lunar (LCI, LFPA, LFME), Mars (MCI, MCMF), and Earth-Moon barycenter (EMBI) frames, the EMR/SER/GSE synodic frames, `rotation_icrf_to_body_fixed_iau`, and the generic `rotation_frame_to_frame`, `position_frame_to_frame`, and `state_frame_to_frame` router. Functions that can fail for a single input (synodic and router transforms, IAU rotations) raise the same `RuntimeError` for a batch.


```python
import numpy as np

import brahe as bh

bh.initialize_eop()

epc = bh.Epoch(2024, 1, 1, 12, 0, 0.0, time_system=bh.UTC)

# Build a batch of ECI states: one row per satellite, columns [x, y, z, vx, vy, vz]
raan = np.linspace(0.0, 360.0, 6, endpoint=False)
states_eci = np.array(
    [
        bh.state_koe_to_eci(
            np.array([bh.R_EARTH + 500e3, 0.001, 97.8, r, 0.0, 0.0]),
            bh.AngleFormat.DEGREES,
        )
        for r in raan
    ]
)
print(f"ECI states shape: {states_eci.shape}")

# One epoch, many states: the rotation matrices are computed once
states_ecef = bh.state_eci_to_ecef(epc, states_eci)
print(f"ECEF states shape: {states_ecef.shape}")
print(
    f"First ECEF state: {np.array2string(states_ecef[0], precision=3, suppress_small=True, max_line_width=120)}"
)

# The same call with the components along the first axis
states_ecef_t = bh.state_eci_to_ecef(epc, states_eci.T, axis=0)
print(f"Transposed layout shape: {states_ecef_t.shape}")

# Many epochs, one position: a ground station tracked through inertial space
epochs = [epc + 600.0 * i for i in range(6)]
station_ecef = bh.position_geodetic_to_ecef(
    np.array([-122.4, 37.8, 0.0]), bh.AngleFormat.DEGREES
)
station_eci = bh.position_ecef_to_eci(epochs, station_ecef)
print(f"Station ECI positions shape: {station_eci.shape}")
for e, r in zip(epochs, station_eci):
    print(f"  {e}: [{r[0]:.1f}, {r[1]:.1f}, {r[2]:.1f}] m")

# Many epochs, many states: one epoch per row
states_ecef_series = bh.state_eci_to_ecef(epochs, states_eci)
print(f"Per-epoch ECEF states shape: {states_ecef_series.shape}")

# A sequence of epochs also vectorizes the rotation matrices
rotations = bh.rotation_eci_to_ecef(epochs)
print(f"Rotation matrices shape: {rotations.shape}")
```
