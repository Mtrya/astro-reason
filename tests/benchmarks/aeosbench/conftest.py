"""Pytest configuration and fixtures for tests_bsk."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

# Path to fixture directory
FIXTURES_DIR = Path("fixtures")


def load_json(path: Path) -> dict[str, Any]:
    """Load JSON file."""
    with open(path) as f:
        return json.load(f)


def get_fixture_ids() -> list[int]:
    """Get list of available fixture case IDs."""
    if not FIXTURES_DIR.exists():
        return []

    index_path = FIXTURES_DIR / "index.json"
    if not index_path.exists():
        return []

    index = load_json(index_path)
    return [f["case_id"] for f in index.get("fixtures", [])]


def load_fixture(case_id: int) -> tuple[dict, dict, dict, dict] | None:
    """Load a fixture by case ID.

    Returns:
        Tuple of (constellation, taskset, solution, metrics) or None if not found.
    """
    case_dir = FIXTURES_DIR / "cases" / f"{case_id:05d}"
    solution_path = FIXTURES_DIR / "solutions" / f"{case_id:05d}.json"
    metrics_path = FIXTURES_DIR / "metrics" / f"{case_id:05d}.json"

    if not all(p.exists() for p in [case_dir, solution_path, metrics_path]):
        return None

    constellation = load_json(case_dir / "constellation.json")
    taskset = load_json(case_dir / "taskset.json")
    solution = load_json(solution_path)
    metrics = load_json(metrics_path)

    return constellation, taskset, solution, metrics


@pytest.fixture(scope="module")
def case_157_data():
    """Load case 157 fixture data (single case for initial testing)."""
    result = load_fixture(157)
    if result is None:
        pytest.skip("Case 157 fixture not found")
    return result


@pytest.fixture(scope="module")
def all_fixtures():
    """Load all available fixtures."""
    case_ids = get_fixture_ids()
    fixtures = []
    for case_id in case_ids:
        result = load_fixture(case_id)
        if result is not None:
            fixtures.append((case_id, result))
    return fixtures


def pytest_generate_tests(metafunc):
    """Generate parametrized tests for all fixtures."""
    if "fixture_data" in metafunc.fixturenames:
        case_ids = get_fixture_ids()
        if case_ids:
            # Create test IDs for each case
            metafunc.parametrize(
                "fixture_data",
                case_ids,
                ids=[f"case_{cid}" for cid in case_ids],
            )
        else:
            metafunc.parametrize("fixture_data", [])
