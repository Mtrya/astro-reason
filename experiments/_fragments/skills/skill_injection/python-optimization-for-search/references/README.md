# Python Optimization For Search References

Search-code checklist. `examples/search_loop_patterns.py` shows the same ideas on synthetic data.

## Profiling

- Profile before rewriting. Guessing is often wrong.
- Use deterministic profiling for whole functions and small timing loops for tiny hot snippets.
- Sort profile output by cumulative time to find expensive call trees, then by internal time to find tight loops.
- Separate construction time, scoring time, search time, and output-writing time in your own logs.

Useful docs:

- Python profiling: https://docs.python.org/3/library/profile.html
- Python timing helpers: https://docs.python.org/3/library/timeit.html

## Caching

- Cache pure repeatable computations whose inputs can be made hashable.
- Do not cache values that depend on hidden mutable state, random seeds, wall clock, or partially edited schedules.
- Prefer an explicit cache dictionary when you need eviction, counters, or debugging.
- Keep candidate libraries immutable once search starts so cached scores remain meaningful.

Useful docs:

- Python `functools`: https://docs.python.org/3/library/functools.html

## Vectorization And Batching

- Batch candidate scoring when the same formula is applied to many candidates.
- Use NumPy arrays for numeric filters, masks, and top-k preselection when memory stays reasonable.
- Avoid broadcasting shapes that create huge temporary arrays.
- Use `out=` and `where=` on ufuncs when they make memory use clearer.
- Keep a stable ID array beside vectorized scores so selections map back to original candidates.

Useful docs:

- NumPy broadcasting: https://numpy.org/doc/stable/user/basics.broadcasting.html
- NumPy ufuncs: https://numpy.org/doc/stable/reference/ufuncs.html
- NumPy vectorization glossary: https://numpy.org/doc/stable/glossary.html#term-vectorization

## Multiprocessing

- Use process workers only for coarse independent batches.
- Worker functions and their arguments/results must be picklable.
- Protect process-pool entrypoints with `if __name__ == "__main__":`.
- Do not mutate shared search state from workers; return results and merge deterministically.
- Avoid calling executor or future methods from inside submitted worker functions.

Useful docs:

- Python multiprocessing: https://docs.python.org/3/library/multiprocessing.html
- Python concurrent futures: https://docs.python.org/3/library/concurrent.futures.html

## Deterministic Search

- Sort candidates by stable tie-breakers after score fields.
- Use fixed seeds for any randomized perturbation.
- Insert or remove compound choices atomically: either the full move is accepted or the old schedule is restored.
- Recompute the objective from scratch after accepted moves until you trust any incremental delta logic.
- Save checkpoints with atomic replace writes so interrupted runs leave a readable file.
