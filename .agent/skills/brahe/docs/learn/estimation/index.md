# Estimation

Estimation processes measurements to refine a spacecraft's state -- position, velocity, and
optionally additional parameters -- beyond what the dynamics model alone can predict. Brahe
provides an Extended Kalman Filter (EKF) with built-in and custom measurement models. The
primary workflow is: create a filter with an initial state estimate, feed it observations,
and read the refined state.

## The Core Workflow

Set up an EKF with a propagator, measurement model, and initial covariance, then process
observations sequentially. The filter propagates state and covariance to each observation
epoch and incorporates the measurement to produce an updated estimate.

```python
import numpy as np
import brahe as bh

# Initialize EOP data for frame transformations
bh.initialize_eop()

# Define a LEO circular orbit
epoch = bh.Epoch(2024, 1, 1, 0, 0, 0.0)
r = bh.R_EARTH + 500e3
v = (bh.GM_EARTH / r) ** 0.5
true_state = np.array([r, 0.0, 0.0, 0.0, v, 0.0])

# Create a truth propagator for generating observations
truth_prop = bh.NumericalOrbitPropagator(
    epoch,
    true_state,
    bh.NumericalPropagationConfig.default(),
    bh.ForceModelConfig.two_body(),
)

# Perturbed initial state: 1 km position error, 1 m/s velocity error
initial_state = true_state.copy()
initial_state[0] += 1000.0
initial_state[4] += 1.0

# Initial covariance reflecting our uncertainty
p0 = np.diag([1e6, 1e6, 1e6, 1e2, 1e2, 1e2])

# Create the EKF with inertial position measurements (10 m noise)
ekf = bh.ExtendedKalmanFilter(
    epoch,
    initial_state,
    p0,
    measurement_models=[bh.InertialPositionMeasurementModel(10.0)],
    propagation_config=bh.NumericalPropagationConfig.default(),
    force_config=bh.ForceModelConfig.two_body(),
)

# Process 30 observations at 60-second intervals
dt = 60.0
for i in range(1, 31):
    obs_epoch = epoch + dt * i
    truth_prop.propagate_to(obs_epoch)
    truth_pos = truth_prop.current_state()[:3]

    obs = bh.Observation(obs_epoch, truth_pos, model_index=0)
    ekf.process_observation(obs)

# Compare final state to truth
truth_prop.propagate_to(ekf.current_epoch())
truth_final = truth_prop.current_state()
final_state = ekf.current_state()
pos_error = np.linalg.norm(final_state[:3] - truth_final[:3])
vel_error = np.linalg.norm(final_state[3:6] - truth_final[3:6])

print("Initial position error: 1000.0 m")
print(f"Final position error:   {pos_error:.2f} m")
print(f"Final velocity error:   {vel_error:.4f} m/s")
print(f"Observations processed: {len(ekf.records())}")

# Show final covariance diagonal (1-sigma uncertainties)
cov = ekf.current_covariance()
sigma = np.sqrt(np.diag(cov))
print("\n1-sigma uncertainties:")
print(f"  Position: [{sigma[0]:.1f}, {sigma[1]:.1f}, {sigma[2]:.1f}] m")
print(f"  Velocity: [{sigma[3]:.4f}, {sigma[4]:.4f}, {sigma[5]:.4f}] m/s")
```


The EKF constructor accepts an initial epoch, state, covariance, one or more measurement
models, and propagation configuration. Internally it builds a numerical orbit propagator
with STM (State Transition Matrix) propagation enabled -- the STM drives covariance
prediction between observations. Each call to `process_observation()` performs a predict
step (propagate to observation time) followed by an update step (incorporate the
measurement via Kalman gain).

## How the Pieces Connect

The estimation module has three main components:

**Measurement models** define the observation function $h(\mathbf{x}, t)$ that maps a
state vector to a predicted measurement. Built-in models handle GPS-like position and
velocity observations in both inertial and ECEF frames. Custom models can be defined in
Python by subclassing `MeasurementModel`.

**The Extended Kalman Filter** orchestrates the estimation loop. It owns a numerical
propagator for state and covariance prediction and a list of measurement models for
incorporating observations. Different measurement types can arrive at different times --
each `Observation` carries a `model_index` indicating which model to use.

**Filter records** capture the full diagnostic state at each update: pre-fit state,
post-fit state, pre-fit and post-fit residuals, covariance, and Kalman gain. These enable
analysis of filter performance, consistency checks, and residual monitoring.

## What's Available

The current release includes two sequential filters:

- **Extended Kalman Filter (EKF)** -- linearizes dynamics and measurements using STM and
  Jacobians. Efficient (one propagation per step) and well-suited for mildly nonlinear
  problems.

- **Unscented Kalman Filter (UKF)** -- propagates sigma points through true nonlinear
  functions without linearization. More robust for strongly nonlinear problems, at the cost
  of 2n+1 propagations per step.

- **Batch Least Squares (BLS)** -- processes all observations simultaneously, iterating to
  minimize the weighted sum of squared residuals. Best for offline orbit determination with
  complete observation arcs. Supports two solver formulations and consider parameters.

All estimators share the same measurement models, observation types, and Python API.

---

## See Also

- [Measurement Models](measurement_models.md) -- Built-in GPS-like measurement types
- [Extended Kalman Filter](extended_kalman_filter.md) -- EKF setup, processing, and diagnostics
- [Unscented Kalman Filter](unscented_kalman_filter.md) -- UKF sigma points and EKF comparison
- [Custom Models](custom_models.md) -- Defining measurement models in Python
- [Batch Least Squares](batch_least_squares.md) -- BLS offline orbit determination
- [Estimation API Reference](../../library_api/estimation/index.md) -- Complete type and method documentation
- [Covariance and Sensitivity](../orbit_propagation/numerical_propagation/covariance_sensitivity.md) -- STM propagation used by the EKF