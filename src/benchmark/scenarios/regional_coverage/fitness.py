"""Fitness function for regional_coverage benchmark."""

from pathlib import Path
from .verifier import verify_plan


def compute_fitness(plan_path: str, case_dir: str) -> float:
    """Compute scalar fitness score for simulated annealing optimization.
    
    Mean polygon coverage is the fitness.
    
    Returns:
        Fitness score in [0, 1] where 1.0 is optimal.
    """
    result = verify_plan(plan_path, case_dir)
    
    if not result.get("valid"):
        return 0.0
    
    metrics = result.get("metrics", {})
    polygon_coverage = metrics.get("polygon_coverage", {})
    
    if not polygon_coverage:
        return 0.0
    
    coverages = [p["coverage_percentage"] / 100.0 for p in polygon_coverage.values()]
    return sum(coverages) / len(coverages)
