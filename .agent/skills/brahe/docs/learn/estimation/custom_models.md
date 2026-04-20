# Custom Measurement Models

Subclass `MeasurementModel` in Python to define any nonlinear measurement function. The
Rust EKF calls your Python `predict()` method during filtering, and computes the
measurement Jacobian via finite differences automatically unless you provide an analytical
override.

## The Pattern

```python
import numpy as np
import brahe as bh

bh.initialize_eop()


# Define a custom range measurement model
class RangeModel(bh.MeasurementModel):
    """Measures distance from a ground station to the satellite."""

    def __init__(self, station_eci, sigma):
        super().__init__()
        self.station_eci = np.array(station_eci)
        self.sigma = sigma

    def predict(self, epoch, state):
        pos = state[:3]
        return np.array([np.linalg.norm(pos - self.station_eci)])

    def noise_covariance(self):
        return np.array([[self.sigma**2]])

    def measurement_dim(self):
        return 1

    def name(self):
        return "Range"


# Set up orbit and truth propagator
epoch = bh.Epoch(2024, 1, 1, 0, 0, 0.0)
r = bh.R_EARTH + 500e3
v = (bh.GM_EARTH / r) ** 0.5
true_state = np.array([r, 0.0, 0.0, 0.0, v, 0.0])

truth_prop = bh.NumericalOrbitPropagator(
    epoch,
    true_state,
    bh.NumericalPropagationConfig.default(),
    bh.ForceModelConfig.two_body(),
)

# Ground station (approximately on the equator)
station = np.array([bh.R_EARTH, 0.0, 0.0])

# Create EKF with both a built-in model and our custom range model
position_model = bh.InertialPositionMeasurementModel(10.0)
range_model = RangeModel(station, 100.0)

initial_state = true_state.copy()
initial_state[0] += 500.0  # 500m position offset
p0 = np.diag([1e6, 1e6, 1e6, 1e2, 1e2, 1e2])

ekf = bh.ExtendedKalmanFilter(
    epoch,
    initial_state,
    p0,
    measurement_models=[position_model, range_model],
    propagation_config=bh.NumericalPropagationConfig.default(),
    force_config=bh.ForceModelConfig.two_body(),
)

# Alternate between position and range observations
dt = 60.0
for i in range(1, 21):
    obs_epoch = epoch + dt * i
    truth_prop.propagate_to(obs_epoch)
    truth_st = truth_prop.current_state()

    if i % 2 == 0:
        # Position observation (model_index=0)
        obs = bh.Observation(obs_epoch, truth_st[:3], model_index=0)
    else:
        # Range observation (model_index=1)
        true_range = np.linalg.norm(truth_st[:3] - station)
        obs = bh.Observation(obs_epoch, np.array([true_range]), model_index=1)

    record = ekf.process_observation(obs)
    print(
        f"  {record.measurement_name:20s} prefit residual norm: "
        f"{np.linalg.norm(record.prefit_residual):.3f}"
    )

# Summary
truth_prop.propagate_to(ekf.current_epoch())
pos_error = np.linalg.norm(ekf.current_state()[:3] - truth_prop.current_state()[:3])
print(f"\nFinal position error: {pos_error:.2f} m")
print(
    f"Records: {len(ekf.records())} "
    f"(InertialPosition: {sum(1 for r in ekf.records() if r.measurement_name == 'InertialPosition')}, "
    f"Range: {sum(1 for r in ekf.records() if r.measurement_name == 'Range')})"
)
```


The `RangeModel` above measures the Euclidean distance from a ground station to the
satellite. It implements four required methods and relies on the default finite-difference
Jacobian. The EKF processes range observations alongside built-in position observations by
assigning different `model_index` values.

## Required Methods

Every custom model must implement these four methods:

**`predict(epoch, state) -> numpy.ndarray`** -- compute the predicted measurement
$h(\mathbf{x}, t)$. The `epoch` is a `brahe.Epoch` and `state` is a 1D numpy array.
Return a 1D numpy array of length `measurement_dim()`.

**`noise_covariance() -> numpy.ndarray`** -- return the measurement noise covariance
matrix $R$ as a 2D numpy array of shape `(m, m)`. This is called once at construction and
cached, so it must not depend on epoch or state.

**`measurement_dim() -> int`** -- return the dimension of the measurement vector. Also
called once and cached.

**`name() -> str`** -- return a human-readable name. This appears in `FilterRecord` entries
and is useful for filtering residuals by model type.

## Analytical Jacobian (Optional)

By default, the measurement Jacobian $H = \partial h / \partial \mathbf{x}$ is computed via
central finite differences using the same perturbation strategy as the propagator Jacobians.
This calls your `predict()` method $2n$ times (where $n$ is the state dimension), which
works but adds Python function-call overhead.

To provide an analytical Jacobian, override `jacobian()` and return a 2D numpy array:

```
class RangeModelAnalytical(bh.MeasurementModel):
    def __init__(self, station_eci, sigma):
        super().__init__()
        self.station_eci = np.array(station_eci)
        self.sigma = sigma

    def predict(self, epoch, state):
        return np.array([np.linalg.norm(state[:3] - self.station_eci)])

    def jacobian(self, epoch, state):
        diff = state[:3] - self.station_eci
        r = np.linalg.norm(diff)
        h = np.zeros((1, len(state)))
        h[0, :3] = diff / r
        return h

    def noise_covariance(self):
        return np.array([[self.sigma**2]])

    def measurement_dim(self):
        return 1

    def name(self):
        return "RangeAnalytical"
```

Return `None` from `jacobian()` to explicitly request the finite-difference fallback.

## Mixing Models

A single EKF can use multiple measurement models -- both built-in and custom. Each
`Observation` carries a `model_index` that selects which model processes it:

```
ekf = bh.ExtendedKalmanFilter(
    epoch, state, p0,
    measurement_models=[
        bh.InertialPositionMeasurementModel(10.0),  # index 0
        RangeModel(station, 100.0),                  # index 1
    ],
    propagation_config=bh.NumericalPropagationConfig.default(),
    force_config=bh.ForceModelConfig.two_body(),
)

# Position observation uses model 0
obs_pos = bh.Observation(t1, position_measurement, model_index=0)

# Range observation uses model 1
obs_range = bh.Observation(t2, np.array([range_km]), model_index=1)
```

Built-in models passed to the EKF execute entirely in Rust with no Python overhead. Custom
Python models incur GIL acquisition on each `predict()` and `jacobian()` call. For
performance-critical applications with many observations, consider implementing custom
models in Rust via the `MeasurementModel` trait.

---

## See Also

- [Measurement Models](measurement_models.md) -- Built-in GPS-like measurement types
- [Extended Kalman Filter](extended_kalman_filter.md) -- EKF setup and processing
- [MeasurementModel API Reference](../../library_api/estimation/common_types.md) -- Base class documentation