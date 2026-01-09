"""Common interface and utilities for baseline algorithms."""

import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Set, Callable
from datetime import datetime, timedelta

from planner.scenario import Scenario
from planner.models import PlannerAccessWindow, PlannerAction, ValidationError, ConflictError

logger = logging.getLogger(__name__)


@dataclass
class BaselineResult:
    success: bool
    elapsed_seconds: float
    actions_count: int
    error: str | None = None


def load_scenario(case_path: Path) -> Scenario:
    """Load scenario from case directory."""
    return Scenario(
        satellite_file=str(case_path / "satellites.yaml"),
        target_file=str(case_path / "targets.yaml"),
        station_file=str(case_path / "stations.yaml"),
        plan_file=str(case_path / "initial_plan.json"),
    )



def window_to_action_dict(
    window: PlannerAccessWindow,
    use_middle_minutes: float | None = None,
) -> Dict[str, Any]:
    """Convert a window to an action dict for stage_action().
    
    Args:
        window: Access window to convert
        use_middle_minutes: If set, use the middle N minutes of the window.
                           Otherwise use full window.
    
    Returns:
        Action dict ready for stage_action()
    """
    start = window.start
    end = window.end
    
    if use_middle_minutes is not None:
        duration = (end - start).total_seconds()
        target_duration = use_middle_minutes * 60
        
        if duration > target_duration:
            midpoint = start + (end - start) / 2
            half_dur = timedelta(seconds=target_duration / 2)
            start = midpoint - half_dur
            end = midpoint + half_dur
    
    action_dict: Dict[str, Any] = {
        "satellite_id": window.satellite_id,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
    }
    
    if window.target_id:
        action_dict["type"] = "observation"
        action_dict["target_id"] = window.target_id
    elif window.strip_id:
        action_dict["type"] = "observation"
        action_dict["strip_id"] = window.strip_id
    elif window.station_id:
        action_dict["type"] = "downlink"
        action_dict["station_id"] = window.station_id
    elif window.peer_satellite_id:
        action_dict["type"] = "intersatellite_link"
        action_dict["peer_satellite_id"] = window.peer_satellite_id
    else:
        raise ValueError("Window has no valid target/station/peer")
    
    return action_dict


def try_stage_action(scenario: Scenario, action_dict: Dict[str, Any]) -> bool:
    """Try to stage an action, returning True if successful."""
    try:
        scenario.stage_action(action_dict)
        return True
    except Exception:
        return False


def compute_windows(
    scenario: Scenario,
    benchmark_type: str,
    case_path: Path,
    max_observation_windows: int | None = None,
    max_downlink_windows: int | None = None,
    max_isl_windows: int | None = None,
    shuffle_seed: int | None = None,
) -> List[PlannerAccessWindow]:
    """Compute all windows using benchmark-specific logic.

    Note: Different benchmarks have different compute_all_windows signatures.
    Most benchmarks only need the scenario, but regional_coverage also needs
    case_path to load region definitions from the case directory.

    Args:
        scenario: Loaded scenario object
        benchmark_type: Type of benchmark (determines which windows to compute)
        case_path: Path to case directory (needed for some benchmarks)
        max_observation_windows: Maximum observation windows to compute (None for unlimited)
        max_downlink_windows: Maximum downlink windows to compute (None for unlimited)
        max_isl_windows: Maximum ISL windows to compute (None for unlimited, latency_optimization only)
        shuffle_seed: Random seed for shuffling entities (None for no shuffle)

    Returns:
        List of access windows for the specified benchmark

    Raises:
        ValueError: If benchmark_type is unknown
    """
    if benchmark_type == "revisit_optimization":
        from benchmark.scenarios.revisit_optimization.all_windows import compute_all_windows

        return compute_all_windows(
            scenario,
            max_observation_windows=max_observation_windows,
            max_downlink_windows=max_downlink_windows,
            shuffle_seed=shuffle_seed,
        )
    if benchmark_type == "stereo_imaging":
        from benchmark.scenarios.stereo_imaging.all_windows import compute_all_windows

        return compute_all_windows(
            scenario,
            max_observation_windows=max_observation_windows,
            max_downlink_windows=max_downlink_windows,
            shuffle_seed=shuffle_seed,
        )
    if benchmark_type == "latency_optimization":
        from benchmark.scenarios.latency_optimization.all_windows import compute_all_windows

        return compute_all_windows(
            scenario,
            max_observation_windows=max_observation_windows,
            max_downlink_windows=max_downlink_windows,
            max_isl_windows=max_isl_windows,
            shuffle_seed=shuffle_seed,
        )
    if benchmark_type == "regional_coverage":
        from benchmark.scenarios.regional_coverage.all_windows import compute_all_windows

        return compute_all_windows(
            scenario,
            case_path,
            max_observation_windows=max_observation_windows,
            max_downlink_windows=max_downlink_windows,
            shuffle_seed=shuffle_seed,
        )

    raise ValueError(f"Unknown benchmark type: {benchmark_type}")


def evaluate_state_fitness(
    state: Set[int],
    windows: List[PlannerAccessWindow],
    case_path: Path,
    fitness_fn: Callable[[str, str], float],
    benchmark_type: str,
    temp_plan_path: str | None = None,
) -> float:
    """Evaluate fitness of a state (set of window indices) efficiently.

    Args:
        state: Set of window indices to include in plan
        windows: List of all available windows
        case_path: Path to case directory
        fitness_fn: Fitness function that takes (plan_path, case_path)
        benchmark_type: Type of benchmark
        temp_plan_path: Optional path to reuse for temporary plan file.
                       If None, creates a new temp file.

    Returns:
        Fitness score (0.0 if plan is invalid)
    """
    scenario = load_scenario(case_path)
    compute_windows(scenario, benchmark_type, case_path)

    for idx in sorted(state):
        if idx >= len(windows):
            continue
        window = windows[idx]
        use_middle = 5.0 if window.target_id or window.strip_id else None
        action_dict = window_to_action_dict(window, use_middle_minutes=use_middle)
        try_stage_action(scenario, action_dict)

    if temp_plan_path is None:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_plan_path = f.name
        should_delete = True
    else:
        should_delete = False

    try:
        result = scenario.commit_plan(temp_plan_path)

        if not result.valid:
            return 0.0

        fitness = fitness_fn(temp_plan_path, str(case_path))
        return fitness
    finally:
        if should_delete:
            Path(temp_plan_path).unlink(missing_ok=True)
