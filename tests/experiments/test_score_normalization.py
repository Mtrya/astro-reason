from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from experiments._shared import score_normalization as scores


def test_clip_ratio_and_lower_score_helpers() -> None:
    assert scores.clip01(-0.25) == 0.0
    assert scores.clip01(1.25) == 1.0
    assert scores.ratio_score_pct(5, 10) == pytest.approx(50.0)
    assert scores.ratio_score_pct(12, 10) == pytest.approx(100.0)
    assert scores.lower_score(25, 100) == pytest.approx(0.75)


def test_scarcity_bonus_values_late_satellite_reductions_more() -> None:
    easy_reduction = scores.scarcity_bonus(8, n_min=4, n_max=10)
    hard_reduction = scores.scarcity_bonus(5, n_min=4, n_max=10)
    perfect = scores.scarcity_bonus(4, n_min=4, n_max=10)

    assert easy_reduction == pytest.approx((2 / 6) ** 2)
    assert hard_reduction == pytest.approx((5 / 6) ** 2)
    assert perfect == pytest.approx(1.0)
    assert (perfect - hard_reduction) > easy_reduction


def test_revisit_gap_curve_matches_reader_facing_thresholds() -> None:
    assert scores.revisit_target_gap_score_pct(
        max_gap_hours=48.0,
        expected_revisit_hours=8.0,
        horizon_hours=48.0,
    ) == 0.0
    assert scores.revisit_target_gap_score_pct(
        max_gap_hours=8.0,
        expected_revisit_hours=8.0,
        horizon_hours=48.0,
    ) == 100.0
    assert scores.revisit_target_gap_score_pct(
        max_gap_hours=24.0,
        expected_revisit_hours=8.0,
        horizon_hours=48.0,
    ) == pytest.approx(36.0)


def test_constellation_scores_are_gated_before_resource_bonus() -> None:
    assert scores.relay_constellation_score_pct(
        service_fraction=0.99,
        worst_demand_service_fraction=1.0,
        num_added_satellites=1,
        min_added_satellites=1,
        max_added_satellites=6,
        mean_latency_ms=10,
        latency_p95_ms=10,
        latency_cap_ms=100,
    ) < 70.0

    assert scores.revisit_constellation_score_pct(
        gap_score=1.0,
        num_satellites=4,
        min_satellites=4,
        max_satellites=10,
    ) == pytest.approx(100.0)


def test_task_specific_score_functions() -> None:
    assert scores.stereo_imaging_score_pct(normalized_quality=0.42) == pytest.approx(42.0)
    assert scores.spot5_score_pct(
        computed_profit=120,
        total_possible_profit=100,
    ) == pytest.approx(100.0)
    assert scores.satnet_score_pct(
        u_rms=1.0,
        u_rms_cap=2.0,
        u_max=2.0,
        u_max_cap=4.0,
    ) == pytest.approx(50.0)
