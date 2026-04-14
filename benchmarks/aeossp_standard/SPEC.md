# AEOSSP Standard SPEC

Status: tracked development spec for the `aeossp_standard` benchmark.

This document is a benchmark-development artifact. Its stable public substance
should later be absorbed into `benchmarks/aeossp_standard/README.md` once the
benchmark is implemented and promoted to finished status.

`aeossp_standard` is a planning-oriented Agile Earth Observation Satellite
Scheduling Problem benchmark grounded in standard AEOSSP formulations and
informed by AEOS-Bench, but it is not intended to be a numerical reproduction
of any single prior benchmark.

## 1. Purpose

`aeossp_standard` is the repository's canonical benchmark for standard
Earth-observation scheduling under realistic-but-benchmark-practical orbital,
attitude, and power constraints.

For each case, the space agent receives:

- a fixed 12-hour planning horizon
- a fixed constellation of real Earth-observation satellites expressed through
  frozen TLEs and benchmark-local subsystem parameters
- a set of time-windowed point-imaging tasks
- hard observation, resource, and agility constraints

The space agent must return:

- an event-based schedule of observation actions

The benchmark is scheduling-focused, not constellation-design-focused. The
solver does not add satellites, choose orbits, or redesign the fleet.

## 2. Design Goals

The benchmark should satisfy the following goals:

- preserve the spirit of standard AEOSSP formulations
- use a standalone benchmark-owned verifier rather than an external benchmark
  engine
- stay physically meaningful without inheriting Basilisk-scale implementation
  complexity
- use event-based planning rather than per-second reactive assignment vectors
- create real trade-offs through observation timing, slew feasibility, battery
  usage, and dense task-window contention
- remain deterministic and offline-friendly
- keep the public interface algorithm-agnostic
- provide canonical dataset generation and benchmark-owned fixtures

## 3. Contract Alignment

The finished benchmark must conform to `docs/benchmark_contract.md`.

The intended finished shape is:

```text
benchmarks/aeossp_standard/
├── README.md
├── generator/
│   └── run.py
├── verifier/
│   └── run.py
├── visualizer/
│   └── run.py
└── dataset/
    ├── example_solution.json
    ├── index.json
    └── cases/
        └── case_0001/
            ├── mission.yaml
            ├── satellites.yaml
            └── tasks.yaml
```

`SPEC.md` is a temporary tracked development artifact and should be absorbed
into `README.md` before finished-benchmark promotion.

Frozen contract decisions:

- `generator/run.py` is the canonical public generator entrypoint
- `verifier/run.py` is the canonical public verifier entrypoint
- `visualizer/run.py` is the canonical public visualizer entrypoint
- the public verifier CLI accepts positional `case_dir` and `solution_path`
- `dataset/example_solution.json` is a single real solution object using the
  same schema as a normal submission
- `dataset/index.json` is optional by contract but will be provided
- the canonical case layout is:
  - `mission.yaml`
  - `satellites.yaml`
  - `tasks.yaml`

Frozen non-goals:

- no compatibility layer for the current `benchmarks/aeosbench/` case format
- no direct support for AEOS-Bench assignment vectors
- no Basilisk dependency in the canonical verifier

Intended finished-benchmark metadata once promoted:

- `repro_ci: true`
- `generated_paths`:
  - `dataset/cases`
  - `dataset/index.json`

`dataset/example_solution.json` is intentionally not generator-owned, because it
is a curated runnable example rather than a canonical generated artifact.

## 4. Benchmark Summary

### 4.1 Core formulation

The canonical formulation is:

- fixed real-satellite constellation provided by the case
- fixed point-imaging tasks with release and due windows
- solver-proposed observation intervals
- verifier-owned orbit propagation
- verifier-owned visibility, slew, and battery validation
- completion-first scoring with turnaround time and power as secondary signals

### 4.2 Canonical mission story

The benchmark models a standard agile electro-optical Earth-observation scheduling
problem over one half-day planning cycle.

Each satellite follows a frozen publicly sourced orbit and has a benchmark-owned
payload, power model, and agility model. Each task represents a point target
that becomes available at `release_time`, expires at `due_time`, and requires
one continuous observation interval of a specified duration.

The solver's job is to decide which tasks to observe and when to observe them,
while respecting physical visibility, slew retargeting, and battery
constraints.

### 4.3 What this benchmark is and is not

In scope:

- fixed-constellation observation scheduling
- point-target electro-optical observation planning
- frozen TLE-based orbit propagation
- verifier-owned observation geometry
- battery accounting
- attitude retargeting feasibility
- completion metrics

Out of scope:

- constellation design
- downlink and data-delivery planning
- onboard storage modeling
- cloud cover and stochastic weather
- detailed optical image quality scoring
- full reaction-wheel momentum propagation
- drag, low-thrust control, or maneuver execution
- solver-authored visibility claims
- solver-authored energy claims

## 5. Canonical Mission Story

The benchmark assumes a small-to-medium constellation of agile LEO
Earth-observation satellites serving many more imaging requests than can be
completed within one 12-hour planning cycle.

The planner faces four main sources of contention:

- time-window overlap between tasks
- finite access opportunities driven by orbital geometry
- finite retargeting agility between tasks
- finite battery capacity across the horizon

The benchmark intentionally evaluates successful acquisition, not data delivery
to ground. If an image is acquired validly, it counts as acquired; downstream
dissemination is out of scope for this benchmark.

## 6. What Is In Scope / Out Of Scope

### 6.1 In scope

- fixed 12-hour planning horizon
- real satellite orbits from frozen TLEs
- event-based observation actions
- task release and due windows
- required continuous dwell duration
- sensor-type compatibility
- battery charging and discharging
- maneuver feasibility through a bounded slew model
- completion scoring

### 6.2 Out of scope in v1

- constellation augmentation or redesign
- downlink and ground-station planning
- onboard storage accumulation or release
- weather and cloud cover
- detailed radiometry or image quality
- task fragmentation with additive partial credit
- star tracker, thermal, or keep-out modeling beyond simple benchmark-owned
  pointing limits
- full six-degree-of-freedom rigid-body simulation
- multi-satellite cooperative imaging of one task

### 6.3 Explicit simplifications

Frozen v1 simplifications:

- each task is a point target, not a polygonal AOI
- each task is binary-complete rather than partially creditable
- the verifier derives required pointing from task geometry; the solver does
  not submit low-level attitude commands
- ground-side daylight is encoded into task windows rather than enforced
  through a separate target-illumination validity rule

## 7. Mission and Scheduling Abstraction

### 7.1 Planning horizon

Frozen contract:

- each case uses one fixed 12-hour horizon
- tasks may have narrower release and due windows inside that horizon

The half-day horizon is long enough for meaningful resource trade-offs while
keeping case inspection and verifier runtime manageable.

### 7.2 Task model

Each task represents a single imaging request over a point target.

Each task includes:

- `task_id`
- `name`
- `latitude_deg`
- `longitude_deg`
- `altitude_m`
- `release_time`
- `due_time`
- `required_duration_s`
- `required_sensor_type`
- `weight`

Frozen semantics:

- `release_time` and `due_time` define the only time window in which the task
  may be serviced
- `release_time`, `due_time`, and `required_duration_s` must align to the
  public action grid
- the target must be observed continuously for exactly
  `required_duration_s` to count as complete
- `required_duration_s` is encoded as an integer number of seconds

### 7.3 Action model

The public solution is event-based.

Supported action types in v1:

- `observation`

Each observation action includes:

- `type`
- `satellite_id`
- `task_id`
- `start_time`
- `end_time`

The solver does not submit:

- per-second assignment vectors
- commanded quaternions or MRPs
- pointing angles
- visibility opportunity IDs
- battery or energy state claims
- any benchmark-owned helper opportunity IDs

### 7.4 Task completion semantics

Frozen v1 completion semantics:

- a task is complete if there exists at least one valid observation action
  targeting that task whose duration is exactly `required_duration_s`
- fragmented observations of the same task do not add together
- if several valid full observations exist, the earliest completion time is
  used for turnaround time
- duplicate valid observations of an already-complete task are allowed but do
  not increase completion credit

This preserves the continuous-observation spirit of standard AEOSSP while
fitting an event-based public schedule contract.

## 8. Physical and Astrodynamics Abstraction

### 8.1 Canonical propagation choice

Frozen canonical choice:

- Brahe-backed SGP4 propagation from frozen TLEs

This is the recommended canonical propagation for `aeossp_standard`.

Justification:

- the benchmark is scheduling-only, so real frozen constellation states are more
  natural than solver-facing Cartesian orbit design
- TLE-based cases align with existing Earth-observation benchmark patterns in
  this repository
- SGP4 from frozen TLEs is deterministic, compact, and easy for the generator
  to reproduce
- it avoids the cost and fragility of Basilisk while retaining realistic
  orbital motion

Frozen verifier frame choices:

- inertial propagation frame: GCRF-compatible SGP4 output handling
- Earth-fixed geometry frame: ITRF
- Earth shape for geometry: WGS84
- deterministic static EOP provider for offline reproducibility

### 8.2 Satellite state representation

Each satellite entry in `satellites.yaml` includes:

- `satellite_id`
- `norad_catalog_id`
- `tle_line1`
- `tle_line2`

The verifier treats the TLE pair as the orbital source of truth.

### 8.3 Geometry sampling

Frozen verifier-owned sample steps:

- `geometry_sample_step_s`: used for observation visibility and attitude checks
- `resource_sample_step_s`: used for battery integration between events

Recommended defaults:

- `geometry_sample_step_s = 5`
- `resource_sample_step_s = 10`

These are mission-level parameters stored in `mission.yaml`.

Frozen timing-grid rules:

- `horizon_end - horizon_start` must be exactly divisible by
  `action_time_step_s`, `geometry_sample_step_s`, and `resource_sample_step_s`
- `action_time_step_s`, `geometry_sample_step_s`, and `resource_sample_step_s`
  must all be positive integers

## 9. Observation / Imaging Semantics

### 9.1 Imaging model

An observation action represents one continuous point-target imaging interval.

The verifier derives the required boresight direction from:

- the propagated satellite state
- the target geodetic position
- the action interval

The solver does not choose the look vector directly.

### 9.2 Hard observation validity

An observation action is hard-valid only if all of the following hold:

- referenced `satellite_id` and `task_id` exist
- `end_time > start_time`
- action timestamps lie on the public action grid
- the action lies fully within the mission horizon
- the action lies fully within the task's `[release_time, due_time]` window
- the action duration is exactly `required_duration_s`
- the satellite sensor type matches the task's `required_sensor_type`
- the target remains geometrically observable at every geometry sample inside
  the action interval
- the required pointing remains within the satellite's maximum off-nadir limit
- the satellite does not overlap another observation action in time
- the action is reachable from neighboring actions given slew plus settling time
- battery remains within bounds over the whole schedule

If any action violates a hard rule, the whole solution is invalid.

### 9.3 Continuous-visibility rule

The benchmark preserves continuous-observation semantics:

- the target must remain observable for the full action interval
- short interruptions are not tolerated
- sampling discretization is verifier-owned, and any gap detected at sampled
  times invalidates the action

### 9.4 Opportunity interpretation

The benchmark does not expose a canonical `opportunities.json` case file in v1.

The solver receives satellites and tasks, not pre-authorized access windows.
The verifier and optional visualizers may derive access intervals internally for
diagnostics.

## 10. Onboard Resource Model

### 10.1 Explicit v1 resources

Frozen explicit v1 resources:

- battery energy

### 10.2 Satellite resource fields

Each satellite entry includes:

- `resource_model`
  - `battery_capacity_wh`
  - `initial_battery_wh`
  - `idle_power_w`
  - `imaging_power_w`
  - `slew_power_w`
  - `sunlit_charge_power_w`

Frozen bounds:

- battery state must always remain in `[0, battery_capacity_wh]`

### 10.3 Battery accounting

The verifier models:

- baseline bus draw through `idle_power_w`
- additional imaging draw while an observation action is active
- additional maneuver draw during computed slew-plus-settle windows
- sunlight charging through `sunlit_charge_power_w` when the spacecraft is not
  eclipsed, including while observation or maneuver loads are active

`PC` is defined as total gross electrical energy consumption in watt-hours over
the mission horizon. Solar charging does not reduce `PC`; it only affects
battery feasibility.

## 11. Attitude / Slew Model

### 11.1 Public abstraction

The public benchmark uses a verifier-derived pointing model rather than
solver-authored attitude commands.

For each observation action, the verifier derives the required line-of-sight
pointing direction from spacecraft to target.

The benchmark-owned pointing strategy is:

- during an observation action, the spacecraft body tracks the target line of
  sight closely enough to maintain continuous observation
- between consecutive observation actions, the spacecraft follows a
  minimum-time bounded retargeting maneuver between the terminal look vector of
  the earlier observation and the initial look vector of the later observation
- before the first observation of the horizon and after the last, the default
  body attitude is nadir-pointed

This is more realistic than a pure "enough slack between actions" heuristic,
while still benchmark-practical: the benchmark owns a nominal body-pointing
story and checks a bounded kinematic retargeting model rather than simulating
full rigid-body dynamics.

### 11.2 Satellite agility fields

Each satellite entry includes:

- `attitude_model`
  - `max_slew_velocity_deg_per_s`
  - `max_slew_acceleration_deg_per_s2`
  - `settling_time_s`
  - `max_off_nadir_deg`

### 11.3 Slew feasibility

Between consecutive observation actions on the same satellite, the verifier
computes a required retargeting angle from the end-of-action pointing direction
of the earlier observation to the start-of-action pointing direction of the
later observation.

Frozen feasibility model:

- bang-coast-bang scalar slew profile
- bounded by maximum angular acceleration and maximum angular velocity
- fixed settling time added after the slew
- zero angular-rate assumption at action boundaries after settling

If the available gap between consecutive observation actions is shorter than the
required slew-plus-settle time, the solution is invalid.

### 11.4 Nadir baseline

When a satellite has no prior or subsequent active observation constraining its
attitude, the canonical default body attitude is nadir-pointed for the purpose
of maneuver estimation.

This means:

- the first observation of the horizon must be reachable from nadir
- the final observation does not require a post-action return slew for validity
- between consecutive observations, the verifier does **not** require an
  explicit return to nadir

### 11.5 Derived attitude curve

Although the public solution is event-based, a benchmark-owned nominal attitude
curve is still defined.

For a chosen visualizer sampling grid, the nominal body-pointing profile is:

- nadir before the first active observation and after the last
- target-tracking during active observation intervals
- minimum-time bang-coast-bang interpolation between the terminal look vector of
  one observation and the initial look vector of the next
- if a visualizer chooses to display attitude during long idle spans, it may
  optionally show a relaxed return toward nadir after the minimum retargeting
  reservation is satisfied, but this is diagnostic only and does not affect
  verifier validity

This nominal attitude curve is the one the visualizer should render. The
generator and verifier do not need to materialize a full per-second attitude
history as part of the public case or solution contract.

## 12. Opportunity and Visibility Semantics

### 12.1 Visibility conditions

A task is observable by a satellite at time `t` only if:

- the target is above the Earth limb from the spacecraft viewpoint
- the required boresight angle from nadir does not exceed
  `attitude_model.max_off_nadir_deg`
- the satellite sensor type matches the task's `required_sensor_type`

### 12.2 Sensor modality and illumination

`aeossp_standard` is an electro-optical benchmark with benchmark-owned visible
and infrared modality labels.

Frozen v1 rules:

- visible-vs-infrared behavior is modeled through task and satellite sensor
  types
- target-side daylight is not a separate hard-validity check in v1
- if daylight is operationally required for a task, the generator should encode
  that through the task's release and due window
- spacecraft eclipse state affects charging only

### 12.3 Access intervals

For diagnostics and visualizers, the verifier may expose derived continuous
access intervals for each `(satellite, task)` pair.

These intervals are verifier-derived artifacts, not public case inputs.

## 13. Metrics and Ranking Intent

### 13.1 Reported metrics

The canonical verifier reports:

- `CR`
- `WCR`
- `TAT`
- `PC`

Definitions:

- `CR`: fraction of tasks completed
- `WCR`: weighted fraction of completed tasks using task weights
- `TAT`: mean turnaround time in seconds across completed tasks, or `null` if
  no tasks are completed
- `PC`: total electrical energy consumption in watt-hours

The verifier may also report:

- `num_completed_tasks`
- `num_tasks`
- `per_task`
- `diagnostics`

### 13.2 Weighted metrics

Frozen weight semantics:

- if a task omits `weight`, it defaults to `1.0`
- `WCR` uses task weights, not task duration

### 13.3 Turnaround time

`TAT` is computed over completed tasks only:

```text
TAT = mean(completion_time_i - release_time_i)
```

where `completion_time_i` is the end of the earliest valid full observation for
task `i`.

### 13.4 Ranking intent

Frozen ranking order:

1. `valid = true`
2. maximize `WCR`
3. maximize `CR`
4. minimize `TAT`
5. minimize `PC`

Rationale:

- weights carry the primary mission value signal
- turnaround time is secondary to completion
- power consumption is a tie-breaker rather than the primary objective
- if both compared solutions have no completed tasks, `TAT` is treated as tied
  and ranking falls through to `PC`

## 14. Solution Contract

### 14.1 Public solution schema

The public solution is one JSON object:

```json
{
  "actions": [
    {
      "type": "observation",
      "satellite_id": "sat_001",
      "task_id": "task_001",
      "start_time": "2026-07-01T03:21:00Z",
      "end_time": "2026-07-01T03:21:30Z"
    }
  ]
}
```

Frozen public rules:

- only single-case solution objects are supported
- there is no multi-case wrapper
- `actions` may be empty
- action order in the JSON object is not semantically meaningful; the verifier
  may sort by time internally
- there is no `satellites` top-level field because the constellation is fixed
- there is no route, energy, or resource-state claim field

### 14.2 Unsupported action types

Unsupported action types invalidate the solution.

The verifier should not silently ignore unknown public action types for this
benchmark.

### 14.3 Time-grid alignment

All action timestamps must lie on `mission.action_time_step_s`.

Recommended default:

- `action_time_step_s = 5`

## 15. Case File Contract

### 15.1 `mission.yaml`

`mission.yaml` is the case-level verifier contract.

Required content:

```yaml
mission:
  case_id: str
  horizon_start: ISO8601
  horizon_end: ISO8601
  action_time_step_s: int
  geometry_sample_step_s: int
  resource_sample_step_s: int

  propagation:
    model: sgp4
    frame_inertial: gcrf
    frame_fixed: itrf
    earth_shape: wgs84

  scoring:
    ranking_order: [valid, WCR, CR, TAT, PC]
    reported_metrics: [CR, WCR, TAT, PC]
```

Additional benchmark-owned metadata may be included if documented, but the
fields above are the canonical verifier contract.

### 15.2 `satellites.yaml`

`satellites.yaml` root structure:

```yaml
satellites:
  - satellite_id: str
    norad_catalog_id: int
    tle_line1: str
    tle_line2: str

    sensor:
      sensor_type: visible | infrared

    attitude_model:
      max_slew_velocity_deg_per_s: float
      max_slew_acceleration_deg_per_s2: float
      settling_time_s: float
      max_off_nadir_deg: float

    resource_model:
      battery_capacity_wh: float
      initial_battery_wh: float
      idle_power_w: float
      imaging_power_w: float
      slew_power_w: float
      sunlit_charge_power_w: float
```

Hard satellite constraints:

- `battery_capacity_wh > 0`
- `0 <= initial_battery_wh <= battery_capacity_wh`
- all power terms are non-negative
- all slew/settling parameters are non-negative
- `tle_line1` and `tle_line2` must form a valid TLE pair

### 15.3 `tasks.yaml`

`tasks.yaml` root structure:

```yaml
tasks:
  - task_id: str
    name: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    release_time: ISO8601
    due_time: ISO8601
    required_duration_s: int
    required_sensor_type: visible | infrared
    weight: float
```

Hard task constraints:

- `release_time` and `due_time` both lie inside the mission horizon
- `due_time > release_time`
- `required_duration_s > 0`
- `weight > 0`
- `release_time`, `due_time`, and `required_duration_s` lie on the public
  action grid
- `required_sensor_type` is one of `visible` or `infrared`

### 15.4 Dataset root metadata

`dataset/index.json` should include:

- `benchmark`
- `canonical_seed`
- `case_ids`
- `example_smoke_case_id`
- per-case summaries:
  - `path`
  - `num_satellites`
  - `num_tasks`
  - `horizon_hours`
  - task-weight summary

## 16. Verifier Semantics

### 16.1 Verifier architecture

The canonical verifier should follow a clean two-stage structure:

1. geometry and resource analysis
2. scoring and report synthesis

Stage 1 responsibilities:

- load and validate the case
- load and validate the solution
- propagate satellites across needed times
- validate observation geometry
- validate per-satellite action overlap
- validate slew feasibility
- integrate battery state
- derive per-task completion and completion times

Stage 2 responsibilities:

- compute aggregate metrics
- emit structured violations and diagnostics

### 16.2 Invalidity policy

Frozen policy:

- any hard action or resource violation makes the whole solution invalid
- invalid solutions should still return a structured report with:
  - `valid = false`
  - metrics with `CR = 0`, `WCR = 0`, `TAT = null`, and `PC = 0`
  - `violations`
  - helpful diagnostics when available

### 16.3 Frozen report shape

Top-level verifier report:

```json
{
  "valid": true,
  "metrics": {
    "CR": 0.0,
    "WCR": 0.0,
    "TAT": null,
    "PC": 0.0
  },
  "violations": [],
  "diagnostics": {
    "per_task": {},
    "per_satellite_resource_summary": {}
  }
}
```

### 16.4 Runtime target

The verifier implementation should be built toward this performance target:

- on this machine, a valid near-limit solution with roughly:
  - the case's full satellite set
  - about 100 observation actions
- should run in under 10 seconds

This is a coding-quality target, not a benchmark-scoring metric.

## 17. Generator Requirements

### 17.1 Generator ownership

`aeossp_standard` owns its dataset generator.

The canonical no-flag path must:

1. download or reuse public source data
2. produce the canonical dataset under `dataset/cases/`

### 17.2 Source workflow

Recommended source categories:

- public Earth-observation TLE source for real satellites, preferably sourced
  directly from CelesTrak and frozen into a benchmark-owned snapshot cache
- public geographic target source, combining:
  - world-city or infrastructure targets for high-value tasks
  - land-distributed background targets for geographic diversity

The exact source endpoints remain a tuning choice, but the workflow must be
fully benchmark-owned and reproducible.

### 17.3 Canonical release strategy

Recommended defaults:

- 5 canonical cases
- one shared 12-hour horizon family
- one canonical generator seed
- difficulty progression emerges from seeded stochastic generation rather than a
  hand-maintained per-case recipe

### 17.4 Generator principles

Frozen principles:

- no hand-maintained per-case tuple list as the source of truth
- case generation should be seed-driven and algorithmic
- canonical cases should remain loadable without external caches present
- `dataset/source_data/` may be used as a gitignored download/cache directory

### 17.5 Opportunity generation

The generator may internally derive opportunities to sample or calibrate tasks,
but canonical cases should not require a tracked `opportunities.json` file in
v1.

## 18. Visualizer Expectations

### 18.1 Case visualizer

The benchmark should provide a case visualizer that helps calibrate:

- satellite ground tracks over the 12-hour horizon
- task geographic distribution
- task release and due windows
- derived access opportunities

Recommended artifacts:

- map view of satellites and tasks
- per-task opportunity timeline
- per-satellite access density summary
- optional derived body-pointing trace for selected satellites

### 18.2 Solution visualizer

The benchmark should provide a solution visualizer that uses verifier-derived
analysis rather than reimplementing physics.

Recommended artifacts:

- action timeline
- completed and uncompleted task overview
- per-satellite battery trace
- per-satellite derived attitude curve on a visualizer-owned fine grid
- first-failure diagnostics for invalid solutions

### 18.3 Testing philosophy

Visualizer correctness should primarily be established by human inspection.
Only minimal smoke coverage is recommended for entrypoint stability.

## 19. Fixture And Test Requirements

### 19.1 Verifier fixture priorities

The benchmark should include small committed fixtures that lock:

- malformed solution rejection
- unknown task or satellite rejection
- off-grid and out-of-horizon timing rejection
- observation visibility invalidation
- slew infeasibility invalidation
- battery violation invalidation
- full-completion scoring
- turnaround time semantics
- deterministic earliest-completion semantics

### 19.2 Generator testing philosophy

Generator quality should not be treated as solved by shallow schema assertions
alone.

Recommended generator checks:

- deterministic output for a fixed seed
- loadability of generated cases
- manual visual inspection of case geography and opportunity structure

### 19.3 Visualizer testing philosophy

Do not invest heavily in visualizer pixel tests.

Recommended visualizer checks:

- `--help` and CLI smoke
- one artifact write smoke with tiny local inputs

## 20. Canonical Dataset Release Targets

### 20.1 Frozen release targets

Frozen goals for the first public release:

- 5 canonical cases
- 12-hour horizon in every case
- fixed-constellation scheduling only
- event-based observation-only solution contract
- Brahe-backed TLE propagation
- explicit battery constraints
- focused fixture corpus and verifier tests

### 20.2 Recommended not-yet-frozen defaults

Recommended tuning targets:

- 20 to 40 satellites per case
- 200 to 800 tasks per case
- task durations roughly 15 to 90 seconds
- release and due windows wide enough that multiple opportunities exist for
  some tasks, but not so wide that scheduling becomes trivial
- enough battery pressure that observing every geometrically visible task is not
  feasible

## 21. Open Tuning Knobs vs Frozen Contract

### 21.1 Frozen contract decisions

These are frozen for implementation:

- benchmark name: `aeossp_standard`
- scheduling-only benchmark, not constellation design
- Brahe-backed verifier
- frozen TLE-based satellite orbits
- event-based observation schedule
- 12-hour horizon
- explicit battery in v1
- no downlink in v1
- no storage in v1
- canonical case files:
  - `mission.yaml`
  - `satellites.yaml`
  - `tasks.yaml`
- no backward compatibility with current `aeosbench` format

### 21.2 Recommended defaults

These should be treated as default implementation choices unless calibration
shows a clear problem:

- `action_time_step_s = 5`
- `geometry_sample_step_s = 5`
- `resource_sample_step_s = 10`
- 5 canonical cases

### 21.3 Tuning knobs not yet frozen

These remain tunable during implementation:

- exact public EO satellite filtering strategy on top of the CelesTrak source
- exact task-source mix
- exact per-case task counts
- exact battery magnitudes
- exact task duration distribution
- exact visible-versus-infrared sensor/task mix across the canonical dataset

## 22. Migration / Relationship To Legacy `aeosbench`

`aeossp_standard` should replace the current public `aeosbench` benchmark once
implemented and validated.

Frozen migration intent:

- `aeossp_standard` is the new canonical public benchmark
- the current `aeosbench` public interface is legacy and should not define the
  long-term contract

Preserve in spirit from AEOS-Bench:

- fixed-constellation agile EO scheduling
- task release and due windows
- continuous-observation requirement
- completion, turnaround time, and power-style metrics
- meaningful onboard subsystem constraints

Intentionally changed for AstroReason-Bench:

- event-based action schedule instead of per-second assignment vectors
- Brahe-backed verification instead of Basilisk-backed ground truth
- simpler public case shape
- benchmark-owned reproducible generator
- acquisition-focused semantics rather than data-delivery semantics
- no expectation of metric-level numerical equivalence with AEOS-Bench

The eventual public README may link to the official AEOS-Bench repository and
to a separate reproduction repository for lineage, but the benchmark contract
here should stand on its own.

## Appendix A: Top Unresolved Design Decisions

These are the top unresolved decisions that may still need tuning during
implementation:

1. The exact public EO satellite filtering strategy for the canonical dataset.
2. The exact task source mix between city or infrastructure targets and
   geographically distributed land targets.
3. The precise battery magnitudes that best preserve trade-offs without making
   most cases invalid by default.
4. The exact visible-versus-infrared sensor/task mix across the canonical
   dataset.
5. The exact task-window and duration distribution that best balances schedule
   density against verifier tractability.

## Appendix B: Primary Influences

Local files that most influenced this spec:

- `docs/benchmark_contract.md`
- `benchmarks/revisit_constellation/README.md`
- `benchmarks/relay_constellation/README.md`
- `benchmarks/regional_coverage/README.md`
- `benchmarks/stereo_imaging/README.md`
- `benchmarks/aeosbench/dataset/README.md`
- `benchmarks/aeosbench/generator.py`
- `benchmarks/aeosbench/verifier/__init__.py`
- `benchmarks/aeosbench/verifier/models.py`
- `benchmarks/aeosbench/verifier/progress.py`
- the pre-promotion `relay_constellation` development spec from the parent of
  commit `8c2c1aded78dd45c407b3dc21e4f9914dbb36e09`

External public influences:

- the AEOS-Bench paper, "Towards Realistic Earth-Observation Constellation
  Scheduling: Benchmark and Methodology"
- the official AEOS-Bench repository
- standard agile Earth-observation scheduling literature on time-windowed
  imaging, continuous dwell constraints, and resource-constrained satellite
  tasking
