from __future__ import annotations

import math
from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from solvers.regional_coverage.cp_local_search.src.candidates import (
    Candidate,
    generate_candidates,
)
from solvers.regional_coverage.cp_local_search.src.case_io import (
    SolverConfig,
    load_case,
)
from solvers.regional_coverage.cp_local_search.src.coverage import (
    CoverageFootprint,
    CoverageIndex,
)
from solvers.regional_coverage.cp_local_search.src.sequence import (
    SatelliteSequence,
    insert_candidate,
    is_consistent,
    remove_candidate,
)
from solvers.regional_coverage.cp_local_search.src.time_grid import grid_offsets
from solvers.regional_coverage.cp_local_search.src.transition import (
    required_transition_gap_s,
    slew_time_s,
    transition_result,
)


CASE_DIR = REPO_ROOT / "benchmarks" / "regional_coverage" / "dataset" / "cases" / "test" / "case_0001"


def _candidate(
    candidate_id: str,
    *,
    satellite_id: str = "sat_iceye-x2",
    start_offset_s: int = 0,
    end_offset_s: int = 20,
    roll_deg: float = -26.0,
    samples: frozenset[str] = frozenset({"sample_a"}),
) -> Candidate:
    return Candidate(
        candidate_id=candidate_id,
        satellite_id=satellite_id,
        start_offset_s=start_offset_s,
        end_offset_s=end_offset_s,
        duration_s=end_offset_s - start_offset_s,
        roll_deg=roll_deg,
        coverage_sample_ids=samples,
        base_coverage_weight_m2=1.0,
        estimated_energy_wh=1.0,
        estimated_slew_in_gap_s=2.0,
        footprint_center_latitude_deg=0.0,
        footprint_center_longitude_deg=0.0,
        footprint_heading_deg=0.0,
        along_half_m=100.0,
        cross_half_m=100.0,
    )


def test_load_case_reads_public_regional_coverage_files() -> None:
    case = load_case(CASE_DIR)

    assert case.mission.case_id == "case_0001"
    assert case.mission.time_step_s == 10
    assert len(case.satellites) == 10
    assert len(case.regions) == 3
    assert len(case.samples) > 10_000
    assert "sat_iceye-x2" in case.satellites


def test_action_grid_offsets_are_duration_bounded() -> None:
    case = load_case(CASE_DIR)
    mission = case.mission

    offsets = grid_offsets(mission, stride_s=3600, duration_s=20)

    assert offsets[0] == 0
    assert offsets[1] == 3600
    assert offsets[-1] + 20 <= mission.horizon_duration_s
    assert all(offset % mission.time_step_s == 0 for offset in offsets)


def test_candidate_generation_is_deterministic_and_grid_aligned() -> None:
    case = load_case(CASE_DIR)
    config = SolverConfig(
        candidate_stride_s=3600,
        max_candidates_per_satellite=1,
        max_zero_coverage_candidates_per_satellite=1,
    )

    first, first_summary = generate_candidates(case, config)
    second, second_summary = generate_candidates(case, config)

    assert [candidate.candidate_id for candidate in first] == [
        candidate.candidate_id for candidate in second
    ]
    assert first_summary.as_dict() == second_summary.as_dict()
    assert len(first) == len(case.satellites)
    assert all(candidate.duration_s == 20 for candidate in first)
    assert all(candidate.start_offset_s % case.mission.time_step_s == 0 for candidate in first)


def test_coverage_mapping_selects_samples_inside_oriented_strip() -> None:
    case = load_case(CASE_DIR)
    samples = case.samples[:2]
    index = CoverageIndex(
        samples=samples,
        total_weight_m2=sum(sample.weight_m2 for sample in samples),
        sample_weight_by_id={sample.sample_id: sample.weight_m2 for sample in samples},
    )
    origin = samples[0]
    footprint = CoverageFootprint(
        center_latitude_deg=origin.latitude_deg,
        center_longitude_deg=origin.longitude_deg,
        heading_deg=0.0,
        along_half_m=100.0,
        cross_half_m=100.0,
    )

    hits = index.samples_for_footprint(footprint)

    assert hits == frozenset({origin.sample_id})
    assert index.total_weight(hits) == pytest.approx(origin.weight_m2)


def test_roll_slew_formula_matches_triangular_and_trapezoidal_cases() -> None:
    satellite = load_case(CASE_DIR).satellites["sat_iceye-x2"]

    triangular = slew_time_s(1.0, satellite)
    trapezoidal = slew_time_s(10.0, satellite)

    assert triangular == pytest.approx(2.0 * math.sqrt(1.0 / 0.4))
    assert trapezoidal == pytest.approx(10.0 / 1.2 + 1.2 / 0.4)
    assert required_transition_gap_s(-26.0, 26.0, satellite) == pytest.approx(
        52.0 / 1.2 + 1.2 / 0.4 + 2.0
    )


def test_sequence_insert_remove_and_transition_feasibility() -> None:
    case = load_case(CASE_DIR)
    satellite = case.satellites["sat_iceye-x2"]
    sequence = SatelliteSequence(satellite_id="sat_iceye-x2")
    first = _candidate("c1", start_offset_s=0, end_offset_s=20, roll_deg=-26.0)
    feasible_second = _candidate("c2", start_offset_s=100, end_offset_s=120, roll_deg=26.0)
    infeasible_second = _candidate("c3", start_offset_s=40, end_offset_s=60, roll_deg=26.0)

    assert insert_candidate(case, sequence, first).success is True
    assert transition_result(first, feasible_second, satellite=satellite).feasible is True
    assert insert_candidate(case, sequence, feasible_second).success is True
    ok, reasons = is_consistent(case, sequence)
    assert ok, reasons
    assert sequence.covered_sample_ids() == {"sample_a"}

    removed = remove_candidate(sequence, "c2")
    assert removed.candidate_id == "c2"
    result = insert_candidate(case, sequence, infeasible_second)
    assert result.success is False
    assert "candidate lacks required transition gap from previous" in result.reject_reasons
