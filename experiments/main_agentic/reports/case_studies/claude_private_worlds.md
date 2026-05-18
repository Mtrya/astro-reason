# Claude Case Study: Private Worlds And Authority Discovery

Date: 2026-05-19

This report investigates a recurring Claude pattern in `main_agentic` traces: Claude can inspect enough files to build a plausible private problem, then let that private problem become the authority. When the root workspace contract and packaged verifier are not acquired early enough, the space agent builds a self-consistent world, validates inside it, and exits with confident claims that the benchmark verifier later rejects or treats as empty.

The headline is not that Claude fails to use tools. It uses tools heavily. The sharper pattern is **premature authority closure**: Claude closes the task contract before it has found the contract authority.

Here, **authority** means the root workspace contract and checker:

- `/app/workspace/README.md`
- `/app/workspace/verifier`

The central examples are `stereo_imaging / claude_code / test / case_0002` and `case_0005`, but the pattern also appears in all five Regional Coverage Claude runs, four of five Relay Constellation Claude runs, `aeossp_standard` case 0005, and SPOT-5/SatNet edge cases. The counterexamples are equally important: Claude can recover when it performs an authority sweep over `/app/workspace`, reads `README.md`, and lets `/app/workspace/verifier` override its private model.

This report keeps the Claude focus, but it now also compares nearby non-Claude traces. The comparison matters because private solver models are not inherently bad. Every successful space agent needs some private propagation, geometry, search, or scheduling model. The failure studied here is narrower: the private model becomes the task authority.

## Evidence Base

Aggregate outcomes come from:

- `experiments/main_agentic/reports/aeossp_standard.md`
- `experiments/main_agentic/reports/regional_coverage.md`
- `experiments/main_agentic/reports/relay_constellation.md`
- `experiments/main_agentic/reports/revisit_constellation.md`
- `experiments/main_agentic/reports/satnet.md`
- `experiments/main_agentic/reports/spot5.md`
- `experiments/main_agentic/reports/stereo_imaging.md`

The intended workspace contracts are the prompt fragments under `experiments/_fragments/prompts/*/README.default.md`. The behavioral evidence comes from local trace artifacts under `results/agent_runs/experiments/main_agentic/matrix/.../claude_code/...` and the tracked trace-viewer exports under `experiments/main_agentic/reports/traces/data/events/`.

Because `results/*` paths are local run outputs, treat them as diagnostic evidence. The stable report-level claims are anchored to the tracked reports, prompt fragments, benchmark contracts, and trace-viewer exports.

Cross-model comparison uses the companion case studies:

- `experiments/main_agentic/reports/case_studies/minimax_cross_benchmark_failure.md`
- `experiments/main_agentic/reports/case_studies/stereo_imaging_opencode_dpsk_authority_drift.md`
- `experiments/main_agentic/reports/case_studies/stereo_imaging_kimi_cross_track_overlap.md`
- `experiments/main_agentic/reports/case_studies/relay_constellation_codex_success.md`

Those reports are not imported as unquestioned conclusions. They are useful because they anchor the same authority-discipline question in other harnesses: did the space agent read the root contract, run the packaged verifier, and demote its private model when the verifier disagreed?

## What "Second Sweep" Means Here

In this report, **second sweep** means late authority discovery: Claude realizes that `/app/workspace/README.md` or `/app/workspace/verifier` exists only after it has already started solving.

It does **not** mean a post-verifier improvement pass. Claude is often good at improving once it is anchored to the real verifier. The problem studied here is earlier and sharper: when authority discovery never happens, Claude iterates on a false verifier, inferred schema, or implicit private scorer.

## Authority Buckets

I grouped all 35 `main_agentic / claude_code` test runs into three buckets.

| Bucket | Definition |
| --- | --- |
| Early authority discovery | Claude reads the root README or invokes the packaged verifier before making a durable solver/output commitment. |
| Late authority discovery | Claude first begins committing to a solver/output, then later discovers and uses the root README or packaged verifier. |
| No authority discovery | Claude never reads the root README and never invokes the packaged verifier. |

The durable-commitment threshold intentionally ignores harmless preliminary inspection such as listing `case/`, reading case files, checking package versions, or probing library APIs. It starts when Claude writes or announces a solver/output/validator, launches a solver-building task, or otherwise begins turning its inferred model into durable artifacts.

This matters because almost every run begins by inspecting `case/`. A case-first read is not automatically a failure. It becomes dangerous only when it authorizes Claude to stop looking for the actual contract.

## Result Matrix

| Benchmark | Early | Late | No authority |
| --- | ---: | ---: | ---: |
| AEOSSP Standard | 4 | 0 | 1 |
| Regional Coverage | 0 | 0 | 5 |
| Relay Constellation | 0 | 1 | 4 |
| Revisit Constellation | 5 | 0 | 0 |
| SatNet | 3 | 1 | 1 |
| SPOT-5 | 2 | 1 | 2 |
| Stereo Imaging | 3 | 0 | 2 |
| **Total** | **17** | **3** | **15** |

The outcome split is sharp:

| Bucket | Runs | Official outcome |
| --- | ---: | --- |
| Early authority discovery | 17 | all official `success`, all valid |
| Late authority discovery | 3 | all official `success`, all valid |
| No authority discovery | 15 | 4 invalid, 5 verifier errors, 6 valid-but-zero-value |

The late bucket is small, but it is important: late discovery usually rescues the run. The no-authority bucket is the real failure bucket.

## Main Pattern

Claude authority discovery is not near-random. It clusters by benchmark and strongly predicts outcome.

Evidence against pure randomness:

- Revisit Constellation is 5/5 early authority.
- Regional Coverage is 5/5 no authority.
- Relay Constellation is 4/5 no authority, with the only recovery tied to late root discovery.
- All 20 early/late authority runs are valid official successes.
- All serious schema-crash or zero-value schema failures are in the no-authority bucket.

Evidence for a stochastic layer:

- Stereo Imaging has both early-authority successes and no-authority schema failures under the same benchmark family.
- SPOT-5 alternates between correct schema discovery and selected-ID dictionary outputs.
- Several runs begin similarly with `ls /app/workspace/case/`, but diverge depending on whether Claude later asks "what is the solution format?" or declares the case files sufficient.

The best-supported rule is:

> Claude looks for authority when it remains uncertain. Claude invents authority when `case/` feels complete.

## The Case-First Trap

Yes, Claude did `ls`.

In all five `stereo_imaging / claude_code` cases, its first filesystem action was to inspect `case/`, usually exactly:

```text
ls /app/workspace/case/
```

That first `ls` is the trap. It confirms `mission.yaml`, `satellites.yaml`, and `targets.yaml`, which are rich enough to invite a full orbital simulation. In the bad runs, Claude then treats those case files as the whole benchmark interface. It does not read the root `README.md`, does not run `/app/workspace/verifier`, and does not discover the required `actions` schema before writing `solution.json`.

So the answer is not "Claude did not look." It looked into the wrong box, found enough structure to feel oriented, and stopped looking for authority.

## Stereo Imaging: The Cleanest Private World

The aggregate `stereo_imaging` report shows Claude as unstable:

| Case | Authority bucket | Official status | Final top-level keys | What happened |
| --- | --- | --- | --- | --- |
| `case_0001` | early | valid, very low score | `actions` | Acquired contract, but ended after provider limit with only small valid coverage. |
| `case_0002` | no authority | `verifier_error` | `observations`, `stereo_pairs` | Invented product-level schema; official verifier required `actions`. |
| `case_0003` | early | valid, high score | `actions` | Strong control: root contract and verifier were used. |
| `case_0004` | early | valid, very low score | `actions` | Contract acquired, but search/model quality weak and run timed out improving. |
| `case_0005` | no authority | `verifier_error` | `stereo_observations` | Invented target-level stereo schema; official verifier required `actions`. |

The two failures are the exact private-world signature: Claude reads only the case YAML files, infers that the task is to output stereo products, and never reads the README that says the solution must contain raw observation `actions`.

### Case 0005

`case_0005` is not truncated. The run metadata says `agent_status: success`, `agent_exit_code: 0`, duration about 2080 seconds, and empty stderr. The final Claude message has `stop_reason: "end_turn"` and says:

```text
The solution is finalized.
```

The official harness then fails verification:

```text
ValueError: Solution must contain an 'actions' array
```

The written file begins with:

```json
{
  "stereo_observations": [
```

That schema is a complete invented interface. It describes per-target grouped products with embedded observations. The benchmark contract is the opposite: submit raw observation actions only; the verifier derives stereo pairs and tri-stereo products later.

The failure is especially sharp because the correct README says this explicitly:

```text
This problem is modeled as scheduling raw optical observations, not explicitly choosing image pairs.
```

Claude did not disagree with the README. It did not read it.

### The Private Verifier Loop

After it chooses the wrong representation, Claude reinforces it. In `case_0005`, it writes `/app/workspace/verify.py`, loads `solution.json`, reads `sol["stereo_observations"]`, and reports:

```text
=== VERIFICATION RESULTS ===
Total entries: 141
Valid stereo pairs: 98
Issues found: 0
Normalized quality (over all targets): 0.7371
```

The final answer then repeats the private verifier's story: 98 of 141 targets covered, all 98 with tri-stereo, zero validation issues, average quality 1.06. None of those claims pass through the benchmark verifier. They are internally coherent facts about Claude's invented schema and invented scoring model.

This is the characteristic failure: Claude does not merely hallucinate a field name at the end. It builds a world where that field name is real. Solvers emit it, validators assert it, summaries celebrate it, and the final answer closes the round inside it.

The private verifier can be explicit, as in `stereo_imaging` case 0005, or implicit, as in relay and regional runs where the solver's own feasibility checks, generated summaries, and final confidence take the role that the packaged verifier should have played. The key test is not whether a file is literally named `verify.py`; it is whether Claude's final acceptance criterion is external authority or an internally invented one.

## Late Recovery: When The Second Sweep Works

Late authority discovery is the most important control. It shows that Claude can begin in a private direction and still recover if root authority interrupts before final hardening.

### Relay Constellation Case 0004

Relay `case_0004` initially looks like a private-world run. Claude reads case files, explores Brahe APIs, and announces:

```text
Now I have a good understanding of the tooling. Let me write the complete solver.
```

Then, before writing the durable solver, it lists the workspace root:

```text
AGENTS.md
README.md
case
verifier
```

It reads `/app/workspace/README.md`, checks the verifier file, and corrects its representation to the required `added_satellites` plus `actions` schema. The official run succeeds.

This is what "second sweep" means here: not "now optimize more," but "stop and rediscover the workspace authority after already doing some work."

### SatNet W20 and SPOT-5 1021

SatNet `W20_2018` initially parses `problem.json`, sees complex resource combinations and multi-antenna tracks, and then searches for solution-format documentation. That search reveals `README.md` and the verifier. The run succeeds.

SPOT-5 `1021` reads the large `.spot` file and infers a known satellite photography format, but the file structure remains odd enough that Claude checks README/instruction files. It finds the root README and verifier, then writes the correct bookkeeping schema.

These recoveries support the main hypothesis: Claude discovers authority when it remains uncertain.

## Cross-Benchmark Pattern

### Revisit Constellation: Stable Positive Control

All five Revisit Constellation Claude runs bind to authority early and all five succeed. Claude reads the root contract before committing to a durable solver/output. This makes Revisit the cleanest positive control: Claude can build substantial mission-design machinery when the authority hierarchy is established first.

### Regional Coverage: Stable Private-World Failure

All five Regional Coverage Claude runs are no-authority runs. Claude never reads the root README and never invokes the packaged verifier. It treats `manifest.json`, `satellites.yaml`, `regions.geojson`, and `coverage_grid.json` as sufficient.

The outputs look plausible, and several contain an `actions` field, but the official verifier parses zero strip observations:

```text
valid: true
weighted_coverage_ratio: 0.0
coverage_ratio: 0.0
num_actions: 0
```

This is an especially revealing failure because it is not always a JSON-shape crash. The official verifier can accept the file as valid while treating it as benchmark-empty.

### Relay Constellation: Natural-Domain Schema Trap

Four of five Relay Constellation Claude runs never bind to authority. They submit natural domain artifacts such as:

```text
added_satellites, schedule
added_satellites, link_plan
```

The successful relay case, `case_0004`, is the late-authority recovery described above. Relay therefore repeats the same contrast: when Claude invents a natural domain artifact, it fails; when it binds to the benchmark action contract, it can succeed.

### AEOSSP, SatNet, And SPOT-5

AEOSSP has four early-authority successes and one no-authority valid-zero run. The bad case writes `observations` instead of `actions`, and the official metrics are `CR=0`, `WCR=0`.

SatNet has three early, one late, and one no-authority run. The no-authority run, `W30_2018`, ends in `verifier_error`. The late case, `W20_2018`, is recovered by explicit solution-format discovery.

SPOT-5 is mixed. The no-authority failures submit dictionaries keyed by selected candidate IDs rather than the required bookkeeping object with `claimed_profit`, `claimed_weight`, `n_candidates`, `n_selected`, and `assignments`.

## Failure Modes In No-Authority Runs

No-authority runs produce three kinds of failure:

1. **Verifier error**: the schema is so wrong the official verifier cannot parse it, as in `stereo_observations` or SPOT selected-ID dictionaries.
2. **Verifier invalid**: the object has recognizable pieces but not the required action contract, as in relay `schedule` / `link_plan`.
3. **Valid but zero-value**: the official verifier treats the file as empty or non-contributing, as in Regional Coverage and AEOSSP `case_0005`.

The third category is the easiest to miss in aggregate reports because it can look like a valid but weak run. Trace inspection shows it is often a contract failure, not an optimization failure.

## Cross-Model Comparison

The private-world behavior is **not Claude-only** if the phrase means "a space agent builds a private model and sometimes lets it outrank the verifier." That broader failure appears in Minimax, DPSK, and Kimi traces too. But the clean Claude pattern is narrower and more severe: Claude often never reaches the authority contradiction at all. It builds the wrong interface, validates the wrong interface, and exits normally inside that alternate benchmark.

The useful comparison is:

| Harness | Typical authority pattern | Private-world flavor | Contrast with Claude |
| --- | --- | --- | --- |
| `claude_code` | Often `case/` first; authority discovery is early, late, or absent depending on benchmark. | Premature authority closure: inferred schema and private validation become the whole task. | Cleanest sealed-world pattern. Bad runs often have no README/verifier contact before finalizing. |
| `opencode_minimax` | Frequently reads README and runs verifier, but unevenly and often too late. | Verifier contact without verifier discipline: private simulator survives contradiction, or valid-zero output is accepted as enough. | Less sealed than Claude; the official verifier is often visible, but it does not reliably reorganize the solver. |
| `opencode_dpsk` | Usually acquires the README/verifier in stereo traces. | Verifier-authority drift during optimization: private access/footprint model guides decisions after official feedback. | More grounded than Claude on schema, but brittle under geometry and hard-validity pressure. |
| `kimi_cli` | Usually reads README/verifier in the stereo traces. | Frame-binding failure: private coordinate convention remains misaligned with verifier signs. | Not a full invented benchmark; it knows the contract but binds one crucial physical interface incorrectly. |
| `codex` | In the relay positive control, reads README early, writes a minimal valid baseline, and repeatedly uses verifier metrics. | Private scripts are search heuristics, not authority. | The clean counterexample: private model exists, but stays subordinate to README/verifier. |

This makes "private world" a graded phenomenon rather than a binary label.

### Minimax: Contact Without Discipline

Minimax is the closest non-Claude analogue, but its failure is less sealed. The companion Minimax report found 23 of 35 tracked Minimax traces reading `/app/workspace/README.md` and 23 running the packaged verifier. That is materially different from Claude's no-authority regional and bad stereo runs.

The problem is what happens after contact. In `stereo_imaging / opencode_minimax / case_0002`, Minimax never reads the README/verifier and writes claimed stereo pairs covering targets; that is a Claude-like schema-private failure. But many other Minimax failures are subtler. In relay, all five traces read the README and run the verifier, yet the aggregate service fraction is zero. In revisit, Minimax can see verifier-reported off-nadir violations and still finalize because the solution "structure" looks right to its private Brahe-access proxy. In regional and AEOSSP, it often repairs the schema but continues trusting weak geometry or accepts valid files with near-zero objective value.

So Minimax does have private-world moments, but its dominant pattern is not "never saw authority." It is "saw authority, then treated it as a debugger or filter rather than a governing contract."

### DPSK: Grounded, Then Drifting

The DPSK stereo traces are useful because they separate schema discovery from acceptance discipline. DPSK usually lists the workspace, reads the README, loads Brahe, and runs the local verifier. Its failure is therefore not the Claude failure of inventing `stereo_observations` without seeing that `actions` are required.

DPSK's failures happen later. It builds a substantial private model for access windows, signed steering, strip overlap, and scheduling. In `case_0001`, the verifier reports a valid schedule with `coverage_ratio=0.0` and `normalized_quality=0.0`; DPSK still accepts hard validity as the deliverable even though all evaluated pairs have zero overlap. In `case_0004`, it finds a high-scoring derived product schedule but finalizes while the verifier still reports hard violations. In `case_0003`, the same harness succeeds after fixing the across-track sign convention and preserving final verifier validity.

That pattern is weaker than Claude's sealed private world but still belongs in the same family: the private model becomes the active source of truth for the next action. The difference is that DPSK usually starts from the right authority hierarchy and then lets it decay.

### Kimi: Contract-Aware, Frame-Misaligned

Kimi's stereo failure is even less like Claude's. Kimi usually reads the README and uses the verifier. It knows the submission is supposed to be raw observation `actions`, and it spends much of the run trying to reconcile access, overlap, convergence, and pixel scale.

The private component is a coordinate-frame model. Kimi expresses `off_nadir_across_deg` in the opposite signed cross-track convention from the verifier in three productive stereo cases. That can leave observations hard-valid while boresight strips miss the target AOIs, so the official metric collapses to zero or near-zero. Counterfactual mirroring of `off_nadir_across_deg` dramatically improves `case_0002` and `case_0005`.

This is a private-model failure, but not a full private-world failure. Kimi is inside the real benchmark contract. It just binds one high-leverage physical interface incorrectly and then debug-loops around the wrong suspects for too long.

### Codex: The Counterexample

The relay Codex case study is the strongest control. Codex also writes private scripts, private geometry estimates, and case-specific search code. The difference is hierarchy. It reads the README early, writes a minimal `added_satellites` plus `actions` solution before optimizing, checks the verifier, and treats verifier metrics as the final arbiter.

That is exactly the distinction this report needs. Private modeling is not the bug. Private modeling is normal search. The bug is allowing the private model to define validity, schema, or score after the workspace has already provided a stronger authority.

### What Is Claude-Specific?

The Claude-specific behavior in these traces is not "uses private models" and not "can be wrong." It is the combination of:

1. **case-first closure**: `case/` feels complete enough to define the benchmark;
2. **durable invented interface**: the first serious solver/output encodes the inferred schema;
3. **self-reinforcing validation**: later scripts consume the same invented fields they emit;
4. **polished final confidence**: the final message reports coherent private metrics absent from the official run;
5. **normal completion**: the run can end with `end_turn`, not timeout or crash.

Other harnesses show pieces of this. Minimax sometimes invents schema; DPSK and Kimi sometimes let private physics outrank verifier feedback. Claude's bad runs are distinctive because the alternate contract becomes complete before external authority enters the loop. The result is not merely an incorrect approximation to the verifier; it is an alternate task.

## Mechanism

Claude's failure mode has four stages.

1. **Salience narrows the task boundary**. The prompt says to solve the prepared case using files in `case/`, so Claude starts inside `case/`.

2. **The case files are rich enough to create false completeness**. Mission files, satellites, targets, region grids, demands, or `.spot` instances provide enough structure to design a serious solver.

3. **The first durable artifact encodes an invented contract**. In bad stereo runs, the first solver writes grouped products (`observations` plus `stereo_pairs`, or `stereo_observations`) rather than raw `actions`; in relay, it writes `schedule` or `link_plan`; in SPOT-5, it writes selected-ID dictionaries.

4. **Private validation replaces authority**. Claude checks physical plausibility, target coverage, routing, constraint satisfaction, or profit, but it checks them against its own data model. After that, the README/verifier are no longer missing information; they are outside the story.

The key phrase is premature authority closure. Claude closes the contract before it has found the contract authority.

## Why `ls` Is Not Enough

The important diagnostic is not "did it call `ls`?" It is "what did `ls` authorize?"

In bad traces, `ls /app/workspace/case/` authorizes Claude to proceed. It sees the instance data and starts building. In good traces, an additional root-level discovery step changes the authority hierarchy:

```text
/app/workspace/README.md defines the submission contract
/app/workspace/verifier checks the submission contract
case/ supplies instance data
private scripts are search heuristics only
```

Without that hierarchy, Claude's internal solver becomes equal or superior to the benchmark contract. That is why it can say "all validity checks passed" while the official verifier cannot even find an `actions` array.

## Claude-Specific Characterization

This does feel like a Claude characteristic in these traces: once it has a sufficiently detailed local model, it tends to inhabit it. It writes clean code, gives precise metrics, reasons through physical edge cases, and produces polished final summaries. That competence makes the failure harder to detect. The private world is not sloppy; it is too complete.

The same tendency is a strength when the world is anchored correctly. In `stereo_imaging` case 0003 and `revisit_constellation` case 0001, Claude builds substantial case-specific machinery and gets verifier-confirmed wins. But the machinery is only trustworthy when the first authority binding is correct.

The short version:

```text
Claude is not primarily failing from lack of reasoning depth; it is failing from ungrounded depth. It can go very deep after choosing the wrong authority.
```

## Implications

For trace auditing, classify Claude runs by authority timing before interpreting score:

```text
Did Claude read root README or invoke packaged verifier before durable solver/output commitment?
If no, did it ever do so later?
If no, treat final metrics and final claims as private-world artifacts until proven otherwise.
```

For prompt design, the phrase "using the files in `case/`" is accurate but risky for Claude. It can make `case/` feel like the whole contract. The prompt should force the authority hierarchy before case reasoning:

```text
First inspect /app/workspace.
Read /app/workspace/README.md before writing any solver or solution.
Use case/ only as instance data.
If /app/workspace/verifier exists, run it before claiming validity.
```

For result interpretation, separate:

- **authority failures**: wrong schema, private validator, zero parsed actions
- **optimization failures**: correct schema, official verifier used, low score

Claude can be strong in the second category. The characteristic weakness here is the first category: ungrounded depth after premature closure.

## Practical Trace Checklist

When auditing future Claude traces, check these in order:

- Did Claude read root README or invoke packaged verifier before durable solver/output commitment?
- If not, did it ever do so later?
- First filesystem action: `case/` only, or root workspace?
- Did the first durable `solution.json` use the required top-level key?
- Did Claude create a private `verify.py` before using the packaged verifier?
- Does the final message report private metrics that are absent from `run.json`?
- Did the final stop reason show a normal `end_turn` or a provider/timeout stop?

For `stereo_imaging` case 0005, the answers are the bad signature: `case/` first, no README, no packaged verifier, private `verify.py`, wrong top-level key, final `end_turn`. That is a normal completed Claude run, and that is exactly the problem.
