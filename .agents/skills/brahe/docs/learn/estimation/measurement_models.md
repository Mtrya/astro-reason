# Measurement Models

Measurement models define $h(\mathbf{x}, t)$ — the function mapping a filter state to a
predicted observation — along with a noise covariance $R$. Brahe provides six built-in
models for GNSS-like observations in ECEF and inertial frames. All assume the filter state
is Cartesian ECI: $\mathbf{x} = [x, y, z, v_x, v_y, v_z, \ldots]$ in meters and m/s.

The most common starting point is an ECEF position model consuming raw GNSS receiver
outputs:

```python
import numpy as np

import brahe as bh

bh.initialize_eop()

# Define a LEO circular orbit
epoch = bh.Epoch(2024, 1, 1, 0, 0, 0.0)
r = bh.R_EARTH + 500e3
v = (bh.GM_EARTH / r) ** 0.5
true_state = np.array([r, 0.0, 0.0, 0.0, v, 0.0])

# Truth propagator for generating simulated GNSS observations
truth_prop = bh.NumericalOrbitPropagator(
    epoch,
    true_state,
    bh.NumericalPropagationConfig.default(),
    bh.ForceModelConfig.two_body(),
)

# Perturbed initial state: 1 km position error
initial_state = true_state.copy()
initial_state[0] += 1000.0
initial_state[4] += 1.0
p0 = np.diag([1e6, 1e6, 1e6, 1e2, 1e2, 1e2])

# ECEF position model with typical GNSS accuracy (5 m noise)
ecef_model = bh.ECEFPositionMeasurementModel(5.0)

ekf = bh.ExtendedKalmanFilter(
    epoch,
    initial_state,
    p0,
    measurement_models=[ecef_model],
    propagation_config=bh.NumericalPropagationConfig.default(),
    force_config=bh.ForceModelConfig.two_body(),
)

# Simulate GNSS observations: get truth ECI state, convert to ECEF
dt = 60.0
for i in range(1, 21):
    obs_epoch = epoch + dt * i
    truth_prop.propagate_to(obs_epoch)
    truth_eci = truth_prop.current_state()

    # Simulate GNSS: convert truth position to ECEF
    truth_ecef_pos = bh.position_eci_to_ecef(obs_epoch, truth_eci[:3])

    obs = bh.Observation(obs_epoch, truth_ecef_pos, model_index=0)
    ekf.process_observation(obs)

# Compare final state to truth
truth_prop.propagate_to(ekf.current_epoch())
truth_final = truth_prop.current_state()
final_state = ekf.current_state()
pos_error = np.linalg.norm(final_state[:3] - truth_final[:3])
vel_error = np.linalg.norm(final_state[3:6] - truth_final[3:6])

print("ECEF GNSS tracking with ECEFPositionMeasurementModel:")
print("  Initial position error: 1000.0 m")
print(f"  Final position error:   {pos_error:.2f} m")
print(f"  Final velocity error:   {vel_error:.4f} m/s")
print(f"  Observations processed: {len(ekf.records())}")
```


## ECEF Models

ECEF models process **GNSS receiver outputs** reported in the Earth-fixed frame. The
filter state remains in ECI — these models internally rotate the predicted state from ECI
to ECEF at each observation epoch. Jacobians are computed via central finite differences
because the rotation is epoch-dependent.

### ECEFPositionMeasurementModel

- **State**: $\mathbf{x} = [x, y, z, v_x, v_y, v_z, \ldots]_{\text{ECI}}$ (meters, m/s)
- **Measurement**: $\mathbf{z} = R_{\text{ECI} \to \text{ECEF}}(t) \cdot [x, y, z]_{\text{ECI}}$ — 3 values in meters
- **Jacobian**: Numerical (finite difference)

### ECEFVelocityMeasurementModel

Converts the full ECI state to ECEF and extracts velocity, properly accounting for Earth
rotation effects.

- **State**: $\mathbf{x} = [x, y, z, v_x, v_y, v_z, \ldots]_{\text{ECI}}$ (meters, m/s)
- **Measurement**: $\mathbf{z} = [v_x, v_y, v_z]_{\text{ECEF}}$ — 3 values in m/s
- **Jacobian**: Numerical (finite difference)

### ECEFStateMeasurementModel

Full 6D position + velocity in ECEF. Useful when a GNSS receiver provides both solutions
simultaneously.

- **State**: $\mathbf{x} = [x, y, z, v_x, v_y, v_z, \ldots]_{\text{ECI}}$ (meters, m/s)
- **Measurement**: $\mathbf{z} = [x, y, z, v_x, v_y, v_z]_{\text{ECEF}}$ — 6 values in meters + m/s
- **Jacobian**: Numerical (finite difference)

## Inertial Models

Inertial models directly extract components from the ECI state vector. The mapping is a
simple selection (identity sub-matrix), so Jacobians are **analytical** — fast and exact.
Use these when measurements are already in ECI, for simulation, or when the frame
conversion is handled externally.

### InertialPositionMeasurementModel

- **State**: $\mathbf{x} = [x, y, z, v_x, v_y, v_z, \ldots]_{\text{ECI}}$ (meters, m/s)
- **Measurement**: $\mathbf{z} = [x, y, z]_{\text{ECI}}$ — 3 values in meters
- **Jacobian**: $H = [I_{3 \times 3} \mid 0_{3 \times (n-3)}]$ (analytical)

### InertialVelocityMeasurementModel

- **State**: $\mathbf{x} = [x, y, z, v_x, v_y, v_z, \ldots]_{\text{ECI}}$ (meters, m/s)
- **Measurement**: $\mathbf{z} = [v_x, v_y, v_z]_{\text{ECI}}$ — 3 values in m/s
- **Jacobian**: $H = [0_{3 \times 3} \mid I_{3 \times 3} \mid 0_{3 \times (n-6)}]$ (analytical)

### InertialStateMeasurementModel

- **State**: $\mathbf{x} = [x, y, z, v_x, v_y, v_z, \ldots]_{\text{ECI}}$ (meters, m/s)
- **Measurement**: $\mathbf{z} = [x, y, z, v_x, v_y, v_z]_{\text{ECI}}$ — 6 values in meters + m/s
- **Jacobian**: $H = [I_{6 \times 6} \mid 0_{6 \times (n-6)}]$ (analytical)

## Azimuth/Elevation/Range

`AzElRangeMeasurementModel` handles **ground-based radar/tracking sensor observations** in
the station's local topocentric (SEZ) frame. Unlike the ECEF and inertial models above, the
measurement is angular plus range, not a Cartesian sub-vector of the state:

- **State**: $\mathbf{x} = [x, y, z, v_x, v_y, v_z, \ldots]_{\text{ECI}}$ (meters, m/s)
- **Measurement**: $\mathbf{z} = [\text{azimuth}, \text{elevation}, \text{range}] +
  \mathbf{b}$ -- azimuth clockwise from north, elevation from the local horizon, in the
  units given by `AngleFormat` at construction (degrees or radians); range in meters
- **Jacobian**: Numerical (finite difference) -- the ECI-to-ECEF rotation is epoch-dependent

The model accepts a constant bias `[bias_az, bias_el, bias_range]`, applied inside
`predict()`. This models a calibrated sensor (e.g. Vallado Table 4-4 az/el/range bias
values): a filter built with the same bias as the measurement source stays consistent,
rather than needing to estimate the bias away as an unmodeled error.

`residual()` wraps the azimuth component into $[-180°, 180°)$ (or $[-\pi, \pi)$ in radians;
round-half-away-from-zero maps an exact $+180°$ to $-180°$) so a pass crossing the 0/360°
boundary does not produce a spurious ~360° residual:

```python
import numpy as np

import brahe as bh

bh.initialize_eop()

# Configuration
MEAS_INTERVAL = 15.0  # seconds between measurements during a pass
DURATION = 2 * 3600.0  # tracking duration (seconds)
SEED = 42

# Truth orbit: LEO at 700 km, 72 degree inclination
epoch = bh.Epoch(2024, 1, 1, 0, 0, 0.0)
oe = np.array([bh.R_EARTH + 700e3, 0.001, 72.0, 30.0, 0.0, 0.0])
true_state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)


# Hermite-cubic interpolation (the propagator default) lets the trajectory,
# stored at the ~60 s adaptive-step cadence, be sampled accurately at the much
# finer measurement cadence used for measurement simulation.
truth_config = bh.NumericalPropagationConfig.default()
truth_prop = bh.NumericalOrbitPropagator(
    epoch,
    true_state,
    truth_config,
    bh.ForceModelConfig.two_body(),
)
epoch_end = epoch + DURATION
truth_prop.propagate_to(epoch_end)
truth_traj = truth_prop.trajectory

# Build sensors from the Vallado SSN dataset (calibrated radar and optical
# sites; radar measures az/el/range, optical measures angles-only az/el)
sites = bh.datasets.ssn_sensors.load()
sensors = bh.SimpleSSNSensor.from_locations_calibrated(sites, seed=SEED)
print(f"Loaded {len(sites)} SSN sites, {len(sensors)} calibrated sensors")

# Find passes and simulate measurements only inside them
observations = []
passes = []
for i, sensor in enumerate(sensors):
    constraint = bh.ElevationConstraint(min_elevation_deg=max(sensor.el_min, 1.0))
    windows = bh.location_accesses(
        sensor.location, truth_prop, epoch, epoch_end, constraint
    )
    for w in windows:
        obs = sensor.simulate_observations(
            truth_traj, w.window_open, w.window_close, MEAS_INTERVAL, i
        )
        observations.extend(obs)
        if obs:
            passes.append((sensor.name, w))

observations.sort(key=lambda o: o.epoch)
print(f"Simulated {len(observations)} measurements over {len(passes)} passes")

# EKF from a perturbed initial state, using each sensor's matching model
initial_state = np.array(true_state)
initial_state[0] += 1000.0
initial_state[4] += 1.0
p0 = np.diag([1e6, 1e6, 1e6, 1e2, 1e2, 1e2])

ekf = bh.ExtendedKalmanFilter(
    epoch,
    initial_state,
    p0,
    measurement_models=[s.measurement_model() for s in sensors],
    propagation_config=bh.NumericalPropagationConfig.default(),
    force_config=bh.ForceModelConfig.two_body(),
)

# Process observations in order; propagate through gaps between passes
GAP_SPLIT = 600.0  # start a new arc when consecutive obs are > 10 min apart
prev_epoch = epoch
for obs in observations:
    if obs.epoch - prev_epoch > GAP_SPLIT:
        # advance through the gap in 60 s steps to record covariance growth
        t = prev_epoch + 60.0
        while t < obs.epoch:
            ekf.propagate_to(t)
            t = t + 60.0
    ekf.process_observation(obs)
    prev_epoch = obs.epoch

# Compare final estimate to truth
truth_final = truth_traj.interpolate(ekf.current_epoch())
err = np.linalg.norm(ekf.current_state()[:3] - truth_final[:3])
print(f"Final position error: {err:.1f} m")
sigma = np.sqrt(np.diag(ekf.current_covariance()))
print(f"Final position 1-sigma: [{sigma[0]:.1f}, {sigma[1]:.1f}, {sigma[2]:.1f}] m")

assert err < 500.0, "EKF should converge to a small position error"
print("Example validated successfully!")
```


The azimuth wrap is handled consistently everywhere the measurement is differenced. The
`AzElRangeMeasurementModel` Jacobian override differences its two perturbed predictions
through `residual()`, and the Unscented Kalman Filter forms its predicted measurement mean
with the reference-point trick `z_mean = z_0 + Σ wᵢ · residual(zᵢ, z_0)` and computes its
innovation and cross-covariance deviations through `residual()` as well. So a pass whose
sigma-point azimuths straddle the wrap (e.g. some near 359°, others near 1°) yields a
well-defined mean near the true azimuth rather than a value biased toward the middle of the
circle. For measurement models with plain-subtraction residuals the reference-point mean is
algebraically identical to the ordinary weighted mean, so non-angular models are unaffected.

`SimpleSSNSensor` pairs a sensor site (location, field-of-view limits, bias/noise
calibration -- see the [SSN Sensor Datasets](../datasets/ssn_sensors.md) guide) with
measurement generation, and its `measurement_model()` method returns an
`AzElRangeMeasurementModel` built from the same bias and noise, so simulated measurements
and the filter's model stay consistent by construction. See the
[SSN Radar Tracking example](../../examples/ssn_tracking.md) for a full EKF/UKF/BLS
walkthrough built on this dataset.

## Noise Specification

All models accept noise as a scalar sigma (isotropic), per-axis sigmas, a full covariance
matrix, or upper-triangular packed elements:

```python
import numpy as np

import brahe as bh

# --- Scalar sigma: same noise on all axes ---
model = bh.ECEFPositionMeasurementModel(5.0)
print("Scalar (5 m isotropic):")
print(model.noise_covariance())

# --- Per-axis sigma: different noise per component ---
model = bh.ECEFPositionMeasurementModel.per_axis(3.0, 3.0, 8.0)
print("\nPer-axis (3, 3, 8 m):")
print(model.noise_covariance())

# --- Full covariance: captures cross-axis correlations ---
cov = np.array(
    [
        [9.0, 1.0, 0.0],
        [1.0, 9.0, 0.0],
        [0.0, 0.0, 64.0],
    ]
)
model = bh.ECEFPositionMeasurementModel.from_covariance(cov)
print("\nFull covariance (with correlations):")
print(model.noise_covariance())

# --- Upper-triangular: compact packed form ---
# Elements: [c00, c01, c02, c11, c12, c22]
upper = np.array([9.0, 1.0, 0.0, 9.0, 0.0, 64.0])
model = bh.ECEFPositionMeasurementModel.from_upper_triangular(upper)
print("\nUpper-triangular packed:")
print(model.noise_covariance())

# --- Standalone covariance helpers ---
r = bh.isotropic_covariance(3, 10.0)
print(f"\nisotropic_covariance(3, 10.0) diagonal: {np.diag(r)}")

r = bh.diagonal_covariance(np.array([5.0, 10.0, 15.0]))
print(f"diagonal_covariance([5, 10, 15]) diagonal: {np.diag(r)}")
```


## Custom Measurement Models

For observations beyond the built-in models — range, range-rate, angles, Doppler, or any
nonlinear function — define a custom measurement model. Subclass `MeasurementModel` in
Python or implement the `MeasurementModel` trait in Rust.

The full pattern, including analytical Jacobians and mixing custom models with built-in
models in a single filter, is covered in the [Custom Models](custom_models.md) guide.

---

## See Also

- [Custom Models](custom_models.md) -- Writing custom measurement models with examples
- [Extended Kalman Filter](extended_kalman_filter.md) -- Using models with the EKF
- [Unscented Kalman Filter](unscented_kalman_filter.md) -- Using models with the UKF
- [SSN Sensor Datasets](../datasets/ssn_sensors.md) -- Sensor sites backing `SimpleSSNSensor`
- [Measurement Models API Reference](../../library_api/estimation/measurement_models.md) -- Complete class documentation for AzElRangeMeasurementModel and AzElMeasurementModel
- [Sensor Models API Reference](../../library_api/estimation/sensor_models.md) -- Complete SimpleSSNSensor documentation