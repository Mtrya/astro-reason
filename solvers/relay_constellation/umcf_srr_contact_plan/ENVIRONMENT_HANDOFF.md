# UMCF/SRR Solver Environment Handoff

## Current State

Phase 2 LP code is implemented, but the solver-local Python environment still needs a clean owner pass. The LP backend is `scipy.optimize.linprog(method="highs")`, imported lazily by `src/lp_relaxation.py`.

The current tracked scripts deliberately do not attempt package installation:

- `setup.sh` validates imports from the active interpreter.
- `solve.sh` runs the active interpreter with `PYTHONPATH` pointed at the repo root.
- `pyproject.toml` and `uv.lock` were not changed for SciPy.

This means LP mode requires an environment that already provides:

- `brahe`
- `numpy`
- `pyyaml`
- `scipy`

## Attempted Path

I started wiring `.venv` creation directly in `setup.sh`, but package installation was unreliable in this session:

- direct `pip` downloads were extremely slow and timed out repeatedly;
- resolving `brahe>=1.3.4` pulled a `matplotlib>=3.9.4` dependency that the package index could not satisfy for Python 3.13;
- installing `brahe --no-deps` may be viable, but should be tested deliberately rather than committed half-validated.

## Recommended Finish

Use a solver-local `.venv` hidden behind `setup.sh` and `solve.sh`, without adding SciPy to the top-level project dependencies.

Suggested implementation:

1. `setup.sh`
   - create `solvers/relay_constellation/umcf_srr_contact_plan/.venv`;
   - prefer `uv venv` / `uv pip install` if `uv` is available;
   - install `numpy`, `pyyaml`, `scipy`, and `brahe`;
   - if `brahe` resolution still fails because of plotting dependencies, test and document `uv pip install --no-deps brahe>=1.3.4`;
   - validate imports with `.venv/bin/python`.

2. `solve.sh`
   - fail fast if `.venv/bin/python` is missing;
   - run `.venv/bin/python -m solvers.relay_constellation.umcf_srr_contact_plan.src.solve`;
   - keep `PYTHONPATH` pointed at the repo root.

3. Validation
   - `bash solvers/relay_constellation/umcf_srr_contact_plan/setup.sh`
   - `solvers/relay_constellation/umcf_srr_contact_plan/.venv/bin/python -m pytest tests/solvers/test_relay_umcf_srr.py`
   - `uv run python experiments/main_solver/run.py --benchmark relay_constellation --solver relay_constellation_umcf_srr_contact_plan --case test/case_0001`

4. Artifact checks
   - `debug/lp_summary.json` exists;
   - `debug/srr_summary.json` reports `"probability_source": "lp"`;
   - `status.json` includes `srr_lp_diagnostics`;
   - official smoke status is `verified`.

## Interim Testing Note

LP tests in `tests/solvers/test_relay_umcf_srr.py` skip when SciPy is absent. Non-LP focused tests still run in the current repository environment.
