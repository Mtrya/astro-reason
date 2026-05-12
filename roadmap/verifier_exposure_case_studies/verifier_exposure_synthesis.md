# Verifier Exposure Synthesis

This synthesis connects the Phase 1-4 reports into one evidence-first thesis about `experiments/verifier_exposure`. It cites the aggregate reports `experiments/verifier_exposure/reports/stereo_imaging.md` and `experiments/verifier_exposure/reports/satnet.md`, the experiment contract in `experiments/verifier_exposure/README.md`, and the completed phase reports:

- `roadmap/verifier_exposure_case_studies/stereo_codex_case0004_verifier_source.md`
- `roadmap/verifier_exposure_case_studies/stereo_opencode_case0005_transparent_rescue.md`
- `roadmap/verifier_exposure_case_studies/stereo_no_verifier_failure_modes.md`
- `roadmap/verifier_exposure_case_studies/satnet_verifier_exposure_control.md`

## Aggregate Pattern

Verifier exposure is benchmark-dependent.

For `stereo_imaging`, exposure changes both validity and score:

| Exposure | Runs | Valid Rate | Mean Score |
| --- | ---: | ---: | ---: |
| `none` | 10 | 0.4000 | 18.96 |
| `opaque` | 10 | 0.9000 | 40.95 |
| `transparent` | 10 | 1.0000 | 82.21 |

For `satnet`, exposure has little aggregate effect:

| Exposure | Runs | Valid Rate | Mean Score |
| --- | ---: | ---: | ---: |
| `none` | 10 | 1.0000 | 65.85 |
| `opaque` | 10 | 1.0000 | 64.84 |
| `transparent` | 10 | 1.0000 | 65.92 |

The key conclusion is not "verifiers always improve agents." The evidence supports a narrower claim: local verifier exposure matters most when the benchmark's accepted solution mechanics depend on implementation details that are difficult to reconstruct from case files and prose alone.

## Mechanism 1: No Verifier Removes The Correction Loop

Stereo evidence: Phase 3 shows the no-verifier stereo tier failing in three distinct ways. Codex `case_0002` and `case_0003` are hard-valid but product-empty: official validity is `true`, but coverage, quality, and score are all zero. Codex `case_0004` and DPSK `case_0001`, `case_0004`, and `case_0005` are hard-invalid. DPSK `case_0002` and `case_0003` are verifier errors from malformed timestamps with seconds equal to `60`, tied back to `benchmarks/stereo_imaging/verifier/io.py`.

The trace mechanism is repeated: the space agent reads the README, builds a private propagation/access/product model, and reports high local confidence. Those private checks are sometimes enough, as Codex `case_0001` and `case_0005` prove, but they are brittle. Without an executable checker, private metrics become the final authority even when they disagree with the hidden official verifier.

SatNet control: Phase 4 shows the opposite baseline. SatNet no-verifier rows are 10/10 valid. The reason is visible in the contract: `case/problem.json` already contains request durations, compatible resources, and precomputed view periods, while `case/maintenance.csv` contains downtime windows. The README fragment states the JSON array schema, setup/teardown equations, view-period containment, antenna overlap, maintenance, per-track minimum, and fairness metrics. No local verifier is needed to reconstruct line-of-sight geometry or product formation.

Conclusion: no-verifier risk is not generic. It is high when the task requires exact hidden derivations, as in stereo imaging; it is much lower when the case files and README expose the operative scheduling mechanics, as in SatNet.

## Mechanism 2: Opaque Verifiers Recover Validity Before They Recover Quality

Stereo evidence: Phase 1 and Phase 2 both show opaque exposure changing the failure mode. Codex `case_0004` moves from no-verifier invalid to opaque valid with one useful target: coverage `0.0079`, quality `0.0079`, score `0.7931`. DPSK `case_0005` moves from no-verifier invalid to opaque hard-valid but still score zero: coverage `0`, quality `0`, score `0.0000`.

That distinction matters. Opaque feedback can say "this file is accepted" and can expose final metrics or violations through the binary, but it does not give agents an implementation substrate for access, boresight, overlap, stereo-mode, or product scoring. The opaque stereo traces therefore recover hard validity before they recover broad product construction.

SatNet control: opaque exposure does not produce a comparable aggregate jump. SatNet opaque rows are all valid, but mean score is 64.84, slightly below the no-verifier mean of 65.85. On selected traces, opaque feedback helps W10 Codex, but W20 Codex is worse than no-verifier. This supports the search-variance interpretation: when hard validity is already easy to satisfy from the prompt and case data, a checker mostly changes iteration choices.

Conclusion: opaque verifiers are strongest as local acceptance gates. They are less reliable as guides for constructing high-quality solutions when the missing piece is a complex verifier-internal model.

## Mechanism 3: Transparent Source Provides Implementation Guidance

Stereo evidence: the largest changes come when transparent source turns verifier behavior into solver machinery. In Phase 1, Codex `case_0004` moves from invalid, to opaque score `0.7931`, to transparent score `90.62`. The transparent trace reads `verifier/run.py`, `verifier/engine.py`, `verifier/models.py`, and `verifier/io.py`, then imports verifier internals such as access checks, boresight construction, stereo pair mode, and pair evaluation into its solver.

Phase 2 shows the same mechanism for DPSK `case_0005`: no-verifier invalid, opaque valid-zero, transparent valid with coverage `0.9504`, quality `0.9405`, and score `94.05`. The transparent trace uses readable source to align access filtering, signed boresight steering, slew/settle gaps, midpoint separation, convergence, pixel-scale ratio, and coverage-first product search.

SatNet control: transparent source does not dominate SatNet. W10 Codex improves from 66.80 none, to 78.09 opaque, to 81.01 transparent, but W20 Codex is best with no verifier at 76.54, compared with 61.17 opaque and 71.89 transparent. DPSK W30 is also best with no verifier: 65.30 none, 50.61 opaque, 61.84 transparent. Phase 4 traces show transparent SatNet agents reading or importing `verifier.py`, but the aggregate effect remains tiny because source mostly confirms already visible scheduling rules.

Conclusion: transparent source is most valuable when it reveals executable implementation detail that the agent can adapt into candidate generation and scoring. It is not a magic optimization booster. When the contract is already data-visible, transparent source may help validation or scoring but does not guarantee better search.

## Benchmark-Specific Thesis

The stereo traces support the strong verifier-exposure thesis. `stereo_imaging` requires agents to align with TLE propagation, target access, boresight steering, slew timing, deterministic strip overlap, stereo and tri-stereo product construction, and normalized product quality. The README is detailed, but small implementation mismatches can cause invalid, valid-zero, or low-quality schedules. Transparent source makes those mechanics exact and reusable.

The SatNet traces support the control thesis. `satnet` is still a scheduling problem, but the hard view windows are precomputed and visible. The verifier largely checks interval arithmetic, resource combinations, maintenance, non-overlap, setup/teardown equality, per-track minimum duration, and mission fairness. Agents can implement those from `README.md`, `problem.json`, and `maintenance.csv`; remaining score variation mostly comes from allocation heuristics, CP-SAT versus greedy search, arraying choices, long-request chunking, and timeout behavior.

Together, the evidence says verifier exposure changes outcomes when it changes the agent's source of truth for hidden mechanics. It has much less aggregate impact when the source of truth is already present in the prompt and case files.

## Practical Implications

For benchmark workspace design, choose verifier exposure deliberately. If the goal is to measure independent reconstruction from a public prose contract, no-verifier or opaque-only settings are meaningful but should be expected to include schema, parser, hard-validity, and product-model failures. If the goal is to measure planning/search on top of an exact physical or geometric contract, transparent source may be the fairer interface because it prevents hidden implementation reconstruction from dominating.

For evaluation interpretation, separate validity from score. Stereo Phase 3 shows that `valid=true` can still mean zero product value, and `verifier_error` can be a loader/parser failure rather than geometry. Opaque rows should not be read as "solved" just because validity recovered.

For future experiments, the next useful split is not simply "more traces." It is targeted ablation of source guidance versus executable feedback: for example, expose only schema/parser helpers, only access/geometry helpers, or only a score-reporting opaque checker. Stereo is the right benchmark for that ablation; SatNet is the control.

The existing stereo Kimi and DPSK authority-drift reports should remain separate from these verifier-exposure reports. They diagnose broader main-agentic behavior and harness-specific authority drift, while the verifier-exposure roadmap isolates a controlled three-tier workspace ablation. The synthesis can cite them as related context, but folding them into this set would blur the controlled exposure comparison.

## Bottom Line

Across these phases, the evidence supports a conditional thesis: verifier exposure matters when it changes authority alignment. In stereo imaging, no verifier leaves agents dependent on brittle private models, opaque verifiers recover some hard validity, and transparent source can convert verifier internals into high-quality solver construction. In SatNet, the same exposure ladder has little aggregate effect because the README and case files already expose most validity and scoring mechanics; score differences mostly reflect search strategy.
