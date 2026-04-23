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
- [Measurement Models API Reference](../../library_api/estimation/measurement_models.md) -- Complete class documentation