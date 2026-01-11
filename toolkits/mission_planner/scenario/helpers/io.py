"""Plan I/O utilities."""

import json
from pathlib import Path
from typing import Dict, Any


def export_plan_to_json(plan_data: Dict[str, Any], path: Path | str | None = None) -> Path:
    """
    Export plan data to a JSON file.

    Args:
        plan_data: Plan dictionary with 'metadata' and 'actions'
        path: Optional output path. Defaults to plan.json in current dir

    Returns:
        Path to the written file
    """
    if path is None:
        plan_dir = Path("./")
        plan_dir.mkdir(parents=True, exist_ok=True)
        path = plan_dir / "plan.json"
    else:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(plan_data, f, indent=2)

    return path


def load_plan_json(path: Path | str) -> Dict[str, Any]:
    """
    Load and parse a plan JSON file.

    Args:
        path: Path to the plan JSON file

    Returns:
        Dictionary containing plan data with 'metadata' and 'actions' keys

    Raises:
        FileNotFoundError: If the file doesn't exist
        ValueError: If the JSON is invalid or missing required fields
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Plan file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as f:
            plan_data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in plan file: {e}")

    if "actions" not in plan_data:
        raise ValueError("Plan JSON missing required 'actions' field")

    return plan_data