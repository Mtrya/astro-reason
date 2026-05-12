# Stereo Codex Case 0004: Source Exposure Converts Proxy Search Into Verifier-Aligned Search

## Evidence Base

This case study explains the Codex `stereo_imaging` `case_0004` contrast across the three verifier-exposure tiers. Aggregate outcomes come from `experiments/verifier_exposure/reports/stereo_imaging.md`. The three behavior traces are:

- `experiments/verifier_exposure/reports/traces/data/events/none__stereo_imaging__codex__test__case_0004.js`
- `experiments/main_agentic/reports/traces/data/events/stereo_imaging__codex__test__case_0004.js`
- `experiments/verifier_exposure/reports/traces/data/events/transparent__stereo_imaging__codex__test__case_0004.js`

Workspace exposure contracts come from `experiments/verifier_exposure/configs/none.yaml`, `experiments/verifier_exposure/configs/opaque.yaml`, and `experiments/verifier_exposure/configs/transparent.yaml`. The benchmark-facing contract is the rendered stereo README fragment, `experiments/_fragments/prompts/stereo_imaging/README.default.md`, plus the verifier source under `benchmarks/stereo_imaging/verifier/`.

Ignored `results/*` artifacts are not needed for the main claims below. Official score claims use the aggregate report, while trace-local verifier claims are treated as evidence about the space agent's iteration loop.

## Aggregate Outcome

For the same benchmark, harness, split, and case, the aggregate report records a clean three-step transition:

| Exposure | System | Case | Valid | Coverage | Quality | Score |
| --- | --- | --- | --- | ---: | ---: | ---: |
| `none` | `codex` | `case_0004` | false | 0 | 0 | 0.0000 |
| `opaque` | `codex` | `case_0004` | true | 0.0079 | 0.0079 | 0.7931 |
| `transparent` | `codex` | `case_0004` | true | 0.9603 | 0.9062 | 90.62 |

The surrounding Codex rows show that `case_0004` is the cleanest within-harness exposure contrast, not merely a hard case. Codex scores high on other no-verifier stereo cases, but this case moves from invalid, to one-target valid, to high-quality broad coverage when source is exposed. Solver baselines also show the case is solvable: the two tracked solver rows for `case_0004` score 92.38 and 85.32.

## Workspace Authority

The exposure configs define what the evaluated space agent could see.

In `none`, the workspace receives the rendered README, the case directory, prompt, and AGENTS instructions. `workspace_verifier.exposed` is false and the command is "No verifier helper is available in this workspace."

In `opaque`, the workspace receives the same README and case files plus `experiments/_fragments/opaque_verifiers/artifacts/{benchmark}/verifier` at `/app/workspace/verifier`. The command is `./verifier case/ solution.json`, but source is not assembled.

In `transparent`, the workspace receives the same README and case files plus readable verifier source. In the transparent trace, the initial listing shows `verifier/run.py`, `verifier/models.py`, `verifier/engine.py`, and `verifier/io.py` in the workspace.

Official evaluation is still external in all tiers. The local helper is an iteration aid, not the scoring source of record.

## Verifier Contract

The README tells the space agent that it must submit raw observation actions under top-level `actions`; the validator derives stereo and tri-stereo products. It also states that actions whose `type` is not `"observation"` are ignored, that target access is derived rather than submitted, and that coverage comes only from valid derived products.

The verifier source makes the implementation details exact. `benchmarks/stereo_imaging/verifier/io.py` parses only observation actions from the `actions` array and rejects timezone-naive timestamps. `benchmarks/stereo_imaging/verifier/engine.py` defines the local steering frame with `across = np.cross(along, nadir)`, builds commanded boresight vectors from the submitted along/across angles, samples pushbroom strip centerlines every 8 seconds, estimates pair overlap with deterministic Monte Carlo samples, and computes `coverage_ratio` plus `normalized_quality` from the best valid product per target.

Those implementation details matter because stereo imaging is not just interval scheduling. A schedule can be syntactically valid, target-accessible, and still low-scoring if the commanded strips do not overlap the AOI or if the solver's private scoring proxy diverges from the verifier.

## Trace Comparison

### No Verifier: High Proxy Confidence, Official Invalid

The no-verifier trace lists only `README.md`, `case/targets.yaml`, `case/mission.yaml`, `case/satellites.yaml`, and `AGENTS.md`. It reads the README, creates an empty `solution.json`, then writes a standalone `solver.py` with its own SGP4, access, steering, overlap, and quality approximations.

The run's own status message captures the authority problem: it selected 252 observation actions covering all 126 targets with a proxy normalized score of `0.9790`, but explicitly notes that there was no official verifier in the workspace and that the score was based on a conservative proxy rather than a ground-truth check. The aggregate report then records the external outcome as `verifier_invalid`, `valid=false`, score `0.0000`.

The evidence supports a narrow claim: without any local verifier helper, Codex built a plausible private model and could not close the loop against the authoritative hard-validity checks before finalizing. The tracked artifacts do not need an ignored `results/*` replay to establish the key mechanism: trace-local confidence came from a proxy, and official evaluation rejected the final file.

### Opaque Verifier: Validity Recovered, Product Search Collapses

The opaque trace starts with `README.md`, `verifier`, `AGENTS.md`, and the case YAMLs. Codex reads the README, runs `./verifier --help`, writes an empty `solution.json`, and verifies that the empty file is hard-valid with zero coverage and zero quality. It then writes `search_solution.py`, a private search script that calls the opaque executable for feedback.

The final result is not invalid. The trace says the current best verified schedule contains a same-satellite same-pass stereo pair for `open_079` on `sat_cbers_4`, and reports `valid: true`, `coverage_ratio: 0.007936507936507936`, and `normalized_quality: 0.007930781958095398` with no violations. The aggregate row matches that shape: valid, coverage `0.0079`, quality `0.0079`, score `0.7931`.

This is the middle tier's specific lesson. Opaque feedback was enough to avoid the no-verifier invalid submission, but not enough to build a broad, verifier-aligned product model on this case. The final file has two actions for one target. Codex even reports that denser cross-satellite, same-pass, and tri-stereo searches did not beat that pair on the verifier. The local checker became an acceptance gate, but the search model stayed too weak.

### Transparent Verifier: Source Becomes The Solver Interface

The transparent trace differs before optimization begins. The initial listing exposes readable verifier files, and Codex reads the README, `verifier/run.py`, `verifier/engine.py`, `verifier/models.py`, and `verifier/io.py` near the start. It also lists verifier engine function names, including access, boresight, product, and target-ECEF helpers.

The transparent solver then imports verifier internals directly in `solve_case.py`, including `_access_holds_over_window`, `_access_interval_sampling_step_s`, `_access_predicate`, `_boresight_ground_intercept_ecef_m`, `_boresight_unit_vector`, `_evaluate_stereo_pair`, `_satellite_local_axes`, `_stereo_pair_mode`, `_target_ecef_m`, `load_case`, and the verifier model dataclasses. That is the central behavioral difference: implementation source was not merely read as documentation; it became the computational substrate for candidate generation and scoring.

The trace shows rapid verifier-aligned iteration:

- first candidate pass: 126 candidate targets, 2137 candidate observations, 558 candidate products, then an invalid high-score report due to one slew/settle violation;
- repaired pass: valid with coverage `0.9523809523809523` and quality `0.8988960277443747`;
- broader candidate pass: 914 candidate products and valid quality above `0.9175`;
- final local claim: valid with coverage `0.9920634920634921`, quality `0.9341800542742376`, and no violations.

The official aggregate score is lower than the trace-local final claim, at coverage `0.9603` and quality `0.9062`, but both are high-quality valid outcomes. This discrepancy is a reminder that local helper output is not the final source of record. One plausible implementation-level reason is visible in the verifier source: `verify_solution` sets `case_id = case_path.name`, and `_stereo_mc_rng` uses that case id in the deterministic overlap seed. The workspace helper is run against a directory named `case`, while external evaluation uses the canonical case directory name. The important case-study claim does not depend on the local 0.9342 number; the aggregate report establishes the official transparent score of 90.62.

## Why Source Exposure Helped

This case isolates three different authority regimes.

With no verifier, Codex used the README and a private geometry proxy as the final authority. The proxy looked strong by its own metrics, but official evaluation found the submitted schedule invalid.

With an opaque verifier, Codex gained a hard-validity oracle. That changed the outcome from invalid to valid, but the opaque executable did not give Codex reusable implementation detail. The final schedule was a verified one-target pair, not a broad solution.

With transparent source, Codex could bind its search to the verifier's exact mechanics. It reused source-level access checks, local axes, boresight construction, stereo-mode logic, and pair evaluation while constructing candidates. That prevented the common stereo failure mode where a private access or footprint model becomes the active source of truth. Source exposure turned the verifier from a late yes/no checker into an executable specification for search.

## Root Cause Statement

For Codex `stereo_imaging` `case_0004`, the decisive exposure effect is not simply "more validation runs." It is authority alignment.

The no-verifier run trusted a private proxy and failed external validity. The opaque run used the verifier as an acceptance gate and recovered hard validity, but could not turn opaque feedback into a broad product-construction model. The transparent run read and imported verifier source early, then built its solver around the same routines that define access, steering, overlap, product validity, and scoring. That source-level alignment is the best-supported explanation for the jump from `0.7931` to `90.62`.

## Implications

`case_0004` is the cleanest Phase 1 example because it separates three benefits that can otherwise blur together:

- README-only task understanding can produce confident but invalid proxy solutions.
- Opaque verifier feedback can enforce hard validity without producing high-quality search.
- Transparent verifier source can expose enough implementation structure for geometry-heavy product construction.

The result should not be generalized to every Codex stereo run without later phases. The aggregate report includes no-verifier Codex successes on `case_0001` and `case_0005`, so source exposure is not the only way Codex can solve stereo cases. But on `case_0004`, the tracked traces and aggregate rows line up unusually well: source access changed the solver from proxy-guided or checker-gated behavior into verifier-aligned construction.
