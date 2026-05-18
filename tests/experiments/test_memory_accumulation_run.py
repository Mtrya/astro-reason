from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from experiments.memory_accumulation import aggregate, plot_scores, run, write_reports


def _write_test_config(tmp_path: Path) -> Path:
    results_root = tmp_path / "results"
    fragments_root = tmp_path / "fragments"
    config_path = tmp_path / "memory_test.yaml"
    config_path.write_text(
        "\n".join(
            [
                "name: memory_accumulation",
                "mode: batch",
                "condition: test_condition",
                "accumulation:",
                "  harnesses:",
                "    - codex",
                "    - opencode_dpsk",
                "  train_cases:",
                "    - stereo_imaging/train/case_0001",
                "    - revisit_constellation/train/case_0001",
                "evaluation:",
                "  memory_sources:",
                "    - codex",
                "    - opencode_dpsk",
                "  harnesses:",
                "    - opencode_dpsk",
                "  benchmarks:",
                "    - benchmark: satnet",
                "      split: test",
                "      cases:",
                "        - W10_2018",
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
                "fragments:",
                f"  root: {fragments_root}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return config_path


def _write_satnet_memory_and_baseline_runs(tmp_path: Path) -> None:
    memory_run_dir = (
        tmp_path
        / "results"
        / "memory_test"
        / "eval"
        / "test_condition"
        / "codex"
        / "satnet"
        / "opencode_dpsk"
        / "test"
        / "W10_2018"
    )
    memory_run_dir.mkdir(parents=True)
    (memory_run_dir / "run.json").write_text(
        json.dumps(
            {
                "experiment": "memory_accumulation",
                "phase": "eval",
                "condition": "test_condition",
                "memory_source": "codex",
                "benchmark": "satnet",
                "split": "test",
                "harness": "opencode_dpsk",
                "case_id": "W10_2018",
                "overall_status": "success",
                "agent_status": "success",
                "verifier_status": "valid",
                "verifier": {
                    "valid": True,
                    "metrics": {
                        "u_rms": 0.25,
                        "u_max": 0.5,
                        "score_hours": 10.0,
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    baseline_dir = tmp_path / "main_agentic" / "matrix" / "satnet" / "opencode_dpsk" / "test" / "W10_2018"
    baseline_dir.mkdir(parents=True)
    (baseline_dir / "run.json").write_text(
        json.dumps(
            {
                "experiment": "main_agentic",
                "benchmark": "satnet",
                "split": "test",
                "harness": "opencode_dpsk",
                "case_id": "W10_2018",
                "overall_status": "success",
                "agent_status": "success",
                "verifier_status": "valid",
                "verifier": {
                    "valid": True,
                    "metrics": {
                        "u_rms": 0.5,
                        "u_max": 1.0,
                        "score_hours": 5.0,
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_default_config_builds_train_and_eval_axes() -> None:
    config = run.load_family_config(run.DEFAULT_CONFIG)
    train_items = run.build_train_items(config, harnesses=("codex",))
    eval_items = run.build_eval_items(
        config,
        benchmarks=("satnet",),
        memory_sources=("codex",),
        harnesses=("opencode_dpsk",),
        cases=("W10_2018",),
    )

    assert len(train_items) == 12
    assert train_items[0].phase == "train"
    assert train_items[0].memory_source == "codex"
    assert train_items[0].benchmark == "stereo_imaging"
    assert train_items[0].split == "train"
    assert any(spec.target.as_posix() == "/app/workspace/memory" for spec in train_items[0].base_item.assemble)
    assert any(
        spec.source.as_posix().endswith("experiments/_fragments/skills/memory_accumulation/skill-writing")
        and spec.target.as_posix() == "/home/korolev/.codex/skills/skill-writing"
        for spec in train_items[0].base_item.assemble
    )

    assert len(eval_items) == 1
    assert eval_items[0].phase == "eval"
    assert eval_items[0].memory_source == "codex"
    assert eval_items[0].harness == "opencode_dpsk"
    assert any(
        spec.source.as_posix().endswith("memory_accumulation/cross_benchmark_round_robin_v1/codex/memory")
        for spec in eval_items[0].base_item.assemble
    )


def test_train_and_eval_use_memory_specific_agents_fragments() -> None:
    config = run.load_family_config(run.DEFAULT_CONFIG)
    (train_item,) = run.build_train_items(config, harnesses=("codex",))[:1]
    (opencode_train_item,) = run.build_train_items(config, harnesses=("opencode_dpsk",))[:1]
    (eval_item,) = run.build_eval_items(
        config,
        benchmarks=("satnet",),
        memory_sources=("codex",),
        harnesses=("codex",),
        cases=("W10_2018",),
    )

    train_agents = [spec for spec in train_item.base_item.assemble if spec.target.as_posix() == "/app/workspace/AGENTS.md"]
    opencode_train_agents = [
        spec for spec in opencode_train_item.base_item.assemble if spec.target.as_posix() == "/app/workspace/AGENTS.md"
    ]
    eval_agents = [spec for spec in eval_item.base_item.assemble if spec.target.as_posix() == "/app/workspace/AGENTS.md"]

    assert train_agents[0].source.name == "AGENTS.memory_accumulation.train.md"
    assert opencode_train_agents[0].source.name == "AGENTS.memory_accumulation.train.opencode.md"
    assert eval_agents[0].source.name == "AGENTS.memory_accumulation.eval.md"


def test_promote_fragments_copies_train_state_with_manifest(tmp_path: Path) -> None:
    config = run.load_family_config(_write_test_config(tmp_path))
    state = config.results.root / config.config_path.stem / "train_state" / "test_condition" / "codex"
    (state / "memory").mkdir(parents=True)
    (state / ".agents" / "skills" / "learned-skill").mkdir(parents=True)
    (state / "memory" / "notes.md").write_text("note\n", encoding="utf-8")
    (state / ".agents" / "skills" / "learned-skill" / "SKILL.md").write_text("skill\n", encoding="utf-8")

    run.promote_fragments(config, harnesses=("codex",), force=False)

    target = config.fragments_root / "test_condition" / "codex"
    assert (target / "memory" / "notes.md").read_text(encoding="utf-8") == "note\n"
    assert (target / ".agents" / "skills" / "learned-skill" / "SKILL.md").exists()
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_harness"] == "codex"
    assert manifest["train_cases"] == [
        "stereo_imaging/train/case_0001",
        "revisit_constellation/train/case_0001",
    ]


def test_memory_accumulation_aggregate_collects_baseline_and_memory_rows(tmp_path: Path) -> None:
    config_path = _write_test_config(tmp_path)
    _write_satnet_memory_and_baseline_runs(tmp_path)

    assert aggregate.main(
        [
            "--config",
            str(config_path),
            "--main-agentic-root",
            str(tmp_path / "main_agentic" / "matrix"),
        ]
    ) == 0

    rows = (tmp_path / "results" / "summaries" / "runs.csv").read_text(encoding="utf-8")
    summary = json.loads((tmp_path / "results" / "summaries" / "summary.json").read_text(encoding="utf-8"))
    assert "no_memory,none,opencode_dpsk" in rows
    assert "test_condition,codex,opencode_dpsk" in rows
    assert summary["by_memory_source"]["codex"]["mean_normalized_score_pct"] == 68.75
    assert summary["by_memory_source"]["none"]["mean_normalized_score_pct"] == 37.5


def test_memory_accumulation_reports_and_plots_from_aggregate(tmp_path: Path) -> None:
    config_path = _write_test_config(tmp_path)
    _write_satnet_memory_and_baseline_runs(tmp_path)
    aggregate.main(
        [
            "--config",
            str(config_path),
            "--main-agentic-root",
            str(tmp_path / "main_agentic" / "matrix"),
        ]
    )

    reports_dir = tmp_path / "reports"
    assert plot_scores.main(["--config", str(config_path), "--reports-dir", str(reports_dir)]) == 0
    assert write_reports.main(["--config", str(config_path), "--reports-dir", str(reports_dir)]) == 0

    overview = (reports_dir / "overview.md").read_text(encoding="utf-8")
    satnet = (reports_dir / "satnet.md").read_text(encoding="utf-8")
    assert "# Memory Accumulation" in overview
    assert "memory_transfer_delta.png" in overview
    assert "| satnet | codex | opencode_dpsk | 1 | 37.50 | 68.75 | 31.25 | 1 | 0 |" in overview
    assert "# SatNet" in satnet
    assert "score_hours" in satnet
    for output_name in plot_scores.PLOT_OUTPUTS:
        assert (reports_dir / output_name).exists()


def test_memory_accumulation_analysis_driver_wires_reports_and_plots() -> None:
    result = subprocess.run(
        [
            str(REPO_ROOT / "scripts" / "run_agentic_analysis.sh"),
            "--family",
            "memory_accumulation",
            "--dry-run",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
        text=True,
    )

    assert "experiments/memory_accumulation/aggregate.py" in result.stdout
    assert "experiments/memory_accumulation/plot_scores.py" in result.stdout
    assert "experiments/memory_accumulation/write_reports.py" in result.stdout


def test_memory_accumulation_accepts_revisit_is_valid_verifier_payload(
    monkeypatch,
    tmp_path: Path,
) -> None:
    item = SimpleNamespace(benchmark="revisit_constellation", split="train", case_id="case_0001")

    monkeypatch.setattr(run, "_verifier_command", lambda *_args: ["verifier"])
    monkeypatch.setattr(
        run,
        "_run_capture",
        lambda *_args, **_kwargs: (
            0,
            json.dumps({"is_valid": True, "metrics": {"threshold_violation_count": 0}}),
            "",
            True,
        ),
    )

    status, payload = run._external_verifier(item, tmp_path, solution_present=True)

    assert status == "valid"
    assert payload["valid"] is True
    assert payload["is_valid"] is True


def test_memory_accumulation_accepts_spot5_compact_verifier_payload(
    monkeypatch,
    tmp_path: Path,
) -> None:
    item = SimpleNamespace(benchmark="spot5", split="train", case_id="507")

    monkeypatch.setattr(run, "_verifier_command", lambda *_args: ["verifier"])
    monkeypatch.setattr(
        run,
        "_run_capture",
        lambda *_args, **_kwargs: (0, "VALID: profit=15137, weight=0\n", "", True),
    )

    status, payload = run._external_verifier(item, tmp_path, solution_present=True)

    assert status == "valid"
    assert payload["valid"] is True
    assert payload["metrics"]["computed_profit"] == 15137
    assert payload["metrics"]["computed_weight"] == 0


def test_memory_accumulation_requests_verbose_satnet_metrics() -> None:
    command = run._verifier_command(
        "satnet",
        Path("benchmarks/satnet/dataset/cases/test/W10_2018"),
        Path("solution.json"),
    )

    assert command[-1] == "--verbose"


def test_memory_accumulation_aggregate_backfills_satnet_verbose_metrics(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config_path = _write_test_config(tmp_path)
    _write_satnet_memory_and_baseline_runs(tmp_path)
    memory_run_dir = (
        tmp_path
        / "results"
        / "memory_test"
        / "eval"
        / "test_condition"
        / "codex"
        / "satnet"
        / "opencode_dpsk"
        / "test"
        / "W10_2018"
    )
    run_payload = json.loads((memory_run_dir / "run.json").read_text(encoding="utf-8"))
    run_payload["verifier"]["metrics"]["u_rms"] = None
    run_payload["verifier"]["metrics"]["u_max"] = None
    run_payload["verifier"]["metrics"]["n_satisfied_requests"] = None
    (memory_run_dir / "run.json").write_text(json.dumps(run_payload) + "\n", encoding="utf-8")
    (memory_run_dir / "solution.json").write_text("[]\n", encoding="utf-8")

    monkeypatch.setattr(aggregate.family_run, "_verifier_command", lambda *_args: ["verifier", "--verbose"])
    monkeypatch.setattr(
        aggregate.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            stdout=(
                "Status: VALID\n"
                "U_rms: 0.250000\n"
                "U_max: 0.500000\n"
                "Total tracking hours: 10.0000\n"
                "Tracks: 12\n"
                "Satisfied requests: 9\n"
            ),
            returncode=0,
        ),
    )

    assert aggregate.main(
        [
            "--config",
            str(config_path),
            "--main-agentic-root",
            str(tmp_path / "main_agentic" / "matrix"),
        ]
    ) == 0

    rows = (tmp_path / "results" / "summaries" / "runs.csv").read_text(encoding="utf-8")
    assert "0.25,0.5,12,68.75" in rows
    assert ",9,0.25,0.5," in rows


def test_memory_accumulation_counts_valid_timeout_solution_as_success() -> None:
    assert run._overall_status("timeout", "valid") == "success"
