from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from experiments.verifier_exposure import aggregate, write_reports


def _write_run(path: Path, *, harness: str, coverage: float, quality: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "harness": harness,
                "case_id": "case_0001",
                "overall_status": "success",
                "agent_status": "success",
                "verifier_status": "valid",
                "duration_seconds": 12.5,
                "verifier": {
                    "valid": True,
                    "metrics": {
                        "coverage_ratio": coverage,
                        "normalized_quality": quality,
                    },
                },
            }
        ),
        encoding="utf-8",
    )


def test_aggregate_records_include_opaque_and_solver_baselines(tmp_path: Path) -> None:
    results_root = tmp_path / "verifier_exposure"
    main_agentic_root = tmp_path / "main_agentic"
    config_path = tmp_path / "default.yaml"
    config = {
        "benchmark": "stereo_imaging",
        "split": "test",
        "exposures": ["none"],
        "harnesses": ["codex"],
        "cases": ["case_0001"],
        "results": {"root": str(results_root), "aggregate_dir": "summaries"},
    }
    baseline_data = {
        "rows": [
            {
                "benchmark": "stereo_imaging",
                "method": "stereo_solver",
                "split": "test",
                "case_id": "case_0001",
                "metrics": {
                    "coverage_ratio": 0.75,
                    "normalized_quality": 0.8,
                    "solve_s": 42,
                },
            }
        ]
    }
    _write_run(
        results_root / "default" / "none" / "stereo_imaging" / "codex" / "test" / "case_0001" / "run.json",
        harness="codex",
        coverage=0.25,
        quality=0.5,
    )
    _write_run(
        main_agentic_root / "stereo_imaging" / "codex" / "test" / "case_0001" / "run.json",
        harness="codex",
        coverage=0.4,
        quality=0.6,
    )

    rows = aggregate._records(
        config,
        config_path,
        baseline_data=baseline_data,
        baseline_path=tmp_path / "main_solver.yaml",
        main_agentic_root=main_agentic_root,
    )
    summary = aggregate._summary(rows)

    assert [(row["kind"], row["source_experiment"], row["exposure"], row["system"]) for row in rows] == [
        ("agent", "verifier_exposure", "none", "codex"),
        ("agent", "main_agentic", "opaque", "codex"),
        ("solver", "main_solver", "solver", "stereo_solver"),
    ]
    assert summary["schema_version"] == 2
    assert summary["by_exposure"]["opaque"]["mean_coverage_ratio"] == 0.4
    assert summary["by_exposure"]["solver"]["mean_normalized_quality"] == 0.8
    assert summary["by_exposure_system"]["solver/stereo_solver"]["kind"] == "solver"


def test_write_report_renders_exposure_and_case_tables(tmp_path: Path) -> None:
    summary = {
        "schema_version": 2,
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
        "by_exposure_system": {
            "none/codex": {
                "kind": "agent",
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
            "kind": "agent",
            "system": "codex",
            "harness": "codex",
            "case_id": "case_0001",
            "artifact_state": "present",
            "overall_status": "success",
            "verifier_status": "valid",
            "valid": "True",
            "duration_seconds": "12.5",
            "coverage_ratio": "0.25",
            "normalized_quality": "0.75",
        },
        {
            "exposure": "none",
            "kind": "agent",
            "system": "opencode_dpsk",
            "harness": "opencode_dpsk",
            "case_id": "case_0002",
            "artifact_state": "missing_or_malformed",
            "overall_status": "missing_artifact",
            "verifier_status": "missing_artifact",
            "valid": "",
            "duration_seconds": "",
            "coverage_ratio": "",
            "normalized_quality": "",
        },
    ]

    report_path = write_reports._write_report(summary=summary, rows=rows, reports_dir=tmp_path)

    report = report_path.read_text(encoding="utf-8")
    assert report_path == tmp_path / "stereo_imaging.md"
    assert "| Exposure | Runs | Valid | Valid Rate | Mean Coverage | Mean Quality |" in report
    assert "| none | 2 | 1 | 0.5000 | 0.2500 | 0.7500 | missing_artifact: 1, success: 1 |" in report
    assert "| none | agent | codex | 1 | 1 | 1.0000 | 0.2500 | 0.7500 | success: 1 |" in report
    assert "| none | agent | codex | case_0001 | present | success | valid | true | 12.50 |" in report
    assert "| none | agent | opencode_dpsk | case_0002 | missing_or_malformed | missing_artifact |" in report
