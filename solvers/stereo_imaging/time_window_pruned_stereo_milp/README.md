# Time-Window-Pruned Stereo MILP Solver — Phase 1

Standalone scaffold for the stereo-imaging MILP solver described in Kim et al. 2020.

## Phase 1 Scope

- Public YAML parsing for `satellites.yaml`, `targets.yaml`, and `mission.yaml`.
- Deterministic candidate observation library per `(satellite, target, access_interval)`.
- Cheap local prechecks: horizon, duration, combined off-nadir, solar elevation, LOS.
- Emits a **valid empty `solution.json`** and a debug candidate summary.

## Phase 1 Limitations

- Access intervals are approximated with a coarse time step; exact SGP4/access reproduction is deferred to Phase 6.
- No stereo pair/tri enumeration, pruning, or MILP model yet.

## Solver Contract

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

`setup.sh` checks that `brahe`, `numpy`, `yaml`, and `skyfield` are available.

`solve.sh` writes:
- `solution.json`: benchmark-compatible empty solution.
- `status.json`: run summary, candidate counts, rejection reasons, timing.
- `debug/candidate_summary.json`: sample candidates and rejections when `debug: true`.

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
