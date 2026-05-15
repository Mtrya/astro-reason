from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from experiments.skill_injection import aggregate, write_reports
from experiments.skill_injection import plot_scores
from experiments._shared import score_normalization as score_norm


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


def test_skill_injection_aggregate_records_benchmark_specific_skills(tmp_path: Path) -> None:
    results_root = tmp_path / "results"
    config_path = tmp_path / "skill_scoped.yaml"
    config_path.write_text(
        "\n".join(
            [
                "name: skill_injection",
                "mode: batch",
                "benchmarks:",
                "  - benchmark: regional_coverage",
                "    split: test",
                "    cases: [case_0001]",
                "    conditions: [compact_domain]",
                "    harnesses: [opencode_dpsk]",
                "  - benchmark: relay_constellation",
                "    split: test",
                "    cases: [case_0001]",
                "    conditions: [compact_domain]",
                "    harnesses: [opencode_dpsk]",
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

    assert aggregate.main(
        [
            "--config",
            str(config_path),
            "--main-agentic-root",
            str(tmp_path / "main_agentic" / "matrix"),
        ]
    ) == 0

    runs_path = results_root / "summaries" / "runs.csv"
    with runs_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    skills_by_key = {
        (row["benchmark"], row["condition"]): row["skills"]
        for row in rows
    }

    assert skills_by_key[("regional_coverage", "compact_domain")] == "regional-coverage-compact-procedure"
    assert skills_by_key[("relay_constellation", "compact_domain")] == "relay-constellation-compact-procedure"


def _write_run_json(
    run_dir: Path,
    *,
    benchmark: str,
    condition: str,
    metrics: dict[str, object],
) -> None:
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "experiment": "skill_injection",
                "benchmark": benchmark,
                "split": "test",
                "condition": condition,
                "harness": "opencode_dpsk",
                "case_id": "case_0001",
                "overall_status": "success",
                "agent_status": "success",
                "verifier_status": "valid",
                "duration_seconds": 12.5,
                "skills": [] if condition == "no_skill" else ["placeholder-skill"],
                "verifier": {
                    "valid": True,
                    "metrics": metrics,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_skill_injection_aggregate_extracts_regional_and_relay_scores(tmp_path: Path) -> None:
    results_root = tmp_path / "results"
    config_path = tmp_path / "regional_relay.yaml"
    config_path.write_text(
        "\n".join(
            [
                "name: skill_injection",
                "mode: batch",
                "benchmarks:",
                "  - benchmark: regional_coverage",
                "    split: test",
                "    cases: [case_0001]",
                "    conditions: [compact_domain]",
                "    harnesses: [opencode_dpsk]",
                "  - benchmark: relay_constellation",
                "    split: test",
                "    cases: [case_0001]",
                "    conditions: [compact_domain]",
                "    harnesses: [opencode_dpsk]",
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
    main_agentic = tmp_path / "main_agentic" / "matrix"
    regional_metrics = {
        "weighted_coverage_ratio": 0.4,
        "coverage_ratio": 0.3,
        "num_actions": 10,
        "min_battery_wh": 500.0,
    }
    relay_metrics = {
        "service_fraction": 1.0,
        "worst_demand_service_fraction": 0.5,
        "num_added_satellites": 2,
        "mean_latency_ms": 100.0,
        "latency_p95_ms": 200.0,
    }
    _write_run_json(
        main_agentic / "regional_coverage" / "opencode_dpsk" / "test" / "case_0001",
        benchmark="regional_coverage",
        condition="no_skill",
        metrics=regional_metrics,
    )
    _write_run_json(
        main_agentic / "relay_constellation" / "opencode_dpsk" / "test" / "case_0001",
        benchmark="relay_constellation",
        condition="no_skill",
        metrics=relay_metrics,
    )

    assert aggregate.main(["--config", str(config_path), "--main-agentic-root", str(main_agentic)]) == 0

    with (results_root / "summaries" / "runs.csv").open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    regional_row = next(row for row in rows if row["benchmark"] == "regional_coverage" and row["condition"] == "no_skill")
    relay_row = next(row for row in rows if row["benchmark"] == "relay_constellation" and row["condition"] == "no_skill")
    regional_expected = score_norm.regional_coverage_score_pct(
        weighted_coverage_ratio=0.4,
        coverage_ratio=0.3,
        num_actions=10,
        min_battery_wh=500.0,
        **aggregate._regional_case_constants("test", "case_0001"),
    )
    relay_expected = score_norm.relay_constellation_score_pct(
        service_fraction=1.0,
        worst_demand_service_fraction=0.5,
        num_added_satellites=2,
        mean_latency_ms=100.0,
        latency_p95_ms=200.0,
        min_added_satellites=0,
        latency_cap_ms=1000.0,
        **aggregate._relay_case_constants("test", "case_0001"),
    )

    assert regional_row["weighted_coverage_ratio"] == "0.4"
    assert regional_row["num_actions"] == "10"
    assert abs(float(regional_row["normalized_score_pct"]) - regional_expected) < 1e-3
    assert relay_row["service_fraction"] == "1"
    assert relay_row["worst_demand_service_fraction"] == "0.5"
    assert abs(float(relay_row["normalized_score_pct"]) - relay_expected) < 1e-3

    summary = json.loads((results_root / "summaries" / "summary.json").read_text(encoding="utf-8"))
    assert summary["by_benchmark_condition"]["regional_coverage/compact_domain"]["mean_normalized_score_pct"] == 0.0
    assert summary["by_benchmark_condition"]["relay_constellation/compact_domain"]["mean_normalized_score_pct"] == 0.0


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


def test_skill_injection_write_reports_with_regional_and_relay_metrics(tmp_path: Path) -> None:
    results_root = tmp_path / "results"
    config_path = tmp_path / "regional_relay_reports.yaml"
    config_path.write_text(
        "\n".join(
            [
                "name: skill_injection",
                "mode: batch",
                "benchmarks:",
                "  - benchmark: regional_coverage",
                "    split: test",
                "    cases: [case_0001]",
                "    conditions: [compact_domain]",
                "    harnesses: [opencode_dpsk]",
                "  - benchmark: relay_constellation",
                "    split: test",
                "    cases: [case_0001]",
                "    conditions: [compact_domain]",
                "    harnesses: [opencode_dpsk]",
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
    main_agentic = tmp_path / "main_agentic" / "matrix"
    _write_run_json(
        main_agentic / "regional_coverage" / "opencode_dpsk" / "test" / "case_0001",
        benchmark="regional_coverage",
        condition="no_skill",
        metrics={
            "weighted_coverage_ratio": 0.4,
            "coverage_ratio": 0.3,
            "num_actions": 10,
            "min_battery_wh": 500.0,
        },
    )
    _write_run_json(
        main_agentic / "relay_constellation" / "opencode_dpsk" / "test" / "case_0001",
        benchmark="relay_constellation",
        condition="no_skill",
        metrics={
            "service_fraction": 1.0,
            "worst_demand_service_fraction": 0.5,
            "num_added_satellites": 2,
            "mean_latency_ms": 100.0,
            "latency_p95_ms": 200.0,
        },
    )
    aggregate.main(["--config", str(config_path), "--main-agentic-root", str(main_agentic)])

    reports_dir = tmp_path / "reports"
    assert write_reports.main(["--config", str(config_path), "--reports-dir", str(reports_dir)]) == 0

    regional_report = (reports_dir / "regional_coverage.md").read_text(encoding="utf-8")
    relay_report = (reports_dir / "relay_constellation.md").read_text(encoding="utf-8")
    assert "Mean Weighted Coverage" in regional_report
    assert "Mean Actions" in regional_report
    assert "Weighted Coverage" in regional_report
    assert "Mean Service" in relay_report
    assert "Mean Worst Demand" in relay_report
    assert "P95 Latency" in relay_report
    assert (reports_dir / "regional_coverage_opencode_dpsk_scores.png").exists()
    assert (reports_dir / "relay_constellation_opencode_dpsk_scores.png").exists()
