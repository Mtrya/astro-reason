# Reproduction Fidelity Notes

This document explains how the solver reproduces methods from Rogers et al. and Gerard et al., and how those methods are adapted to the `relay_constellation` benchmark.

## What Comes From Rogers

Rogers et al. formulate constellation configuration design as a family of MILPs, including the **Maximal Covering Location Problem (MCLP)**, which selects a fixed number of orbital slots to maximize observation rewards over targets.

This solver reproduces the Rogers layer through:

- **Finite orbital slot library** (`orbit_library.py`) — deterministic grid of candidate orbits within case altitude, inclination, eccentricity, and RAAN bounds. Default: 2 altitude shells × 2 inclination bands × 3 RAAN planes × 2 phase slots = 24 candidates.
- **Cardinality constraint** — selects up to `max_added_satellites` (benchmark upper bound), not an exact fixed number.
- **Coverage reward scoring** — each candidate is scored by its marginal contribution to demand-window service potential (the set of demand-samples that become reachable when the candidate is added).
- **Greedy selection** — iterative marginal-gain heuristic that adds the highest-scoring candidate until the budget is exhausted or marginal gain drops to zero.
- **Optional small MILP** — when candidates ≤ 20 and `max_added_satellites` ≤ 5, a PuLP/CBC MILP solves the exact MCLP over the simplified coverage matrix. Falls back to greedy if the MILP is too large or fails.

## What Comes From Gerard

Gerard et al. introduce a **time-expanded graph (TEG)** contact-plan scheduler for optical interplanetary networks, with per-sample link selection, degree-cap constraints, and both greedy and MILP solvers.

This solver reproduces the Gerard layer through:

- **Time-expanded graph representation** — feasibility of every ground link and inter-satellite link is precomputed at every routing sample (default 60 s step) over the full horizon.
- **Per-sample greedy max-weight matching** — at each sample, feasible links are scored by active demand weight, then selected greedily respecting per-satellite and per-endpoint degree caps.
- **Interval compaction** — consecutive samples with the same link selected are merged into compact interval actions.
- **Bounded per-sample MILP** — for small problems (≤ 50 samples with links, ≤ 500 total binary variables), a PuLP/CBC MILP selects links at each sample to maximize total utility. Falls back to greedy if bounds are exceeded or the solver fails.
- **Degree-cap enforcement** — both greedy and MILP respect `max_links_per_satellite` and `max_links_per_endpoint`.

## Benchmark Adaptations

The original papers target different mission contexts. The following adaptations bridge paper methods to the benchmark contract:

| Paper Concept | Benchmark Adaptation |
|---------------|----------------------|
| Rogers observation reward (coverage over targets) | Demand-window service-potential score (path diversity via ground + ISL connectivity) |
| Rogers fixed cardinality N (exactly N satellites) | `max_added_satellites` upper bound (`<= K`) |
| Gerard capacity objective (maximize temporal flow) | Action-interval generator (ground_link and inter_satellite_link intervals) |
| Gerard retargeting delay (pointing/acquisition overhead) | **Not modeled** — benchmark assumes instant link switching |
| Gerard route tables and DTN forwarding | **Not modeled** — benchmark verifier owns route allocation and latency scoring |
| Rogers MILP over full candidate set | Greedy marginal-gain heuristic with optional small MILP for ≤20 candidates |
| Gerard full-horizon MILP scheduler | Bounded per-sample MILP with deterministic greedy fallback |

## Known Limitations

- **Coarse candidate grid**: default 24 candidates is much smaller than Rogers' hundreds-to-thousands. This is configurable via `orbit_grid` but trades fidelity for compute time.
- **Greedy MCLP**: the default greedy selector is not guaranteed optimal. The optional MILP mode is exact but bounded to small instances.
- **Per-sample MILP scheduler**: solves each sample independently, not a full-horizon MILP as in Gerard. This is a scalability adaptation.
- **No retargeting delay**: benchmark does not model optical PAT overhead, so the solver does not account for it.
- **Verifier-owned routing**: the solver cannot influence which routes the verifier chooses. High link utility does not guarantee high verifier service fraction if the verifier selects different paths.

## Expected Behavior

When running mode comparisons, the following ordering should hold in most cases:

1. **no-added baseline** (backbone only) ≤ **greedy MCLP + greedy scheduler** in `service_fraction`
2. **greedy scheduler** ≤ **MILP scheduler** on small cases where MILP fires
3. More candidates (via `orbit_grid`) should improve MCLP score but increase propagation time

If the ordering is violated, inspect:
- Whether the reward construction matches verifier route rules
- Whether degree-cap repair or overlap issues are present
- Whether the candidate grid covers the orbital regions the verifier expects
