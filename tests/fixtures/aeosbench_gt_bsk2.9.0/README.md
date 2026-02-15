# AEOS-Bench Ground Truth Fixtures

This directory contains ground truth fixtures for the AEOS-Bench satellite constellation scheduling benchmark. Each fixture represents a complete scheduling scenario with case data, generated solutions, computed metrics, and dynamics curves.

## Overview

A **fixture** is a tuple of `(case, solution, metrics, curves)` that captures a complete satellite constellation scheduling scenario:

- **Case**: The problem instance (satellite constellation + task set)
- **Solution**: The scheduling decisions (which satellite does which task at each timestep)
- **Metrics**: Aggregated performance metrics (completion rates, turnaround time, power consumption)

These fixtures serve as ground truth for verifying the correctness of AEOS-Bench custom verifier implementations.

## Generation Methodology

### Case Selection

Fixtures are drawn from [the official AEOS-Bench dataset](https://huggingface.co/datasets/MessianX/AEOS-dataset) across four splits:

| Split | Count | Description |
|-------|-------|-------------|
| train | 8 | Training distribution cases |
| val_seen | 4 | Validation with seen constellations |
| val_unseen | 4 | Validation with unseen constellations |
| test | 4 | Test set cases |

Cases are selected randomly (seed=42) from available case IDs (00000-09999).

### Solution Generation

Solutions are generated using the **OptimalAlgorithm** (see [the official AEOS-Bench](https://github.com/buaa-colalab/AEOSBench) repository for detail), which implements a greedy nearest-neighbor heuristic with visibility constraints:

1. **Visibility Check**: A satellite can only work on a task if:
   - The task is within line-of-sight (geometric visibility)
   - The off-nadir angle is ≤ 60° (sensor pointing constraint)
   - The task sensor type matches the satellite sensor type

2. **Assignment Strategy**:
   - For each satellite, find the nearest ongoing task satisfying visibility constraints
   - Attempt to maintain task continuity (stick with previous assignment if still valid)
   - Toggle sensors on/off based on assignments
   - Guide satellite attitude toward assigned task locations

3. **Simulation**: The algorithm runs for 3600 timesteps (1 second intervals, 1 hour mission) using Basilisk astrodynamics simulator.

### Metrics Computation

After solution generation, the solution is replayed through the Basilisk simulator to compute metrics:

- **CR** (Completion Rate): Fraction of tasks completed successfully
- **WCR** (Weighted Completion Rate): Fraction of task duration completed
- **PCR** (Partial Completion Rate): Average progress on incomplete tasks
- **WPCR** (Weighted Partial Completion Rate): Weighted average progress
- **TAT** (Turn-Around Time): Average time from task release to completion
- **PC** (Power Consumption): Total energy consumed by sensors

## Directory Structure

```
fixtures/
├── index.json                 # Master index of all fixtures
├── cases/                     # Problem instances
│   ├── 00000/
│   │   ├── constellation.json # Satellite orbits, sensors, resources
│   │   └── taskset.json       # Tasks with release/due times, locations
│   └── ...
├── solutions/                 # Scheduling solutions
│   ├── 00000.json            # Per-satellite task assignments
│   └── ...
└── metrics/                   # Performance metrics
    ├── 00000.json            # CR, WCR, PCR, WPCR, TAT, PC
    └── ...
```

## File Formats

### index.json

```json
{
  "num_fixtures": 20,
  "fixtures": [
    {
      "case_id": 0,
      "split": "test",
      "algorithm": "optimal"
    },
    ...
  ]
}
```

### constellation.json

Contains satellite orbital elements, sensors, batteries, and reaction wheels.

### taskset.json

```json
{
  "tasks": [
    {
      "id": 0,
      "release_time": 0,
      "due_time": 1200,
      "duration": 10,
      "coordinate": [34.0522, -118.2437],
      "sensor_type": 0
    },
    ...
  ]
}
```

### solutions/00000.json

```json
{
  "case_id": 0,
  "algorithm": "OptimalAlgorithm",
  "assignments": {
    "0": [-1, -1, 5, 5, 5, -1, ...],
    "1": [3, 3, 3, -1, -1, 8, ...],
    ...
  }
}
```

Each satellite has an array of length 3601 (timesteps 0-3600), where:
- `-1` = idle
- `N` = assigned to task ID N

### metrics/00000.json

```json
{
  "case_id": 0,
  "algorithm": "OptimalAlgorithm",
  "metrics": {
    "CR": 0.8532,
    "WCR": 0.8234,
    "PCR": 0.1523,
    "WPCR": 0.1821,
    "TAT": 452.34,
    "PC": 12500.0
  },
  "num_succeeded": 42,
  "num_failed": 8,
  "num_total": 50
}
```

### curves/00000.json

```json
{
  "case_id": 0,
  "algorithm": "OptimalAlgorithm",
  "num_timesteps": 3601,
  "satellites": {
    "0": {
      "attitude_mrp": [[0.0, 0.0, 0.0], ...],
      "position_eci": [[x, y, z], ...],
      "velocity_eci": [[vx, vy, vz], ...],
      "battery_level": [100.0, 99.8, ...],
      "sensor_enabled": [false, false, true, ...],
      "reaction_wheel_omega": [[w1, w2, w3], ...],
      "reaction_wheel_torque": [[t1, t2, t3], ...],
      "assignment": [-1, -1, 5, ...]
    },
    ...
  },
  "tasks": {
    "visibility": {
      "0": [[true, false, ...], ...],
      ...
    },
    "progress": [[0, 0, 1, ...], ...]
  }
}
```

## Usage

### Loading a Fixture

```python
import json
from pathlib import Path

# Load via index
with open("fixtures/index.json") as f:
    index = json.load(f)

case_id = index["fixtures"][0]["case_id"]

# Load components
with open(f"fixtures/cases/{case_id:05d}/constellation.json") as f:
    constellation = json.load(f)

with open(f"fixtures/cases/{case_id:05d}/taskset.json") as f:
    taskset = json.load(f)

with open(f"fixtures/solutions/{case_id:05d}.json") as f:
    solution = json.load(f)

with open(f"fixtures/metrics/{case_id:05d}.json") as f:
    metrics = json.load(f)

with open(f"fixtures/curves/{case_id:05d}.json") as f:
    curves = json.load(f)
```

### Replaying a Solution

See `ReplayFixtureAlgorithm` in the appendix for replaying solutions through the Basilisk simulator to verify metrics or extract additional data.

## Technical Details

### Simulation Parameters

- **Timestep**: 1 second (`INTERVAL = 1.0`)
- **Mission Duration**: 3600 seconds (`MAX_TIME_STEP = 3600`)
- **Earth Radius**: 6,378,136.6 meters (`RADIUS_EARTH`)
- **Max Off-Nadir Angle**: 60° (`MAX_OFF_NADIR_ANGLE = π/3`)
- **Simulation Framework**: NASA Basilisk astrodynamics simulator

### Visibility Constraints

A satellite at position `r_sat` can observe a task at position `r_task` if:

1. Distance constraint: `|r_sat - r_task| >= R_EARTH` (above horizon)
2. Angle constraint: `cos(θ) > cos(60°)` where:
   ```
   cos(θ) = (|r_task - r_sat|² + |r_sat|² - R_EARTH²) / (2 × |r_task - r_sat| × |r_sat|)
   ```

### Coordinate Systems

- **ECEF**: Earth-Centered Earth-Fixed (rotates with Earth)
- **ECI**: Earth-Centered Inertial (fixed in space)
- **LLA**: Latitude/Longitude/Altitude (ground locations)

Task coordinates are specified as [latitude, longitude] and converted to ECEF/ECI using the current Earth rotation matrix from SPICE.

## Appendix: Source Code

### generate_fixtures.py

```python
#!/usr/bin/env python3
"""Generate ground truth fixtures for AEOS-Bench verifier testing.

This script generates 20 fixtures of (case, solution, metrics, curves) tuples
using the official Basilisk astrodynamics simulation.

Usage:
    python generate_fixtures.py [--output fixtures] [--num-fixtures 20]
"""

from __future__ import annotations

import argparse
import json
import math
import random
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import torch

from constellation.algorithms import (
    OptimalAlgorithm,
    # RandomValidAlgorithm,
    ReplayFixtureAlgorithm,
)
from constellation.callbacks import ComposedCallback
from constellation.constants import MAX_TIME_STEP, RADIUS_EARTH
from constellation.controller import Controller
from constellation.data import Constellation, TaskSet
from constellation.environments import BasiliskEnvironment
from constellation.evaluators import (
    CompletionRateEvaluator,
    PowerUsageEvaluator,
    TurnAroundTimeEvaluator,
)
from constellation.task_managers import TaskManager


# Fixture selection strategy
FIXTURE_CONFIG = {
    "train": 8,
    "val_seen": 4,
    "val_unseen": 4,
    "test": 4,
}

# Algorithm distribution (must sum to num_fixtures)
ALGORITHM_DISTRIBUTION = {
    "optimal":20,
    # "random_valid": 0,
}


def get_case_path(case_id: int, split: str) -> tuple[Path, Path]:
    """Get paths to constellation and taskset files for a case."""
    case_dir = f"{case_id // 1000:02d}"
    constellation_path = (
        Path("data") / "constellations" / split / case_dir / f"{case_id:05d}.json"
    )
    taskset_path = Path("data") / "tasksets" / split / case_dir / f"{case_id:05d}.json"
    return constellation_path, taskset_path


def select_cases(num_fixtures: int = 20) -> list[tuple[int, str]]:
    """Select case IDs from each split.

    Returns list of (case_id, split) tuples.
    """
    cases = []
    rng = random.Random(42)  # Fixed seed for reproducibility

    for split, count in FIXTURE_CONFIG.items():
        # Find available cases in this split
        split_dir = Path("data") / "constellations" / split
        if not split_dir.exists():
            print(f"Warning: {split_dir} does not exist, skipping {split}")
            continue

        available_cases = []
        for subdir in split_dir.iterdir():
            if subdir.is_dir():
                for case_file in subdir.glob("*.json"):
                    case_id = int(case_file.stem)
                    available_cases.append(case_id)

        if len(available_cases) < count:
            print(f"Warning: Only {len(available_cases)} cases available in {split}, need {count}")
            selected = available_cases
        else:
            selected = rng.sample(available_cases, count)

        cases.extend([(case_id, split) for case_id in sorted(selected)])

    return cases[:num_fixtures]


def load_case(case_id: int, split: str) -> tuple[Constellation, TaskSet]:
    """Load constellation and taskset for a given case."""
    constellation_path, taskset_path = get_case_path(case_id, split)

    if not constellation_path.exists():
        raise FileNotFoundError(f"Constellation not found: {constellation_path}")
    if not taskset_path.exists():
        raise FileNotFoundError(f"Taskset not found: {taskset_path}")

    constellation = Constellation.load(str(constellation_path))
    taskset = TaskSet.load(str(taskset_path))

    return constellation, taskset


def generate_solution(
    case_id: int,
    constellation: Constellation,
    taskset: TaskSet,
    algorithm_type: str,
    seed: int | None = None,
) -> dict[str, Any]:
    """Generate solution using specified algorithm."""
    environment = BasiliskEnvironment(constellation=constellation, all_tasks=taskset)
    task_manager = TaskManager(timer=environment.timer, taskset=taskset)

    if algorithm_type == "optimal":
        algorithm = OptimalAlgorithm(timer=environment.timer)
    elif algorithm_type == "random_valid":
        algorithm = RandomValidAlgorithm(timer=environment.timer, seed=seed)
    else:
        raise ValueError(f"Unknown algorithm type: {algorithm_type}")

    algorithm.prepare(environment, task_manager)

    # Capture assignments at each step
    assignments: dict[int, list[int]] = {sat_id: [] for sat_id in constellation.keys()}

    controller = Controller(
        name=f"fixture_{case_id}",
        environment=environment,
        task_manager=task_manager,
        callbacks=ComposedCallback(callbacks=[]),
    )

    for step in range(MAX_TIME_STEP + 1):
        actions, assignment = algorithm.step(
            task_manager.ongoing_tasks,
            environment.get_constellation(),
            environment.get_earth_rotation(),
        )
        controller.step(actions, assignment)

        for sat_idx, sat_id in enumerate(sorted(constellation.keys())):
            assignments[sat_id].append(assignment[sat_idx])

    return {
        "case_id": case_id,
        "algorithm": algorithm.__class__.__name__,
        "assignments": assignments,
    }


def replay_and_extract(
    constellation: Constellation,
    taskset: TaskSet,
    solution: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Replay solution and extract both metrics and curves in a single run.

    This combines metrics computation and curve extraction to minimize
    expensive Basilisk simulation runs.
    """
    environment = BasiliskEnvironment(constellation=constellation, all_tasks=taskset)
    task_manager = TaskManager(timer=environment.timer, taskset=taskset)

    evaluators = [
        CompletionRateEvaluator(),
        TurnAroundTimeEvaluator(),
        PowerUsageEvaluator(),
    ]

    controller = Controller(
        name="replay",
        environment=environment,
        task_manager=task_manager,
        callbacks=ComposedCallback(callbacks=evaluators),
    )

    replay_algorithm = ReplayFixtureAlgorithm(
        timer=environment.timer,
        assignments=solution["assignments"],
    )
    replay_algorithm.prepare(environment, task_manager)

    # Initialize curve storage
    curves_data: dict[int, dict[str, list]] = {
        sat_id: {
            "attitude_mrp": [],
            "position_eci": [],
            "velocity_eci": [],
            "battery_level": [],
            "sensor_enabled": [],
            "reaction_wheel_omega": [],
            "reaction_wheel_torque": [],
            "assignment": [],
        }
        for sat_id in constellation.keys()
    }

    # Task progress tracking
    task_progress: list[list[int]] = [[] for _ in range(len(taskset))]

    # Visibility tracking
    visibility_per_task: dict[int, list[list[bool]]] = {
        task.id_: [] for task in taskset
    }

    basilisk_env = environment
    sat_ids = sorted(constellation.keys())

    # Initialize callbacks
    controller.callbacks.before_run()

    for step in range(MAX_TIME_STEP + 1):
        actions, assignment = replay_algorithm.step(
            task_manager.ongoing_tasks,
            environment.get_constellation(),
            environment.get_earth_rotation(),
        )
        controller.step(actions, assignment)

        # Extract satellite states
        for sat_idx, sat_id in enumerate(sat_ids):
            satellite = basilisk_env._satellites[sat_idx]
            state = satellite.spacecraft_state

            curves_data[sat_id]["attitude_mrp"].append(list(state.sigma_BN))
            curves_data[sat_id]["position_eci"].append(list(state.r_CN_N))
            curves_data[sat_id]["velocity_eci"].append(list(state.v_CN_N))
            curves_data[sat_id]["battery_level"].append(
                satellite.battery.batPowerOutMsg.read().storageLevel
            )
            curves_data[sat_id]["sensor_enabled"].append(
                satellite.power_sink.powerStatus == 1
            )

            # Reaction wheel states
            rw_states = satellite._rw_state_effector.rwSpeedOutMsg.read()
            omega = list(rw_states.wheelSpeeds)
            curves_data[sat_id]["reaction_wheel_omega"].append(omega)

            rw_torques = satellite._rw_motor_torque.rwMotorTorqueOutMsg.read()
            torque = list(rw_torques.motorTorque)
            curves_data[sat_id]["reaction_wheel_torque"].append(torque)

            curves_data[sat_id]["assignment"].append(assignment[sat_idx])

        # Record task progress
        for task_idx, progress in enumerate(task_manager.progress.tolist()):
            task_progress[task_idx].append(int(progress))

        # Record visibility for each task
        is_visible = controller.memo.get("is_visible", torch.zeros(len(sat_ids), len(taskset)))
        for task_idx, task in enumerate(taskset):
            vis_per_sat = [bool(is_visible[sat_idx][task_idx]) for sat_idx in range(len(sat_ids))]
            visibility_per_task[task.id_].append(vis_per_sat)

    # Finalize callbacks
    controller.callbacks.after_run()

    metrics = {
        "case_id": solution["case_id"],
        "algorithm": solution["algorithm"],
        "metrics": controller.memo.get("metrics", {}),
        "num_succeeded": task_manager.num_succeeded_tasks,
        "num_failed": len(taskset) - task_manager.num_succeeded_tasks,
        "num_total": len(taskset),
    }

    curves = {
        "case_id": solution["case_id"],
        "algorithm": solution["algorithm"],
        "num_timesteps": MAX_TIME_STEP + 1,
        "satellites": curves_data,
        "tasks": {
            "visibility": {str(k): v for k, v in visibility_per_task.items()},
            "progress": task_progress,
        },
    }

    return metrics, curves


def save_case(
    case_id: int,
    constellation: Constellation,
    taskset: TaskSet,
    output_dir: Path,
) -> None:
    """Save case files to output directory."""
    case_dir = output_dir / "cases" / f"{case_id:05d}"
    case_dir.mkdir(parents=True, exist_ok=True)

    # Save constellation
    constellation_data = constellation.to_dict()
    with open(case_dir / "constellation.json", "w") as f:
        json.dump(constellation_data, f, indent=2)

    # Save taskset
    taskset_data = {"tasks": taskset.to_dicts()}
    with open(case_dir / "taskset.json", "w") as f:
        json.dump(taskset_data, f, indent=2)


def save_solution(
    case_id: int,
    solution: dict[str, Any],
    output_dir: Path,
) -> None:
    """Save solution to output directory."""
    solutions_dir = output_dir / "solutions"
    solutions_dir.mkdir(parents=True, exist_ok=True)

    # Minimal format: only case_id, algorithm, assignments
    minimal_solution = {
        "case_id": solution["case_id"],
        "algorithm": solution["algorithm"],
        "assignments": solution["assignments"],
    }

    with open(solutions_dir / f"{case_id:05d}.json", "w") as f:
        json.dump(minimal_solution, f, indent=2)


def save_metrics(
    case_id: int,
    metrics: dict[str, Any],
    output_dir: Path,
) -> None:
    """Save metrics to output directory."""
    metrics_dir = output_dir / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)

    with open(metrics_dir / f"{case_id:05d}.json", "w") as f:
        json.dump(metrics, f, indent=2)


def save_curves(
    case_id: int,
    curves: dict[str, Any],
    output_dir: Path,
) -> None:
    """Save curves to output directory."""
    curves_dir = output_dir / "curves"
    curves_dir.mkdir(parents=True, exist_ok=True)

    with open(curves_dir / f"{case_id:05d}.json", "w") as f:
        json.dump(curves, f, indent=2)


def save_index(
    fixtures: list[dict[str, Any]],
    output_dir: Path,
) -> None:
    """Save index file with metadata for all fixtures."""
    index = {
        "num_fixtures": len(fixtures),
        "fixtures": fixtures,
    }

    with open(output_dir / "index.json", "w") as f:
        json.dump(index, f, indent=2)


def generate_fixtures(
    num_fixtures: int = 20,
    output_dir: str = "fixtures",
) -> None:
    """Generate complete fixture set."""
    output_path = Path(output_dir)

    # Clean and create output directory
    if output_path.exists():
        shutil.rmtree(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    # Select cases
    cases = select_cases(num_fixtures)
    print(f"Selected {len(cases)} cases: {cases}")

    # Assign algorithms
    algorithms = []
    for algo_type, count in ALGORITHM_DISTRIBUTION.items():
        algorithms.extend([algo_type] * count)
    algorithms = algorithms[:num_fixtures]
    random.Random(42).shuffle(algorithms)

    fixtures = []

    for i, ((case_id, split), algorithm_type) in enumerate(zip(cases, algorithms)):
        print(f"\n[{i+1}/{num_fixtures}] Processing case {case_id} from {split} with {algorithm_type}")

        try:
            # Load case
            constellation, taskset = load_case(case_id, split)
            print(f"  Loaded: {len(constellation)} satellites, {len(taskset)} tasks")

            # Generate solution
            print(f"  Generating solution...")
            solution = generate_solution(
                case_id, constellation, taskset, algorithm_type, seed=42 + i
            )

            # Replay solution to compute metrics and extract curves
            print(f"  Replaying solution to compute metrics and extract curves...")
            metrics, curves = replay_and_extract(constellation, taskset, solution)
            print(f"    CR: {metrics['metrics'].get('CR', 0):.4f}")

            # Save all data
            print(f"  Saving files...")
            save_case(case_id, constellation, taskset, output_path)
            save_solution(case_id, solution, output_path)
            save_metrics(case_id, metrics, output_path)
            save_curves(case_id, curves, output_path)

            fixtures.append({
                "case_id": case_id,
                "split": split,
                "algorithm": algorithm_type,
            })

            print(f"  Done!")

        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()

    # Save index
    save_index(fixtures, output_path)
    print(f"\nGenerated {len(fixtures)} fixtures in {output_dir}/")
    print(f"  - cases/: {len(fixtures)} cases")
    print(f"  - solutions/: {len(fixtures)} solutions")
    print(f"  - metrics/: {len(fixtures)} metrics")
    print(f"  - curves/: {len(fixtures)} curves")
    print(f"  - index.json: master index")


def main():
    parser = argparse.ArgumentParser(
        description="Generate ground truth fixtures for AEOS-Bench"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="fixtures",
        help="Output directory for fixtures",
    )
    parser.add_argument(
        "--num-fixtures",
        type=int,
        default=20,
        help="Number of fixtures to generate",
    )
    args = parser.parse_args()

    generate_fixtures(
        num_fixtures=args.num_fixtures,
        output_dir=args.output,
    )


if __name__ == "__main__":
    main()
```

### replay_fixture.py

```python
__all__ = [
    'ReplayFixtureAlgorithm',
]

import torch

from ..data import Action, Actions, Constellation, TaskSet
from ..environments import BaseEnvironment
from ..task_managers import TaskManager
from .base import BaseAlgorithm


class ReplayFixtureAlgorithm(BaseAlgorithm):
    """Replay algorithm for fixture generation and verification.

    Replays assignments from a simple dict format without requiring
    trajectory files or time model dependencies.

    Args:
        assignments: Dict mapping satellite_id -> list of task assignments
                     per timestep. -1 means idle.
    """

    def __init__(
        self,
        *args,
        assignments: dict[int, list[int]],
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._assignments = assignments
        self._satellite_ids = sorted(assignments.keys())

    def prepare(
        self,
        environment: BaseEnvironment,
        task_manager: TaskManager,
    ) -> None:
        self._task_manager = task_manager

    def step(
        self,
        tasks: TaskSet,
        constellation: Constellation,
        earth_rotation: torch.Tensor,
    ) -> tuple[Actions, list[int]]:
        """Return actions and assignment for current timestep."""
        time = self._timer.time

        # Get assignments for current timestep for each satellite
        task_ids = []
        target_locations = []

        task_id_to_task = {task.id_: task for task in tasks}

        for sat_id in self._satellite_ids:
            assignment_list = self._assignments[sat_id]
            if time < len(assignment_list):
                task_id = assignment_list[time]
            else:
                task_id = -1

            task_ids.append(task_id)

            # Get target location if task is valid and ongoing
            if task_id in task_id_to_task:
                target_locations.append(task_id_to_task[task_id].coordinate)
            else:
                target_locations.append(None)

        # Determine toggles based on current sensor state vs desired assignment
        toggles = []
        for task_id, satellite in zip(task_ids, constellation.sort()):
            # Toggle if:
            # - task_id == -1 and sensor is enabled (need to turn off)
            # - task_id != -1 and sensor is disabled (need to turn on)
            should_be_enabled = task_id != -1
            is_enabled = satellite.sensor.enabled
            toggles.append(should_be_enabled != is_enabled)

        actions = Actions(
            Action(toggle, target_location)
            for toggle, target_location in zip(toggles, target_locations)
        )

        return actions, task_ids
```
