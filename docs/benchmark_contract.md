# Benchmark Contract

This document defines the repository contract for benchmark layout, public entrypoints, and CI enforcement.

The contract is enforced only for benchmarks listed in `benchmarks/finished_benchmarks.json`. Benchmarks that are still under active construction are documented by repository conventions, but they are not yet subject to strict CI checks.

## Finished Benchmark Metadata

`benchmarks/finished_benchmarks.json` is the source of truth for which benchmarks are considered finished.

Each finished benchmark entry records:

- the benchmark name
- whether generator reproducibility should run in dedicated CI
- which dataset paths are generator-owned canonical outputs

Promoting a benchmark to finished status should happen only when its public README, dataset layout, generator, verifier, and tests are ready to be treated as stable.

## Required Benchmark Shape

Each finished benchmark must live under `benchmarks/<name>/` and must contain:

- `README.md`
- `dataset/`
- `splits.yaml`
- a generator entrypoint: `generator.py` or `generator/run.py`
- a verifier entrypoint: `verifier.py` or `verifier/run.py`

Optional:

- `visualizer.py` or `visualizer/run.py`
- `dataset/index.json`
- `dataset/README.md`

No other tracked top-level benchmark entries are allowed for finished benchmarks.

## Entrypoint Invocation Policy

Benchmark entrypoint invocation follows the file layout:

- **Top-level script** (`generator.py`, `verifier.py`, `visualizer.py`): invoke directly as `python benchmarks/<name>/<entrypoint>.py ...` (from the repository root).
- **Package entrypoint** (`generator/run.py`, `verifier/run.py`, `visualizer/run.py`): invoke as a module: `python -m benchmarks.<name>.<entrypoint_pkg>.run ...` (from the repository root).

Do not support both invocation styles for the same entrypoint. Do not add bootstrap hacks (`sys.path` surgery, fake runtime packages) solely to make a nested `run.py` work as a direct path script.

## Dataset Contract

The canonical dataset layout for finished benchmarks is:

```text
dataset/
├── example_solution.json  # required, one minimal runnable example (same schema as a real solution)
├── cases/
│   └── <split>/
│       └── <case_id>/
├── index.json      # optional
└── README.md       # optional
```

Rules:

- `dataset/cases/` is mandatory.
- The canonical committed layout for finished benchmarks is `dataset/cases/<split>/<case_id>/`.
- Split names are benchmark-owned path segments validated through `splits.yaml`.
- Case identifiers are benchmark-specific. CI does not require a `case_####` naming pattern.
- The dataset root must include `example_solution.json`, `example_solution.yaml`, or `example_solution.yml` so CI can run the public verifier against a real benchmark case automatically. This file must contain a **single** solution object with the same schema as a normal per-case solution file (not a mapping from case IDs to solutions).
- `index.json` is optional. If present, it is benchmark metadata, not a second source of truth for completion status. It may include optional `example_smoke_case` (string): a relative case path such as `test/case_0001` that resolves under `dataset/cases/` for verifier smoke tests. When omitted, CI uses the lexicographically first case directory under `dataset/cases/<split>/`.
- Generators must not write `dataset/README.md`.
- Additional tracked dataset files are allowed when they are benchmark-owned public artifacts and are documented in the benchmark README.
- `dataset/source_data/` may be used as a download/cache directory, but it must stay gitignored and must not be required to exist before running the generator.

## Unit Conventions (recommended, not CI-enforced)

Benchmark datasets should encode physical units consistently:

- Linear quantities: meters (key suffix `_m` or documented in README when a key is dimensionless).
- Area quantities: square meters.
- Time durations: seconds (suffix `_s` or `_sec` as documented for that benchmark).
- Speed quantities: meters per second (suffix `_m_s` or equivalent documented naming).
- Angular quantities: either degrees (suffix `_deg`) or radians (suffix `_rad`).
- Timestamps: ISO 8601 with `Z` or an explicit UTC offset.

Prefer SI-style keys and values where it improves clarity, but benchmarks may use non-SI time units such as hours when that is the natural problem vocabulary and is clearly documented in the benchmark README.

## Generator Contract

Finished benchmark generators must satisfy the following:

- A committed benchmark-local `splits.yaml` is mandatory for finished benchmarks.
- **Top-level** `generator.py`: runnable as `python benchmarks/<name>/generator.py ...`.
- **Nested** `generator/run.py`: runnable as `python -m benchmarks.<name>.generator.run ...`.
- Reproducing the canonical dataset must use an explicit YAML path:
  - `python benchmarks/<name>/generator.py benchmarks/<name>/splits.yaml`
  - `python -m benchmarks.<name>.generator.run benchmarks/<name>/splits.yaml`
- Running without the required YAML path must fail with usage information. Finished benchmarks do not keep a no-argument canonical generation path.
- The committed `splits.yaml` is benchmark-owned public configuration, not a placeholder. It should expose the intended dataset-construction parameters clearly enough that readers do not need to reverse-engineer generator defaults from Python code.
- Dataset-construction parameters belong in YAML. Purely operational controls such as `--help`, and benchmark-specific runtime toggles like force-refresh or force-download behavior when justified, may remain optional CLI flags.
- If source downloads are needed, the generator may cache them under `dataset/source_data/`, but it must also be able to perform a live download when that cache is absent.

Case specifications should be derived algorithmically from parameters (seed, scaling rules, sampling), not from hand-maintained lists of per-case tuples. Hardcoding curated lists such as `base_specs` or `BASE_SPECS` is discouraged; see `stereo_imaging` generator patterns (e.g. sampling driven by seed) for a reference approach.

### `splits.yaml` Schemas

Finished benchmarks must commit a `splits.yaml` with a top-level `splits:` mapping. Two shared shapes are supported:

**Split parameters** for algorithmic generators that build cases per split:

```yaml
splits:
  easy:
    seed: 42
    case_count: 5
    max_satellites: 3
  hard:
    seed: 142
    case_count: 5
    max_satellites: 12
```

**Split assignments** for fixed-case benchmarks that assign existing case IDs into splits:

```yaml
splits:
  test:
    - case_001
    - case_002
  train:
    - case_003
    - case_004
```

Rules:

- Single-split YAML is valid.
- Use one schema per benchmark `splits:` mapping rather than mixing assignment lists and parameter mappings.
- Benchmark-owned per-split fields remain benchmark-specific inside the shared outer `splits:` structure.
- Non-obvious benchmark-owned fields should be documented. Inline YAML comments are preferred when they help explain the parameter meaning or its effect on dataset construction.

## Verifier Contract

Finished benchmark verifiers must satisfy the following:

- **Top-level** `verifier.py`: runnable as `python benchmarks/<name>/verifier.py ...`.
- **Nested** `verifier/run.py`: runnable as `python -m benchmarks.<name>.verifier.run ...`.
- The public CLI accepts two positional arguments:
  - `case_dir`
  - `solution_path`
- Any additional CLI options must be optional.
- Verifiers must be runnable as documented and must be able to load canonical cases without crashing.

The dataset-level `example_solution.json` or `example_solution.yaml` is the preferred verifier smoke-test convention for finished benchmarks. It holds one minimal runnable solution whose schema matches real submissions. Pairing with a case directory uses `example_smoke_case` in `index.json` when the smoke case is not the lexicographically first under `dataset/cases/<split>/`. The field value is a relative path such as `test/case_0001`. These are runnable examples, not baselines.

### Reference frames (recommendations, not CI-enforced)

Frame choices are benchmark-specific. For verifiers that use Earth-centered frames:

- **Earth-fixed (ECEF):** prefer a defined realization such as ITRF when high precision matters.
- **Inertial (ECI):** prefer a standard celestial frame such as GCRF when applicable.
- Use one astrodynamics stack consistently within a verifier to avoid mixed-frame inconsistencies.
- If Earth orientation parameters (EOP) or similar affect solutions, document the strategy in the benchmark README.

These are recommendations, not strict CI requirements: some benchmarks may use simplified frames for clarity.

## Enforced CI Checks

For finished benchmarks, CI enforces:

- benchmark presence in `benchmarks/finished_benchmarks.json`
- required top-level files and directories
- canonical dataset case layout under `dataset/cases/<split>/<case_id>/`
- presence and schema validity of benchmark-local `splits.yaml`
- example solution for verifier smoke tests at dataset root
- no tracked `dataset/source_data/`
- no tracked editor backup artifacts such as files ending in `~`
- no `sys.path` hacks in benchmark generator/verifier/visualizer code
- no `from benchmarks.` imports in benchmark generator/verifier/visualizer code
- generator `--help`, generator no-arg failure, and verifier smoke tests using the supported invocation for each entrypoint shape (direct script vs `python -m`)
- passing repository tests

GitHub Actions runs:

- PR/push CI for tests plus contract validation
- a separate reproducibility workflow for finished benchmarks whose metadata has `"repro_ci": true`; it invokes generators with the committed `splits.yaml` path and compares only generator-owned outputs from `generated_paths`

The reproducibility workflow compares only generator-owned dataset outputs from `generated_paths`, because finished benchmarks may also keep documented, hand-written dataset artifacts such as dataset-level notes.

## Documented But Not Fully Automated Yet

The following are part of the public contract even when CI does not fully enforce them yet:

- benchmark public code and public artifacts must not reference internal-only guidance such as `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, or `docs/internal/`
- public verifier/generator/visualizer code should avoid path hacks and other brittle bootstrapping
- public benchmark-facing data and comments should avoid benchmark-leakage phrasing that explicitly tells a space agent it is inside a verification harness
- the repository remains solution-free; example solutions are only for verifier smoke tests and are not baselines
