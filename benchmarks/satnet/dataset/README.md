# SatNet Dataset Layout

The canonical SatNet dataset is stored as case-by-case week/year instances.

## Structure

```text
dataset/
├── README.md
├── index.json
├── mission_color_map.json
└── cases/
    └── W10_2018/
        ├── problem.json
        ├── maintenance.csv
        └── metadata.json
```

## Canonical Cases

Each case directory contains everything required to verify one SatNet instance:

- `problem.json`: request list for exactly one `(week, year)` instance
- `maintenance.csv`: maintenance windows filtered to that same instance
- `metadata.json`: lightweight summary and provenance metadata

Shared, non-verifier-critical benchmark metadata remains at dataset scope:

- `index.json`: manifest of canonical cases
- `mission_color_map.json`: mission display metadata carried over from the
  upstream SatNet release

## Provenance

The canonical cases are generated from the aggregate upstream SatNet data:

- repository: `https://github.com/edwinytgoh/satnet`
- source files: `data/problems.json`, `data/maintenance.csv`,
  `data/mission_color_map.json`

Use [generator.py](/home/betelgeuse/Developments/AstroReason-Bench/benchmarks/satnet/generator.py)
to regenerate this layout from the upstream source or a local copy of the
upstream `data/` directory.
