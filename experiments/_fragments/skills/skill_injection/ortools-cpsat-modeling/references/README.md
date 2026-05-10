# OR-Tools CP-SAT Modeling References

Checked on 2026-05-10 against official OR-Tools documentation and a throwaway validation environment.

## Official OR-Tools Sources

- CP-SAT solver guide: https://developers.google.com/optimization/cp/cp_solver. The guide imports `from ortools.sat.python import cp_model`, creates `cp_model.CpModel()`, uses lowercase Python methods such as `new_int_var`, `add`, `solve`, and `value`, explains that CP-SAT requires integer modeling, and documents statuses `OPTIMAL`, `FEASIBLE`, `INFEASIBLE`, `MODEL_INVALID`, and `UNKNOWN`.
- Setting solver limits: https://developers.google.com/optimization/cp/cp_tasks. The Python example sets `solver.parameters.max_time_in_seconds = 10.0` before `solver.solve(model)`.
- Python install overview: https://developers.google.com/optimization/install/python. The page recommends the Pip package path for normal Python use.
- Python API reference: https://or-tools.github.io/docs/pdoc/ortools/sat/python/cp_model.html. The generated API docs include `CpModel.new_bool_var`, `CpModel.add`, `CpModel.maximize`, `CpSolver.solve`, `CpSolver.value`, `CpSolver.status_name`, `CpSolver.objective_value`, `CpSolver.best_objective_bound`, and `CpSolver.wall_time`.

## Temporary Environment Validation

- First attempt: `/tmp/astroreason-ortools-cpsat-skill-env` with system Python 3.14.4. Install command `/tmp/astroreason-ortools-cpsat-skill-env/bin/python -m pip install --upgrade pip ortools` could not complete because compatible transitive wheels were unavailable for the current Python 3.14 environment, ending at `No matching distribution found for protobuf<6.34,>=6.33.1`.
- Validated environment: `/tmp/astroreason-ortools-cpsat-skill-env-py312`.
- Python: `3.12.12`.
- Install command: `UV_CACHE_DIR=/tmp/astroreason-uv-cache uv pip install --python /tmp/astroreason-ortools-cpsat-skill-env-py312/bin/python ortools`.
- Installed package: `ortools==9.15.6755` with `protobuf==6.33.6`, `numpy==2.4.4`, and `pandas==3.0.2`.
- API smoke check in that environment confirmed `CpModel.new_bool_var`, `CpModel.add`, `CpModel.maximize`, `CpSolver.solve`, `CpSolver.value`, `CpSolver.status_name`, `CpSolver.objective_value`, and `CpSolver.best_objective_bound`.
- Example validation:
  - `/tmp/astroreason-ortools-cpsat-skill-env-py312/bin/python experiments/_fragments/skills/skill_injection/ortools-cpsat-modeling/examples/binary_coverage_cp_sat.py` returned `OPTIMAL`, selected `["p_a", "p_d", "p_e"]`, coverage `4`, and quality `78`.
  - `/tmp/astroreason-ortools-cpsat-skill-env-py312/bin/python experiments/_fragments/skills/skill_injection/ortools-cpsat-modeling/examples/sequential_lexicographic_solve.py` returned two `OPTIMAL` statuses, selected `["p_a", "p_d", "p_e"]`, primary coverage `4`, and secondary quality `78`.

## Local Evidence Anchor

- `solvers/stereo_imaging/time_window_pruned_stereo_milp/README.md` is used only as evidence for generic product-selection decomposition: candidates/products, conflict graph, coverage variables, lexicographic objective, time limits, clear backend status, and the warning that candidate/product enumeration can dominate runtime.
- `solvers/stereo_imaging/time_window_pruned_stereo_milp/config.example.yaml` is used only as evidence for generic runtime configuration style: explicit backend choice, solve time limit, pruning knobs, debug artifacts, and avoiding silent fallback.
- This skill intentionally does not copy stereo-imaging formulas, solver source code, solver commands, or benchmark-specific product strategy.
