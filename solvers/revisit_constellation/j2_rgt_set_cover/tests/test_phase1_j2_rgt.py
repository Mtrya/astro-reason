from __future__ import annotations

from pathlib import Path
import json
import subprocess

import pytest

from src.case_io import load_case
from src.rgt import (
    EARTH_RADIUS_M,
    SIDEREAL_DAY_SEC,
    RgtSearchConfig,
    analytical_brouwer_closure_score,
    circular_state_eci,
    closure_score_from_geocentric,
    enumerate_seeds,
    numerical_closure_score_at_duration,
    search_rgt_templates,
    solve_rgt_semimajor_axis,
)


REPO_ROOT = Path(__file__).resolve().parents[4]
CASE_DIR = REPO_ROOT / "benchmarks/revisit_constellation/dataset/cases/test/case_0001"
SOLVER_DIR = REPO_ROOT / "solvers/revisit_constellation/j2_rgt_set_cover"


def test_load_case_rejects_bool_integer(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "assets.json").write_text(
        json.dumps(
            {
                "max_num_satellites": True,
                "satellite_model": {
                    "min_altitude_m": 500000.0,
                    "max_altitude_m": 900000.0,
                },
            }
        ),
        encoding="utf-8",
    )
    (case_dir / "mission.json").write_text(
        json.dumps(
            {
                "horizon_start": "2025-07-17T12:00:00Z",
                "horizon_end": "2025-07-19T12:00:00Z",
                "targets": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="max_num_satellites"):
        load_case(case_dir)


def test_circular_state_respects_altitude_bounds() -> None:
    case = load_case(CASE_DIR)
    semi_major_axis, iterations, rejection = solve_rgt_semimajor_axis(
        repeat_days=1,
        revolutions=14,
        inclination_deg=53.0,
        min_altitude_m=case.satellite_model.min_altitude_m,
        max_altitude_m=case.satellite_model.max_altitude_m,
    )

    assert rejection is None
    assert iterations > 0
    assert semi_major_axis is not None
    altitude_m = semi_major_axis - EARTH_RADIUS_M
    assert case.satellite_model.min_altitude_m <= altitude_m <= case.satellite_model.max_altitude_m
    assert len(circular_state_eci(semi_major_axis, 53.0)) == 6


def test_closure_score_wraps_longitude() -> None:
    score = closure_score_from_geocentric(179.0, 0.0, -179.0, 0.0)

    assert score.longitude_delta_deg == pytest.approx(2.0)
    assert score.surface_error_m < 250_000.0


def test_seed_enumeration_is_deterministic_for_shuffled_inclinations() -> None:
    left = RgtSearchConfig(
        max_repeat_days=1,
        min_revolutions_per_day=14,
        max_revolutions_per_day=15,
        inclinations_deg=(97.8, 53.0, 63.4),
    )
    right = RgtSearchConfig(
        max_repeat_days=1,
        min_revolutions_per_day=14,
        max_revolutions_per_day=15,
        inclinations_deg=(63.4, 97.8, 53.0),
    )

    assert enumerate_seeds(left) == enumerate_seeds(right)


def test_brouwer_j2_closure_agrees_with_numerical_j2_for_seed() -> None:
    case = load_case(CASE_DIR)
    semi_major_axis, _, rejection = solve_rgt_semimajor_axis(
        repeat_days=1,
        revolutions=15,
        inclination_deg=97.8,
        min_altitude_m=case.satellite_model.min_altitude_m,
        max_altitude_m=case.satellite_model.max_altitude_m,
    )
    assert rejection is None
    assert semi_major_axis is not None

    analytical_closure, analytical_state = analytical_brouwer_closure_score(
        case,
        semi_major_axis_m=semi_major_axis,
        inclination_deg=97.8,
        eccentricity=0.0,
        mean_anomaly_deg=0.0,
        duration_sec=SIDEREAL_DAY_SEC,
    )
    numerical_closure = numerical_closure_score_at_duration(
        case,
        analytical_state,
        duration_sec=SIDEREAL_DAY_SEC,
    )

    assert abs(
        analytical_closure.surface_error_m - numerical_closure.surface_error_m
    ) < 5_000.0


def test_j2_search_accepts_analytically_closed_template() -> None:
    case = load_case(CASE_DIR)
    config = RgtSearchConfig(
        max_repeat_days=1,
        min_revolutions_per_day=15,
        max_revolutions_per_day=15,
        inclinations_deg=(97.8,),
        max_templates=1,
        closure_tolerance_m=5_000.0,
        refinement_iterations=8,
    )

    result = search_rgt_templates(case, config)

    assert len(result.accepted_templates) == 1
    template = result.accepted_templates[0]
    assert template.closure is not None
    assert template.closure.surface_error_m <= config.closure_tolerance_m
    assert template.rejection_reason is None


def test_full_profile_analytical_rgt_matches_numerical_j2_oracle() -> None:
    case = load_case(CASE_DIR)
    config = RgtSearchConfig(
        max_repeat_days=2,
        min_revolutions_per_day=12,
        max_revolutions_per_day=16,
        inclinations_deg=(30.0, 45.0, 53.0, 63.4, 75.0, 97.8),
        max_templates=12,
        closure_tolerance_m=5_000.0,
        refinement_iterations=8,
    )

    result = search_rgt_templates(case, config)

    assert len(result.accepted_templates) == config.max_templates
    for template in result.accepted_templates:
        assert template.closure is not None
        numerical_closure = numerical_closure_score_at_duration(
            case,
            template.state_eci_m_mps,
            duration_sec=template.repeat_period_sec,
        )
        assert numerical_closure.surface_error_m <= config.closure_tolerance_m
        assert abs(
            numerical_closure.surface_error_m - template.closure.surface_error_m
        ) < config.closure_tolerance_m


def test_solve_sh_writes_phase1_status_and_debug(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    output_dir = tmp_path / "solution"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        "\n".join(
            [
                "rgt_search:",
                "  max_repeat_days: 1",
                "  min_revolutions_per_day: 15",
                "  max_revolutions_per_day: 15",
                "  inclinations_deg: [97.8]",
                "  max_templates: 1",
                "  closure_tolerance_m: 5000.0",
                "  refinement_iterations: 8",
            ]
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "bash",
            str(SOLVER_DIR / "solve.sh"),
            str(CASE_DIR),
            str(config_dir),
            str(output_dir),
        ],
        check=False,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr
    status = json.loads((output_dir / "status.json").read_text(encoding="utf-8"))
    solution = json.loads((output_dir / "solution.json").read_text(encoding="utf-8"))
    debug = json.loads(
        (output_dir / "debug/closure_search.json").read_text(encoding="utf-8")
    )
    assert status["status"] == "completed"
    assert status["phase"] == 1
    assert status["closure_search"]["accepted_count"] == 1
    assert solution == {"satellites": [], "actions": []}
    assert debug["accepted_count"] == 1
