# Solver Audit: umcf_srr_contact_plan

## Bottom Line

- Target claim: faithful reproduction adapted to the benchmark
- Status: NOT_YET
- Compute status: FAIR_TO_EVALUATE
- Headline blockers:
  - LP relaxation is MISSING; the solver uses heuristic uniform probabilities instead of fractional flow optimization, which is the core of the UMCF/SRR method.
  - Node-degree caps are tracked but not consumed during internal rounding, so the oracle does not truly respect per-sample degree constraints.

## Compute And Runtime

### Literature regime

The reference method (Lamothe et al., UMCF with SRR for satellite contact planning) expects:

- An LP solver for the fractional relaxation of the multi-commodity flow problem.
- A column-generation loop to build the path-restricted LP from k-shortest paths.
- Sequential randomized rounding with dynamic path-change penalties.
- The LP dominates the theoretical runtime; rounding is comparatively cheap.

### Current regime

- No LP solver or external optimizer is used.
- All computation is pure Python 3.13 with NumPy vectorization for geometry.
- The solver runs end-to-end in approximately 13 seconds on the smoke case (test/case_0001).
- A 300-second timeout is configured for the experiment runner.

### Execution model

- **Propagation**: Multi-process via `ProcessPoolExecutor` across satellites. This is the only parallel stage and provides roughly a 9x speedup over single-threaded propagation (10.8 s vs 97.8 s on the smoke case).
- **Candidate selection**: Sequential Python loop by default. An opt-in `parallel_eval` flag exists but is disabled because per-candidate work (Union-Find reachability on ~30 nodes) is too small to amortize fork/pickle/join overhead.
- **Graph construction and SRR oracle**: Single-threaded Python per sample. This is vectorized NumPy for geometry but sequential for path enumeration and rounding.
- **Action generation**: Single-threaded Python for repair and compaction.

The dominant execution model for everything except propagation is single-threaded Python, but the aggregate runtime is small enough that this is not the primary blocker.

### Runtime profile

Measured on test/case_0001 (smoke case, 24 satellites total, ~5760 routing samples):

- Orbit propagation: ~10.8 s (71% of total)
- Graph construction (all samples): ~2.7 s (18%)
- Candidate selection: ~1.4 s (9%)
- SRR oracle + action generation: ~0.5 s (3%)
- Total end-to-end: ~13.4 s

### Why the current budget is or is not fair

The current budget is fair. The solver completes the full pipeline in well under 15 seconds on the smoke case. Even accounting for harder cases with more satellites or demands, the runtime is comfortably inside the 300-second envelope. The algorithm is not an iterative search method that needs sustained minutes to converge; it is a deterministic greedy selection followed by per-sample rounding. The only search-like component is the optional multi-run randomized mode, and even 10–20 seeds would finish within the timeout.

## Optimization And Time Budget

### Bottlenecks

1. **Orbit propagation** dominates at ~71% of runtime. Each worker must initialize a fresh brahe `NumericalOrbitPropagator` and EOP provider. This overhead is inherent to the process-based parallelism model and cannot be reduced without batching or caching propagator state across workers.
2. **Graph construction** is the next largest stage at ~18%. It is already vectorized NumPy but runs sequentially across samples.
3. **Candidate selection** was previously the dominant bottleneck (~51 s) due to `ProcessPoolExecutor` overhead on trivial per-candidate work. This has been fixed by switching to sequential evaluation.

### What to optimize first

- **Propagation worker initialization**: brahe propagator and EOP provider setup per worker is significant. If brahe ever exposes a way to share or serialize propagator state cheaply, that would help. This is not actionable today.
- **Graph construction across samples**: The per-sample geometry loops are vectorized within each sample but sequential across samples. Batching multiple samples into one NumPy operation could reduce Python-loop overhead, though the gain is marginal given the current 2.7 s cost.
- **Do not re-enable parallel candidate evaluation** unless the candidate library grows well past the current ~30-node scale.

### Recommended budget and run policy

- **Single deterministic run**: 60 seconds is more than sufficient.
- **Multi-run randomized mode**: 300 seconds allows roughly 20 seeds at current per-run cost. This is a fair evaluation for the randomized variant.
- No change to timeout policy is needed. The solver is not underprovisioned.

## Reproduction Gaps

### Implemented and adapted pieces

- **Path-set restriction (k-shortest simple paths)**: IMPLEMENTED — Dijkstra + DFS enumeration with hop-count then distance tie-breaking, configurable `k_paths` and `max_path_hops`.
- **SRR control flow (sequential demand-sorted rounding with capacity updates)**: IMPLEMENTED — Commodities sorted by decreasing demand weight, paths selected sequentially, unit edge capacities tracked.
- **Dynamic path-change penalty**: ADAPTED — Per-sample boost to the previously selected path. The reference formulation uses per-block penalties spanning multiple samples. The adaptation is benchmark-appropriate because the benchmark evaluates per-sample routing independently.
- **Action geometry pre-validation**: IMPLEMENTED — Exact brahe elevation filter removes boundary-mismatch samples before compaction.
- **Candidate orbit library generation**: IMPLEMENTED — Deterministic grid over altitude, inclination, RAAN, and mean anomaly with constraint filtering.
- **Greedy marginal candidate selection**: IMPLEMENTED — Union-Find reachability proxy scoring, selecting candidates by marginal contribution to demand connectivity.

### Partial or missing pieces

- **LP relaxation for fractional flows**: MISSING — The reference method solves a path-restricted LP to obtain fractional path probabilities, then rounds. The solver substitutes heuristic uniform probabilities (all candidate paths for a commodity weighted equally). This is the largest reproduction gap and blocks the target claim because the fractional solution drives rounding quality.
- **Column generation for path pricing**: MISSING — The reference builds the LP incrementally via column generation. Without an LP backend, this cannot exist.
- **Path-sequence / arc-path / arc-node LP formulations**: MISSING — The reference discusses these formulations; none are implemented.
- **Node-degree modeling in the oracle**: PARTIAL — Per-sample degree caps (`max_links_per_satellite`, `max_links_per_endpoint`) are enforced as hard constraints in the action-generation repair step, but they are not modeled as node capacities inside the SRR oracle itself. The oracle can select paths that violate degree caps, relying on repair to drop edges afterward. This means the oracle is optimizing an objective that does not match the true feasible set.
- **k-nearest hop restriction**: MISSING — The reference restricts candidate paths to those using only satellites within k hops of source or destination. This is not implemented.

### What must change to reach the target claim

1. **Implement LP relaxation**: Add a fractional-flow LP backend (even a lightweight one via `scipy.optimize.linprog` or `cvxopt`) to replace heuristic probabilities. This is the single most important change.
2. **Integrate degree caps into the oracle**: Model `max_links_per_satellite` and `max_links_per_endpoint` as node capacities during rounding, not just in post-hoc repair. This may require augmenting the SRR state with per-node usage counts and rejecting paths that would exceed caps.
3. **Add column generation loop**: Once an LP backend exists, implement the pricing subproblem to iteratively add improving paths rather than pre-computing a fixed k-shortest set.
4. **Implement k-nearest hop restriction**: Filter candidate paths by hop distance from source and destination endpoints.

## Action Plan

- **Algorithmic completion work** (highest priority):
  - Add an LP relaxation backend. `scipy.optimize.linprog` is the most realistic choice given the no-external-solver constraint, though it may struggle with the full per-sample formulation size. Consider solving a single aggregated LP across samples or a reduced representative subset.
  - Integrate node-degree caps into the SRR oracle rounding logic.
  - Implement k-nearest hop path filtering.
- **Optimization work** (lower priority, marginal gains):
  - Investigate batching graph construction across samples to reduce Python-loop overhead.
  - Document that parallel candidate evaluation is available but not recommended at current scale.
- **Runtime-budget or run-policy changes**: None required. Current budget is fair.

## Sanity Footnote

- The solver produces valid solutions on all tested cases. The verifier accepts its submissions. Service fraction on the smoke case is ~0.81 with candidate selection enabled, versus ~0.75 with backbone only. The randomized multi-run mode occasionally improves results (case_0002: 0.965 vs 0.954 deterministic) but is not consistently better (case_0005: 0.814 vs 0.877 deterministic). Validity is not in question; reproduction fidelity is.
