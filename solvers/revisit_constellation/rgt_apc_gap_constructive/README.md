# RGT/APC Gap-Constructive Solver

This solver is a runnable reproduced solver for `revisit_constellation`.

It combines repeating-ground-track/access-profile-constellation design ideas from Zhang and Lee with the freshness-aware constructive scheduling pattern from Mercado-Martinez, Soret, and Jurado-Navas, adapted to the benchmark's public case and solution contract.

## Citation

```bibtex
@article{zhang2018leo,
  title = {LEO Constellation Design Methodology for Observing Multi-Targets},
  author = {Zhang, Chen and Jin, Jin and Kuang, Linling and Yan, Jian},
  journal = {Astrodynamics},
  volume = {2},
  number = {2},
  pages = {121--131},
  year = {2018},
  doi = {10.1007/s42064-017-0015-4}
}

@article{lee2020apc,
  title = {Satellite Constellation Pattern Optimization for Complex Regional Coverage},
  author = {Lee, Hang Woon and Shimizu, Seiichi and Yoshikawa, Shoji and Ho, Koki},
  journal = {Journal of Spacecraft and Rockets},
  volume = {57},
  number = {6},
  pages = {1309--1327},
  year = {2020},
  doi = {10.2514/1.A34657},
  eprint = {1910.00672},
  archivePrefix = {arXiv}
}

@article{mercado2025energyconstructive,
  title = {Scheduling Agile Earth Observation Satellites with Onboard Processing and Real-Time Monitoring},
  author = {Mercado-Martinez, Antonio M. and Soret, Beatriz and Jurado-Navas, Antonio},
  year = {2025},
  eprint = {2506.11556},
  archivePrefix = {arXiv}
}
```

The solver is standalone. It reads `assets.json` and `mission.json`, writes a benchmark solution JSON, and does not import or execute benchmark, experiment, runtime, or other solver internals.

## Method Summary

The pipeline is:

1. Load the public `revisit_constellation` case files.
2. Generate deterministic circular RGT/APC-style candidate satellites inside the case altitude and satellite-count bounds.
3. Sample candidate-target access profiles and group visible samples into observation opportunities.
4. Greedily select satellites by benchmark-style marginal improvement to revisit-gap timelines.
5. Build observation actions with Mercado-style freshness, assignment flexibility, and opportunity-cost priorities.
6. Run solver-local validation and deterministic insertion/removal repair.
7. Emit the repaired schedule as `solution.json` and retain no-op, FIFO, constructive, and repaired mode comparisons as debug evidence.

The final action set contains only `observation` actions. Satellite states are Cartesian GCRF states at mission start.

## Benchmark Adaptation

The benchmark differs from the papers in several important ways:

- Zhang and Lee operate primarily at the constellation/access-profile design layer. The benchmark scores scheduled observation midpoints, so this solver uses RGT/APC access timelines as candidate-design evidence and then schedules concrete observations.
- Lee's APC formulation uses circular convolution between seed access profiles, constellation pattern vectors, and coverage timelines. This solver reproduces the shifted-access-profile idea with bounded phase slots, but does not solve Lee's BILP coverage-satisfaction model.
- Mercado's AoI freshness is adapted to benchmark midpoint revisit gaps. The current target freshness is the target's largest boundary-inclusive gap from mission start, existing observation midpoints, and mission end.
- Assignment flexibility is the count of remaining locally feasible observation options for the target.
- Opportunity cost is the quality-weighted freshness profit of locally conflicting options that would be blocked by choosing an observation.
- The benchmark's hard validity rules require geometry, non-overlap, slew/settle, and battery feasibility. The solver checks these locally and then relies on official experiment-owned verification for the authoritative result.

APC visibility/access timelines are not final scheduled observations. They are candidate opportunities. The emitted `solution.json` uses the repaired constructive schedule.

## Solver Contract

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

`setup.sh` is a no-op when using the project environment.

`solve.sh` writes:

- `solution.json`: primary benchmark solution
- `status.json`: solver summary, timings, local validation, mode comparison, and paper-to-benchmark adaptation notes
- `debug/*`: detailed debug artifacts

## RGT/APC Orbit Library

The orbit library enumerates circular RGT-style base orbits from integer revolution/day ratios and expands them into deterministic phase slots. Candidates are filtered against the case's initial-orbit altitude bounds and capped by both `max_candidates` and `max_num_satellites`.

When no RGT candidate survives the altitude bounds, the solver falls back to a small deterministic circular-altitude grid. This fallback is reported in `status.json`; it is a robustness path, not a claim of APC optimality.

## Gap-Aware Satellite Selection

Candidate satellites are selected greedily. Each round adds the candidate whose opportunity timeline most improves the benchmark-shaped score:

- threshold violation count
- capped maximum revisit gap
- raw maximum revisit gap
- mean revisit gap

All gap calculations are boundary-inclusive and use observation midpoints, matching the benchmark scoring convention.

## Constructive Scheduling And Repair

The scheduler first builds one observation option per visibility window, anchored near the best local off-nadir/range sample. It then chooses observations by:

- freshness: largest current target revisit gap
- flexibility: fewer remaining target options first
- opportunity cost: lower conflict profit loss first
- deterministic ties: timestamps, satellite IDs, target IDs, and window IDs

Solver-local validation checks unknown references, duration, sampled geometry, same-satellite overlap, required slew/settle gaps, and conservative battery risk.

Repair is deterministic. It removes locally invalid or risky observations with the lowest score damage, then tries to insert feasible observations for high-gap targets. The emitted solution uses the repaired mode. The no-op, FIFO, and unrepaired constructive modes are retained only for reproduction-fidelity diagnostics.

## Configuration

The solver reads optional config from either:

- `<config_dir>/config.yaml`
- `<config_dir>/config.yml`

See [config.example.yaml](./config.example.yaml) for a complete example.

Key knobs:

- `orbit_library.max_candidates`
- `orbit_library.max_rgt_days`
- `orbit_library.min_revolutions_per_day`
- `orbit_library.max_revolutions_per_day`
- `orbit_library.phase_slot_count`
- `orbit_library.fallback_altitude_count`
- `visibility.sample_step_sec`
- `visibility.max_windows`
- `visibility.keep_samples_per_window`
- `selection.max_selected_satellites`
- `selection.require_positive_improvement`
- `scheduling.max_actions`
- `scheduling.max_actions_per_target`
- `scheduling.observation_margin_sec`
- `scheduling.transition_gap_sec`
- `scheduling.require_positive_gap_improvement`
- `scheduling.enforce_simple_energy_budget`
- `scheduling.enable_repair`
- `scheduling.repair_max_iterations`

Lower visibility sample steps improve opportunity fidelity but increase runtime. `transition_gap_sec: null` uses a conservative case-derived bang-coast-bang slew/settle gap during option conflict checks.

## Debug Artifacts

Every run writes:

- `debug/orbit_candidates.json`: generated candidate satellite states
- `debug/visibility_windows.json`: sampled candidate-target access windows
- `debug/selection_rounds.json`: greedy satellite-selection rounds and marginal improvements
- `debug/scheduling_decisions.json`: constructive scheduling decisions, priorities, scores, and improvements
- `debug/scheduling_rejections.json`: skipped options and solver-local reasons
- `debug/local_validation.json`: final local hard-validity and high-gap report
- `debug/repair_steps.json`: deterministic removal/insertion repair log
- `debug/scheduling_summary.json`: compact option, action, rejection, repair, high-gap, and mode counts
- `debug/mode_comparison.json`: solver-local no-op, FIFO, constructive, and repaired comparison metrics
- `debug/adaptation_notes.json`: paper concepts mapped to benchmark mechanics

These artifacts are intended to answer:

- whether candidate coverage exists before scheduling
- which satellites improved the revisit timeline
- why a target remained high-gap or unobserved
- whether repair changed the constructive solution
- how FIFO/no-op compare with the constructive and repaired modes
- which paper components are reproduced and which are benchmark adaptations

## Running It

Direct setup:

```bash
./solvers/revisit_constellation/rgt_apc_gap_constructive/setup.sh
```

Direct solve on a public smoke case:

```bash
./solvers/revisit_constellation/rgt_apc_gap_constructive/solve.sh \
  benchmarks/revisit_constellation/dataset/cases/test/case_0001
```

Direct solve with a config directory:

```bash
./solvers/revisit_constellation/rgt_apc_gap_constructive/solve.sh \
  benchmarks/revisit_constellation/dataset/cases/test/case_0001 \
  /path/to/config_dir \
  /tmp/revisit_rgt_apc_solution
```

Official smoke verification through `main_solver`:

```bash
uv run python experiments/main_solver/run.py \
  --benchmark revisit_constellation \
  --solver revisit_constellation_rgt_apc_gap_constructive \
  --case test/case_0001
```

Aggregate experiment results:

```bash
uv run python experiments/main_solver/aggregate.py
```

## Sanity Baseline

The literature reports coverage and AoI-style scheduling behavior, not benchmark `capped_max_revisit_gap_hours` on these public cases. Treat the papers as method references, not as a numeric target table.

What matters here is:

- official verification passes
- selected satellite count respects the case cap
- local validation is clean before official verification
- constructive/repaired modes improve mean revisit gap over no-op
- repair does not collapse the schedule
- high-gap and unobserved targets are visible in debug summaries

On the official smoke case, the experiment-owned verifier has passed with 18 satellites, 238 observation actions, and no hard-validity violations. Some targets remain high-gap because the bounded RGT/APC candidate grid does not cover every target frequently enough under the benchmark geometry and resource rules.

## Known Limitations

- This is a faithful method-family reproduction adapted to the benchmark, not a reproduction of every table or exact optimization model in Zhang, Lee, or Mercado.
- The Lee APC/BILP coverage-satisfaction model is not solved exactly; RGT/APC is used as deterministic candidate generation and access-profile evidence.
- The solver uses circular RGT-style or fallback circular candidates only; it may miss asymmetric non-RGT or elliptical designs that score better.
- Visibility windows are sampled, so very short opportunities can be missed or approximated.
- Battery feasibility is handled by conservative solver-local validation and repair, while the benchmark verifier remains authoritative.
- Full public-case sweeps are slower than the focused smoke because visibility sampling dominates runtime.

## Evidence Type

This solver is registered in `experiments/main_solver` and `solvers/finished_solvers.json` with `evidence_type: reproduced_solver`.
