from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from experiments._shared import aggregate, trace_viewer, workspace, write_reports


def test_shared_analysis_modules_expose_family_neutral_helpers() -> None:
    profile = SimpleNamespace(
        score_metrics=(
            SimpleNamespace(
                name="score",
                path="metrics.score",
                direction="maximize",
                role="primary",
            ),
        ),
        flag_metrics=(),
    )

    summary = aggregate.build_group_summary(
        records=[
            {
                "artifact_state": "present",
                "overall_status": "success",
                "agent_status": "success",
                "verifier_status": "valid",
                "valid": True,
                "metrics": {"score": 10},
                "processed_metrics": {},
                "flags": {},
            }
        ],
        profile=profile,
        benchmark="synthetic",
        harness="example_harness",
    )

    event = trace_viewer._event(
        source="synthetic",
        event_type="message",
        role="assistant",
        title="Assistant",
        text="Wrote solution.json and verifier says VALID.",
        seq=0,
    )

    assert summary["primary_metric"]["stats"]["mean"] == 10.0
    assert "solution_json" in event["tags"]
    assert "verifier" in event["tags"]
    assert workspace.render_template("{case_id} {unknown}", {"case_id": "case_0001"}) == (
        "case_0001 {unknown}"
    )
    assert write_reports.format_value("12.5") == "12.50"
