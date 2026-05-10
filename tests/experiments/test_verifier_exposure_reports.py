from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from experiments.verifier_exposure import write_reports


def test_write_report_renders_exposure_and_case_tables(tmp_path: Path) -> None:
    summary = {
        "schema_version": 1,
        "experiment": "verifier_exposure",
        "by_exposure": {
            "none": {
                "run_count": 2,
                "valid_count": 1,
                "valid_rate": 0.5,
                "overall_status_counts": {"success": 1, "missing_artifact": 1},
                "verifier_status_counts": {"valid": 1, "missing_artifact": 1},
                "mean_coverage_ratio": 0.25,
                "mean_normalized_quality": 0.75,
            }
        },
        "by_exposure_harness": {
            "none/codex": {
                "run_count": 1,
                "valid_count": 1,
                "valid_rate": 1.0,
                "overall_status_counts": {"success": 1},
                "mean_coverage_ratio": 0.25,
                "mean_normalized_quality": 0.75,
            }
        },
    }
    rows = [
        {
            "exposure": "none",
            "harness": "codex",
            "case_id": "case_0001",
            "artifact_state": "present",
            "overall_status": "success",
            "verifier_status": "valid",
            "valid": "True",
            "coverage_ratio": "0.25",
            "normalized_quality": "0.75",
        },
        {
            "exposure": "none",
            "harness": "opencode_dpsk",
            "case_id": "case_0002",
            "artifact_state": "missing_or_malformed",
            "overall_status": "missing_artifact",
            "verifier_status": "missing_artifact",
            "valid": "",
            "coverage_ratio": "",
            "normalized_quality": "",
        },
    ]

    report_path = write_reports._write_report(summary=summary, rows=rows, reports_dir=tmp_path)

    report = report_path.read_text(encoding="utf-8")
    assert report_path == tmp_path / "stereo_imaging.md"
    assert "| Exposure | Runs | Valid | Valid Rate | Mean Coverage | Mean Quality |" in report
    assert "| none | 2 | 1 | 0.5000 | 0.2500 | 0.7500 | missing_artifact: 1, success: 1 |" in report
    assert "| none | codex | 1 | 1 | 1.0000 | 0.2500 | 0.7500 | success: 1 |" in report
    assert "| none | codex | case_0001 | present | success | valid | true | 0.2500 | 0.7500 |" in report
    assert "| none | opencode_dpsk | case_0002 | missing_or_malformed | missing_artifact |" in report
