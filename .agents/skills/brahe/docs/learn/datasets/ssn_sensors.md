# SSN Sensor Datasets

## Overview

The SSN sensor dataset provides representative locations, field-of-view limits, and
calibration (bias/noise) values for U.S. Space Surveillance Network sites. This data is
essential for:

- **Simulating radar/optical tracking**: Build `SimpleSSNSensor` instances that generate
  az/el/range measurements consistent with a matching `AzElRangeMeasurementModel`
- **Access analysis**: Determine when a sensor's field of view covers a target orbit
- **Orbit determination testing**: Exercise EKF/UKF/BLS estimators against a realistic,
  multi-site sensor network

Brahe includes embedded GeoJSON data for 21 SSN sites. The data is:

- **Offline-capable**: No network requests required
- **Calibrated**: Includes bias and noise values for sensors with published Table 4-4 entries
- **Wrap-aware**: Azimuth field-of-view windows that cross north are represented correctly

## Loading

Load all SSN sensor sites, filter by sensor type, and inspect a site's properties:


```python
import brahe as bh

# Initialize EOP data
bh.initialize_eop()

# Load all SSN sensor sites
sites = bh.datasets.ssn_sensors.load()
print(f"Total SSN sites: {len(sites)}")

# Filter by sensor type: radar/phased-array/mechanical trackers report
# az/el/range, optical trackers report angles-only az/el
radars = [s for s in sites if s.properties["sensor_type"] == "azel_range"]
optical = [s for s in sites if s.properties["sensor_type"] == "azel"]
print(f"Radar/phased-array/mechanical sites: {len(radars)}")
print(f"Optical (angles-only) sites: {len(optical)}")

# Inspect one site's properties
eglin = next(s for s in sites if s.get_name() == "Eglin")
props = eglin.properties
print(f"\n{eglin.get_name()}")
print(f"Location: ({eglin.lat:.2f}, {eglin.lon:.2f})")
print(f"System: {props['system']}")
print(f"Category: {props['category']}")
print(f"Elevation limits: {props.get('el_min_deg')} - {props.get('el_max_deg')} deg")
print(f"Range max: {props.get('range_max_m') / 1e3:.0f} km")
print(f"Azimuth noise: {props.get('az_noise_deg')} deg")

assert len(sites) == 21
assert len(radars) + len(optical) == len(sites)
assert eglin.properties["sensor_type"] == "azel_range"
print("\nExample validated successfully!")
```


`bh.datasets.ssn_sensors.load()` returns every site as a `PointLocation`.
`SimpleSSNSensor.from_locations()` builds a sensor for every site -- radar (`azel_range`,
measuring az/el/range) and optical (`azel`, angles-only az/el) alike -- defaulting the
sites that lack full Table 4-4 calibration to zero noise and bias (flagged
`calibrated == False`, overridable with `with_noise()`/`with_bias()`).
`from_locations_calibrated()` restricts the result to the fully-calibrated sites -- this is
the set used throughout the [SSN Radar Tracking example](../../examples/ssn_tracking.md).

## Properties

Each site is a `PointLocation` with geodetic coordinates (`lon()`, `lat()`, `alt()`) and a
`properties` dictionary:

| Field | Type | Units | Description |
|-------|------|-------|--------------|
| `sensor_type` | `str` | -- | `"azel_range"` (radar/phased-array/mechanical trackers, az/el/range) or `"azel"` (angles-only optical trackers, az/el) |
| `system` | `str` | -- | Sensor system description, e.g. `"Phased Array"`, `"Radar"`, `"GEODSS"` |
| `category` | `str` | -- | Vallado network category, e.g. `"dedicated"`, `"collateral"`, `"contributing"` |
| `sensor_numbers` | `list[int]` | -- | SSN sensor ID number(s) at the site |
| `az_min_deg` | `float`, optional | degrees | Azimuth field-of-view start. Wrap-aware: when `az_min_deg > az_max_deg`, the window crosses north |
| `az_max_deg` | `float`, optional | degrees | Azimuth field-of-view end |
| `el_min_deg` | `float`, optional | degrees | Minimum elevation angle |
| `el_max_deg` | `float`, optional | degrees | Maximum elevation angle |
| `range_max_m` | `float`, optional | meters | Maximum range; absent means effectively unlimited |
| `az_bias_deg` | `float`, optional | degrees | Constant azimuth measurement bias (Table 4-4) |
| `el_bias_deg` | `float`, optional | degrees | Constant elevation measurement bias |
| `range_bias_m` | `float`, optional | meters | Constant range measurement bias |
| `az_noise_deg` | `float`, optional | degrees | Azimuth measurement noise standard deviation |
| `el_noise_deg` | `float`, optional | degrees | Elevation measurement noise standard deviation |
| `range_noise_m` | `float`, optional | meters | Range measurement noise standard deviation |

`sensor_type` determines which fields are present: `azel` sites carry no range fields at
all, and sites appearing only in Table 4-2 (location and field-of-view, no calibration)
carry no bias/noise fields. `SimpleSSNSensor.from_location()` accepts both `azel_range` and
`azel` sites; a site missing one or more noise fields still constructs, defaulted to zero
noise and flagged uncalibrated, rather than raising an error.

## Building Sensors and Measurement Models

Build a sensor from a single site, generate a measurement, and inspect the matching
`AzElRangeMeasurementModel` that `measurement_model()` builds from the sensor's own bias
and noise -- the model and the sensor stay consistent because both read the same
calibration:


```python
import numpy as np
import brahe as bh

# Initialize EOP data
bh.initialize_eop()

# Load a fully-calibrated radar site and build a sensor from it
sites = bh.datasets.ssn_sensors.load()
eglin_site = next(s for s in sites if s.get_name() == "Eglin")
sensor = bh.SimpleSSNSensor.from_location(eglin_site, seed=42)
print(f"Sensor: {sensor.name}")
print(f"Azimuth window: {sensor.az_min:.1f} - {sensor.az_max:.1f} deg")
print(f"Elevation limits: {sensor.el_min:.1f} - {sensor.el_max:.1f} deg")
print(f"Range max: {sensor.range_max / 1e3:.0f} km")
print(f"Calibrated: {sensor.calibrated}")

# Build the matching measurement model: same bias/noise as the sensor, so a
# filter built from it stays consistent with measurements the sensor produces
model = sensor.measurement_model()
print(f"Measurement model: {model.name()}")

# A target 500 km away, due south (within Eglin's southwest-facing azimuth
# window) and 45 deg above the horizon, built by offsetting the site in the
# local East-North-Zenith frame and converting to ECI.
epoch = bh.Epoch(2024, 1, 1, 0, 0, 0.0)
az, el, rng = np.radians(180.0), np.radians(45.0), 500e3
horizontal = rng * np.cos(el)
enz_offset = np.array(
    [horizontal * np.sin(az), horizontal * np.cos(az), rng * np.sin(el)]
)
target_ecef = bh.relative_position_enz_to_ecef(
    eglin_site.center_ecef(), enz_offset, bh.EllipsoidalConversionType.GEODETIC
)
state_eci = bh.state_ecef_to_eci(epoch, np.concatenate([target_ecef, np.zeros(3)]))

# True (noise-free, bias-free) geometry vs. a simulated measurement
truth = sensor.azelrange(epoch, state_eci)
print(
    f"\nTrue az/el/range: [{truth[0]:.2f} deg, {truth[1]:.2f} deg, {truth[2] / 1e3:.1f} km]"
)

measurement = sensor.measure(epoch, state_eci)
print(
    f"Measured az/el/range: [{measurement[0]:.2f} deg, {measurement[1]:.2f} deg, "
    f"{measurement[2] / 1e3:.1f} km]"
)

assert measurement is not None, "Target inside the field of view should be visible"
assert abs(measurement[0] - truth[0]) < 1.0, "azimuth should stay close to truth"
assert abs(measurement[1] - truth[1]) < 1.0, "elevation should stay close to truth"
assert abs(measurement[2] - truth[2]) < 5000.0, "range should stay close to truth"
print("\nExample validated successfully!")
```


See [Azimuth/Elevation/Range Measurements](../estimation/measurement_models.md#azimuthelevationrange)
for how the resulting model is used in a filter.

## Source

Values are from Vallado, *Fundamentals of Astrodynamics and Applications*, 4th Ed.,
Tables 4-2 (site locations and systems), 4-3 (field-of-view limits), and 4-4 (bias/noise
calibration). NAVSPASUR is excluded from the embedded dataset. These values are
representative and dated -- they reflect the published tables, not current SSN
configuration or performance, and should not be used for operational sensor modeling.

---

## See Also

- [Datasets Overview](index.md) - Understanding datasets in Brahe
- [Measurement Models](../estimation/measurement_models.md) - Azimuth/Elevation/Range measurement model
- [SSN Radar Tracking Example](../../examples/ssn_tracking.md) - Full EKF/UKF/BLS walkthrough
- [SSN Sensor Datasets API Reference](../../library_api/datasets/ssn_sensors.md) - Complete function documentation