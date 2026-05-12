# SatNet Verifier Exposure Control

This report explains why `satnet` is the control benchmark for the verifier-exposure study. Aggregate outcomes come from `experiments/verifier_exposure/reports/satnet.md`. The main trace comparisons are:

- `experiments/verifier_exposure/reports/traces/data/events/none__satnet__codex__test__W10_2018.js`
- `experiments/main_agentic/reports/traces/data/events/satnet__codex__test__W10_2018.js`
- `experiments/verifier_exposure/reports/traces/data/events/transparent__satnet__codex__test__W10_2018.js`
- `experiments/verifier_exposure/reports/traces/data/events/none__satnet__codex__test__W20_2018.js`
- `experiments/main_agentic/reports/traces/data/events/satnet__codex__test__W20_2018.js`
- `experiments/verifier_exposure/reports/traces/data/events/transparent__satnet__codex__test__W20_2018.js`
- `experiments/verifier_exposure/reports/traces/data/events/none__satnet__opencode_dpsk__test__W30_2018.js`
- `experiments/main_agentic/reports/traces/data/events/satnet__opencode_dpsk__test__W30_2018.js`
- `experiments/verifier_exposure/reports/traces/data/events/transparent__satnet__opencode_dpsk__test__W30_2018.js`

## Aggregate Outcome

The SatNet exposure summary is nearly flat compared with `stereo_imaging`:

| Exposure | Runs | Valid Rate | Mean Score | Overall Statuses |
| --- | ---: | ---: | ---: | --- |
| `none` | 10 | 1.0000 | 65.85 | success: 10 |
| `opaque` | 10 | 1.0000 | 64.84 | success: 10 |
| `transparent` | 10 | 1.0000 | 65.92 | success: 10 |

By harness, the same pattern holds. Codex scores 69.46 with no verifier, 69.45 with opaque verifier, and 69.95 with transparent source. DPSK scores 62.25 with no verifier, 60.23 with opaque verifier, and 61.90 with transparent source. Every agent row is valid.

That is the opposite of the stereo-imaging aggregate, where no-verifier validity is only 40 percent and transparent source raises mean score from 18.96 to 82.21. SatNet therefore helps separate "verifier exposure fixes hidden contract reconstruction" from ordinary search variance.

## Why SatNet Is Less Exposure-Sensitive

The no-verifier SatNet workspace still exposes most of the operative mechanics. `experiments/verifier_exposure/configs/none.yaml` assembles `README.md`, `AGENTS.md`, and `case/`. For SatNet, the case files contain `problem.json` with request durations, compatible resources, and precomputed `resource_vp_dict` view periods, plus `maintenance.csv` with downtime intervals. The space agent does not need to reconstruct line-of-sight geometry, boresight steering, Monte Carlo overlap, or stereo product formation.

The README fragment at `experiments/_fragments/prompts/satnet/README.default.md` gives the key verifier contract directly: output is a JSON array, rows use `RESOURCE`, `SC`, `START_TIME`, `TRACKING_ON`, `TRACKING_OFF`, `END_TIME`, and `TRACK_ID`; timing must satisfy exact setup and teardown equations; communication intervals must fit inside `TRX ON`/`TRX OFF`; antenna occupancy is half-open `[START_TIME, END_TIME)` including setup and teardown; long requests use a capped per-track minimum; request satisfaction and mission fairness are computed from capped allocated seconds.

The tracked verifier source, `benchmarks/satnet/verifier.py`, mostly implements those same data-visible rules: parse tracks, group arrayed logical tracks, check resource/view-period containment, setup/teardown equality, maintenance, antenna overlap, per-track minimum duration, then compute `U_rms` and `U_max` from per-subject unsatisfied fractions. Transparent source can still help avoid small mistakes, but it does not reveal a hidden physics model in the way `benchmarks/stereo_imaging/verifier/engine.py` does for stereo imaging.

## W10 Codex: Exposure Helps, But As Search Feedback

`W10_2018` is the positive exposure example for Codex:

| Exposure | System | Case | Valid | Score |
| --- | --- | --- | --- | ---: |
| `none` | `codex` | `W10_2018` | true | 66.80 |
| `opaque` | `codex` | `W10_2018` | true | 78.09 |
| `transparent` | `codex` | `W10_2018` | true | 81.01 |

The no-verifier trace reads the README and case files, builds `solver.py`, and finishes with local contract validation: `U_rms = 0.240315455433703`, `U_max = 0.6071428571428571`, 198 satisfied requests, and 875.4 communication hours. It explicitly notes that no bundled official verifier is available.

The opaque trace lists `verifier`, reads the README, runs `./verifier --help`, and later verifies a schedule with `VALID`, `U_rms=0.153978`, `U_max=0.414286`, 234 satisfied requests, 1028.8 tracking hours, and 244 tracks. The transparent trace reads `verifier.py` and finishes with `U_rms = 0.143576`, `U_max = 0.328720`, 215 satisfied requests, 1022.5333 tracking hours, and 251 tracks.

This is a real exposure benefit, but it looks like validation/scoring feedback and search guidance, not contract rescue. All three runs are valid. The higher-scoring runs use local verifier feedback to keep better candidate schedules, whereas the no-verifier run already understands the schema and hard constraints well enough to submit a valid solution.

## W20 Codex: More Verifier Is Not Monotonic

`W20_2018` is the cautionary control:

| Exposure | System | Case | Valid | Score |
| --- | --- | --- | --- | ---: |
| `none` | `codex` | `W20_2018` | true | 76.54 |
| `opaque` | `codex` | `W20_2018` | true | 61.17 |
| `transparent` | `codex` | `W20_2018` | true | 71.89 |

The no-verifier trace builds a local validator/scorer and CP-SAT scheduler from the README rules. It finishes valid with `U_rms = 0.15366053284511205`, `U_max = 0.4772727272727273`, 243 satisfied requests, and 1187.9 communication hours. The transparent trace reads `verifier.py`, imports verifier functions for local verification/scoring, and finishes valid with `U_rms = 0.208120`, `U_max = 0.500000`, 201 satisfied requests, 1074.1 tracking hours, and 311 tracks. The opaque trace verifies with `./verifier` and ends valid, but its own scorer reports approximately `U_rms=0.229896`, `U_max=0.863636`, and 252 satisfied requests.

The aggregate ranking follows search quality, not exposure tier. No-verifier Codex found the best W20 schedule among the three exposure rows, despite having no executable verifier helper. This is the strongest evidence that SatNet is not primarily bottlenecked by hidden verifier semantics.

## W30 DPSK: Transparent Source Does Not Dominate

DPSK `W30_2018` gives the harness contrast requested by the phase plan:

| Exposure | System | Case | Valid | Score |
| --- | --- | --- | --- | ---: |
| `none` | `opencode_dpsk` | `W30_2018` | true | 65.30 |
| `opaque` | `opencode_dpsk` | `W30_2018` | true | 50.61 |
| `transparent` | `opencode_dpsk` | `W30_2018` | true | 61.84 |

The no-verifier DPSK trace reads the README and case files, writes a formatted JSON list, and its final summary claims 306 rows, 289 logical tracks, `U_rms = 0.3050`, `U_max = 0.4732`, 173/293 satisfied requests, and all hard constraints passing. The transparent trace reads `verifier.py` early and finishes valid with a fairness-first greedy schedule: `U_rms = 0.2939`, `U_max = 0.6449`, 234 tracks, 1033.5 communication hours, and 189/293 satisfied requests. The opaque trace spends its run in multi-start/deep search and the aggregate records a valid but lower-scoring result.

Transparent source improves some local objective pieces relative to the no-verifier trace, but the aggregate score is lower than the no-verifier row. The likely explanation is objective tradeoff and search variance: SatNet scoring depends on mission-level unsatisfied-demand distribution, especially `U_rms` and `U_max`, so more hours or more satisfied requests need not dominate if the worst missions move differently. The selected traces support the modest claim only: transparent source does not control DPSK W30 outcome the way it controls stereo-imaging rescue cases.

## Control Interpretation

SatNet has verifier exposure effects, but they are second-order:

- Validity is already solved from the README and case files. No-verifier rows are 10/10 valid.
- The exposed verifier mostly confirms parse/schema/timing rules already written in the prompt fragment.
- Transparent source can help agents implement an exact scorer or run verifier internals, as in Codex W20, but that does not guarantee better search.
- Score movement is mixed case-by-case: W10 Codex improves with exposure, W20 Codex gets worse with exposure, and DPSK W30 is best with no verifier.
- The remaining bottleneck is scheduling strategy: fairness-first allocation, long-request chunking, arrayed contacts, maintenance/overlap packing, CP-SAT versus greedy heuristics, and timeout behavior.

This is why SatNet is the useful control for the stereo reports. In stereo imaging, verifier exposure changes whether agents can align with hidden geometric and product-scoring machinery at all. In SatNet, most mechanics are explicit in `problem.json`, `maintenance.csv`, and `README.md`; verifier exposure mainly changes feedback quality and search iteration. The aggregate result is therefore flat: all tiers are valid, and mean scores differ by about one point rather than by tens of points.
