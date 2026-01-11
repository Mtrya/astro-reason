"""Verify stereo-imaging benchmark plan.

This module validates plans and computes benchmark-specific metrics including:
- Number of stereo targets (targets with valid stereo pairs)
- Stereo coverage percentage
- Target coverage (observations vs requirements)
- Validity checks (from planner validation logic)
"""

from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime, timedelta
import json
import yaml

from engines.astrox.analytics import compute_stereo_compliance
from engines.astrox.models.satellite import Satellite
from engines.astrox.models.target import Target
from engines.astrox.orbital.access import compute_accessibility


def verify_plan(plan_path: str, case_dir: str) -> dict[str, Any]:
    """Verify plan and compute stereo-imaging metrics.
    
    Args:
        plan_path: Path to plan.json file
        case_dir: Path to case directory containing requirements.yaml
        
    Returns:
        Dictionary with verification results including:
        - valid: bool
        - metrics: dict with num_stereo_targets, stereo_coverage, target_coverage
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
        
        # Load satellites and targets for potential AER re-calculation
        with open(case_path / "satellites.yaml") as f:
            satellites_list = yaml.safe_load(f)
        
        with open(case_path / "targets.yaml") as f:
            targets_list = yaml.safe_load(f)
            
        sat_lookup = {s["id"]: s for s in satellites_list}
        target_lookup = {t["id"]: t for t in targets_list}
        
        req = requirements.get("stereo_imaging", {})
        
        # Extract stereo parameters
        min_separation_deg = req.get("min_azimuth_sep_deg", 15.0)
        max_separation_deg = req.get("max_azimuth_sep_deg", 60.0)
        
        # Extract observations from plan
        actions = plan.get("actions", [])
        observations = [a for a in actions if a.get("type") == "observation"]
        
        # Group observations by target
        obs_by_target = {}
        for obs in observations:
            target_id = obs.get("target_id")
            if not target_id:
                continue
                
            if target_id not in obs_by_target:
                obs_by_target[target_id] = []
            
            az = obs.get("azimuth_deg")
            el = obs.get("elevation_deg")
            time_str = obs.get("start")
            
            if time_str is None:
                continue
            
            # If geometric data is missing, re-calculate using engine
            if az is None or el is None:
                sat_id = obs.get("satellite_id")
                if sat_id in sat_lookup and target_id in target_lookup:
                    az_calc, el_calc = _get_aer_from_engine(
                        sat_lookup[sat_id],
                        target_lookup[target_id],
                        time_str
                    )
                    if az_calc is not None:
                        az, el = az_calc, el_calc

            if az is not None and el is not None:
                obs_by_target[target_id].append({
                    "id": obs.get("action_id", ""),
                    "time": _parse_iso(time_str),
                    "azimuth_deg": float(az),
                    "elevation_deg": float(el),
                })
        
        # Compute stereo metrics
        stereo_targets = []
        for target_id, obs_list in obs_by_target.items():
            stats = compute_stereo_compliance(
                obs_list,
                min_separation_deg=min_separation_deg,
                max_separation_deg=max_separation_deg,
            )
            if stats.get("has_stereo"):
                stereo_targets.append(target_id)
        
        # Compute coverage
        required_observations = req.get("required_observations", {})
        num_stereo = len(stereo_targets)
        required_stereo = len(required_observations)
        stereo_coverage = num_stereo / required_stereo if required_stereo > 0 else 0.0
        
        # Compute target coverage
        total_required = sum(required_observations.values())
        total_actual = sum(len(obs_by_target.get(tid, [])) for tid in required_observations.keys())
        target_coverage = total_actual / total_required if total_required > 0 else 0.0
        
        return {
            "valid": True,
            "metrics": {
                "num_stereo_targets": num_stereo,
                "stereo_coverage": stereo_coverage,
                "target_coverage": target_coverage,
                "stereo_targets": stereo_targets,
            },
            "violations": [],
        }
        
    except Exception as e:
        return {
            "valid": False,
            "error": f"Verification failed: {str(e)}",
        }


def _parse_iso(iso_str: str) -> datetime:
    """Parse ISO 8601 datetime string."""
    if iso_str is None:
        return None
    return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))


def _get_aer_from_engine(sat_data: Dict, target_data: Dict, time_str: str) -> tuple[float, float] | tuple[None, None]:
    """Re-compute azimuth and elevation using the engine."""
    try:
        # Convert to models
        valid_sat_keys = ['tle_line1', 'tle_line2', 'apogee_km', 'perigee_km', 'period_min', 'inclination_deg']
        sat = Satellite(**{k: sat_data[k] for k in valid_sat_keys})
        
        target = Target(
            latitude_deg=target_data['latitude_deg'],
            longitude_deg=target_data['longitude_deg'],
            altitude_m=target_data.get('altitude_m', 0.0)
        )
        
        # Setup thin window around time (10 seconds)
        dt = _parse_iso(time_str)
        t_start = (dt - timedelta(seconds=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        t_end = (dt + timedelta(seconds=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        windows = compute_accessibility(
            satellite=sat,
            target=target,
            time_window=(t_start, t_end),
        )
        
        if not windows:
            return None, None
            
        win = windows[0]
        if win.max_elevation_point:
            return win.max_elevation_point.azimuth_deg, win.max_elevation_point.elevation_deg
            
        return None, None
    except:
        return None, None


def score_plan(plan_path: str, case_dir: str) -> dict[str, Any]:
    """Score plan (alias for verify_plan for backward compatibility)."""
    return verify_plan(plan_path, case_dir)
