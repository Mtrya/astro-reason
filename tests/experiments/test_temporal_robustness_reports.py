from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from experiments.temporal_robustness import aggregate, write_reports


def _row(
    *,
    kind: str = "agent",
    system: str = "codex",
    split: str,
    case_id: str = "case_0001",
    wcr: float,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "system": system,
        "harness": system,
        "split": split,
        "case_id": case_id,
        "valid": True,
        "status": "success",
        "overall_status": "success",
        "verifier_status": "valid",
        "WCR": wcr,
        "CR": wcr + 0.1,
        "TAT": 1000.0 + wcr,
        "PC": 2000.0 + wcr,
    }


def test_report_summary_keeps_same_case_id_split_scoped(tmp_path: Path) -> None:
    rows = [
        _row(split="test", wcr=1.0),
        _row(split="test_horizon_2022", wcr=10.0),
        _row(
            kind="solver",
            system="aeossp_standard_greedy_lns",
            split="test",
            wcr=2.0,
        ),
        _row(
            kind="solver",
            system="aeossp_standard_greedy_lns",
            split="test_horizon_2022",
            wcr=20.0,
        ),
    ]

    write_reports._write_report(rows=rows, reports_dir=tmp_path, config={"cases": ["case_0001"]})

    report = (tmp_path / "aeossp_standard.md").read_text(encoding="utf-8")

    assert "Case identifiers are split-scoped" in report
    assert "| System | Kind | test Runs | test Valid | test Mean WCR |" in report
    assert "| codex | agent | 1 | 1 | 1.0000 | 1.1000 | 1001.0 | 2001.0 | 1 | 1 | 10.00 |" in report
    assert "| greedy_lns | solver | 1 | 1 | 2.0000 | 2.1000 | 1002.0 | 2002.0 | 1 | 1 | 20.00 |" in report
    assert "## case_0001" not in report
    assert "## test Cases" in report
    assert "## test_horizon_2022 Cases" in report


def test_aggregate_harness_summary_is_split_scoped() -> None:
    rows = [
        _row(split="test", wcr=1.0),
        _row(split="test_horizon_2022", wcr=10.0),
    ]

    summary = aggregate._summary(rows)

    assert summary["schema_version"] == 2
    assert "by_harness" not in summary
    assert summary["by_harness_split"]["codex/test"]["mean_WCR"] == pytest.approx(1.0)
    assert summary["by_harness_split"]["codex/test_horizon_2022"]["mean_WCR"] == pytest.approx(10.0)
