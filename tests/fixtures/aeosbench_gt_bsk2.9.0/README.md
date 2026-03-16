# AEOS-Bench Ground Truth Fixtures

This directory contains a hybrid fixture layout for
`tests/benchmarks/test_aeosbench_verifier.py`.

## Layout

One tiny case is kept unpacked for the default developer workflow:

- `cases/00157/`
- `solutions/00157.json`
- `metrics/00157.json`

The remaining fixture corpus is stored in archives:

- `cases.tar.gz`
- `solutions.tar.gz`
- `metrics.tar.gz`

`index.json` still lists the full corpus of case IDs.

## Test Behavior

By default, the AEOS verifier tests only use the unpacked case `00157`.

To run the full archived corpus, set:

```bash
AEOSBENCH_FULL_FIXTURES=1 uv run pytest tests/benchmarks/test_aeosbench_verifier.py
```

When that environment variable is present, the test file extracts the archived
fixtures into a temporary directory and then runs `test_all_fixtures`.

## What The Tests Read

The test loader consumes:

- `cases/<case_id>/constellation.json`
- `cases/<case_id>/taskset.json`
- `solutions/<case_id>.json` and specifically `solution["assignments"]`
- `metrics/<case_id>.json` and specifically `expected["metrics"]`
- `index.json` for the full-corpus case list

The compact fixture format keeps only the fields that the tests read.

## File Formats

### `solutions/<case_id>.json`

```json
{
  "assignments": {
    "0": [-1, -1, 5, 5, 5, -1],
    "1": [3, 3, 3, -1, -1, 8]
  }
}
```

### `metrics/<case_id>.json`

```json
{
  "metrics": {
    "CR": 0.8532,
    "WCR": 0.8234,
    "PCR": 0.1523,
    "WPCR": 0.1821,
    "TAT": 452.34,
    "PC": 12500.0
  }
}
```

### `index.json`

`test_all_fixtures` iterates over `index["fixtures"]` and reads each entry's
`case_id`.

## Notes

- The unpacked case keeps the default test path fast and lightweight.
- The archives preserve the full 20-case corpus without bloating the working tree.
- Full-corpus extraction happens outside the repository so Git and file explorer
  performance stay stable after opt-in runs.
