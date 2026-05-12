# Skill Pack / Opencode DPSK: Product Awareness, Larger Search Surface

## Summary

`skill_pack/opencode_dpsk` produced one excellent stereo-imaging solution, one small nonzero solution, two verifier-valid weak or zero solutions, and one invalid final submission. The aggregate row is 5 runs, 4/5 valid, mean coverage `0.191297482`, mean normalized quality `0.185041434`, and mean score `18.5041434`, matching `results/agent_runs/experiments/skill_injection/summaries/runs.csv` and the rounded `18.50` row in `experiments/skill_injection/reports/stereo_imaging.md`.

The mechanism is not "more skills are worse." The traces show real uptake of the stereo product strategy skill and, in several cases, relevant Brahe and scheduling guidance. The problem is that the richer toolkit often led DPSK into larger candidate-generation, geometry-debugging, and solver-construction loops before it had a robust verifier-aligned incumbent. `case_0001` converted that machinery into a high score. `case_0002`, `case_0003`, `case_0004`, and `case_0005` show the other side: product awareness was present, but overlap modeling, access containment, timestamp, and slew/settle details still governed the final score.

This report is scoped only to `skill_pack/opencode_dpsk`. It uses aggregate rows from `experiments/skill_injection/reports/stereo_imaging.md` and `runs.csv`; trace sequence numbers from `roadmap/skill_injection_case_studies/evidence/traces/data/events/skill_pack__opencode_dpsk__test__case_*.js`; and final `run.json`, `solution.json`, and `verifier_stdout.txt` under `results/agent_runs/experiments/skill_injection/default/skill_pack/stereo_imaging/opencode_dpsk/test/case_*/`.

## Evidence Base

Primary aggregate numbers were recalculated directly from `results/agent_runs/experiments/skill_injection/summaries/runs.csv` and checked against the rounded table in `experiments/skill_injection/reports/stereo_imaging.md`. The Phase 1 inventory in `roadmap/skill_injection_case_studies/evidence/RUN_INVENTORY.md` independently records the same cell count and mean score for `skill_pack/opencode_dpsk`: 5 runs, 4 valid, mean score `18.504143`.

Behavior claims use exported trace events from `roadmap/skill_injection_case_studies/evidence/traces/data/events/skill_pack__opencode_dpsk__test__case_*.js`, with the broader signal digest in `roadmap/skill_injection_case_studies/evidence/TRACE_SIGNALS.md`. Final validity, action counts, pair counts, overlap failures, and hard violations use the corresponding `run.json` and `verifier_stdout.txt` files under `results/agent_runs/experiments/skill_injection/default/skill_pack/stereo_imaging/opencode_dpsk/test/case_*/`. The "valid pairs" and overlap-failure counts below are from verifier `diagnostics.pair_evaluations`, using `valid_pair`, `overlap_fraction < 0.8`, and `overlap_fraction == 0.0`.

## Aggregate Outcome

| Condition | Harness | Valid | Mean coverage | Mean quality | Mean score | Statuses |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `skill_pack` | `opencode_dpsk` | 4/5 | 0.1913 | 0.1850 | 18.50 | success: 3, timeout: 1, verifier_invalid: 1 |
| `compact_domain` | `opencode_dpsk` | 5/5 | 0.3327 | 0.2846 | 28.46 | success: 4, timeout: 1 |
| `no_skill` | `opencode_dpsk` | 4/5 | 0.3487 | 0.2749 | 13.00 | success: 4, verifier_invalid: 1 |

The skill-pack condition improved over no-skill DPSK on mean score because of `case_0001`, but it did not match compact-domain DPSK's validity or mean score. The compact report already noted that compact-domain DPSK's main improvement was validity discipline. Skill-pack DPSK had product awareness too, but it spent more runs in broad solver/debug loops and had one invalid final file.

| Case | Skill-pack score | Compact-domain score | No-skill score | Skill-pack final verifier diagnostic |
| --- | ---: | ---: | ---: | --- |
| `case_0001` | 90.3319 | 9.98302 | 0 | 295 observations, 147 pair evaluations, 131 valid pairs, 0 violations. |
| `case_0002` | 1.85877 | 90.3201 | 0 | 167 observations, 57 pair evaluations, 4 valid pairs, 0 violations. |
| `case_0003` | 0 | 0 | 64.9751 | 212 observations, 106 pair evaluations, 0 valid pairs, 0 violations. |
| `case_0004` | 0.330047 | 0 | invalid, score 0 | Timeout; 2 observations, 1 pair evaluation, 1 valid pair, 0 violations. |
| `case_0005` | 0 | 42.013 | 0 | Invalid; 278 observations, 139 pair evaluations, 0 valid pairs, 1 violation. |

All five final `solution.json` files used the correct raw-observation schema: top-level `actions`, with action fields `type`, `satellite_id`, `target_id`, `start_time`, `end_time`, `off_nadir_along_deg`, and `off_nadir_across_deg`. The failures were downstream of schema acquisition.

The final verifier diagnostics distinguish the cases:

| Case | Pair evaluations | Valid pairs | Invalid pairs below overlap threshold | Invalid pairs with zero overlap | Hard violations |
| --- | ---: | ---: | ---: | ---: | ---: |
| `case_0001` | 147 | 131 | 16 | 0 | 0 |
| `case_0002` | 57 | 4 | 53 | 44 | 0 |
| `case_0003` | 106 | 0 | 106 | 105 | 0 |
| `case_0004` | 1 | 1 | 0 | 0 | 0 |
| `case_0005` | 139 | 0 | 139 | 139 | 1 |

## What The Skill Pack Offered

The condition in `experiments/skill_injection/conditions/skill_pack.yaml` injected four skills: `python-optimization-for-search`, `ortools-cpsat-modeling`, `classical-or-scheduling-methods`, and `stereo-imaging-product-strategy`. The product skill says to keep product libraries small until a valid nonzero solution exists, diagnose valid-zero outputs through pair evaluations, and keep the best valid incumbent. The OR and optimization skills similarly emphasize pruning, fallback incumbents, and bounded search before exact modeling.

Trace evidence shows skill uptake, but not uniform use of all four skills:

| Case | Skills opened in trace | Verifier contact |
| --- | --- | --- |
| `case_0001` | `brahe`, `stereo-imaging-product-strategy`, `classical-or-scheduling-methods` at seq 23-25; `ortools available` checked at seq 35. | Empty baseline verifier at seq 111; final verifier at seq 576. |
| `case_0002` | `stereo-imaging-product-strategy` and `brahe` at seq 18-19. | Empty baseline at seq 25; final verifier at seq 706. |
| `case_0003` | `stereo-imaging-product-strategy` and `brahe` at seq 17-18. | First verifier at seq 44; final verifier at seq 679. |
| `case_0004` | `stereo-imaging-product-strategy`, `brahe`, and later `ortools-cpsat-modeling` at seq 5, 16, and 521. | First verifier at seq 213; final verifier at seq 557; run timed out. |
| `case_0005` | `brahe`, `stereo-imaging-product-strategy`, `ortools-cpsat-modeling`, `classical-or-scheduling-methods`, and `python-optimization-for-search`. | First verifier at seq 164; final verifier at seq 678. |

The important pattern is that skill-pack DPSK nearly always understood the contract as raw observations and derived products. Its failures came from the private solver not matching verifier geometry or schedule constraints soon enough, not from submitting pair claims or an uninterpretable schema.

## Case Findings

### `case_0001`: High Score From Product-First Iteration

`case_0001` is the positive example. The trace reads the README, loads product and scheduling skills, verifies an empty baseline at seq 111, and then iterates through candidate/product construction. Early solver output at seq 207 built `513496` pair products and scheduled all targets, but verifier checks exposed access failures. Later output at seq 397 built a smaller library of `13086` products, reached high coverage/quality, but remained invalid because of 27 slew/settle violations. The run then repaired schedule feasibility: seq 419 reports a valid schedule with coverage `0.8099` and quality `0.8014`; seq 548 reports a stronger valid schedule with coverage `0.9366`, quality `0.9265`, and zero violations.

The official final artifact is slightly lower than the trace-local final claim. The trace at seq 576 says `133/142` targets and quality `0.926505`; final `run.json` reports 131 valid pairs, coverage `0.9154929577`, normalized quality `0.9033189157`, and zero violations. The robust claim is therefore not the trace-local metric, but the mechanism: product-aware candidate building plus repeated verifier repair produced a high-quality valid incumbent.

### `case_0002`: Product Awareness, Low-Across Debugging, Low Final Coverage

`case_0002` read the product strategy and Brahe skills early and verified an empty skeleton at seq 25. It then spent a long run debugging why many legal-looking products failed overlap. The trace records several failed high-volume attempts, then a more targeted insight: at seq 629, a "low-across" candidate solution was valid with 4 covered targets, and seq 632 identifies the key progress as exact across-track steering for low-across targets. Subsequent local optimization added `rugged_041` at seq 685 and `open_063` at seq 698.

The final verifier artifact is valid but small: 167 observations, 57 evaluated pairs, 4 valid pairs in `run.json`, with score `1.85877`. The trace's late local check at seq 706 claimed 6 covered targets, but the official run row and final verifier payload are lower. The safe diagnosis is that the space agent found a real overlap-debugging direction, but did not convert it into broad product coverage before finalization.

### `case_0003`: Valid Schedule With Product-Zero Geometry

`case_0003` used the product and Brahe skills and maintained hard validity. The final official payload reports 212 observations, 106 evaluated pairs, 0 valid pairs, 0 violations, and score 0. The trace shows why this was not a schema problem: seq 563 confirms the correct action fields, seq 567 shows verifier-valid zero metrics, and seq 679 again reports `valid: true` with coverage and quality both zero.

The mechanism was private geometry drift. The trace repeatedly tries to correct off-nadir and propagation mismatches using verifier-derived observations. Seq 606 identifies an action-order bug between the solver's internal actions and verifier-derived observations; seq 614 briefly reaches one valid pair after sorting; later broader runs regress to zero valid pairs, with seq 667 reporting best overlap only `0.43`. The final answer at seq 686 explicitly says the file is valid but has 0% coverage because the solver could not reconcile its position/overlap model with verifier behavior. The final verifier confirms the objective failure: 105 of 106 invalid pairs have exactly zero overlap.

### `case_0004`: Timeout Preserved A Tiny Valid Baseline

`case_0004` is the timeout case. It read product and Brahe skills early, then loaded `ortools-cpsat-modeling` at seq 521 after earlier vectorized access and product-building attempts. The trace says the reason for considering CP-SAT was a desire for "a more systematic solution," but it immediately narrows back to preserving a proven valid pair. Seq 533 verifies a handcrafted baseline with coverage `0.0079365`, quality about `0.0031`, and no violations; seq 566 again reports a final one-target baseline with two actions.

The official final result matches that shape: timeout, verifier-valid, 2 observations, 1 evaluated pair, 1 valid pair, coverage `0.0079365079`, normalized quality `0.0033004735`, score `0.330047`. This is exactly the fallback-incumbent lesson from the injected skills, but at very small scale. The richer modeling path did not finish, but a tiny valid product survived the timeout.

### `case_0005`: Correct Schema, Invalid Final Schedule

`case_0005` is the main negative skill-pack DPSK outcome. It opened the four skill-pack skills plus the Brahe skill at seq 22-26. It generated large candidate libraries repeatedly: seq 160 reports `878128` candidate products, seq 633 reports `49040`, seq 640 reports `5380`, seq 651 reports `39220`, and seq 661 reports `86467`. Several trace-local runs achieved verifier-valid hard constraints but no products: seq 633 reports `Valid: True` with zero violations and 0 valid pairs, and seq 636 summarizes that state as valid hard constraints with 0 valid pairs and zero nonzero overlaps.

The final submitted file was worse than a valid zero incumbent: official `run.json` marks it invalid with 278 observations, 139 pair evaluations, 0 valid pairs, and one hard violation. The verifier violation is narrow but fatal: `sat_cartosat_2c` needed about `25.962s` of slew/settle gap and had `25.942s`, a shortfall of about `0.020s`. The trace sees this exact failure at seq 678 and tries to reason through the discrepancy at seq 681-697, but the final message at seq 698 accepts the 278-action file with one minor slew violation and 0 coverage. This is the clearest case where richer solver work did not preserve the best verifier-valid incumbent.

## Root Cause

The skill pack changed the failure mode from contract acquisition to solver discipline. In all five DPSK runs, final files used the right action schema and the traces show early product-strategy or Brahe contact. That is materially better than a schema-authority failure.

What remained hard was verifier-aligned product geometry and schedule repair. `case_0001` solved enough of the stack to produce a high score. `case_0002` found a few overlap-sensitive products but only 4 official valid pairs. `case_0003` and `case_0005` generated many legal observations whose derived pairs collapsed to zero overlap. `case_0004` fell back to one proven product before timeout. The final score distribution follows these verifier facts more closely than the number of skills loaded.

The richer toolkit also increased the search surface. The traces contain several large candidate/product loops before a stable incumbent: `case_0001` reached `513496` early pair products before pruning and repair; `case_0002` built `878128` candidate products in an early solver path; `case_0005` repeatedly generated tens of thousands of products and still finished with one hard violation. This does not prove the skills caused the failures. It does show that the space agent often pursued broad solver construction even though the skills themselves warned to keep product libraries small and preserve fallbacks.

## Implications

Treat `skill_pack/opencode_dpsk` as a mixed intervention. It can help: `case_0001` demonstrates strong product-aware scheduling and verifier repair, and `case_0004` shows a tiny fallback surviving timeout. It can also fail to pay for its complexity: broad candidate generation and late solver changes consumed runs where compact-domain DPSK either kept validity or found stronger final products.

The next experiment should not simply add more skills. The most targeted change would be an explicit "verifier-incumbent discipline" requirement in the prompt or runtime: after every nonzero valid verifier result, checkpoint it atomically and never submit a later file unless the packaged verifier proves it is valid and no worse. Pair that with a compact verifier-diagnostics summarizer for `diagnostics.pair_evaluations`, especially overlap and slew/settle failures, so product-aware search can repair the actual scorer rather than a private proxy.
