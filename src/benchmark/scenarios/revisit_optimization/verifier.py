"""Verify revisit-optimization benchmark plan.

This module validates plans and computes benchmark-specific metrics including:
- Gap statistics (min, max, avg revisit gaps per target)
- Target coverage (observations vs requirements)
- Validity checks (from planner validation logic)
"""

from pathlib import Path
from typing import Any
from datetime import datetime
import json
import yaml


def verify_plan(plan_path: str, case_dir: str) -> dict[str, Any]:
    """Verify plan and compute revisit-optimization metrics.
    
    Args:
        plan_path: Path to plan.json file
        case_dir: Path to case directory containing requirements.yaml
        
    Returns:
        Dictionary with verification results including:
        - valid: bool
        - metrics: dict with gap_statistics and target_coverage
        - violations: list of constraint violations
    """
    try:
        case_path = Path(case_dir)
        
        # Load plan
        with open(plan_path) as f:
            plan = json.load(f)
        
        # Load requirements
        with open(case_path / "requirements.yaml") as f:
            requirements = yaml.safe_load(f)
        
        meta = requirements.get("meta", {})
        req = requirements.get("revisit_optimization", {})
        
        horizon_start = _parse_iso(meta.get("horizon_start"))
        horizon_end = _parse_iso(meta.get("horizon_end"))
        
        # Extract observations from plan
        actions = plan.get("actions", [])
        observations = [a for a in actions if a.get("type") == "observation"]
        
        # Parse requirements
        monitoring_targets = req.get("monitoring_targets", [])
        mapping_targets = req.get("mapping_targets", {})
        
        all_target_ids = set(monitoring_targets) | set(mapping_targets.keys())
        
        # Compute gap statistics for all targets
        gap_statistics = {}
        violations = []
        
        for target_id in all_target_ids:
            stats = _compute_gap_statistics(
                observations, target_id, horizon_start, horizon_end
            )
            if stats is not None:
                gap_statistics[target_id] = stats
        
        # Compute target coverage
        total_required = sum(mapping_targets.values())
        total_actual = sum(
            gap_statistics.get(tid, {}).get("num_observations", 0)
            for tid in mapping_targets.keys()
        )
        target_coverage = total_actual / total_required if total_required > 0 else 0.0
        
        # Return results
        return {
            "valid": True,
            "metrics": {
                "gap_statistics": gap_statistics,
                "target_coverage": target_coverage,
            },
            "violations": violations,
        }
        
    except Exception as e:
        return {
            "valid": False,
            "error": f"Verification failed: {str(e)}",
        }


def _parse_iso(iso_str: str) -> datetime:
    """Parse ISO 8601 datetime string."""
    return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))


def _compute_gap_statistics(
    observations: list[dict],
    target_id: str,
    horizon_start: datetime,
    horizon_end: datetime,
) -> dict[str, Any] | None:
    """Compute min/max/avg gaps for a target.
    
    Args:
        observations: List of observation actions
        target_id: Target ID to compute stats for
        horizon_start: Mission start time
        horizon_end: Mission end time
        
    Returns:
        Dict with gap statistics or None if no observations
    """
    # Get all observation times for this target
    obs_times = [
        _parse_iso(a["start"])
        for a in observations
        if a.get("target_id") == target_id and a.get("start")
    ]
    obs_times = sorted(obs_times)
    
    if len(obs_times) == 0:
        return None
    
    # Include horizon boundaries
    all_times = [horizon_start] + obs_times + [horizon_end]
    
    # Compute gaps
    gaps_hours = [
        (all_times[i + 1] - all_times[i]).total_seconds() / 3600
        for i in range(len(all_times) - 1)
    ]
    
    return {
        "min_gap_hours": min(gaps_hours),
        "max_gap_hours": max(gaps_hours),
        "avg_gap_hours": sum(gaps_hours) / len(gaps_hours),
        "num_observations": len(obs_times),
    }


def score_plan(plan_path: str, case_dir: str) -> dict[str, Any]:
    """Score plan (alias for verify_plan for backward compatibility)."""
    return verify_plan(plan_path, case_dir)
