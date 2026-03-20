"""Tests for the SatNet benchmark verifier."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np
import pytest

from benchmarks.satnet.verifier import (
    Instance,
    Solution,
    Track,
    load_case,
    make_case_id,
    verify,
    verify_case,
)


DATASET_DIR = Path("benchmarks/satnet/dataset")
CASES_DIR = DATASET_DIR / "cases"
FIXTURES_DIR = Path("tests/fixtures/satnet_mock_solutions")
GROUND_TRUTH_SUMMARY = FIXTURES_DIR / "ground_truth_summary.json"


@dataclass
class GroundTruthCase:
    case_id: str
    week: int
    year: int
    solution_path: Path
    metrics_path: Path


def get_ground_truth_cases() -> list[GroundTruthCase]:
    """Load available ground-truth cases from fixtures."""

    if not GROUND_TRUTH_SUMMARY.exists():
        return []

    with GROUND_TRUTH_SUMMARY.open("r") as file_obj:
        summary = json.load(file_obj)

    return [
        GroundTruthCase(
            case_id=make_case_id(item["week"], item["year"]),
            week=item["week"],
            year=item["year"],
            solution_path=FIXTURES_DIR / item["solution_file"],
            metrics_path=FIXTURES_DIR / item["metrics_file"],
        )
        for item in summary
    ]


@pytest.fixture
def load_ground_truth(request):
    """Fixture to load a specific ground-truth case."""

    case = request.param

    with case.metrics_path.open("r") as file_obj:
        metrics = json.load(file_obj)

    with case.solution_path.open("r") as file_obj:
        solution_data = json.load(file_obj)
        solution = Solution(tracks=[Track.from_dict(track) for track in solution_data])

    instance = load_case(CASES_DIR / case.case_id)
    return instance, solution, metrics


@pytest.mark.parametrize("load_ground_truth", get_ground_truth_cases(), indirect=True)
def test_ground_truth_validation(load_ground_truth):
    """The verifier should reproduce the stored SatNet ground truth metrics."""

    instance, solution, metrics = load_ground_truth
    result = verify(instance, solution)

    assert result.is_valid, (
        f"Ground truth solution for {instance.case_id} should be valid. "
        f"Errors: {result.errors}"
    )
    assert np.isclose(result.score, metrics["score"], atol=1e-4)
    assert result.n_tracks == metrics["n_tracks"]
    assert result.n_satisfied_requests == metrics["n_satisfied_requests"]
    assert np.isclose(result.u_rms, metrics["u_rms"], atol=1e-4)
    assert np.isclose(result.u_max, metrics["u_max"], atol=1e-4)

    expected_per_mission_u_i = metrics["per_mission_u_i"]
    assert len(result.per_mission_u_i) == len(expected_per_mission_u_i)
    for mission_id, expected_u_i in expected_per_mission_u_i.items():
        assert mission_id in result.per_mission_u_i
        assert np.isclose(result.per_mission_u_i[mission_id], expected_u_i, atol=1e-4)


def test_verify_case_helper_matches_direct_verification():
    """The case-path helper should match manual case loading."""

    case = get_ground_truth_cases()[0]
    instance = load_case(CASES_DIR / case.case_id)
    with case.solution_path.open("r") as file_obj:
        solution_data = json.load(file_obj)
    solution = Solution(tracks=[Track.from_dict(track) for track in solution_data])

    direct = verify(instance, solution)
    via_case = verify_case(CASES_DIR / case.case_id, case.solution_path)

    assert direct.is_valid == via_case.is_valid
    assert np.isclose(direct.score, via_case.score, atol=1e-8)
    assert direct.n_tracks == via_case.n_tracks
    assert direct.n_satisfied_requests == via_case.n_satisfied_requests
    assert np.isclose(direct.u_rms, via_case.u_rms, atol=1e-8)
    assert np.isclose(direct.u_max, via_case.u_max, atol=1e-8)


@pytest.fixture
def simple_valid_case() -> tuple[Instance, Solution]:
    """Load a single valid case for corruption testing."""

    case_id = "W10_2018"
    solution_path = FIXTURES_DIR / f"{case_id}_solution.json"
    if not solution_path.exists():
        pytest.skip(f"{case_id} fixture not found")

    with solution_path.open("r") as file_obj:
        solution_data = json.load(file_obj)
        solution = Solution(tracks=[Track.from_dict(track) for track in solution_data])

    instance = load_case(CASES_DIR / case_id)
    return instance, solution


def test_case_metadata_matches_instance():
    """Case metadata should agree with the parsed instance."""

    instance = load_case(CASES_DIR / "W20_2018")
    assert instance.case_id == "W20_2018"
    assert instance.week == 20
    assert instance.year == 2018
    assert instance.metadata["request_count"] == len(instance.requests)
    assert instance.metadata["maintenance_window_count"] == len(instance.maintenance)


def test_violation_view_period(simple_valid_case):
    instance, valid_solution = simple_valid_case

    corrupt_tracks = deepcopy(valid_solution.tracks)
    target_track = corrupt_tracks[0]
    shift = 7 * 24 * 3600
    target_track.start_time += shift
    target_track.tracking_on += shift
    target_track.tracking_off += shift
    target_track.end_time += shift

    result = verify(instance, Solution(tracks=corrupt_tracks))
    assert not result.is_valid
    assert any("not within any View Period" in error for error in result.errors)


def test_violation_overlap(simple_valid_case):
    instance, valid_solution = simple_valid_case

    corrupt_tracks = deepcopy(valid_solution.tracks)
    corrupt_tracks.append(deepcopy(corrupt_tracks[0]))

    result = verify(instance, Solution(tracks=corrupt_tracks))
    assert not result.is_valid
    assert any("Overlap between tracks" in error for error in result.errors)


def test_violation_setup_time_mismatch(simple_valid_case):
    instance, valid_solution = simple_valid_case

    corrupt_tracks = deepcopy(valid_solution.tracks)
    corrupt_tracks[0].start_time -= 60

    result = verify(instance, Solution(tracks=corrupt_tracks))
    assert not result.is_valid
    assert any("Setup time mismatch" in error for error in result.errors)


def test_violation_teardown_time_mismatch(simple_valid_case):
    instance, valid_solution = simple_valid_case

    corrupt_tracks = deepcopy(valid_solution.tracks)
    corrupt_tracks[0].end_time += 60

    result = verify(instance, Solution(tracks=corrupt_tracks))
    assert not result.is_valid
    assert any("Teardown time mismatch" in error for error in result.errors)


def test_violation_minimum_duration(simple_valid_case):
    instance, valid_solution = simple_valid_case

    corrupt_tracks = deepcopy(valid_solution.tracks)
    target_track = corrupt_tracks[0]
    request = instance.requests[target_track.track_id]
    target_track.tracking_off = target_track.tracking_on + 1
    target_track.end_time = target_track.tracking_off + int(request.teardown_time * 60)

    result = verify(instance, Solution(tracks=corrupt_tracks))
    assert not result.is_valid
    assert any("below minimum" in error for error in result.errors)


def test_unknown_track_id(simple_valid_case):
    instance, valid_solution = simple_valid_case

    corrupt_tracks = deepcopy(valid_solution.tracks)
    corrupt_tracks[0].track_id = "non-existent-uuid"

    result = verify(instance, Solution(tracks=corrupt_tracks))
    assert not result.is_valid
    assert any("Unknown track_id" in error for error in result.errors)


def test_invalid_antenna(simple_valid_case):
    instance, valid_solution = simple_valid_case

    corrupt_tracks = deepcopy(valid_solution.tracks)
    corrupt_tracks[0].resource = "DSS-999"

    result = verify(instance, Solution(tracks=corrupt_tracks))
    assert not result.is_valid
    assert any("Antenna 'DSS-999' not available" in error for error in result.errors)


@pytest.mark.parametrize("load_ground_truth", get_ground_truth_cases(), indirect=True)
def test_fairness_metric_calculation(load_ground_truth):
    """Fairness metrics should remain available on valid solutions."""

    instance, solution, _metrics = load_ground_truth
    result = verify(instance, solution)

    assert hasattr(result, "u_rms")
    assert hasattr(result, "u_max")
    assert hasattr(result, "per_mission_u_i")
    assert isinstance(result.per_mission_u_i, dict)
    assert len(result.per_mission_u_i) > 0
    assert 0.0 <= result.u_rms <= 1.0
    assert 0.0 <= result.u_max <= 1.0
