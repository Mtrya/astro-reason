"""Verify regional-coverage benchmark plan.

This module validates plans and computes benchmark-specific metrics including:
- Polygon coverage percentage per region
- Validity checks (from planner validation logic)
"""

from pathlib import Path
from typing import Any
from datetime import datetime
import json
import yaml

from engines.astrox.analytics import compute_polygon_coverage


def verify_plan(plan_path: str, case_dir: str) -> dict[str, Any]:
    """Verify plan and compute regional-coverage metrics.
    
    Args:
        plan_path: Path to plan.json file
        case_dir: Path to case directory containing requirements.yaml
        
    Returns:
        Dictionary with verification results including:
        - valid: bool
        - metrics: dict with polygon_coverage
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
        
        # Load satellites for swath width (YAML is top-level list)
        with open(case_path / "satellites.yaml") as f:
            satellites_list = yaml.safe_load(f)
        
        # Load targets for positions (YAML is top-level list)
        with open(case_path / "targets.yaml") as f:
            targets_list = yaml.safe_load(f)
        
        req = requirements.get("regional_coverage", {})
        polygons = req.get("polygons", [])
        
        # Build satellite lookup
        sat_lookup = {}
        for sat in satellites_list:
            sat_lookup[sat["id"]] = sat
        
        # Build target lookup
        target_lookup = {}
        for target in targets_list:
            target_lookup[target["id"]] = target
        
        # Extract observations from plan
        actions = plan.get("actions", [])
        observations = [a for a in actions if a.get("type") == "observation"]
        
        # Load registered strips from plan
        registered_strips = {s["id"]: s for s in plan.get("registered_strips", [])}
        
        # Compute coverage for each polygon
        polygon_coverage = {}
        violations = []
        
        for polygon in polygons:
            polygon_id = polygon["id"]
            vertices = [(lat, lon) for lat, lon in polygon["vertices"]]
            required_coverage = polygon.get("required_coverage_percentage", 0.0)
            
            # Build observation strips with swath widths
            strips_with_width = []
            for obs in observations:
                sat_id = obs.get("satellite_id")
                strip_id = obs.get("strip_id")
                
                if not sat_id:
                    continue
                
                sat = sat_lookup.get(sat_id)
                if not sat:
                    continue
                
                swath_km = sat.get("swath_width_km", 0.0)
                
                # Use registered strip data if available
                if strip_id and strip_id in registered_strips:
                    strip_data = registered_strips[strip_id]
                    strip_polyline = [(lat, lon) for lat, lon in strip_data["points"]]
                    strips_with_width.append((strip_polyline, swath_km))
                elif obs.get("target_id"):
                    # Fallback: single-point observation (target-based)
                    target_id = obs.get("target_id")
                    target = target_lookup.get(target_id)
                    if target:
                        strip_polyline = [(target["latitude_deg"], target["longitude_deg"])]
                        strips_with_width.append((strip_polyline, swath_km))
            
            # Compute polygon coverage
            stats = compute_polygon_coverage(vertices, strips_with_width)
            coverage_pct = stats["coverage_ratio"] * 100.0
            
            polygon_coverage[polygon_id] = {
                "coverage_percentage": coverage_pct,
                "required_coverage_percentage": required_coverage,
            }
            
            if coverage_pct < required_coverage:
                violations.append(
                    f"{polygon_id}: coverage={coverage_pct:.1f}% "
                    f"below required {required_coverage:.1f}%"
                )
        
        return {
            "valid": True,
            "metrics": {
                "polygon_coverage": polygon_coverage,
            },
            "violations": violations,
        }
        
    except Exception as e:
        return {
            "valid": False,
            "error": f"Verification failed: {str(e)}",
        }


def score_plan(plan_path: str, case_dir: str) -> dict[str, Any]:
    """Score plan (alias for verify_plan for backward compatibility)."""
    return verify_plan(plan_path, case_dir)
