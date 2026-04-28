"""Smoke tests for the SatNet visualizer."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from benchmarks.satnet.visualizer.run import (
    _availability_counts,
    render_availability,
    render_schedule,
)
from benchmarks.satnet.verifier import load_case


REPO_ROOT = Path(__file__).resolve().parents[2]
CASE_DIR = REPO_ROOT / "benchmarks" / "satnet" / "dataset" / "cases" / "test" / "W10_2018"
SOLUTION_PATH = REPO_ROOT / "tests" / "fixtures" / "satnet_mock_solutions" / "W10_2018_solution.json"


def _assert_png(path: Path) -> None:
    assert path.is_file()
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_availability_counts_match_expected_shape() -> None:
    instance = load_case(CASE_DIR)

    antennas, counts = _availability_counts(instance)

    assert counts.shape == (len(antennas), 7)
    assert "DSS-34" in antennas
    assert counts.sum() > 0


def test_render_availability_writes_png(tmp_path: Path) -> None:
    out_path = tmp_path / "availability.png"

    written = render_availability(CASE_DIR, out_path)

    assert written == out_path
    _assert_png(out_path)


def test_render_schedule_writes_satisfaction_and_timeline(tmp_path: Path) -> None:
    satisfaction_path, timeline_path = render_schedule(CASE_DIR, SOLUTION_PATH, tmp_path)

    assert satisfaction_path.name == "satisfaction.png"
    assert timeline_path.name == "timeline.png"
    _assert_png(satisfaction_path)
    _assert_png(timeline_path)


def test_visualizer_cli_named_flags(tmp_path: Path) -> None:
    availability_path = tmp_path / "availability.png"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "benchmarks.satnet.visualizer.run",
            "availability",
            "--case-dir",
            str(CASE_DIR),
            "--out-path",
            str(availability_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    _assert_png(availability_path)
