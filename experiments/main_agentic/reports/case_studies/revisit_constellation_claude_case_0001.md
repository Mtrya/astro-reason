# Claude on Revisit Constellation Case 0001

This case study diagnoses why `claude_code` succeeded unusually well on `revisit_constellation` `test/case_0001`. The focus is not benchmark-wide Claude performance. It is the single run where Claude inferred a verifier-compatible astrodynamics model from a black-box workspace, reached the primary revisit floor, and then reduced the architecture to 10 satellites.

The evidence is anchored to tracked artifacts: aggregate outcomes in `experiments/main_agentic/reports/revisit_constellation.md`, run metadata in `experiments/main_agentic/reports/traces/data/runs.js`, the exposed workspace contract in `experiments/_fragments/prompts/revisit_constellation/README.default.md`, benchmark assembly in `experiments/main_agentic/benchmarks/revisit_constellation.yaml`, the trace export `experiments/main_agentic/reports/traces/data/events/revisit_constellation__claude_code__test__case_0001.js`, solver baseline rows in `experiments/main_solver/README.md`, and solver documentation under `solvers/revisit_constellation/`.

## Outcome

The result is a real case-level win. In `main_agentic`, Claude's final `case_0001` artifact is valid with `capped_max_revisit_gap_hours = 6.0`, `max_revisit_gap_hours = 5.933333333333334`, and `num_satellites = 10`. The primary metric is at the theoretical floor because every target in this case has `expected_revisit_period_hours = 6.0`, and the contract defines each target's capped gap as `max(max_revisit_gap_hours, expected_revisit_period_hours)`.

On the same case, the other main-agentic rows are weaker in at least one dimension:

| Harness | Valid | capped gap h | max gap h | satellites |
| --- | --- | ---: | ---: | ---: |
| `claude_code` | true | 6.0000 | 5.9333 | 10 |
| `opencode_dpsk` | true | 6.0000 | 5.0583 | 15 |
| `codex` | true | 6.0628 | 7.0833 | 18 |
| `kimi_cli` | true | 6.1784 | 9.5633 | 14 |
| `opencode_minimax` | false | - | - | - |

The solver baseline context is also important. The stronger recorded first-party solver, `revisit_constellation_j2_rgt_set_cover`, reaches the 6 h floor on `case_0001` with 16 satellites and 225 actions. Claude reaches the same primary floor with 10 satellites. The older `rgt_apc_gap_constructive` row uses 20 satellites and remains at capped gap 7.3074 h.

## Workspace Authority

The assembled workspace exposed a rendered README, `AGENTS.md`, the two case files, and an opaque verifier binary. It did not expose benchmark verifier source. The experiment config assembles:

- `experiments/_fragments/prompts/revisit_constellation/README.default.md` as `/app/workspace/README.md`
- `benchmarks/revisit_constellation/dataset/cases/test/case_0001` as `/app/workspace/case`
- an opaque verifier artifact as `/app/workspace/verifier`
- the default prompt as `/home/korolev/PROMPT.md`

So the key behavior is not "Claude read verifier internals." It did not. The interesting behavior is that it inferred enough of the verifier's numerical model from the public contract, Brahe APIs, and verifier error messages.

Claude's early authority acquisition was good. It listed `case/`, read `mission.json` and `assets.json`, then read `/app/workspace/README.md` and `AGENTS.md`. It found `/app/workspace/verifier`, checked Python packages, and saw `brahe`, `numpy`, `scipy`, `sgp4`, and `skyfield`. The trace does not show a `./verifier --help` call for this run, but it does show direct verifier use after generating candidates.

## The Diagnostic Pivot

Claude's first successful-looking solver was not verifier-valid. It initially wrote a fast private model with custom J2 propagation and a simplified GCRF-to-ITRF Earth rotation. That private model produced a 20-satellite schedule whose internal metric was already at the 6 h floor. But the packaged verifier rejected it.

The verifier errors were precise:

- several observations were just beyond the 30 degree off-nadir limit, such as 30.041, 30.349, 30.291, 30.157, 30.279, 30.257, and 30.567 degrees;
- two same-satellite transitions lacked enough slew and settle time, needing about 62-64 seconds while only 35 seconds was available.

Claude had also printed a frame-conversion check before the verifier run:

```text
GMST calibration: brahe=115.2379 deg, ours=113.5936 deg
GMST offset: 1.6443 deg
ITRF check at t=0 ... Diff: 17601.56 m
ITRF check at t=24h: diff=17603.26 m
```

That gave it a causal explanation. The private model was close enough to find good opportunities, but not close enough for borderline visibility acceptance. The off-nadir failures were not random schema mistakes; they were exactly the kind of marginal geometry errors expected from an approximate frame transform. The slew errors revealed a second private-model bug: candidate scheduling needed the benchmark's bang-coast-bang slew gap, not just non-overlap.

The trace then shows a high-quality repair decision. Claude explicitly says the errors are from "slight propagation/rotation mismatches and missing slew constraints" and decides to "use brahe's propagator directly for precision, and properly enforce slew constraints." It tests Brahe performance and discovers:

- `NumericalOrbitPropagator.from_eci(...).propagate_to(...)` works for J2 propagation;
- `state_gcrf(epoch)` queries are fast after propagation;
- direct `state_itrf(epoch)` queries are too slow at every sample;
- `rotation_gcrf_to_itrf(epoch)` is fast and exactly matches `position_gcrf_to_itrf` when applied as a matrix.

This is the non-trivial step. It independently converges on the same basic primitives used by the verifier: Brahe numerical J2 propagation and Brahe GCRF/ITRF frame rotation. The public README says propagation uses `brahe.NumericalOrbitPropagator` and deterministic EOP, but it does not hand the space agent an efficient vectorized implementation. Claude had to discover the performance path: propagate in GCRF, precompute rotation matrices every 10 seconds, and apply them with NumPy.

## What Claude Built

Claude's final solver family was a generated, case-specific architecture search rather than a reproduction of the first-party solver. Its main components were:

1. Create Walker delta constellations from orbital elements, output as GCRF Cartesian initial states.
2. Use Brahe J2 propagation over the 48 h horizon.
3. Precompute `rotation_gcrf_to_itrf` matrices on the 10-second sample grid.
4. Convert target geodetic coordinates with `position_geodetic_to_ecef`.
5. Build access windows by filtering sampled visibility on elevation, target slant range, sensor range, and off-nadir angle, with a 0.5 degree safety margin.
6. Convert access windows into observation candidates.
7. Greedily insert observations per satellite while checking overlap and required slew/settle gaps from the README formula.
8. Compute boundary-inclusive per-target max revisit gaps using observation midpoints.
9. Once the primary metric hit the floor, search smaller constellations.

The first verified repaired solution used 20 satellites and 913 actions. The verifier accepted it with capped gap 6.0 and max actual gap about 4.6583 h. This was already a valid success, but not the final success.

## Objective Switching

The decisive optimization move was objective switching. Claude re-read the scoring section around the formula:

```text
target_capped_gap = max(max_revisit_gap_hours, expected_revisit_period_hours)
capped_max_revisit_gap_hours = mean(target_capped_gap over targets)
```

Because all 28 targets in case 0001 have expected revisit 6 h, a valid solution cannot score below 6.0 on the primary metric. Claude noticed that once every target's actual max gap was below 6 h, more observations and more satellites could not improve the primary metric. It then switched to the secondary objective, `num_satellites`.

That is a key part of the result. A solver that keeps optimizing raw max gap after reaching the floor can waste capacity. Claude instead treated 6.0 as a service threshold and searched for the smallest constellation that still stayed under it.

## The Pruning Search

Claude then explored a compact Walker family. The final architecture came from a Walker `12/4/1` constellation at 50 degrees inclination and 700 km altitude, with two satellites removed. The trace records this progression:

- 12-satellite Walker variants at 700-750 km and 50-65 degrees repeatedly reached max gaps just under 6 h.
- An 11-satellite removal from the 12-satellite base verified at the 6 h floor.
- Several direct 10-satellite Walker patterns failed.
- A systematic "drop 2 from 12" search found that dropping satellites `(0, 11)` preserved max gap 5.933 h.
- A "drop 3 from 12" search for 9 satellites found the best tested combination at about 6.058 h in-trace, and a later direct 9-satellite Walker search failed by wider margins.

I also ran a small analyst-side reproduction using the public case files, Brahe zero-EOP setup, the same Walker `12/4/1` family, 10-second sampling, and a simple greedy scheduler. It is not a tracked artifact and is not needed for the main claim, but it usefully sanity-checks the trace: the best two-satellite removals included `(0, 11)`, `(5, 6)`, `(7, 8)`, and `(7, 11)`, all around 5.933 h; the best three-satellite removals in that approximate rerun were just above 6 h. This supports Claude's empirical search story while preserving the caveat below.

The final verifier call in the trace reports:

```text
Valid: True
Score: 6.0
Max gap: 5.933333333333334
Satellites: 10
Violations: 0
```

The aggregate run metadata records the same values, with 639 actions and per-target gaps all below 6 h.

## Why This Is Not Just Luck

There is search luck in which Walker family and satellite removals worked, but the success is not schema luck or private-metric drift.

First, Claude used the correct solution shape from the exposed README: top-level `satellites` and `actions`, GCRF Cartesian state fields, and observation actions with `action_type`, `satellite_id`, `target_id`, `start`, and `end`.

Second, it allowed the verifier to override its private model. The first private model said the 20-satellite solution was good; the verifier rejected it. Claude did not rationalize the rejection away. It diagnosed the numerical mismatch, changed propagation and frame conversion, added a safety margin, enforced slew gaps, and re-ran the verifier.

Third, the final optimization target matched the benchmark. Reducing satellites after reaching the floor is not gaming the score. The README explicitly ranks valid solutions by capped gap first, then fewer satellites. The normalized scorer for revisit similarly rewards gap satisfaction first and satellite scarcity after the threshold is met. Claude's 10-satellite result is therefore an architecture-design improvement, not a cosmetic post-processing trick.

## The Overclaim

Claude's final statement says 9 satellites "definitively" cannot achieve 6 h revisit and that 10 satellites is "optimal." The trace does not prove that. It proves a much narrower claim: 9 satellites failed in the tested Walker removals and several direct 9-satellite Walker patterns. A non-Walker design, a different altitude/inclination family, or a more sophisticated scheduler is not ruled out by that evidence.

So the fair conclusion is:

- verifier-confirmed: 10 satellites achieve the 6 h floor on this case;
- strongly suggested by Claude's local search: 9 satellites is difficult within the explored Walker family;
- not proven: global 10-satellite optimality.

This distinction matters because it is a common trace pattern. Space agents often turn "my empirical search did not find a better design" into "no better design exists." The result remains impressive, but the optimality claim should be softened.

## Agent Adaptiveness Versus Solvers

This case is strong evidence that evaluated space agents can benefit from per-case adaptiveness. Claude acted less like a fixed algorithm and more like a solver designer in the loop. It read the case, inferred the score floor, selected a Walker family, debugged its numerical model against verifier feedback, changed implementation strategy for speed, and ran focused architecture-pruning experiments.

That is hard to encode in a reusable solver. A solver can certainly be adaptive, and the first-party J2 set-cover solver is far more systematic than Claude's generated script. But a fixed solver must anticipate its adaptation policy before seeing every case. Claude synthesized its policy during the run:

- "20 satellites proves the geometry can meet the floor."
- "The primary metric is saturated."
- "The remaining useful search is satellite-count reduction."
- "A 12-satellite Walker family is close to the threshold."
- "Prune satellites from the working Walker constellation and verify."

That live change of search objective and design family is the advantage. It also has a cost. Claude spent about 3058 seconds on one case, wrote many temporary scripts, and produced an empirical method rather than a reusable, documented solver. The first-party solver is less nimble on this exact case but has explicit profiles, debug artifacts, deterministic candidate construction, and a repeatable contract.

The right conclusion is therefore bounded: coding agents can exploit case structure very effectively when the workspace contract is precise, the verifier is available, and the instance has compact architectural degrees of freedom. This does not make them better general solvers by default. It shows that the benchmark is measuring an additional capability: on-the-fly method design under black-box verifier feedback.

## Takeaway

Claude's `case_0001` success came from verifier-aligned adaptiveness. The crucial moment was not merely using Brahe; it was recognizing that a custom J2 and simplified frame model produced near-threshold geometry errors, then discovering an efficient Brahe-compatible path with `NumericalOrbitPropagator` and `rotation_gcrf_to_itrf` without seeing verifier source. Once the primary score hit the 6 h floor, Claude correctly switched from "more coverage" to "fewer satellites" and found a 10-satellite pruned Walker constellation. The result is an excellent example of a space agent turning a precise public contract and opaque verifier into a bespoke, case-structured solver loop.
