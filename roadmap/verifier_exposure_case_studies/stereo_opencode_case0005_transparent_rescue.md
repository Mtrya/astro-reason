# Stereo Opencode DPSK Case 0005: Transparent Source Rescues Product Construction

## Evidence Base

This case study covers `stereo_imaging` `case_0005` for the `opencode_dpsk` harness across verifier-exposure tiers. Aggregate outcomes come from `experiments/verifier_exposure/reports/stereo_imaging.md`. Behavioral evidence comes from the three trace exports named in the Phase 2 plan:

- `experiments/verifier_exposure/reports/traces/data/events/none__stereo_imaging__opencode_dpsk__test__case_0005.js`
- `experiments/main_agentic/reports/traces/data/events/stereo_imaging__opencode_dpsk__test__case_0005.js`
- `experiments/verifier_exposure/reports/traces/data/events/transparent__stereo_imaging__opencode_dpsk__test__case_0005.js`

Workspace authority comes from `experiments/verifier_exposure/configs/none.yaml`, `experiments/verifier_exposure/configs/opaque.yaml`, and `experiments/verifier_exposure/configs/transparent.yaml`. The stereo contract comes from `experiments/_fragments/prompts/stereo_imaging/README.default.md` and `benchmarks/stereo_imaging/verifier/`.

This report also builds on `experiments/main_agentic/reports/case_studies/stereo_imaging_opencode_dpsk_authority_drift.md`, which diagnosed the opaque `opencode_dpsk` stereo runs as unstable verifier-centered iteration. The new contribution here is the three-tier verifier-exposure comparison for one case, not a repeat of the full DPSK case-by-case report.

## Aggregate Outcome

The aggregate report records the strongest DPSK rescue on `case_0005`:

| Exposure | System | Case | Valid | Coverage | Quality | Score |
| --- | --- | --- | --- | ---: | ---: | ---: |
| `none` | `opencode_dpsk` | `case_0005` | false | 0 | 0 | 0.0000 |
| `opaque` | `opencode_dpsk` | `case_0005` | true | 0 | 0 | 0.0000 |
| `transparent` | `opencode_dpsk` | `case_0005` | true | 0.9504 | 0.9405 | 94.05 |

This is not just a valid-rate improvement. The opaque run is already hard-valid, but it has zero stereo product value. Transparent source changes both the validity discipline and the quality mechanism: the final official run is valid and covers almost all targets with high normalized quality.

Solver baselines confirm that `case_0005` is highly solvable but not trivial: the two tracked solver rows score 97.47 and 93.88. The transparent DPSK score of 94.05 is in that solver-baseline band, while the none and opaque DPSK scores remain zero.

## Authority Setup

The three exposure configs define what the space agent could inspect.

In `none`, the workspace has `README.md`, `case/`, the prompt, and AGENTS instructions. No verifier helper is exposed.

In `opaque`, the workspace adds a runnable `verifier` artifact with command `./verifier case/ solution.json`, but no readable source.

In `transparent`, the workspace adds readable verifier source. The transparent trace's initial workspace listing contains `verifier/`, and the run reads `verifier/run.py`, `verifier/engine.py`, `verifier/models.py`, and `verifier/io.py` before building the final solver.

Official evaluation still happens outside the workspace in all three tiers. Local verifier output and trace-local metrics are useful for understanding the iteration loop, while the aggregate report is the source of record for official scores.

## Contract Details That Matter

The README contract says the submission is raw observation actions, not product claims. The verifier later derives stereo and tri-stereo products from `actions`. A schedule can therefore be hard-valid and still score zero if no valid product is formed.

The verifier source explains why. In `benchmarks/stereo_imaging/verifier/engine.py`, hard validity includes line of sight, off-nadir, solar elevation, same-satellite non-overlap, and slew/settle checks. Product validity is stricter: pair mode, midpoint separation, convergence angle, pixel scale ratio, and overlap all have to pass. Overlap is computed from commanded boresight strip centerlines in the target-local plane using deterministic Monte Carlo samples. The signed boresight frame is also exact in source: `across = np.cross(along, nadir)`, and the boresight vector combines nadir, along, and across components through tangent steering.

Those details are precisely where DPSK struggled in the existing authority-drift report. The opaque `case_0005` failure was not schema ignorance; it was a sparse, hard-valid fallback with too few useful stereo pairs and zero overlap-derived score.

## None Exposure: Large Self-Checked Schedule, External Invalid

The no-verifier trace starts with only `AGENTS.md`, `case/`, and `README.md` in the workspace. It reads the README and case YAMLs, loads the Brahe skill, and builds a private solver around Brahe propagation and custom access logic. There is no local verifier call because the exposure config does not provide one.

The run initially finds no access windows, then debugs its coordinate and access computations. Later it writes a much larger schedule: 838 observations, 140 of 141 targets with at least one observation, 137 targets with at least two observations, and 133 with at least three observations. The final message says basic checks passed: timestamp format, duration bounds, same-satellite non-overlap, combined off-nadir, and access-window containment.

The aggregate row contradicts the trace-local confidence: official evaluation records `verifier_invalid`, `valid=false`, coverage `0`, quality `0`, and score `0.0000`.

The durable claim here is limited but important. Without local verifier feedback, DPSK could build a large plausible schedule and still miss at least one authoritative hard-validity condition. The trace itself shows only private checks at the end, so the report should not infer a specific official violation from ignored artifacts. The tracked aggregate establishes the final invalid outcome.

## Opaque Exposure: Validity Recovered, Product Value Still Zero

The opaque trace starts with `AGENTS.md`, `case/`, `README.md`, and `verifier`. It reads the README, uses the Brahe skill, writes a series of increasingly constrained private solvers, and repeatedly checks against the opaque verifier.

This local feedback changes the failure mode. DPSK diagnoses hard-validity issues that the no-verifier run could not close: solar filtering, same-satellite overlap, and access-window containment. By the final iterations, it preserves a hard-valid file:

- 14 observation actions;
- 11 targets with observations;
- 3 targets with two observations;
- `valid=true`;
- `coverage_ratio=0.0`;
- `normalized_quality=0.0`;
- no violations.

The decisive trace line is the verifier diagnostic summary: "Pair evaluations: 3; Non-zero scores: 0; Total targets scored: 141." DPSK then reasons that the 3 evaluated pairs all failed convergence, overlap, or pixel scale, and finalizes because the solution is at least valid.

The aggregate row matches the trace: valid, coverage `0`, quality `0`, score `0.0000`.

This is a different failure from `none`. Opaque exposure rescues hard validity, but not product construction. DPSK uses the verifier as an acceptance gate, yet its private access and observation-selection model collapses to a sparse schedule that cannot create any valid stereo products.

## Transparent Exposure: Source-Guided Solver Construction

The transparent trace changes before the first serious solver is written. DPSK reads `verifier/engine.py`, `verifier/models.py`, and `verifier/io.py` early. It then explicitly plans around verifier mechanics: access requires line of sight, off-nadir, and solar elevation; product construction must satisfy same-pass or cross-satellite rules, convergence, pixel scale, overlap, and slew/settle.

The solver is still a private implementation, not a direct import of the verifier as a black box. But it is source-guided in the important places. The trace records DPSK adding `_boresight_unit`, `_angle_between`, and `_min_slew_time_s` to match verifier slew behavior. It inspects solver snippets that enforce midpoint separation, convergence bounds, pixel-scale ratio, same-satellite same-pass constraints, observation non-overlap, and slew gaps. It also reasons directly from verifier-source behavior when adding boresight-ground-intersection checks and when debugging residual access and slew violations.

The improvement is visible in the trace-local iteration:

- an early source-guided solution covers only about 32% and has five violations;
- after slew and access fixes, coverage jumps above 0.87 with only small slew/settle violations left;
- a later scheduler finds 847 access windows across 751 satellite-target pairs, generates 4616 observation slots, evaluates 15666 candidate stereo pairs, and runs a two-phase coverage-first then quality-maximizing schedule;
- final local verification reports `valid=true`, `coverage_ratio=0.9574468085106383`, and `normalized_quality=0.9469358983953489`;
- the final trace message reports 1045 observations covering 136 of 141 targets, with no violations.

The official aggregate is slightly lower but confirms the same outcome class: valid, coverage `0.9504`, quality `0.9405`, score `94.05`. As in Phase 1, the aggregate row is the score source of record; local trace metrics explain the iteration.

## What Transparent Source Added Beyond Opaque Feedback

The opaque run knew whether a final file was accepted, but it did not reveal enough of the product-construction mechanism for DPSK to build broad stereo coverage. The final opaque schedule had only 14 observations and 3 evaluated pairs, all zero-score.

The transparent run used source to stabilize the exact mechanics that opaque feedback exposed only indirectly:

- access was implemented as line-of-sight, off-nadir, and solar filtering rather than a broad Brahe access proxy;
- boresight steering was tied to the verifier's signed along/across frame and ground-intercept behavior;
- same-satellite scheduling used the verifier's boresight-angle slew model, not just interval non-overlap;
- candidate products were filtered by the same time-separation, convergence, pixel-scale, and same-pass/cross-satellite rules that the verifier enforces;
- search strategy shifted from "find any valid observations" to coverage-first pair construction followed by quality improvement.

This is why `case_0005` is a cleaner transparent-source rescue than a simple "ran the checker more" story. Opaque exposure already allowed checker feedback and produced `valid=true`. The missing ingredient was a source-aligned product model.

## Relation To The DPSK Authority-Drift Report

The earlier DPSK report describes opaque `case_0005` as a sparse hard-valid fallback: 14 mostly conservative observations, only 3 pair evaluations, and zero overlap/product score. This Phase 2 report agrees with that diagnosis but adds the exposure comparison.

The key difference is not that transparent source fixes one named bug such as cross-track sign. The transparent trace supports a broader mechanism: source exposure lets DPSK align access discovery, boresight steering, slew preservation, candidate-pair filtering, and coverage-first scheduling with the verifier contract. The cross-track convention is part of that contract, but the trace evidence does not justify reducing the rescue to that one issue.

## Root Cause Statement

For `opencode_dpsk` on `stereo_imaging` `case_0005`, the no-verifier run failed because private validation did not preserve official hard validity. The opaque run recovered hard validity but produced only a sparse valid-zero schedule. The transparent run succeeded because readable verifier source turned the verifier from a late oracle into an implementation guide for geometry, access, pair validity, slew constraints, and search.

That is the strongest DPSK verifier-source rescue in the stereo aggregate: `0.0000` invalid, to `0.0000` valid-zero, to `94.05` valid high-quality.

## Implications

This case separates three failure modes that should not be collapsed:

- `none`: no local verifier, large private schedule, official hard-validity failure;
- `opaque`: local verifier, hard-valid file, zero valid product value;
- `transparent`: readable verifier source, broad source-aligned product construction, high official score.

For future synthesis, `case_0005` is strong evidence that geometry-heavy benchmarks can benefit from transparent verifier source even when an opaque verifier already exists. The value is not just local pass/fail feedback. It is making the exact scoring and validity machinery available early enough for the space agent to build the solver around it.
