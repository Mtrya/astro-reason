# MCLP+TEG Relay Solver

A deterministic solver for the `relay_constellation` benchmark that combines:

1. **MCLP candidate selection** — greedily (or via small MILP) selects additional relay satellites to maximize demand-window coverage.
2. **TEG contact scheduling** — per-sample link selection (greedy or bounded MILP) with interval compaction.

## Entrypoints

```bash
./setup.sh          # prepares solver-local dependencies (no-op if already ready)
./solve.sh <case_dir> [config_dir] [solution_dir]
```

## Configuration

Place a `config.json` in `config_dir` to control solver behavior:

```json
{
  "mclp_mode": "auto",
  "scheduler_mode": "auto",
  "parallel_mode": "auto",
  "time_budget_s": 300,
  "milp_config": {
    "max_total_variables": 500,
    "max_samples": 50,
    "milp_time_limit_per_sample": 5.0
  }
}
```

| Key | Values | Default | Description |
|-----|--------|---------|-------------|
| `mclp_mode` | `"auto"`, `"greedy"`, `"milp"` | `"auto"` | Candidate selection strategy. `"auto"` tries MILP for small problems and falls back to greedy. |
| `scheduler_mode` | `"auto"`, `"greedy"`, `"milp"` | `"auto"` | Contact scheduling strategy. `"auto"` tries MILP within bounds, falls back to greedy. |
| `parallel_mode` | `"auto"`, `"parallel"`, `"sequential"` | `"auto"` | Execution model. `"auto"` uses process parallelism when there are multiple satellites or >1000 samples. |
| `time_budget_s` | positive integer | `300` | Expected per-case compute budget in seconds. Informational; the solver does not hard-cut at this limit. |
| `milp_config` | object | `{}` | Bounds for the scheduler MILP (see `src/milp_scheduler.py`). |

## Compute Envelope

This solver is a planning method that propagates satellites over a 96-hour horizon and evaluates link feasibility at 60-second granularity. A fair evaluation should allow **at least 5 minutes (300 s) per case**.

With `parallel_mode=auto` the solver uses all available CPU cores for:

- **Satellite propagation** — embarrassingly parallel across satellites (dominant stage, ~4 s per satellite sequentially).
- **Link-feasibility cache** — chunked by sample index across worker processes.

Parallel execution does not change algorithmic results; it only reduces wall-clock time.

## Output Artifacts

In `solution_dir`:

- `solution.json` — benchmark-shaped solution (`added_satellites`, `actions`).
- `status.json` — solver metadata, stage timings, execution model, and compute budget.
- `debug/` — optional diagnostic dumps (orbit candidates, link cache summary, MCLP rewards, TEG summary, MILP summary).

### `status.json` execution model

```json
{
  "execution_model": {
    "parallel_mode": "auto",
    "parallel_enabled": true,
    "worker_count": 16,
    "propagation_mode": "parallel",
    "link_cache_mode": "parallel",
    "parallel_fallback": false
  },
  "compute_budget_s": 300,
  "timings_s": {
    "propagate_backbone_total": 4.1,
    "propagate_backbone_per_satellite_ms": [4120, 4115, ...],
    "propagate_candidates_total": 2.0,
    "propagate_candidates_per_satellite_ms": [2050, 2048, ...],
    "build_link_cache_total": 0.35,
    ...
  }
}
```

## Algorithm Notes

- **Candidate generation** uses a conservative deterministic grid within case orbit constraints. The grid step defaults to the full altitude and inclination range, producing a small candidate set for speed.
- **MCLP greedy** evaluates marginal demand-sample coverage per candidate and selects up to `max_added_satellites`.
- **TEG greedy** scores each feasible link by demand weight, then selects links respecting per-satellite and per-endpoint degree caps.
- **MILP modes** are bounded: they activate only when the problem is small enough (configurable via `milp_config`).

## Dependencies

- Python 3.11+
- `brahe` (astrodynamics)
- `numpy`
- `pulp` (optional, for MILP modes)
