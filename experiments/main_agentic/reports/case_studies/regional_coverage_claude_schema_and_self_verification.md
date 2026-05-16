# Regional Coverage Claude Case Study: Premature Contract Closure

This note examines the five `claude_code` regional coverage runs in the `main_agentic` aggregate report:

- `regional_coverage / claude_code / test / case_0001`
- `regional_coverage / claude_code / test / case_0002`
- `regional_coverage / claude_code / test / case_0003`
- `regional_coverage / claude_code / test / case_0004`
- `regional_coverage / claude_code / test / case_0005`

All five runs were reported as successful and valid, but all five scored zero weighted coverage in the benchmark aggregate. The immediate symptom was an output schema mismatch: Claude wrote nonempty schedules, but the benchmark parsed zero strip observations. The deeper failure was premature contract closure. Claude inferred a complete task interface from the case files and short prompt, then built solvers and validators around that inferred interface without reading the workspace `README.md` or using the workspace `verifier`.

## Evidence Base

This case study is anchored to tracked repository artifacts, not to ignored `results/*` run directories. The aggregate scores come from `experiments/main_agentic/reports/regional_coverage.md`. The behavioral evidence comes from the tracked trace exports `experiments/main_agentic/reports/traces/data/events/regional_coverage__claude_code__test__case_0001.js` through `case_0005.js`. The intended workspace assembly is in `experiments/main_agentic/benchmarks/regional_coverage.yaml`, which copies `experiments/_fragments/prompts/regional_coverage/README.default.md` to `/app/workspace/README.md` and the opaque verifier artifact to `/app/workspace/verifier`. The scoring and parsing behavior is in `benchmarks/regional_coverage/verifier.py`.

The ignored run outputs are useful for ad hoc local debugging, but the report should not depend on them as stable citations. The trace exports already contain the critical evidence: the initial prompt, Claude's file-discovery choices, its generated validation commands, its schema checks, and its final coverage claims.

## Aggregate Outcome

The regional coverage report shows a uniform valid-empty outcome for Claude:

| Case | Valid | weighted_coverage_ratio | coverage_ratio | num_actions |
| --- | --- | ---: | ---: | ---: |
| `case_0001` | true | 0.0000 | 0.0000 | 0 |
| `case_0002` | true | 0.0000 | 0.0000 | 0 |
| `case_0003` | true | 0.0000 | 0.0000 | 0 |
| `case_0004` | true | 0.0000 | 0.0000 | 0 |
| `case_0005` | true | 0.0000 | 0.0000 | 0 |

The important diagnostic is `num_actions=0`, not just the zero coverage. Claude's traces show it believed it wrote nonempty schedules: `case_0001` printed 64 actions, `case_0002` printed 55 actions, `case_0003` printed 49 actions early in the run, `case_0004` printed 64 actions, and `case_0005` printed a nonempty `actions` array. The benchmark verifier nevertheless counted zero parsed strip observations in every case.

This is why Claude's normalized scores are around 20 rather than literal zero: the files were valid JSON and did not violate hard constraints after parsing, but they were valid as empty schedules. They earned no coverage.

## Intended Contract

The assembled regional coverage README says the workspace contains `case/`, `README.md`, and a local verifier helper when present. It defines the required action shape as:

```json
{
  "type": "strip_observation",
  "satellite_id": "sat_iceye-x2",
  "start_time": "2025-07-17T03:31:00Z",
  "duration_s": 20,
  "roll_deg": 20.0
}
```

The same README states that a `strip_observation` action is interpreted only from `type`, `satellite_id`, `start_time`, `duration_s`, and `roll_deg`, and that actions with another `type` are not strip observations and do not create coverage. The public verifier implements that rule directly: `_parse_actions` skips any row whose `raw_action.get("type")` is not exactly `"strip_observation"`, then reads `duration_s` and `roll_deg` from the remaining rows.

This contract was not hidden in the repository. The `main_agentic` benchmark config assembles it into `/app/workspace/README.md`, and it also assembles `/app/workspace/verifier`. The problem is that Claude's trace does not show it discovering either root-level artifact.

## What Claude Actually Read

Across all five regional traces, Claude does not read `/app/workspace/README.md` and does not run `/app/workspace/verifier`. The first exploration step is always case-centered:

| Case | First workspace action | Root `README.md` read? | Verifier run? |
| --- | --- | ---: | ---: |
| `case_0001` | `ls /app/workspace/case/` | no | no |
| `case_0002` | `ls /app/workspace/case/` | no | no |
| `case_0003` | `ls /app/workspace/case/` | no | no |
| `case_0004` | `find /app/workspace/case/ ...` | no | no |
| `case_0005` | `Glob case/**/*` | no | no |

The case directory lists exactly the instance data files: `coverage_grid.json`, `manifest.json`, `regions.geojson`, and `satellites.yaml`. Claude then reads the manifest, satellites, regions, and grid. It does not list `/app/workspace`, does not read `/app/workspace/README.md`, and does not run `/app/workspace/verifier --help`.

That matters because the four case files describe the physical instance, not the submission interface. They contain time horizons, TLEs, sensor limits, regions, and grid samples. They do not define the JSON action schema with `type: "strip_observation"` and `roll_deg`. Once Claude chose to look only inside `case/`, it had enough information to invent a plausible scheduling model but not enough information to know the benchmark-facing output contract.

The short task prompt likely contributed to the attention trap: it says, "Please solve the prepared regional strip-coverage case using the files in `case/`" and "Write `solution.json` at the workspace root." That is compatible with reading the root README, but it makes `case/` the salient place to start. Claude followed that salience literally and never recovered the stronger local authority sitting one directory above.

## Contract Drift

Claude submitted internally plausible but benchmark-invisible action rows. The exact variants differ by case, but the repeated pattern is stable:

| Case | Claude action fields visible in trace | Missing benchmark-critical fields |
| --- | --- | --- |
| `case_0001` | `satellite_id`, `start_time`, `end_time`, `roll_angle_deg` | `type`, `duration_s`, `roll_deg` |
| `case_0002` | `satellite_id`, `start_time`, `duration_s`, `roll_angle_deg` | `type`, `roll_deg` |
| `case_0003` | `satellite_id`, `start_time`, `duration_s`, `off_nadir_deg` or `roll_angle_deg` variants | `type`, `roll_deg` |
| `case_0004` | `satellite_id`, `start_time`, `duration_s`, `roll_angle_deg` | `type`, `roll_deg` |
| `case_0005` | `satellite_id`, `start_time`, `duration_s`, `roll_angle_deg` | `type`, `roll_deg` |

The names Claude chose are natural if the model is reasoning from first principles: observations often have a start/end interval, and `roll_angle_deg` is a descriptive name for attitude. But the benchmark contract is intentionally narrower: it wants duration, not end time, and `roll_deg`, not a generic roll-angle field. The verifier then derives end time, strip geometry, and coverage itself.

Because `type` was absent, the benchmark did not parse these rows as strip observations. The result is a valid empty schedule: no parsed actions, no schedule violations, no coverage. This is why the aggregate report shows `valid=true` and `num_actions=0`.

## Self-Validation

Claude did not merely forget a field at the final write step. It created validation routines that reinforced the wrong contract.

In `case_0001`, Claude's final "validation" is an inline Python script that asserts `spec_version == "v1"`, `case_id == "case_0001"`, `len(actions) == 64`, and then checks that each action has `satellite_id`, `start_time`, `end_time`, and `roll_angle_deg`. It validates edge off-nadir using `roll_angle_deg`, checks timing from `start_time` to `end_time`, and prints "Validation passed!" The next check says all actions are within horizon and "valid", but its time-grid condition is `if dur % 10 != 0 and dur % 5 != 0`, which lets 5-second-aligned durations pass even though the case action grid is 10 seconds.

In `case_0002`, the final quick validation again checks `duration_s` and `roll_angle_deg`. It prints "All constraints satisfied" after asserting `20 <= duration_s <= 180` and `-40 <= roll_angle_deg <= 40`. The benchmark action schema requires `roll_deg`, and some regional cases have sensor max duration 120 seconds rather than 180 seconds. So the validation was not just incomplete; it was a separate contract.

In `case_0004`, Claude's own final field check is especially compact evidence of the drift. It checks whether every action has exactly `satellite_id`, `start_time`, `duration_s`, and `roll_angle_deg`. That is a confident schema assertion, but it asserts the wrong schema: no `type`, no `roll_deg`.

In `case_0005`, Claude first says it wants to "understand the solution format better," but the next checks still stay inside the case files and package list. It then writes a solver that emits `roll_angle_deg`; after the solver reports 100% proxy coverage, it verifies timing and satellite conflicts privately rather than checking the root verifier.

This is the first root-cause layer: Claude did not treat validation as a query to an external authority. It treated validation as a local consistency check over the representation it had already decided to use.

## Proxy Verifier

The `case_0002` trace is especially revealing because Claude writes `/app/workspace/verify.py` and explicitly calls it a verifier. Its description says it will "verify solution.json coverage by computing actual strip footprints at 5s intervals." That sounds like the local benchmark verifier, but it is a custom proxy.

The proxy propagates TLEs with `sgp4.api.Satrec`, converts TEME-like positions to ECEF using a simple GMST rotation, converts ECEF to geodetic coordinates with an iterative WGS84 formula, estimates ground-track direction from consecutive latitude/longitude samples, treats grid samples as flat local offsets using roughly 111 km per degree, and counts a sample as covered when it falls inside a cross-track band and an along-track window.

The simplified transform in the trace is:

```python
def gmst_from_jd(jd, fr):
    T = ((jd - 2451545.0) + fr) / 36525.0
    gmst = (67310.54841 + (876600*3600 + 8640184.812866)*T + 0.093104*T**2 - 6.2e-6*T**3)
    return (gmst % 86400.0) / 86400.0 * 2 * math.pi

def teme_to_ecef(r_teme, jd, fr):
    theta = gmst_from_jd(jd, fr)
    ct, st = math.cos(-theta), math.sin(-theta)
    return np.array([r_teme[0]*ct - r_teme[1]*st, r_teme[0]*st + r_teme[1]*ct, r_teme[2]])
```

The core proxy coverage test is:

```python
near_km = alt * math.tan(math.radians(abs(roll) - fov/2))
far_km = alt * math.tan(math.radians(abs(roll) + fov/2))

dl = rs["lats"] - pos[0]
dn = rs["lons"] - pos[1]
dns = dn * math.cos(math.radians(pos[0]))

ct = (dns * td[1] - dl * td[0]) * 111.0
at = (dns * td[0] + dl * td[1]) * 111.0

at_limit = COV_STEP * 7.8 * 0.5 + 5
in_at = np.abs(at) <= at_limit
ct_signed = ct * side
in_ct = (ct_signed >= near_km) & (ct_signed <= far_km)
hits = np.where(in_at & in_ct)[0]
```

Claude then tunes against this proxy. It edits the proxy to remove the along-track filter, worries that this may be "too generous", restores a half-step along-track limit, sweeps `AT_FACTOR` values, compares solver coverage to proxy coverage, and chooses the schedule based on the proxy. At one point it writes that the solution achieves 100% under the "most likely evaluator model" and 99.85-99.90% under "conservative models." The phrase "most likely evaluator model" is the tell: Claude is guessing the evaluator rather than running the one assembled into the workspace.

The other regional cases show the same pattern in lighter form. Claude repeatedly writes solvers whose comments describe "proper strip evaluation", "marginal-weight greedy", "actual coverage", or "validated" constraints. These checks are often useful search heuristics, but they are not authoritative. Because they consume the same invented fields they emit, they cannot detect the benchmark-facing schema error.

## Benchmark Verifier Contrast

The real verifier does not use a flat band around a latitude/longitude ground track. It uses Brahe SGP propagation, obtains ECEF position and velocity, derives local satellite axes, applies signed roll to the boresight vector, intersects center and edge rays with the WGS84 ellipsoid, builds strip segment polygons from consecutive inner/outer edge hits, and applies Shapely point-in-polygon coverage against the scoring grid.

The benchmark path is:

1. `brahe.SGPPropagator.from_tle(...)`
2. `propagator.state_ecef(epoch)`
3. `_boresight_unit_vector(...)`
4. `_ray_ellipsoid_intersection_m(...)`
5. `_segment_polygon_lonlat(...)`
6. Shapely coverage against grid samples

The proxy may be useful as a search heuristic, but it is not equivalent to this ray/ellipsoid/polygon model. In regional strip coverage, small differences in frame handling, roll sign, swath-edge geometry, longitude projection, and along-track inclusion can turn near-perfect proxy coverage into low benchmark coverage. However, this geometry mismatch is still secondary. Claude never reached the point where geometry fidelity could matter officially, because the schedule was not parsed as strip observations in the first place.

## Why This Happened

The root cause is not simply that Claude used `roll_angle_deg` instead of `roll_deg`. It is that Claude failed to establish the hierarchy of authority in the prepared workspace.

There were three possible authorities available: the short user prompt, the root README plus verifier, and the case files. The correct hierarchy is README/verifier first, case files second, solver heuristics third. Claude inverted that hierarchy. It obeyed the short prompt's salient phrase "using the files in `case/`", treated the case files as enough to reconstruct the task, and then used its own scripts as the authority for both schema and scoring.

This is a recognizable agent failure mode on scientific optimization tasks. The task looks like a modeling problem, so the model enters "build a simulator" mode early. Once a simulator exists, every subsequent check asks whether the solution is consistent with that simulator. The local verifier would have collapsed the error immediately by reporting `num_actions=0`, but Claude's workflow never routed through it.

The trace also shows how the failure compounds. After the first invented schema appears, later scripts and assertions reuse it. The names become part of the local ecosystem: solvers emit `roll_angle_deg`, validators assert `roll_angle_deg`, debug scripts print `roll_angle_deg`, and final messages summarize proxy coverage. At that point, the model is no longer merely missing a README detail; it is living inside a self-consistent alternate benchmark.

## Antecedents Of Authority Acquisition

The important behavioral distinction is not simply "read README" versus "do not read README." Claude often starts by inspecting `case/` even in successful benchmark families. The more predictive distinction is whether it performs a second authority sweep before committing to the first durable solver/schema.

In these traces, Claude appears biased toward treating `case/` as the operative task boundary and then jumping into implementation. That behavior is not always fatal: it performs well when a later interruption or uncertainty triggers a second sweep over the root workspace, revealing the README and verifier before the private representation hardens. The failures occur when the case-only interpretation remains unchallenged long enough for Claude to build, score, and validate inside its self-inferred benchmark.

Several antecedents appear in the traces.

First, the first filesystem operation narrows attention. In failed regional runs, Claude starts with `ls /app/workspace/case/`, `find /app/workspace/case/`, or `Glob case/**/*`. That makes the workspace look as if the case files are the task. By contrast, successful control traces often follow the case read with `Glob **/*.md`, `ls /app/workspace`, or an explicit search for validation scripts and schema definitions.

Second, the case files are self-describing enough to create false confidence. `manifest.json` contains the benchmark name, case ID, horizon, time step, scoring fields, sensor settings, and action-count limit. `satellites.yaml`, `regions.geojson`, and `coverage_grid.json` contain enough geometry to build a plausible strip-coverage optimizer. But none of these files define the benchmark-facing JSON action schema. Claude therefore has enough information to solve a neighboring scientific optimization problem, but not enough information to submit to this benchmark.

Third, prompt wording can become a schema attractor. The prompt says "regional strip-coverage case" and "valid schedule", while pointing Claude to `case/`. Those words are accurate at the human level, but they do not name `type: "strip_observation"` or `roll_deg`. Claude converts the high-level noun "schedule" into a generic schedule interface with `start_time`, `duration_s` or `end_time`, and `roll_angle_deg`.

Fourth, early private success suppresses further authority search. In regional cases, Claude's proxy solvers often report 90-100% coverage. Once it has a high internal score, it becomes less likely to ask whether the official verifier agrees. This makes high proxy performance dangerous: it reduces the very uncertainty that would have triggered a README or verifier check.

Fifth, tooling friction can accidentally help. In the successful `relay_constellation / claude_code / case_0004` trace, Claude also starts from the case files. But it then spends time exploring `brahe` APIs and coordinate transforms. Before writing the serious solver, it lists `/app/workspace`, discovers `README.md` and `verifier`, reads the README, and uses the verifier repeatedly. The added uncertainty created an authority-discovery checkpoint. In the failed regional runs, Claude never hits such a checkpoint before its private solver becomes the working contract.

This suggests a more precise mechanism: Claude fails when it closes the contract too early. Once it has committed to a representation and seen private success, later work mostly optimizes inside that representation.

## Comparison With Other Harness Traces

The contrast with stronger regional coverage traces supports this interpretation. In the tracked `codex` trace for `case_0001`, the agent lists `/app/workspace`, sees `README.md`, `verifier`, `AGENTS.md`, and `case/`, reads `README.md`, checks `./verifier --help`, writes an empty `solution.json`, and runs `./verifier case/ solution.json` before building the solver. In the tracked `kimi_cli` trace for `case_0001`, the agent's first stated plan is to read the README, it reads `/app/workspace/README.md`, checks `/app/workspace/verifier`, and runs `./verifier --help`.

This difference is not about orbital mechanics talent. It is about the first few minutes of tool discipline. The agents that inspected the root workspace acquired the output schema and local verifier before optimizing. Claude inspected only `case/`, so it optimized under a guessed interface.

The same pattern also explains Claude's much better `aeossp_standard` results. In the tracked AEOSSP traces for `case_0001` through `case_0004`, Claude starts from case files but then lists the root workspace, reads `/app/workspace/README.md`, and runs the local verifier repeatedly; its high WCR values there are mostly verifier-guided, not accidental. The exception is `aeossp_standard / claude_code / case_0005`: Claude again skips README and verifier, writes a top-level `observations` array instead of the required `actions` array with `type: "observation"`, self-validates that private schema, and receives an official valid-empty score of zero. This cross-benchmark contrast sharpens the root cause: Claude succeeds when it binds to README plus verifier early, and fails quietly when it treats case files and self-checks as the authority.

The relay constellation traces provide another useful control. Claude fails four of five relay cases after submitting `schedule` or `link_plan` instead of the required physical `actions`. The only successful relay case, `case_0004`, is the one where it performs the late authority sweep, reads the README, and runs the verifier. Relay therefore shows that Claude can recover from an initial case-only start, but only if something interrupts premature contract closure.

This also helps interpret regional coverage. The regional result should not be read as "Claude cannot reason about SAR strip coverage." The traces show that Claude can build elaborate propagation, candidate-generation, and greedy/local-search machinery. The failure is that this machinery is attached to the wrong contract.

## Implications

For evaluation interpretation, the `claude_code` regional coverage result should not be summarized as "Claude cannot find regional coverage schedules." The better reading is: these runs failed to bind to the benchmark contract and then self-validated against an invented evaluator. In a benchmark where the local verifier is the intended authority, that is a first-order failure.

For prompt and harness design, the fix is not mainly to explain SGP4 geometry more thoroughly. The README already explains the action contract and the verifier already encodes the scoring geometry. The important intervention is to force authority acquisition before optimization. A stronger task prompt would say: "Start by reading `/app/workspace/README.md`; run `/app/workspace/verifier --help`; before finishing, run `/app/workspace/verifier case/ solution.json` and use its reported `num_actions` and metrics." The workspace rule could also explicitly say that `case/` contains instance data, while `README.md` and `verifier` define the submission contract.

For benchmark and prompt wording, avoid nouns that invite invented top-level artifacts unless they are immediately tied to the actual schema. "Schedule" and "link plan" are natural English descriptions, but agents may literalize them into `schedule` or `link_plan`. The safer pattern is to name the required top-level field and action type in the short prompt as well as the README.

For benchmark diagnostics, it may be worth adding a warning when `solution.actions` is non-empty but no `strip_observation` actions are parsed. That would preserve the current rule that unknown action types do not create coverage, while making this exact failure mode visible as schema drift instead of a quietly valid empty schedule.

## Follow-Up Questions

The next useful investigation is whether this is Claude-specific, prompt-specific, or interaction-specific across Claude runs. The trace evidence here shows that Claude missed root-level authority in all five regional cases, while some other harnesses did not. A deeper sweep could count, across all tracked traces, which harnesses read `README.md`, which ran `verifier --help`, which ran the verifier on an empty or draft solution, which created a private verifier first, and whether those early actions predict nonzero `num_actions` and final score.
