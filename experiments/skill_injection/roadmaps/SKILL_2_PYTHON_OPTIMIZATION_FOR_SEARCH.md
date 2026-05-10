# Skill 2: Python Optimization For Search

## Goal

Write `python-optimization-for-search`, a general skill-pack skill that helps agents build fast-enough candidate generation, product enumeration, and local search scripts in Python under a two-hour run budget.

## Inputs To Read

- Official Python docs:
  - `https://docs.python.org/3/library/multiprocessing.html`
  - `https://docs.python.org/3/library/concurrent.futures.html`
  - `https://docs.python.org/3/library/profile.html`
  - `https://docs.python.org/3/library/timeit.html`
- Official NumPy docs when vectorized examples are included:
  - `https://numpy.org/doc/stable/user/basics.broadcasting.html`
  - `https://numpy.org/doc/stable/reference/ufuncs.html`
- Local solver evidence:
  - CP solver README sections on candidate/product counts and runtime bottlenecks.
  - MILP solver README sections on batched satellite state series, parallel candidate generation, early rejection filters, product enumeration, and profiling fields.
- Existing repo convention:
  - `solvers/stereo_imaging/*/README.md`
  - `tests/experiments/test_workspace_assembly.py` for artifact discipline style.

## In Scope

- Create:
  - `experiments/_fragments/skills/skill_injection/python-optimization-for-search/SKILL.md`
  - `.../references/README.md`
  - `.../examples/search_loop_patterns.py`
  - optionally `.../scripts/profile_stub.py`
- Cover:
  - profiling before optimizing
  - cache expensive geometry/state computations
  - batch work by satellite, target, or independent instance block
  - use vectorized NumPy array operations for dense numeric transforms when data can be represented as arrays
  - avoid accidental slow vectorization caused by huge temporary arrays, object dtype arrays, or tiny one-off arrays
  - avoid repeated full-pool rescans
  - safe `ProcessPoolExecutor` patterns
  - deterministic seeds and stable tie-breaking
  - checkpointing best valid/likely-valid outputs

## Out Of Scope

- Benchmark-specific stereo formulas.
- OR-Tools modeling.
- Installing packages or changing system environments.
- Generic Python tutorials unrelated to search-heavy scheduling.

## Implementation Notes

- Examples must be synthetic and runnable without benchmark files.
- The examples should demonstrate shape, not final performance: build candidates once, store numeric fields in list or array structures, optionally vectorize cheap scoring/filtering, index by target, keep priority queues or sorted lists, run bounded improvement loops, and periodically write best-known output.
- Explain when not to use multiprocessing: tiny tasks, large pickle payloads, hidden shared state, and debug-first phases.
- Explain when not to use vectorization: branch-heavy logic, variable-length records, small loops where array construction dominates, and cases where a clear loop plus caching is easier to validate.
- Reference the official Python and NumPy docs in `references/README.md` and note the docs version/date checked.

## Validation

- Run the example script with `uv run python`.
- Confirm any vectorized snippet also has a small expected-output check so future agents can tell whether the array transformation is correct.
- Confirm `SKILL.md` does not mention stereo-specific private case details.
- Confirm examples are ASCII, deterministic, and short.
- Run skill-injection dry-run for `skill_pack` after the directory exists.

## Exit Criteria

- The skill can stand alone for other search-heavy benchmark tasks.
- At least one example script runs successfully and demonstrates the recommended control flow.
- Major performance claims cite Python official docs, NumPy official docs, or local solver evidence.

## Suggested Prompt

Read `experiments/skill_injection/roadmaps/SKILL_WRITING_ROADMAP.md` and this phase doc. Use official Python docs, official NumPy vectorization/broadcasting docs, and the stereo solver READMEs as sources. Create only the `python-optimization-for-search` skill directory with `SKILL.md`, `references/README.md`, and a runnable synthetic example. Include vectorization guidance alongside profiling, caching, batching, multiprocessing, deterministic search loops, and checkpointing. Do not add stereo-specific strategy or OR-Tools content. Run the example and focused tests.
