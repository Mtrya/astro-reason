# Solver Audit: regional_coverage_celf_submodular

## Bottom Line
- Target claim: faithful reproduction adapted to the benchmark with fair optimization and compute envelope
- Status: NOT_YET
- Compute status: OPTIMIZATION_BLOCKED
- Headline blockers:
- The CELF/CEF fixed-set selector is implemented and covered by focused lazy-vs-naive tests, but the current public smoke run maps all capped candidates to zero coverage samples.
- More runtime will not materially improve the current smoke result until solver-local candidate geometry and coverage mapping produce nonzero candidate rewards.
- The runtime is single-threaded Python across candidate generation, coverage mapping, CELF selection, and repair. That is acceptable for the current tiny capped smoke path, but not yet a fair scalable compute envelope for quality evaluation.
- The Leskovec online bound from Section 3.2 is not implemented, and the solver does not yet provide quality certificates against the fixed candidate set.

## Compute And Runtime
### Literature regime
Leskovec et al. treat the expensive part as repeated submodular reward evaluation over a large fixed ground set. Section 4 emphasizes sparse inverted-index representations for fast reward lookup and CELF lazy marginal recomputation to avoid the naive greedy cost of repeatedly evaluating every remaining element. The reported regime is large-scale selection over many possible nodes and many scenarios, with preprocessing that makes later marginal updates cheap.

### Current regime
The solver builds a fixed set of timed strip candidates from the public regional-coverage case, maps each candidate to public coverage-grid samples, runs both unit-cost and cost-benefit CELF variants when enabled, chooses the higher objective, and then runs deterministic schedule validation and repair.

The default smoke configuration uses `time_stride_s: 600`, `max_candidates_total: 512`, and `budget: max_actions_total`. On `test/case_0001`, the latest main_solver artifact reports 512 candidates, all from `sat_iceye-x2`, with `truncated_by_cap: true`.

### Execution model
The hot path is single-threaded Python. Candidate generation is nested Python loops, coverage mapping scans coverage samples against an approximate centerline, CELF uses a Python `heapq`, and repair uses Python sequence checks. There is no vectorized NumPy, compiled extension, multiprocessing, or distributed execution in the solver.

### Runtime profile
The current smoke profile is dominated by solver-local coverage mapping, not CELF:

- case loading: about 0.030 s
- candidate generation: about 0.001 s
- coverage mapping: about 0.142 s
- CELF selection: about 0.002 s
- schedule repair: about 0.00004 s
- solver total: about 0.177 s
- official verifier: about 14.16 s

The smoke run officially verifies as valid, with no violations, but emits an empty solution with `coverage_ratio: 0.0`.

### Why the current budget is or is not fair
The current budget is not the limiting factor for the smoke case. The selector receives no positive marginal rewards because `coverage_summary.zero_coverage_count == candidate_count == 512`. Increasing runtime, thread count, or selection budget would only recompute zero-gain candidates faster or longer.

For quality evaluation after the coverage signal is fixed, the current default cap and stride are likely too conservative. A fair next regime should allow a broader candidate set across satellites, roll values, and start times, and should give preprocessing plus selection at least a multi-minute budget if coverage mapping remains Python-heavy.

## Optimization And Time Budget
### Bottlenecks
The immediate bottleneck is modeling, not raw runtime: solver-local candidate coverage does not overlap the public coverage grid on the smoke case. The next bottleneck after that will likely be coverage mapping, because it currently loops over candidates and samples in Python.

CELF selection itself is not currently a bottleneck. It is exercised by tests, but the public smoke run does not demonstrate lazy savings because every candidate has zero marginal gain, so both variants recompute all 512 entries once and accept none.

### What to optimize first
First fix the candidate geometry and coverage mapping so smoke candidates produce nonzero candidate rewards when physically plausible. Candidate generation should also avoid deterministic truncation that only samples the first satellite and first roll bins.

After coverage signal exists, optimize coverage mapping before simply increasing runtime:

- use spatial indexing over coverage samples by region or lat/lon bins
- broaden candidates deterministically across satellites before applying caps
- consider vectorized distance checks or compiled spatial primitives
- preserve deterministic ordering and debug summaries while adding parallel mapping

Only then should CELF runtime budgets be expanded meaningfully.

### Recommended budget and run policy
For the next fidelity phase, use a two-tier policy:

- smoke/contract mode: keep a small deterministic cap, but require nonzero candidate coverage on at least one public smoke case unless the case truly has no accessible strips
- evaluation mode: use an uncapped or much larger deterministic candidate set with a total solver budget in the several-minute range, and report whether preprocessing or selection consumed the budget

Repeated runs or random seeds are not required for this deterministic CELF reproduction. Multi-config sweeps over stride, cap, roll grid, and cost mode are more relevant than stochastic restarts.

## Reproduction Gaps
### Implemented and adapted pieces
- IMPLEMENTED: fixed-ground-set monotone unique coverage reward over candidate sample sets.
- IMPLEMENTED: unit-cost lazy greedy selection.
- IMPLEMENTED: cost-benefit lazy greedy selection.
- IMPLEMENTED: CEF-style return of the higher-reward unit-cost or cost-benefit variant.
- IMPLEMENTED: deterministic tie breaking and small-case lazy-vs-naive agreement tests.
- ADAPTED: paper sensor/node is mapped to one timed `strip_observation` candidate.
- ADAPTED: paper scenario/item is mapped to one public coverage-grid sample index.
- ADAPTED: paper budget is mapped to benchmark `max_actions_total` or an explicit solver budget.
- ADAPTED: post-selection validation and deterministic repair are added because the benchmark requires slew, overlap, power, duty, and output-schema validity outside the paper's pure set-selection model.

### Partial or missing pieces
- PARTIAL: candidate coverage geometry is solver-local and approximate, and currently produces zero coverage on the smoke artifact.
- PARTIAL: candidate generation is deterministic but cap-biased toward early satellites and roll bins.
- PARTIAL: cost modes exist, but the default smoke uses action-count cost, making unit-cost and cost-benefit equivalent.
- MISSING: Leskovec Section 3.2 online optimality bound.
- MISSING: sparse or indexed coverage representation at the scale implied by Section 4.
- MISSING: fair evaluation run policy for larger candidate sets and multi-case quality reporting.
- EXTRA: schedule repair is outside Leskovec CELF/CEF, but is a benchmark-validity adaptation and is reported separately.

### What must change to reach the target claim
The solver needs nonzero, verifier-relevant candidate coverage before the reproduction claim is meaningful beyond algorithmic scaffolding. Once that signal exists, it needs a fair candidate-generation policy, spatially efficient coverage mapping, and a documented evaluation budget that lets the fixed-set CELF method run as a planning solver rather than a tiny smoke-validity path.

## Action Plan
- Fix solver-local geometry or candidate sampling so public smoke candidates cover at least some regional-coverage samples when plausible.
- Replace the current first-N candidate cap with a deterministic balanced cap across satellites, roll bins, durations, and time windows.
- Add audit tests or smoke fixtures that distinguish "valid empty output" from "selector had nonzero candidate rewards and made a selection."
- Add spatial indexing or vectorization for candidate-to-sample mapping before increasing runtime budgets.
- Add optional online-bound computation over the fixed candidate set if the solver is expected to claim the Section 3.2 quality-certificate part of Leskovec et al.
- Define a main_solver evaluation config with a larger cap, broader stride/roll sweep, and a multi-minute total budget after the coverage mapping issue is resolved.

## Sanity Footnote
- Hardened solver contract validation passes after moving CELF tests under `solvers/regional_coverage/celf_submodular/tests` and adding solver-local `test.sh`.
- Focused CELF tests pass: 18 tests.
- Official main_solver smoke verification passes on `regional_coverage_celf_submodular` and `test/case_0001` with `valid: true` and no verifier violations.
- The verified smoke output is empty and scores zero coverage, so it is validity evidence only, not quality evidence.
