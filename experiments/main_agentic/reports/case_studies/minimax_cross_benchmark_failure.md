# Minimax Cross-Benchmark Case Study: Verifier Contact Without Verifier Discipline

This note diagnoses `opencode_minimax` across the tracked `main_agentic` benchmark reports. The broad pattern is not a single bug. Minimax alternates between three failure modes: it sometimes misses the root README and invents a schema, it often reads the README and runs the verifier but too late to restructure the solver, and it sometimes deliberately settles for verifier-valid outputs with zero or near-zero objective value. The root cause is therefore sharper than "bad astrodynamics" but different from the earlier Claude regional case: Minimax often contacts the verifier, but it does not consistently let the verifier and README govern the whole workflow.

## Evidence Base

This case study is anchored to tracked repository artifacts rather than ignored `results/*` directories. Aggregate outcomes come from `experiments/main_agentic/reports/aeossp_standard.md`, `experiments/main_agentic/reports/regional_coverage.md`, `experiments/main_agentic/reports/relay_constellation.md`, `experiments/main_agentic/reports/revisit_constellation.md`, `experiments/main_agentic/reports/satnet.md`, `experiments/main_agentic/reports/spot5.md`, and `experiments/main_agentic/reports/stereo_imaging.md`. Behavioral evidence comes from the tracked trace exports under `experiments/main_agentic/reports/traces/data/events/*__opencode_minimax__*.js`. Contract evidence comes from the benchmark README fragments under `experiments/_fragments/prompts/` and verifier implementations under `benchmarks/*/verifier*`.

There is an important asymmetry in this evidence base. The evaluated agents did not see the verifier source code; in the workspace they saw an opaque verifier binary plus a README. The README is often detailed enough to describe the contract nearly at code-level precision, but it is still normal and necessary for an agent to write its own propagation, geometry, scheduling, and scoring approximations in order to search. In this report, verifier source is used only as retrospective analyst evidence to explain why the opaque verifier behaved as it did. The red flag is not "the agent wrote a private model." The red flag is "the agent treated the private model as an authoritative verifier, or kept trusting it after the packaged verifier contradicted it."

## Aggregate Outcome

The aggregate rows already show that Minimax is not uniformly broken, but it is weak exactly where contract fidelity and verifier-guided repair matter most:

| Benchmark | Minimax aggregate | Immediate reading |
| --- | --- | --- |
| `revisit_constellation` | 0/5 valid, normalized mean 0.0000 | Hard failure across every case. |
| `relay_constellation` | 4/5 valid, service_fraction 0.0000 | Mostly valid submissions, but no served demand. |
| `stereo_imaging` | 1/5 valid, normalized_quality 0.0000 | Mostly invalid; the valid case has no stereo product quality. |
| `regional_coverage` | 5/5 valid, weighted_coverage_ratio 0.0440 | Valid schedules, often empty or geometrically ineffective. |
| `aeossp_standard` | 5/5 valid, WCR 0.2008 | Valid but far below other harnesses; one zero case. |
| `spot5` | 4/5 valid, computed_profit 56820.5 | Mixed; simple cases work, one schema miss invalidates a high-profit attempt. |
| `satnet` | 1 tracked valid run, normalized mean 55.81 | A partial success, but only one aggregate case is present in the report. |

The cross-benchmark symptom is therefore not just invalid JSON or timeouts. Minimax frequently produces a syntactically valid or even verifier-valid file, but the file is semantically empty with respect to the benchmark objective.

## Authority Acquisition

A quick trace sweep over the 35 tracked Minimax traces found 23 traces where Minimax read `/app/workspace/README.md`, 23 where it ran the packaged verifier on some solution or test file, and 14 where it checked verifier help. This is materially better than the Claude regional failure mode, where the two failing traces never found the root README or verifier. But the per-benchmark distribution is uneven:

| Benchmark | Traces | README read | Verifier run |
| --- | ---: | ---: | ---: |
| `aeossp_standard` | 5 | 4 | 4 |
| `regional_coverage` | 5 | 4 | 4 |
| `relay_constellation` | 5 | 5 | 5 |
| `revisit_constellation` | 5 | 1 | 1 |
| `satnet` | 5 | 3 | 3 |
| `spot5` | 5 | 4 | 4 |
| `stereo_imaging` | 5 | 2 | 2 |

This table explains why the failure looks inconsistent. In relay, Minimax knows the contract and the verifier, but cannot build useful link plans. In revisit and several stereo cases, it often skips the local authority altogether and invents a solution shape or physics loop. In regional and AEOSSP, it often recovers schema authority but still lets a weak approximate simulator decide too much about validity.

## Mode 1: Schema Authority Failure

The clearest schema failures happen when Minimax starts directly from `case/` files or from its own domain intuition instead of the root README. In `spot5 / opencode_minimax / 1403`, the trace writes a solution with a top-level `"targets"` list after internally verifying target conflicts. The tracked SPOT-5 README fragment requires `claimed_profit`, `claimed_weight`, `n_candidates`, `n_selected`, and an `assignments` vector; `benchmarks/spot5/verifier.py` parses JSON through `payload["assignments"]`. The aggregate report marks `1403` invalid even though the trace claims a high-profit valid selection.

The same pattern appears in `revisit_constellation / opencode_minimax / case_0001`. The trace never reads the root README or runs the verifier, then validates a file by checking `len(sol['observations'])`. The tracked revisit README requires top-level `satellites` and `actions`, with observation rows using `action_type`, `satellite_id`, `target_id`, `start`, and `end`; `benchmarks/revisit_constellation/verifier/io.py` requires `solution.json.satellites` and `solution.json.actions`. The model solved a plausible constellation-planning problem, but not the submitted interface.

Regional coverage has a related but partially recoverable version. In `regional_coverage / opencode_minimax / case_0001`, the trace writes 64 actions with `satellite_id`, `start_time`, `end_time`, and `look_direction`. The tracked regional README says the verifier only interprets `type`, `satellite_id`, `start_time`, `duration_s`, and `roll_deg`, with `type = "strip_observation"`. The aggregate report consequently shows `valid=true`, `num_actions=0`, and zero coverage. In later regional cases Minimax reads the README and uses `type: "strip_observation"`, but the early schema miss shows the same root weakness: it does not always establish the contract before building the solver.

## Mode 2: Verifier Used Late As A Debugger

Several traces show Minimax running the real verifier only after it has already committed to a large custom solver model. A custom model is not itself suspicious; the opaque verifier cannot be used as a fast inner-loop oracle for every candidate. The failure pattern is that verifier feedback arrives after the model's representation, objective, or geometry assumptions have hardened, so the verifier becomes a late debugger rather than the final arbiter of the workflow. In `aeossp_standard / opencode_minimax / case_0002`, the trace eventually reaches a valid `actions` schema and repeatedly runs `./verifier case/ solution.json`, but the final metrics are only `CR=0.00949`, `WCR=0.00845`, and 17 completed tasks out of 1791. The final explanation blames strict geometry constraints, even though other harnesses reach WCR around 0.71 on the same benchmark family. The verifier is used to prune invalid actions, not to force a better modeling strategy.

`regional_coverage / opencode_minimax / case_0004` is even more revealing. The trace first runs the verifier and sees `num_actions: 0`, then reads the README at sequence 309 and repairs the schema. After that, it keeps generating 64 or 49 parsed `strip_observation` actions, but official verifier output remains zero weighted coverage. The debug prints show it comparing its own predicted coverage against verifier-derived `centerline_lonlat` and covered weights. This is the verifier doing exactly what it should do, but too late: Minimax is trying to patch a proxy geometry model after that model has become the acceptance criterion.

`stereo_imaging / opencode_minimax / case_0001` follows the same pattern. The trace reads the README and verifier help early, then repeatedly runs `./verifier`. It can remove hard violations, but the final aggregate score is still valid with `normalized_quality=0.0000`. The README says the submitted object must be raw observation `actions`, and stereo products are derived by validation; the verifier uses `load_solution_actions` and then derives products from same-target observations. Minimax can satisfy action validity but fails to produce observations that form useful stereo products.

## Mode 3: Valid Empty Or Valid Zero Objective

Relay is the most important counterexample to a simple "schema miss" theory. All five relay traces read the README and run the verifier. The tracked relay README is explicit: submit `added_satellites` and physical link `actions`; do not submit routes, service claims, or latency calculations, because routing is derived during validation. Minimax gets enough contract authority to produce parseable solutions, but the aggregate service_fraction is 0.0000 in every case.

In `relay_constellation / opencode_minimax / case_0001`, the trace explicitly creates a no-action baseline and observes that the verifier reports `valid: true` with `service_fraction: 0.0`. It then writes "Valid solution: 6 LEO satellites at 1200 km altitude, 30 deg inclination Service fraction = 0.0 but solution is VALID" and final-verifies that file. This is a strategic surrender, not a hidden schema bug. The benchmark allows valid-but-unserved schedules so that feasibility and objective quality remain separate; Minimax accepts feasibility as enough.

This explains why aggregate validity can be misleading. For relay and some regional/stereo cases, `valid=true` means "the file obeys hard constraints," not "the mission objective was solved." Minimax often treats the first meaning as sufficient.

## Mode 4: Private Models Become Private Verifiers

Across revisit, regional, relay, AEOSSP, and stereo, Minimax repeatedly writes bespoke geometry code: Walker constellation generation, simplified access windows, elevation filters, off-nadir heuristics, ground-track sweeps, and task-specific validators. That is expected. The agents only have an opaque verifier and a README, so a useful solver almost has to approximate the hidden validation logic while searching. The problem is narrower: Minimax often lets the approximation become a private verifier. It uses the packaged verifier as an occasional endpoint check, but when the two disagree it does not consistently demote the private model and reorganize around the authoritative result.

In revisit, this becomes fatal. `revisit_constellation / opencode_minimax / case_0004` eventually reads the README and runs the verifier, which reports infeasible observations such as off-nadir angles above 30 degrees. Minimax then writes that Brahe access computation "doesn't fully account for off-nadir and range constraints" and finalizes anyway because the structure is correct. The official report marks the case invalid. The model understands that its simulator and the verifier disagree, but it treats that disagreement as a limitation of its proxy rather than as a command to make the submitted file pass the local verifier.

In stereo, the simulator can be wrong even when it produces impressive local claims. `stereo_imaging / opencode_minimax / case_0002` never reads the README or verifier and writes a solution containing 54 claimed stereo pairs covering 38 targets. The tracked stereo README says the solution should schedule raw observation actions, not explicit pairs, and `benchmarks/stereo_imaging/verifier/io.py` requires an `actions` array with each row having `type: "observation"`. The trace's "All pairs valid!" statement is the problematic move: private validation over a non-contract object replaces the opaque local verifier.

## Mode 5: Skill Avoidance And Equation Drift

`aeossp_standard / opencode_minimax / case_0001` is a useful trace because it is not a total failure: the aggregate report gives it `valid=true` and WCR 0.5241. But the trace still exposes a lower-level workflow weakness. At sequence 33, Minimax says the problem "requires orbital mechanics calculations" and says it will check whether the Brahe skill can help, then immediately pivots: "But actually, let me think about this more carefully" and writes a Skyfield/SGP4 solver instead. Unlike the neighboring AEOSSP traces, this trace contains no Brahe skill load event.

The early hand-built geometry is not just a library substitution; it contains basic equation drift. One generated visibility function tries to subtract a latitude-like object from a target point and compare a distance-like quantity to `max_off_nadir`:

```python
def is_visible(sat_pos, target_lat, target_lon, target_alt, max_off_nadir):
    sublon, sublat = wgs84.subpoint(sat_pos)
    target_point = wgs84.latlon(target_lat, target_lon, target_alt)
    diff = target_point - sublat
    dist = math.sqrt(diff[0]**2 + diff[1]**2 + diff[2]**2)
    return dist <= max_off_nadir
```

A later off-nadir helper starts to assemble ECEF vectors, then returns `0.0`. The slew helper converts `theta_deg` to radians but leaves `omega` and `alpha` in degrees-per-second units, so the branch condition and duration formula mix angular units. These are not subtle high-fidelity disagreements with WGS84 or EOP handling; they are signs that the model did not have even a stable simplified astrodynamics kernel in mind.

The trace eventually recovers by treating the real verifier as a filter: the Skyfield solver produces 1935 actions, 1834 action failures, and only 101 completed tasks; a later SGP4 version produces 1424 actions and 325 action failures; Minimax filters the failed action indices out and obtains a valid 1099-action solution with WCR 0.5241. That final score should therefore be read as verifier-rescued, not as evidence that the original astrodynamics model was sound.

## Focused Check: Relay And Revisit Astrodynamics

The two suspected astrodynamics-heavy traces sharpen the distinction between skill use, solver modeling, and verifier discipline. `relay_constellation / opencode_minimax / case_0001` is not a "did not read the skill" failure. The trace loads the Brahe skill at sequence 20, reads `/app/workspace/README.md` at sequence 29, and runs `/app/workspace/verifier case/ /app/workspace/solution.json` repeatedly. It is also not a failure merely because Minimax wrote geometry helpers; with an opaque verifier, that is normal. The problem is that Minimax starts using those helpers to second-guess the verifier. Its private helper converts ground stations to ECEF, then calls `compute_elevation` with satellite coordinates taken directly from `network.json` or from its own simple propagation. At sequence 330 it explicitly checks sample 3160 by using each backbone satellite's initial `x_m`, `y_m`, and `z_m`; at sequence 382 it says it is using the "INITIAL backbone_002 position" because that might be what the validator is doing. That is a different physical contract from the README's frame/timing description and from the opaque verifier's observed behavior. Retrospectively, the tracked verifier source confirms the mismatch: the relay verifier propagates from ECI/GCRF using Brahe with a J2 force model, transforms each sampled position with `position_eci_to_ecef`, and only then computes ground-link elevation through `relative_position_ecef_to_enz` and `position_enz_to_azel`. So the hand-written elevation equation is concerning not because it exists, but because it becomes an alternate verifier that mixes frames and sometimes skips time propagation. This explains the trace's later confusion: it sees its computed elevations disagree with verifier failures, cannot reconcile them, and retreats to the verifier-valid zero-service baseline.

The revisit trace is different. `revisit_constellation / opencode_minimax / case_0004` does use Brahe APIs extensively: it inspects `WalkerConstellationGenerator`, `location_accesses`, `AccessWindow`, and eventually reads the README and runs the local verifier. Its core error is treating Brahe's `location_accesses(..., ElevationConstraint(...))` as if it were equivalent to the benchmark's full observation feasibility test. As a search heuristic, elevation-only access is reasonable; as a substitute verifier, it is not. Retrospectively, the verifier source shows why the opaque verifier rejected the solution: it constructs `NumericalOrbitPropagator.from_eci` with a J2 force model, samples every action, checks ECEF elevation, target max slant range, sensor max range, and off-nadir angle in ECI, then separately checks slew and battery. Minimax's generated code builds windows from an elevation-only access search, adds a coarse 60-second gap as a proxy for slew, and does not include an equivalent off-nadir or sensor-range filter before writing actions. The local verifier then reports observations with off-nadir angles around 40-50 degrees against a 30 degree limit. The revealing part is the response: Minimax says Brahe access computation "doesn't fully account for off-nadir and range constraints" and finalizes anyway because the structure is correct. That is not a failure to know simplified orbital equations; it is a failure to let the local verifier redefine what counts as a valid observation once the proxy model is contradicted.

`revisit_constellation / opencode_minimax / case_0005` is a useful adjacent counterexample. It loads the Brahe skill very early and searches the Brahe API, but the trace does not read the root README or run the verifier. It writes a private result shape with `constellation`, `schedule`, `targets_covered`, and `max_revisit_gap_hours`, while the verifier expects `satellites` and `actions`. It also shows unit uncertainty around `state_ecef`, wondering whether the state is in meters or kilometers. So case 0005 supports the "authority discipline" diagnosis more than a pure "equations from scratch" diagnosis: even with the right library in view, Minimax can still solve the wrong interface and trust a private metric as if it were the benchmark metric.

## Comparison To Better Minimax Cases

The better Minimax cases support the same diagnosis. On SPOT-5 case `8`, it reads the README, discovers the verifier, runs it on an empty solution, then verifies the final assignment vector as `VALID: profit=10, weight=0`. On SatNet `W10_2018`, it reads the README and runs the verifier, ending with a valid but weaker schedule than Codex. These successes are mostly in benchmarks where the solution interface is simple enough that local parsing and verifier feedback line up quickly.

AEOSSP also shows partial competence. `case_0001` reaches WCR 0.5241 after reading the README and running the verifier, which is not a lucky schema guess. But the remaining AEOSSP cases are much weaker, and `case_0005` reads neither README nor verifier and ends at zero. The pattern is conditional: when Minimax binds early to README plus verifier, it can produce something real; when it does not, or when the verifier requires a major redesign, it degrades sharply.

## Root Cause

The root-root-cause is weak authority discipline under scientific-optimization pressure. Minimax tends to enter "build a simulator and solve" mode early, which is a reasonable response to an opaque verifier. The failure appears when that simulator becomes a source of truth instead of a candidate generator. If Minimax has not read the README, the simulator invents the output schema and benchmark objective. If it has read the README, the simulator may still invent enough physics or pairing logic that passing the verifier becomes an after-the-fact cleanup step. When cleanup is easy, the run succeeds. When cleanup requires changing the representation, schedule construction, or geometry model, Minimax either settles for valid zero output or finalizes an invalid file with a private justification.

This is why other candidate explanations are secondary. The model is not merely bad at coordinate transformations; some failures happen before geometry is parsed at all. It is not merely bad at schema; relay uses the right schema but scores zero. It is not merely failing to use the verifier; many traces do run it. The unifying issue is that Minimax does not consistently keep the local README and verifier as the controlling authority throughout the run.

## Practical Implications

For interpreting benchmark results, Minimax's poor performance should be read as a workflow failure more than a raw reasoning failure. The traces show many moments where the correct information was available, and sometimes even observed, but was not allowed to reorganize the solution process.

For harness design, the most targeted mitigation would be to force a pre-solve authority handshake: list `/app/workspace`, read `/app/workspace/README.md`, run `/app/workspace/verifier --help`, write a minimal schema-correct `solution.json`, and run the verifier before trusting any large solver output as valid. This would not ban private solvers or approximations; it would keep them in the right role. They can propose candidates and guide search, while the packaged verifier remains the acceptance test. This would not solve relay routing or stereo geometry by itself, but it would eliminate the silent schema-invention class and would surface objective-zero baselines earlier.

For report diagnostics, aggregate tables should keep exposing validity and objective metrics separately, and where possible include diagnostic counters like `num_actions`, `validated_actions`, `valid_products`, or `completed_tasks`. Minimax's traces show why: a valid file with `service_fraction=0.0`, `num_actions=0`, or `normalized_quality=0.0` is a very different failure from an invalid parser crash, and the right fix depends on that distinction.
