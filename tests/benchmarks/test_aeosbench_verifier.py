"""Test AEOS-Bench verifier against ground-truth fixtures.

These tests validate that the Basilisk-based verifier produces metrics that
match the stored fixtures.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import benchmarks.aeosbench.verifier as aeos_verifier_module
from benchmarks.aeosbench.verifier import AEOSVerifierBSK


FIXTURES_DIR = Path("tests/fixtures/aeosbench_gt_bsk2.9.0")
DEFAULT_CASE_ID = 157
FULL_FIXTURES_ENV = "AEOSBENCH_FULL_FIXTURES"
ARCHIVE_NAMES = ("cases.tar.gz", "solutions.tar.gz", "metrics.tar.gz")
EXTRACTED_FIXTURES_DIR = Path(tempfile.gettempdir()) / "aeosbench_gt_bsk2.9.0"
REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPO_ROOT / "benchmarks" / "aeosbench" / "verifier" / "run.py"


def _full_fixtures_requested() -> bool:
    return os.environ.get(FULL_FIXTURES_ENV, "").lower() in {"1", "true", "yes", "on"}


def _full_fixture_tree_present() -> bool:
    non_default_case = EXTRACTED_FIXTURES_DIR / "cases" / "00105" / "taskset.json"
    return non_default_case.exists()


def _safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    destination_resolved = destination.resolve()
    for member in archive.getmembers():
        member_path = (destination / member.name).resolve()
        if not str(member_path).startswith(f"{destination_resolved}{os.sep}"):
            raise ValueError(f"Unsafe archive member path: {member.name}")
    archive.extractall(destination)


def _extract_full_fixtures() -> Path:
    if _full_fixture_tree_present():
        return EXTRACTED_FIXTURES_DIR

    missing_archives = [
        archive_name for archive_name in ARCHIVE_NAMES if not (FIXTURES_DIR / archive_name).exists()
    ]
    if missing_archives:
        pytest.skip(f"Missing archived fixtures: {', '.join(missing_archives)}")

    if EXTRACTED_FIXTURES_DIR.exists():
        shutil.rmtree(EXTRACTED_FIXTURES_DIR)

    EXTRACTED_FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(FIXTURES_DIR / "index.json", EXTRACTED_FIXTURES_DIR / "index.json")
    shutil.copytree(FIXTURES_DIR / "cases", EXTRACTED_FIXTURES_DIR / "cases")
    shutil.copytree(FIXTURES_DIR / "solutions", EXTRACTED_FIXTURES_DIR / "solutions")
    shutil.copytree(FIXTURES_DIR / "metrics", EXTRACTED_FIXTURES_DIR / "metrics")

    for archive_name in ARCHIVE_NAMES:
        archive_path = FIXTURES_DIR / archive_name
        with tarfile.open(archive_path, "r:gz") as archive:
            _safe_extract(archive, EXTRACTED_FIXTURES_DIR)

    return EXTRACTED_FIXTURES_DIR


def _load_fixture(case_id: int, *, fixtures_dir: Path = FIXTURES_DIR) -> tuple[dict, dict, dict, dict]:
    case_dir = fixtures_dir / "cases" / f"{case_id:05d}"
    solution_path = fixtures_dir / "solutions" / f"{case_id:05d}.json"
    metrics_path = fixtures_dir / "metrics" / f"{case_id:05d}.json"

    with open(case_dir / "constellation.json") as f:
        constellation = json.load(f)
    with open(case_dir / "taskset.json") as f:
        taskset = json.load(f)
    with open(solution_path) as f:
        solution = json.load(f)
    with open(metrics_path) as f:
        expected_metrics = json.load(f)

    return constellation, taskset, solution, expected_metrics


def _assert_metrics_close(*, actual: dict[str, float], expected: dict[str, float], case_id: int) -> None:
    # Tolerances account for float32 storage precision in fixtures.
    tolerances = {
        "CR": 1e-7,
        "WCR": 1e-7,
        "PCR": 1e-7,
        "WPCR": 1e-7,
        "TAT": 1e-4,
        "PC": 1e-1,
    }

    for key, tol in tolerances.items():
        diff = abs(actual[key] - expected[key])
        assert diff < tol, (
            f"{key} mismatch for case {case_id}: "
            f"got {actual[key]:.10f}, expected {expected[key]:.10f}, "
            f"diff={diff:.10e} (tol={tol:.2e})"
        )


def test_verify_normalizes_string_satellite_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    sat_ids = list(range(12))
    raw_assignments = {
        str(sat_id): [sat_id] * aeos_verifier_module.NUM_TIMESTEPS for sat_id in sat_ids
    }
    captured_assignment_t: list[int] = []

    class FakeEnvironment:
        def __init__(self, constellation: SimpleNamespace, taskset: SimpleNamespace) -> None:
            self.satellites = [
                SimpleNamespace(id=sat.id, is_sensor_enabled=False)
                for sat in sorted(constellation.satellites, key=lambda sat: sat.id)
            ]

        def is_visible(self, taskset: SimpleNamespace) -> np.ndarray:
            return np.zeros((len(self.satellites), len(taskset.tasks)), dtype=bool)

        def take_actions(
            self,
            toggles: list[bool],
            target_locations: list[tuple[float, float] | None],
        ) -> None:
            return None

        def step(self, time_nano: int) -> None:
            return None

    class FakeTracker:
        def __init__(self, constellation: SimpleNamespace, taskset: SimpleNamespace) -> None:
            return None

        def get_ongoing_ids(self, timestep: int) -> set[int]:
            return set()

        def record(
            self,
            timestep: int,
            vis: np.ndarray,
            assignment_t: list[int],
        ) -> None:
            if timestep == 0:
                captured_assignment_t[:] = assignment_t

        def compute_metrics(self) -> dict[str, float]:
            return {
                "CR": 0.0,
                "WCR": 0.0,
                "PCR": 0.0,
                "WPCR": 0.0,
                "TAT": 0.0,
                "PC": 0.0,
                "valid": True,
            }

    monkeypatch.setattr(aeos_verifier_module, "BSKEnvironment", FakeEnvironment)
    monkeypatch.setattr(aeos_verifier_module, "ProgressTracker", FakeTracker)

    verifier = object.__new__(AEOSVerifierBSK)
    verifier.constellation = SimpleNamespace(
        satellites=[SimpleNamespace(id=sat_id) for sat_id in sat_ids]
    )
    verifier.taskset = SimpleNamespace(tasks=[])

    result = verifier.verify(raw_assignments)

    assert result["valid"]
    assert captured_assignment_t == sat_ids


def test_run_py_help_works_when_executed_directly() -> None:
    result = subprocess.run(
        [sys.executable, str(RUNNER_PATH), "--help"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Verify AEOS-Bench satellite scheduling solutions" in result.stdout


def test_case_157_metrics() -> None:
    if not FIXTURES_DIR.exists():
        pytest.skip("Fixtures directory not found")

    case_id = DEFAULT_CASE_ID
    try:
        constellation, taskset, solution, expected = _load_fixture(case_id)
    except FileNotFoundError:
        pytest.skip(f"Case {case_id} fixture not found")

    verifier = AEOSVerifierBSK(constellation, taskset)
    result = verifier.verify(solution["assignments"])

    assert result["valid"], "Verifier returned invalid result"
    _assert_metrics_close(
        actual=result,
        expected=expected["metrics"],
        case_id=case_id,
    )


@pytest.mark.parametrize(
    "case_id",
    [
        157,
    ],
)
def test_specific_case(case_id: int) -> None:
    if not FIXTURES_DIR.exists():
        pytest.skip("Fixtures directory not found")

    fixtures_dir = FIXTURES_DIR
    if case_id != DEFAULT_CASE_ID and _full_fixtures_requested():
        fixtures_dir = _extract_full_fixtures()

    try:
        constellation, taskset, solution, expected = _load_fixture(case_id, fixtures_dir=fixtures_dir)
    except FileNotFoundError:
        pytest.skip(f"Case {case_id} fixture not found")

    verifier = AEOSVerifierBSK(constellation, taskset)
    result = verifier.verify(solution["assignments"])

    assert result["valid"], "Verifier returned invalid result"
    _assert_metrics_close(
        actual=result,
        expected=expected["metrics"],
        case_id=case_id,
    )


def test_all_fixtures() -> None:
    if not FIXTURES_DIR.exists():
        pytest.skip("Fixtures directory not found")

    if not _full_fixtures_requested():
        pytest.skip(
            f"Set {FULL_FIXTURES_ENV}=1 to extract archived AEOS fixtures and run the full corpus"
        )

    fixtures_dir = _extract_full_fixtures()

    index_path = fixtures_dir / "index.json"
    if not index_path.exists():
        pytest.skip("No fixtures available")

    with open(index_path) as f:
        index = json.load(f)
    case_ids = [fixture["case_id"] for fixture in index.get("fixtures", [])]

    if not case_ids:
        pytest.skip("No fixtures available")

    failures: list[str] = []
    for case_id in case_ids:
        try:
            constellation, taskset, solution, expected = _load_fixture(case_id, fixtures_dir=fixtures_dir)

            verifier = AEOSVerifierBSK(constellation, taskset)
            result = verifier.verify(solution["assignments"])

            if not result["valid"]:
                failures.append(f"Case {case_id}: invalid result")
                continue

            try:
                _assert_metrics_close(
                    actual=result,
                    expected=expected["metrics"],
                    case_id=case_id,
                )
            except AssertionError as e:
                failures.append(str(e))
        except Exception as e:
            failures.append(f"Case {case_id}: exception: {e}")

    if failures:
        pytest.fail("\n".join(failures))
