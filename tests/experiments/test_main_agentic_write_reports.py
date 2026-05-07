from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from experiments.main_agentic import plot_radar, write_reports


def test_case_tables_use_valid_and_normalized_score_columns(tmp_path: Path) -> None:
    baseline_data = plot_radar._load_baseline_data(
        REPO_ROOT / "experiments" / "main_agentic" / "baselines" / "main_solver.yaml"
    )
    summary_rows = [
        {
            "benchmark": "stereo_imaging",
            "harness": "codex",
            "present_runs": "2",
            "success_count": "1",
            "valid_count": "1",
            "invalid_count": "1",
            "timeout_count": "0",
            "primary_metric_name": "normalized_quality",
            "primary_metric_mean": "0.5",
        }
    ]
    run_rows = [
        {
            "config_name": "matrix",
            "benchmark": "stereo_imaging",
            "harness": "codex",
            "split": "test",
            "case_id": "case_0001",
            "artifact_state": "present",
            "overall_status": "success",
            "verifier_status": "valid",
            "valid": "True",
            "duration_seconds": "12.5",
            "normalized_quality": "0.5",
            "coverage_ratio": "0.75",
            "profit_score_pct": "99.0",
        },
        {
            "config_name": "matrix",
            "benchmark": "stereo_imaging",
            "harness": "codex",
            "split": "test",
            "case_id": "case_0002",
            "artifact_state": "present",
            "overall_status": "verifier_invalid",
            "verifier_status": "invalid",
            "valid": "False",
            "duration_seconds": "20.0",
            "normalized_quality": "",
            "coverage_ratio": "",
            "profit_score_pct": "12.0",
        },
    ]

    write_reports._write_benchmark_report(
        benchmark="stereo_imaging",
        summary_rows=summary_rows,
        run_rows=run_rows,
        reports_dir=tmp_path,
        baseline_data=baseline_data,
    )

    report = (tmp_path / "stereo_imaging.md").read_text(encoding="utf-8")

    assert "| Case | Valid | Duration (s) | Normalized Score | normalized_quality | coverage_ratio |" in report
    assert "| Case | Overall | Verifier |" not in report
    assert "| case_0001 | true | 12.50 | 50.00 | 0.5000 | 0.7500 |" in report
    assert "| case_0002 | false | 20.00 | 0.0000 | - | - |" in report
    assert "profit_score_pct" not in report

