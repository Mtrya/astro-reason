"""Fitness function for stereo_imaging benchmark."""

from pathlib import Path
from .verifier import verify_plan


def compute_fitness(plan_path: str, case_dir: str) -> float:
    """Compute scalar fitness score for simulated annealing optimization.
    
    Stereo coverage ratio is the fitness.
    
    Returns:
        Fitness score in [0, 1] where 1.0 is optimal.
    """
    result = verify_plan(plan_path, case_dir)
    
    if not result.get("valid"):
        return 0.0
    
    metrics = result.get("metrics", {})
    return metrics.get("stereo_coverage", 0.0)
