---
dataset_info:
  features:
    - name: case_id
      dtype: string
    - name: split
      dtype: string
    - name: benchmark
      dtype: string
    - name: index_metadata
      dtype: struct
    - name: files
      sequence:
        - name: path
          dtype: string
        - name: content
          dtype: string
  splits:
    - name: test
      num_bytes: 0
      num_examples: 0
  configs:
    - config_name: aeossp_standard
    - config_name: regional_coverage
    - config_name: relay_constellation
    - config_name: revisit_constellation
    - config_name: satnet
    - config_name: spot5
    - config_name: stereo_imaging
  download_size: 0
  dataset_size: 0
  license: various
language:
  - en
tags:
  - aerospace
  - satellite-scheduling
  - operations-research
  - constraint-optimization
  - astrodynamics
  - benchmark
---

# AstroReason-Bench Datasets

This is the canonical Hugging Face Dataset repository for **AstroReason-Bench**, a benchmark suite for evaluating AI agents and algorithms on space mission design and planning problems.

Each benchmark is exposed as a separate **config** (subset) within this dataset. Splits within a config map transparently to the benchmark's own dataset splits (e.g., `test`, `single_orbit`, `multi_orbit`).

## Dataset Summary

| Config | Cases | Splits | Domain |
|---|---|---|---|
| `aeossp_standard` | 5 | `test` | Agile Earth-observation satellite scheduling |
| `regional_coverage` | 5 | `test` | SAR-like regional strip-observation planning |
| `relay_constellation` | 5 | `test` | Relay satellite constellation augmentation |
| `revisit_constellation` | 5 | `test` | Constellation design for uniform target revisit |
| `satnet` | 5 | `test` | Deep Space Network (DSN) antenna scheduling |
| `spot5` | 21 | `single_orbit`, `multi_orbit`, `test` | SPOT-5 daily photograph scheduling (DCKP) |
| `stereo_imaging` | 5 | `test` | Optical stereo/tri-stereo imaging planning |

## Dataset Structure

Every example in every config follows the same schema:

```json
{
  "case_id": "case_0001",
  "split": "test",
  "benchmark": "aeossp_standard",
  "index_metadata": { ... case-specific metadata from index.json ... },
  "files": [
    {"path": "mission.yaml", "content": "..."},
    {"path": "satellites.yaml", "content": "..."},
    {"path": "tasks.yaml", "content": "..."}
  ]
}
```

- **`case_id`**: Unique identifier for the case within the benchmark.
- **`split`**: The dataset split the case belongs to.
- **`benchmark`**: The benchmark name.
- **`index_metadata`**: The case-level entry from the benchmark's `dataset/index.json` (e.g., satellite counts, task counts, horizons, thresholds, provenance).
- **`files`**: A list of all text files inside the case directory. Each entry has a `path` (relative to the case directory) and the full UTF-8 `content`.

> **Note**: Because different cases contain different filenames, `files` is stored as a uniform list of objects rather than a dictionary with dynamic keys. This ensures consistent features across splits.

## Quickstart

### Loading a single benchmark

```python
from datasets import load_dataset

# Load the aeossp_standard benchmark
ds = load_dataset("AstroReason-Bench/datasets", "aeossp_standard")
print(ds["test"][0]["case_id"])
```

### Loading a specific case's files

```python
case = ds["test"][0]
for file in case["files"]:
    print(file["path"])
    # file["content"] contains the full text of the file
```

### Iterating all configs

```python
from datasets import get_dataset_config_names

configs = get_dataset_config_names("AstroReason-Bench/datasets")
for config in configs:
    ds = load_dataset("AstroReason-Bench/datasets", config)
    for split_name, split_ds in ds.items():
        print(f"{config}/{split_name}: {len(split_ds)} cases")
```

## Benchmark Descriptions

### `aeossp_standard`
A planning-oriented agile Earth-observation satellite scheduling benchmark. Each case provides a fixed constellation of real satellites (via frozen TLEs), time-windowed point-imaging tasks, and hard constraints on observation geometry, battery state, and slew feasibility. The solver submits a schedule of `observation` actions. Metrics include completion ratio (`CR`), weighted completion ratio (`WCR`), time-averaged tardiness (`TAT`), and power consumption (`PC`).

**Case files**: `mission.yaml`, `satellites.yaml`, `tasks.yaml`

### `regional_coverage`
A SAR-like regional imaging benchmark. The solver must plan strip observations over polygonal regions of interest to maximize unique weighted coverage. Cases include real satellites with frozen TLEs, GeoJSON region definitions, and a benchmark-owned fine-grid scoring model. Hard constraints include roll-only strip geometry, same-satellite retargeting limits, battery feasibility, and optional per-region minimum coverage thresholds.

**Case files**: `manifest.json`, `satellites.yaml`, `regions.geojson`, `coverage_grid.json`

### `relay_constellation`
A partial constellation-design benchmark for relay service augmentation. Given an immutable MEO relay backbone and ground endpoints, the solver adds a bounded number of lower-altitude relay satellites and schedules ground-link and inter-satellite-link actions. The verifier scores service fraction, latency percentiles, and the number of added satellites.

**Case files**: `manifest.json`, `network.json`, `demands.json`

### `revisit_constellation`
A constellation-design and scheduling benchmark focused on revisit performance. The solver designs a satellite constellation (initial GCRF Cartesian states up to a case cap) and schedules `observation` actions to keep target revisit gaps as small as possible over a 48-hour horizon. Scoring is driven by `mean_revisit_gap_hours`, `max_revisit_gap_hours`, and `satellite_count`.

**Case files**: `assets.json`, `mission.json`

### `satnet`
A reinforcement-learning benchmark derived from NASA/JPL Deep Space Network (DSN) operations. The task is to schedule ground-station antenna tracks for interplanetary spacecraft over one-week windows, respecting precomputed view periods, setup/teardown times, maintenance windows, and non-overlap constraints. The primary metric is total scheduled communication hours.

**Case files**: `problem.json`, `maintenance.csv`, `metadata.json`

### `spot5`
A constraint optimization benchmark based on the ROADEF 2003 Challenge and CNES SPOT-5 operations. Cases are encoded in the DCKP (Disjunctively Constrained Knapsack Problem) format. The solver selects photographs and assigns cameras to maximize total profit while respecting binary/ternary disjunctive constraints and an onboard memory capacity constraint (for multi-orbit instances).

**Case files**: `<case_id>.spot`

### `stereo_imaging`
An optical satellite stereo imaging benchmark. The solver schedules timed observations from real satellites to acquire same-pass stereo or tri-stereo products over ground targets. The verifier scores `coverage_ratio` (fraction of targets with a valid stereo product) and `normalized_quality` (mean best-per-target quality based on convergence angle, overlap, and pixel scale).

**Case files**: `satellites.yaml`, `targets.yaml`, `mission.yaml`

## Data Splits and Splits Policy

- `aeossp_standard`, `regional_coverage`, `relay_constellation`, `revisit_constellation`, `satnet`, `stereo_imaging`: Currently expose a single committed split `test`.
- `spot5`: Exposes three splits:
  - `single_orbit`: 14 cases without memory constraints.
  - `multi_orbit`: 7 cases with a memory capacity of 200.
  - `test`: A 5-case sample drawn with seed 42 (overlaps with `single_orbit` and `multi_orbit`).

Future benchmark releases may add additional splits (e.g., `train`, `val`) transparently without changing the schema.

## Dataset Creation

All canonical datasets are generated or curated by the AstroReason-Bench repository. Where generators exist, they are deterministic and tied to committed `splits.yaml` contracts. Canonical cases are committed to the repository and are the source of truth for evaluation.

## Source Data

| Config | Primary Sources |
|---|---|
| `aeossp_standard` | CelesTrak TLE snapshot; GeoNames cities; Natural Earth land polygons |
| `regional_coverage` | CelesTrak TLE snapshot; GeoNames; Natural Earth |
| `relay_constellation` | Synthetic case generator with deterministic seeds |
| `revisit_constellation` | Kaggle world-cities dataset; CelesTrak TLE snapshot |
| `satnet` | Derived from NASA/JPL Deep Space Network operations research (Chien et al., 2021) |
| `spot5` | Mendeley Data DCKP abstraction (Wei & Hao, 2021) of CNES SPOT-5 ROADEF 2003 instances |
| `stereo_imaging` | Kaggle world-cities; CelesTrak TLE snapshot |

## Considerations for Using the Data

- **Algorithm-agnostic**: Benchmarks define problems and verification, not preferred solving strategies.
- **Standalone**: Each config is self-contained with no runtime dependencies on other configs.
- **No solutions included**: This dataset contains only problem instances (cases). Solutions, baselines, and leaderboards belong in downstream repositories.
- **Binary files skipped**: The upload script ingests only text-based case files. Any future binary artifacts would be excluded from this HF release.

## Licensing Information

This dataset repository aggregates multiple sources with different provenance:

- **`spot5`**: The `.spot` instances are from the Mendeley Data release (DOI: 10.17632/2kbzg9nw3b.1) and are provided under **CC BY 4.0**.
- **`satnet`**: Derived from NASA/JPL Deep Space Network operations research. Used for research and educational purposes.
- **All other benchmarks** (`aeossp_standard`, `regional_coverage`, `relay_constellation`, `revisit_constellation`, `stereo_imaging`): Original benchmark materials created by the AstroReason-Bench project.

Please cite the appropriate references when using individual benchmarks (see Citation Information).

## Citation Information

If you use this dataset suite in your research, please cite the AstroReason-Bench paper and the original benchmark sources:

### AstroReason-Bench (suite)
```
@article{wang2026astroreason,
  title={AstroReason-Bench: Evaluating Unified Agentic Planning across Heterogeneous Space Planning Problems},
  author={Wang, Weiyi and Chen, Xinchi and Gong, Jingjing and Huang, Xuanjing and Qiu, Xipeng},
  journal={arXiv preprint arXiv:2601.11354},
  year={2026}
}
```

### SatNet
```bibtex
@inproceedings{goh2021satnet,
  title={SatNet: A benchmark for satellite scheduling optimization},
  author={Goh, Edwin and Venkataram, Hamsa Shwetha and Balaji, Bharathan and Wilson, Brian D and Johnston, Mark D},
  booktitle={AAAI-22 workshop on Machine Learning for Operations Research (ML4OR)},
  year={2021}
}
```

### SPOT-5 / DCKP
```bibtex
@article{wei2023responsive,
  title={Responsive strategic oscillation for solving the disjunctively constrained knapsack problem},
  author={Wei, Zequn and Hao, Jin-Kao and Ren, Jintong and Glover, Fred},
  journal={European Journal of Operational Research},
  volume={309},
  number={3},
  pages={993--1009},
  year={2023},
  publisher={Elsevier}
}
```

## Contact and Links

- **Repository**: https://github.com/Mtrya/AstroReason-Bench
- **Issue Tracker**: https://github.com/Mtrya/AstroReason-Bench/issues
