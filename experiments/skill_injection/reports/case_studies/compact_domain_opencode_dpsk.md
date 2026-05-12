# Compact Domain / Opencode DPSK: Validity Discipline, Uneven Product Geometry

## Summary

`compact_domain/opencode_dpsk` is the clearest positive stereo-imaging signal in the skill-injection experiment, but it is not a clean "skill solves benchmark" result. The condition produced 5/5 verifier-valid submissions, three nonzero scores, and mean score `28.463224`. It also produced two verifier-valid zero-score cases. The evidence points to a narrow mechanism: the compact procedure helped the evaluated space agent establish the right authority workflow around `actions`, early skeleton validation, raw observations, and repeated verifier checks, but it did not guarantee that the private product builder would match the verifier's overlap, convergence, and pixel-scale geometry.

This case study is scoped only to `compact_domain/opencode_dpsk`. Aggregate rows are in `experiments/skill_injection/reports/stereo_imaging.md` and `results/agent_runs/experiments/skill_injection/summaries/runs.csv`. Causal claims below were checked against local replay artifacts: exported opencode traces, final `solution.json`, `run.json`, `agent_stdout.txt`, and `verifier_stdout.txt` under `results/agent_runs/experiments/skill_injection/default/compact_domain/stereo_imaging/opencode_dpsk/test/case_*/`. The internal roadmap evidence bundle recorded the trace sequence numbers cited here; this public report summarizes those signals rather than depending on the roadmap directory as the report destination.

## Aggregate Outcome

| Condition | Harness | Valid | Mean coverage | Mean quality | Mean score | Statuses |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `compact_domain` | `opencode_dpsk` | 5/5 | 0.3327 | 0.2846 | 28.46 | success: 4, timeout: 1 |
| `no_skill` | `opencode_dpsk` | 4/5 | 0.3487 | 0.2749 | 13.00 | success: 4, verifier_invalid: 1 |

The compact condition improved hard validity and shifted which cases scored. The no-skill DPSK control scored only on `case_0003` and had an invalid high-metric attempt on `case_0004`; compact-domain DPSK scored on `case_0001`, `case_0002`, and `case_0005`, made `case_0004` verifier-valid, but lost the no-skill `case_0003` score. This is a workflow and validity improvement, not a monotone geometry improvement.

| Case | No-skill DPSK score | Compact-domain DPSK score | Compact-domain final verifier diagnostic |
| --- | ---: | ---: | --- |
| `case_0001` | 0 | 9.98302 | 137 interpreted observations, 70 pair evaluations, 19 valid pairs, 0 violations. |
| `case_0002` | 0 | 90.3201 | 1150 interpreted observations, 948 pair evaluations, 575 valid pairs, 0 violations. |
| `case_0003` | 64.9751 | 0 | Timeout; 73 interpreted observations, 28 pair evaluations, 0 valid pairs, 0 violations. |
| `case_0004` | invalid, score 0 | 0 | 263 interpreted observations, 216 pair evaluations, 0 valid pairs, 0 violations. |
| `case_0005` | 0 | 42.013 | 206 interpreted observations, 175 pair evaluations, 99 valid pairs, 0 violations. |

The final submitted solutions all used the required raw-observation schema: a top-level `actions` array with action fields `type`, `satellite_id`, `target_id`, `start_time`, `end_time`, `off_nadir_along_deg`, and `off_nadir_across_deg`. That matters because the zero-score cases were not empty or silently unparsed submissions. They were legal schedules whose derived stereo products failed product rules.

The product diagnostics separate hard validity from scoring. In the local `run.json` verifier payloads, every compact-domain DPSK file had zero hard violations, but invalid pair checks failed for different geometry reasons:

| Case | Pair evaluations | Valid pairs | Invalid pairs with overlap below 0.5 | Invalid pairs with zero overlap | Invalid pairs with pixel-scale ratio above 1.5 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `case_0001` | 70 | 19 | 0 | 0 | 31 |
| `case_0002` | 948 | 575 | 1 | 0 | 287 |
| `case_0003` | 28 | 0 | 28 | 26 | 0 |
| `case_0004` | 216 | 0 | 216 | 216 | 1 |
| `case_0005` | 175 | 99 | 7 | 0 | 56 |

## What The Compact Skill Offered

The injected condition is defined in `experiments/skill_injection/conditions/compact_domain.yaml`: one skill, `stereo-imaging-compact-procedure`. The skill body in `experiments/_fragments/skills/skill_injection/stereo-imaging-compact-procedure/SKILL.md` tells the space agent to start with a valid `actions` skeleton, submit raw observations rather than pair claims, schedule candidate products atomically, seed broad target coverage, and diagnose valid-zero outputs as product-rule failures.

Trace evidence shows actual uptake. In all five compact-domain DPSK traces, the space agent read `/app/workspace/README.md`, opened the compact skill, and ran the packaged verifier. Representative examples:

| Case | README read | Compact skill read | First verifier signal | Final verifier signal |
| --- | --- | --- | --- | --- |
| `case_0001` | seq 13 | seq 6 | seq 28 | seq 563 |
| `case_0002` | seq 10 | seq 19 | seq 44 valid empty baseline after an earlier missing-file verifier error | seq 545 valid restored backup |
| `case_0003` | seq 12 | seq 16, plus skill example/reference at seq 22-23 | seq 29 | seq 600 |
| `case_0004` | seq 11 | seq 12 | seq 28 | seq 846 |
| `case_0005` | seq 9 | seq 17, plus skill example/reference at seq 24-25 | seq 23 | seq 724 |

The behavioral effect is acceptance discipline. The runs kept or recovered verifier-valid files even when optimization went sideways. `case_0002` is the cleanest example: after a late refinement made the file invalid with an insufficient slew/settle violation, the space agent restored `solution_bak.json` and revalidated a high-scoring file. `case_0003` timed out, but still left a valid incumbent. `case_0004` accepted a valid zero rather than submitting an invalid high-ambition schedule.

## Case Findings

### `case_0001`: Small Nonzero Recovery

`case_0001` moved from early schema/verifier contact to a small nonzero schedule. The final verifier payload reports 137 interpreted observations, 70 pair evaluations, 19 valid pairs, coverage `0.1338028169`, normalized quality `0.0998302230`, and no hard violations. A representative valid pair for `open_077` was cross-satellite, had overlap `1.0`, convergence `8.96 deg`, pixel-scale ratio `1.324`, and positive pair quality.

The limiting factor was product quality, not validity. Invalid pair diagnostics include failures from overlap below threshold, convergence outside the allowed range, and pixel-scale ratio above `1.5`. The trace shows repeated solver/verifier loops and a final compact verifier check at seq 563 with `Valid: True`, coverage around `0.1338`, and quality around `0.0997`.

### `case_0002`: Best-Case Skill Uptake

`case_0002` is the strongest positive case. The trace reads the README, opens the compact skill, establishes an empty valid baseline, then iterates with a Brahe-based access solver and frequent verifier checks. The final official run row records score `90.3201`, coverage `0.983471`, and normalized quality `0.903201`; the final `run.json` has 1150 interpreted observations, 948 pair evaluations, 575 valid pairs, and no violations.

This case also shows why the compact workflow mattered. A late verifier call reported an invalid schedule with an insufficient slew/settle gap: `sat_worldview_1` needed about `26.623s`, but the gap was `5.602s`. The trace then restored `solution_bak.json` and got `valid: True` with coverage around `0.9752` and normalized quality around `0.8996`. The final official metrics are slightly higher because the run artifact captures the final submitted solution, but both the trace-local check and final verifier diagnostics agree on the causal point: the space agent preserved a high-scoring valid incumbent and fell back when a refinement broke hard constraints.

### `case_0003`: Timeout With A Valid But Product-Zero Incumbent

`case_0003` ended with `agent_status=timeout`, exit code 124, and duration about `10000.7` seconds. It still produced a verifier-valid final file. That is a meaningful difference from a broken timeout: the compact workflow preserved an artifact the verifier could score.

The artifact had no objective value. Final diagnostics report 73 interpreted observations, 28 pair evaluations, 0 valid pairs, and 0 hard violations. All 28 evaluated pairs were below the overlap threshold, with 26 at `overlap_fraction = 0.0`, so the schedule was legal but did not create any recognized stereo product. The trace tail shows the space agent still debugging a boresight/sign convention problem and trying zero steering when time ran out. This is runtime/search incompleteness under a hard timeout, not a schema failure.

The no-skill control scored `64.9751` on the same case, so this case is the main counterexample to any blanket "compact skill solves DPSK" claim. The compact skill improved authority discipline, but the private geometry model still had to learn the verifier's product conventions quickly enough.

### `case_0004`: Valid Schedule, Zero Overlap

`case_0004` converted a no-skill invalid outcome into a hard-valid compact-domain outcome, but the score stayed zero. The final verifier diagnostics report 263 interpreted observations, 216 pair evaluations, 0 valid pairs, and 0 violations.

The root cause is explicit in verifier diagnostics: every evaluated pair had `overlap_fraction = 0.0`. The final stdout says the space agent believed it had verified target-pointing and timeline logic, but could not reconcile its footprint reasoning with the verifier's overlap computation. That is private product-model drift after good authority acquisition. The compact skill even names this class of failure: valid singles can score zero when they never form a valid stereo or tri-stereo product.

### `case_0005`: Mid-Quality Corrective Debugging

`case_0005` is the middle success: official score `42.013`, coverage `0.546099`, normalized quality `0.42013`. The trace starts with README and compact-skill reads, verifies a baseline, hits an invalid intermediate at seq 207, then progressively repairs the solution. Later trace-local verifier checks show valid nonzero schedules, including seq 689 with coverage around `0.5532` and quality around `0.4326`, and seq 700 with 101 valid pairs out of 175 evaluated pairs.

The final official verifier payload reports 206 interpreted observations, 175 pair evaluations, 99 valid pairs, and 0 violations. A representative same-satellite pair for `open_091` has overlap `0.93`, convergence `30.72 deg`, pixel-scale ratio about `1.001`, and positive pair quality. Remaining invalid pairs were not all overlap collapse; many failed pixel-scale or threshold details. This is the case where corrective debugging most visibly crossed from valid-zero to useful product generation.

## Root Cause

The compact procedure helped most where the failure mode was authority and workflow. It pushed the space agent toward reading the README, using the required raw-observation schema, keeping a valid baseline, inserting observations as products, and repeatedly consulting the packaged verifier. That explains the 5/5 validity row and the absence of schema-mismatch failures in compact-domain DPSK.

The compact procedure did not solve the hard product model. Scores still depended on whether the private access, boresight, footprint, convergence, pixel-scale, and timeline heuristics aligned with the verifier's derived stereo-product model before timeout. The two zero-score compact runs had real interpreted observations and pair evaluations, but zero valid products: `case_0003` had 73 observations and 28 evaluated pairs, all below the overlap threshold; `case_0004` had 263 observations and 216 evaluated pairs, all with exactly zero overlap. In both cases, hard validity passed while derived product quality failed completely.

The shortest diagnosis is: compact-domain skill injection made DPSK disciplined about validity and verifier contact, but normalized quality still depended on learning the verifier's geometry conventions.

## Implications

For interpreting skill injection, treat `compact_domain/opencode_dpsk` as a partial positive control. It shows that a compact procedural skill can change the reliability surface: all five submissions were valid, three became nonzero, and one no-skill invalid case became hard-valid. It should not be cited as proof that the skill alone teaches stereo geometry; `case_0003` regressed from a no-skill high score to a timeout-valid zero, and `case_0004` remained product-zero.

For follow-up work, the most targeted intervention is not another broad procedural skill. The traces suggest a verifier-facing product-debugging aid: summarize pair-evaluation failures by target and reason, especially overlap, convergence, and pixel-scale ratio. That would preserve the useful compact recipe while giving valid-zero runs a faster way to repair product geometry before timeout.
