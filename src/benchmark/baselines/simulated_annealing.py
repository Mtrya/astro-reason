"""Simulated Annealing baseline scheduler.

Purpose: Probabilistic local search for escaping local minima.
Strategy: Binary mask state, neighbor generation (add/remove/swap), Metropolis criterion.
"""

import logging
import random
import math
import time
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, List, Set, Callable

from .base import (
    BaselineResult,
    load_scenario,
    window_to_action_dict,
    try_stage_action,
    evaluate_state_fitness,
    compute_windows,
)
from planner.models import PlannerAccessWindow

if TYPE_CHECKING:
    from planner.scenario import Scenario

logger = logging.getLogger(__name__)


MAX_WINDOWS = 5000
DEFAULT_SEED = 42
INITIAL_TEMP = 1.0
COOLING_RATE = 0.995
MIN_TEMP = 0.01


def run(
    case_path: Path,
    output_path: Path,
    timeout: int = 300,
    benchmark_type: str = "revisit_optimization",
    seed: int = DEFAULT_SEED,
    max_windows: int = MAX_WINDOWS,
    initial_temp: float = INITIAL_TEMP,
    cooling_rate: float = COOLING_RATE,
    min_temp: float = MIN_TEMP,
) -> BaselineResult:
    """Run simulated annealing baseline algorithm.

    Args:
        case_path: Path to case directory
        output_path: Path to save plan.json
        timeout: Maximum execution time in seconds
        benchmark_type: Type of benchmark
        seed: Random seed for reproducibility
        max_windows: Maximum number of windows to consider
        initial_temp: Initial temperature for annealing
        cooling_rate: Temperature cooling rate per iteration
        min_temp: Minimum temperature before stopping

    Returns:
        BaselineResult with success status, elapsed time, and action count
    """
    start_time = time.time()
    random.seed(seed)
    logger.info(f"Starting SA: benchmark={benchmark_type}, max_windows={max_windows}, temp={initial_temp}, cooling={cooling_rate}")

    try:
        scenario = load_scenario(case_path)
        windows = compute_windows(scenario, benchmark_type, case_path)
        logger.info(f"Computed {len(windows)} windows")

        if len(windows) > max_windows:
            windows = random.sample(windows, max_windows)
            logger.info(f"Sampled {max_windows} windows")

        fitness_fn = _get_fitness_fn(benchmark_type)

        # Create persistent temp file for fitness evaluations
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_plan_path = f.name

        try:
            current_state = _initialize_greedy(scenario, windows)
            current_fitness = evaluate_state_fitness(
                current_state, windows, case_path, fitness_fn, benchmark_type, temp_plan_path
            )
            logger.info(f"Initial greedy solution: {len(current_state)} actions, fitness={current_fitness:.4f}")

            best_state = current_state.copy()
            best_fitness = current_fitness

            temperature = initial_temp
            iteration = 0

            while temperature > min_temp and time.time() - start_time < timeout:
                neighbor = _generate_neighbor(current_state, len(windows))
                neighbor_fitness = evaluate_state_fitness(
                    neighbor, windows, case_path, fitness_fn, benchmark_type, temp_plan_path
                )

                delta = neighbor_fitness - current_fitness

                if delta > 0 or random.random() < math.exp(delta / temperature):
                    current_state = neighbor
                    current_fitness = neighbor_fitness

                    if current_fitness > best_fitness:
                        best_state = current_state.copy()
                        best_fitness = current_fitness
                        logger.info(f"New best at iter {iteration}: fitness={best_fitness:.4f}, temp={temperature:.6f}")

                temperature *= cooling_rate
                iteration += 1

                if iteration % 100 == 0:
                    logger.debug(f"Iter {iteration}: temp={temperature:.6f}, current_fitness={current_fitness:.4f}, best={best_fitness:.4f}")

            logger.info(f"SA completed: {iteration} iterations, best_fitness={best_fitness:.4f}")
        finally:
            Path(temp_plan_path).unlink(missing_ok=True)

        scenario = load_scenario(case_path)
        _compute_windows(scenario, benchmark_type, case_path)
        actions_count = _apply_state(best_state, windows, scenario)
        result = scenario.commit_plan(str(output_path))
        logger.info(f"Final plan: actions={actions_count}, valid={result.valid}, elapsed={time.time()-start_time:.2f}s")

        return BaselineResult(
            success=result.valid,
            elapsed_seconds=time.time() - start_time,
            actions_count=actions_count,
        )

    except Exception as e:
        logger.error(f"SA failed: {e}", exc_info=True)
        return BaselineResult(
            success=False,
            elapsed_seconds=time.time() - start_time,
            actions_count=0,
            error=str(e),
        )


def _get_fitness_fn(benchmark_type: str) -> Callable[[str, str], float]:
    """Get benchmark-specific fitness function."""
    if benchmark_type == "revisit_optimization":
        from benchmark.scenarios.revisit_optimization.fitness import compute_fitness
    elif benchmark_type == "stereo_imaging":
        from benchmark.scenarios.stereo_imaging.fitness import compute_fitness
    elif benchmark_type == "latency_optimization":
        from benchmark.scenarios.latency_optimization.fitness import compute_fitness
    elif benchmark_type == "regional_coverage":
        from benchmark.scenarios.regional_coverage.fitness import compute_fitness
    else:
        raise ValueError(f"Unknown benchmark type: {benchmark_type}")
    return compute_fitness


def _initialize_greedy(scenario: "Scenario", windows: List[PlannerAccessWindow]) -> Set[int]:
    """Initialize with a greedy solution."""
    state = set()
    for i, window in enumerate(windows[:500]):
        use_middle = 5.0 if window.target_id or window.strip_id else None
        action_dict = window_to_action_dict(window, use_middle_minutes=use_middle)
        if try_stage_action(scenario, action_dict):
            state.add(i)
    return state


def _generate_neighbor(state: Set[int], num_windows: int) -> Set[int]:
    """Generate a neighbor state by add/remove/swap."""
    neighbor = state.copy()
    operation = random.choice(["add", "remove", "swap"])
    
    if operation == "add" or (operation == "swap" and not state):
        available = [i for i in range(num_windows) if i not in neighbor]
        if available:
            neighbor.add(random.choice(available))
    elif operation == "remove" or (operation == "swap" and len(state) == num_windows):
        if neighbor:
            neighbor.remove(random.choice(list(neighbor)))
    else:
        if neighbor:
            neighbor.remove(random.choice(list(neighbor)))
        available = [i for i in range(num_windows) if i not in neighbor]
        if available:
            neighbor.add(random.choice(available))
    
    return neighbor


def _apply_state(
    state: Set[int],
    windows: List[PlannerAccessWindow],
    scenario: "Scenario",
) -> int:
    """Apply final state to scenario."""
    count = 0
    for idx in sorted(state):
        window = windows[idx]
        use_middle = 5.0 if window.target_id or window.strip_id else None
        action_dict = window_to_action_dict(window, use_middle_minutes=use_middle)
        if try_stage_action(scenario, action_dict):
            count += 1
    return count
