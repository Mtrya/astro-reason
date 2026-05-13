from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from experiments.skill_injection import aggregate, write_reports
from experiments.skill_injection import plot_scores


def _write_test_config(tmp_path: Path) -> Path:
    results_root = tmp_path / "results"
    config_path = tmp_path / "skill_test.yaml"
    config_path.write_text(
        "\n".join(
            [
                "name: skill_injection",
                "mode: batch",
                "benchmark: stereo_imaging",
                "split: test",
                "cases:",
                "  - case_0001",
                "conditions:",
                "  - compact_domain",
                "harnesses:",
                "  - opencode_dpsk",
                "timeout_seconds: 60",
                "batch:",
                "  max_concurrency: 1",
                "  max_retries: 0",
                "  skip_completed: true",
                "  retry_statuses: []",
                "resources: {}",
                "results:",
                f"  root: {results_root}",
                "  aggregate_dir: summaries",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return config_path


def _write_fake_run(config_path: Path, tmp_path: Path) -> None:
    run_dir = (
        tmp_path
        / "main_agentic"
        / "matrix"
        / "stereo_imaging"
        / "opencode_dpsk"
        / "test"
        / "case_0001"
    )
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "experiment": "skill_injection",
                "benchmark": "stereo_imaging",
                "split": "test",
                "condition": "no_skill",
                "harness": "opencode_dpsk",
                "case_id": "case_0001",
                "overall_status": "success",
                "agent_status": "success",
                "verifier_status": "valid",
                "duration_seconds": 12.5,
                "skills": [],
                "verifier": {
                    "valid": True,
                    "metrics": {
                        "coverage_ratio": 0.5,
                        "normalized_quality": 0.25,
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_skill_injection_aggregate_writes_rows_and_summary(tmp_path: Path) -> None:
    config_path = _write_test_config(tmp_path)
    _write_fake_run(config_path, tmp_path)

    assert aggregate.main(
        [
            "--config",
            str(config_path),
            "--main-agentic-root",
            str(tmp_path / "main_agentic" / "matrix"),
        ]
    ) == 0

    summary_path = tmp_path / "results" / "summaries" / "summary.json"
    runs_path = tmp_path / "results" / "summaries" / "runs.csv"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    with runs_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 2
    assert rows[0]["condition"] == "no_skill"
    assert rows[0]["source_experiment"] == "main_agentic"
    assert rows[0]["normalized_score_pct"] == "25"
    assert rows[1]["condition"] == "compact_domain"
    assert rows[1]["source_experiment"] == "skill_injection"
    assert rows[1]["artifact_state"] == "missing_artifact"
    assert rows[1]["normalized_score_pct"] == "0"
    assert summary["by_condition"]["no_skill"]["mean_normalized_score_pct"] == 25.0
    assert summary["by_condition"]["compact_domain"]["missing_count"] == 1
    assert summary["by_condition"]["compact_domain"]["mean_normalized_score_pct"] == 0.0


def test_skill_injection_write_reports_from_aggregate(tmp_path: Path) -> None:
    config_path = _write_test_config(tmp_path)
    _write_fake_run(config_path, tmp_path)
    aggregate.main(
        [
            "--config",
            str(config_path),
            "--main-agentic-root",
            str(tmp_path / "main_agentic" / "matrix"),
        ]
    )

    reports_dir = tmp_path / "reports"
    assert write_reports.main(["--config", str(config_path), "--reports-dir", str(reports_dir)]) == 0

    report = (reports_dir / "stereo_imaging.md").read_text(encoding="utf-8")
    assert "# Skill Injection" in report
    assert "no_skill" in report
    assert "compact_domain" in report
    assert "25" in report
    for spec in plot_scores.PLOT_SPECS:
        assert (reports_dir / spec.output_name).exists()
