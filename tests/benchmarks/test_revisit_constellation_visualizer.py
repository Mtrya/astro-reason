"""Smoke tests for the revisit_constellation visualizer."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from benchmarks.revisit_constellation.visualizer.run import (
    render_overview,
    render_solution,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "revisit_constellation"
CASE_DIR = FIXTURE_DIR / "single_observation_valid"
SOLUTION_PATH = CASE_DIR / "solution.json"


def _assert_png(path: Path) -> None:
    assert path.is_file()
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_render_overview_writes_png(tmp_path: Path) -> None:
    out_path = tmp_path / "overview.png"

    written = render_overview(CASE_DIR, out_path)

    assert written == out_path
    _assert_png(out_path)


def test_render_solution_writes_target_pages(tmp_path: Path) -> None:
    written = render_solution(
        CASE_DIR,
        SOLUTION_PATH,
        tmp_path,
        max_targets=1,
        max_actions_per_target=1,
        track_window_min=10.0,
        track_step_s=120.0,
    )

    assert len(written) == 1
    assert written[0].name.startswith("target_01_t1")
    _assert_png(written[0])


def test_visualizer_cli_named_flags(tmp_path: Path) -> None:
    out_path = tmp_path / "overview.png"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "benchmarks.revisit_constellation.visualizer.run",
            "overview",
            "--case-dir",
            str(CASE_DIR),
            "--out-path",
            str(out_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    _assert_png(out_path)
