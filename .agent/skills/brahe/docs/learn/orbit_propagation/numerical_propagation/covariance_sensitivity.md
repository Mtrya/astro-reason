# Covariance and Sensitivity

The `NumericalOrbitPropagator` can propagate additional quantities alongside the orbital state, enabling covariance propagation and sensitivity analysis. This is essential for uncertainty quantification, orbit determination, and mission analysis.

## Full Example

Here is a complete example demonstrating STM, covariance, and sensitivity propagation together:


```python
import numpy as np
import brahe as bh

# Initialize EOP and space weather data (required for NRLMSISE-00 drag model)
bh.initialize_eop()
bh.initialize_sw()

# Create initial epoch and state (LEO satellite)
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)
oe = np.array([bh.R_EARTH + 500e3, 0.01, 45.0, 15.0, 30.0, 45.0])
state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

# Define spacecraft parameters: [mass, drag_area, Cd, srp_area, Cr]
params = np.array([500.0, 2.0, 2.2, 2.0, 1.3])

# Create propagation config enabling STM and sensitivity with history storage
prop_config = (
    bh.NumericalPropagationConfig.default()
    .with_stm()
    .with_stm_history()
    .with_sensitivity()
    .with_sensitivity_history()
)

# Define initial covariance (diagonal)
# Position uncertainty: 10 m (variance = 100 m²)
# Velocity uncertainty: 0.01 m/s (variance = 0.0001 m²/s²)
P0 = np.diag([100.0, 100.0, 100.0, 0.0001, 0.0001, 0.0001])

# Create propagator with full force model
prop = bh.NumericalOrbitPropagator(
    epoch,
    state,
    prop_config,
    bh.ForceModelConfig.default(),
    params=params,
    initial_covariance=P0,
)

print("=== Variational Propagation Overview ===\n")
print("Initial State:")
print(f"  Semi-major axis: {oe[0] / 1000:.1f} km")
print(f"  Position std: {np.sqrt(P0[0, 0]):.1f} m")
print(f"  Velocity std: {np.sqrt(P0[3, 3]) * 1000:.2f} mm/s")

# Propagate for one orbital period
orbital_period = bh.orbital_period(oe[0])
prop.propagate_to(epoch + orbital_period)

# === STM Access ===
print("\n--- State Transition Matrix (STM) ---")
stm = prop.stm()
print(f"STM shape: {stm.shape}")
print(
    f"STM determinant: {np.linalg.det(stm):.6f} (should be ~1 for conservative forces)"
)

# STM at intermediate time (half orbit)
stm_half = prop.stm_at(epoch + orbital_period / 2)
print(f"STM at t/2 available: {stm_half is not None}")

# === Covariance Propagation ===
print("\n--- Covariance Propagation ---")

# Manual propagation: P(t) = STM @ P0 @ STM^T
P_manual = stm @ P0 @ stm.T

# Using built-in covariance retrieval
P_gcrf = prop.covariance_gcrf(epoch + orbital_period)
P_rtn = prop.covariance_rtn(epoch + orbital_period)

# Extract position uncertainties
pos_std_gcrf = np.sqrt(np.diag(P_gcrf[:3, :3]))
pos_std_rtn = np.sqrt(np.diag(P_rtn[:3, :3]))

print("Position std (GCRF frame):")
print(
    f"  X: {pos_std_gcrf[0]:.1f} m, Y: {pos_std_gcrf[1]:.1f} m, Z: {pos_std_gcrf[2]:.1f} m"
)
print("Position std (RTN frame):")
print(
    f"  R: {pos_std_rtn[0]:.1f} m, T: {pos_std_rtn[1]:.1f} m, N: {pos_std_rtn[2]:.1f} m"
)

# === Sensitivity Analysis ===
print("\n--- Parameter Sensitivity ---")
sens = prop.sensitivity()
print(f"Sensitivity matrix shape: {sens.shape}")

# Position sensitivity magnitude to each parameter
param_names = ["mass", "drag_area", "Cd", "srp_area", "Cr"]
print("\nPosition sensitivity to 1% parameter uncertainty:")
for i, name in enumerate(param_names):
    pos_sens_mag = np.linalg.norm(sens[:3, i])
    param_uncertainty = params[i] * 0.01  # 1% uncertainty
    pos_error = pos_sens_mag * param_uncertainty
    print(f"  {name:10s}: {pos_error:.2f} m")

# === Summary ===
print("\n--- Summary ---")
total_pos_std_initial = np.sqrt(np.trace(P0[:3, :3]))
total_pos_std_final = np.sqrt(np.trace(P_gcrf[:3, :3]))
print(
    f"Total position uncertainty: {total_pos_std_initial:.1f} m -> {total_pos_std_final:.1f} m"
)
print(f"Uncertainty growth factor: {total_pos_std_final / total_pos_std_initial:.1f}x")

# Validate outputs
assert stm.shape == (6, 6)
assert sens.shape == (6, 5)
assert P_gcrf.shape == (6, 6)
assert P_rtn.shape == (6, 6)
assert total_pos_std_final >= total_pos_std_initial

print("\nExample validated successfully!")
```


## Architecture Overview

### Configuration Hierarchy

Variational propagation is configured through the `VariationalConfig` within `NumericalPropagationConfig`:

```.no-linenums
NumericalPropagationConfig
├── method: IntegrationMethod
├── integrator: IntegratorConfig
└── variational: VariationalConfig
    ├── enable_stm: bool
    ├── enable_sensitivity: bool
    ├── store_stm_history: bool
    ├── store_sensitivity_history: bool
    ├── jacobian_method: DifferenceMethod
    └── sensitivity_method: DifferenceMethod
```

### Auto-Enable Behavior

Providing `initial_covariance` when creating the propagator automatically enables STM propagation, even without explicitly setting `enable_stm = true`.

---

## State Transition Matrices (STM)

The State Transition Matrix (STM) is a foundational tool for linear uncertainty propagation. It describes how small perturbations in the initial state map to perturbations at a later time:

$$\delta \mathbf{x}(t) = \Phi(t, t_0) \delta \mathbf{x}(t_0)$$

where $\Phi(t, t_0)$ is the 6x6 STM from epoch $t_0$ to time $t$.

### STM Structure

For orbital mechanics with state $\mathbf{x} = [x, y, z, v_x, v_y, v_z]^T$, the 6x6 STM has structure:

$$\Phi = \begin{bmatrix} \frac{\partial \mathbf{r}}{\partial \mathbf{r}_0} & \frac{\partial \mathbf{r}}{\partial \mathbf{v}_0} \\ \frac{\partial \mathbf{v}}{\partial \mathbf{r}_0} & \frac{\partial \mathbf{v}}{\partial \mathbf{v}_0} \end{bmatrix}$$

| Submatrix | Location | Physical Meaning |
|-----------|----------|------------------|
| $\frac{\partial \mathbf{r}}{\partial \mathbf{r}_0}$ | Upper left | Position sensitivity to initial position |
| $\frac{\partial \mathbf{r}}{\partial \mathbf{v}_0}$ | Upper right | Position sensitivity to initial velocity |
| $\frac{\partial \mathbf{v}}{\partial \mathbf{r}_0}$ | Lower left | Velocity sensitivity to initial position |
| $\frac{\partial \mathbf{v}}{\partial \mathbf{v}_0}$ | Lower right | Velocity sensitivity to initial velocity |

### STM Properties

The STM has several important mathematical properties:

1. **Identity at initial time**: $\Phi(t_0, t_0) = I$

2. **Composition**: STMs can be composed to span longer intervals:
   $\Phi(t_2, t_0) = \Phi(t_2, t_1) \Phi(t_1, t_0)$

3. **Determinant preservation**: For Hamiltonian systems (conservative forces only), $\det(\Phi) = 1$

### Enabling STM Propagation


```python
import numpy as np
import brahe as bh

# Initialize EOP data
bh.initialize_eop()

# Create initial epoch and state
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)
oe = np.array([bh.R_EARTH + 500e3, 0.01, 45.0, 15.0, 30.0, 45.0])
state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

# Method 1: Enable STM via builder pattern
prop_config = bh.NumericalPropagationConfig.default().with_stm().with_stm_history()

# Create propagator with two-body gravity
prop = bh.NumericalOrbitPropagator(
    epoch,
    state,
    prop_config,
    bh.ForceModelConfig.two_body(),
    None,
)

print("=== STM Propagation Example ===\n")

# Propagate for one orbital period
orbital_period = bh.orbital_period(oe[0])
prop.propagate_to(epoch + orbital_period)

# Access STM at final time
stm = prop.stm()
print(f"Final STM shape: {stm.shape}")
print(f"STM determinant: {np.linalg.det(stm):.6f}")

# STM at initial time should be identity
stm_initial = prop.stm_at(epoch)
print("\nSTM at t=0 (should be identity):")
print(f"  Max off-diagonal: {np.max(np.abs(stm_initial - np.eye(6))):.2e}")

# STM at intermediate time
half_period = epoch + orbital_period / 2
stm_half = prop.stm_at(half_period)
print("\nSTM at t=T/2:")
print(f"  Determinant: {np.linalg.det(stm_half):.6f}")

# STM composition property: Phi(t2,t0) = Phi(t2,t1) * Phi(t1,t0)
# For verification, we check that the STM is invertible
stm_inv = np.linalg.inv(stm)
identity_check = stm @ stm_inv
print("\nSTM * STM^-1 (should be identity):")
print(f"  Max deviation from I: {np.max(np.abs(identity_check - np.eye(6))):.2e}")

# STM structure interpretation
print("\n=== STM Structure ===")
print("Upper-left 3x3: Position sensitivity to initial position")
print("Upper-right 3x3: Position sensitivity to initial velocity")
print("Lower-left 3x3: Velocity sensitivity to initial position")
print("Lower-right 3x3: Velocity sensitivity to initial velocity")

# Show magnitude of each block
pos_pos = np.linalg.norm(stm[:3, :3])
pos_vel = np.linalg.norm(stm[:3, 3:])
vel_pos = np.linalg.norm(stm[3:, :3])
vel_vel = np.linalg.norm(stm[3:, 3:])

print("\nBlock Frobenius norms after one orbit:")
print(f"  dr/dr0: {pos_pos:.2f}")
print(f"  dr/dv0: {pos_vel:.2f}")
print(f"  dv/dr0: {vel_pos:.6f}")
print(f"  dv/dv0: {vel_vel:.2f}")

# Validate
assert stm.shape == (6, 6)
assert np.abs(np.linalg.det(stm) - 1.0) < 1e-6  # Hamiltonian system preserves volume
assert stm_initial is not None
assert stm_half is not None

print("\nExample validated successfully!")
```


---

## Covariance Propagation

The primary application of the STM is propagating uncertainty. Given an initial covariance $P_0$, the propagated covariance is:

$$P(t) = \Phi(t, t_0) P_0 \Phi(t, t_0)^T$$

### Creating a Propagator with Initial Covariance


```python
import numpy as np
import brahe as bh

# Initialize EOP data
bh.initialize_eop()

# Create initial epoch and state
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)
oe = np.array([bh.R_EARTH + 500e3, 0.01, 45.0, 15.0, 30.0, 45.0])
state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

# Create propagation config with STM enabled
prop_config = bh.NumericalPropagationConfig.default().with_stm()

# Create propagator (two-body for clean demonstration)
prop = bh.NumericalOrbitPropagator(
    epoch,
    state,
    prop_config,
    bh.ForceModelConfig.two_body(),
    None,
)

# Define initial covariance (diagonal)
# Position uncertainty: 10 m in each axis
# Velocity uncertainty: 0.01 m/s in each axis
P0 = np.diag([100.0, 100.0, 100.0, 0.0001, 0.0001, 0.0001])

print("Initial Covariance (diagonal, sqrt):")
print(f"  Position std: {np.sqrt(P0[0, 0]):.1f} m")
print(f"  Velocity std: {np.sqrt(P0[3, 3]) * 1000:.2f} mm/s")

# Propagate for one orbital period
orbital_period = bh.orbital_period(oe[0])
prop.propagate_to(epoch + orbital_period)

# Get the State Transition Matrix
stm = prop.stm()
print(f"\nSTM shape: {stm.shape}")

# Propagate covariance: P(t) = Phi @ P0 @ Phi^T
P = stm @ P0 @ stm.T

# Extract position and velocity uncertainties
pos_cov = P[:3, :3]
vel_cov = P[3:, 3:]

print("\nPropagated Covariance after one orbit:")
print(
    f"  Position std (x,y,z): ({np.sqrt(pos_cov[0, 0]):.1f}, {np.sqrt(pos_cov[1, 1]):.1f}, {np.sqrt(pos_cov[2, 2]):.1f}) m"
)
print(
    f"  Velocity std (x,y,z): ({np.sqrt(vel_cov[0, 0]) * 1000:.2f}, {np.sqrt(vel_cov[1, 1]) * 1000:.2f}, {np.sqrt(vel_cov[2, 2]) * 1000:.2f}) mm/s"
)

# Compute position uncertainty magnitude
pos_uncertainty_initial = np.sqrt(np.trace(P0[:3, :3]))
pos_uncertainty_final = np.sqrt(np.trace(pos_cov))

print("\nTotal position uncertainty:")
print(f"  Initial: {pos_uncertainty_initial:.1f} m")
print(f"  Final:   {pos_uncertainty_final:.1f} m")
print(f"  Growth:  {pos_uncertainty_final / pos_uncertainty_initial:.1f}x")

# Validate that covariance was propagated
assert stm is not None
assert stm.shape == (6, 6)
assert pos_uncertainty_final >= pos_uncertainty_initial  # Uncertainty grows

print("\nExample validated successfully!")
```


### Covariance in RTN Frame

The RTN (Radial-Tangential-Normal) frame provides physical insight into how uncertainty evolves relative to the orbit.


```python
import numpy as np
import brahe as bh

# Initialize EOP data
bh.initialize_eop()

# Create initial epoch and state
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)
oe = np.array([bh.R_EARTH + 500e3, 0.01, 45.0, 15.0, 30.0, 45.0])
state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

# Enable STM for covariance propagation
prop_config = bh.NumericalPropagationConfig.default().with_stm().with_stm_history()

# Define initial covariance in ECI frame
# Position uncertainty: 10 m in each axis
# Velocity uncertainty: 0.01 m/s in each axis
P0 = np.diag([100.0, 100.0, 100.0, 0.0001, 0.0001, 0.0001])

# Create propagator with initial covariance
prop = bh.NumericalOrbitPropagator(
    epoch,
    state,
    prop_config,
    bh.ForceModelConfig.two_body(),
    None,
    initial_covariance=P0,
)

print("=== Covariance in RTN Frame ===\n")
print("Initial position std (ECI): 10.0 m in each axis")

# Propagate for one orbital period
orbital_period = bh.orbital_period(oe[0])
prop.propagate_to(epoch + orbital_period)

# Get covariance in different frames
target = epoch + orbital_period
P_gcrf = prop.covariance_gcrf(target)
P_rtn = prop.covariance_rtn(target)

# Extract position covariances (3x3 upper-left block)
pos_cov_gcrf = P_gcrf[:3, :3]
pos_cov_rtn = P_rtn[:3, :3]

print("\n--- GCRF Frame Results ---")
print("Position std (X, Y, Z):")
print(f"  X: {np.sqrt(pos_cov_gcrf[0, 0]):.1f} m")
print(f"  Y: {np.sqrt(pos_cov_gcrf[1, 1]):.1f} m")
print(f"  Z: {np.sqrt(pos_cov_gcrf[2, 2]):.1f} m")

print("\n--- RTN Frame Results ---")
print("Position std (R, T, N):")
print(f"  Radial (R):     {np.sqrt(pos_cov_rtn[0, 0]):.1f} m  <- Altitude uncertainty")
print(f"  Tangential (T): {np.sqrt(pos_cov_rtn[1, 1]):.1f} m  <- Along-track timing")
print(f"  Normal (N):     {np.sqrt(pos_cov_rtn[2, 2]):.1f} m  <- Cross-track offset")

# Physical interpretation
print("\n--- Physical Interpretation ---")
print("RTN frame aligns with the orbit:")
print("  R (Radial): Points from Earth center to satellite")
print("  T (Tangential): Points along velocity direction")
print("  N (Normal): Completes right-hand system (cross-track)")
print()
print("Key insight: Along-track (T) uncertainty grows fastest because")
print("velocity uncertainty causes timing errors that accumulate.")
print(
    f"After one orbit: T/R ratio = {np.sqrt(pos_cov_rtn[1, 1]) / np.sqrt(pos_cov_rtn[0, 0]):.1f}x"
)

# Show correlation structure
print("\n--- Position Correlation Matrix (RTN) ---")
pos_std_rtn = np.sqrt(np.diag(pos_cov_rtn))
corr_rtn = pos_cov_rtn / np.outer(pos_std_rtn, pos_std_rtn)
print("       R      T      N")
for i, name in enumerate(["R", "T", "N"]):
    print(
        f"  {name}  {corr_rtn[i, 0]:6.3f} {corr_rtn[i, 1]:6.3f} {corr_rtn[i, 2]:6.3f}"
    )

# Validate
assert P_gcrf.shape == (6, 6)
assert P_rtn.shape == (6, 6)
assert np.sqrt(pos_cov_rtn[1, 1]) > np.sqrt(pos_cov_rtn[0, 0])  # T > R

print("\nExample validated successfully!")
```


### RTN Frame Interpretation

| Component | Physical Meaning | Typical Behavior |
|-----------|------------------|------------------|
| Radial (R) | Altitude uncertainty | Bounded oscillation |
| Tangential (T) | Along-track timing | Unbounded growth |
| Normal (N) | Cross-track offset | Bounded oscillation |

The along-track (tangential) uncertainty grows fastest because velocity uncertainty causes timing errors that accumulate over time. After one orbit, the T/R ratio is typically 20-30x.

### Covariance Evolution Visualization

The following plot shows how position uncertainty evolves over three orbital periods in the ECI frame:


**Plot Source**

```python
import numpy as np
import plotly.graph_objects as go

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))
from brahe_theme import save_themed_html, get_theme_colors

# Configuration
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# Initialize EOP data
bh.initialize_eop()

# Create initial epoch and state
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)
oe = np.array([bh.R_EARTH + 500e3, 0.01, 45.0, 15.0, 30.0, 45.0])
state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

# Create propagation config with STM enabled and history storage
prop_config = bh.NumericalPropagationConfig.default().with_stm().with_stm_history()

# Create propagator (two-body for clean demonstration)
prop = bh.NumericalOrbitPropagator(
    epoch,
    state,
    prop_config,
    bh.ForceModelConfig.two_body(),
    None,
)

# Define initial covariance (diagonal)
# Position uncertainty: 10 m in each axis (100 m² variance)
# Velocity uncertainty: 0.01 m/s in each axis (0.0001 m²/s² variance)
P0 = np.diag([100.0, 100.0, 100.0, 0.0001, 0.0001, 0.0001])

# Propagate for 3 orbital periods
orbital_period = bh.orbital_period(oe[0])
total_time = 3 * orbital_period
prop.propagate_to(epoch + total_time)

# Sample covariance evolution
times = []  # in orbital periods
pos_sigma_r = []  # Radial (x) std dev
pos_sigma_t = []  # Tangential (y) std dev
pos_sigma_n = []  # Normal (z) std dev
pos_total = []  # Total position std dev

dt = orbital_period / 50  # 50 samples per orbit
t = 0.0
while t <= total_time:
    current_epoch = epoch + t
    stm = prop.stm_at(current_epoch)

    if stm is not None:
        # Propagate covariance: P(t) = STM @ P0 @ STM^T
        P = stm @ P0 @ stm.T

        # Extract position standard deviations
        sigma_x = np.sqrt(P[0, 0])
        sigma_y = np.sqrt(P[1, 1])
        sigma_z = np.sqrt(P[2, 2])

        times.append(t / orbital_period)  # Convert to orbital periods
        pos_sigma_r.append(sigma_x)
        pos_sigma_t.append(sigma_y)
        pos_sigma_n.append(sigma_z)
        pos_total.append(np.sqrt(sigma_x**2 + sigma_y**2 + sigma_z**2))

    t += dt


def create_figure(theme):
    colors = get_theme_colors(theme)

    fig = go.Figure()

    # Position uncertainty traces
    fig.add_trace(
        go.Scatter(
            x=times,
            y=pos_sigma_r,
            mode="lines",
            name="X (radial-like)",
            line=dict(color=colors["primary"], width=2),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=times,
            y=pos_sigma_t,
            mode="lines",
            name="Y (along-track-like)",
            line=dict(color=colors["secondary"], width=2),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=times,
            y=pos_sigma_n,
            mode="lines",
            name="Z (cross-track-like)",
            line=dict(color=colors["accent"], width=2),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=times,
            y=pos_total,
            mode="lines",
            name="Total (RSS)",
            line=dict(color=colors["error"], width=2, dash="dash"),
        )
    )

    # Initial uncertainty reference
    initial_total = np.sqrt(3 * 100.0)  # sqrt(3 * 100 m²)
    fig.add_hline(
        y=initial_total,
        line_dash="dot",
        line_color="gray",
        annotation_text=f"Initial: {initial_total:.1f} m",
        annotation_position="top right",
    )

    fig.update_layout(
        title="Position Uncertainty Evolution (Two-Body)",
        xaxis_title="Time (orbital periods)",
        yaxis_title="Position Std Dev (m)",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=500,
        margin=dict(l=60, r=40, t=80, b=60),
    )

    return fig


# Save themed HTML files
light_path, dark_path = save_themed_html(create_figure, OUTDIR / SCRIPT_NAME)
print(f"Generated {light_path}")
print(f"Generated {dark_path}")
```

### RTN Covariance Evolution

The RTN frame clearly shows why along-track error dominates:


**Plot Source**

```python
import brahe as bh
import numpy as np
import plotly.graph_objects as go

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))
from brahe_theme import save_themed_html, get_theme_colors

# Configuration
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# Initialize EOP data
bh.initialize_eop()

# Create initial epoch and state
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)
oe = np.array([bh.R_EARTH + 500e3, 0.01, 45.0, 15.0, 30.0, 45.0])
state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

# Create propagation config with STM enabled and history storage
prop_config = bh.NumericalPropagationConfig.default().with_stm().with_stm_history()

# Define initial covariance (diagonal)
# Position uncertainty: 10 m in each axis (100 m² variance)
# Velocity uncertainty: 0.01 m/s in each axis (0.0001 m²/s² variance)
P0 = np.diag([100.0, 100.0, 100.0, 0.0001, 0.0001, 0.0001])

# Create propagator with initial covariance
prop = bh.NumericalOrbitPropagator(
    epoch,
    state,
    prop_config,
    bh.ForceModelConfig.two_body(),
    None,
    initial_covariance=P0,
)

# Propagate for 3 orbital periods
orbital_period = bh.orbital_period(oe[0])
total_time = 3 * orbital_period
prop.propagate_to(epoch + total_time)

# Sample RTN covariance evolution using STM-based propagation
# This avoids numerical issues with covariance interpolation
times = []  # in orbital periods
sigma_r = []  # Radial std dev
sigma_t = []  # Tangential std dev
sigma_n = []  # Normal std dev

dt = orbital_period / 50  # 50 samples per orbit
t = 0.0
while t <= total_time:
    current_epoch = epoch + t
    stm = prop.stm_at(current_epoch)

    if stm is not None:
        # Propagate covariance in ECI: P(t) = STM @ P0 @ STM^T
        P_eci = stm @ P0 @ stm.T

        # Get state at current epoch to compute RTN rotation
        state_t = prop.state(current_epoch)
        if state_t is not None:
            # Compute RTN rotation matrix from ECI state
            r = state_t[:3]
            v = state_t[3:]

            # RTN basis vectors
            r_hat = r / np.linalg.norm(r)  # Radial
            h = np.cross(r, v)  # Angular momentum
            n_hat = h / np.linalg.norm(h)  # Normal (cross-track)
            t_hat = np.cross(n_hat, r_hat)  # Tangential (along-track)

            # Rotation matrix from ECI to RTN (for position)
            R_eci_to_rtn = np.array([r_hat, t_hat, n_hat])

            # Transform position covariance to RTN
            P_pos_eci = P_eci[:3, :3]
            P_pos_rtn = R_eci_to_rtn @ P_pos_eci @ R_eci_to_rtn.T

            times.append(t / orbital_period)
            sigma_r.append(np.sqrt(P_pos_rtn[0, 0]))
            sigma_t.append(np.sqrt(P_pos_rtn[1, 1]))
            sigma_n.append(np.sqrt(P_pos_rtn[2, 2]))

    t += dt


def create_figure(theme):
    colors = get_theme_colors(theme)

    fig = go.Figure()

    # RTN uncertainty traces
    fig.add_trace(
        go.Scatter(
            x=times,
            y=sigma_r,
            mode="lines",
            name="Radial (R)",
            line=dict(color=colors["primary"], width=2),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=times,
            y=sigma_t,
            mode="lines",
            name="Tangential (T)",
            line=dict(color=colors["secondary"], width=2),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=times,
            y=sigma_n,
            mode="lines",
            name="Normal (N)",
            line=dict(color=colors["accent"], width=2),
        )
    )

    # Add annotations for physical interpretation
    fig.add_annotation(
        x=2.5,
        y=sigma_t[-1] * 0.9,
        text="Along-track: unbounded growth",
        showarrow=False,
        font=dict(size=10),
    )

    fig.add_annotation(
        x=2.5,
        y=sigma_r[-1] * 1.5,
        text="Radial/Normal: bounded oscillation",
        showarrow=False,
        font=dict(size=10),
    )

    # Initial uncertainty reference
    initial_std = 10.0  # m
    fig.add_hline(
        y=initial_std,
        line_dash="dot",
        line_color="gray",
        annotation_text=f"Initial: {initial_std:.0f} m",
        annotation_position="top left",
    )

    fig.update_layout(
        title="Position Uncertainty Evolution in RTN Frame",
        xaxis_title="Time (orbital periods)",
        yaxis_title="Position Std Dev (m)",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=500,
        margin=dict(l=60, r=40, t=80, b=60),
    )

    return fig


# Save themed HTML files
light_path, dark_path = save_themed_html(create_figure, OUTDIR / SCRIPT_NAME)
print(f"Generated {light_path}")
print(f"Generated {dark_path}")
```

---

## Sensitivity Propagation

In addition to STM propagation (which tracks sensitivity to initial state), the propagator can compute **parameter sensitivity** - how the state changes with respect to configuration parameters.

### Parameter Sensitivity

The sensitivity matrix $S(t)$ describes how the state at time $t$ depends on the parameters:

$$S(t) = \frac{\partial \mathbf{x}(t)}{\partial \mathbf{p}}$$

where $\mathbf{p}$ is the parameter vector. This enables answering questions like:

- "How does a 1% uncertainty in drag coefficient affect position prediction?"
- "What is the impact of mass uncertainty on orbit determination?"

### Configuration Parameters

The default parameter vector contains spacecraft physical properties:

| Index | Parameter | Units | Description |
|-------|-----------|-------|-------------|
| 0 | mass | kg | Spacecraft mass |
| 1 | drag_area | m² | Cross-sectional area for drag |
| 2 | Cd | - | Drag coefficient |
| 3 | srp_area | m² | Cross-sectional area for SRP |
| 4 | Cr | - | Solar radiation pressure coefficient |

### Enabling Sensitivity Propagation


```python
import numpy as np
import brahe as bh

# Initialize EOP and space weather data (required for NRLMSISE-00 drag model)
bh.initialize_eop()
bh.initialize_sw()

# Create initial epoch and state
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)
oe = np.array([bh.R_EARTH + 400e3, 0.01, 45.0, 0.0, 0.0, 0.0])
state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

# Create propagation config with sensitivity enabled
prop_config = (
    bh.NumericalPropagationConfig.default()
    .with_sensitivity()
    .with_sensitivity_history()
)

# Define spacecraft parameters: [mass, drag_area, Cd, srp_area, Cr]
params = np.array([500.0, 2.0, 2.2, 2.0, 1.3])

# Create propagator with full force model (needed for parameter sensitivity)
prop = bh.NumericalOrbitPropagator(
    epoch,
    state,
    prop_config,
    bh.ForceModelConfig.default(),
    params=params,
)

print("Spacecraft Parameters:")
print(f"  Mass: {params[0]:.1f} kg")
print(f"  Drag area: {params[1]:.1f} m²")
print(f"  Drag coefficient (Cd): {params[2]:.1f}")
print(f"  SRP area: {params[3]:.1f} m²")
print(f"  SRP coefficient (Cr): {params[4]:.1f}")

# Propagate for one orbital period
orbital_period = bh.orbital_period(oe[0])
prop.propagate_to(epoch + orbital_period)

# Get the sensitivity matrix (6 x 5)
sens = prop.sensitivity()

if sens is not None:
    print(f"\nSensitivity Matrix shape: {sens.shape}")
    print(
        "(Rows: state components [x,y,z,vx,vy,vz], Cols: params [mass,A_d,Cd,A_s,Cr])"
    )

    # Analyze position sensitivity to each parameter
    pos_sens = sens[:3, :]  # First 3 rows
    param_names = ["mass", "drag_area", "Cd", "srp_area", "Cr"]

    print("\nPosition sensitivity magnitude to each parameter:")
    for i, name in enumerate(param_names):
        # Position sensitivity magnitude for this parameter
        mag = np.linalg.norm(pos_sens[:, i])
        print(f"  {name:10s}: {mag:.3e} m per unit param")

    # Compute impact of 1% parameter uncertainties
    print("\nPosition error from 1% parameter uncertainty:")
    param_uncertainties = params * 0.01  # 1% of each parameter
    for i, name in enumerate(param_names):
        # dpos = sensitivity * dparam
        pos_error = np.linalg.norm(pos_sens[:, i]) * param_uncertainties[i]
        print(f"  {name:10s}: {pos_error:.1f} m")

    # Total position error (RSS)
    total_pos_error = 0.0
    for i in range(len(params)):
        pos_error = np.linalg.norm(pos_sens[:, i]) * param_uncertainties[i]
        total_pos_error += pos_error**2
    total_pos_error = np.sqrt(total_pos_error)
    print(f"\n  Total (RSS): {total_pos_error:.1f} m")

    # Validate
    assert sens.shape == (6, 5)
    print("\nExample validated successfully!")
else:
    print("\nSensitivity not available (may require full force model)")
```


### Interpreting Sensitivity Results

The sensitivity matrix $S$ is 6x5 (state dimension x parameter count):

- **Column 0**: Sensitivity to mass - affects drag acceleration ($a \propto 1/m$)
- **Column 1**: Sensitivity to drag area - affects drag force
- **Column 2**: Sensitivity to Cd - drag coefficient uncertainty
- **Column 3**: Sensitivity to SRP area - solar radiation pressure
- **Column 4**: Sensitivity to Cr - SRP coefficient uncertainty

Physical insights:

- For LEO orbits, drag parameters (mass, drag_area, Cd) typically dominate
- For GEO orbits, SRP parameters (srp_area, Cr) become more important
- Two-body propagation shows zero sensitivity (no force depends on parameters)
- Sensitivity grows over time as perturbation effects accumulate

### Sensitivity Evolution Visualization

The following plot shows how position sensitivity to each parameter evolves over time for a LEO orbit:


**Plot Source**

```python
import numpy as np
import plotly.graph_objects as go

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))
from brahe_theme import save_themed_html, get_theme_colors

# Configuration
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# Initialize EOP and space weather data
# (Space weather is required for NRLMSISE00 atmospheric model)
bh.initialize_eop()
bh.initialize_sw()

# Create initial epoch and state (LEO orbit with significant drag)
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)
oe = np.array([bh.R_EARTH + 400e3, 0.01, 45.0, 0.0, 0.0, 0.0])
state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)

# Create propagation config with sensitivity enabled and history storage
prop_config = (
    bh.NumericalPropagationConfig.default()
    .with_sensitivity()
    .with_sensitivity_history()
)

# Define spacecraft parameters: [mass, drag_area, Cd, srp_area, Cr]
params = np.array([500.0, 2.0, 2.2, 2.0, 1.3])

# Create propagator with full force model (uses NRLMSISE00 for drag)
prop = bh.NumericalOrbitPropagator(
    epoch,
    state,
    prop_config,
    bh.ForceModelConfig.default(),
    params=params,
)

# Propagate for 3 orbital periods
orbital_period = bh.orbital_period(oe[0])
total_time = 3 * orbital_period
prop.propagate_to(epoch + total_time)

# Sample sensitivity evolution
param_names = ["mass", "drag_area", "Cd", "srp_area", "Cr"]
times = []  # in orbital periods
sens_mag = {name: [] for name in param_names}  # Position sensitivity magnitude

dt = orbital_period / 50  # 50 samples per orbit
t = 0.0
while t <= total_time:
    current_epoch = epoch + t
    sens = prop.sensitivity_at(current_epoch)

    if sens is not None:
        times.append(t / orbital_period)  # Convert to orbital periods

        # Compute position sensitivity magnitude for each parameter
        for i, name in enumerate(param_names):
            pos_sens = np.linalg.norm(sens[:3, i])
            sens_mag[name].append(pos_sens)

    t += dt


def create_figure(theme):
    colors = get_theme_colors(theme)

    fig = go.Figure()

    color_map = {
        "mass": colors["primary"],
        "drag_area": colors["secondary"],
        "Cd": colors["accent"],
        "srp_area": colors["error"],
        "Cr": "gray",
    }

    # Add traces for each parameter
    for name in param_names:
        if sens_mag[name]:
            fig.add_trace(
                go.Scatter(
                    x=times,
                    y=sens_mag[name],
                    mode="lines",
                    name=name,
                    line=dict(color=color_map[name], width=2),
                )
            )

    fig.update_layout(
        title="Position Sensitivity to Parameters (LEO, 400 km)",
        xaxis_title="Time (orbital periods)",
        yaxis_title="Position Sensitivity (m per unit param)",
        yaxis_type="log",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=500,
        margin=dict(l=60, r=40, t=80, b=60),
    )

    return fig


# Save themed HTML files
light_path, dark_path = save_themed_html(create_figure, OUTDIR / SCRIPT_NAME)
print(f"Generated {light_path}")
print(f"Generated {dark_path}")
```

---

## Configuration Reference

### VariationalConfig Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enable_stm` | bool | false | Enable State Transition Matrix computation |
| `enable_sensitivity` | bool | false | Enable parameter sensitivity computation |
| `store_stm_history` | bool | false | Store STM at each trajectory point |
| `store_sensitivity_history` | bool | false | Store sensitivity at each trajectory point |
| `jacobian_method` | DifferenceMethod | Central | Finite difference method for Jacobian |
| `sensitivity_method` | DifferenceMethod | Central | Finite difference method for sensitivity |

### DifferenceMethod Options

| Method | Accuracy | Cost | Description |
|--------|----------|------|-------------|
| Forward | O(h) | S+1 evaluations | First-order forward differences |
| Central | O(h²) | 2S evaluations | Second-order central differences (default) |
| Backward | O(h) | S+1 evaluations | First-order backward differences |

### Computational Considerations

STM and sensitivity computation significantly increase computational cost:

| Configuration | State dimension | Memory per step |
|---------------|-----------------|-----------------|
| State only | 6 | ~48 bytes |
| With STM | 42 (6 + 36) | ~336 bytes |
| With Sensitivity | 36 (6 + 30) | ~288 bytes |
| With Both | 72 (6 + 36 + 30) | ~576 bytes |

---

## See Also

- [Integrator Configuration](integrator_configuration.md) - Variational equation settings
- [Numerical Orbit Propagator](numerical_orbit_propagator.md) - Propagator fundamentals
- [Force Models](force_models.md) - Force model configuration