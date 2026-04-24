# Time-Window-Pruned Stereo MILP Solver

Standalone solver for the stereo-imaging scheduling problem described in Kim et al. 2020.

## Method Summary

The solver implements a five-stage pipeline:

1. **Candidate generation** — For each `(satellite, target, access_interval)`, samples start times and steering angles, then applies cheap local prechecks (horizon, duration, combined off-nadir, solar elevation, LOS).
2. **Product enumeration** — Evaluates all candidate combinations within each interval as stereo pairs or tri-stereo sets. Checks convergence angle, overlap fraction, and pixel-scale ratio against benchmark thresholds.
3. **Time-window cluster pruning** — Clusters candidates by temporal gap and caps each cluster to a lambda-bound, preserving anchors and products.
4. **Optimization** — Builds an abstract MILP (observation/pair/tri variables, conflict constraints, coverage constraints) and solves with OR-Tools or PuLP when available; falls back to a deterministic greedy solver otherwise.
5. **Repair** — Conservatively removes observations that violate transition-time or exclusivity constraints, then augments coverage with the best valid product for any uncovered targets.

The solver produces a non-empty `solution.json` containing selected observations whenever valid products exist. Coverage and quality depend on the dataset geometry and steering agility of the satellites.

## Solver Contract

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

`setup.sh` checks that `brahe`, `numpy`, `yaml`, and `skyfield` are available and optionally installs solver-local dependencies (`ortools`, `pulp`) from `requirements.txt`.

### Backend installation

The solver works out of the box with a deterministic greedy fallback. To use the exact MILP formulation, install one of the following backends:

```bash
pip install ortools>=9.11
# or
pip install pulp>=2.9
```

`setup.sh` will attempt to install both automatically when `pip` is available. With a backend installed, set `backend: auto` (default) or explicitly `backend: ortools` / `backend: pulp`. Increase `time_limit_s` to 1800 or more for exact solves on dense cases.

`solve.sh` writes:
- `solution.json`: benchmark-compatible list of selected observations.
- `status.json`: run summary, candidate counts, product counts, timing, backend used.
- `debug/candidate_summary.json`, `debug/product_summary.json`, `debug/pruning_summary.json`, `debug/repair_log.json` when `debug: true`.

## Known Limitations

- Access intervals are found with a coarse time-step search rather than exact SGP4 root-finding; minor drift relative to exact propagation is expected.
- Solar elevation and LOS checks are sampled at the observation midpoint.
- Overlap fraction is estimated with a deterministic polar grid rather than Monte Carlo; values may differ by a few percent from the verifier.
- If no valid stereo pairs or tri-stereo sets exist for a target (e.g. only one satellite accesses it, or slew time exceeds the gap between consecutive intervals), that target will remain uncovered.

## Citation

```bibtex
@article{kim2020task,
  title={Task Scheduling of Multiple Agile Satellites with Transition Time and Stereo Imaging Constraints},
  author={Kim, Junhong and Ahn, Jaemyung and Choi, Han-Lim and Cho, Doo-Hyun},
  journal={Journal of Aerospace Information Systems},
  year={2020},
  doi={10.2514/1.I010775}
}
```
