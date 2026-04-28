"""Smoke tests for the relay_constellation visualizer."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from benchmarks.relay_constellation.visualizer.plot import render_overview
from benchmarks.relay_constellation.visualizer.run import main
from benchmarks.relay_constellation.visualizer.solution import render_solution


FIXTURE_DIR = Path("tests/fixtures/relay_constellation/full_service_valid")


def _texture_path(tmp_path: Path) -> Path:
    path = tmp_path / "earth.png"
    Image.new("RGB", (720, 360), color=(128, 172, 205)).save(path)
    return path


def test_render_overview_writes_two_pngs_only(tmp_path: Path) -> None:
    out_dir = tmp_path / "overview"
    result = render_overview(
        FIXTURE_DIR,
        out_dir,
        texture_path=_texture_path(tmp_path),
    )

    assert result["ground_tracks_png"] == "ground_tracks.png"
    assert result["baseline_connectivity_png"] == "baseline_connectivity.png"
    assert (out_dir / "ground_tracks.png").is_file()
    assert (out_dir / "baseline_connectivity.png").is_file()
    assert not (out_dir / "manifest.json").exists()
    assert not (out_dir / "connectivity_manifest.json").exists()


def test_render_solution_writes_pngs_only(tmp_path: Path) -> None:
    out_dir = tmp_path / "solution"
    result = render_solution(
        FIXTURE_DIR,
        FIXTURE_DIR / "solution.json",
        out_dir,
        texture_path=_texture_path(tmp_path),
    )

    assert result["ground_tracks_png"] == "ground_tracks.png"
    assert result["scheduled_connectivity_png"] == "scheduled_connectivity.png"
    assert result["demand_window_pngs"] == ["demand_windows/demand_001.png"]
    assert (out_dir / "ground_tracks.png").is_file()
    assert (out_dir / "scheduled_connectivity.png").is_file()
    assert (out_dir / "demand_windows" / "demand_001.png").is_file()
    assert not (out_dir / "summary.json").exists()
    assert not (out_dir / "snapshots").exists()


def test_visualizer_cli_uses_named_flags(tmp_path: Path) -> None:
    out_dir = tmp_path / "cli"

    assert main(
        [
            "overview",
            "--case-dir",
            str(FIXTURE_DIR),
            "--out-dir",
            str(out_dir),
            "--texture-path",
            str(_texture_path(tmp_path)),
        ]
    ) == 0

    assert (out_dir / "ground_tracks.png").is_file()
    assert (out_dir / "baseline_connectivity.png").is_file()
