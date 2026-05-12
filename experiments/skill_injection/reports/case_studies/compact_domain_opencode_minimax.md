# Compact Domain / Opencode Minimax: Skill Read, Contract Not Acquired

## Summary

`compact_domain/opencode_minimax` is the all-valid, all-zero minimax skill-injection cell. Recomputed from `results/agent_runs/experiments/skill_injection/summaries/runs.csv`, it has 5 runs, 5 verifier-valid submissions, mean coverage `0.0`, mean normalized quality `0.0`, and mean score `0.0`. The headline is therefore not hard invalidity. It is verifier-valid zero output.

The root cause is condition-specific: the compact skill was available and often read, but Minimax did not reliably acquire the workspace output contract. Four final files contain action-like objects with target, satellite, and time fields, but no `type: "observation"` action and no contract-complete `end_time` plus boresight fields. The verifier therefore derived zero observations, zero pair evaluations, and zero violations. The fifth case repaired a schema error only as far as `{"actions": []}`, also valid and zero.

This is the schema-authority side of the broader Minimax pattern described in `experiments/main_agentic/reports/case_studies/minimax_cross_benchmark_failure.md`: the model built a private solver or private validator, then treated that private result as the mission answer even when the local README/verifier contract had not been established.

## Evidence Base

Aggregate numbers come from `results/agent_runs/experiments/skill_injection/summaries/runs.csv` and match the rounded `compact_domain/opencode_minimax` row in `experiments/skill_injection/reports/stereo_imaging.md`. The Phase 1 inventory in `roadmap/skill_injection_case_studies/evidence/RUN_INVENTORY.md` independently records this cell as 5 runs, 5 valid, mean score `0`.

Trace claims use `roadmap/skill_injection_case_studies/evidence/traces/data/events/compact_domain__opencode_minimax__test__case_*.js` and the signal digest in `roadmap/skill_injection_case_studies/evidence/TRACE_SIGNALS.md`. Final action schemas and verifier diagnostics use the matching `run.json`, `solution.json`, and `verifier_stdout.txt` files under `results/agent_runs/experiments/skill_injection/default/compact_domain/stereo_imaging/opencode_minimax/test/case_*/`.

Contract evidence comes from `experiments/_fragments/prompts/stereo_imaging/README.default.md`, which says the required top-level field is `actions`, each interpreted action must have `type: "observation"`, and stereo products are derived by validation. The injected compact skill in `experiments/_fragments/skills/skill_injection/stereo-imaging-compact-procedure/SKILL.md` also says to write a minimal `actions` skeleton, submit raw observations, and validate often.

## Aggregate Outcome

| Condition | Harness | Runs | Valid | Mean coverage | Mean quality | Mean score | Statuses |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `compact_domain` | `opencode_minimax` | 5 | 5 | 0.0 | 0.0 | 0.0 | success: 5 |
| `skill_pack` | `opencode_minimax` | 5 | 3 | 0.0 | 0.0 | 0.0 | success: 3, verifier_invalid: 2 |
| `no_skill` | `opencode_minimax` | 5 | 1 | 0.0 | 0.0 | 0.0 | success: 1, verifier_error: 3, verifier_invalid: 1 |

These rows were recomputed from `runs.csv`. Compact-domain minimax improved validity relative to the no-skill minimax condition, but it did not improve the objective. The validity gain mostly came from submitting files the verifier could accept as having no interpreted observations, not from producing valid stereo products.

| Case | Status | Score | Final actions | Interpreted observations | Pair evaluations | Violations | Final schema pattern |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `case_0001` | success / valid | 0 | 216 | 0 | 0 | 0 | `satellite_id`, `target_id`, `start_time`, `duration_s`; no `type` |
| `case_0002` | success / valid | 0 | 14 | 0 | 0 | 0 | `satellite_id`, `target_id`, `start_time`, `duration`; no `type` |
| `case_0003` | success / valid | 0 | 156 | 0 | 0 | 0 | `satellite_id`, `target_id`, `start`, `end`; no `type` |
| `case_0004` | success / valid | 0 | 1120 | 0 | 0 | 0 | `satellite_id`, `target_id`, `start_time`, `duration`; no `type` |
| `case_0005` | success / valid | 0 | 0 | 0 | 0 | 0 | empty `actions` array |

## What The Compact Skill Offered

The compact skill was relevant and direct. It told the space agent to start with a minimal `actions` array, add raw observations in small batches, insert products atomically, and diagnose valid-zero schedules as legal singles that fail product rules. If followed together with the README, it should have pushed Minimax toward schema-correct raw observation rows and verifier checks.

Trace evidence shows the skill was visible and usually opened: `case_0001` opens `stereo-imaging-compact-procedure` at seq 4, `case_0002` at seq 16, `case_0003` at seq 15, `case_0004` at seq 12, and `case_0005` at seq 5. Several runs also read the compact skill example or reference. Skill presence did not become contract discipline.

## What Minimax Actually Did

The first four compact-domain minimax runs built a private schedule representation rather than the README action schema. `case_0001` generated action-like rows and at seq 449 reported "Validation passed! 216 actions, 108 targets" from a private validation script. The final assistant message claimed 216 actions, 108 stereo products, 108 targets, no timeline conflicts, and proper timestamps. The official verifier, however, derived 0 observations and 0 pair evaluations because the submitted rows lacked `type: "observation"` and contract-complete fields.

`case_0002` is similar but with some verifier contact. It listed the workspace at seq 4, checked verifier help at seq 26, wrote and verified an empty baseline at seq 39, then ended with 14 action-like rows and a private "7 products" claim at seq 512 and seq 544. The final `solution.json` still used `duration`, not `end_time`, and lacked `type`, boresight fields, and interpreted observations. The verifier accepted the file as valid zero.

`case_0003` opened the compact skill and Brahe, then wrote a solver around access windows and products. The final file had 156 action-like rows with `start` and `end`, not the required `start_time`, `end_time`, `type`, and boresight fields. The run did not show root README or packaged verifier use in the Phase 1 trace signals. Official diagnostics again show 0 interpreted observations and 0 pair evaluations.

`case_0004` had more authority contact than `case_0003`: it found `README.md` and `verifier` in a workspace glob, opened the compact skill, and checked verifier help at seq 26. It also verified an empty baseline at seq 34. But its final file contained 1120 rows with `start_time` and `duration` and no `type: "observation"`. The verifier-valid result still meant no interpreted actions, not a solved stereo schedule.

`case_0005` is the only compact-domain minimax run where verifier feedback forced a contract correction all the way to top-level `actions`. The trace reads the compact skill, its example, and its reference; seq 36 runs verifier help, seq 40 validates a minimal file, and seq 48 verifies `{"actions": []}` after an earlier top-level `schedule` schema error. The final file stayed empty, so the outcome remained valid zero.

## Why Validity Was Misleading

The verifier diagnostics are decisive: every compact-domain minimax final artifact has `derived_observations` length 0 and `diagnostics.pair_evaluations` length 0. Four files contain many action-like objects, but the README says actions with a non-`"observation"` type are ignored and the required action fields include `end_time`, `off_nadir_along_deg`, and `off_nadir_across_deg`. Since these files produced no interpreted observations, there were no hard observation violations to report and no stereo products to score.

This distinction matters because a valid empty or uninterpreted schedule is different from a legal observation schedule with bad product geometry. Compact-domain minimax mostly failed before product geometry. It did not get far enough for overlap, convergence, or pixel-scale ratio to become the official bottleneck.

## Comparison To Skill-Pack Minimax

The paired `skill_pack/opencode_minimax` report shows a different failure surface. Skill-pack minimax also scored zero, but cases `case_0003`, `case_0004`, and `case_0005` used `type: "observation"` rows that the verifier interpreted. Its failures moved downstream into empty schedules, legal observations with no valid pair, and invalid access/slew schedules.

Compact-domain minimax is therefore not evidence that the compact stereo procedure was harmful to geometry search. It is evidence that reading a compact procedural skill did not force Minimax to acquire the authoritative output contract. The single compact skill could be skimmed and then absorbed into a private representation rather than used as a verifier-bound workflow.

## Relationship To The Main-Agentic Minimax Diagnosis

The existing main-agentic minimax case study frames Minimax as "verifier contact without verifier discipline." Compact-domain minimax sharpens one branch of that diagnosis. In several runs, the model had skill guidance about raw observation actions, but it did not read or apply the root README contract before committing to a private schedule shape. In the runs where it did touch the verifier, it often used the verifier to prove that an empty file was acceptable rather than to force contract-complete nonempty observations.

The recurring pattern is not "Minimax cannot do stereo geometry." It is earlier: Minimax treats its own schedule object and validation counters as meaningful even when the packaged verifier would not interpret the actions at all.

## Root Cause

The root cause for this condition is schema authority failure under a veneer of skill uptake. The compact skill supplied the right high-level moves, but Minimax did not make the README and packaged verifier the controlling authority for the submitted object. The result was a set of verifier-valid files whose validity came from having no interpreted observations.

This is why the cell is 5/5 valid and still 0.0 mean score. Validity only says no interpreted hard constraints were violated. It does not mean any target received a valid stereo product.

## Implications

For skill injection, this cell is a warning about compact skill design and runtime discipline. A short skill can improve workflow only if the space agent first binds it to the local README and local verifier. Otherwise the skill's words can be reinterpreted inside a private schema.

The most targeted follow-up is an authority handshake before any solver work: read `/app/workspace/README.md`, run `./verifier --help`, write `{"actions": []}`, verify it, then add one contract-complete `type: "observation"` action and inspect whether the verifier derives it. That would have exposed the compact-domain minimax failure before hundreds of uninterpreted action-like rows were generated.
