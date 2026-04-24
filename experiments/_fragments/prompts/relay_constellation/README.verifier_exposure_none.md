# Relay-Network Augmentation Planning Problem

This workspace contains one relay-network planning problem over a fixed mission horizon.

You are given:

- case-wide timing and hard constraints in `case/manifest.json`
- an existing relay backbone and ground endpoints in `case/network.json`
- demanded communication windows between endpoint pairs in `case/demands.json`

Your job is to produce `solution.json` with:

- any additional relay satellites you want to add
- a time-bounded link-activation plan that improves service across the demanded windows

The existing backbone is fixed. This is an augmentation problem, not a greenfield redesign.

No local verifier helper is available in this workspace. Use this README as the validation contract while you work.

## Expected Output

Write one JSON object named `solution.json` at the workspace root.

It should contain two top-level arrays:

- `added_satellites`
- `actions`

Each added satellite entry defines one solver-chosen initial state with:

- `satellite_id`
- `x_m`
- `y_m`
- `z_m`
- `vx_m_s`
- `vy_m_s`
- `vz_m_s`

Each action should activate one physical link interval with:

- `action_type`
- `start_time`
- `end_time`

For ground links, also include:

- `endpoint_id`
- `satellite_id`

For inter-satellite links, also include:

- `satellite_id_1`
- `satellite_id_2`

Do not submit end-to-end routes, latency claims, or service claims. Routing and service are derived from the active physical-link schedule.

## Modeling Contract

Use SI units, degrees, and timezone-aware ISO 8601 timestamps. Let `H0 = manifest.json.horizon_start`, `H1 = manifest.json.horizon_end`, and `dt = manifest.json.routing_step_s`.

Action intervals and demanded windows are sampled on this grid:

```text
sample_index(t) = (t - H0) / dt
```

An action covers integer samples `start_index, ..., end_index - 1`, so:

```text
H0 <= start_time < end_time <= H1
start_index and end_index are integers
```

Backbone satellites in `case/network.json.backbone_satellites` are immutable GCRF Cartesian states at `manifest.json.epoch`. Entries in `added_satellites` use the same frame and units. Added `satellite_id` values must be unique, must not collide with backbone IDs, and `len(added_satellites) <= manifest.json.constraints.max_added_satellites`.

For each added satellite, orbit validity is derived from `x_m`, `y_m`, `z_m`, `vx_m_s`, `vy_m_s`, and `vz_m_s`. With position norm `r`, speed `v`, Earth parameter `mu`, specific energy `epsilon = 0.5 * v^2 - mu / r`, semi-major axis `a = -mu / (2 * epsilon)`, eccentricity `e`, and inclination `i`, hard constraints are:

```text
epsilon < 0
0 <= e < 1
min_altitude_m <= a * (1 - e) - R_earth
a * (1 + e) - R_earth <= max_altitude_m
e <= max_eccentricity, if present
min_inclination_deg <= i, if present
i <= max_inclination_deg, if present
```

Propagation uses GCRF states from `manifest.json.epoch`, UTC time, deterministic Earth orientation, and a J2-only gravity model. Link geometry is evaluated in Earth-fixed coordinates at each covered routing sample.

Actions activate physical links, not routes. A `ground_link` requires `endpoint_id` from `network.json.ground_endpoints` and any known `satellite_id` from the backbone or added set. An `inter_satellite_link` requires distinct known `satellite_id_1` and `satellite_id_2`. The physical identity of an inter-satellite link is unordered, so `A-B` and `B-A` are the same link. Unsupported `action_type`, unknown endpoints or satellites, off-grid intervals, zero-duration intervals, out-of-horizon intervals, and overlapping intervals on the same physical link are invalid.

At every covered sample, a `ground_link` is feasible only if the endpoint-to-satellite elevation is at least the endpoint's `min_elevation_deg`; if `constraints.max_ground_range_m` exists, slant range must also be no greater than that value. An `inter_satellite_link` is feasible only if satellite separation is no greater than `constraints.max_isl_range_m` and the straight segment between satellites is clear of Earth. The feasible link distance at that sample is retained for routing latency.

At each routing sample, active feasible links must also satisfy:

```text
active links incident to any satellite <= max_links_per_satellite
active links incident to any ground endpoint <= max_links_per_endpoint
```

Ground endpoints are terminal endpoints only. In a route for one demand, a ground endpoint may appear only as that demand's source or destination, never as an intermediate transit node.

## Validation Pseudocode

Use this as a practical approximation of how `solution.json` is checked.

```text
load manifest, network, demands, and solution
known_satellites = backbone_satellites + added_satellites

validate added satellites:
  reject duplicate IDs or IDs colliding with the backbone
  reject if more than max_added_satellites are added
  for each added state:
    compute specific energy, semi-major axis, eccentricity, inclination
    reject unbound, open, degenerate, too-low, too-high, or inclination-violating orbits

validate schedule syntax:
  for each action:
    normalize its physical link key
    convert start_time and end_time to routing-grid indices
    reject unknown endpoints, unknown satellites, same-satellite ISLs,
           off-grid times, zero duration, out-of-horizon intervals,
           or overlapping intervals on the same physical link

build reduced timeline:
  demand samples come from every demanded window
  action samples come from every submitted action interval
  propagate only satellites referenced by actions

for each action sample:
  propagate referenced satellites from the common epoch with J2 gravity
  convert positions to Earth-fixed coordinates
  for each active ground_link:
    compute endpoint-relative elevation and slant range
    reject if elevation is too low or ground range is too large
  for each active inter_satellite_link:
    compute satellite separation
    reject if range is too large or Earth intersects the line segment
  reject if any satellite or endpoint has too many simultaneous active links

for each demand sample:
  build an undirected graph from active feasible links
  edge length is the physical link distance at that sample
  endpoints may only be the source or destination of their own demand route
  if one demand is active:
    serve it with the shortest feasible path, if one exists
  if multiple demands are active:
    choose non-overlapping paths that maximize total demand weight
    break ties by lower total latency
    break remaining ties deterministically by route ordering

compute metrics:
  demand_service_fraction = served_samples / requested_samples
  service_fraction = weighted mean of demand_service_fraction
  worst_demand_service_fraction = minimum demand_service_fraction
  latency_ms = 1000 * path_length_m / 299792458 for served samples
  mean_latency_ms and latency_p95_ms are null if no samples are served
```

Numerical comparisons use a small tolerance around exact boundaries. Avoid designs that rely on being exactly at range, elevation, altitude, inclination, or time-grid limits.

## What Good Solutions Do

A strong solution should:

- satisfy all hard validity rules
- serve as much demanded communication as possible
- avoid starving the worst-served demand
- reduce path latency when multiple service patterns are feasible
- avoid adding unnecessary satellites once service quality is already strong

In practical terms, valid service comes first, then robustness across demands, then latency, then augmentation efficiency.
