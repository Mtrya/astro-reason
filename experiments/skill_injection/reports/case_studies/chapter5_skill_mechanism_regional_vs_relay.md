# Skill-Injection Mechanism: Regional Coverage Versus Relay Constellation

## Summary

This rewrite is grounded in the exported OpenCode + DeepSeek V4 Pro traces, not only the aggregate tables. I inspected the opencode SQLite traces, agent stdout, run metadata, verifier outputs, and final solutions for Regional Coverage and Relay Constellation across the compact-domain and skill-pack conditions under the skill-injection result root. The no-skill baseline traces are not present under `results/agent_runs/experiments/skill_injection/default/no_skill/...`; the exact expected paths are missing. The corresponding baseline runs are exported under the main-agentic matrix and match the no-skill aggregate rows, so I use those traces explicitly as the baseline rather than silently treating the aggregate report as trace evidence.

Human-written procedures helped Regional Coverage most when they changed candidate generation and verifier-backed incumbent selection. The Regional skill pack made the agent generate far larger candidate pools, score candidates by actual or proxy covered samples, and repeatedly keep the best valid file. It did not merely increase action volume: the skill-pack mean action count is lower than no-skill while weighted coverage is much higher. Relay Constellation behaved differently. Procedures reduced catastrophic zero-service outcomes, but the full skill pack often widened search into relay-placement and link-activation choices that then had to satisfy endpoint caps, satellite link caps, simultaneous visibility, and complete routed paths. The compact procedure was better on mean score because it kept the run closer to a service-first, demand-window loop.

## Trace Coverage

| Slice | Exported trace evidence inspected |
| --- | --- |
| Regional no-skill | Main-agentic baseline traces for all five OpenCode + DeepSeek V4 Pro test cases. Missing under the skill root at `results/agent_runs/experiments/skill_injection/default/no_skill/regional_coverage/opencode_dpsk/test/<case>/...`. |
| Regional compact-domain | Skill-injection traces for all five cases, including opencode DB rows, stdout, verifier stdout, run metadata, and solutions. |
| Regional skill-pack | Skill-injection traces for all five cases, including opencode DB rows, stdout, verifier stdout, run metadata, and solutions. |
| Relay no-skill | Main-agentic baseline traces for all five OpenCode + DeepSeek V4 Pro test cases. Missing under the skill root at `results/agent_runs/experiments/skill_injection/default/no_skill/relay_constellation/opencode_dpsk/test/<case>/...`. |
| Relay compact-domain | Skill-injection traces for all five cases. |
| Relay skill-pack | Skill-injection traces for all five cases. |

The aggregate reports remain useful for matched outcome numbers, but the mechanism claims below come from the trace behavior: tool calls, skill reads, generated solver scripts, verifier calls, candidate counts, incumbent updates, and final handoff behavior.

## Outcome Pattern

| Family | Condition | OpenCode + DeepSeek V4 Pro outcome | Trace-supported mechanism |
| --- | --- | --- | --- |
| Regional Coverage | No skill | 5/5 valid, mean weighted coverage 0.3965, mean score 35.79. | Self-discovered orbit geometry and repeated verifier use, but the search often spends many attempts fixing coordinate conventions before finding productive strips. |
| Regional Coverage | Compact-domain | 5/5 valid, mean weighted coverage 0.4149, mean score 40.38. | Reads the compact strip procedure and usually writes an empty valid skeleton early; improves validity discipline but can remain conservative and under-search some cases. |
| Regional Coverage | Skill-pack | 5/5 valid, mean weighted coverage 0.6438, mean score 55.25. | Reads the domain strip strategy plus search/optimization skills; generates much broader candidate pools, tries multiple selection strategies, and preserves verifier-scored incumbents. |
| Relay Constellation | No skill | 5/5 valid, mean service 0.5594, mean score 35.67; zero service on cases 3 and 5. | Builds substantial orbit/link solvers, but valid files can still contain no useful routed service because links do not compose into simultaneous endpoint-to-endpoint paths. |
| Relay Constellation | Compact-domain | 5/5 valid, mean service 0.6576, mean score 39.17. | Reads compact relay procedure, starts from valid skeletons, repeatedly analyzes demanded windows, and avoids some zero-service collapses with conservative service-first routing. |
| Relay Constellation | Skill-pack | 5/5 valid, mean service 0.6006, mean score 36.05. | Reads the service strategy, but broader augmentation/link search often creates repair work around endpoint caps, overlapping links, infeasible geometry, and unserved demand windows. |

## Workflow Comparison

| Family | No skill workflow | Compact-domain workflow | Skill-pack workflow |
| --- | --- | --- | --- |
| Regional Coverage | Reads case files and README, invokes Brahe, then builds many private solver variants. The traces show repeated coordinate-frame and roll-sign debugging, many verifier calls, and gradual improvement from zero or weak coverage to valid incumbents. | Invokes `regional-coverage-compact-procedure` before solving. In every inspected case it creates or tests a schema-valid empty solution early, then moves to strip generation. It is verifier-disciplined but often keeps a smaller productive set. | Invokes `regional-coverage-strip-strategy` plus search skills. It shifts from "make a valid strip" to broad candidate generation, exact or approximate coverage scoring, multiple sort/fill strategies, and final incumbent preservation. |
| Relay Constellation | Reads contract files, invokes Brahe, writes a valid skeleton in several cases, then builds orbit/link/path solvers. The main failure is not syntax or validity; it is failing to turn active links and added satellites into simultaneous routed service for every demand. | Invokes `relay-constellation-compact-procedure`, usually writes a valid empty skeleton, and repeatedly inspects backbone feasibility and demanded windows. It improves by rescuing zero-service cases, not by dominating every high-performing no-skill case. | Invokes `relay-constellation-service-strategy`. It broadens search over added relays, ground links, ISLs, and path allocations, but traces show substantial time spent resolving max-link, overlap, geometry, and timestamp issues; extra guidance does not guarantee better routed service. |

## Regional Coverage Trace Evidence

The Regional skill pack changed both the breadth and the shape of candidate generation. In `case_0002`, the no-skill trace invokes only the Brahe skill, writes fourteen solver variants, and makes seventeen verifier calls. It repeatedly improves from zero coverage through small candidate sets: row 71 reports 1,550 strip candidates, row 137 falls back to 88 candidates, row 190 reports 72 candidates, and later rows select 24 to 27 actions before the final 15-action valid solution. The run is active, but a lot of effort goes into recovering geometry and producing any coverage rather than systematically filling all high-value regions.

The compact trace for the same case invokes `regional-coverage-compact-procedure` at row 18, writes `{"actions": []}` at row 27, and verifies that empty file at row 28. That is the intended early valid skeleton behavior. But the trace also shows why compact guidance is not enough: rows 81 and 137 report zero raw candidates, row 184 finds only 40 raw candidates, and row 207 reaches 86 candidates. The compact run is safer, but its smaller search leaves a weak 9-action final file with weighted coverage 0.0985.

The skill-pack trace for `case_0002` invokes Brahe and `regional-coverage-strip-strategy` at rows 17-18, then shifts into a much wider search. Row 121 reports 11,688 total candidates and 9,390 unique candidates. Row 141 expands to more than 6 million raw candidates and 4.8 million unique candidates before later pruning. Rows 153 and 160 continue with 444,321 unique candidates. The final file has 58 actions and weighted coverage 0.6321. That is a real candidate-generation change, not just a larger final action count.

The same pattern appears in high-performing skill-pack cases. In `case_0004`, the skill-pack trace invokes the strip strategy and search skill, then reports 38,628 candidates at row 94, 312,936 raw candidates and 251,300 unique candidates at row 127, and 9,732 access-window candidates at row 131. The final solution reaches weighted coverage 0.8591. In `case_0005`, the skill-pack trace shows explicit incumbent improvement: row 264 starts from a baseline and adds Sahara-East candidates one by one; rows 291 and 295 continue with targeted improvements, raising the verifier-backed weighted coverage from roughly 0.60 to above 0.75 before final handoff.

The skill pack therefore broadens region coverage and changes candidate generation. It also improves incumbent preservation in the sense that the agent repeatedly keeps the best verified solution while testing alternatives. It is not simply action volume: Regional no-skill averages 54.2 actions and skill-pack averages 47.6, yet mean weighted coverage rises from 0.3965 to 0.6438. The mechanism is better candidate selection and replacement, not "more JSON."

The boundary is visible in `case_0003`. No-skill finds 880,956 candidates in an iterative solver and ends with weighted coverage 0.4890. The skill-pack trace invokes four skills, makes 42 verifier calls, and explores 16,422 candidates plus later single-candidate tests, but its final solution has only 15 actions and weighted coverage 0.2643. The skill pack can widen search and still choose a worse family when the current case geometry does not match the heuristic.

## Relay Constellation Trace Evidence

Relay failures are not primarily caused by failure to read the contract. The no-skill `case_0003` trace reads the README, network, and demands, writes a minimal solution at row 28, verifies the empty zero-service file at row 32, invokes Brahe at row 36, analyzes all eight backbone orbits at row 76, and then builds multiple link/path solvers. The trace repeatedly identifies demanded windows and visibility gaps. Yet the final run is valid with eight added satellites and service 0.0. The agent understood many ingredients, but never assembled a simultaneous source-to-destination service graph that the verifier could route.

The compact condition changes the failure mode. In Relay `case_0001`, the compact trace invokes `relay-constellation-compact-procedure`, writes valid skeletons, and makes 45 verifier calls. It analyzes orbit parameters, ground visibility, and demanded windows, then maintains valid handoff behavior. Its score is lower than the strongest no-skill construction on that case, but the compact condition is not trying to maximize satellite count; it is a service-first rescue procedure. Across cases it removes the two zero-service collapses seen in no-skill.

The skill-pack Relay traces show why the full pack is not the best Relay condition. In `case_0004`, the skill-pack trace eventually computes a partial valid service file, but the run spends many rows repairing exactly the coupled constraints that make Relay hard: overlapping ISL actions, endpoint max-link violations, infeasible ground links, and timestamp/visibility mismatches. The final verified result serves demand_002, demand_003, and demand_004 partially or strongly, but leaves demand_001, demand_005, and demand_006 at zero service; overall service is 0.3111 and worst-demand service is 0.0. Extra procedural material widened the search but did not solve demand prioritization and end-to-end path completion.

Relay `case_0005` is the positive side of the skill pack. No-skill ends with zero service despite ten added satellites. Skill-pack ends with service 0.7913 and worst-demand service 0.6750, also with ten added satellites. That trace shows the service strategy can help when the broader search lands on compatible relays and links. But this is not monotone: on cases 1, 2, and 4, no-skill or compact-domain beats the full skill pack. The dominant lesson is not that the skill pack is bad; it is that Relay needs the right coupling of demand-window prioritization, relay placement, link activation timing, and path routing. More guidance can increase the search space the agent must coordinate.

## Why Compact Beats The Full Skill Pack On Relay

Compact-domain helps Relay more than the full skill pack on the mean because it constrains the workflow around demanded windows and valid service incumbents. The full skill pack pushes the agent toward broader network design and service strategy, but the traces show repeated failures at the composition layer: links are individually plausible but overlap illegally, violate endpoint capacity, miss simultaneous visibility, or fail to connect both endpoints inside the same demanded window. Compact guidance more often keeps the agent checking actual per-demand service and preserving a valid partial-service file.

This is not evidence that Relay is simply "harder." It is evidence that the injected procedure covers different fractions of the work. Regional Coverage has a local marginal loop: add one strip, verify it, measure fresh covered samples, keep or reject it. Relay has a conjunctive loop: added satellites, ground links, ISLs, time intervals, degree limits, endpoint visibility, and shortest-path allocation must all align. The same style of static procedure maps cleanly to Regional's local action space but only partially to Relay's time-varying graph construction.

## Paper-Ready Explanation

Human-written procedures help most when they turn solution construction into a local verifier-guided search. In Regional Coverage, the skill pack changed the agent's workflow from recovering geometry to generating and preserving broad marginal-coverage candidates, so mean quality rose without simply increasing action count. In Relay Constellation, procedural guidance rescued zero-service cases, but the main bottleneck remained coupled routed service: relay placement, link timing, endpoint caps, and simultaneous paths had to work together, so the compact service-first procedure was more reliable than the broader skill pack.

## Provenance

Primary trace roots inspected:

- `results/agent_runs/experiments/skill_injection/default/compact_domain/regional_coverage/opencode_dpsk/test/*`
- `results/agent_runs/experiments/skill_injection/default/skill_pack/regional_coverage/opencode_dpsk/test/*`
- `results/agent_runs/experiments/skill_injection/default/compact_domain/relay_constellation/opencode_dpsk/test/*`
- `results/agent_runs/experiments/skill_injection/default/skill_pack/relay_constellation/opencode_dpsk/test/*`
- `results/agent_runs/experiments/main_agentic/matrix/regional_coverage/opencode_dpsk/test/*`
- `results/agent_runs/experiments/main_agentic/matrix/relay_constellation/opencode_dpsk/test/*`

Missing expected baseline roots:

- `results/agent_runs/experiments/skill_injection/default/no_skill/regional_coverage/opencode_dpsk/test/*`
- `results/agent_runs/experiments/skill_injection/default/no_skill/relay_constellation/opencode_dpsk/test/*`

Aggregate reports used only for matched outcome numbers:

- `experiments/skill_injection/reports/regional_coverage.md`
- `experiments/skill_injection/reports/relay_constellation.md`
