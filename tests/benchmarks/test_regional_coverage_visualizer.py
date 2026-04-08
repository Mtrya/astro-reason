"""Small smoke tests for the regional_coverage development visualizer."""

from __future__ import annotations

from pathlib import Path
import json

from benchmarks.regional_coverage.visualizer.run import render_inspection, render_overview


REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "benchmarks" / "regional_coverage" / "dataset"
CASE_0001_DIR = DATASET_DIR / "cases" / "case_0001"
EXAMPLE_SOLUTION_PATH = DATASET_DIR / "example_solution.json"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_render_overview_writes_html(tmp_path: Path) -> None:
    out_path = tmp_path / "overview.png"
    written = render_overview(
        CASE_0001_DIR,
        out_path,
        ground_track_step_s=900.0,
        max_ground_tracks=3,
    )

    assert written == out_path
    assert out_path.is_file()
    assert out_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_render_inspection_example_solution_writes_summary_and_manifest(tmp_path: Path) -> None:
    out_dir = tmp_path / "inspect"
    written_dir = render_inspection(CASE_0001_DIR, EXAMPLE_SOLUTION_PATH, out_dir)

    assert written_dir == out_dir
    summary_path = out_dir / "summary.html"
    manifest_path = out_dir / "manifest.json"
    assert summary_path.is_file()
    assert manifest_path.is_file()

    manifest = _read_json(manifest_path)
    assert manifest["case_id"] == "case_0001"
    assert manifest["verifier_valid"] is True
    assert manifest["metrics"]["coverage_ratio"] == 0.0
    assert manifest["selected_action_indices"] == []


def test_render_inspection_invalid_solution_records_violations(tmp_path: Path) -> None:
    out_dir = tmp_path / "invalid"
    solution_path = tmp_path / "invalid_solution.json"
    solution_path.write_text(
        json.dumps(
            {
                "actions": [
                    {
                        "type": "strip_observation",
                        "satellite_id": "missing_sat",
                        "start_time": "2025-07-17T00:00:00Z",
                        "duration_s": 20,
                        "roll_deg": 20.0,
                    }
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    render_inspection(CASE_0001_DIR, solution_path, out_dir)

    manifest = _read_json(out_dir / "manifest.json")
    assert manifest["verifier_valid"] is False
    assert any("unknown satellite_id" in violation for violation in manifest["verifier_violations"])
    assert manifest["actions"][0]["accepted_for_schedule"] is False
    assert (out_dir / "summary.html").is_file()
    assert (out_dir / "action_000.html").is_file()
