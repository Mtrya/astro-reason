# AEOS-Bench Test Dataset

A subset of 10 test cases for evaluating Agile Earth Observation Satellite (AEOS) constellation scheduling algorithms, randomly sampled from the full AEOS-Bench test split.

[![NeurIPS 2025](https://img.shields.io/badge/NeurIPS-2025-purple)](https://neurips.cc/virtual/2025/loc/san-diego/poster/116515)
[![arXiv](https://img.shields.io/badge/arXiv-2510.26297-b31b1b.svg)](https://arxiv.org/abs/2510.26297)

---

## Overview

AEOS-Bench is the first large-scale benchmark suite for realistic AEOS constellation scheduling. This dataset contains **10 randomly selected test cases (seed=42)** for evaluation of scheduling algorithms.

---

## The Constellation Scheduling Problem

### Problem Definition

Given:
- **Satellites**: A constellation of $N_S$ satellites in Low Earth Orbit (LEO), each with:
  - Orbital parameters (semi-major axis, eccentricity, inclination, etc.)
  - Attitude control system (MRP-based with reaction wheels)
  - Power system (battery + solar panels)
  - Imaging sensor (with field-of-view constraints)

- **Tasks**: A set of $N_T$ imaging tasks, each with:
  - Ground target coordinates (latitude, longitude)
  - Release time (when task becomes available)
  - Due time (task deadline)
  - Required observation duration

**Goal**: Assign tasks to satellites over time to maximize task completion while respecting all operational constraints.

### Action Space

At each timestep $t$, the scheduler outputs an assignment vector $\mathbf{a} = [a_1, a_2, \dots, a_{N_S}]$ where:
- $a_i = 0$: Satellite $i$ powers down its sensor
- $a_i > 0$: Satellite $i$ activates sensor and reorients to service task $a_i$

The platform automatically converts high-level task assignments into low-level attitude-pointing and power commands for the physics simulator.

### Operational Constraints

1. **Dynamics**: Satellites follow orbital and attitude dynamics
2. **Field-of-View (FOV)**: Ground target must be within sensor FOV cone
3. **Continuity**: Tasks require continuous observation (no interruptions)
4. **Time Window**: Tasks must be completed between release time and due time

---

## Evaluation Metrics

Six metrics assess scheduling performance:

| Metric | Description | Formula | Goal |
|--------|-------------|---------|------|
| **CR** | Completion Rate | $\frac{\text{completed tasks}}{\text{total tasks}}$ | ↑ Maximize |
| **WCR** | Weighted Completion Rate | $\frac{\sum w_i \cdot \mathbb{1}[\text{task } i \text{ done}]}{\sum w_i}$ | ↑ Maximize |
| **PCR** | Priority Completion Rate | $\frac{\text{completed priority tasks}}{\text{total priority tasks}}$ | ↑ Maximize |
| **WPCR** | Weighted Priority CR | Weighted PCR | ↑ Maximize |
| **TAT** | Turn-Around Time | Mean time from release to completion | ↓ Minimize |
| **PC** | Power Consumption | Total energy consumed (Wh) | ↓ Minimize |

---

## Dataset Structure

```
dataset/
├── README.md                  # This file
├── BASILISK_VERSION.md        # (coming soon — see below)
├── DATASET_SELECTION.md       # (coming soon — see below)
├── cases.tar.gz               # 10 test cases (compressed)
└── cases/                     # 10 test cases (extracted)
    ├── 00025/
    │   ├── constellation.json # Satellite configuration
    │   └── taskset.json       # Imaging tasks
    ├── 00104/
    │   ├── constellation.json
    │   └── taskset.json
    └── ...
```

### Companion Documents

- **`BASILISK_VERSION.md`** — documents the Basilisk physics simulator version used to generate this dataset and explains why results may not be directly comparable to the original AEOS-Bench paper. Will be released once ongoing experiments are finalized.
- **`DATASET_SELECTION.md`** — explains the test case selection methodology (random sampling with seed=42). Will be released alongside `BASILISK_VERSION.md`.

### File Format

#### `constellation.json`
Contains satellite asset definitions:
```json
{
  "satellites": {
    "sat_0": {
      "orbit": {
        "a": 6878137.0,        // Semi-major axis (m)
        "e": 0.001,            // Eccentricity
        "i": 98.2,             // Inclination (deg)
        "omega": 45.0,         // Argument of periapsis (deg)
        "Omega": 0.0,          // RAAN (deg)
        "f": 0.0               // True anomaly (deg)
      },
      "mass": 500.0,           // Mass (kg)
      "inertia": [...],        // Inertia tensor (kg·m²)
      "reaction_wheels": [...],// RW configuration
      "solar_panel": {...},    // Power generation
      "battery": {...},        // Energy storage
      "sensor": {...}          // Imaging payload
    },
    ...
  }
}
```

#### `taskset.json`
Contains imaging task definitions:
```json
{
  "tasks": {
    "task_0": {
      "target": {
        "latitude": 34.05,      // Target latitude (deg)
        "longitude": -118.25    // Target longitude (deg)
      },
      "release_time": 0,        // When task becomes available (sec)
      "due_time": 3600,         // Task deadline (sec)
      "duration": 30,           // Required observation time (sec)
      "priority": 1,            // Task priority
      "weight": 1.0             // Task weight
    },
    ...
  }
}
```

---

## Usage

### Extract the Dataset

```bash
tar -xzf dataset/cases.tar.gz -C dataset/
```

### Load a Test Case

```python
import json
from pathlib import Path

# Load case 00025
case_id = 25
case_dir = Path('dataset/cases') / f'{case_id:05d}'

with open(case_dir / 'constellation.json') as f:
    constellation = json.load(f)

with open(case_dir / 'taskset.json') as f:
    taskset = json.load(f)

print(f"Satellites: {len(constellation['satellites'])}")
print(f"Tasks: {len(taskset['tasks'])}")
```

---

## Notes

⚠️ **Test Set Selection**: See `DATASET_SELECTION.md` for details (coming soon).

⚠️ **Basilisk Version**: See `BASILISK_VERSION.md` for details (coming soon).

We're still running experiments to characterize observations related to **Test Set Selection** and **Basilisk Version**. `DATASET_SELECTION.md` and `BASILISK_VERSION.md` will be released once those experiments are complete.