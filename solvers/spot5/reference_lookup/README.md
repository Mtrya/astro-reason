# SPOT5 Reference Lookup Solver

This solver is a fixture-backed lookup baseline for SPOT5.

It recognizes known SPOT5 instance files by SHA-256 hash and copies the matching
reference solution into the requested solution directory. It is reproducible and
verifier-backed, but it is not a general SPOT5 solver and makes no claim about
unseen instances.

## Contract

```bash
./setup.sh
./solve.sh <case_dir> [config_dir] [solution_dir]
```

`config_dir` is experiment-owned and may be omitted. `solution_dir` defaults to
`solution/` when omitted.

For supported cases, the solver writes:

- `solution.spot_sol.txt`: primary SPOT5 solution artifact
- `status.json`: lookup metadata

For unsupported cases, it exits nonzero and writes `status.json` with
`status: "unsupported_case"` when a solution directory is available.

## Provenance

Solution fixtures are copied from `tests/fixtures/spot5_val_sol/`. They are
reference solutions obtained from the DCKP-RSOA repository and discussed in the
SPOT5 benchmark README.
