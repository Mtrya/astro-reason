from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
SOLVER_DIR = REPO_ROOT / "solvers" / "aeossp_standard" / "mwis_conflict_graph" / "src"
sys.path.insert(0, str(SOLVER_DIR))

from candidates import CandidateConfig, generate_candidates, start_offsets_for_task  # noqa: E402
from case_io import (  # noqa: E402
    AeosspCase,
    AttitudeModel,
    Mission,
    ResourceModel,
    Satellite,
    Task,
    iso_z,
    parse_iso_z,
)
from geometry import (  # noqa: E402
    action_sample_times,
    initial_slew_feasible_from_vectors,
)


def _mission() -> Mission:
    return Mission(
        case_id="unit_case",
        horizon_start=datetime(2026, 4, 14, 4, 0, tzinfo=UTC),
        horizon_end=datetime(2026, 4, 14, 5, 0, tzinfo=UTC),
        action_time_step_s=5,
        geometry_sample_step_s=5,
        resource_sample_step_s=10,
    )


def _satellite(satellite_id: str = "sat_a", sensor_type: str = "visible") -> Satellite:
    return Satellite(
        satellite_id=satellite_id,
        norad_catalog_id=1,
        tle_line1="tle1",
        tle_line2="tle2",
        sensor_type=sensor_type,
        attitude_model=AttitudeModel(
            max_slew_velocity_deg_per_s=1.0,
            max_slew_acceleration_deg_per_s2=1.0,
            settling_time_s=2.0,
            max_off_nadir_deg=30.0,
        ),
        resource_model=ResourceModel(
            battery_capacity_wh=1.0,
            initial_battery_wh=1.0,
            idle_power_w=1.0,
            imaging_power_w=1.0,
            slew_power_w=1.0,
            sunlit_charge_power_w=0.0,
        ),
    )


def _task(task_id: str = "task_a", sensor_type: str = "visible") -> Task:
    mission = _mission()
    return Task(
        task_id=task_id,
        name="task",
        latitude_deg=0.0,
        longitude_deg=0.0,
        altitude_m=0.0,
        release_time=mission.horizon_start + timedelta(seconds=10),
        due_time=mission.horizon_start + timedelta(seconds=30),
        required_duration_s=10,
        required_sensor_type=sensor_type,
        weight=3.0,
        target_ecef_m=(1.0, 0.0, 0.0),
    )


def test_iso_z_timestamp_round_trip() -> None:
    parsed = parse_iso_z("2026-04-14T04:00:05Z")

    assert parsed.tzinfo is UTC
    assert iso_z(parsed) == "2026-04-14T04:00:05Z"


def test_action_grid_iteration_respects_window_and_duration() -> None:
    case = AeosspCase(
        case_dir=Path("."),
        mission=_mission(),
        satellites={},
        tasks={"task_a": _task()},
    )

    assert start_offsets_for_task(case, _task()) == [10, 15, 20]
    assert start_offsets_for_task(case, _task(), stride_multiplier=2) == [10, 20]


def test_geometry_sample_times_include_boundaries_and_interior_grid() -> None:
    mission = _mission()
    start = mission.horizon_start + timedelta(seconds=7)
    end = mission.horizon_start + timedelta(seconds=22)

    assert [int((item - mission.horizon_start).total_seconds()) for item in action_sample_times(mission, start, end)] == [
        7,
        10,
        15,
        20,
        22,
    ]


def test_initial_slew_feasibility_from_nadir_vectors() -> None:
    satellite = _satellite()

    assert initial_slew_feasible_from_vectors(
        nadir_vector_eci=np.array([1.0, 0.0, 0.0]),
        target_vector_eci=np.array([1.0, 0.0, 0.0]),
        available_gap_s=2.0,
        satellite=satellite,
    )
    assert not initial_slew_feasible_from_vectors(
        nadir_vector_eci=np.array([1.0, 0.0, 0.0]),
        target_vector_eci=np.array([0.0, 1.0, 0.0]),
        available_gap_s=2.0,
        satellite=satellite,
    )


def test_generate_candidates_filters_sensor_and_keeps_stable_ids(monkeypatch) -> None:
    mission = _mission()
    case = AeosspCase(
        case_dir=Path("."),
        mission=mission,
        satellites={
            "sat_a": _satellite("sat_a", "visible"),
            "sat_b": _satellite("sat_b", "infrared"),
        },
        tasks={
            "task_a": _task("task_a", "visible"),
            "task_b": _task("task_b", "infrared"),
        },
    )

    class DummyPropagation:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr("candidates.PropagationContext", DummyPropagation)
    monkeypatch.setattr("candidates.observation_geometry_valid", lambda **kwargs: True)
    monkeypatch.setattr("candidates.initial_slew_feasible", lambda **kwargs: True)

    candidates, summary = generate_candidates(case, CandidateConfig())
    candidate_ids = [item.candidate_id for item in candidates]

    assert candidate_ids == [
        "sat_a|task_a|10",
        "sat_a|task_a|15",
        "sat_a|task_a|20",
        "sat_b|task_b|10",
        "sat_b|task_b|15",
        "sat_b|task_b|20",
    ]
    assert len(candidate_ids) == len(set(candidate_ids))
    assert summary.candidate_count == 6
    assert summary.skipped_sensor_mismatch == 6
