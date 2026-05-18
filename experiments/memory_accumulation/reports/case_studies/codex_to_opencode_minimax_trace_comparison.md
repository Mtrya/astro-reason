# Codex Memory To Opencode MiniMax Trace Comparison

This case study compares the held-out `codex -> opencode_minimax` memory transfer runs against no-memory Opencode MiniMax runs and the existing skill-injection controls. The useful traces are not the mostly-empty `session_diff/*.json` files; for Opencode runs, the chronological evidence is in `session_logs/opencode/opencode.db`, with aggregate outcomes in `results/agent_runs/experiments/memory_accumulation/summaries/runs.csv` and the generated reports under `experiments/memory_accumulation/reports/`.

## Outcome

The cleanest positive transfer is `regional_coverage`. For Opencode MiniMax, Codex memory improves the matched mean normalized score from `17.73` to `20.94`, with four of five cases improving. The strongest concrete case is `regional_coverage/case_0002`: no-memory Opencode MiniMax scores `0.1697`, compact skill injection scores `0.0288`, skill-pack injection scores `0.0192`, and Codex-memory Opencode MiniMax scores `0.3121`.

`relay_constellation` shows a narrower but informative transfer. No-memory Opencode MiniMax scores zero on every matched relay case. Codex memory improves only `case_0003`, reaching `service_fraction = 0.2156`, for a five-case mean normalized-score lift from `0.0000` to `2.2633`. The trace shows that memory transfers a relay-orbit design prior, but not the harder link-window scheduling strategy.

`satnet` is the counterexample. After backfilling the primary metrics from verbose verifier output, Codex-memory Opencode MiniMax is valid on all five cases but averages `32.46`, below the no-memory Opencode MiniMax mean of `37.54`. Memory helps validity on `W50_2018`, where the no-memory run is verifier-invalid, but hurts the primary fairness metric on the other weeks.

## Regional Coverage

The `regional_coverage/case_0002` memory trace reads prior memory notes that describe a verified strip-coverage workflow, including verifier-driven iteration and a previous high-coverage solution. It then inspects all three regions in `coverage_grid.json`, generates candidates, verifies repeatedly, and preserves the best verified incumbent when a later variant regresses.

The no-memory trace is disciplined enough to read the README and use the verifier, but its search is much narrower. It repeatedly frames the case around the Black Sea and ends with a mostly single-region solution. The final valid no-memory score is `weighted_coverage_ratio = 0.1697`; the Codex-memory run reaches `0.3121`, covering portions of all three regions.

The skill-injection controls are a useful warning. Both compact and skill-pack runs encourage verifier discipline, but on this case they appear to anchor the space agent to a one-strip or Black-Sea-heavy procedure. They validate more carefully than a naive run, yet their scores are far lower than both no-memory and Codex-memory Opencode MiniMax. The lesson is that a procedural skill can reduce schema and validity errors while still over-constraining the search representation.

## Relay Constellation

The `relay_constellation/case_0003` memory trace reads `relay-network-augmentation-run-notes.md` and carries over a specific Walker-like six-relay design: altitude, inclination, RAAN, anomaly, and phase are all reused as design priors. That is enough to get a nonzero valid service solution where the no-memory and skill-pack Opencode MiniMax controls remain at zero.

The failure mode is equally clear. After reaching a valid ground-link-only solution, the run tries to add relay-relay ISLs, discovers apparently feasible links, and then invalidates the solution because those links are not feasible across the full horizon or violate link limits. It then reverts to the valid ground-link-only incumbent. The transferred memory solved the orbit-selection part, but not the activation-window and max-link scheduling part.

This is a good target for a better memory artifact: the note should not only record the relay geometry, but also the exact scheduling abstraction that made ISLs safe, including how feasibility was checked over time.

## SatNet

SatNet exposes the sharpest distinction between validity, total hours, and the true primary metric. The benchmark contract prioritizes `U_rms`, then `U_max`; `score_hours` is only secondary service volume. The memory reports now show the corrected values:

| Case | No-Memory Score | Memory Score | No-Memory U_rms | Memory U_rms | Note |
| --- | ---: | ---: | ---: | ---: | --- |
| W10_2018 | 55.81 | 41.01 | 0.3273 | 0.4533 | memory stops after a quick valid schedule |
| W20_2018 | 26.94 | 18.09 | 0.6408 | 0.7589 | memory has high hours but poor fairness |
| W30_2018 | 62.67 | 37.27 | 0.2978 | 0.5030 | memory underperforms strongly |
| W40_2018 | 42.28 | 28.06 | 0.4830 | 0.6258 | memory underperforms strongly |
| W50_2018 | 0.00 | 37.90 | invalid | 0.5060 | memory fixes validity |

On `W10_2018`, the no-memory trace spends much longer exploring fairness-aware randomized orderings. It records intermediate private metrics such as `U_rms = 0.372680`, then `0.337627`, then finally `0.327299` with `U_max = 0.785714`, and confirms the final solution with the verifier. The Codex-memory trace, by contrast, reaches a valid solution quickly (`627.3` hours, `205` tracks), tries to ask the opaque verifier for detailed metrics, receives only compact output, and stops without the same randomized fairness search.

On `W50_2018`, memory helps in a different way. The no-memory run builds invalid arrayed contacts; the stored verifier errors include unavailable antenna combinations such as `DSS-34_DSS-35`. The memory run explicitly reasons through arrayed-resource semantics, corrects the output to one row per participating antenna, runs the verifier with `-v`, and lands on a valid solution with `U_rms = 0.506049` and `U_max = 0.965986`. This is a validity win, but still a weak fairness result.

The SatNet lesson is therefore not "memory helps" or "memory hurts" in general. It helps with contract recovery in `W50_2018`, but it appears to shorten or redirect optimization on the other cases. For SatNet, reusable memory should encode the fairness-search strategy, not just the schedule format and feasibility rules.

## Metric Plumbing

The missing SatNet metrics came from the memory-accumulation runner invoking the SatNet verifier without `--verbose`. Compact verifier output only contains validity, `total_hours`, and `tracks`, so `run.json` stored `u_rms`, `u_max`, and `n_satisfied_requests` as null even for successful runs.

The runner now requests verbose output for `satnet` and `spot5`, matching `main_agentic`. The memory aggregator also has a narrow SatNet fallback: when a valid saved run is missing `u_rms`, `u_max`, or satisfied-request count, it re-runs the repository verifier on the saved `solution.json` and fills those metrics before computing normalized scores. This lets existing traces be reported correctly without rerunning the space agents.

## Takeaways

Memory is strongest when it transfers a case-general search discipline and a verifier-backed acceptance habit. `regional_coverage/case_0002` is the best demonstration because memory changes the search breadth and the final selection policy.

Memory is weaker when it transfers only a design prior. `relay_constellation/case_0003` gets the relay geometry right but fails to recover high-value ISL scheduling.

Skills and memory are not substitutes. Skills reduce contract and workflow errors, but the regional controls show that a skill can also anchor the search too tightly. Memory can encode richer empirical priors, but SatNet shows that it can also steer the space agent away from the true primary metric unless the memory explicitly records the optimization target and not just a valid construction.
