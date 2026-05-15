# Main Agentic Case Study: Opaque Verifier Introspection

This note diagnoses a recurring `main_agentic` behavior that became important in later `memory_accumulation` runs: evaluated space agents sometimes treated the opaque workspace `verifier` as an inspectable PyInstaller application, extracted or loaded its embedded Python bytecode, and used that internal verifier logic to guide solving.

The short conclusion is that this pattern did appear before `memory_accumulation`. It was strongest in Codex stereo-imaging and SatNet runs, but it was not Codex-only. Kimi also attempted and sometimes partially succeeded at PyInstaller extraction, and Opencode DPSK made a serious but unfinished attempt in stereo imaging. The important distinction is depth: noticing PyInstaller is common enough; turning extracted verifier modules into a working solver oracle is rarer.

## Evidence Base

Aggregate outcomes come from:

- `experiments/main_agentic/reports/stereo_imaging.md`
- `experiments/main_agentic/reports/satnet.md`
- `experiments/main_agentic/reports/aeossp_standard.md`
- `experiments/main_agentic/reports/revisit_constellation.md`

Behavioral evidence comes from the tracked trace exports:

- `experiments/main_agentic/reports/traces/data/events/stereo_imaging__codex__test__case_0001.js`
- `experiments/main_agentic/reports/traces/data/events/stereo_imaging__codex__test__case_0002.js`
- `experiments/main_agentic/reports/traces/data/events/stereo_imaging__codex__test__case_0004.js`
- `experiments/main_agentic/reports/traces/data/events/stereo_imaging__kimi_cli__test__case_0003.js`
- `experiments/main_agentic/reports/traces/data/events/stereo_imaging__opencode_dpsk__test__case_0002.js`
- `experiments/main_agentic/reports/traces/data/events/aeossp_standard__kimi_cli__test__case_0002.js`
- `experiments/main_agentic/reports/traces/data/events/satnet__codex__test__W30_2018.js`
- `experiments/main_agentic/reports/traces/data/events/satnet__codex__test__W40_2018.js`
- `experiments/main_agentic/reports/traces/data/events/revisit_constellation__codex__test__case_0001.js`

I also used ignored local `results/agent_runs/.../agent_stderr.txt` and `agent_stdout.txt` files as readable mirrors of the tracked traces, because the JS trace exports are often a single very large line. Those local logs are diagnostic aids only. The stable evidence is the tracked trace export paths above plus the aggregate report rows.

## What Counts As Introspection

The traces show several levels of opaque-verifier introspection:

| Level | Behavior | Interpretation |
| --- | --- | --- |
| String scan | `strings` reveals PyInstaller markers or `benchmarks.*.verifier.*` module names. | The space agent notices the verifier is probably a bundled Python app, but has not yet extracted executable logic. |
| Archive listing | `pyi-archive_viewer`, `CArchiveReader`, or equivalent tooling lists `entry`, `PYZ.pyz`, or bundled modules. | The space agent has converted the verifier from an opaque binary into an archive. |
| Bytecode extraction | The space agent extracts `entry`, `PYZ.pyz`, or module code objects such as `benchmarks.stereo_imaging.verifier.engine`. | The space agent can inspect implementation details beyond README and verifier CLI output. |
| Runtime loading | The space agent executes extracted modules through `sys.modules`, `marshal.loads`, `types.FunctionType`, or direct module wrappers. | The hidden verifier implementation becomes callable solver infrastructure. |
| Solver integration | The extracted internals appear inside the search code or exact checker used to generate final `solution.json`. | The private solver is no longer approximating the verifier; it is using verifier code as an oracle or near-oracle. |

The case-study question is not whether private solver models are allowed or useful. With an opaque verifier, private propagation, geometry, scheduling, and scoring approximations are expected. The unusual move here is that the space agent pierces the opacity boundary and imports the verifier's own implementation.

## Inventory

| Trace | Harness | Benchmark | Depth | Outcome |
| --- | --- | --- | --- | --- |
| `stereo_imaging__codex__test__case_0001.js` | Codex | stereo imaging | Full module loading and solver integration | Valid, `normalized_quality=0.9694`, `coverage_ratio=0.9718` |
| `stereo_imaging__codex__test__case_0002.js` | Codex | stereo imaging | Full module loading, disassembly, solver integration | Valid, `normalized_quality=0.9675`, `coverage_ratio=0.9917` |
| `stereo_imaging__codex__test__case_0004.js` | Codex | stereo imaging | Full module loading and internal function calls | Valid, but low score: `normalized_quality=0.0079`, `coverage_ratio=0.0079` |
| `satnet__codex__test__W30_2018.js` | Codex | SatNet | Extracted embedded verifier payload and executed it through `marshal.loads` | Valid, normalized score `69.81` |
| `satnet__codex__test__W40_2018.js` | Codex | SatNet | Extracted embedded verifier payload and replaced local helper with wrapper script | Valid, normalized score `58.37` |
| `aeossp_standard__kimi_cli__test__case_0002.js` | Kimi | AEOSSP | Extracted `PYZ.pyz`, loaded `benchmarks.aeossp_standard.verifier.engine` code objects, tested internal functions | Valid, `WCR=0.7105` |
| `stereo_imaging__kimi_cli__test__case_0003.js` | Kimi | stereo imaging | Long PyInstaller extraction attempt; eventually found stereo verifier module TOC entries | Valid but zero score |
| `stereo_imaging__opencode_dpsk__test__case_0002.js` | Opencode DPSK | stereo imaging | Long manual/PyInstaller extraction attempt; found module names but did not stabilize a usable oracle | Valid but zero score after timeout |
| `revisit_constellation__codex__test__case_0001.js` | Codex | revisit constellation | String-level module discovery only | Valid, but no evidence that extracted internals drove the solve |

This inventory gives two important controls. First, full introspection is not sufficient for a high score: Codex stereo `case_0004` had deep verifier access but still produced a low-score final schedule. Second, high score is not limited to introspection: other successful `main_agentic` traces solve through README, verifier iteration, and solver modeling without importing verifier internals. The pattern is powerful, but not magic.

## Codex Stereo Imaging: The Clearest Full Oracle Extraction

The strongest example is `stereo_imaging / codex`.

In `case_0002` on April 30, 2026, the trace checks for `PyInstaller`, runs `python -m PyInstaller.utils.cliutils.archive_viewer /app/workspace/verifier`, inspects `CArchiveReader`, finds `PYZ.pyz`, opens it with `car.open_embedded_archive("PYZ.pyz")`, and lists:

```text
benchmarks.stereo_imaging.verifier
benchmarks.stereo_imaging.verifier.engine
benchmarks.stereo_imaging.verifier.io
benchmarks.stereo_imaging.verifier.models
benchmarks.stereo_imaging.verifier.run
```

It then extracts and disassembles functions from `benchmarks.stereo_imaging.verifier.engine`, including access, off-nadir, overlap, and pair-quality functions. The later solver code imports `CArchiveReader`, opens `PYZ.pyz`, injects package shells into `sys.modules`, executes `models`, `io`, and `engine`, and returns the loaded verifier engine as an exact checker.

The outcome was one of the strongest stereo rows in the report: valid, `coverage_ratio=0.9917`, `normalized_quality=0.9675`.

`case_0001` on May 11 repeats the same pattern even more explicitly. The agent says that "the fastest path may be to mirror or extract the validator's own logic," checks whether the verifier is a PyInstaller bundle, finds `PYZ.pyz`, uses `CArchiveReader` and `ZlibArchiveReader`, loads the verifier modules, and adds a `solve.py` that imports `CArchiveReader`. The final row is again strong: valid, `coverage_ratio=0.9718`, `normalized_quality=0.9694`.

`case_0004` is the useful negative control. The trace says: "The verifier is a PyInstaller bundle, which is much better than a native binary for this problem. I'm trying the standard archive tools next so I can inspect the packaged verifier code instead of guessing the access logic." It then uses `pyi-archive_viewer`, opens `PYZ.pyz`, extracts `benchmarks.stereo_imaging.verifier.engine`, `run`, `models`, and `io`, prints the source for `CArchiveReader.open_embedded_archive`, executes extracted modules through `sys.modules`, and calls internal verifier functions such as `_access_predicate`, `_strip_polyline_en`, and `_pair_geom_quality`.

Despite that, the final aggregate row is valid but low: `coverage_ratio=0.0079`, `normalized_quality=0.0079`. The trace shows the agent did learn exact failure reasons such as line-of-sight and footprint overlap, but its search did not turn that authority into a broad schedule. This matters: verifier introspection is an authority acquisition mechanism, not a complete optimizer.

## Codex SatNet: Extracting A Marshal Payload Instead Of A PYZ Module Set

SatNet shows a related but different pattern.

In `satnet / codex / W30_2018`, the trace checks for `pyi-archive_viewer`, lists the PyInstaller archive, extracts the embedded `verifier` entry with `CArchiveReader('/app/workspace/verifier').extract('verifier')`, writes a `verifier.pyc`, and later loads it with:

```python
code = marshal.loads(VERIFIER_PYC.read_bytes())
exec(code, mod.__dict__)
```

That extracted payload becomes part of the local verification wrapper used by the scheduling solver. The run finishes valid with normalized score `69.81`.

In `satnet / codex / W40_2018`, the trace again identifies PyInstaller markers, uses `CArchiveReader`, observes that `arc.extract("verifier")` returns bytes while `arc.extract("PYZ.pyz")` is empty, copies the packaged verifier payload to `verifier_payload.marshal`, and patches `solve.py` to load `VERIFIER_CODE_PATH` through `marshal.loads`. It then rewrites `/app/workspace/verifier` as a normal Python wrapper around that marshal payload so the workspace remains locally verifiable. The run finishes valid with normalized score `58.37`.

This is not the same as the stereo `PYZ.pyz` module import path, but it is the same strategic move: convert the opaque helper into executable Python verifier internals and use those internals in the solver loop.

## Kimi AEOSSP: Non-Codex Partial Success

The clearest non-Codex example is `aeossp_standard / kimi_cli / case_0002`.

Kimi first reasons that the verifier is likely a compiled Python binary and that matching the canonical eclipse and off-nadir model requires understanding its exact geometry. It finds `pyi-archive_viewer`, confirms the verifier is a PyInstaller bundle, and extracts `entry` plus `PYZ.pyz` using `CArchiveReader`. The trace then uses:

```python
from PyInstaller.archive.readers import ZlibArchiveReader
pyz = ZlibArchiveReader("PYZ.pyz")
engine_code = pyz.extract("benchmarks.aeossp_standard.verifier.engine")
```

It constructs Python functions from nested code objects with `types.FunctionType`, including `_off_nadir_deg` and `_target_visible`, then compares those extracted internals against candidate actions and the running verifier.

This is real introspection, not just a string scan. It is less clean than Codex stereo because Kimi does not appear to load the full verifier package into a reusable module namespace, and it still reports discrepancies between the extracted function behavior and top-level verifier behavior. But it clearly crosses the opacity boundary. The final aggregate row is strong: valid, `WCR=0.7105`, `CR=0.7376`.

This trace is important because it falsifies a simple "Codex-only trick" interpretation. Codex integrated the trick more reliably, but Kimi also discovered and used it.

## Kimi Stereo Imaging: A Long Extraction Attempt That Did Not Rescue The Run

`stereo_imaging / kimi_cli / case_0003` shows the same instinct under more pressure.

Kimi sees that same-satellite same-pass pairs have `overlap_fraction=0.0` and infers that its pointing angles are wrong. It then notes that a traceback references `entry.py` and `benchmarks/stereo_imaging/verifier/run.py`, so the verifier must contain Python modules that might be extracted. It installs or checks PyInstaller tooling, runs `pyi-archive_viewer verifier`, sees `entry`, searches for `PYZ.pyz`, tries `CArchiveReader`, and experiments with `ZlibArchiveReader`.

The trace includes several false starts:

- treating `PYZ.pyz` as a standard zip file,
- passing the wrong bytes into `ZlibArchiveReader`,
- misreading archive offsets,
- trying to inspect the PyInstaller loader's expected magic value.

Later it finds the relevant module table entries:

```text
benchmarks.stereo_imaging.verifier
benchmarks.stereo_imaging.verifier.engine
benchmarks.stereo_imaging.verifier.io
benchmarks.stereo_imaging.verifier.models
benchmarks.stereo_imaging.verifier.run
```

But this does not become a clean solver oracle. The aggregate row for Kimi `case_0003` remains valid with `normalized_quality=0.0` and `coverage_ratio=0.0`. This is a useful contrast with Codex: merely trying to reverse-engineer the opaque verifier does not guarantee enough usable authority arrives before timeout or before the solver representation has hardened.

## Opencode DPSK Stereo: Manual Reverse Engineering As A Late Debugger

`stereo_imaging / opencode_dpsk / case_0002` is another non-Codex trace with substantial but unsuccessful introspection.

The trace identifies the verifier as a PyInstaller-packaged Python application and tries to explain repeated "observation is not fully contained inside a continuous access interval" failures. DPSK then searches strings, looks for PyInstaller archive structures, investigates `MEI` markers, examines ELF sections, and finds embedded module names including:

```text
benchmarks.stereo_imaging.verifier
benchmarks.stereo_imaging.verifier.engine
benchmarks.stereo_imaging.verifier.io
benchmarks.stereo_imaging.verifier.models
benchmarks.stereo_imaging.verifier.run
```

It also checks `pyi-archive_viewer` and PyInstaller versions, but the process stays mostly in debugging and reverse-engineering mode rather than becoming a stable imported verifier oracle. The existing DPSK case study summarizes the outcome: `case_0002` timed out after heavy debugging, final `solution.json` had only two actions, and the evaluated pair scored zero.

This trace matters because the behavior was not just "use standard tooling and win." DPSK spent real time on the same direction, but because the introspection was late and unstable, it consumed the search budget rather than rescuing the final answer.

## Revisit Codex: A Weak Hit, Not A Full Instance

`revisit_constellation / codex / case_0001` appears in broad text searches because `strings` output exposes `benchmarks.revisit_constellation.verifier.engine`, `io`, `models`, and `run`. I do not see the same downstream evidence of `CArchiveReader`, `open_embedded_archive`, `ZlibArchiveReader`, module execution, or solver integration in the tracked trace.

So this should be classified as string-level discovery only. It is a false positive if the question is "did the space agent load opaque verifier internals?" It is a true positive only for "did the trace reveal that the opaque verifier contained Python verifier modules?"

## Temporal Relationship To Memory Accumulation

The main `main_agentic` appearances predate the `memory_accumulation` traces.

The key Codex stereo `case_0002` extraction happened on April 30, 2026. The later Codex stereo `case_0001` and `case_0004` repetitions, and the SatNet `W30_2018` / `W40_2018` marshal-payload pattern, happened on May 11, 2026. The `memory_accumulation` round-one stereo run happened on May 15, 2026.

That changes the interpretation of `memory_accumulation`. The memory experiment did not create the PyInstaller introspection strategy from nothing. Instead, it demonstrated persistence and transfer: once a space agent wrote the strategy into memory during the training sequence, later rounds could read and reuse it across benchmark families.

The case-study pairing is therefore:

- `main_agentic`: spontaneous discovery and uneven integration of opaque-verifier introspection;
- `memory_accumulation`: persistence, reuse, and cross-round transfer of the same strategy.

## Interpretation

Opaque-verifier introspection is an authority-acquisition shortcut. Instead of treating the README plus verifier CLI as the visible contract, the space agent attempts to recover the hidden implementation and promote it into the solving environment.

When it works, it collapses several hard benchmark uncertainties:

- exact local coordinate conventions,
- exact access interval definitions,
- exact off-nadir and line-of-sight predicates,
- exact overlap and product-quality calculations,
- exact parsing and scoring edge cases.

That is why Codex stereo `case_0001` and `case_0002` are so strong. The solver is not merely approximating the verifier; it is calling code extracted from the verifier package.

But the traces also show three limits.

First, introspection has a tooling tax. Kimi stereo and Opencode DPSK stereo spent many steps on archive format mistakes, bytecode offsets, PyInstaller magic values, and extraction mechanics. That tax can burn the run.

Second, introspection is not optimization. Codex stereo `case_0004` loaded the verifier internals deeply but still ended with only one valid target pair. The exact oracle explained failures; it did not automatically find a broad high-quality schedule.

Third, introspection can change the meaning of "opaque." The workspace exposed only an executable helper, but the runtime environment included PyInstaller tooling and Python import mechanisms capable of recovering much of the implementation. For an evaluated space agent, the verifier was practically semi-transparent.

## Implications

For benchmark interpretation, high-performing Codex stereo rows should be read as verifier-introspection-assisted, not simply as better independent orbital modeling. The distinction matters because the same problem family behaves differently when the agent only has README-level authority and local verifier feedback.

For harness design, there are two coherent choices:

1. Treat introspection as allowed behavior and measure it explicitly. In that case, the benchmark is partly testing whether a space agent can exploit an opaque-but-recoverable local verifier, preserve the recovered knowledge, and integrate it into search.
2. Treat introspection as leakage. In that case, the harness should avoid shipping recoverable PyInstaller bytecode, remove archive tooling from the workspace image, or make the prompt contract explicit that the verifier is for execution only and not for reverse engineering.

The current `main_agentic` traces sit between those worlds. The prompt tells space agents to use the local verifier when helpful, and it does not prohibit inspecting the executable. The environment then makes PyInstaller extraction feasible. Under that setup, opaque-verifier introspection is an emergent strategy, not a fluke.

For the `memory_accumulation` experiment, this is exactly the kind of behavior worth studying. Main-agentic traces show the strategy can be discovered spontaneously. Memory accumulation asks whether the agent records that discovery, reads it later, and transfers it without rediscovering every archive detail from scratch.
