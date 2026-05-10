# Python Optimization For Search References

Checked on 2026-05-10. This skill is grounded in official Python and NumPy documentation plus local solver READMEs used only as evidence for general optimization patterns.

## Official Python Sources

- Python `profile` and `cProfile` documentation: https://docs.python.org/3/library/profile.html. The docs describe deterministic profiling, recommend `cProfile` for most users because it is a C extension with reasonable overhead, and show sorting profile reports by cumulative or internal time.
- Python `timeit` documentation: https://docs.python.org/3/library/timeit.html. The docs describe timing small snippets, using repeated trials, and treating the best run as the lower bound when noise is present.
- Python `functools` documentation: https://docs.python.org/3/library/functools.html. The docs define `cache`, `lru_cache`, and `cached_property`; the skill uses these only for pure repeatable computations.
- Python `multiprocessing` documentation: https://docs.python.org/3/library/multiprocessing.html. The docs describe process-based parallelism, data parallelism over input values, and the `if __name__ == "__main__":` importability pattern for subprocesses.
- Python `concurrent.futures` documentation: https://docs.python.org/3/library/concurrent.futures.html. The docs state that `ProcessPoolExecutor` uses `multiprocessing`, can side-step the GIL, requires picklable callables/arguments/results, requires an importable `__main__`, and can deadlock if executor/future methods are called from submitted worker callables.

## Official NumPy Sources

- NumPy broadcasting guide: https://numpy.org/doc/stable/user/basics.broadcasting.html. The guide says broadcasting vectorizes array operations so looping happens in C rather than Python, usually without needless copies, while warning that broadcasting can waste memory in bad shapes.
- NumPy ufunc reference: https://numpy.org/doc/stable/reference/ufuncs.html. The reference defines universal functions as elementwise operations on ndarrays that support broadcasting, type casting, `where`, and `out` arguments.
- NumPy glossary vectorization entry: https://numpy.org/doc/stable/glossary.html#term-vectorization. Use this for terminology when explaining vectorized array operations.

## Local Solver Evidence

- `solvers/stereo_imaging/cp_local_search_stereo_insertion/README.md` describes reusable candidate and product libraries, deterministic greedy seeding, atomic insertion/rollback moves, bounded local search, seeded multi-run perturbations, conservative repair, candidate/product summaries, and distinct construction/search timing.
- `solvers/stereo_imaging/time_window_pruned_stereo_milp/README.md` describes batched state generation, parallel candidate generation, cheap prechecks, product enumeration with early rejection filters, candidate pruning, profiling counters by stage, and clear backend/runtime status fields.
- These READMEs support general engineering advice only. This skill intentionally does not copy stereo formulas, solver commands, solver source code, or benchmark-specific strategy.

## Validation Note

- `examples/search_loop_patterns.py` is a synthetic, deterministic script with no benchmark inputs. It demonstrates batched candidate generation, vectorized scoring/filtering, pure-function caching, optional `ProcessPoolExecutor`, stable greedy/local-search loops, and atomic checkpoint writes.
- Run it with `uv run python experiments/_fragments/skills/skill_injection/python-optimization-for-search/examples/search_loop_patterns.py`.
