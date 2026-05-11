# Regional Coverage Claude Case Study: Missed Authority And Self-Verification

This note examines the two `claude_code` regional coverage runs that are present in the `main_agentic` aggregate report:

- `regional_coverage / claude_code / test / case_0001`
- `regional_coverage / claude_code / test / case_0002`

Both runs were reported as successful and valid, but both scored zero weighted coverage in the benchmark aggregate. The immediate score collapse was an output schema mismatch, but that is only the symptom. The deeper failure is that Claude did not acquire the local benchmark authority before solving: it did not read the workspace `README.md`, did not use the workspace `verifier`, inferred the solution interface from case files, and then built a private solver/verifier loop around that inferred interface.

## Evidence Base

This case study is anchored to tracked repository artifacts, not to ignored `results/*` run directories. The aggregate scores come from `experiments/main_agentic/reports/regional_coverage.md`. The behavioral evidence comes from the tracked trace exports `experiments/main_agentic/reports/traces/data/events/regional_coverage__claude_code__test__case_0001.js` and `experiments/main_agentic/reports/traces/data/events/regional_coverage__claude_code__test__case_0002.js`. The intended workspace assembly is in `experiments/main_agentic/benchmarks/regional_coverage.yaml`, which copies `experiments/_fragments/prompts/regional_coverage/README.default.md` to `/app/workspace/README.md` and the opaque verifier artifact to `/app/workspace/verifier`. The scoring and parsing behavior is in `benchmarks/regional_coverage/verifier.py`.

The ignored run outputs are useful for ad hoc local debugging, but the report should not depend on them as stable citations. The trace exports already contain the critical evidence: the initial prompt, Claude's file-discovery choices, its generated validation commands, its schema checks, and its final coverage claims.

## Aggregate Outcome

The regional coverage report counts only two `claude_code` cases:

| Case | Valid | weighted_coverage_ratio | coverage_ratio | num_actions |
| --- | --- | ---: | ---: | ---: |
| `case_0001` | true | 0.0000 | 0.0000 | 0 |
| `case_0002` | true | 0.0000 | 0.0000 | 0 |

The important diagnostic is `num_actions=0`, not just the zero coverage. Claude's traces show it believed it wrote nonempty schedules: `case_0001` printed 64 actions in `solution.json`, and `case_0002` printed 55 actions in `solution.json`. The benchmark verifier nevertheless counted zero parsed strip observations.

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

In both Claude traces, the first exploration command is `ls /app/workspace/case/`. The result lists exactly the case data files: `coverage_grid.json`, `manifest.json`, `regions.geojson`, and `satellites.yaml`. Claude then reads the manifest, satellites, regions, and grid. It does not first list `/app/workspace`, does not read `/app/workspace/README.md`, and does not run `/app/workspace/verifier --help`.

That matters because the four case files describe the physical instance, not the submission interface. They contain time horizons, TLEs, sensor limits, regions, and grid samples. They do not define the JSON action schema with `type: "strip_observation"` and `roll_deg`. Once Claude chose to look only inside `case/`, it had enough information to invent a plausible scheduling model but not enough information to know the benchmark-facing output contract.

The short task prompt likely contributed to the attention trap: it says, "Please solve the prepared regional strip-coverage case using the files in `case/`" and "Write `solution.json` at the workspace root." That is compatible with reading the root README, but it makes `case/` the salient place to start. Claude followed that salience literally and never recovered the stronger local authority sitting one directory above.

## Contract Drift

Claude submitted an internally plausible but benchmark-invisible schema:

- In `case_0001`, the trace prints actions with `satellite_id`, `start_time`, `end_time`, and `roll_angle_deg`, with no `type`, no `duration_s`, and no `roll_deg`.
- In `case_0002`, the trace's final assertion checks `duration_s` and `roll_angle_deg`, with no assertion for `type` or `roll_deg`.

The names Claude chose are natural if the model is reasoning from first principles: observations often have a start/end interval, and `roll_angle_deg` is a descriptive name for attitude. But the benchmark contract is intentionally narrower: it wants duration, not end time, and `roll_deg`, not a generic roll-angle field. The verifier then derives end time, strip geometry, and coverage itself.

Because `type` was absent, the benchmark did not parse these rows as strip observations. The result is a valid empty schedule: no parsed actions, no schedule violations, no coverage. This is why the aggregate report shows `valid=true` and `num_actions=0`.

## Self-Validation

Claude did not merely forget a field at the final write step. It created validation routines that reinforced the wrong contract.

In `case_0001`, Claude's final "validation" is an inline Python script that asserts `spec_version == "v1"`, `case_id == "case_0001"`, `len(actions) == 64`, and then checks that each action has `satellite_id`, `start_time`, `end_time`, and `roll_angle_deg`. It validates edge off-nadir using `roll_angle_deg`, checks timing from `start_time` to `end_time`, and prints "Validation passed!" The next check says all actions are within horizon and "valid", but its time-grid condition is `if dur % 10 != 0 and dur % 5 != 0`, which lets 5-second-aligned durations pass even though the case action grid is 10 seconds.

In `case_0002`, the final quick validation again checks `duration_s` and `roll_angle_deg`. It prints "All constraints satisfied" after asserting `20 <= duration_s <= 180` and `-40 <= roll_angle_deg <= 40`. The benchmark action schema requires `roll_deg`, and the sensor max duration in the cases is 120 seconds, not 180 seconds. So the validation was not just incomplete; it was a separate contract.

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

The root-root-cause is not simply that Claude used `roll_angle_deg` instead of `roll_deg`. It is that Claude failed to establish the hierarchy of authority in the prepared workspace.

There were three possible authorities available: the short user prompt, the root README plus verifier, and the case files. The correct hierarchy is README/verifier first, case files second, solver heuristics third. Claude inverted that hierarchy. It obeyed the short prompt's salient phrase "using the files in `case/`", treated the case files as enough to reconstruct the task, and then used its own scripts as the authority for both schema and scoring.

This is a recognizable agent failure mode on scientific optimization tasks. The task looks like a modeling problem, so the model enters "build a simulator" mode early. Once a simulator exists, every subsequent check asks whether the solution is consistent with that simulator. The local verifier would have collapsed the error immediately by reporting `num_actions=0`, but Claude's workflow never routed through it.

The trace also shows how the failure compounds. After the first invented schema appears, later scripts and assertions reuse it. The names become part of the local ecosystem: solvers emit `roll_angle_deg`, validators assert `roll_angle_deg`, debug scripts print `roll_angle_deg`, and final messages summarize proxy coverage. At that point, the model is no longer merely missing a README detail; it is living inside a self-consistent alternate benchmark.

## Comparison With Other Harness Traces

The contrast with stronger regional coverage traces supports this interpretation. In the tracked `codex` trace for `case_0001`, the agent lists `/app/workspace`, sees `README.md`, `verifier`, `AGENTS.md`, and `case/`, reads `README.md`, checks `./verifier --help`, writes an empty `solution.json`, and runs `./verifier case/ solution.json` before building the solver. In the tracked `kimi_cli` trace for `case_0001`, the agent's first stated plan is to read the README, it reads `/app/workspace/README.md`, checks `/app/workspace/verifier`, and runs `./verifier --help`.

This difference is not about orbital mechanics talent. It is about the first few minutes of tool discipline. The agents that inspected the root workspace acquired the output schema and local verifier before optimizing. Claude inspected only `case/`, so it optimized under a guessed interface.

The same pattern also explains Claude's much better `aeossp_standard` results. In the tracked AEOSSP traces for `case_0001` through `case_0004`, Claude does list the root workspace, read `/app/workspace/README.md`, and run the local verifier repeatedly; its high WCR values there are mostly verifier-guided, not accidental. The exception is `aeossp_standard / claude_code / case_0005`: Claude again skips README and verifier, writes a top-level `observations` array instead of the required `actions` array with `type: "observation"`, self-validates that private schema, and receives an official valid-empty score of zero. This cross-benchmark contrast sharpens the root cause: Claude succeeds when it binds to README plus verifier early, and fails quietly when it treats case files and self-checks as the authority.

## Implications

For evaluation interpretation, the `claude_code` regional coverage result should not be summarized as "Claude cannot find regional coverage schedules." The better reading is: these runs failed to bind to the benchmark contract and then self-validated against an invented evaluator. In a benchmark where the local verifier is the intended authority, that is a first-order failure.

For prompt and harness design, the fix is not mainly to explain SGP4 geometry more thoroughly. The README already explains the action contract and the verifier already encodes the scoring geometry. The important intervention is to force authority acquisition before optimization. A stronger task prompt would say: "Start by reading `/app/workspace/README.md`; run `/app/workspace/verifier --help`; before finishing, run `/app/workspace/verifier case/ solution.json` and use its reported `num_actions` and metrics." The workspace rule could also explicitly say that `case/` contains instance data, while `README.md` and `verifier` define the submission contract.

For benchmark diagnostics, it may be worth adding a warning when `solution.actions` is non-empty but no `strip_observation` actions are parsed. That would preserve the current rule that unknown action types do not create coverage, while making this exact failure mode visible as schema drift instead of a quietly valid empty schedule.

## Follow-Up Questions

The next useful investigation is whether this is Claude-specific or prompt-specific across Claude runs. The trace evidence here shows that Claude missed root-level authority in these two cases, while some other harnesses did not. A deeper sweep could count, across all tracked traces, which harnesses read `README.md`, which ran `verifier --help`, which ran the verifier on an empty or draft solution, and whether those early actions predict nonzero `num_actions` and final score.
