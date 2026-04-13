# Relay Constellation SPEC

Status: tracked development spec for the `relay_constellation` benchmark redesign.

This document is a temporary tracked benchmark-development artifact. The
intended end-state is that its stable public content will be absorbed into
[`benchmarks/relay_constellation/README.md`](/home/betelgeuse/Developments/AstroReason-Bench/benchmarks/relay_constellation/README.md)
once the benchmark is finished.

This spec is written with the repository benchmark contract as a hard design
constraint. See
[`docs/benchmark_contract.md`](/home/betelgeuse/Developments/AstroReason-Bench/docs/benchmark_contract.md).

## 1. Purpose

`relay_constellation` is a relay-network augmentation benchmark.

The space agent receives:

- a fixed planning horizon of 96 hours
- an immutable relay backbone expressed as satellite initial states
- a set of fixed ground communication endpoints
- a set of demanded communication windows between endpoint pairs
- case-specific orbital and communication constraints

The space agent must return:

- a bounded set of additional relay satellites that augment the provided
  backbone
- a time-bounded communication contact plan that activates relay links over the
  mission horizon

This redesign intentionally replaces the old `latency_optimization` benchmark
story. The new benchmark is purely relay-service-focused:

- no sensing branch
- no mapping targets
- no onboard resource management
- no attitude dynamics

## 2. Design Goals

The redesign must satisfy the following repository-level goals:

- benchmark-core, not solution-core
- standalone verifier and generator owned by this repository
- algorithm-agnostic public interface
- deterministic and offline-friendly evaluation
- physically meaningful without requiring proprietary mission tools
- hard to game through solver-authored topology claims

## 3. Contract Alignment

The finished benchmark must conform to
[`docs/benchmark_contract.md`](/home/betelgeuse/Developments/AstroReason-Bench/docs/benchmark_contract.md).

The intended finished shape is:

```text
benchmarks/relay_constellation/
├── README.md
├── generator/
│   └── run.py
├── verifier/
│   └── run.py
├── SPEC.md                  # temporary tracked development artifact
└── dataset/
    ├── example_solution.json
    ├── index.json
    └── cases/
        └── case_0001/
            ├── manifest.json
            ├── network.json
            └── demands.json
```

Notes:

- `generator/run.py` is the canonical public generator entrypoint.
- `verifier/run.py` is the canonical public verifier entrypoint.
- The verifier public CLI accepts `case_dir` and `solution_path` as positional
  arguments.
- `dataset/example_solution.json` is a single per-case solution object, not a
  mapping.
- `dataset/index.json` is optional by contract, but this benchmark will provide
  it.
- `SPEC.md` is temporary and should be absorbed into the public README before
  promotion to finished status.

Intended finished-benchmark metadata once promoted:

- `repro_ci: true`
- `generated_paths`:
  - `dataset/cases`
  - `dataset/index.json`
  - `dataset/example_solution.json`

## 4. Benchmark Summary

### 4.1 Core formulation

The canonical formulation is:

- immutable baseline relay backbone provided by the case
- fixed ground endpoints provided by the case
- fixed demanded communication windows provided by the case
- solver-proposed additional satellites
- solver-proposed time-bounded link activations
- verifier-validated communication feasibility and verifier-owned routing
- service-first scoring with latency as a secondary metric

The benchmark does not accept solver-authored:

- routing tables
- latency claims
- demand-service claims

### 4.2 Canonical mission story

The benchmark models partial constellation design, not full greenfield design.

Each case provides an immutable MEO relay backbone with known service gaps. The
solver may add up to a bounded number of additional relay satellites to improve
service and reduce latency.

Existing backbone satellites are immutable. The task is to augment the provided
network, not redesign it from scratch.

The intended augmentation story is LEO-first: the provided MEO layer offers a
stable but imperfect baseline, and the solver adds lower-altitude relays to pad
coverage gaps or improve path length where baseline-only routes are unavailable
or high-latency.

### 4.3 What this benchmark is and is not

In scope:

- constellation augmentation by adding satellites
- benchmark-local J2 propagation
- time-bounded link-activation planning
- line-of-sight link feasibility validation
- end-to-end relay service between endpoint pairs
- latency computed from geometric path length

Out of scope:

- sensing and imaging
- mapping-target coverage
- power or storage modeling
- attitude or antenna steering dynamics
- queueing and data buffering
- stochastic link outages
- solver-authored end-to-end routing schedules

## 5. Mission and Service Abstraction

### 5.1 Service objective

The benchmark evaluates whether communication demands are served over their
requested windows.

Each demand window is defined by:

- a source ground endpoint
- a destination ground endpoint
- a start time
- an end time
- an optional demand weight

At each verifier-owned sample instant inside the window, a demand is considered
served if there exists a physically feasible multihop relay path from source to
destination through the backbone plus solver-added satellites using only the
solver-activated links that are active at that instant.

### 5.2 Availability-first semantics

Primary objective:

- maximize served fraction of the requested windows

Secondary objective:

- minimize served-time latency

Important scoring rule:

- unavailable parts of a demand window reduce service fraction
- unavailable parts do **not** contribute synthetic or infinite latency

This avoids double-penalizing unserved time and keeps the metric semantics
clear:

- service fraction measures how much of the requested window is usable
- latency measures path quality only where service exists

### 5.3 Canonical ranking intent

Deterministic ranking order:

1. `valid = true`
2. maximize global `service_fraction`
3. maximize `worst_demand_service_fraction`
4. minimize `latency_p95_ms`
5. minimize `mean_latency_ms`
6. minimize `num_added_satellites`

The benchmark should not collapse service and latency into one opaque scalar.

## 6. Canonical Physical Abstraction

### 6.1 Propagation and frames

The verifier uses one pinned astrodynamics stack consistently, following the
frame guidance in
[`docs/benchmark_contract.md`](/home/betelgeuse/Developments/AstroReason-Bench/docs/benchmark_contract.md):

- benchmark-local initial Cartesian states, not TLEs
- `brahe.NumericalOrbitPropagator`
- J2-only gravity model
- GCRF as the inertial frame
- ITRF as the Earth-fixed frame
- zero-valued static EOP provider for deterministic offline verification

The canonical benchmark explicitly does **not** use SGP4 or frozen TLEs for
propagation.

### 6.2 State representation

Both case-provided backbone satellites and solver-added satellites use the same
representation:

- `x_m`
- `y_m`
- `z_m`
- `vx_m_s`
- `vy_m_s`
- `vz_m_s`

All states are interpreted as GCRF Cartesian states at the case epoch.

This is intentionally aligned with the existing public design pattern in
`revisit_constellation`.

### 6.3 Orbit validity

The verifier derives osculating orbit properties from each state and rejects any
added satellite whose state violates case constraints.

Canonical hard checks:

- bound orbit (`specific_orbital_energy < 0`)
- perigee altitude above `min_altitude_m`
- apogee altitude below `max_altitude_m`
- derived inclination within the allowed case band if one is provided
- eccentricity within the allowed case band if one is provided

The benchmark does not require the solver to output orbital elements. The
verifier may derive them internally for validation and diagnostics.

## 7. Node and Link Model

### 7.1 Ground endpoints

Ground endpoints are static geodetic points on Earth.

Each endpoint includes:

- `endpoint_id`
- `latitude_deg`
- `longitude_deg`
- `altitude_m`
- `min_elevation_deg`

Canonical public cases support only ground-to-ground communication demands.

### 7.2 Link types

The verifier models two kinds of communication links:

- ground-to-satellite links
- inter-satellite links

Both link types are scheduled by the solver as time-bounded actions. The
verifier validates whether each scheduled link remains geometrically feasible
throughout its scheduled interval.

### 7.3 Ground-to-satellite feasibility

A ground-to-satellite link is feasible at time `t` when:

- the satellite is above the endpoint's local elevation mask:
  - `elevation_deg >= min_elevation_deg`
- the line of sight is not Earth-blocked
- optional `max_ground_range_m` is satisfied if the case specifies one

### 7.4 Inter-satellite feasibility

An inter-satellite link is feasible at time `t` when:

- the straight line segment between the two satellites is not Earth-blocked
- the separation is within `max_isl_range_m`

The canonical public release should use a simple line-of-sight plus range model.
It should not introduce antenna steering, Doppler, or link-budget submodels.

### 7.5 Link concurrency

Canonical cases may specify:

- `max_links_per_satellite`
- `max_links_per_endpoint`

Interpretation:

- at any sampled instant, a satellite may participate in at most that many
  active scheduled communication links
- at any sampled instant, a ground endpoint may participate in at most that
  many active scheduled ground-to-satellite links

This is the intended simple concurrency cap for the benchmark. It is included to
avoid unrealistic fully-connected relay behavior without introducing full
attitude or power modeling.

### 7.6 Per-sample link allocation semantics

At a verifier sample instant, each active scheduled link action creates exactly
one usable communication edge in the sampled network.

The canonical v1 benchmark uses unit-capacity edges:

- one active `ground_link` action may be allocated to at most one served demand
  at that sample instant
- one active `inter_satellite_link` action may be allocated to at most one
  served demand at that sample instant
- one served demand consumes one unit of capacity on every active action along
  its selected path at that sample instant

This benchmark intentionally models binary per-sample link occupancy rather than
bandwidth or queueing. That keeps contention meaningful without introducing a
full traffic-engineering submodel.

## 8. Routing and Service Semantics

### 8.1 Solver-owned contact plan, verifier-owned routing

The solver owns:

- added satellites
- time-bounded link-activation actions

The verifier owns:

- link registration
- time-sampled communication graph construction
- path selection
- service determination
- latency computation

The solver does not submit end-to-end routes or demand assignments.

### 8.2 Sampled service model

The verifier samples the horizon at a fixed case-defined interval:

- `routing_step_s`

For an action on the interval `[start_time, end_time)`, the verifier checks the
sample instants:

```text
start_time, start_time + routing_step_s, ..., < end_time
```

This sampled interpretation is the canonical public contract for v1. The
verifier does not attempt continuous-time root finding between sample instants.

At each sample instant:

1. propagate all satellites to the sample time
2. determine which scheduled link actions are active
3. validate active scheduled links against the physical feasibility rules
4. invalidate the solution immediately if any active scheduled link violates the
   action contract
5. construct the active communication graph from the scheduled links
   that are active at that instant
6. determine which active demands are served
7. compute the latency of the selected path for each served demand

The benchmark models immediate end-to-end service over simultaneously available
links. It does not model store-and-forward buffering across time.

### 8.3 Scheduled topology interpretation

The action list is interpreted as an interval-based topology plan.

This is intentionally more expressive than a static provisioned topology and
more readable than a per-sample adjacency matrix:

- the solver chooses when a candidate ground-to-satellite or inter-satellite
  link should be active
- the verifier checks whether the action is physically feasible over its full
  scheduled interval
- a demand may only use links that are both solver-scheduled and verifier-valid

The result is equivalent to a sampled topology plan at the verifier time step,
but the public contract remains interval-based and readable for space agents.

### 8.4 Demand service under contention

When multiple demands are active at the same sample instant, the verifier
selects a deterministic feasible set of served demands subject to the link
feasibility rules, the per-satellite and per-endpoint link caps, and the
unit-capacity rule for each active scheduled action.

Canonical optimization intent at one sample instant:

1. maximize the total active demand weight served
2. break ties by minimizing total latency across the served demands

The implementation may use any deterministic exact method suitable for the small
canonical case sizes.

In other words, two demands may not share the same active scheduled action at
the same sample instant, even if the geometry would permit both routes.

## 9. Metrics

### 9.1 Per-demand metrics

For each demand `d`, let its sampled time set be `K_d`.

Define:

- `served(d, k) = 1` if demand `d` is served at sample `k`, else `0`
- `latency_ms(d, k)` only for served samples

For a served demand-sample, end-to-end latency is:

```text
latency_ms(d, k) = 1000 * total_path_length_m(d, k) / c_m_s
```

where `total_path_length_m(d, k)` is the sum of Euclidean edge lengths along
the verifier-selected path at sample `k`, and `c_m_s = 299792458.0`.

Then:

```text
service_fraction_d = sum_k served(d, k) / |K_d|
```

Latency summaries for a demand are computed only over the served samples:

- `mean_latency_ms_d`
- `latency_p95_ms_d`

If a demand has zero served samples, its latency fields are `null`.

### 9.2 Global metrics

Let `w_d` be the demand weight, defaulting to `1.0`.

Primary global metric:

```text
service_fraction =
    sum_d(w_d * service_fraction_d) / sum_d(w_d)
```

Fairness-like secondary service metric:

```text
worst_demand_service_fraction = min_d(service_fraction_d)
```

Latency summaries:

- `mean_latency_ms`
- `latency_p95_ms`

These latency summaries are computed over the pooled served demand-samples only.
Unserved samples do not contribute artificial latency.

Additional reporting metrics:

- `num_added_satellites`
- `num_demanded_windows`
- `num_backbone_satellites`

## 10. Solution Contract

### 10.1 Solution file shape

The canonical solution is a single JSON object:

```json
{
  "added_satellites": [
    {
      "satellite_id": "added_001",
      "x_m": 6878137.0,
      "y_m": 0.0,
      "z_m": 0.0,
      "vx_m_s": 0.0,
      "vy_m_s": 7612.608,
      "vz_m_s": 0.0
    }
  ],
  "actions": [
    {
      "action_type": "ground_link",
      "endpoint_id": "ground_a",
      "satellite_id": "backbone_001",
      "start_time": "2026-01-01T01:00:00Z",
      "end_time": "2026-01-01T01:30:00Z"
    },
    {
      "action_type": "inter_satellite_link",
      "satellite_id_1": "backbone_001",
      "satellite_id_2": "added_001",
      "start_time": "2026-01-01T01:00:00Z",
      "end_time": "2026-01-01T01:30:00Z"
    }
  ]
}
```

The dataset-level example solution is:

```json
{
  "added_satellites": [],
  "actions": []
}
```

### 10.2 Added satellite fields

Each solver-added satellite entry includes:

- `satellite_id`
- `x_m`
- `y_m`
- `z_m`
- `vx_m_s`
- `vy_m_s`
- `vz_m_s`

### 10.3 Action fields

The solution `actions` list is an interval-based contact plan.

Supported action types are:

- `ground_link`
- `inter_satellite_link`

Each action includes:

- `action_type`
- `start_time`
- `end_time`

`ground_link` actions also include:

- `endpoint_id`
- `satellite_id`

The `satellite_id` in a `ground_link` action may reference either a
case-provided backbone satellite or a solver-added satellite.

`inter_satellite_link` actions also include:

- `satellite_id_1`
- `satellite_id_2`

An `inter_satellite_link` action may connect any two distinct satellites in the
combined network, including backbone-backbone, backbone-added, or added-added
pairs.

Action timing is interpreted on a closed-open interval:

```text
[start_time, end_time)
```

Canonical timing rules:

- `start_time` and `end_time` must lie on the case `routing_step_s` grid
- `end_time > start_time`
- actions must lie fully within the horizon
- zero-duration actions are invalid

### 10.4 Hard validity rules for actions

The verifier rejects a solution if any action violates any of the following:

- malformed action structure
- unknown endpoint or satellite reference
- `inter_satellite_link` uses the same satellite on both ends
- action times are off-grid or outside the horizon
- scheduled geometry is infeasible at any verifier sample inside the action
- duplicate or overlapping actions for the same unordered link are present
- per-satellite or per-endpoint concurrency caps are exceeded

The solver does not submit end-to-end routes or latency claims.

### 10.5 Additional hard validity rules

The verifier rejects a solution if any of the following hold:

- malformed solution structure
- duplicate added `satellite_id`
- `satellite_id` collides with a backbone satellite ID
- more than `max_added_satellites` satellites are proposed
- any added state violates orbit validity constraints

The benchmark does not require the solver to use the full allowed satellite
budget.

## 11. Case File Contract

### 11.1 `manifest.json`

`manifest.json` holds case-level metadata and verifier configuration:

- `case_id`
- `benchmark`
- `seed`
- `epoch`
- `horizon_start`
- `horizon_end`
- `routing_step_s`
- `propagation`
- `constraints`
- `scoring`

Canonical logical shape:

```json
{
  "case_id": "case_0001",
  "benchmark": "relay_constellation",
  "seed": 42,
  "epoch": "2026-01-01T00:00:00Z",
  "horizon_start": "2026-01-01T00:00:00Z",
  "horizon_end": "2026-01-05T00:00:00Z",
  "routing_step_s": 60,
  "propagation": {
    "model": "j2",
    "frame": "gcrf",
    "earth_fixed_frame": "itrf"
  },
  "constraints": {
    "max_added_satellites": 6,
    "min_altitude_m": 500000.0,
    "max_altitude_m": 1500000.0,
    "max_eccentricity": 0.02,
    "min_inclination_deg": 20.0,
    "max_inclination_deg": 85.0,
    "max_isl_range_m": 6000000.0,
    "max_links_per_satellite": 3,
    "max_links_per_endpoint": 1
  },
  "scoring": {
    "primary_metric": "service_fraction",
    "secondary_metric": "latency_p95_ms"
  }
}
```

The numeric values shown above are illustrative of the intended added-satellite
regime only. They are not yet frozen canonical release values and should be
treated as tuning targets during generator calibration.

### 11.2 `network.json`

`network.json` contains the immutable network assets:

- `backbone_satellites`
- `ground_endpoints`

The v1 case format does not include pre-provisioned relay links. All
communication links become usable only through solver-authored actions that are
then verified against geometry.

In the intended canonical story, `backbone_satellites` represent the provided
MEO relay layer. The orbital constraints in `manifest.json` apply to
solver-added augmentation satellites, not to the immutable backbone.

Canonical logical shape:

```json
{
  "backbone_satellites": [
    {
      "satellite_id": "backbone_001",
      "x_m": 6878137.0,
      "y_m": 0.0,
      "z_m": 0.0,
      "vx_m_s": 0.0,
      "vy_m_s": 7612.608,
      "vz_m_s": 0.0
    }
  ],
  "ground_endpoints": [
    {
      "endpoint_id": "ground_a",
      "latitude_deg": 40.7128,
      "longitude_deg": -74.0060,
      "altitude_m": 0.0,
      "min_elevation_deg": 10.0
    }
  ]
}
```

### 11.3 `demands.json`

`demands.json` contains the demanded communication windows:

- `demanded_windows`

Canonical logical shape:

```json
{
  "demanded_windows": [
    {
      "demand_id": "demand_001",
      "source_endpoint_id": "ground_a",
      "destination_endpoint_id": "ground_b",
      "start_time": "2026-01-01T01:00:00Z",
      "end_time": "2026-01-01T03:00:00Z",
      "weight": 1.0
    }
  ]
}
```

Each demanded-window record describes one service window. Repeated windows for
the same endpoint pair are represented as separate records.

### 11.4 `dataset/index.json`

The benchmark will provide `dataset/index.json` and use it as dataset metadata,
not as a second source of truth for benchmark completion.

Canonical logical shape:

```json
{
  "benchmark": "relay_constellation",
  "generator_seed": 42,
  "example_smoke_case_id": "case_0001",
  "cases": [
    {
      "case_id": "case_0001",
      "path": "cases/case_0001",
      "horizon_hours": 96,
      "num_backbone_satellites": 6,
      "num_ground_endpoints": 4,
      "num_demanded_windows": 6,
      "num_endpoint_pairs": 3,
      "max_added_satellites": 6
    }
  ]
}
```

## 12. Verifier Semantics

### 12.1 Verifier ownership

The verifier owns:

- propagation
- frame conversion
- orbit validity checks
- action feasibility validation
- active-graph construction from scheduled link actions
- routing and demand service selection
- metric computation

The solver owns only the added satellites and the link-activation actions.

### 12.2 Output schema

Canonical logical shape:

```json
{
  "valid": true,
  "metrics": {
    "service_fraction": 0.0,
    "worst_demand_service_fraction": 0.0,
    "mean_latency_ms": null,
    "latency_p95_ms": null,
    "num_added_satellites": 0,
    "num_demanded_windows": 0,
    "num_backbone_satellites": 0,
    "per_demand": {}
  },
  "violations": [],
  "diagnostics": {}
}
```

Frozen top-level fields:

- `valid`
- `metrics`
- `violations`
- `diagnostics`

### 12.3 Diagnostics

Expected diagnostics should include at least:

- derived orbit summaries for added satellites
- action-validity summary counts
- link-feasibility summary counts
- per-sample demand-allocation summary counts
- per-demand served sample counts
- optional route-debug summaries for sampled instants

## 13. Generator Requirements

The generator must:

- build canonical cases under `dataset/cases/`
- write `dataset/example_solution.json`
- write `dataset/index.json`
- sample cases algorithmically from a seed, not from hand-maintained case tables
- generate immutable backbones with known service gaps
- keep canonical cases small enough for deterministic verifier routing
- generate endpoint and demand-window layouts that exercise link-concurrency
  tradeoffs

The generator must not:

- write solver-authored route hints
- require external proprietary constellation tools
- preserve any sensing or mapping-target branch from `latency_optimization`

### 13.1 Recommended canonical release target

The first canonical public release should target:

- 5 canonical cases
- one canonical dataset split only
- one dataset-level `example_solution.json`

### 13.2 Recommended case-family ranges

Recommended release targets:

- horizon per case: fixed at `96 h` in the canonical public release
- immutable MEO backbone satellites: likely a modest fixed set rather than a
  dense mesh, but the exact count is intentionally left to tuning
- allowed additions per case: likely single-digit, for example `4` to `8`, but
  this is intentionally left to tuning
- ground endpoints per case: `4` to `6`
- endpoint pairs: `2` to `5`
- demanded windows per case: `4` to `8`
- `routing_step_s`: `60`
- added-satellite altitude band: expected to be LEO, with exact bounds left to
  tuning
- added-satellite eccentricity cap: near-circular, with exact bounds left to
  tuning
- added-satellite inclination band: expected to avoid both backbone copies and
  implausibly polar-heavy defaults, with exact bounds left to tuning
- `max_isl_range_m`: expected to be materially larger than the old low-orbit
  shell setting because the immutable backbone is now MEO, but the exact bound
  is intentionally left to tuning
- `max_links_per_satellite`: `3`
- `max_links_per_endpoint`: `1`

These are generator-side guidance bands, not promises that every final case
uses the entire range.

### 13.3 Recommended endpoint, demand, and backbone sampling

The first canonical generator should use structured sampling, not arbitrary
worldwide randomization.

Recommended endpoint policy:

- sample from a curated library of roughly `24` to `40` realistic ground sites
- select `4` to `6` endpoints per case
- enforce a minimum pairwise separation of roughly `15 deg`

Recommended demand-window policy:

- sample `2` to `5` endpoint pairs per case
- assign `1` to `2` windows per selected pair
- quantize window starts to a `5 min` grid
- draw window durations from a discrete mix:
  - short: `30` to `60 min`
  - medium: `60` to `120 min`
  - long: `120` to `180 min`
- bias the mix toward medium windows
- default all demand weights to `1.0` in the first canonical release
- write `weight` explicitly in canonical demand records, even when it is `1.0`

Recommended calibration goals for Phase 02 inspection:

- the immutable backbone alone should achieve neither almost zero nor almost
  complete service once inspected with the case visualizer
- the canonical set should trend toward a baseline weighted `service_fraction`
  band of roughly `0.2` to `0.8`
- cases should include at least one interval with overlapping active demands
- the demand set should include at least one demand whose baseline service
  appears materially improvable
- the immutable MEO layer alone should often provide partial service but leave
  clear availability or latency improvement headroom for added lower-altitude
  relays

Recommended backbone policy:

- use a generator-owned MEO-like backbone rather than importing a real
  operational constellation
- use one homogeneous relay-satellite communication model in the first release
- use a small immutable MEO constellation, likely across multiple planes, but
  treat the count, altitude, and inclination choices as tuning parameters
  rather than fixed commitments
- keep the public case format in Cartesian initial states even if the generator
  samples higher-level backbone parameters internally
- treat the solver-added layer as a separate augmentation regime with its own
  orbital-constraint band, expected to be LEO-like in the first release

## 14. Tests and Fixtures

The redesign must add focused tests under `tests/benchmarks/` and case-local
fixtures under `tests/fixtures/`.

Minimum test categories:

- parser / schema validation
- duplicate or invalid satellite-state rejection
- max-added-satellite rejection
- orbit-validity rejection
- action time-grid and interval validation
- concurrency-cap regression
- scheduled-link geometry validation
- ground-link visibility regression
- ISL visibility / Earth-occultation regression
- deterministic per-demand service regression
- served-time-only latency regression
- example-solution smoke case

Fixture philosophy:

- small exact cases with one or two backbone satellites and a tiny number of
  endpoints and demands
- deterministic known-service and no-service intervals
- exact assertions on service fraction and latency for tiny synthetic cases

## 15. Migration from `latency_optimization`

This redesign intentionally replaces the legacy benchmark story found in
`latency_optimization`.

The new benchmark removes:

- the sensing / observation branch
- mapping-target coverage metrics
- `engines.astrox` verifier dependency
- the old case vocabulary of `requirements.yaml`, `targets.yaml`, and
  planner-authored compatibility layers

The benchmark-core replacement path should follow the newer standalone pattern
used by `revisit_constellation`, `stereo_imaging`, and `regional_coverage`.
