# SSN Radar Tracking: EKF, UKF, and Batch Least Squares

In this example we'll simulate Space Surveillance Network (SSN) radar tracking of a LEO object and estimate its orbit sequentially with an Extended Kalman Filter (EKF) and an Unscented Kalman Filter (UKF). We'll load the Vallado SSN sensor dataset, find the passes visible to each sensor over a 6-hour tracking arc, simulate az/el/range measurements during those passes, and compare how the two filters converge on the true orbit. A separate script, `ssn_tracking_bls.py`, solves the same scenario with Batch Least Squares (BLS) instead; we walk through it near the end of this page.

---

## Setup

First, we'll import the necessary libraries, initialize Earth orientation parameters, and configure the tracking arc:

```python
#!/usr/bin/env python
# /// script
# dependencies = ["brahe", "plotly", "numpy"]
# ///

"""
SSN Radar Tracking: Extended and Unscented Kalman Filters

This example simulates Space Surveillance Network (SSN) radar tracking of a
LEO object and estimates its orbit sequentially with an Extended Kalman
Filter and an Unscented Kalman Filter. It loads the Vallado SSN sensor
dataset, builds az/el/range sensors, visualizes the sensor network's ground
coverage against a simulated LEO ground track, simulates radar measurements
during passes over a 6-hour tracking arc, processes them sequentially with
both filters while propagating through the gaps between passes, and
compares each filter's true position error against its formal 3-sigma
uncertainty.

A batch-estimation companion, ssn_tracking_bls.py, reproduces the same
scenario and solves for the orbit with Batch Least Squares instead; it is
excluded from the automated example tests because BLS re-propagates the
full arc at every iteration and takes on the order of three minutes to run.
"""

# --8<-- [start:all]
# --8<-- [start:preamble]
import os
import pathlib
import sys
import time

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import brahe as bh

bh.initialize_eop()

# Configuration
MEAS_INTERVAL = 15.0  # seconds between measurements during a pass
DURATION = 6 * 3600.0  # tracking duration (seconds)
SEED = 42
PROPAGATE_STEP = 60.0  # gap-propagation step (seconds)
# --8<-- [end:preamble]

# Configuration for output files
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# --8<-- [start:load_sensors]
# Load the Vallado SSN sensor sites and build sensors from the fully
# calibrated sites. The dataset mixes radar/phased-array (azel_range, measuring
# az/el/range) and optical (angles-only az/el) trackers; both are supported.
# from_locations_calibrated keeps only sites with full Table 4-4 calibration --
# it drops two radar sites (Haystack, HAX) that lack noise values, while
# from_locations would include them instead, defaulted to zero noise.
sites = bh.datasets.ssn_sensors.load()
sensors = bh.SimpleSSNSensor.from_locations_calibrated(sites, seed=SEED)
print(f"Loaded {len(sites)} SSN sites, {len(sensors)} calibrated sensors")

print("\n" + "=" * 100)
print("SSN Sensor Network")
print("=" * 100)
print(
    f"{'Name':<28}{'System':<12}{'El Min':>8}{'Range Max':>12}"
    f"{'Az Noise':>10}{'El Noise':>10}{'Range Noise':>13}"
)
print("-" * 100)
for s in sensors:
    props = s.location.properties
    system = props.get("system", "?")
    az_noise = props.get("az_noise_deg", float("nan"))
    el_noise = props.get("el_noise_deg", float("nan"))
    range_noise = props.get("range_noise_m", float("nan"))
    range_max_str = (
        f"{s.range_max / 1e3:>9.0f} km" if s.range_max is not None else "  unlimited"
    )
    print(
        f"{s.name:<28}{system:<12}{s.el_min:>7.1f}°{range_max_str:>12}"
        f"{az_noise:>9.4f}°{el_noise:>9.4f}°{range_noise:>11.1f} m"
    )
print("=" * 100)
# --8<-- [end:load_sensors]

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

# --8<-- [start:visualize_network]
# Assign each sensor a stable color, reused for its measurement traces in the
# figure below, so a comm cone's color on the map identifies the same sensor
# in the az/el/range plot.
PALETTE = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
    "#aec7e8",
    "#ffbb78",
    "#98df8a",
    "#ff9896",
    "#c5b0d5",
]
sensor_colors = {s.name: PALETTE[i % len(PALETTE)] for i, s in enumerate(sensors)}

fig_network = bh.plot_groundtrack(
    trajectories=[
        {"trajectory": truth_prop.trajectory, "color": "red", "line_width": 2}
    ],
    ground_stations=[
        {"stations": [s.location], "color": sensor_colors[s.name], "alpha": 0.25}
        for s in sensors
    ],
    gs_cone_altitude=700e3,
    gs_min_elevation=5.0,
    basemap="natural_earth",
    backend="plotly",
)

# plot_groundtrack's built-in legend can't label per-sensor groups (every
# station-marker trace is named "Ground Stations"), so add a small manual
# legend mapping each sensor's name to its color.
for s in sensors:
    fig_network.add_trace(
        go.Scattergeo(
            lat=[None],
            lon=[None],
            mode="markers",
            marker={"size": 8, "color": sensor_colors[s.name]},
            name=s.name,
            showlegend=True,
        )
    )
fig_network.update_layout(showlegend=True)
# --8<-- [end:visualize_network]

# --8<-- [start:simulate_measurements]
# Find passes and simulate measurements only inside them. Sensor measurement
# buckets for the figure below are filled as each pass is simulated, since
# per-sensor plotting order doesn't depend on the global time order that the
# sequential filters need; only `observations` has to be globally sorted.
observations = []
passes = []  # (sensor_name, window, n_obs)
sensor_meas = {
    i: {"t": [], "az": [], "el": [], "range_km": []} for i in range(len(sensors))
}
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
            passes.append((sensor.name, w, len(obs)))
        bucket = sensor_meas[i]
        for o in obs:
            bucket["t"].append((o.epoch - epoch) / 60.0)
            bucket["az"].append(o.measurement[0])
            bucket["el"].append(o.measurement[1])
            # Optical sensors are angles-only (2-dim); they have no range trace.
            if len(o.measurement) > 2:
                bucket["range_km"].append(o.measurement[2] / 1e3)

observations.sort(key=lambda o: o.epoch)
passes.sort(key=lambda p: p[1].window_open)
print(f"\nSimulated {len(observations)} measurements over {len(passes)} passes")

print("\n" + "=" * 100)
print("Pass Table")
print("=" * 100)
print(f"{'Site':<28}{'Start':<22}{'End':<22}{'Duration (min)':>16}{'Obs':>8}")
print("-" * 100)
for sensor_name, w, n_obs in passes:
    start_str = str(w.window_open).split(".")[0]
    end_str = str(w.window_close).split(".")[0]
    duration_min = w.duration / 60.0
    print(
        f"{sensor_name:<28}{start_str:<22}{end_str:<22}{duration_min:>14.1f} m{n_obs:>8}"
    )
print("=" * 100)

fig_measurements = make_subplots(
    rows=3,
    cols=1,
    shared_xaxes=True,
    subplot_titles=("Azimuth (deg)", "Elevation (deg)", "Range (km)"),
    vertical_spacing=0.08,
)
for i, sensor in enumerate(sensors):
    bucket = sensor_meas[i]
    if not bucket["t"]:
        continue
    color = sensor_colors[sensor.name]
    fig_measurements.add_trace(
        go.Scatter(
            x=bucket["t"],
            y=bucket["az"],
            mode="markers",
            name=sensor.name,
            legendgroup=sensor.name,
            marker={"color": color, "size": 5},
        ),
        row=1,
        col=1,
    )
    fig_measurements.add_trace(
        go.Scatter(
            x=bucket["t"],
            y=bucket["el"],
            mode="markers",
            name=sensor.name,
            legendgroup=sensor.name,
            showlegend=False,
            marker={"color": color, "size": 5},
        ),
        row=2,
        col=1,
    )
    # Angles-only optical sensors contribute no range trace.
    if bucket["range_km"]:
        fig_measurements.add_trace(
            go.Scatter(
                x=bucket["t"][: len(bucket["range_km"])],
                y=bucket["range_km"],
                mode="markers",
                name=sensor.name,
                legendgroup=sensor.name,
                showlegend=False,
                marker={"color": color, "size": 5},
            ),
            row=3,
            col=1,
        )

fig_measurements.update_xaxes(title_text="Time (minutes)", row=3, col=1)
fig_measurements.update_yaxes(title_text="Azimuth (deg)", row=1, col=1)
fig_measurements.update_yaxes(title_text="Elevation (deg)", row=2, col=1)
fig_measurements.update_yaxes(title_text="Range (km)", row=3, col=1)
fig_measurements.update_layout(
    title="Simulated SSN Radar Measurements (6-hour Tracking Arc)",
    height=800,
    margin={"l": 60, "r": 40, "t": 80, "b": 60},
)
# --8<-- [end:simulate_measurements]

# --8<-- [start:run_filters]


def extract_rtn_error_series(filt, truth_trajectory, t0):
    """Extract per-axis RTN error/1-sigma and total position error from filter records.

    Rotates each record's ECI position error and position-covariance block
    into the radial/along-track/cross-track (RTN) frame of the truth state
    at that epoch, using the library's ECI-to-RTN rotation.
    """
    t_min = []
    err_r, err_t, err_n, err_total = [], [], [], []
    sig_r, sig_t, sig_n, sig_total = [], [], [], []
    for rec in filt.records():
        truth_state = truth_trajectory.interpolate(rec.epoch)
        error_eci = rec.state_updated[:3] - truth_state[:3]
        rot = bh.rotation_eci_to_rtn(truth_state)
        error_rtn = rot @ error_eci
        cov_rtn = rot @ rec.covariance_updated[:3, :3] @ rot.T
        sigma_rtn = np.sqrt(np.diag(cov_rtn))

        t_min.append((rec.epoch - t0) / 60.0)
        err_r.append(error_rtn[0])
        err_t.append(error_rtn[1])
        err_n.append(error_rtn[2])
        sig_r.append(sigma_rtn[0])
        sig_t.append(sigma_rtn[1])
        sig_n.append(sigma_rtn[2])
        err_total.append(np.linalg.norm(error_eci))
        sig_total.append(np.linalg.norm(sigma_rtn))
    return {
        "t": np.array(t_min),
        "err_r": np.array(err_r),
        "err_t": np.array(err_t),
        "err_n": np.array(err_n),
        "sig_r": np.array(sig_r),
        "sig_t": np.array(sig_t),
        "sig_n": np.array(sig_n),
        "err_total": np.array(err_total),
        "sig_total": np.array(sig_total),
    }


# Shared initial guess: perturbed by 1 km in x-position, 1 m/s in y-velocity
initial_state = np.array(true_state)
initial_state[0] += 1000.0
initial_state[4] += 1.0
p0 = np.diag([1e6, 1e6, 1e6, 1e2, 1e2, 1e2])
models = [s.measurement_model() for s in sensors]

ekf = bh.ExtendedKalmanFilter(
    epoch,
    initial_state,
    p0,
    measurement_models=models,
    propagation_config=bh.NumericalPropagationConfig.default(),
    force_config=bh.ForceModelConfig.two_body(),
)
ukf = bh.UnscentedKalmanFilter(
    epoch,
    initial_state,
    p0,
    propagation_config=bh.NumericalPropagationConfig.default(),
    force_config=bh.ForceModelConfig.two_body(),
    measurement_models=models,
)

# Merge the (possibly overlapping) per-sensor pass windows -- e.g. Cavalier
# and Millstone both track the object around the same time -- into
# non-overlapping tracking intervals, sorted by start time.
interval_bounds = sorted((w.window_open, w.window_close) for _, w, _ in passes)
intervals = []
for start, end in interval_bounds:
    if intervals and start <= intervals[-1][1]:
        intervals[-1][1] = max(intervals[-1][1], end)
    else:
        intervals.append([start, end])

# Step each filter window-by-window: propagate through the gap before an
# interval at a fixed cadence (prediction-only, so covariance growth during
# the gap is recorded), then process every observation within the interval
# in time order.
print()
for name, filt in (("EKF", ekf), ("UKF", ukf)):
    start_time = time.time()
    prev_epoch = epoch
    for start, end in intervals:
        t = prev_epoch + PROPAGATE_STEP
        while t < start:
            filt.propagate_to(t)
            t = t + PROPAGATE_STEP
        for obs in observations:
            if start <= obs.epoch <= end:
                filt.process_observation(obs)
        prev_epoch = end
    print(
        f"{name} processed {len(observations)} observations in {time.time() - start_time:.1f} s"
    )

ekf_rtn = extract_rtn_error_series(ekf, truth_traj, epoch)
ukf_rtn = extract_rtn_error_series(ukf, truth_traj, epoch)
# --8<-- [end:run_filters]

# --8<-- [start:analyze_results]
FILTER_STYLES = {
    "EKF": {"color": "steelblue", "fill": "rgba(70, 130, 180, 0.2)"},
    "UKF": {"color": "coral", "fill": "rgba(255, 127, 80, 0.2)"},
}

fig_filters = make_subplots(
    rows=4,
    cols=2,
    shared_xaxes=True,
    subplot_titles=(
        "EKF Radial",
        "UKF Radial",
        "EKF Along-track",
        "UKF Along-track",
        "EKF Cross-track",
        "UKF Cross-track",
        "EKF Total Position Error",
        "UKF Total Position Error",
    ),
    vertical_spacing=0.06,
)


def add_band_and_error(fig, row, col, t_min, sigma, err, style):
    """Add a shaded +/- 3-sigma band with the signed error line drawn over it."""
    fig.add_trace(
        go.Scatter(
            x=t_min,
            y=3 * sigma,
            mode="lines",
            line={"width": 0},
            showlegend=False,
            hoverinfo="skip",
        ),
        row=row,
        col=col,
    )
    fig.add_trace(
        go.Scatter(
            x=t_min,
            y=-3 * sigma,
            mode="lines",
            line={"width": 0},
            fill="tonexty",
            fillcolor=style["fill"],
            showlegend=False,
            hoverinfo="skip",
        ),
        row=row,
        col=col,
    )
    fig.add_trace(
        go.Scatter(
            x=t_min,
            y=err,
            mode="lines",
            line={"color": style["color"], "width": 1.5},
            showlegend=False,
        ),
        row=row,
        col=col,
    )


for col, (name, result) in enumerate((("EKF", ekf_rtn), ("UKF", ukf_rtn)), start=1):
    style = FILTER_STYLES[name]
    add_band_and_error(
        fig_filters, 1, col, result["t"], result["sig_r"], result["err_r"], style
    )
    add_band_and_error(
        fig_filters, 2, col, result["t"], result["sig_t"], result["err_t"], style
    )
    add_band_and_error(
        fig_filters, 3, col, result["t"], result["sig_n"], result["err_n"], style
    )
    fig_filters.add_trace(
        go.Scatter(
            x=result["t"],
            y=result["err_total"],
            mode="lines",
            line={"color": style["color"], "width": 2},
            showlegend=False,
        ),
        row=4,
        col=col,
    )

# Shade pass windows on every row/column
for _, w, _ in passes:
    t0_min = (w.window_open - epoch) / 60.0
    t1_min = (w.window_close - epoch) / 60.0
    for row in (1, 2, 3, 4):
        for col in (1, 2):
            fig_filters.add_vrect(
                x0=t0_min,
                x1=t1_min,
                fillcolor="gray",
                opacity=0.15,
                line_width=0,
                row=row,
                col=col,
            )

for row, label in (
    (1, "Radial (m)"),
    (2, "Along-track (m)"),
    (3, "Cross-track (m)"),
    (4, "Position error (m)"),
):
    fig_filters.update_yaxes(title_text=label, row=row, col=1)
fig_filters.update_xaxes(title_text="Time (minutes)", row=4, col=1)
fig_filters.update_xaxes(title_text="Time (minutes)", row=4, col=2)
fig_filters.update_layout(
    title="EKF / UKF Filter Consistency (RTN)",
    height=1100,
    margin={"l": 60, "r": 40, "t": 80, "b": 60},
)

print("\n" + "=" * 80)
print("Filter Summary")
print("=" * 80)
print(
    f"EKF final position error: {ekf_rtn['err_total'][-1]:.1f} m  "
    f"(3-sigma = {3 * ekf_rtn['sig_total'][-1]:.1f} m)"
)
print(
    f"UKF final position error: {ukf_rtn['err_total'][-1]:.1f} m  "
    f"(3-sigma = {3 * ukf_rtn['sig_total'][-1]:.1f} m)"
)
print("=" * 80)

assert ekf_rtn["err_total"][-1] < 500.0, "EKF should converge to a small position error"
assert ukf_rtn["err_total"][-1] < 500.0, "UKF should converge to a small position error"
print("\nExample validated successfully!")
# --8<-- [end:analyze_results]
# --8<-- [end:all]

# ============================================================================
# Plot Output Section (for documentation generation)
# ============================================================================

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "plots"))
from brahe_theme import save_themed_html

# Save the sensor network ground track as themed HTML
light_path, dark_path = save_themed_html(fig_network, OUTDIR / f"{SCRIPT_NAME}_network")
print(f"\n✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")

# Save the measurement time series as themed HTML
light_path, dark_path = save_themed_html(
    fig_measurements, OUTDIR / f"{SCRIPT_NAME}_measurements"
)
print(f"✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")

# Save the filter comparison figure as themed HTML
light_path, dark_path = save_themed_html(fig_filters, OUTDIR / f"{SCRIPT_NAME}_filters")
print(f"✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")
```

## Load the Sensor Network

We load the Vallado SSN sensor sites and build sensors from them. The dataset's 21 sites split into two sensor types, both supported by `SimpleSSNSensor`: radar/phased-array/mechanical (`azel_range`) trackers, which measure `[azimuth, elevation, range]`, and optical (`azel`) trackers, which are angles-only and measure `[azimuth, elevation]` via the [`AzElMeasurementModel`](../library_api/estimation/measurement_models.md). Each sensor's `measurement_model()` returns the model matching its type. `SimpleSSNSensor.from_locations()` builds a sensor for every site, defaulting sites that lack Table 4-4 calibration to zero noise and bias -- overridable with `with_noise()`/`with_bias()`. `from_locations_calibrated()` restricts to the fully-calibrated sites (16 of the 21: 13 radar plus the 3 calibrated optical trackers Socorro, Maui, and Diego Garcia); this example uses the calibrated set so simulated measurement noise always matches Table 4-4:

```python
#!/usr/bin/env python
# /// script
# dependencies = ["brahe", "plotly", "numpy"]
# ///

"""
SSN Radar Tracking: Extended and Unscented Kalman Filters

This example simulates Space Surveillance Network (SSN) radar tracking of a
LEO object and estimates its orbit sequentially with an Extended Kalman
Filter and an Unscented Kalman Filter. It loads the Vallado SSN sensor
dataset, builds az/el/range sensors, visualizes the sensor network's ground
coverage against a simulated LEO ground track, simulates radar measurements
during passes over a 6-hour tracking arc, processes them sequentially with
both filters while propagating through the gaps between passes, and
compares each filter's true position error against its formal 3-sigma
uncertainty.

A batch-estimation companion, ssn_tracking_bls.py, reproduces the same
scenario and solves for the orbit with Batch Least Squares instead; it is
excluded from the automated example tests because BLS re-propagates the
full arc at every iteration and takes on the order of three minutes to run.
"""

# --8<-- [start:all]
# --8<-- [start:preamble]
import os
import pathlib
import sys
import time

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import brahe as bh

bh.initialize_eop()

# Configuration
MEAS_INTERVAL = 15.0  # seconds between measurements during a pass
DURATION = 6 * 3600.0  # tracking duration (seconds)
SEED = 42
PROPAGATE_STEP = 60.0  # gap-propagation step (seconds)
# --8<-- [end:preamble]

# Configuration for output files
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# --8<-- [start:load_sensors]
# Load the Vallado SSN sensor sites and build sensors from the fully
# calibrated sites. The dataset mixes radar/phased-array (azel_range, measuring
# az/el/range) and optical (angles-only az/el) trackers; both are supported.
# from_locations_calibrated keeps only sites with full Table 4-4 calibration --
# it drops two radar sites (Haystack, HAX) that lack noise values, while
# from_locations would include them instead, defaulted to zero noise.
sites = bh.datasets.ssn_sensors.load()
sensors = bh.SimpleSSNSensor.from_locations_calibrated(sites, seed=SEED)
print(f"Loaded {len(sites)} SSN sites, {len(sensors)} calibrated sensors")

print("\n" + "=" * 100)
print("SSN Sensor Network")
print("=" * 100)
print(
    f"{'Name':<28}{'System':<12}{'El Min':>8}{'Range Max':>12}"
    f"{'Az Noise':>10}{'El Noise':>10}{'Range Noise':>13}"
)
print("-" * 100)
for s in sensors:
    props = s.location.properties
    system = props.get("system", "?")
    az_noise = props.get("az_noise_deg", float("nan"))
    el_noise = props.get("el_noise_deg", float("nan"))
    range_noise = props.get("range_noise_m", float("nan"))
    range_max_str = (
        f"{s.range_max / 1e3:>9.0f} km" if s.range_max is not None else "  unlimited"
    )
    print(
        f"{s.name:<28}{system:<12}{s.el_min:>7.1f}°{range_max_str:>12}"
        f"{az_noise:>9.4f}°{el_noise:>9.4f}°{range_noise:>11.1f} m"
    )
print("=" * 100)
# --8<-- [end:load_sensors]

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

# --8<-- [start:visualize_network]
# Assign each sensor a stable color, reused for its measurement traces in the
# figure below, so a comm cone's color on the map identifies the same sensor
# in the az/el/range plot.
PALETTE = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
    "#aec7e8",
    "#ffbb78",
    "#98df8a",
    "#ff9896",
    "#c5b0d5",
]
sensor_colors = {s.name: PALETTE[i % len(PALETTE)] for i, s in enumerate(sensors)}

fig_network = bh.plot_groundtrack(
    trajectories=[
        {"trajectory": truth_prop.trajectory, "color": "red", "line_width": 2}
    ],
    ground_stations=[
        {"stations": [s.location], "color": sensor_colors[s.name], "alpha": 0.25}
        for s in sensors
    ],
    gs_cone_altitude=700e3,
    gs_min_elevation=5.0,
    basemap="natural_earth",
    backend="plotly",
)

# plot_groundtrack's built-in legend can't label per-sensor groups (every
# station-marker trace is named "Ground Stations"), so add a small manual
# legend mapping each sensor's name to its color.
for s in sensors:
    fig_network.add_trace(
        go.Scattergeo(
            lat=[None],
            lon=[None],
            mode="markers",
            marker={"size": 8, "color": sensor_colors[s.name]},
            name=s.name,
            showlegend=True,
        )
    )
fig_network.update_layout(showlegend=True)
# --8<-- [end:visualize_network]

# --8<-- [start:simulate_measurements]
# Find passes and simulate measurements only inside them. Sensor measurement
# buckets for the figure below are filled as each pass is simulated, since
# per-sensor plotting order doesn't depend on the global time order that the
# sequential filters need; only `observations` has to be globally sorted.
observations = []
passes = []  # (sensor_name, window, n_obs)
sensor_meas = {
    i: {"t": [], "az": [], "el": [], "range_km": []} for i in range(len(sensors))
}
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
            passes.append((sensor.name, w, len(obs)))
        bucket = sensor_meas[i]
        for o in obs:
            bucket["t"].append((o.epoch - epoch) / 60.0)
            bucket["az"].append(o.measurement[0])
            bucket["el"].append(o.measurement[1])
            # Optical sensors are angles-only (2-dim); they have no range trace.
            if len(o.measurement) > 2:
                bucket["range_km"].append(o.measurement[2] / 1e3)

observations.sort(key=lambda o: o.epoch)
passes.sort(key=lambda p: p[1].window_open)
print(f"\nSimulated {len(observations)} measurements over {len(passes)} passes")

print("\n" + "=" * 100)
print("Pass Table")
print("=" * 100)
print(f"{'Site':<28}{'Start':<22}{'End':<22}{'Duration (min)':>16}{'Obs':>8}")
print("-" * 100)
for sensor_name, w, n_obs in passes:
    start_str = str(w.window_open).split(".")[0]
    end_str = str(w.window_close).split(".")[0]
    duration_min = w.duration / 60.0
    print(
        f"{sensor_name:<28}{start_str:<22}{end_str:<22}{duration_min:>14.1f} m{n_obs:>8}"
    )
print("=" * 100)

fig_measurements = make_subplots(
    rows=3,
    cols=1,
    shared_xaxes=True,
    subplot_titles=("Azimuth (deg)", "Elevation (deg)", "Range (km)"),
    vertical_spacing=0.08,
)
for i, sensor in enumerate(sensors):
    bucket = sensor_meas[i]
    if not bucket["t"]:
        continue
    color = sensor_colors[sensor.name]
    fig_measurements.add_trace(
        go.Scatter(
            x=bucket["t"],
            y=bucket["az"],
            mode="markers",
            name=sensor.name,
            legendgroup=sensor.name,
            marker={"color": color, "size": 5},
        ),
        row=1,
        col=1,
    )
    fig_measurements.add_trace(
        go.Scatter(
            x=bucket["t"],
            y=bucket["el"],
            mode="markers",
            name=sensor.name,
            legendgroup=sensor.name,
            showlegend=False,
            marker={"color": color, "size": 5},
        ),
        row=2,
        col=1,
    )
    # Angles-only optical sensors contribute no range trace.
    if bucket["range_km"]:
        fig_measurements.add_trace(
            go.Scatter(
                x=bucket["t"][: len(bucket["range_km"])],
                y=bucket["range_km"],
                mode="markers",
                name=sensor.name,
                legendgroup=sensor.name,
                showlegend=False,
                marker={"color": color, "size": 5},
            ),
            row=3,
            col=1,
        )

fig_measurements.update_xaxes(title_text="Time (minutes)", row=3, col=1)
fig_measurements.update_yaxes(title_text="Azimuth (deg)", row=1, col=1)
fig_measurements.update_yaxes(title_text="Elevation (deg)", row=2, col=1)
fig_measurements.update_yaxes(title_text="Range (km)", row=3, col=1)
fig_measurements.update_layout(
    title="Simulated SSN Radar Measurements (6-hour Tracking Arc)",
    height=800,
    margin={"l": 60, "r": 40, "t": 80, "b": 60},
)
# --8<-- [end:simulate_measurements]

# --8<-- [start:run_filters]


def extract_rtn_error_series(filt, truth_trajectory, t0):
    """Extract per-axis RTN error/1-sigma and total position error from filter records.

    Rotates each record's ECI position error and position-covariance block
    into the radial/along-track/cross-track (RTN) frame of the truth state
    at that epoch, using the library's ECI-to-RTN rotation.
    """
    t_min = []
    err_r, err_t, err_n, err_total = [], [], [], []
    sig_r, sig_t, sig_n, sig_total = [], [], [], []
    for rec in filt.records():
        truth_state = truth_trajectory.interpolate(rec.epoch)
        error_eci = rec.state_updated[:3] - truth_state[:3]
        rot = bh.rotation_eci_to_rtn(truth_state)
        error_rtn = rot @ error_eci
        cov_rtn = rot @ rec.covariance_updated[:3, :3] @ rot.T
        sigma_rtn = np.sqrt(np.diag(cov_rtn))

        t_min.append((rec.epoch - t0) / 60.0)
        err_r.append(error_rtn[0])
        err_t.append(error_rtn[1])
        err_n.append(error_rtn[2])
        sig_r.append(sigma_rtn[0])
        sig_t.append(sigma_rtn[1])
        sig_n.append(sigma_rtn[2])
        err_total.append(np.linalg.norm(error_eci))
        sig_total.append(np.linalg.norm(sigma_rtn))
    return {
        "t": np.array(t_min),
        "err_r": np.array(err_r),
        "err_t": np.array(err_t),
        "err_n": np.array(err_n),
        "sig_r": np.array(sig_r),
        "sig_t": np.array(sig_t),
        "sig_n": np.array(sig_n),
        "err_total": np.array(err_total),
        "sig_total": np.array(sig_total),
    }


# Shared initial guess: perturbed by 1 km in x-position, 1 m/s in y-velocity
initial_state = np.array(true_state)
initial_state[0] += 1000.0
initial_state[4] += 1.0
p0 = np.diag([1e6, 1e6, 1e6, 1e2, 1e2, 1e2])
models = [s.measurement_model() for s in sensors]

ekf = bh.ExtendedKalmanFilter(
    epoch,
    initial_state,
    p0,
    measurement_models=models,
    propagation_config=bh.NumericalPropagationConfig.default(),
    force_config=bh.ForceModelConfig.two_body(),
)
ukf = bh.UnscentedKalmanFilter(
    epoch,
    initial_state,
    p0,
    propagation_config=bh.NumericalPropagationConfig.default(),
    force_config=bh.ForceModelConfig.two_body(),
    measurement_models=models,
)

# Merge the (possibly overlapping) per-sensor pass windows -- e.g. Cavalier
# and Millstone both track the object around the same time -- into
# non-overlapping tracking intervals, sorted by start time.
interval_bounds = sorted((w.window_open, w.window_close) for _, w, _ in passes)
intervals = []
for start, end in interval_bounds:
    if intervals and start <= intervals[-1][1]:
        intervals[-1][1] = max(intervals[-1][1], end)
    else:
        intervals.append([start, end])

# Step each filter window-by-window: propagate through the gap before an
# interval at a fixed cadence (prediction-only, so covariance growth during
# the gap is recorded), then process every observation within the interval
# in time order.
print()
for name, filt in (("EKF", ekf), ("UKF", ukf)):
    start_time = time.time()
    prev_epoch = epoch
    for start, end in intervals:
        t = prev_epoch + PROPAGATE_STEP
        while t < start:
            filt.propagate_to(t)
            t = t + PROPAGATE_STEP
        for obs in observations:
            if start <= obs.epoch <= end:
                filt.process_observation(obs)
        prev_epoch = end
    print(
        f"{name} processed {len(observations)} observations in {time.time() - start_time:.1f} s"
    )

ekf_rtn = extract_rtn_error_series(ekf, truth_traj, epoch)
ukf_rtn = extract_rtn_error_series(ukf, truth_traj, epoch)
# --8<-- [end:run_filters]

# --8<-- [start:analyze_results]
FILTER_STYLES = {
    "EKF": {"color": "steelblue", "fill": "rgba(70, 130, 180, 0.2)"},
    "UKF": {"color": "coral", "fill": "rgba(255, 127, 80, 0.2)"},
}

fig_filters = make_subplots(
    rows=4,
    cols=2,
    shared_xaxes=True,
    subplot_titles=(
        "EKF Radial",
        "UKF Radial",
        "EKF Along-track",
        "UKF Along-track",
        "EKF Cross-track",
        "UKF Cross-track",
        "EKF Total Position Error",
        "UKF Total Position Error",
    ),
    vertical_spacing=0.06,
)


def add_band_and_error(fig, row, col, t_min, sigma, err, style):
    """Add a shaded +/- 3-sigma band with the signed error line drawn over it."""
    fig.add_trace(
        go.Scatter(
            x=t_min,
            y=3 * sigma,
            mode="lines",
            line={"width": 0},
            showlegend=False,
            hoverinfo="skip",
        ),
        row=row,
        col=col,
    )
    fig.add_trace(
        go.Scatter(
            x=t_min,
            y=-3 * sigma,
            mode="lines",
            line={"width": 0},
            fill="tonexty",
            fillcolor=style["fill"],
            showlegend=False,
            hoverinfo="skip",
        ),
        row=row,
        col=col,
    )
    fig.add_trace(
        go.Scatter(
            x=t_min,
            y=err,
            mode="lines",
            line={"color": style["color"], "width": 1.5},
            showlegend=False,
        ),
        row=row,
        col=col,
    )


for col, (name, result) in enumerate((("EKF", ekf_rtn), ("UKF", ukf_rtn)), start=1):
    style = FILTER_STYLES[name]
    add_band_and_error(
        fig_filters, 1, col, result["t"], result["sig_r"], result["err_r"], style
    )
    add_band_and_error(
        fig_filters, 2, col, result["t"], result["sig_t"], result["err_t"], style
    )
    add_band_and_error(
        fig_filters, 3, col, result["t"], result["sig_n"], result["err_n"], style
    )
    fig_filters.add_trace(
        go.Scatter(
            x=result["t"],
            y=result["err_total"],
            mode="lines",
            line={"color": style["color"], "width": 2},
            showlegend=False,
        ),
        row=4,
        col=col,
    )

# Shade pass windows on every row/column
for _, w, _ in passes:
    t0_min = (w.window_open - epoch) / 60.0
    t1_min = (w.window_close - epoch) / 60.0
    for row in (1, 2, 3, 4):
        for col in (1, 2):
            fig_filters.add_vrect(
                x0=t0_min,
                x1=t1_min,
                fillcolor="gray",
                opacity=0.15,
                line_width=0,
                row=row,
                col=col,
            )

for row, label in (
    (1, "Radial (m)"),
    (2, "Along-track (m)"),
    (3, "Cross-track (m)"),
    (4, "Position error (m)"),
):
    fig_filters.update_yaxes(title_text=label, row=row, col=1)
fig_filters.update_xaxes(title_text="Time (minutes)", row=4, col=1)
fig_filters.update_xaxes(title_text="Time (minutes)", row=4, col=2)
fig_filters.update_layout(
    title="EKF / UKF Filter Consistency (RTN)",
    height=1100,
    margin={"l": 60, "r": 40, "t": 80, "b": 60},
)

print("\n" + "=" * 80)
print("Filter Summary")
print("=" * 80)
print(
    f"EKF final position error: {ekf_rtn['err_total'][-1]:.1f} m  "
    f"(3-sigma = {3 * ekf_rtn['sig_total'][-1]:.1f} m)"
)
print(
    f"UKF final position error: {ukf_rtn['err_total'][-1]:.1f} m  "
    f"(3-sigma = {3 * ukf_rtn['sig_total'][-1]:.1f} m)"
)
print("=" * 80)

assert ekf_rtn["err_total"][-1] < 500.0, "EKF should converge to a small position error"
assert ukf_rtn["err_total"][-1] < 500.0, "UKF should converge to a small position error"
print("\nExample validated successfully!")
# --8<-- [end:analyze_results]
# --8<-- [end:all]

# ============================================================================
# Plot Output Section (for documentation generation)
# ============================================================================

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "plots"))
from brahe_theme import save_themed_html

# Save the sensor network ground track as themed HTML
light_path, dark_path = save_themed_html(fig_network, OUTDIR / f"{SCRIPT_NAME}_network")
print(f"\n✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")

# Save the measurement time series as themed HTML
light_path, dark_path = save_themed_html(
    fig_measurements, OUTDIR / f"{SCRIPT_NAME}_measurements"
)
print(f"✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")

# Save the filter comparison figure as themed HTML
light_path, dark_path = save_themed_html(fig_filters, OUTDIR / f"{SCRIPT_NAME}_filters")
print(f"✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")
```

## Visualize the Sensor Network

Next we propagate a truth trajectory -- a 700 km, 72&deg; inclination LEO orbit -- and plot its ground track against the sensor network's coverage cones, using each sensor's minimum elevation angle. Each sensor gets a stable color, reused for its measurement traces in the next figure, so a comm cone's color on the map identifies the same sensor in the az/el/range plot below:

```python
#!/usr/bin/env python
# /// script
# dependencies = ["brahe", "plotly", "numpy"]
# ///

"""
SSN Radar Tracking: Extended and Unscented Kalman Filters

This example simulates Space Surveillance Network (SSN) radar tracking of a
LEO object and estimates its orbit sequentially with an Extended Kalman
Filter and an Unscented Kalman Filter. It loads the Vallado SSN sensor
dataset, builds az/el/range sensors, visualizes the sensor network's ground
coverage against a simulated LEO ground track, simulates radar measurements
during passes over a 6-hour tracking arc, processes them sequentially with
both filters while propagating through the gaps between passes, and
compares each filter's true position error against its formal 3-sigma
uncertainty.

A batch-estimation companion, ssn_tracking_bls.py, reproduces the same
scenario and solves for the orbit with Batch Least Squares instead; it is
excluded from the automated example tests because BLS re-propagates the
full arc at every iteration and takes on the order of three minutes to run.
"""

# --8<-- [start:all]
# --8<-- [start:preamble]
import os
import pathlib
import sys
import time

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import brahe as bh

bh.initialize_eop()

# Configuration
MEAS_INTERVAL = 15.0  # seconds between measurements during a pass
DURATION = 6 * 3600.0  # tracking duration (seconds)
SEED = 42
PROPAGATE_STEP = 60.0  # gap-propagation step (seconds)
# --8<-- [end:preamble]

# Configuration for output files
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# --8<-- [start:load_sensors]
# Load the Vallado SSN sensor sites and build sensors from the fully
# calibrated sites. The dataset mixes radar/phased-array (azel_range, measuring
# az/el/range) and optical (angles-only az/el) trackers; both are supported.
# from_locations_calibrated keeps only sites with full Table 4-4 calibration --
# it drops two radar sites (Haystack, HAX) that lack noise values, while
# from_locations would include them instead, defaulted to zero noise.
sites = bh.datasets.ssn_sensors.load()
sensors = bh.SimpleSSNSensor.from_locations_calibrated(sites, seed=SEED)
print(f"Loaded {len(sites)} SSN sites, {len(sensors)} calibrated sensors")

print("\n" + "=" * 100)
print("SSN Sensor Network")
print("=" * 100)
print(
    f"{'Name':<28}{'System':<12}{'El Min':>8}{'Range Max':>12}"
    f"{'Az Noise':>10}{'El Noise':>10}{'Range Noise':>13}"
)
print("-" * 100)
for s in sensors:
    props = s.location.properties
    system = props.get("system", "?")
    az_noise = props.get("az_noise_deg", float("nan"))
    el_noise = props.get("el_noise_deg", float("nan"))
    range_noise = props.get("range_noise_m", float("nan"))
    range_max_str = (
        f"{s.range_max / 1e3:>9.0f} km" if s.range_max is not None else "  unlimited"
    )
    print(
        f"{s.name:<28}{system:<12}{s.el_min:>7.1f}°{range_max_str:>12}"
        f"{az_noise:>9.4f}°{el_noise:>9.4f}°{range_noise:>11.1f} m"
    )
print("=" * 100)
# --8<-- [end:load_sensors]

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

# --8<-- [start:visualize_network]
# Assign each sensor a stable color, reused for its measurement traces in the
# figure below, so a comm cone's color on the map identifies the same sensor
# in the az/el/range plot.
PALETTE = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
    "#aec7e8",
    "#ffbb78",
    "#98df8a",
    "#ff9896",
    "#c5b0d5",
]
sensor_colors = {s.name: PALETTE[i % len(PALETTE)] for i, s in enumerate(sensors)}

fig_network = bh.plot_groundtrack(
    trajectories=[
        {"trajectory": truth_prop.trajectory, "color": "red", "line_width": 2}
    ],
    ground_stations=[
        {"stations": [s.location], "color": sensor_colors[s.name], "alpha": 0.25}
        for s in sensors
    ],
    gs_cone_altitude=700e3,
    gs_min_elevation=5.0,
    basemap="natural_earth",
    backend="plotly",
)

# plot_groundtrack's built-in legend can't label per-sensor groups (every
# station-marker trace is named "Ground Stations"), so add a small manual
# legend mapping each sensor's name to its color.
for s in sensors:
    fig_network.add_trace(
        go.Scattergeo(
            lat=[None],
            lon=[None],
            mode="markers",
            marker={"size": 8, "color": sensor_colors[s.name]},
            name=s.name,
            showlegend=True,
        )
    )
fig_network.update_layout(showlegend=True)
# --8<-- [end:visualize_network]

# --8<-- [start:simulate_measurements]
# Find passes and simulate measurements only inside them. Sensor measurement
# buckets for the figure below are filled as each pass is simulated, since
# per-sensor plotting order doesn't depend on the global time order that the
# sequential filters need; only `observations` has to be globally sorted.
observations = []
passes = []  # (sensor_name, window, n_obs)
sensor_meas = {
    i: {"t": [], "az": [], "el": [], "range_km": []} for i in range(len(sensors))
}
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
            passes.append((sensor.name, w, len(obs)))
        bucket = sensor_meas[i]
        for o in obs:
            bucket["t"].append((o.epoch - epoch) / 60.0)
            bucket["az"].append(o.measurement[0])
            bucket["el"].append(o.measurement[1])
            # Optical sensors are angles-only (2-dim); they have no range trace.
            if len(o.measurement) > 2:
                bucket["range_km"].append(o.measurement[2] / 1e3)

observations.sort(key=lambda o: o.epoch)
passes.sort(key=lambda p: p[1].window_open)
print(f"\nSimulated {len(observations)} measurements over {len(passes)} passes")

print("\n" + "=" * 100)
print("Pass Table")
print("=" * 100)
print(f"{'Site':<28}{'Start':<22}{'End':<22}{'Duration (min)':>16}{'Obs':>8}")
print("-" * 100)
for sensor_name, w, n_obs in passes:
    start_str = str(w.window_open).split(".")[0]
    end_str = str(w.window_close).split(".")[0]
    duration_min = w.duration / 60.0
    print(
        f"{sensor_name:<28}{start_str:<22}{end_str:<22}{duration_min:>14.1f} m{n_obs:>8}"
    )
print("=" * 100)

fig_measurements = make_subplots(
    rows=3,
    cols=1,
    shared_xaxes=True,
    subplot_titles=("Azimuth (deg)", "Elevation (deg)", "Range (km)"),
    vertical_spacing=0.08,
)
for i, sensor in enumerate(sensors):
    bucket = sensor_meas[i]
    if not bucket["t"]:
        continue
    color = sensor_colors[sensor.name]
    fig_measurements.add_trace(
        go.Scatter(
            x=bucket["t"],
            y=bucket["az"],
            mode="markers",
            name=sensor.name,
            legendgroup=sensor.name,
            marker={"color": color, "size": 5},
        ),
        row=1,
        col=1,
    )
    fig_measurements.add_trace(
        go.Scatter(
            x=bucket["t"],
            y=bucket["el"],
            mode="markers",
            name=sensor.name,
            legendgroup=sensor.name,
            showlegend=False,
            marker={"color": color, "size": 5},
        ),
        row=2,
        col=1,
    )
    # Angles-only optical sensors contribute no range trace.
    if bucket["range_km"]:
        fig_measurements.add_trace(
            go.Scatter(
                x=bucket["t"][: len(bucket["range_km"])],
                y=bucket["range_km"],
                mode="markers",
                name=sensor.name,
                legendgroup=sensor.name,
                showlegend=False,
                marker={"color": color, "size": 5},
            ),
            row=3,
            col=1,
        )

fig_measurements.update_xaxes(title_text="Time (minutes)", row=3, col=1)
fig_measurements.update_yaxes(title_text="Azimuth (deg)", row=1, col=1)
fig_measurements.update_yaxes(title_text="Elevation (deg)", row=2, col=1)
fig_measurements.update_yaxes(title_text="Range (km)", row=3, col=1)
fig_measurements.update_layout(
    title="Simulated SSN Radar Measurements (6-hour Tracking Arc)",
    height=800,
    margin={"l": 60, "r": 40, "t": 80, "b": 60},
)
# --8<-- [end:simulate_measurements]

# --8<-- [start:run_filters]


def extract_rtn_error_series(filt, truth_trajectory, t0):
    """Extract per-axis RTN error/1-sigma and total position error from filter records.

    Rotates each record's ECI position error and position-covariance block
    into the radial/along-track/cross-track (RTN) frame of the truth state
    at that epoch, using the library's ECI-to-RTN rotation.
    """
    t_min = []
    err_r, err_t, err_n, err_total = [], [], [], []
    sig_r, sig_t, sig_n, sig_total = [], [], [], []
    for rec in filt.records():
        truth_state = truth_trajectory.interpolate(rec.epoch)
        error_eci = rec.state_updated[:3] - truth_state[:3]
        rot = bh.rotation_eci_to_rtn(truth_state)
        error_rtn = rot @ error_eci
        cov_rtn = rot @ rec.covariance_updated[:3, :3] @ rot.T
        sigma_rtn = np.sqrt(np.diag(cov_rtn))

        t_min.append((rec.epoch - t0) / 60.0)
        err_r.append(error_rtn[0])
        err_t.append(error_rtn[1])
        err_n.append(error_rtn[2])
        sig_r.append(sigma_rtn[0])
        sig_t.append(sigma_rtn[1])
        sig_n.append(sigma_rtn[2])
        err_total.append(np.linalg.norm(error_eci))
        sig_total.append(np.linalg.norm(sigma_rtn))
    return {
        "t": np.array(t_min),
        "err_r": np.array(err_r),
        "err_t": np.array(err_t),
        "err_n": np.array(err_n),
        "sig_r": np.array(sig_r),
        "sig_t": np.array(sig_t),
        "sig_n": np.array(sig_n),
        "err_total": np.array(err_total),
        "sig_total": np.array(sig_total),
    }


# Shared initial guess: perturbed by 1 km in x-position, 1 m/s in y-velocity
initial_state = np.array(true_state)
initial_state[0] += 1000.0
initial_state[4] += 1.0
p0 = np.diag([1e6, 1e6, 1e6, 1e2, 1e2, 1e2])
models = [s.measurement_model() for s in sensors]

ekf = bh.ExtendedKalmanFilter(
    epoch,
    initial_state,
    p0,
    measurement_models=models,
    propagation_config=bh.NumericalPropagationConfig.default(),
    force_config=bh.ForceModelConfig.two_body(),
)
ukf = bh.UnscentedKalmanFilter(
    epoch,
    initial_state,
    p0,
    propagation_config=bh.NumericalPropagationConfig.default(),
    force_config=bh.ForceModelConfig.two_body(),
    measurement_models=models,
)

# Merge the (possibly overlapping) per-sensor pass windows -- e.g. Cavalier
# and Millstone both track the object around the same time -- into
# non-overlapping tracking intervals, sorted by start time.
interval_bounds = sorted((w.window_open, w.window_close) for _, w, _ in passes)
intervals = []
for start, end in interval_bounds:
    if intervals and start <= intervals[-1][1]:
        intervals[-1][1] = max(intervals[-1][1], end)
    else:
        intervals.append([start, end])

# Step each filter window-by-window: propagate through the gap before an
# interval at a fixed cadence (prediction-only, so covariance growth during
# the gap is recorded), then process every observation within the interval
# in time order.
print()
for name, filt in (("EKF", ekf), ("UKF", ukf)):
    start_time = time.time()
    prev_epoch = epoch
    for start, end in intervals:
        t = prev_epoch + PROPAGATE_STEP
        while t < start:
            filt.propagate_to(t)
            t = t + PROPAGATE_STEP
        for obs in observations:
            if start <= obs.epoch <= end:
                filt.process_observation(obs)
        prev_epoch = end
    print(
        f"{name} processed {len(observations)} observations in {time.time() - start_time:.1f} s"
    )

ekf_rtn = extract_rtn_error_series(ekf, truth_traj, epoch)
ukf_rtn = extract_rtn_error_series(ukf, truth_traj, epoch)
# --8<-- [end:run_filters]

# --8<-- [start:analyze_results]
FILTER_STYLES = {
    "EKF": {"color": "steelblue", "fill": "rgba(70, 130, 180, 0.2)"},
    "UKF": {"color": "coral", "fill": "rgba(255, 127, 80, 0.2)"},
}

fig_filters = make_subplots(
    rows=4,
    cols=2,
    shared_xaxes=True,
    subplot_titles=(
        "EKF Radial",
        "UKF Radial",
        "EKF Along-track",
        "UKF Along-track",
        "EKF Cross-track",
        "UKF Cross-track",
        "EKF Total Position Error",
        "UKF Total Position Error",
    ),
    vertical_spacing=0.06,
)


def add_band_and_error(fig, row, col, t_min, sigma, err, style):
    """Add a shaded +/- 3-sigma band with the signed error line drawn over it."""
    fig.add_trace(
        go.Scatter(
            x=t_min,
            y=3 * sigma,
            mode="lines",
            line={"width": 0},
            showlegend=False,
            hoverinfo="skip",
        ),
        row=row,
        col=col,
    )
    fig.add_trace(
        go.Scatter(
            x=t_min,
            y=-3 * sigma,
            mode="lines",
            line={"width": 0},
            fill="tonexty",
            fillcolor=style["fill"],
            showlegend=False,
            hoverinfo="skip",
        ),
        row=row,
        col=col,
    )
    fig.add_trace(
        go.Scatter(
            x=t_min,
            y=err,
            mode="lines",
            line={"color": style["color"], "width": 1.5},
            showlegend=False,
        ),
        row=row,
        col=col,
    )


for col, (name, result) in enumerate((("EKF", ekf_rtn), ("UKF", ukf_rtn)), start=1):
    style = FILTER_STYLES[name]
    add_band_and_error(
        fig_filters, 1, col, result["t"], result["sig_r"], result["err_r"], style
    )
    add_band_and_error(
        fig_filters, 2, col, result["t"], result["sig_t"], result["err_t"], style
    )
    add_band_and_error(
        fig_filters, 3, col, result["t"], result["sig_n"], result["err_n"], style
    )
    fig_filters.add_trace(
        go.Scatter(
            x=result["t"],
            y=result["err_total"],
            mode="lines",
            line={"color": style["color"], "width": 2},
            showlegend=False,
        ),
        row=4,
        col=col,
    )

# Shade pass windows on every row/column
for _, w, _ in passes:
    t0_min = (w.window_open - epoch) / 60.0
    t1_min = (w.window_close - epoch) / 60.0
    for row in (1, 2, 3, 4):
        for col in (1, 2):
            fig_filters.add_vrect(
                x0=t0_min,
                x1=t1_min,
                fillcolor="gray",
                opacity=0.15,
                line_width=0,
                row=row,
                col=col,
            )

for row, label in (
    (1, "Radial (m)"),
    (2, "Along-track (m)"),
    (3, "Cross-track (m)"),
    (4, "Position error (m)"),
):
    fig_filters.update_yaxes(title_text=label, row=row, col=1)
fig_filters.update_xaxes(title_text="Time (minutes)", row=4, col=1)
fig_filters.update_xaxes(title_text="Time (minutes)", row=4, col=2)
fig_filters.update_layout(
    title="EKF / UKF Filter Consistency (RTN)",
    height=1100,
    margin={"l": 60, "r": 40, "t": 80, "b": 60},
)

print("\n" + "=" * 80)
print("Filter Summary")
print("=" * 80)
print(
    f"EKF final position error: {ekf_rtn['err_total'][-1]:.1f} m  "
    f"(3-sigma = {3 * ekf_rtn['sig_total'][-1]:.1f} m)"
)
print(
    f"UKF final position error: {ukf_rtn['err_total'][-1]:.1f} m  "
    f"(3-sigma = {3 * ukf_rtn['sig_total'][-1]:.1f} m)"
)
print("=" * 80)

assert ekf_rtn["err_total"][-1] < 500.0, "EKF should converge to a small position error"
assert ukf_rtn["err_total"][-1] < 500.0, "UKF should converge to a small position error"
print("\nExample validated successfully!")
# --8<-- [end:analyze_results]
# --8<-- [end:all]

# ============================================================================
# Plot Output Section (for documentation generation)
# ============================================================================

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "plots"))
from brahe_theme import save_themed_html

# Save the sensor network ground track as themed HTML
light_path, dark_path = save_themed_html(fig_network, OUTDIR / f"{SCRIPT_NAME}_network")
print(f"\n✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")

# Save the measurement time series as themed HTML
light_path, dark_path = save_themed_html(
    fig_measurements, OUTDIR / f"{SCRIPT_NAME}_measurements"
)
print(f"✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")

# Save the filter comparison figure as themed HTML
light_path, dark_path = save_themed_html(fig_filters, OUTDIR / f"{SCRIPT_NAME}_filters")
print(f"✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")
```

**Interpolation**
Normally sampling measurements at a finer time step (15 s) than the propagation step (~60 s) would introduce interpolation error; brahe's orbit propagators use Hermite-cubic interpolation by default, which avoids these artifacts. See [InterpolationMethod](../library_api/orbits/enums.md#interpolationmethod) for the available interpolation algorithms.


## Simulate Measurements

Access windows bound the simulation: for each sensor we compute the elevation-constrained access windows against the truth trajectory, then call `simulate_observations()` only within those windows. This keeps the observation set to what the sensor geometry actually supports, rather than sampling continuously and discarding invisible epochs:

```python
#!/usr/bin/env python
# /// script
# dependencies = ["brahe", "plotly", "numpy"]
# ///

"""
SSN Radar Tracking: Extended and Unscented Kalman Filters

This example simulates Space Surveillance Network (SSN) radar tracking of a
LEO object and estimates its orbit sequentially with an Extended Kalman
Filter and an Unscented Kalman Filter. It loads the Vallado SSN sensor
dataset, builds az/el/range sensors, visualizes the sensor network's ground
coverage against a simulated LEO ground track, simulates radar measurements
during passes over a 6-hour tracking arc, processes them sequentially with
both filters while propagating through the gaps between passes, and
compares each filter's true position error against its formal 3-sigma
uncertainty.

A batch-estimation companion, ssn_tracking_bls.py, reproduces the same
scenario and solves for the orbit with Batch Least Squares instead; it is
excluded from the automated example tests because BLS re-propagates the
full arc at every iteration and takes on the order of three minutes to run.
"""

# --8<-- [start:all]
# --8<-- [start:preamble]
import os
import pathlib
import sys
import time

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import brahe as bh

bh.initialize_eop()

# Configuration
MEAS_INTERVAL = 15.0  # seconds between measurements during a pass
DURATION = 6 * 3600.0  # tracking duration (seconds)
SEED = 42
PROPAGATE_STEP = 60.0  # gap-propagation step (seconds)
# --8<-- [end:preamble]

# Configuration for output files
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# --8<-- [start:load_sensors]
# Load the Vallado SSN sensor sites and build sensors from the fully
# calibrated sites. The dataset mixes radar/phased-array (azel_range, measuring
# az/el/range) and optical (angles-only az/el) trackers; both are supported.
# from_locations_calibrated keeps only sites with full Table 4-4 calibration --
# it drops two radar sites (Haystack, HAX) that lack noise values, while
# from_locations would include them instead, defaulted to zero noise.
sites = bh.datasets.ssn_sensors.load()
sensors = bh.SimpleSSNSensor.from_locations_calibrated(sites, seed=SEED)
print(f"Loaded {len(sites)} SSN sites, {len(sensors)} calibrated sensors")

print("\n" + "=" * 100)
print("SSN Sensor Network")
print("=" * 100)
print(
    f"{'Name':<28}{'System':<12}{'El Min':>8}{'Range Max':>12}"
    f"{'Az Noise':>10}{'El Noise':>10}{'Range Noise':>13}"
)
print("-" * 100)
for s in sensors:
    props = s.location.properties
    system = props.get("system", "?")
    az_noise = props.get("az_noise_deg", float("nan"))
    el_noise = props.get("el_noise_deg", float("nan"))
    range_noise = props.get("range_noise_m", float("nan"))
    range_max_str = (
        f"{s.range_max / 1e3:>9.0f} km" if s.range_max is not None else "  unlimited"
    )
    print(
        f"{s.name:<28}{system:<12}{s.el_min:>7.1f}°{range_max_str:>12}"
        f"{az_noise:>9.4f}°{el_noise:>9.4f}°{range_noise:>11.1f} m"
    )
print("=" * 100)
# --8<-- [end:load_sensors]

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

# --8<-- [start:visualize_network]
# Assign each sensor a stable color, reused for its measurement traces in the
# figure below, so a comm cone's color on the map identifies the same sensor
# in the az/el/range plot.
PALETTE = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
    "#aec7e8",
    "#ffbb78",
    "#98df8a",
    "#ff9896",
    "#c5b0d5",
]
sensor_colors = {s.name: PALETTE[i % len(PALETTE)] for i, s in enumerate(sensors)}

fig_network = bh.plot_groundtrack(
    trajectories=[
        {"trajectory": truth_prop.trajectory, "color": "red", "line_width": 2}
    ],
    ground_stations=[
        {"stations": [s.location], "color": sensor_colors[s.name], "alpha": 0.25}
        for s in sensors
    ],
    gs_cone_altitude=700e3,
    gs_min_elevation=5.0,
    basemap="natural_earth",
    backend="plotly",
)

# plot_groundtrack's built-in legend can't label per-sensor groups (every
# station-marker trace is named "Ground Stations"), so add a small manual
# legend mapping each sensor's name to its color.
for s in sensors:
    fig_network.add_trace(
        go.Scattergeo(
            lat=[None],
            lon=[None],
            mode="markers",
            marker={"size": 8, "color": sensor_colors[s.name]},
            name=s.name,
            showlegend=True,
        )
    )
fig_network.update_layout(showlegend=True)
# --8<-- [end:visualize_network]

# --8<-- [start:simulate_measurements]
# Find passes and simulate measurements only inside them. Sensor measurement
# buckets for the figure below are filled as each pass is simulated, since
# per-sensor plotting order doesn't depend on the global time order that the
# sequential filters need; only `observations` has to be globally sorted.
observations = []
passes = []  # (sensor_name, window, n_obs)
sensor_meas = {
    i: {"t": [], "az": [], "el": [], "range_km": []} for i in range(len(sensors))
}
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
            passes.append((sensor.name, w, len(obs)))
        bucket = sensor_meas[i]
        for o in obs:
            bucket["t"].append((o.epoch - epoch) / 60.0)
            bucket["az"].append(o.measurement[0])
            bucket["el"].append(o.measurement[1])
            # Optical sensors are angles-only (2-dim); they have no range trace.
            if len(o.measurement) > 2:
                bucket["range_km"].append(o.measurement[2] / 1e3)

observations.sort(key=lambda o: o.epoch)
passes.sort(key=lambda p: p[1].window_open)
print(f"\nSimulated {len(observations)} measurements over {len(passes)} passes")

print("\n" + "=" * 100)
print("Pass Table")
print("=" * 100)
print(f"{'Site':<28}{'Start':<22}{'End':<22}{'Duration (min)':>16}{'Obs':>8}")
print("-" * 100)
for sensor_name, w, n_obs in passes:
    start_str = str(w.window_open).split(".")[0]
    end_str = str(w.window_close).split(".")[0]
    duration_min = w.duration / 60.0
    print(
        f"{sensor_name:<28}{start_str:<22}{end_str:<22}{duration_min:>14.1f} m{n_obs:>8}"
    )
print("=" * 100)

fig_measurements = make_subplots(
    rows=3,
    cols=1,
    shared_xaxes=True,
    subplot_titles=("Azimuth (deg)", "Elevation (deg)", "Range (km)"),
    vertical_spacing=0.08,
)
for i, sensor in enumerate(sensors):
    bucket = sensor_meas[i]
    if not bucket["t"]:
        continue
    color = sensor_colors[sensor.name]
    fig_measurements.add_trace(
        go.Scatter(
            x=bucket["t"],
            y=bucket["az"],
            mode="markers",
            name=sensor.name,
            legendgroup=sensor.name,
            marker={"color": color, "size": 5},
        ),
        row=1,
        col=1,
    )
    fig_measurements.add_trace(
        go.Scatter(
            x=bucket["t"],
            y=bucket["el"],
            mode="markers",
            name=sensor.name,
            legendgroup=sensor.name,
            showlegend=False,
            marker={"color": color, "size": 5},
        ),
        row=2,
        col=1,
    )
    # Angles-only optical sensors contribute no range trace.
    if bucket["range_km"]:
        fig_measurements.add_trace(
            go.Scatter(
                x=bucket["t"][: len(bucket["range_km"])],
                y=bucket["range_km"],
                mode="markers",
                name=sensor.name,
                legendgroup=sensor.name,
                showlegend=False,
                marker={"color": color, "size": 5},
            ),
            row=3,
            col=1,
        )

fig_measurements.update_xaxes(title_text="Time (minutes)", row=3, col=1)
fig_measurements.update_yaxes(title_text="Azimuth (deg)", row=1, col=1)
fig_measurements.update_yaxes(title_text="Elevation (deg)", row=2, col=1)
fig_measurements.update_yaxes(title_text="Range (km)", row=3, col=1)
fig_measurements.update_layout(
    title="Simulated SSN Radar Measurements (6-hour Tracking Arc)",
    height=800,
    margin={"l": 60, "r": 40, "t": 80, "b": 60},
)
# --8<-- [end:simulate_measurements]

# --8<-- [start:run_filters]


def extract_rtn_error_series(filt, truth_trajectory, t0):
    """Extract per-axis RTN error/1-sigma and total position error from filter records.

    Rotates each record's ECI position error and position-covariance block
    into the radial/along-track/cross-track (RTN) frame of the truth state
    at that epoch, using the library's ECI-to-RTN rotation.
    """
    t_min = []
    err_r, err_t, err_n, err_total = [], [], [], []
    sig_r, sig_t, sig_n, sig_total = [], [], [], []
    for rec in filt.records():
        truth_state = truth_trajectory.interpolate(rec.epoch)
        error_eci = rec.state_updated[:3] - truth_state[:3]
        rot = bh.rotation_eci_to_rtn(truth_state)
        error_rtn = rot @ error_eci
        cov_rtn = rot @ rec.covariance_updated[:3, :3] @ rot.T
        sigma_rtn = np.sqrt(np.diag(cov_rtn))

        t_min.append((rec.epoch - t0) / 60.0)
        err_r.append(error_rtn[0])
        err_t.append(error_rtn[1])
        err_n.append(error_rtn[2])
        sig_r.append(sigma_rtn[0])
        sig_t.append(sigma_rtn[1])
        sig_n.append(sigma_rtn[2])
        err_total.append(np.linalg.norm(error_eci))
        sig_total.append(np.linalg.norm(sigma_rtn))
    return {
        "t": np.array(t_min),
        "err_r": np.array(err_r),
        "err_t": np.array(err_t),
        "err_n": np.array(err_n),
        "sig_r": np.array(sig_r),
        "sig_t": np.array(sig_t),
        "sig_n": np.array(sig_n),
        "err_total": np.array(err_total),
        "sig_total": np.array(sig_total),
    }


# Shared initial guess: perturbed by 1 km in x-position, 1 m/s in y-velocity
initial_state = np.array(true_state)
initial_state[0] += 1000.0
initial_state[4] += 1.0
p0 = np.diag([1e6, 1e6, 1e6, 1e2, 1e2, 1e2])
models = [s.measurement_model() for s in sensors]

ekf = bh.ExtendedKalmanFilter(
    epoch,
    initial_state,
    p0,
    measurement_models=models,
    propagation_config=bh.NumericalPropagationConfig.default(),
    force_config=bh.ForceModelConfig.two_body(),
)
ukf = bh.UnscentedKalmanFilter(
    epoch,
    initial_state,
    p0,
    propagation_config=bh.NumericalPropagationConfig.default(),
    force_config=bh.ForceModelConfig.two_body(),
    measurement_models=models,
)

# Merge the (possibly overlapping) per-sensor pass windows -- e.g. Cavalier
# and Millstone both track the object around the same time -- into
# non-overlapping tracking intervals, sorted by start time.
interval_bounds = sorted((w.window_open, w.window_close) for _, w, _ in passes)
intervals = []
for start, end in interval_bounds:
    if intervals and start <= intervals[-1][1]:
        intervals[-1][1] = max(intervals[-1][1], end)
    else:
        intervals.append([start, end])

# Step each filter window-by-window: propagate through the gap before an
# interval at a fixed cadence (prediction-only, so covariance growth during
# the gap is recorded), then process every observation within the interval
# in time order.
print()
for name, filt in (("EKF", ekf), ("UKF", ukf)):
    start_time = time.time()
    prev_epoch = epoch
    for start, end in intervals:
        t = prev_epoch + PROPAGATE_STEP
        while t < start:
            filt.propagate_to(t)
            t = t + PROPAGATE_STEP
        for obs in observations:
            if start <= obs.epoch <= end:
                filt.process_observation(obs)
        prev_epoch = end
    print(
        f"{name} processed {len(observations)} observations in {time.time() - start_time:.1f} s"
    )

ekf_rtn = extract_rtn_error_series(ekf, truth_traj, epoch)
ukf_rtn = extract_rtn_error_series(ukf, truth_traj, epoch)
# --8<-- [end:run_filters]

# --8<-- [start:analyze_results]
FILTER_STYLES = {
    "EKF": {"color": "steelblue", "fill": "rgba(70, 130, 180, 0.2)"},
    "UKF": {"color": "coral", "fill": "rgba(255, 127, 80, 0.2)"},
}

fig_filters = make_subplots(
    rows=4,
    cols=2,
    shared_xaxes=True,
    subplot_titles=(
        "EKF Radial",
        "UKF Radial",
        "EKF Along-track",
        "UKF Along-track",
        "EKF Cross-track",
        "UKF Cross-track",
        "EKF Total Position Error",
        "UKF Total Position Error",
    ),
    vertical_spacing=0.06,
)


def add_band_and_error(fig, row, col, t_min, sigma, err, style):
    """Add a shaded +/- 3-sigma band with the signed error line drawn over it."""
    fig.add_trace(
        go.Scatter(
            x=t_min,
            y=3 * sigma,
            mode="lines",
            line={"width": 0},
            showlegend=False,
            hoverinfo="skip",
        ),
        row=row,
        col=col,
    )
    fig.add_trace(
        go.Scatter(
            x=t_min,
            y=-3 * sigma,
            mode="lines",
            line={"width": 0},
            fill="tonexty",
            fillcolor=style["fill"],
            showlegend=False,
            hoverinfo="skip",
        ),
        row=row,
        col=col,
    )
    fig.add_trace(
        go.Scatter(
            x=t_min,
            y=err,
            mode="lines",
            line={"color": style["color"], "width": 1.5},
            showlegend=False,
        ),
        row=row,
        col=col,
    )


for col, (name, result) in enumerate((("EKF", ekf_rtn), ("UKF", ukf_rtn)), start=1):
    style = FILTER_STYLES[name]
    add_band_and_error(
        fig_filters, 1, col, result["t"], result["sig_r"], result["err_r"], style
    )
    add_band_and_error(
        fig_filters, 2, col, result["t"], result["sig_t"], result["err_t"], style
    )
    add_band_and_error(
        fig_filters, 3, col, result["t"], result["sig_n"], result["err_n"], style
    )
    fig_filters.add_trace(
        go.Scatter(
            x=result["t"],
            y=result["err_total"],
            mode="lines",
            line={"color": style["color"], "width": 2},
            showlegend=False,
        ),
        row=4,
        col=col,
    )

# Shade pass windows on every row/column
for _, w, _ in passes:
    t0_min = (w.window_open - epoch) / 60.0
    t1_min = (w.window_close - epoch) / 60.0
    for row in (1, 2, 3, 4):
        for col in (1, 2):
            fig_filters.add_vrect(
                x0=t0_min,
                x1=t1_min,
                fillcolor="gray",
                opacity=0.15,
                line_width=0,
                row=row,
                col=col,
            )

for row, label in (
    (1, "Radial (m)"),
    (2, "Along-track (m)"),
    (3, "Cross-track (m)"),
    (4, "Position error (m)"),
):
    fig_filters.update_yaxes(title_text=label, row=row, col=1)
fig_filters.update_xaxes(title_text="Time (minutes)", row=4, col=1)
fig_filters.update_xaxes(title_text="Time (minutes)", row=4, col=2)
fig_filters.update_layout(
    title="EKF / UKF Filter Consistency (RTN)",
    height=1100,
    margin={"l": 60, "r": 40, "t": 80, "b": 60},
)

print("\n" + "=" * 80)
print("Filter Summary")
print("=" * 80)
print(
    f"EKF final position error: {ekf_rtn['err_total'][-1]:.1f} m  "
    f"(3-sigma = {3 * ekf_rtn['sig_total'][-1]:.1f} m)"
)
print(
    f"UKF final position error: {ukf_rtn['err_total'][-1]:.1f} m  "
    f"(3-sigma = {3 * ukf_rtn['sig_total'][-1]:.1f} m)"
)
print("=" * 80)

assert ekf_rtn["err_total"][-1] < 500.0, "EKF should converge to a small position error"
assert ukf_rtn["err_total"][-1] < 500.0, "UKF should converge to a small position error"
print("\nExample validated successfully!")
# --8<-- [end:analyze_results]
# --8<-- [end:all]

# ============================================================================
# Plot Output Section (for documentation generation)
# ============================================================================

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "plots"))
from brahe_theme import save_themed_html

# Save the sensor network ground track as themed HTML
light_path, dark_path = save_themed_html(fig_network, OUTDIR / f"{SCRIPT_NAME}_network")
print(f"\n✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")

# Save the measurement time series as themed HTML
light_path, dark_path = save_themed_html(
    fig_measurements, OUTDIR / f"{SCRIPT_NAME}_measurements"
)
print(f"✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")

# Save the filter comparison figure as themed HTML
light_path, dark_path = save_themed_html(fig_filters, OUTDIR / f"{SCRIPT_NAME}_filters")
print(f"✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")
```

Over the 6-hour arc, the network produces hundreds of observations across dozens of passes. Radar measurements are `[azimuth, elevation, range]`; optical measurements are angles-only `[azimuth, elevation]` and so contribute no points to the range subplot. Each is generated with its sensor's own bias and noise from Vallado Table 4-4, and colored to match its sensor in the network figure above:


## Run the Estimators

Each sensor exposes a `measurement_model()` that carries the same bias and noise used to generate its measurements. Because the model applies bias inside `predict()`, a filter built from these models is consistent with the simulated observations -- this is the calibrated-sensor assumption: the filter is told about the same bias the sensor introduces, rather than having to estimate it away.

Passes from different sensors can overlap -- Cavalier and Millstone, for instance, both track the object around the same time -- so the per-sensor pass windows are first merged into non-overlapping tracking intervals. The EKF and UKF then each walk the intervals in order: the filter is stepped forward through the gap before an interval with `propagate_to()` at a fixed 60 s cadence (prediction-only, no measurement update, recording a `FilterRecord` named `"Propagation"` at each step so covariance growth during the gap is visible in the diagnostic output), and every observation within the interval is then processed in time order:

```python
#!/usr/bin/env python
# /// script
# dependencies = ["brahe", "plotly", "numpy"]
# ///

"""
SSN Radar Tracking: Extended and Unscented Kalman Filters

This example simulates Space Surveillance Network (SSN) radar tracking of a
LEO object and estimates its orbit sequentially with an Extended Kalman
Filter and an Unscented Kalman Filter. It loads the Vallado SSN sensor
dataset, builds az/el/range sensors, visualizes the sensor network's ground
coverage against a simulated LEO ground track, simulates radar measurements
during passes over a 6-hour tracking arc, processes them sequentially with
both filters while propagating through the gaps between passes, and
compares each filter's true position error against its formal 3-sigma
uncertainty.

A batch-estimation companion, ssn_tracking_bls.py, reproduces the same
scenario and solves for the orbit with Batch Least Squares instead; it is
excluded from the automated example tests because BLS re-propagates the
full arc at every iteration and takes on the order of three minutes to run.
"""

# --8<-- [start:all]
# --8<-- [start:preamble]
import os
import pathlib
import sys
import time

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import brahe as bh

bh.initialize_eop()

# Configuration
MEAS_INTERVAL = 15.0  # seconds between measurements during a pass
DURATION = 6 * 3600.0  # tracking duration (seconds)
SEED = 42
PROPAGATE_STEP = 60.0  # gap-propagation step (seconds)
# --8<-- [end:preamble]

# Configuration for output files
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# --8<-- [start:load_sensors]
# Load the Vallado SSN sensor sites and build sensors from the fully
# calibrated sites. The dataset mixes radar/phased-array (azel_range, measuring
# az/el/range) and optical (angles-only az/el) trackers; both are supported.
# from_locations_calibrated keeps only sites with full Table 4-4 calibration --
# it drops two radar sites (Haystack, HAX) that lack noise values, while
# from_locations would include them instead, defaulted to zero noise.
sites = bh.datasets.ssn_sensors.load()
sensors = bh.SimpleSSNSensor.from_locations_calibrated(sites, seed=SEED)
print(f"Loaded {len(sites)} SSN sites, {len(sensors)} calibrated sensors")

print("\n" + "=" * 100)
print("SSN Sensor Network")
print("=" * 100)
print(
    f"{'Name':<28}{'System':<12}{'El Min':>8}{'Range Max':>12}"
    f"{'Az Noise':>10}{'El Noise':>10}{'Range Noise':>13}"
)
print("-" * 100)
for s in sensors:
    props = s.location.properties
    system = props.get("system", "?")
    az_noise = props.get("az_noise_deg", float("nan"))
    el_noise = props.get("el_noise_deg", float("nan"))
    range_noise = props.get("range_noise_m", float("nan"))
    range_max_str = (
        f"{s.range_max / 1e3:>9.0f} km" if s.range_max is not None else "  unlimited"
    )
    print(
        f"{s.name:<28}{system:<12}{s.el_min:>7.1f}°{range_max_str:>12}"
        f"{az_noise:>9.4f}°{el_noise:>9.4f}°{range_noise:>11.1f} m"
    )
print("=" * 100)
# --8<-- [end:load_sensors]

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

# --8<-- [start:visualize_network]
# Assign each sensor a stable color, reused for its measurement traces in the
# figure below, so a comm cone's color on the map identifies the same sensor
# in the az/el/range plot.
PALETTE = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
    "#aec7e8",
    "#ffbb78",
    "#98df8a",
    "#ff9896",
    "#c5b0d5",
]
sensor_colors = {s.name: PALETTE[i % len(PALETTE)] for i, s in enumerate(sensors)}

fig_network = bh.plot_groundtrack(
    trajectories=[
        {"trajectory": truth_prop.trajectory, "color": "red", "line_width": 2}
    ],
    ground_stations=[
        {"stations": [s.location], "color": sensor_colors[s.name], "alpha": 0.25}
        for s in sensors
    ],
    gs_cone_altitude=700e3,
    gs_min_elevation=5.0,
    basemap="natural_earth",
    backend="plotly",
)

# plot_groundtrack's built-in legend can't label per-sensor groups (every
# station-marker trace is named "Ground Stations"), so add a small manual
# legend mapping each sensor's name to its color.
for s in sensors:
    fig_network.add_trace(
        go.Scattergeo(
            lat=[None],
            lon=[None],
            mode="markers",
            marker={"size": 8, "color": sensor_colors[s.name]},
            name=s.name,
            showlegend=True,
        )
    )
fig_network.update_layout(showlegend=True)
# --8<-- [end:visualize_network]

# --8<-- [start:simulate_measurements]
# Find passes and simulate measurements only inside them. Sensor measurement
# buckets for the figure below are filled as each pass is simulated, since
# per-sensor plotting order doesn't depend on the global time order that the
# sequential filters need; only `observations` has to be globally sorted.
observations = []
passes = []  # (sensor_name, window, n_obs)
sensor_meas = {
    i: {"t": [], "az": [], "el": [], "range_km": []} for i in range(len(sensors))
}
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
            passes.append((sensor.name, w, len(obs)))
        bucket = sensor_meas[i]
        for o in obs:
            bucket["t"].append((o.epoch - epoch) / 60.0)
            bucket["az"].append(o.measurement[0])
            bucket["el"].append(o.measurement[1])
            # Optical sensors are angles-only (2-dim); they have no range trace.
            if len(o.measurement) > 2:
                bucket["range_km"].append(o.measurement[2] / 1e3)

observations.sort(key=lambda o: o.epoch)
passes.sort(key=lambda p: p[1].window_open)
print(f"\nSimulated {len(observations)} measurements over {len(passes)} passes")

print("\n" + "=" * 100)
print("Pass Table")
print("=" * 100)
print(f"{'Site':<28}{'Start':<22}{'End':<22}{'Duration (min)':>16}{'Obs':>8}")
print("-" * 100)
for sensor_name, w, n_obs in passes:
    start_str = str(w.window_open).split(".")[0]
    end_str = str(w.window_close).split(".")[0]
    duration_min = w.duration / 60.0
    print(
        f"{sensor_name:<28}{start_str:<22}{end_str:<22}{duration_min:>14.1f} m{n_obs:>8}"
    )
print("=" * 100)

fig_measurements = make_subplots(
    rows=3,
    cols=1,
    shared_xaxes=True,
    subplot_titles=("Azimuth (deg)", "Elevation (deg)", "Range (km)"),
    vertical_spacing=0.08,
)
for i, sensor in enumerate(sensors):
    bucket = sensor_meas[i]
    if not bucket["t"]:
        continue
    color = sensor_colors[sensor.name]
    fig_measurements.add_trace(
        go.Scatter(
            x=bucket["t"],
            y=bucket["az"],
            mode="markers",
            name=sensor.name,
            legendgroup=sensor.name,
            marker={"color": color, "size": 5},
        ),
        row=1,
        col=1,
    )
    fig_measurements.add_trace(
        go.Scatter(
            x=bucket["t"],
            y=bucket["el"],
            mode="markers",
            name=sensor.name,
            legendgroup=sensor.name,
            showlegend=False,
            marker={"color": color, "size": 5},
        ),
        row=2,
        col=1,
    )
    # Angles-only optical sensors contribute no range trace.
    if bucket["range_km"]:
        fig_measurements.add_trace(
            go.Scatter(
                x=bucket["t"][: len(bucket["range_km"])],
                y=bucket["range_km"],
                mode="markers",
                name=sensor.name,
                legendgroup=sensor.name,
                showlegend=False,
                marker={"color": color, "size": 5},
            ),
            row=3,
            col=1,
        )

fig_measurements.update_xaxes(title_text="Time (minutes)", row=3, col=1)
fig_measurements.update_yaxes(title_text="Azimuth (deg)", row=1, col=1)
fig_measurements.update_yaxes(title_text="Elevation (deg)", row=2, col=1)
fig_measurements.update_yaxes(title_text="Range (km)", row=3, col=1)
fig_measurements.update_layout(
    title="Simulated SSN Radar Measurements (6-hour Tracking Arc)",
    height=800,
    margin={"l": 60, "r": 40, "t": 80, "b": 60},
)
# --8<-- [end:simulate_measurements]

# --8<-- [start:run_filters]


def extract_rtn_error_series(filt, truth_trajectory, t0):
    """Extract per-axis RTN error/1-sigma and total position error from filter records.

    Rotates each record's ECI position error and position-covariance block
    into the radial/along-track/cross-track (RTN) frame of the truth state
    at that epoch, using the library's ECI-to-RTN rotation.
    """
    t_min = []
    err_r, err_t, err_n, err_total = [], [], [], []
    sig_r, sig_t, sig_n, sig_total = [], [], [], []
    for rec in filt.records():
        truth_state = truth_trajectory.interpolate(rec.epoch)
        error_eci = rec.state_updated[:3] - truth_state[:3]
        rot = bh.rotation_eci_to_rtn(truth_state)
        error_rtn = rot @ error_eci
        cov_rtn = rot @ rec.covariance_updated[:3, :3] @ rot.T
        sigma_rtn = np.sqrt(np.diag(cov_rtn))

        t_min.append((rec.epoch - t0) / 60.0)
        err_r.append(error_rtn[0])
        err_t.append(error_rtn[1])
        err_n.append(error_rtn[2])
        sig_r.append(sigma_rtn[0])
        sig_t.append(sigma_rtn[1])
        sig_n.append(sigma_rtn[2])
        err_total.append(np.linalg.norm(error_eci))
        sig_total.append(np.linalg.norm(sigma_rtn))
    return {
        "t": np.array(t_min),
        "err_r": np.array(err_r),
        "err_t": np.array(err_t),
        "err_n": np.array(err_n),
        "sig_r": np.array(sig_r),
        "sig_t": np.array(sig_t),
        "sig_n": np.array(sig_n),
        "err_total": np.array(err_total),
        "sig_total": np.array(sig_total),
    }


# Shared initial guess: perturbed by 1 km in x-position, 1 m/s in y-velocity
initial_state = np.array(true_state)
initial_state[0] += 1000.0
initial_state[4] += 1.0
p0 = np.diag([1e6, 1e6, 1e6, 1e2, 1e2, 1e2])
models = [s.measurement_model() for s in sensors]

ekf = bh.ExtendedKalmanFilter(
    epoch,
    initial_state,
    p0,
    measurement_models=models,
    propagation_config=bh.NumericalPropagationConfig.default(),
    force_config=bh.ForceModelConfig.two_body(),
)
ukf = bh.UnscentedKalmanFilter(
    epoch,
    initial_state,
    p0,
    propagation_config=bh.NumericalPropagationConfig.default(),
    force_config=bh.ForceModelConfig.two_body(),
    measurement_models=models,
)

# Merge the (possibly overlapping) per-sensor pass windows -- e.g. Cavalier
# and Millstone both track the object around the same time -- into
# non-overlapping tracking intervals, sorted by start time.
interval_bounds = sorted((w.window_open, w.window_close) for _, w, _ in passes)
intervals = []
for start, end in interval_bounds:
    if intervals and start <= intervals[-1][1]:
        intervals[-1][1] = max(intervals[-1][1], end)
    else:
        intervals.append([start, end])

# Step each filter window-by-window: propagate through the gap before an
# interval at a fixed cadence (prediction-only, so covariance growth during
# the gap is recorded), then process every observation within the interval
# in time order.
print()
for name, filt in (("EKF", ekf), ("UKF", ukf)):
    start_time = time.time()
    prev_epoch = epoch
    for start, end in intervals:
        t = prev_epoch + PROPAGATE_STEP
        while t < start:
            filt.propagate_to(t)
            t = t + PROPAGATE_STEP
        for obs in observations:
            if start <= obs.epoch <= end:
                filt.process_observation(obs)
        prev_epoch = end
    print(
        f"{name} processed {len(observations)} observations in {time.time() - start_time:.1f} s"
    )

ekf_rtn = extract_rtn_error_series(ekf, truth_traj, epoch)
ukf_rtn = extract_rtn_error_series(ukf, truth_traj, epoch)
# --8<-- [end:run_filters]

# --8<-- [start:analyze_results]
FILTER_STYLES = {
    "EKF": {"color": "steelblue", "fill": "rgba(70, 130, 180, 0.2)"},
    "UKF": {"color": "coral", "fill": "rgba(255, 127, 80, 0.2)"},
}

fig_filters = make_subplots(
    rows=4,
    cols=2,
    shared_xaxes=True,
    subplot_titles=(
        "EKF Radial",
        "UKF Radial",
        "EKF Along-track",
        "UKF Along-track",
        "EKF Cross-track",
        "UKF Cross-track",
        "EKF Total Position Error",
        "UKF Total Position Error",
    ),
    vertical_spacing=0.06,
)


def add_band_and_error(fig, row, col, t_min, sigma, err, style):
    """Add a shaded +/- 3-sigma band with the signed error line drawn over it."""
    fig.add_trace(
        go.Scatter(
            x=t_min,
            y=3 * sigma,
            mode="lines",
            line={"width": 0},
            showlegend=False,
            hoverinfo="skip",
        ),
        row=row,
        col=col,
    )
    fig.add_trace(
        go.Scatter(
            x=t_min,
            y=-3 * sigma,
            mode="lines",
            line={"width": 0},
            fill="tonexty",
            fillcolor=style["fill"],
            showlegend=False,
            hoverinfo="skip",
        ),
        row=row,
        col=col,
    )
    fig.add_trace(
        go.Scatter(
            x=t_min,
            y=err,
            mode="lines",
            line={"color": style["color"], "width": 1.5},
            showlegend=False,
        ),
        row=row,
        col=col,
    )


for col, (name, result) in enumerate((("EKF", ekf_rtn), ("UKF", ukf_rtn)), start=1):
    style = FILTER_STYLES[name]
    add_band_and_error(
        fig_filters, 1, col, result["t"], result["sig_r"], result["err_r"], style
    )
    add_band_and_error(
        fig_filters, 2, col, result["t"], result["sig_t"], result["err_t"], style
    )
    add_band_and_error(
        fig_filters, 3, col, result["t"], result["sig_n"], result["err_n"], style
    )
    fig_filters.add_trace(
        go.Scatter(
            x=result["t"],
            y=result["err_total"],
            mode="lines",
            line={"color": style["color"], "width": 2},
            showlegend=False,
        ),
        row=4,
        col=col,
    )

# Shade pass windows on every row/column
for _, w, _ in passes:
    t0_min = (w.window_open - epoch) / 60.0
    t1_min = (w.window_close - epoch) / 60.0
    for row in (1, 2, 3, 4):
        for col in (1, 2):
            fig_filters.add_vrect(
                x0=t0_min,
                x1=t1_min,
                fillcolor="gray",
                opacity=0.15,
                line_width=0,
                row=row,
                col=col,
            )

for row, label in (
    (1, "Radial (m)"),
    (2, "Along-track (m)"),
    (3, "Cross-track (m)"),
    (4, "Position error (m)"),
):
    fig_filters.update_yaxes(title_text=label, row=row, col=1)
fig_filters.update_xaxes(title_text="Time (minutes)", row=4, col=1)
fig_filters.update_xaxes(title_text="Time (minutes)", row=4, col=2)
fig_filters.update_layout(
    title="EKF / UKF Filter Consistency (RTN)",
    height=1100,
    margin={"l": 60, "r": 40, "t": 80, "b": 60},
)

print("\n" + "=" * 80)
print("Filter Summary")
print("=" * 80)
print(
    f"EKF final position error: {ekf_rtn['err_total'][-1]:.1f} m  "
    f"(3-sigma = {3 * ekf_rtn['sig_total'][-1]:.1f} m)"
)
print(
    f"UKF final position error: {ukf_rtn['err_total'][-1]:.1f} m  "
    f"(3-sigma = {3 * ukf_rtn['sig_total'][-1]:.1f} m)"
)
print("=" * 80)

assert ekf_rtn["err_total"][-1] < 500.0, "EKF should converge to a small position error"
assert ukf_rtn["err_total"][-1] < 500.0, "UKF should converge to a small position error"
print("\nExample validated successfully!")
# --8<-- [end:analyze_results]
# --8<-- [end:all]

# ============================================================================
# Plot Output Section (for documentation generation)
# ============================================================================

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "plots"))
from brahe_theme import save_themed_html

# Save the sensor network ground track as themed HTML
light_path, dark_path = save_themed_html(fig_network, OUTDIR / f"{SCRIPT_NAME}_network")
print(f"\n✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")

# Save the measurement time series as themed HTML
light_path, dark_path = save_themed_html(
    fig_measurements, OUTDIR / f"{SCRIPT_NAME}_measurements"
)
print(f"✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")

# Save the filter comparison figure as themed HTML
light_path, dark_path = save_themed_html(fig_filters, OUTDIR / f"{SCRIPT_NAME}_filters")
print(f"✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")
```

## Analyze Results

Finally, we check filter consistency -- whether the formal uncertainty actually bounds the true error -- by rotating each record's position error and position-covariance block into the radial/along-track/cross-track (RTN) frame of the truth state at that epoch with `bh.rotation_eci_to_rtn()`. Each per-axis row shades a &plusmn;3&sigma; band from the rotated covariance diagonal and draws the signed error on top, so a consistent filter keeps its error line inside the shaded band; a bottom row shows the unsigned total position error on a linear scale:

```python
#!/usr/bin/env python
# /// script
# dependencies = ["brahe", "plotly", "numpy"]
# ///

"""
SSN Radar Tracking: Extended and Unscented Kalman Filters

This example simulates Space Surveillance Network (SSN) radar tracking of a
LEO object and estimates its orbit sequentially with an Extended Kalman
Filter and an Unscented Kalman Filter. It loads the Vallado SSN sensor
dataset, builds az/el/range sensors, visualizes the sensor network's ground
coverage against a simulated LEO ground track, simulates radar measurements
during passes over a 6-hour tracking arc, processes them sequentially with
both filters while propagating through the gaps between passes, and
compares each filter's true position error against its formal 3-sigma
uncertainty.

A batch-estimation companion, ssn_tracking_bls.py, reproduces the same
scenario and solves for the orbit with Batch Least Squares instead; it is
excluded from the automated example tests because BLS re-propagates the
full arc at every iteration and takes on the order of three minutes to run.
"""

# --8<-- [start:all]
# --8<-- [start:preamble]
import os
import pathlib
import sys
import time

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import brahe as bh

bh.initialize_eop()

# Configuration
MEAS_INTERVAL = 15.0  # seconds between measurements during a pass
DURATION = 6 * 3600.0  # tracking duration (seconds)
SEED = 42
PROPAGATE_STEP = 60.0  # gap-propagation step (seconds)
# --8<-- [end:preamble]

# Configuration for output files
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# --8<-- [start:load_sensors]
# Load the Vallado SSN sensor sites and build sensors from the fully
# calibrated sites. The dataset mixes radar/phased-array (azel_range, measuring
# az/el/range) and optical (angles-only az/el) trackers; both are supported.
# from_locations_calibrated keeps only sites with full Table 4-4 calibration --
# it drops two radar sites (Haystack, HAX) that lack noise values, while
# from_locations would include them instead, defaulted to zero noise.
sites = bh.datasets.ssn_sensors.load()
sensors = bh.SimpleSSNSensor.from_locations_calibrated(sites, seed=SEED)
print(f"Loaded {len(sites)} SSN sites, {len(sensors)} calibrated sensors")

print("\n" + "=" * 100)
print("SSN Sensor Network")
print("=" * 100)
print(
    f"{'Name':<28}{'System':<12}{'El Min':>8}{'Range Max':>12}"
    f"{'Az Noise':>10}{'El Noise':>10}{'Range Noise':>13}"
)
print("-" * 100)
for s in sensors:
    props = s.location.properties
    system = props.get("system", "?")
    az_noise = props.get("az_noise_deg", float("nan"))
    el_noise = props.get("el_noise_deg", float("nan"))
    range_noise = props.get("range_noise_m", float("nan"))
    range_max_str = (
        f"{s.range_max / 1e3:>9.0f} km" if s.range_max is not None else "  unlimited"
    )
    print(
        f"{s.name:<28}{system:<12}{s.el_min:>7.1f}°{range_max_str:>12}"
        f"{az_noise:>9.4f}°{el_noise:>9.4f}°{range_noise:>11.1f} m"
    )
print("=" * 100)
# --8<-- [end:load_sensors]

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

# --8<-- [start:visualize_network]
# Assign each sensor a stable color, reused for its measurement traces in the
# figure below, so a comm cone's color on the map identifies the same sensor
# in the az/el/range plot.
PALETTE = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
    "#aec7e8",
    "#ffbb78",
    "#98df8a",
    "#ff9896",
    "#c5b0d5",
]
sensor_colors = {s.name: PALETTE[i % len(PALETTE)] for i, s in enumerate(sensors)}

fig_network = bh.plot_groundtrack(
    trajectories=[
        {"trajectory": truth_prop.trajectory, "color": "red", "line_width": 2}
    ],
    ground_stations=[
        {"stations": [s.location], "color": sensor_colors[s.name], "alpha": 0.25}
        for s in sensors
    ],
    gs_cone_altitude=700e3,
    gs_min_elevation=5.0,
    basemap="natural_earth",
    backend="plotly",
)

# plot_groundtrack's built-in legend can't label per-sensor groups (every
# station-marker trace is named "Ground Stations"), so add a small manual
# legend mapping each sensor's name to its color.
for s in sensors:
    fig_network.add_trace(
        go.Scattergeo(
            lat=[None],
            lon=[None],
            mode="markers",
            marker={"size": 8, "color": sensor_colors[s.name]},
            name=s.name,
            showlegend=True,
        )
    )
fig_network.update_layout(showlegend=True)
# --8<-- [end:visualize_network]

# --8<-- [start:simulate_measurements]
# Find passes and simulate measurements only inside them. Sensor measurement
# buckets for the figure below are filled as each pass is simulated, since
# per-sensor plotting order doesn't depend on the global time order that the
# sequential filters need; only `observations` has to be globally sorted.
observations = []
passes = []  # (sensor_name, window, n_obs)
sensor_meas = {
    i: {"t": [], "az": [], "el": [], "range_km": []} for i in range(len(sensors))
}
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
            passes.append((sensor.name, w, len(obs)))
        bucket = sensor_meas[i]
        for o in obs:
            bucket["t"].append((o.epoch - epoch) / 60.0)
            bucket["az"].append(o.measurement[0])
            bucket["el"].append(o.measurement[1])
            # Optical sensors are angles-only (2-dim); they have no range trace.
            if len(o.measurement) > 2:
                bucket["range_km"].append(o.measurement[2] / 1e3)

observations.sort(key=lambda o: o.epoch)
passes.sort(key=lambda p: p[1].window_open)
print(f"\nSimulated {len(observations)} measurements over {len(passes)} passes")

print("\n" + "=" * 100)
print("Pass Table")
print("=" * 100)
print(f"{'Site':<28}{'Start':<22}{'End':<22}{'Duration (min)':>16}{'Obs':>8}")
print("-" * 100)
for sensor_name, w, n_obs in passes:
    start_str = str(w.window_open).split(".")[0]
    end_str = str(w.window_close).split(".")[0]
    duration_min = w.duration / 60.0
    print(
        f"{sensor_name:<28}{start_str:<22}{end_str:<22}{duration_min:>14.1f} m{n_obs:>8}"
    )
print("=" * 100)

fig_measurements = make_subplots(
    rows=3,
    cols=1,
    shared_xaxes=True,
    subplot_titles=("Azimuth (deg)", "Elevation (deg)", "Range (km)"),
    vertical_spacing=0.08,
)
for i, sensor in enumerate(sensors):
    bucket = sensor_meas[i]
    if not bucket["t"]:
        continue
    color = sensor_colors[sensor.name]
    fig_measurements.add_trace(
        go.Scatter(
            x=bucket["t"],
            y=bucket["az"],
            mode="markers",
            name=sensor.name,
            legendgroup=sensor.name,
            marker={"color": color, "size": 5},
        ),
        row=1,
        col=1,
    )
    fig_measurements.add_trace(
        go.Scatter(
            x=bucket["t"],
            y=bucket["el"],
            mode="markers",
            name=sensor.name,
            legendgroup=sensor.name,
            showlegend=False,
            marker={"color": color, "size": 5},
        ),
        row=2,
        col=1,
    )
    # Angles-only optical sensors contribute no range trace.
    if bucket["range_km"]:
        fig_measurements.add_trace(
            go.Scatter(
                x=bucket["t"][: len(bucket["range_km"])],
                y=bucket["range_km"],
                mode="markers",
                name=sensor.name,
                legendgroup=sensor.name,
                showlegend=False,
                marker={"color": color, "size": 5},
            ),
            row=3,
            col=1,
        )

fig_measurements.update_xaxes(title_text="Time (minutes)", row=3, col=1)
fig_measurements.update_yaxes(title_text="Azimuth (deg)", row=1, col=1)
fig_measurements.update_yaxes(title_text="Elevation (deg)", row=2, col=1)
fig_measurements.update_yaxes(title_text="Range (km)", row=3, col=1)
fig_measurements.update_layout(
    title="Simulated SSN Radar Measurements (6-hour Tracking Arc)",
    height=800,
    margin={"l": 60, "r": 40, "t": 80, "b": 60},
)
# --8<-- [end:simulate_measurements]

# --8<-- [start:run_filters]


def extract_rtn_error_series(filt, truth_trajectory, t0):
    """Extract per-axis RTN error/1-sigma and total position error from filter records.

    Rotates each record's ECI position error and position-covariance block
    into the radial/along-track/cross-track (RTN) frame of the truth state
    at that epoch, using the library's ECI-to-RTN rotation.
    """
    t_min = []
    err_r, err_t, err_n, err_total = [], [], [], []
    sig_r, sig_t, sig_n, sig_total = [], [], [], []
    for rec in filt.records():
        truth_state = truth_trajectory.interpolate(rec.epoch)
        error_eci = rec.state_updated[:3] - truth_state[:3]
        rot = bh.rotation_eci_to_rtn(truth_state)
        error_rtn = rot @ error_eci
        cov_rtn = rot @ rec.covariance_updated[:3, :3] @ rot.T
        sigma_rtn = np.sqrt(np.diag(cov_rtn))

        t_min.append((rec.epoch - t0) / 60.0)
        err_r.append(error_rtn[0])
        err_t.append(error_rtn[1])
        err_n.append(error_rtn[2])
        sig_r.append(sigma_rtn[0])
        sig_t.append(sigma_rtn[1])
        sig_n.append(sigma_rtn[2])
        err_total.append(np.linalg.norm(error_eci))
        sig_total.append(np.linalg.norm(sigma_rtn))
    return {
        "t": np.array(t_min),
        "err_r": np.array(err_r),
        "err_t": np.array(err_t),
        "err_n": np.array(err_n),
        "sig_r": np.array(sig_r),
        "sig_t": np.array(sig_t),
        "sig_n": np.array(sig_n),
        "err_total": np.array(err_total),
        "sig_total": np.array(sig_total),
    }


# Shared initial guess: perturbed by 1 km in x-position, 1 m/s in y-velocity
initial_state = np.array(true_state)
initial_state[0] += 1000.0
initial_state[4] += 1.0
p0 = np.diag([1e6, 1e6, 1e6, 1e2, 1e2, 1e2])
models = [s.measurement_model() for s in sensors]

ekf = bh.ExtendedKalmanFilter(
    epoch,
    initial_state,
    p0,
    measurement_models=models,
    propagation_config=bh.NumericalPropagationConfig.default(),
    force_config=bh.ForceModelConfig.two_body(),
)
ukf = bh.UnscentedKalmanFilter(
    epoch,
    initial_state,
    p0,
    propagation_config=bh.NumericalPropagationConfig.default(),
    force_config=bh.ForceModelConfig.two_body(),
    measurement_models=models,
)

# Merge the (possibly overlapping) per-sensor pass windows -- e.g. Cavalier
# and Millstone both track the object around the same time -- into
# non-overlapping tracking intervals, sorted by start time.
interval_bounds = sorted((w.window_open, w.window_close) for _, w, _ in passes)
intervals = []
for start, end in interval_bounds:
    if intervals and start <= intervals[-1][1]:
        intervals[-1][1] = max(intervals[-1][1], end)
    else:
        intervals.append([start, end])

# Step each filter window-by-window: propagate through the gap before an
# interval at a fixed cadence (prediction-only, so covariance growth during
# the gap is recorded), then process every observation within the interval
# in time order.
print()
for name, filt in (("EKF", ekf), ("UKF", ukf)):
    start_time = time.time()
    prev_epoch = epoch
    for start, end in intervals:
        t = prev_epoch + PROPAGATE_STEP
        while t < start:
            filt.propagate_to(t)
            t = t + PROPAGATE_STEP
        for obs in observations:
            if start <= obs.epoch <= end:
                filt.process_observation(obs)
        prev_epoch = end
    print(
        f"{name} processed {len(observations)} observations in {time.time() - start_time:.1f} s"
    )

ekf_rtn = extract_rtn_error_series(ekf, truth_traj, epoch)
ukf_rtn = extract_rtn_error_series(ukf, truth_traj, epoch)
# --8<-- [end:run_filters]

# --8<-- [start:analyze_results]
FILTER_STYLES = {
    "EKF": {"color": "steelblue", "fill": "rgba(70, 130, 180, 0.2)"},
    "UKF": {"color": "coral", "fill": "rgba(255, 127, 80, 0.2)"},
}

fig_filters = make_subplots(
    rows=4,
    cols=2,
    shared_xaxes=True,
    subplot_titles=(
        "EKF Radial",
        "UKF Radial",
        "EKF Along-track",
        "UKF Along-track",
        "EKF Cross-track",
        "UKF Cross-track",
        "EKF Total Position Error",
        "UKF Total Position Error",
    ),
    vertical_spacing=0.06,
)


def add_band_and_error(fig, row, col, t_min, sigma, err, style):
    """Add a shaded +/- 3-sigma band with the signed error line drawn over it."""
    fig.add_trace(
        go.Scatter(
            x=t_min,
            y=3 * sigma,
            mode="lines",
            line={"width": 0},
            showlegend=False,
            hoverinfo="skip",
        ),
        row=row,
        col=col,
    )
    fig.add_trace(
        go.Scatter(
            x=t_min,
            y=-3 * sigma,
            mode="lines",
            line={"width": 0},
            fill="tonexty",
            fillcolor=style["fill"],
            showlegend=False,
            hoverinfo="skip",
        ),
        row=row,
        col=col,
    )
    fig.add_trace(
        go.Scatter(
            x=t_min,
            y=err,
            mode="lines",
            line={"color": style["color"], "width": 1.5},
            showlegend=False,
        ),
        row=row,
        col=col,
    )


for col, (name, result) in enumerate((("EKF", ekf_rtn), ("UKF", ukf_rtn)), start=1):
    style = FILTER_STYLES[name]
    add_band_and_error(
        fig_filters, 1, col, result["t"], result["sig_r"], result["err_r"], style
    )
    add_band_and_error(
        fig_filters, 2, col, result["t"], result["sig_t"], result["err_t"], style
    )
    add_band_and_error(
        fig_filters, 3, col, result["t"], result["sig_n"], result["err_n"], style
    )
    fig_filters.add_trace(
        go.Scatter(
            x=result["t"],
            y=result["err_total"],
            mode="lines",
            line={"color": style["color"], "width": 2},
            showlegend=False,
        ),
        row=4,
        col=col,
    )

# Shade pass windows on every row/column
for _, w, _ in passes:
    t0_min = (w.window_open - epoch) / 60.0
    t1_min = (w.window_close - epoch) / 60.0
    for row in (1, 2, 3, 4):
        for col in (1, 2):
            fig_filters.add_vrect(
                x0=t0_min,
                x1=t1_min,
                fillcolor="gray",
                opacity=0.15,
                line_width=0,
                row=row,
                col=col,
            )

for row, label in (
    (1, "Radial (m)"),
    (2, "Along-track (m)"),
    (3, "Cross-track (m)"),
    (4, "Position error (m)"),
):
    fig_filters.update_yaxes(title_text=label, row=row, col=1)
fig_filters.update_xaxes(title_text="Time (minutes)", row=4, col=1)
fig_filters.update_xaxes(title_text="Time (minutes)", row=4, col=2)
fig_filters.update_layout(
    title="EKF / UKF Filter Consistency (RTN)",
    height=1100,
    margin={"l": 60, "r": 40, "t": 80, "b": 60},
)

print("\n" + "=" * 80)
print("Filter Summary")
print("=" * 80)
print(
    f"EKF final position error: {ekf_rtn['err_total'][-1]:.1f} m  "
    f"(3-sigma = {3 * ekf_rtn['sig_total'][-1]:.1f} m)"
)
print(
    f"UKF final position error: {ukf_rtn['err_total'][-1]:.1f} m  "
    f"(3-sigma = {3 * ukf_rtn['sig_total'][-1]:.1f} m)"
)
print("=" * 80)

assert ekf_rtn["err_total"][-1] < 500.0, "EKF should converge to a small position error"
assert ukf_rtn["err_total"][-1] < 500.0, "UKF should converge to a small position error"
print("\nExample validated successfully!")
# --8<-- [end:analyze_results]
# --8<-- [end:all]

# ============================================================================
# Plot Output Section (for documentation generation)
# ============================================================================

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "plots"))
from brahe_theme import save_themed_html

# Save the sensor network ground track as themed HTML
light_path, dark_path = save_themed_html(fig_network, OUTDIR / f"{SCRIPT_NAME}_network")
print(f"\n✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")

# Save the measurement time series as themed HTML
light_path, dark_path = save_themed_html(
    fig_measurements, OUTDIR / f"{SCRIPT_NAME}_measurements"
)
print(f"✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")

# Save the filter comparison figure as themed HTML
light_path, dark_path = save_themed_html(fig_filters, OUTDIR / f"{SCRIPT_NAME}_filters")
print(f"✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")
```


Along-track error typically dominates the other two axes between passes: along-track position error grows from an along-track velocity or timing error integrated over time, while radial and cross-track errors stay comparatively small once the orbit plane and semi-major axis are well observed. The shaded bands widen visibly during the gaps between passes -- reflecting the same covariance growth visible in the `"Propagation"` records -- and narrow again once a new pass starts feeding measurements back in.

The EKF and UKF converge to nearly identical results here, both reaching meter-level final position error, since the two-body dynamics and az/el/range geometry are only mildly nonlinear over this arc; the UKF's sigma-point propagation does not offer a material advantage at this level of nonlinearity. Azimuth wrapping is handled consistently: `AzElRangeMeasurementModel.residual()` wraps the residual, the model's Jacobian differences through it, and the UKF forms its predicted measurement mean and innovation deviations through `residual()` as well, so a pass whose sigma-point azimuths straddle the 0/360&deg; wrap stays well-behaved.

## Batch Least Squares

BLS solves for the orbit in one batch, minimizing the weighted residual cost over the entire observation set at once, rather than the sequential filters' approach of recursively updating a running state estimate and letting covariance grow between passes. Each Gauss-Newton iteration re-propagates the full arc together with the state transition matrix, which makes BLS substantially slower than the sequential filters above, so this variant lives in its own script, `ssn_tracking_bls.py`.

The script reproduces the same scenario as `ssn_tracking.py` -- the sensor dataset, the truth orbit, and the simulated measurements -- before solving with BLS. Its default state-correction convergence threshold (`1e-8`, in mixed position/velocity units) is far tighter than the centimeter-level precision this measurement set actually supports, so the script loosens `state_correction_threshold` and adds a `cost_convergence_threshold`; this stops the solver once corrections are physically insignificant instead of exhausting `max_iterations` on progressively smaller, noise-driven corrections:

```python
#!/usr/bin/env python
# /// script
# dependencies = ["brahe", "numpy"]
# FLAGS = ["MANUAL"]
# ///

"""
SSN Radar Tracking: Batch Least Squares (manual companion)

This is the batch-estimation companion to ssn_tracking.py. It reproduces
the same 6-hour SSN tracking scenario -- the Vallado SSN sensor dataset,
the 700 km/72 degree LEO truth orbit, and the simulated az/el/range
measurements -- and estimates the orbit with Batch Least Squares (BLS)
instead of a sequential filter.

It carries `FLAGS = ["MANUAL"]` and is never run by the automated example
tests: BLS re-propagates the full 6-hour arc at every Gauss-Newton
iteration, which takes minutes locally and exceeds the example-runner
timeout on CI machines. Run this script directly to regenerate its
committed output (docs/outputs/examples/ssn_tracking_bls.py.txt), which
keeps the results available in the documentation without requiring a run.
"""

# --8<-- [start:all]
import time

import numpy as np

import brahe as bh

bh.initialize_eop()

# Configuration -- identical scenario to ssn_tracking.py.
MEAS_INTERVAL = 15.0  # seconds between measurements during a pass
DURATION = 6 * 3600.0  # tracking duration (seconds)
SEED = 42

# Load the Vallado SSN sensor sites and build sensors from the fully
# calibrated sites. The dataset mixes radar/phased-array (azel_range, az/el/
# range) and optical (angles-only az/el) trackers; both are supported.
# from_locations_calibrated keeps only sites with full Table 4-4 calibration --
# it drops two radar sites (Haystack, HAX) that lack noise values, while
# from_locations would include them instead, defaulted to zero noise.
sites = bh.datasets.ssn_sensors.load()
sensors = bh.SimpleSSNSensor.from_locations_calibrated(sites, seed=SEED)
print(f"Loaded {len(sites)} SSN sites, {len(sensors)} calibrated sensors")

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

# Find passes and simulate measurements only inside them
observations = []
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

observations.sort(key=lambda o: o.epoch)
print(f"Simulated {len(observations)} measurements")

# Shared initial guess: perturbed by 1 km in x-position, 1 m/s in y-velocity
initial_state = np.array(true_state)
initial_state[0] += 1000.0
initial_state[4] += 1.0
p0 = np.diag([1e6, 1e6, 1e6, 1e2, 1e2, 1e2])
models = [s.measurement_model() for s in sensors]

# --8<-- [start:run_bls]
# Batch Least Squares over the full observation set. The default
# state-correction threshold (1e-8, mixed position/velocity units) is far
# tighter than the ~cm-level precision this measurement set supports, so a
# looser threshold is used to stop once corrections are physically
# insignificant rather than exhausting max_iterations.
start_time = time.time()
bls_config = bh.BLSConfig(
    state_correction_threshold=1e-3, cost_convergence_threshold=1e-6
)
bls = bh.BatchLeastSquares(
    epoch,
    initial_state,
    p0,
    propagation_config=bh.NumericalPropagationConfig.default(),
    force_config=bh.ForceModelConfig.two_body(),
    measurement_models=models,
    config=bls_config,
)
bls.solve(observations)
print(
    f"BLS solved {len(observations)} observations in {time.time() - start_time:.1f} s"
)

bls_err = np.linalg.norm(bls.current_state()[:3] - true_state[:3])
bls_sigma = np.sqrt(np.sum(np.diag(bls.formal_covariance())[:3]))

print(f"BLS position error: {bls_err:.1f} m  (3-sigma formal = {3 * bls_sigma:.1f} m)")
print(
    f"BLS converged: {bls.converged()}, iterations: {bls.iterations_completed()}, "
    f"final cost: {bls.final_cost():.6e}"
)
# --8<-- [end:run_bls]

assert bls_err < 500.0, "BLS should converge to a small position error"
print("\nExample validated successfully!")
# --8<-- [end:all]
```

???+ example "Output"
```
Loaded 21 SSN sites, 16 calibrated sensors
Simulated 792 measurements
BLS solved 792 observations in 20.4 s
BLS position error: 6.2 m  (3-sigma formal = 26.1 m)
BLS converged: True, iterations: 4, final cost: 2.359809e+03

Example validated successfully!
```

BLS's final position error is somewhat higher than the sequential filters reach, since it minimizes the residual cost over the whole arc rather than tracking the most recent state, though its formal uncertainty remains comparable to the sequential filters', as shown in the output above.

**Full Code**

```
#!/usr/bin/env python
# /// script
# dependencies = ["brahe", "numpy"]
# FLAGS = ["MANUAL"]
# ///

"""
SSN Radar Tracking: Batch Least Squares (manual companion)

This is the batch-estimation companion to ssn_tracking.py. It reproduces
the same 6-hour SSN tracking scenario -- the Vallado SSN sensor dataset,
the 700 km/72 degree LEO truth orbit, and the simulated az/el/range
measurements -- and estimates the orbit with Batch Least Squares (BLS)
instead of a sequential filter.

It carries `FLAGS = ["MANUAL"]` and is never run by the automated example
tests: BLS re-propagates the full 6-hour arc at every Gauss-Newton
iteration, which takes minutes locally and exceeds the example-runner
timeout on CI machines. Run this script directly to regenerate its
committed output (docs/outputs/examples/ssn_tracking_bls.py.txt), which
keeps the results available in the documentation without requiring a run.
"""

# --8<-- [start:all]
import time

import numpy as np

import brahe as bh

bh.initialize_eop()

# Configuration -- identical scenario to ssn_tracking.py.
MEAS_INTERVAL = 15.0  # seconds between measurements during a pass
DURATION = 6 * 3600.0  # tracking duration (seconds)
SEED = 42

# Load the Vallado SSN sensor sites and build sensors from the fully
# calibrated sites. The dataset mixes radar/phased-array (azel_range, az/el/
# range) and optical (angles-only az/el) trackers; both are supported.
# from_locations_calibrated keeps only sites with full Table 4-4 calibration --
# it drops two radar sites (Haystack, HAX) that lack noise values, while
# from_locations would include them instead, defaulted to zero noise.
sites = bh.datasets.ssn_sensors.load()
sensors = bh.SimpleSSNSensor.from_locations_calibrated(sites, seed=SEED)
print(f"Loaded {len(sites)} SSN sites, {len(sensors)} calibrated sensors")

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

# Find passes and simulate measurements only inside them
observations = []
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

observations.sort(key=lambda o: o.epoch)
print(f"Simulated {len(observations)} measurements")

# Shared initial guess: perturbed by 1 km in x-position, 1 m/s in y-velocity
initial_state = np.array(true_state)
initial_state[0] += 1000.0
initial_state[4] += 1.0
p0 = np.diag([1e6, 1e6, 1e6, 1e2, 1e2, 1e2])
models = [s.measurement_model() for s in sensors]

# --8<-- [start:run_bls]
# Batch Least Squares over the full observation set. The default
# state-correction threshold (1e-8, mixed position/velocity units) is far
# tighter than the ~cm-level precision this measurement set supports, so a
# looser threshold is used to stop once corrections are physically
# insignificant rather than exhausting max_iterations.
start_time = time.time()
bls_config = bh.BLSConfig(
    state_correction_threshold=1e-3, cost_convergence_threshold=1e-6
)
bls = bh.BatchLeastSquares(
    epoch,
    initial_state,
    p0,
    propagation_config=bh.NumericalPropagationConfig.default(),
    force_config=bh.ForceModelConfig.two_body(),
    measurement_models=models,
    config=bls_config,
)
bls.solve(observations)
print(
    f"BLS solved {len(observations)} observations in {time.time() - start_time:.1f} s"
)

bls_err = np.linalg.norm(bls.current_state()[:3] - true_state[:3])
bls_sigma = np.sqrt(np.sum(np.diag(bls.formal_covariance())[:3]))

print(f"BLS position error: {bls_err:.1f} m  (3-sigma formal = {3 * bls_sigma:.1f} m)")
print(
    f"BLS converged: {bls.converged()}, iterations: {bls.iterations_completed()}, "
    f"final cost: {bls.final_cost():.6e}"
)
# --8<-- [end:run_bls]

assert bls_err < 500.0, "BLS should converge to a small position error"
print("\nExample validated successfully!")
# --8<-- [end:all]
```

## Full Code Example

**Full Code**

```
#!/usr/bin/env python
# /// script
# dependencies = ["brahe", "plotly", "numpy"]
# ///

"""
SSN Radar Tracking: Extended and Unscented Kalman Filters

This example simulates Space Surveillance Network (SSN) radar tracking of a
LEO object and estimates its orbit sequentially with an Extended Kalman
Filter and an Unscented Kalman Filter. It loads the Vallado SSN sensor
dataset, builds az/el/range sensors, visualizes the sensor network's ground
coverage against a simulated LEO ground track, simulates radar measurements
during passes over a 6-hour tracking arc, processes them sequentially with
both filters while propagating through the gaps between passes, and
compares each filter's true position error against its formal 3-sigma
uncertainty.

A batch-estimation companion, ssn_tracking_bls.py, reproduces the same
scenario and solves for the orbit with Batch Least Squares instead; it is
excluded from the automated example tests because BLS re-propagates the
full arc at every iteration and takes on the order of three minutes to run.
"""

# --8<-- [start:all]
# --8<-- [start:preamble]
import os
import pathlib
import sys
import time

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import brahe as bh

bh.initialize_eop()

# Configuration
MEAS_INTERVAL = 15.0  # seconds between measurements during a pass
DURATION = 6 * 3600.0  # tracking duration (seconds)
SEED = 42
PROPAGATE_STEP = 60.0  # gap-propagation step (seconds)
# --8<-- [end:preamble]

# Configuration for output files
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# --8<-- [start:load_sensors]
# Load the Vallado SSN sensor sites and build sensors from the fully
# calibrated sites. The dataset mixes radar/phased-array (azel_range, measuring
# az/el/range) and optical (angles-only az/el) trackers; both are supported.
# from_locations_calibrated keeps only sites with full Table 4-4 calibration --
# it drops two radar sites (Haystack, HAX) that lack noise values, while
# from_locations would include them instead, defaulted to zero noise.
sites = bh.datasets.ssn_sensors.load()
sensors = bh.SimpleSSNSensor.from_locations_calibrated(sites, seed=SEED)
print(f"Loaded {len(sites)} SSN sites, {len(sensors)} calibrated sensors")

print("\n" + "=" * 100)
print("SSN Sensor Network")
print("=" * 100)
print(
    f"{'Name':<28}{'System':<12}{'El Min':>8}{'Range Max':>12}"
    f"{'Az Noise':>10}{'El Noise':>10}{'Range Noise':>13}"
)
print("-" * 100)
for s in sensors:
    props = s.location.properties
    system = props.get("system", "?")
    az_noise = props.get("az_noise_deg", float("nan"))
    el_noise = props.get("el_noise_deg", float("nan"))
    range_noise = props.get("range_noise_m", float("nan"))
    range_max_str = (
        f"{s.range_max / 1e3:>9.0f} km" if s.range_max is not None else "  unlimited"
    )
    print(
        f"{s.name:<28}{system:<12}{s.el_min:>7.1f}°{range_max_str:>12}"
        f"{az_noise:>9.4f}°{el_noise:>9.4f}°{range_noise:>11.1f} m"
    )
print("=" * 100)
# --8<-- [end:load_sensors]

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

# --8<-- [start:visualize_network]
# Assign each sensor a stable color, reused for its measurement traces in the
# figure below, so a comm cone's color on the map identifies the same sensor
# in the az/el/range plot.
PALETTE = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
    "#aec7e8",
    "#ffbb78",
    "#98df8a",
    "#ff9896",
    "#c5b0d5",
]
sensor_colors = {s.name: PALETTE[i % len(PALETTE)] for i, s in enumerate(sensors)}

fig_network = bh.plot_groundtrack(
    trajectories=[
        {"trajectory": truth_prop.trajectory, "color": "red", "line_width": 2}
    ],
    ground_stations=[
        {"stations": [s.location], "color": sensor_colors[s.name], "alpha": 0.25}
        for s in sensors
    ],
    gs_cone_altitude=700e3,
    gs_min_elevation=5.0,
    basemap="natural_earth",
    backend="plotly",
)

# plot_groundtrack's built-in legend can't label per-sensor groups (every
# station-marker trace is named "Ground Stations"), so add a small manual
# legend mapping each sensor's name to its color.
for s in sensors:
    fig_network.add_trace(
        go.Scattergeo(
            lat=[None],
            lon=[None],
            mode="markers",
            marker={"size": 8, "color": sensor_colors[s.name]},
            name=s.name,
            showlegend=True,
        )
    )
fig_network.update_layout(showlegend=True)
# --8<-- [end:visualize_network]

# --8<-- [start:simulate_measurements]
# Find passes and simulate measurements only inside them. Sensor measurement
# buckets for the figure below are filled as each pass is simulated, since
# per-sensor plotting order doesn't depend on the global time order that the
# sequential filters need; only `observations` has to be globally sorted.
observations = []
passes = []  # (sensor_name, window, n_obs)
sensor_meas = {
    i: {"t": [], "az": [], "el": [], "range_km": []} for i in range(len(sensors))
}
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
            passes.append((sensor.name, w, len(obs)))
        bucket = sensor_meas[i]
        for o in obs:
            bucket["t"].append((o.epoch - epoch) / 60.0)
            bucket["az"].append(o.measurement[0])
            bucket["el"].append(o.measurement[1])
            # Optical sensors are angles-only (2-dim); they have no range trace.
            if len(o.measurement) > 2:
                bucket["range_km"].append(o.measurement[2] / 1e3)

observations.sort(key=lambda o: o.epoch)
passes.sort(key=lambda p: p[1].window_open)
print(f"\nSimulated {len(observations)} measurements over {len(passes)} passes")

print("\n" + "=" * 100)
print("Pass Table")
print("=" * 100)
print(f"{'Site':<28}{'Start':<22}{'End':<22}{'Duration (min)':>16}{'Obs':>8}")
print("-" * 100)
for sensor_name, w, n_obs in passes:
    start_str = str(w.window_open).split(".")[0]
    end_str = str(w.window_close).split(".")[0]
    duration_min = w.duration / 60.0
    print(
        f"{sensor_name:<28}{start_str:<22}{end_str:<22}{duration_min:>14.1f} m{n_obs:>8}"
    )
print("=" * 100)

fig_measurements = make_subplots(
    rows=3,
    cols=1,
    shared_xaxes=True,
    subplot_titles=("Azimuth (deg)", "Elevation (deg)", "Range (km)"),
    vertical_spacing=0.08,
)
for i, sensor in enumerate(sensors):
    bucket = sensor_meas[i]
    if not bucket["t"]:
        continue
    color = sensor_colors[sensor.name]
    fig_measurements.add_trace(
        go.Scatter(
            x=bucket["t"],
            y=bucket["az"],
            mode="markers",
            name=sensor.name,
            legendgroup=sensor.name,
            marker={"color": color, "size": 5},
        ),
        row=1,
        col=1,
    )
    fig_measurements.add_trace(
        go.Scatter(
            x=bucket["t"],
            y=bucket["el"],
            mode="markers",
            name=sensor.name,
            legendgroup=sensor.name,
            showlegend=False,
            marker={"color": color, "size": 5},
        ),
        row=2,
        col=1,
    )
    # Angles-only optical sensors contribute no range trace.
    if bucket["range_km"]:
        fig_measurements.add_trace(
            go.Scatter(
                x=bucket["t"][: len(bucket["range_km"])],
                y=bucket["range_km"],
                mode="markers",
                name=sensor.name,
                legendgroup=sensor.name,
                showlegend=False,
                marker={"color": color, "size": 5},
            ),
            row=3,
            col=1,
        )

fig_measurements.update_xaxes(title_text="Time (minutes)", row=3, col=1)
fig_measurements.update_yaxes(title_text="Azimuth (deg)", row=1, col=1)
fig_measurements.update_yaxes(title_text="Elevation (deg)", row=2, col=1)
fig_measurements.update_yaxes(title_text="Range (km)", row=3, col=1)
fig_measurements.update_layout(
    title="Simulated SSN Radar Measurements (6-hour Tracking Arc)",
    height=800,
    margin={"l": 60, "r": 40, "t": 80, "b": 60},
)
# --8<-- [end:simulate_measurements]

# --8<-- [start:run_filters]


def extract_rtn_error_series(filt, truth_trajectory, t0):
    """Extract per-axis RTN error/1-sigma and total position error from filter records.

    Rotates each record's ECI position error and position-covariance block
    into the radial/along-track/cross-track (RTN) frame of the truth state
    at that epoch, using the library's ECI-to-RTN rotation.
    """
    t_min = []
    err_r, err_t, err_n, err_total = [], [], [], []
    sig_r, sig_t, sig_n, sig_total = [], [], [], []
    for rec in filt.records():
        truth_state = truth_trajectory.interpolate(rec.epoch)
        error_eci = rec.state_updated[:3] - truth_state[:3]
        rot = bh.rotation_eci_to_rtn(truth_state)
        error_rtn = rot @ error_eci
        cov_rtn = rot @ rec.covariance_updated[:3, :3] @ rot.T
        sigma_rtn = np.sqrt(np.diag(cov_rtn))

        t_min.append((rec.epoch - t0) / 60.0)
        err_r.append(error_rtn[0])
        err_t.append(error_rtn[1])
        err_n.append(error_rtn[2])
        sig_r.append(sigma_rtn[0])
        sig_t.append(sigma_rtn[1])
        sig_n.append(sigma_rtn[2])
        err_total.append(np.linalg.norm(error_eci))
        sig_total.append(np.linalg.norm(sigma_rtn))
    return {
        "t": np.array(t_min),
        "err_r": np.array(err_r),
        "err_t": np.array(err_t),
        "err_n": np.array(err_n),
        "sig_r": np.array(sig_r),
        "sig_t": np.array(sig_t),
        "sig_n": np.array(sig_n),
        "err_total": np.array(err_total),
        "sig_total": np.array(sig_total),
    }


# Shared initial guess: perturbed by 1 km in x-position, 1 m/s in y-velocity
initial_state = np.array(true_state)
initial_state[0] += 1000.0
initial_state[4] += 1.0
p0 = np.diag([1e6, 1e6, 1e6, 1e2, 1e2, 1e2])
models = [s.measurement_model() for s in sensors]

ekf = bh.ExtendedKalmanFilter(
    epoch,
    initial_state,
    p0,
    measurement_models=models,
    propagation_config=bh.NumericalPropagationConfig.default(),
    force_config=bh.ForceModelConfig.two_body(),
)
ukf = bh.UnscentedKalmanFilter(
    epoch,
    initial_state,
    p0,
    propagation_config=bh.NumericalPropagationConfig.default(),
    force_config=bh.ForceModelConfig.two_body(),
    measurement_models=models,
)

# Merge the (possibly overlapping) per-sensor pass windows -- e.g. Cavalier
# and Millstone both track the object around the same time -- into
# non-overlapping tracking intervals, sorted by start time.
interval_bounds = sorted((w.window_open, w.window_close) for _, w, _ in passes)
intervals = []
for start, end in interval_bounds:
    if intervals and start <= intervals[-1][1]:
        intervals[-1][1] = max(intervals[-1][1], end)
    else:
        intervals.append([start, end])

# Step each filter window-by-window: propagate through the gap before an
# interval at a fixed cadence (prediction-only, so covariance growth during
# the gap is recorded), then process every observation within the interval
# in time order.
print()
for name, filt in (("EKF", ekf), ("UKF", ukf)):
    start_time = time.time()
    prev_epoch = epoch
    for start, end in intervals:
        t = prev_epoch + PROPAGATE_STEP
        while t < start:
            filt.propagate_to(t)
            t = t + PROPAGATE_STEP
        for obs in observations:
            if start <= obs.epoch <= end:
                filt.process_observation(obs)
        prev_epoch = end
    print(
        f"{name} processed {len(observations)} observations in {time.time() - start_time:.1f} s"
    )

ekf_rtn = extract_rtn_error_series(ekf, truth_traj, epoch)
ukf_rtn = extract_rtn_error_series(ukf, truth_traj, epoch)
# --8<-- [end:run_filters]

# --8<-- [start:analyze_results]
FILTER_STYLES = {
    "EKF": {"color": "steelblue", "fill": "rgba(70, 130, 180, 0.2)"},
    "UKF": {"color": "coral", "fill": "rgba(255, 127, 80, 0.2)"},
}

fig_filters = make_subplots(
    rows=4,
    cols=2,
    shared_xaxes=True,
    subplot_titles=(
        "EKF Radial",
        "UKF Radial",
        "EKF Along-track",
        "UKF Along-track",
        "EKF Cross-track",
        "UKF Cross-track",
        "EKF Total Position Error",
        "UKF Total Position Error",
    ),
    vertical_spacing=0.06,
)


def add_band_and_error(fig, row, col, t_min, sigma, err, style):
    """Add a shaded +/- 3-sigma band with the signed error line drawn over it."""
    fig.add_trace(
        go.Scatter(
            x=t_min,
            y=3 * sigma,
            mode="lines",
            line={"width": 0},
            showlegend=False,
            hoverinfo="skip",
        ),
        row=row,
        col=col,
    )
    fig.add_trace(
        go.Scatter(
            x=t_min,
            y=-3 * sigma,
            mode="lines",
            line={"width": 0},
            fill="tonexty",
            fillcolor=style["fill"],
            showlegend=False,
            hoverinfo="skip",
        ),
        row=row,
        col=col,
    )
    fig.add_trace(
        go.Scatter(
            x=t_min,
            y=err,
            mode="lines",
            line={"color": style["color"], "width": 1.5},
            showlegend=False,
        ),
        row=row,
        col=col,
    )


for col, (name, result) in enumerate((("EKF", ekf_rtn), ("UKF", ukf_rtn)), start=1):
    style = FILTER_STYLES[name]
    add_band_and_error(
        fig_filters, 1, col, result["t"], result["sig_r"], result["err_r"], style
    )
    add_band_and_error(
        fig_filters, 2, col, result["t"], result["sig_t"], result["err_t"], style
    )
    add_band_and_error(
        fig_filters, 3, col, result["t"], result["sig_n"], result["err_n"], style
    )
    fig_filters.add_trace(
        go.Scatter(
            x=result["t"],
            y=result["err_total"],
            mode="lines",
            line={"color": style["color"], "width": 2},
            showlegend=False,
        ),
        row=4,
        col=col,
    )

# Shade pass windows on every row/column
for _, w, _ in passes:
    t0_min = (w.window_open - epoch) / 60.0
    t1_min = (w.window_close - epoch) / 60.0
    for row in (1, 2, 3, 4):
        for col in (1, 2):
            fig_filters.add_vrect(
                x0=t0_min,
                x1=t1_min,
                fillcolor="gray",
                opacity=0.15,
                line_width=0,
                row=row,
                col=col,
            )

for row, label in (
    (1, "Radial (m)"),
    (2, "Along-track (m)"),
    (3, "Cross-track (m)"),
    (4, "Position error (m)"),
):
    fig_filters.update_yaxes(title_text=label, row=row, col=1)
fig_filters.update_xaxes(title_text="Time (minutes)", row=4, col=1)
fig_filters.update_xaxes(title_text="Time (minutes)", row=4, col=2)
fig_filters.update_layout(
    title="EKF / UKF Filter Consistency (RTN)",
    height=1100,
    margin={"l": 60, "r": 40, "t": 80, "b": 60},
)

print("\n" + "=" * 80)
print("Filter Summary")
print("=" * 80)
print(
    f"EKF final position error: {ekf_rtn['err_total'][-1]:.1f} m  "
    f"(3-sigma = {3 * ekf_rtn['sig_total'][-1]:.1f} m)"
)
print(
    f"UKF final position error: {ukf_rtn['err_total'][-1]:.1f} m  "
    f"(3-sigma = {3 * ukf_rtn['sig_total'][-1]:.1f} m)"
)
print("=" * 80)

assert ekf_rtn["err_total"][-1] < 500.0, "EKF should converge to a small position error"
assert ukf_rtn["err_total"][-1] < 500.0, "UKF should converge to a small position error"
print("\nExample validated successfully!")
# --8<-- [end:analyze_results]
# --8<-- [end:all]

# ============================================================================
# Plot Output Section (for documentation generation)
# ============================================================================

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "plots"))
from brahe_theme import save_themed_html

# Save the sensor network ground track as themed HTML
light_path, dark_path = save_themed_html(fig_network, OUTDIR / f"{SCRIPT_NAME}_network")
print(f"\n✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")

# Save the measurement time series as themed HTML
light_path, dark_path = save_themed_html(
    fig_measurements, OUTDIR / f"{SCRIPT_NAME}_measurements"
)
print(f"✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")

# Save the filter comparison figure as themed HTML
light_path, dark_path = save_themed_html(fig_filters, OUTDIR / f"{SCRIPT_NAME}_filters")
print(f"✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")
```

## See Also

- [Estimation](../learn/estimation/index.md)
- [Measurement Models](../learn/estimation/measurement_models.md)
- [Extended Kalman Filter](../learn/estimation/extended_kalman_filter.md)
- [Unscented Kalman Filter](../learn/estimation/unscented_kalman_filter.md)
- [Batch Least Squares](../learn/estimation/batch_least_squares.md)
- [SSN Sensor Datasets](../learn/datasets/ssn_sensors.md)