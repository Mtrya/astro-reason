# Stereo No-Verifier Failure Modes

This report covers the `stereo_imaging` no-verifier tier across both agent harnesses. The source-of-record aggregate rows are in `experiments/verifier_exposure/reports/stereo_imaging.md`. Behavioral evidence comes from tracked no-verifier trace exports under `experiments/verifier_exposure/reports/traces/data/events/`, especially:

- `none__stereo_imaging__codex__test__case_0002.js`
- `none__stereo_imaging__codex__test__case_0003.js`
- `none__stereo_imaging__codex__test__case_0004.js`
- `none__stereo_imaging__opencode_dpsk__test__case_0002.js`
- `none__stereo_imaging__opencode_dpsk__test__case_0003.js`
- `none__stereo_imaging__opencode_dpsk__test__case_0005.js`

The no-verifier workspace contract is `experiments/verifier_exposure/configs/none.yaml`: the space agent receives `README.md`, `AGENTS.md`, and `case/`, but no local verifier helper. The README fragment at `experiments/_fragments/prompts/stereo_imaging/README.default.md` is detailed, but it is still a textual contract. Exact parse behavior, action interpretation, hard validity, derived observations, pair construction, and scoring are implemented in `benchmarks/stereo_imaging/verifier/io.py` and `benchmarks/stereo_imaging/verifier/engine.py`.

## No-Verifier Rows

| System | Case | Overall Status | Verifier Status | Valid | Coverage | Quality | Score | Mode |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | --- |
| `codex` | `case_0001` | success | valid | true | 0.9577 | 0.9297 | 92.97 | control success |
| `codex` | `case_0002` | success | valid | true | 0 | 0 | 0.0000 | hard-valid product-empty |
| `codex` | `case_0003` | success | valid | true | 0 | 0 | 0.0000 | hard-valid product-empty |
| `codex` | `case_0004` | verifier_invalid | invalid | false | 0 | 0 | 0.0000 | hard-invalid |
| `codex` | `case_0005` | success | valid | true | 0.9716 | 0.9663 | 96.63 | control success |
| `opencode_dpsk` | `case_0001` | verifier_invalid | invalid | false | 0 | 0 | 0.0000 | hard-invalid |
| `opencode_dpsk` | `case_0002` | verifier_error | error | false | - | - | 0.0000 | timestamp parse error |
| `opencode_dpsk` | `case_0003` | verifier_error | error | false | - | - | 0.0000 | timestamp parse error |
| `opencode_dpsk` | `case_0004` | verifier_invalid | invalid | false | 0 | 0 | 0.0000 | hard-invalid |
| `opencode_dpsk` | `case_0005` | verifier_invalid | invalid | false | 0 | 0 | 0.0000 | hard-invalid |

The aggregate summary makes the harness split visible: no-verifier Codex is valid on 4/5 cases with mean score 37.92, while no-verifier DPSK is valid on 0/5 cases with two verifier errors and three verifier-invalid rows. The important point is not that no-verifier always fails. It is that, without an executable verifier, the failure surface expands from optimization quality into format parsing, hard validity, and product construction.

## Mode 1: Hard-Valid Product-Empty Schedules

Examples: Codex `case_0002` and `case_0003`.

Immediate symptom: the official aggregate marks both schedules hard-valid, but `coverage=0`, `quality=0`, and `score=0.0000`. In stereo, that means the submitted actions survived action-level validity and scheduling checks, but the verifier found no valid stereo or tri-stereo product for any target.

The traces show why this is a no-verifier-specific failure rather than a simple empty submission. In `none__stereo_imaging__codex__test__case_0002.js`, Codex finishes with 240 observation actions and says its local model estimates `120/121` targets covered and `normalized_quality` about `0.9913`. In `none__stereo_imaging__codex__test__case_0003.js`, Codex finishes with 311 observation actions, claims `120 / 121` targets covered under local checks, and reports no detected syntax, horizon, duration, or off-nadir violations. The aggregate rows disagree completely on product value, not on JSON presence or gross hard validity.

The tracked verifier source explains the split. `benchmarks/stereo_imaging/verifier/engine.py` first accepts actions into derived observations, then constructs valid products only when same-target observations satisfy product mode, midpoint separation, access membership, overlap, convergence, pixel-scale ratio, and tri-stereo anchor rules. The metrics at the end of `verify_solution` are computed only from `covered` targets and `per_target_best` product scores. A schedule can therefore be `valid=true` and still score zero when none of its accepted observations combine into valid products.

Controls: these cases are not impossible. The aggregate report records solver rows of 98.87/97.72 for `case_0002` and 95.72/91.76 for `case_0003`. Codex also scores 96.75 on opaque `case_0002`, 69.06 on opaque `case_0003`, 98.29 on transparent `case_0002`, and 93.58 on transparent `case_0003`. The failure mode is product-model drift: the private model produced plausible schedules, but without verifier feedback it could not tell that official product construction was empty.

## Mode 2: Hard-Invalid Schedules

Examples: Codex `case_0004`; DPSK `case_0001`, `case_0004`, and `case_0005`.

Immediate symptom: the aggregate rows have `verifier_status=invalid`, `valid=false`, and score zero. This differs from Mode 1 because the external verifier rejected the schedule on hard constraints before score mattered.

The trace pattern is still private authority drift. In `none__stereo_imaging__codex__test__case_0004.js`, Codex ends with 252 selected observations covering all 126 targets and a proxy normalized score of `0.9790`, while explicitly noting that no official verifier exists in the workspace. In `none__stereo_imaging__opencode_dpsk__test__case_0005.js`, DPSK ends with 838 observations, claims 140/141 targets covered, 137 targets with at least two observations, and says all basic validation checks passed. The aggregate report marks both invalid.

The DPSK `case_0001` and `case_0004` traces show the same shape even though they are not the phase's main trace set. DPSK `case_0001` reports 4314 observation actions, 142/142 targets covered, and zero basic constraint violations; DPSK `case_0004` reports 725 actions, all 126 targets covered, and zero format/constraint errors. Both are invalid in the aggregate.

The tracked verifier source shows why "basic validation" is insufficient for this benchmark. `benchmarks/stereo_imaging/verifier/engine.py` enforces same-satellite non-overlap and slew/settle gaps, then derives access membership using the verifier's target, boresight, solar, and interval computations. It can reject an action if the observation is not fully contained inside a continuous access interval, if the boresight misses the ellipsoid, if duration or off-nadir limits fail, or if same-satellite gaps are too short. A private checker can pass horizon, duration, ID, and rough access tests while still disagreeing with the official access and slew implementation.

Controls: hard invalidity is not inherent to these cases. Codex `case_0004` moves from invalid with no verifier, to valid low score with opaque exposure, to transparent score 90.62. DPSK `case_0005` moves from invalid with no verifier, to opaque valid-zero, to transparent score 94.05. Solver rows also score 92.38/85.32 for `case_0004` and 97.47/93.88 for `case_0005`. These controls separate case difficulty from authority acquisition.

## Mode 3: Timestamp Parse Errors

Examples: DPSK `case_0002` and `case_0003`.

Immediate symptom: the aggregate rows have `overall_status=verifier_error`, `verifier_status=error`, `valid=false`, and no coverage or quality metrics. This is not a geometry failure. It is a solution-loading failure.

The timestamp examples come from ignored local diagnostics, so they should be treated as diagnostic evidence rather than durable report artifacts. The stderr file for DPSK `case_0002`, `results/agent_runs/experiments/verifier_exposure/default/none/stereo_imaging/opencode_dpsk/test/case_0002/verifier_stderr.txt`, shows `solution.actions[1].start_time` rejected as `invalid ISO 8601 timestamp '2026-04-22T08:30:60Z'`. The stderr file for DPSK `case_0003` shows `solution.actions[62].end_time` rejected as `invalid ISO 8601 timestamp '2026-04-24T07:25:60Z'`.

The durable contract evidence is tracked. `experiments/_fragments/prompts/stereo_imaging/README.default.md` tells the space agent to use timezone-aware ISO 8601 timestamps and says a trailing `Z` is safest. `benchmarks/stereo_imaging/verifier/io.py` implements `_parse_iso_utc` with `datetime.fromisoformat` after translating `Z` to `+00:00`, and wraps parse failures as `invalid ISO 8601 timestamp`. Seconds equal to `60` are rejected by Python's datetime parser, which is why these rows become verifier errors before the engine can compute validity.

The traces show the missing control loop. In `none__stereo_imaging__opencode_dpsk__test__case_0002.js`, DPSK ends by saying the schedule is "fully valid", with 363 actions, 121/121 targets, and zero constraint violations. In `none__stereo_imaging__opencode_dpsk__test__case_0003.js`, DPSK says `solution.json` is ready with 248 observations, 121/121 targets, and "Zero validation errors". Those self-checks did not catch a syntactically invalid timestamp that the official loader rejects immediately.

Controls: transparent DPSK produces valid schedules for both timestamp-error cases, scoring 43.83 on `case_0002` and 73.00 on `case_0003`. Opaque exposure also avoids the parse-error status on both cases: `case_0002` becomes valid-zero and `case_0003` scores 64.98. This suggests an executable verifier mainly acts as a parser and schema guard for the timestamp mode, even when it does not guarantee high product quality.

## Why Codex Sometimes Succeeds Without A Verifier

Codex `case_0001` and `case_0005` are necessary controls. Both no-verifier rows are valid and high-scoring: 92.97 and 96.63. Their traces still show no local verifier run, but they read the README, load the `brahe` skill, implement a local model, and explicitly label their metrics as approximate because the hidden grader is unavailable.

Those successes narrow the claim. No-verifier exposure does not make stereo impossible. It makes exact authority alignment brittle. When the private model happens to match the official verifier closely enough on a case, Codex can succeed. When the private model's access, boresight, slew, overlap, convergence, or product assumptions diverge, the same no-verifier process can produce valid-zero or invalid schedules with confident local metrics.

DPSK's no-verifier pattern is different. Across all five cases, it reads the README and uses Brahe, but its final acceptance claims are stronger than the evidence supports: "fully valid", "100% coverage", "zero validation errors", or "all basic checks passed". The aggregate report shows none of those five submissions were accepted as valid. The issue is not absence of effort or absence of domain tooling; it is the lack of an authoritative executable check to discipline the private solver model before final submission.

## Controls For Synthesis

- Separate hard validity from score. Codex `case_0002` and `case_0003` prove `valid=true` can still mean product-empty and score zero.
- Separate verifier errors from invalid schedules. DPSK `case_0002` and `case_0003` fail in the loader, not in geometry scoring.
- Treat private metrics as hypotheses. The traces repeatedly report high coverage and zero local violations on rows where the aggregate says zero or invalid.
- Use opaque and transparent rows as exposure controls, not as proof that source is always needed. Opaque exposure is enough to catch timestamp parse errors, while transparent source is more important for aligning the stereo product model.
- Use Codex `case_0001` and `case_0005` as no-verifier success controls. The no-verifier failure thesis is about authority fragility, not blanket inability.

## Bottom Line

The no-verifier stereo tier fails in three distinct ways: accepted actions with no valid products, hard-invalid schedules, and malformed timestamps that never reach scoring. All three are visible in the aggregate report, and the traces show a common mechanism: private solver validation becomes the final authority because no local verifier helper is available. The controls show why the result is not just case difficulty. The same cases are solvable by solver baselines and often improve sharply under opaque or transparent exposure.
