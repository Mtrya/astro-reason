from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from experiments.main_agentic import plan


def _write_batch_config(tmp_path: Path, *, batch_extra: str = "") -> Path:
    config_path = tmp_path / "matrix.yaml"
    config_path.write_text(
        "\n".join(
            [
                "name: test_matrix",
                "mode: batch",
                "benchmarks:",
                "  - satnet",
                "harnesses:",
                "  - codex",
                "defaults:",
                "  split: test",
                "  timeout_seconds: 7200",
                "batch:",
                "  max_concurrency: 2",
                "  max_retries: 1",
                "  skip_completed: true",
                "  retry_statuses:",
                "    - runner_error",
                "    - timeout",
                batch_extra.rstrip(),
                "resources: {}",
                "results:",
                "  root: results/agent_runs/experiments/main_agentic",
                "  aggregate_dir: summaries",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return config_path


def test_load_batch_config_defaults_harness_cooldown_to_zero(tmp_path: Path) -> None:
    config = plan.load_batch_config(_write_batch_config(tmp_path))

    assert config.batch.harness_cooldown_seconds == 0


def test_load_batch_config_parses_harness_cooldown(tmp_path: Path) -> None:
    config = plan.load_batch_config(
        _write_batch_config(tmp_path, batch_extra="  harness_cooldown_seconds: 30")
    )

    assert config.batch.harness_cooldown_seconds == 30


def test_load_batch_config_rejects_negative_harness_cooldown(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="harness_cooldown_seconds"):
        plan.load_batch_config(
            _write_batch_config(tmp_path, batch_extra="  harness_cooldown_seconds: -1")
        )


def test_load_batch_config_rejects_boolean_harness_cooldown(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="harness_cooldown_seconds"):
        plan.load_batch_config(
            _write_batch_config(tmp_path, batch_extra="  harness_cooldown_seconds: true")
        )


def test_build_batch_plan_applies_harness_cooldown_override() -> None:
    batch_plan = plan.build_batch_plan(
        config_path=plan.DEFAULT_BATCH_CONFIG,
        benchmark_filters=("satnet",),
        harness_filters=("codex",),
        split_override="test",
        case_filters=("W10_2018",),
        harness_cooldown_override=45,
    )

    assert batch_plan.config.batch.harness_cooldown_seconds == 45
    assert "Harness cooldown seconds: 45" in plan.describe_batch_preview(
        plan.build_batch_preview(batch_plan)
    )


def test_build_batch_plan_rejects_negative_harness_cooldown_override() -> None:
    with pytest.raises(SystemExit, match="--harness-cooldown"):
        plan.build_batch_plan(
            config_path=plan.DEFAULT_BATCH_CONFIG,
            benchmark_filters=("satnet",),
            harness_filters=("codex",),
            split_override="test",
            case_filters=("W10_2018",),
            harness_cooldown_override=-1,
        )
