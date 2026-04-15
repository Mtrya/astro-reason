# Relay Constellation Benchmark

## Status

This benchmark is implemented and is the canonical relay-network augmentation benchmark in this repository.

It replaces the earlier `latency_optimization` benchmark story.

## Problem Summary

`relay_constellation` is a partial constellation-design benchmark for relay service.

For each case, the space agent receives:

- a fixed 96-hour planning horizon
- an immutable MEO relay backbone expressed as Cartesian initial states
- fixed ground communication endpoints
- demanded communication windows between endpoint pairs
- case-specific orbit and communication constraints

The space agent must return:

- a bounded set of additional relay satellites
- a time-bounded contact plan that activates communication links

The benchmark is augmentation-focused, not greenfield redesign. Existing backbone satellites are immutable. The intended augmentation story is
LEO-first: the solver adds lower-altitude relays to improve service and reduce latency relative to the provided MEO baseline.

Out of scope:

- sensing or imaging
- onboard power or storage modeling
- attitude or antenna steering dynamics
- queueing and buffering
- stochastic link outages
- solver-authored routing claims

## Dataset Layout

The canonical dataset lives under:

```text
dataset/
├── example_solution.json
├── index.json
└── cases/
    └── <split>/
        └── <case_id>/
            ├── manifest.json
            ├── network.json
            └── demands.json
```

`dataset/example_solution.json` is one real solution object with the same schema as normal submissions. `dataset/index.json` records case metadata and the smoke pairing through split-relative `example_smoke_case`, and the committed split construction lives in `benchmarks/relay_constellation/splits.yaml`.

## Case Inputs

Each case directory contains exactly three machine-readable files.

### `manifest.json`

`manifest.json` defines the planning horizon, propagation model, routing step, and hard case constraints.

Important fields:

- `case_id`
- `epoch`
- `horizon_start`
- `horizon_end`
- `routing_step_s`
- `constraints`
  - `max_added_satellites`
  - `min_altitude_m`
  - `max_altitude_m`
  - `max_eccentricity`
  - `min_inclination_deg`
  - `max_inclination_deg`
  - `max_isl_range_m`
  - `max_links_per_satellite`
  - `max_links_per_endpoint`
  - optional `max_ground_range_m`

### `network.json`

`network.json` contains the immutable relay backbone and ground endpoints.

- `backbone_satellites[]`
  - `satellite_id`
  - `x_m`
  - `y_m`
  - `z_m`
  - `vx_m_s`
  - `vy_m_s`
  - `vz_m_s`
- `ground_endpoints[]`
  - `endpoint_id`
  - `latitude_deg`
  - `longitude_deg`
  - `altitude_m`
  - `min_elevation_deg`

All satellite states are interpreted as GCRF Cartesian states at the case epoch.

### `demands.json`

`demands.json` contains the demanded communication windows.

- `demanded_windows[]`
  - `demand_id`
  - `source_endpoint_id`
  - `destination_endpoint_id`
  - `start_time`
  - `end_time`
  - `weight`

Each record describes one demanded window for one endpoint pair.

## Solution Contract

A valid submission is one JSON object with two top-level arrays:

- `added_satellites`
- `actions`

### `added_satellites`

Each added satellite uses the same Cartesian state contract as the backbone:

- `satellite_id`
- `x_m`
- `y_m`
- `z_m`
- `vx_m_s`
- `vy_m_s`
- `vz_m_s`

The verifier derives orbit properties internally and rejects added states that violate the case constraints.

### `actions`

The solver submits only interval-based link activations. Supported action types are:

- `ground_link`
- `inter_satellite_link`

Shared fields:

- `action_type`
- `start_time`
- `end_time`

`ground_link` also requires:

- `endpoint_id`
- `satellite_id`

`inter_satellite_link` also requires:

- `satellite_id_1`
- `satellite_id_2`

The solver does not submit end-to-end routes, latency claims, or demand-service claims.

## Validity Rules

The verifier rejects a solution if any hard constraint is violated, including:

- malformed case or solution structure
- duplicate or colliding added satellite IDs
- more added satellites than the case allows
- unbound or out-of-band added orbits
- unknown endpoint or satellite references
- unsupported action types
- zero-duration, off-grid, or out-of-horizon actions
- overlapping actions on the same physical link
- geometrically infeasible ground links
- geometrically infeasible inter-satellite links
- per-sample violations of `max_links_per_satellite`
- per-sample violations of `max_links_per_endpoint`

Intermediate ground endpoints are not legal transit nodes in routed service. Only the demand source and demand destination may appear as ground endpoints in the selected route.

## Routing, Service, And Latency

At each verifier-owned sample instant inside a demanded window, a demand is served if there exists a physically feasible multihop path from source to destination through the backbone plus solver-added satellites using only the currently active scheduled links.

The verifier owns routing and allocation:

- it builds the active communication graph from validated actions
- it allocates routes under unit-capacity edge usage
- it chooses routes deterministically

Ranking intent inside a sample:

1. maximize total served demand weight
2. minimize total latency across served demands
3. break remaining ties deterministically

Latency is computed only for served demand-samples:

```text
latency_ms = 1000 * total_path_length_m / c
```

Unserved time reduces service fraction but does not contribute synthetic or infinite latency.

## Metrics And Ranking

The verifier reports:

- `service_fraction`
- `worst_demand_service_fraction`
- `mean_latency_ms`
- `latency_p95_ms`
- `num_added_satellites`
- `num_demanded_windows`
- `num_backbone_satellites`
- `per_demand`
  - `requested_sample_count`
  - `served_sample_count`
  - `service_fraction`
  - `mean_latency_ms`
  - `latency_p95_ms`

Intended ranking order:

1. valid solutions beat invalid solutions
2. maximize `service_fraction`
3. maximize `worst_demand_service_fraction`
4. minimize `latency_p95_ms`
5. minimize `mean_latency_ms`
6. minimize `num_added_satellites`

## Propagation And Link Model

The verifier uses one pinned astrodynamics stack:

- `brahe.NumericalOrbitPropagator`
- J2-only gravity
- GCRF for inertial states
- ITRF/ECEF for geometry checks
- zero-valued static EOP provider for deterministic offline verification

Link feasibility:

- ground links:
  - endpoint elevation above `min_elevation_deg`
  - optional slant-range limit through `max_ground_range_m`
- inter-satellite links:
  - Euclidean separation within `max_isl_range_m`
  - line of sight not Earth-blocked

The verifier separates geometry from topology:

- first it validates action geometry and stores per-sample edge distances
- then it builds temporal graphs and scores service and latency from those validated edges

## Public Entrypoints

Generator:

```bash
uv run python -m benchmarks.relay_constellation.generator.run \
  benchmarks/relay_constellation/splits.yaml
```

Optional dataset output override:

```bash
uv run python -m benchmarks.relay_constellation.generator.run \
  benchmarks/relay_constellation/splits.yaml \
  --output-dir /tmp/relay_constellation_dataset
```

Verifier:

```bash
uv run python -m benchmarks.relay_constellation.verifier.run \
  benchmarks/relay_constellation/dataset/cases/test/case_0005 \
  benchmarks/relay_constellation/dataset/example_solution.json
```

Visualizer:

```bash
uv run python -m benchmarks.relay_constellation.visualizer.run overview \
  --case-dir benchmarks/relay_constellation/dataset/cases/test/case_0001
```

```bash
uv run python -m benchmarks.relay_constellation.visualizer.run connectivity \
  --case-dir benchmarks/relay_constellation/dataset/cases/test/case_0001
```

```bash
uv run python -m benchmarks.relay_constellation.visualizer.run solution \
  --case-dir benchmarks/relay_constellation/dataset/cases/test/case_0005 \
  --solution-path benchmarks/relay_constellation/dataset/example_solution.json
```

## Tests

Run the focused relay benchmark tests with:

```bash
uv run pytest tests/benchmarks/test_relay_constellation_generator.py tests/benchmarks/test_relay_constellation_verifier.py
```
