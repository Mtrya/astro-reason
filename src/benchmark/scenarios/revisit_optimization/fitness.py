"""Fitness function for revisit_optimization benchmark."""

from pathlib import Path
from .verifier import verify_plan


def compute_fitness(plan_path: str, case_dir: str) -> float:
    """Compute scalar fitness score for simulated annealing optimization.
    
    Lower max gap is better, so fitness = 1.0 - normalized_avg_max_gap.
    
    Returns:
        Fitness score in [0, 1] where 1.0 is optimal.
    """
    result = verify_plan(plan_path, case_dir)
    
    if not result.get("valid"):
        return 0.0
    
    metrics = result.get("metrics", {})
    gap_stats = metrics.get("gap_statistics", {})
    
    if not gap_stats:
        return 0.0
    
    max_gaps = [s["max_gap_hours"] for s in gap_stats.values() if s]
    if not max_gaps:
        return 0.0
    
    avg_max_gap = sum(max_gaps) / len(max_gaps)
    
    horizon_hours = 24.0
    normalized = min(avg_max_gap / horizon_hours, 1.0)
    
    return 1.0 - normalized
