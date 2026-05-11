from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from experiments.main_agentic import aggregate, plan, plot_radar


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


def test_revisit_solver_baseline_is_normalized_before_radar_comparison() -> None:
    baseline_data = plot_radar._load_baseline_data(plot_radar.DEFAULT_BASELINES)
    scores = plot_radar._best_solver_scores_by_case(baseline_data)
    benchmark_scores = plot_radar._solver_baseline_scores_by_benchmark(baseline_data)

    assert scores["revisit_constellation"]["test/case_0001"] == pytest.approx(
        70.0 + 30.0 * ((20.0 - 16.0) / (20.0 - 1.0)) ** 2
    )
    assert scores["revisit_constellation"]["test/case_0003"] == pytest.approx(70.0)
    assert benchmark_scores["revisit_constellation"] == pytest.approx(
        sum(scores["revisit_constellation"].values())
        / len(scores["revisit_constellation"])
    )


def test_radar_keeps_zero_scores_for_invalid_runs(tmp_path: Path) -> None:
    benchmark_dir = tmp_path / "benchmarks"
    benchmark_dir.mkdir()
    (benchmark_dir / "stereo_imaging.csv").write_text(
        "benchmark,harness,split,case_id,valid,normalized_quality,coverage_ratio\n"
        "stereo_imaging,codex,test,case_0001,False,,\n",
        encoding="utf-8",
    )
    baseline_data = plot_radar._load_baseline_data(plot_radar.DEFAULT_BASELINES)

    benchmarks, scores = plot_radar._load_scores(tmp_path, baseline_data)

    assert benchmarks == ["stereo_imaging"]
    assert scores["codex"]["stereo_imaging"] == 0.0


def test_radar_can_plot_normalized_pct_scores_without_solver_relative_scaling(
    tmp_path: Path,
) -> None:
    benchmark_dir = tmp_path / "benchmarks"
    benchmark_dir.mkdir()
    (benchmark_dir / "stereo_imaging.csv").write_text(
        "benchmark,harness,split,case_id,valid,normalized_quality,coverage_ratio\n"
        "stereo_imaging,codex,test,case_0001,True,0.25,0.5\n",
        encoding="utf-8",
    )
    baseline_data = plot_radar._load_baseline_data(plot_radar.DEFAULT_BASELINES)

    benchmarks, scores = plot_radar._load_scores(
        tmp_path,
        baseline_data,
        score_mode="normalized-pct",
    )

    assert benchmarks == ["stereo_imaging"]
    assert scores["codex"]["stereo_imaging"] == pytest.approx(25.0)


def test_spot5_reference_profit_uses_computed_fixture_profit() -> None:
    assert aggregate._spot5_reference_profit("test", "8") == 10
    assert aggregate._spot5_reference_profit("test", "1021") == 169243


def test_spot5_max_profit_uses_unconstrained_case_profit() -> None:
    assert aggregate._spot5_max_profit("test", "8") == 12


def test_spot5_profit_score_normalizes_against_max_profit() -> None:
    score = aggregate._spot5_profit_score_pct(
        _item("spot5", "8"),
        {"metrics": {"computed_profit": 5}},
    )

    assert score == pytest.approx(100.0 * 5 / 12)


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


def test_aggregate_counts_valid_timeout_run_as_success(tmp_path: Path) -> None:
    item = SimpleNamespace(
        config_name="matrix",
        benchmark="satnet",
        harness="codex",
        split="test",
        case_id="W10_2018",
        results_root=tmp_path,
        benchmark_profile=SimpleNamespace(score_metrics=(), flag_metrics=()),
    )
    record = aggregate._normalize_run_record(
        item,
        {
            "overall_status": "timeout",
            "agent_status": "timeout",
            "verifier_status": "valid",
            "verifier": {"valid": True, "metrics": {}},
        },
    )

    assert record["overall_status"] == "success"
    assert record["agent_status"] == "timeout"
    assert record["verifier_status"] == "valid"


def test_load_expected_records_classifies_missing_malformed_and_present_artifacts(
    tmp_path: Path,
) -> None:
    profile = plan.BenchmarkProfile(
        benchmark="synthetic_benchmark",
        assemble=(),
        collect=(),
        verifier_kind="single_file",
        score_metrics=(
            plan.MetricSpec(
                name="score",
                path="metrics.score",
                direction="maximize",
                role="primary",
            ),
        ),
        flag_metrics=(
            plan.FlagMetricSpec(
                name="used_helper",
                path="diagnostics.used_helper",
            ),
        ),
        profile_path=tmp_path / "synthetic.yaml",
    )

    def item(case_id: str) -> SimpleNamespace:
        return SimpleNamespace(
            config_name="matrix",
            benchmark="synthetic_benchmark",
            harness="codex",
            split="test",
            case_id=case_id,
            results_root=tmp_path,
            benchmark_profile=profile,
        )

    missing = item("missing")
    malformed = item("malformed")
    present = item("present")
    plan_like = SimpleNamespace(items=(missing, malformed, present))

    plan.run_output_dir(malformed).mkdir(parents=True)
    (plan.run_output_dir(malformed) / "run.json").write_text("{not json", encoding="utf-8")
    plan.run_output_dir(present).mkdir(parents=True)
    (plan.run_output_dir(present) / "run.json").write_text(
        """
        {
          "overall_status": "success",
          "agent_status": "success",
          "verifier_status": "valid",
          "duration_seconds": 12.5,
          "verifier": {
            "valid": true,
            "metrics": {"score": 42},
            "diagnostics": {"used_helper": true}
          }
        }
        """,
        encoding="utf-8",
    )

    records = aggregate._load_expected_records(plan_like)

    assert [record["artifact_state"] for record in records] == [
        "missing_artifact",
        "malformed_artifact",
        "present",
    ]
    assert records[0]["metrics"] == {"score": None}
    assert records[1]["valid"] is None
    assert records[2]["metrics"] == {"score": 42}
    assert records[2]["flags"] == {"used_helper": True}
