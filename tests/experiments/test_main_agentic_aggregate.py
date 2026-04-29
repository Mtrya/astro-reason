from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from experiments.main_agentic import aggregate, plan


def _item(benchmark: str, case_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        benchmark=benchmark,
        split="test",
        case_id=case_id,
    )


def test_revisit_target_score_uses_smooth_thresholded_power_curve() -> None:
    assert aggregate._revisit_target_score_pct(
        max_gap_hours=48.0,
        expected_revisit_hours=8.0,
        horizon_hours=48.0,
    ) == 0.0
    assert aggregate._revisit_target_score_pct(
        max_gap_hours=8.0,
        expected_revisit_hours=8.0,
        horizon_hours=48.0,
    ) == 100.0
    assert aggregate._revisit_target_score_pct(
        max_gap_hours=24.0,
        expected_revisit_hours=8.0,
        horizon_hours=48.0,
    ) == pytest.approx(36.0)


def test_revisit_processed_metric_scores_invalid_runs_as_zero() -> None:
    processed_metrics = aggregate._processed_metrics_for_run(
        _item("revisit_constellation", "case_0001"),
        valid=False,
        verifier_payload={},
    )

    assert processed_metrics == {"revisit_score_pct": 0.0}


def test_spot5_reference_profit_uses_computed_fixture_profit() -> None:
    assert aggregate._spot5_reference_profit("test", "8") == 10
    assert aggregate._spot5_reference_profit("test", "1021") == 169243


def test_spot5_profit_score_normalizes_against_reference_profit() -> None:
    score = aggregate._spot5_profit_score_pct(
        _item("spot5", "8"),
        {"metrics": {"computed_profit": 5}},
    )

    assert score == pytest.approx(50.0)


def test_group_summary_processed_metric_mean_includes_invalid_zero() -> None:
    profile = plan.BenchmarkProfile(
        benchmark="spot5",
        assemble=(),
        collect=(),
        verifier_kind="single_file",
        score_metrics=(
            plan.MetricSpec(
                name="computed_profit",
                path="metrics.computed_profit",
                direction="maximize",
                role="primary",
            ),
        ),
        flag_metrics=(),
        profile_path=REPO_ROOT / "experiments" / "main_agentic" / "benchmarks" / "spot5.yaml",
    )
    summary = aggregate._build_group_summary(
        records=[
            {
                "artifact_state": "present",
                "overall_status": "success",
                "agent_status": "success",
                "verifier_status": "valid",
                "valid": True,
                "metrics": {"computed_profit": 10},
                "processed_metrics": {"profit_score_pct": 100.0},
                "flags": {},
            },
            {
                "artifact_state": "present",
                "overall_status": "no_solution",
                "agent_status": "no_solution",
                "verifier_status": "no_solution",
                "valid": None,
                "metrics": {"computed_profit": None},
                "processed_metrics": {"profit_score_pct": 0.0},
                "flags": {},
            },
        ],
        profile=profile,
        benchmark="spot5",
        harness="codex",
    )

    assert summary["primary_metric"]["stats"]["mean"] == 10.0
    assert summary["processed_metrics"]["profit_score_pct"]["stats"]["count"] == 2
    assert summary["processed_metrics"]["profit_score_pct"]["stats"]["mean"] == 50.0
