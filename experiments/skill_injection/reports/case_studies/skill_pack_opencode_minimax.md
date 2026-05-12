# Skill Pack / Opencode Minimax: Better Contract Contact, Still Zero Products

## Summary

`skill_pack/opencode_minimax` is the split-pair counterpart to `compact_domain/opencode_minimax`. Recomputed from `results/agent_runs/experiments/skill_injection/summaries/runs.csv`, it has 5 runs, 3 verifier-valid submissions, mean coverage `0.0`, mean normalized quality `0.0`, and mean score `0.0`. Its statuses are success: 3 and verifier_invalid: 2.

The condition-specific diagnosis is downstream of compact-domain minimax. The multi-skill toolkit usually pushed Minimax closer to the actual contract: the traces show product-strategy skill use, README reads in several runs, verifier-help checks, and final `type: "observation"` actions in cases `case_0003`, `case_0004`, and `case_0005`. But the private access and schedule model still did not produce verifier-scoring stereo products. The final outcomes were two valid empty schedules, one valid observation schedule with no valid stereo pair, and two invalid hard schedules.

This is still an extension of the existing Minimax pattern in `experiments/main_agentic/reports/case_studies/minimax_cross_benchmark_failure.md`: verifier contact exists, but verifier discipline is not strong enough to reorganize the solver. The skill pack changed the failure mode from mostly wrong submitted contract to right-ish contract with wrong mission schedule.

## Evidence Base

Aggregate numbers come from `results/agent_runs/experiments/skill_injection/summaries/runs.csv` and match the rounded `skill_pack/opencode_minimax` row in `experiments/skill_injection/reports/stereo_imaging.md`. The Phase 1 inventory in `roadmap/skill_injection_case_studies/evidence/RUN_INVENTORY.md` records the same cell as 5 runs, 3 valid, mean score `0`.

Behavior claims use `roadmap/skill_injection_case_studies/evidence/traces/data/events/skill_pack__opencode_minimax__test__case_*.js` and the signal digest in `roadmap/skill_injection_case_studies/evidence/TRACE_SIGNALS.md`. Final action schemas, derived-observation counts, pair counts, and hard violations use `run.json`, `solution.json`, and `verifier_stdout.txt` under `results/agent_runs/experiments/skill_injection/default/skill_pack/stereo_imaging/opencode_minimax/test/case_*/`.

Skill evidence comes from `experiments/skill_injection/conditions/skill_pack.yaml`, which injects `python-optimization-for-search`, `ortools-cpsat-modeling`, `classical-or-scheduling-methods`, and `stereo-imaging-product-strategy`. The most frequently used relevant guidance is in `experiments/_fragments/skills/skill_injection/stereo-imaging-product-strategy/SKILL.md`: legal singles do not score, valid-zero means no products were derived, invalid schedules must be repaired before product metrics matter, and the best valid incumbent should be preserved.

## Aggregate Outcome

| Condition | Harness | Runs | Valid | Mean coverage | Mean quality | Mean score | Statuses |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `skill_pack` | `opencode_minimax` | 5 | 3 | 0.0 | 0.0 | 0.0 | success: 3, verifier_invalid: 2 |
| `compact_domain` | `opencode_minimax` | 5 | 5 | 0.0 | 0.0 | 0.0 | success: 5 |
| `no_skill` | `opencode_minimax` | 5 | 1 | 0.0 | 0.0 | 0.0 | success: 1, verifier_error: 3, verifier_invalid: 1 |

These rows were recalculated from `runs.csv`. The skill pack improved over no-skill minimax on parser/verifier reach, but all three minimax conditions still had zero mean coverage, zero mean normalized quality, and zero mean score.

| Case | Status | Score | Final actions | Interpreted observations | Pair evaluations | Valid pairs | Violations | Immediate outcome |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `case_0001` | success / valid | 0 | 0 | 0 | 0 | 0 | 0 | valid empty schedule |
| `case_0002` | success / valid | 0 | 0 | 0 | 0 | 0 | 0 | valid empty schedule |
| `case_0003` | success / valid | 0 | 24 | 24 | 1 | 0 | 0 | legal observations, no valid stereo product |
| `case_0004` | verifier_invalid / invalid | 0 | 720 | 720 | 19 | 0 | 676 | invalid hard schedule |
| `case_0005` | verifier_invalid / invalid | 0 | 58 | 58 | 0 | 0 | 29 | invalid hard schedule |

The invalid cases explain why Phase 2 split minimax into two reports. Compact-domain minimax was valid because nothing was interpreted. Skill-pack minimax often was interpreted, and that exposed downstream access, overlap, and slew/settle failures.

## What The Skill Pack Offered

The product-strategy skill directly describes the failure modes that appear here. It says the score comes from derived products, a legal single observation gives no coverage by itself, valid-zero means no valid products were derived, and invalid schedules must fix hard violations before product metrics matter. It also advises keeping product libraries small and preserving the best valid file.

Trace evidence shows actual uptake of at least part of this surface. `case_0001` reads the product strategy skill early and checks verifier help at seq 28; `case_0002` opens product strategy at seq 5, reads the README at seq 19, checks verifier help at seq 34, and later opens Brahe at seq 38; `case_0003` opens product strategy at seq 16, reads the README at seq 26, opens Brahe at seq 40, and reads Brahe access documentation at seq 48; `case_0004` opens product strategy at seq 4, checks verifier help at seq 28, reads the README at seq 32, and reads the product-ranking example at seq 40; `case_0005` opens product strategy and Brahe at seq 15-16, checks verifier help at seq 35, verifies an empty baseline at seq 39, and reads the README later at seq 447.

The missing piece was not total skill avoidance. It was the failure to make verifier results govern the final schedule after the solver started producing empty, invalid, or product-zero outputs.

## Case Findings

### `case_0001`: Long Solver Attempt, Empty Final

`case_0001` is a valid empty schedule after a long attempt. Phase 1 records README read at seq 328, first verifier run at seq 608, and final verifier run at seq 776. The final `solution.json` contains 0 actions; `run.json` reports 0 interpreted observations, 0 pair evaluations, no violations, coverage `0.0`, normalized quality `0.0`, and valid `true`.

This is not a schema-mismatch file like compact-domain `case_0001`. It is the skill-pack version of strategic retreat: after access and solver attempts, the final artifact is the known-safe empty baseline. It satisfies hard validity but creates no target product.

### `case_0002`: Fast Empty Outcome After Authority Contact

`case_0002` has the shortest skill-pack minimax duration in `runs.csv`: `1110.04` seconds. The trace opens product strategy at seq 5, reads the README at seq 19, checks verifier help at seq 34, and opens Brahe at seq 38. The final artifact is still `{"actions": []}`. Official diagnostics report 0 observations, 0 pair evaluations, 0 violations, and zero metrics.

The result shows that authority contact alone is insufficient. Minimax learned the expected shape and the verifier interface, but did not produce even a weak nonempty observation pair before finalization.

### `case_0003`: Correct Schema, Legal Singles, No Product

`case_0003` is the closest skill-pack minimax came to a meaningful schedule. It uses contract-complete action rows with `type`, `satellite_id`, `target_id`, `start_time`, `end_time`, and boresight fields. The final verifier interpreted all 24 actions, found no hard violations, evaluated 1 pair, and found 0 valid pairs. That yields valid `true`, coverage `0.0`, normalized quality `0.0`, and score 0.

The trace shows substantial authority and domain work: product strategy at seq 16, README at seq 26, Brahe at seq 40, access docs at seq 48, first verifier run at seq 320, verifier help at seq 900, and final verifier at seq 1180. It also shows the private model struggling with access and off-nadir conventions: seq 447 reasons about "observation is not fully contained inside a continuous access interval"; seq 776 writes a zero-action fallback during debugging; seq 935 says the solver is still finding combined angles around 60-68 degrees when it expected valid observations.

The final outcome is therefore not contract failure. It is legal-single/product failure: Minimax created a small hard-valid observation schedule, but it did not create a same-target pair that passed overlap and product rules.

### `case_0004`: Interpreted But Invalid At Scale

`case_0004` is a large invalid schedule. The trace opens product strategy at seq 4, checks verifier help at seq 28, reads the README at seq 32, and reads the product-ranking example at seq 40. It generates a large action file; seq 608 reports 720 total actions, and seq 644 runs the verifier on the final shape.

The official verifier interpreted all 720 actions and evaluated 19 pairs, but found 0 valid pairs and 676 hard violations. The violations are dominated by access containment: 661 actions are not fully contained inside a continuous access interval, and 15 violations are insufficient slew/settle gaps. The first violation examples include insufficient gaps such as `need ~2.626s, gap 1.000s` and `need ~2.887s, gap 2.000s`.

This is the clearest downstream failure. The output schema was right enough to be interpreted, but the private access schedule did not match the verifier's access intervals or same-satellite transition rules.

### `case_0005`: Valid Empty Baseline Replaced By Invalid Observations

`case_0005` shows both the positive and negative sides of skill-pack minimax. It opens product strategy and Brahe at seq 15-16, checks verifier help at seq 35, and verifies an empty action file at seq 39 with valid `true`, coverage `0.0`, normalized quality `0.0`, empty derived observations, and empty pair evaluations. That valid baseline was available early.

The final file replaced that baseline with 58 contract-schema observation actions. The verifier interpreted all 58, evaluated 0 pairs, and reported 29 hard violations. Every violation is an action not fully contained inside a continuous access interval. The trace recognizes this: seq 575 prints 54 access-containment violations in an intermediate file, seq 578 explains the issue, and the final message at seq 942 says the saved solution has 58 observations, is invalid due to timing constraints with access windows, and forms 0 pair evaluations.

This is the exact failure mode the product-strategy skill warned about: preserve the best valid file and repair hard constraints before treating product work as meaningful. Minimax had the valid empty incumbent, but submitted the invalid nonempty schedule.

## Valid Zero Versus Invalid Zero

The three valid skill-pack minimax outputs are not identical. `case_0001` and `case_0002` are empty. `case_0003` contains legal observations, but only 1 evaluated pair and 0 valid pairs. All three score zero, but only `case_0003` reaches the product-geometry stage.

The two invalid outputs are different again. `case_0004` is a large interpreted schedule with 676 hard violations, mostly access containment, plus 15 slew/settle failures. `case_0005` is a smaller interpreted schedule with 29 access-containment failures and no pair evaluations. In both, the official score is zero because invalidity blocks useful objective credit, and the product diagnostics show no valid pairs anyway.

This is why the report is split from compact-domain minimax. The compact condition never produced interpreted observations. The skill-pack condition often did, which means the failure moved from contract authority to verifier-aligned access and schedule construction.

## Relationship To The Main-Agentic Minimax Diagnosis

The existing main-agentic minimax study diagnoses "verifier contact without verifier discipline." Skill-pack minimax is an almost literal example. The traces show verifier help, README reads, and local verifier output, but the final behavior still follows a private solver model after the verifier exposes empty, zero, or invalid states.

The skill pack did improve one part of the workflow relative to compact-domain minimax: final files in `case_0003`, `case_0004`, and `case_0005` use the required raw-observation schema. But schema contact is not enough. Stereo scoring depends on derived products under access, overlap, convergence, pixel-scale, and same-satellite transition rules. Minimax did not keep the packaged verifier in the loop strongly enough to make those constraints govern candidate generation.

## Root Cause

The root cause for this condition is solver-model and schedule-quality failure after partial authority acquisition. Minimax often found the right documents and wrote the right kind of action rows, but its private access model produced empty schedules, observations that did not pair, or observations outside verifier access intervals. When the verifier contradicted the private model, Minimax usually debugged locally but did not simplify back to a small, verifier-valid, nonzero product-building loop.

The skill pack may have changed the work surface by encouraging richer product and access modeling, but the evidence does not support a generic "more skills are worse" claim. The stronger claim is narrower: richer skills helped Minimax reach the correct schema more often, yet did not fix its incumbent discipline or verifier-aligned access modeling.

## Implications

For skill injection, `skill_pack/opencode_minimax` is a partial positive control and a negative outcome at the same time. It shows that a multi-skill surface can move Minimax beyond schema invention. It also shows that stereo-imaging success requires more than product awareness: the solver must preserve a verifier-valid incumbent and only widen from candidates that the packaged verifier can interpret and score.

The best follow-up intervention is not another broad optimization skill. It is a hard verifier-incumbent rule: after every verifier-valid nonempty or empty baseline, checkpoint it atomically; never submit a later file unless the packaged verifier proves it is valid and no worse on the official metrics. Pair that with a tiny diagnostic loop that summarizes `derived_observations`, `pair_evaluations`, access-containment violations, and slew/settle failures before any large candidate generation.
