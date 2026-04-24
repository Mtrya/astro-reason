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

The modeled decision is: add a limited number of relay satellites and choose when physical links are active. You do not submit routes, per-demand service assignments, or latency calculations. Instead, the validator builds a time-varying communication graph from your active links and then computes how much demand can actually be served through that graph.

## What Good Solutions Do

A strong solution should:

- satisfy all hard validity rules
- serve as much demanded communication as possible
- avoid starving the worst-served demand
- reduce path latency when multiple service patterns are feasible
- avoid adding unnecessary satellites once service quality is already strong

In practical terms, valid service comes first, then robustness across demands, then latency, then augmentation efficiency.

## Files In This Workspace

- `case/manifest.json`: mission horizon, routing step, and hard orbit/link constraints
- `case/network.json`: immutable backbone satellites and ground endpoints
- `case/demands.json`: demanded communication windows with weights
- `{example_solution_name}`: example output shape when present
- `{verifier_location}`: local validation helper when present

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

Do not submit end-to-end routes, latency claims, or service claims. Routing and service are derived during validation.

## Modeling Contract

Use SI units, degrees, and timezone-aware ISO 8601 timestamps. Let `H0 = manifest.json.horizon_start`, `H1 = manifest.json.horizon_end`, and `dt = manifest.json.routing_step_s`. Link actions and demanded windows are grid sampled:

```text
sample_index(t) = (t - H0) / dt
```

`start_time` and `end_time` must land exactly on this grid, and an action covers integer samples `start_index, ..., end_index - 1`. Therefore:

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

Service is sampled on the same routing grid. For each demanded window in `case/demands.json.demanded_windows`, requested samples are `start_index, ..., end_index - 1`. A demand sample is served if the active feasible graph contains an allocated path from `source_endpoint_id` to `destination_endpoint_id`. Do not submit routes, service assignments, or latency claims.

Each active physical link has unit capacity per sample and can be allocated to at most one demand route. With one active demand, the chosen path is the shortest feasible path. With multiple active demands, allocation maximizes total served demand `weight`, then minimizes total latency, then uses deterministic path ordering as a tie-breaker. For a served sample:

```text
latency_ms = 1000 * total_path_length_m / 299792458
```

Unserved samples reduce service fractions but do not add artificial latency.

For each demand:

```text
demand_service_fraction = served_sample_count / requested_sample_count
```

Reported metrics are:

```text
service_fraction = sum(weight * demand_service_fraction) / sum(weight)
worst_demand_service_fraction = min(demand_service_fraction over demands)
mean_latency_ms = mean latency over served samples, or null if none are served
latency_p95_ms = 95th percentile latency over served samples, or null if none are served
num_added_satellites = len(added_satellites)
```

Validity is required before service metrics are meaningful. Residual ambiguity is limited to numerical orbit/link geometry at hard boundaries; check close range, elevation, and Earth-blockage cases with the local helper.

## Validation Notes

If the workspace exposes a verifier helper, use it for local iteration:

- `{verifier_command}`

Treat it as a local correctness check while you refine `solution.json`.
