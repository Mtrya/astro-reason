from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from experiments.temporal_robustness import trace_viewer as temporal_trace_viewer
from experiments.verifier_exposure import trace_viewer as verifier_trace_viewer


def _read_runs_js(path: Path) -> list[dict[str, object]]:
    text = path.read_text(encoding="utf-8")
    payload = text.split("=", maxsplit=1)[1].strip().removesuffix(";")
    data = json.loads(payload)
    assert isinstance(data, list)
    return data


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_codex_rollout(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "type": "response_item",
            "timestamp": "2026-05-10T00:00:00.000Z",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Wrote solution.json"}],
            },
        }
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_temporal_trace_viewer_builds_split_scoped_runs(tmp_path: Path) -> None:
    config_path = tmp_path / "default.yaml"
    root = tmp_path / "results"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark": "aeossp_standard",
                "splits": ["test_horizon_2022"],
                "cases": ["case_0001"],
                "harnesses": ["codex"],
                "results": {"root": str(root), "aggregate_dir": "summaries"},
            }
        ),
        encoding="utf-8",
    )
    run_dir = root / "default" / "test_horizon_2022" / "aeossp_standard" / "codex" / "case_0001"
    _write_json(
        run_dir / "run.json",
        {
            "overall_status": "success",
            "agent_status": "success",
            "verifier_status": "valid",
            "duration_seconds": 12,
            "verifier": {"valid": True, "metrics": {"WCR": 0.5}},
        },
    )
    _write_codex_rollout(
        run_dir / "session_logs" / "sessions" / "2026" / "05" / "10" / "rollout-1.jsonl"
    )

    run_count, event_count = temporal_trace_viewer._build_trace_viewer(
        config_path=config_path,
        output_dir=tmp_path / "viewer",
        preview_chars=80,
        expanded_chars=500,
    )

    runs = _read_runs_js(tmp_path / "viewer" / "data" / "runs.js")
    assert run_count == 1
    assert event_count == 1
    assert runs[0]["split"] == "test_horizon_2022"
    assert runs[0]["case_id"] == "test_horizon_2022/case_0001"
    assert runs[0]["raw_case_id"] == "case_0001"
    assert runs[0]["trace_kind"] == "codex"
    assert runs[0]["event_counts"] == {"message": 1}


def test_verifier_exposure_trace_viewer_builds_exposure_scoped_runs(tmp_path: Path) -> None:
    config_path = tmp_path / "default.yaml"
    root = tmp_path / "results"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark": "stereo_imaging",
                "split": "test",
                "exposures": ["none"],
                "cases": ["case_0001"],
                "harnesses": ["codex"],
                "results": {"root": str(root), "aggregate_dir": "summaries"},
            }
        ),
        encoding="utf-8",
    )
    run_dir = root / "default" / "none" / "stereo_imaging" / "codex" / "test" / "case_0001"
    _write_json(
        run_dir / "run.json",
        {
            "overall_status": "success",
            "agent_status": "success",
            "verifier_status": "valid",
            "duration_seconds": 12,
            "verifier": {
                "valid": True,
                "metrics": {"coverage_ratio": 0.25, "normalized_quality": 0.75},
            },
        },
    )
    _write_codex_rollout(
        run_dir / "session_logs" / "sessions" / "2026" / "05" / "10" / "rollout-1.jsonl"
    )

    run_count, event_count = verifier_trace_viewer._build_trace_viewer(
        config_path=config_path,
        output_dir=tmp_path / "viewer",
        preview_chars=80,
        expanded_chars=500,
    )

    runs = _read_runs_js(tmp_path / "viewer" / "data" / "runs.js")
    assert run_count == 1
    assert event_count == 1
    assert runs[0]["exposure"] == "none"
    assert runs[0]["case_id"] == "none/case_0001"
    assert runs[0]["raw_case_id"] == "case_0001"
    assert runs[0]["trace_kind"] == "codex"
    assert runs[0]["event_counts"] == {"message": 1}
