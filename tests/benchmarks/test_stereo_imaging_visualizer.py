"""Small regressions for the stereo_imaging visualizer."""

from __future__ import annotations

from pathlib import Path

from benchmarks.stereo_imaging.visualizer.run import (
    _DEFAULT_OUTPUT_ROOT,
    _access_summary_lines,
    _products_output_dir,
    _select_track_satellites,
)


def test_select_track_satellites_spreads_representatives() -> None:
    satellites = {f"sat_{idx:02d}": object() for idx in range(1, 12)}

    selected = _select_track_satellites(satellites, max_ground_tracks=4)

    assert selected == ["sat_01", "sat_04", "sat_07", "sat_11"]


def test_select_track_satellites_can_hide_or_show_all_tracks() -> None:
    satellites = {f"sat_{idx:02d}": object() for idx in range(1, 4)}

    assert _select_track_satellites(satellites, max_ground_tracks=0) == []
    assert _select_track_satellites(satellites, max_ground_tracks=None) == [
        "sat_01",
        "sat_02",
        "sat_03",
    ]


def test_products_output_defaults_to_page_directory() -> None:
    assert _products_output_dir(Path("/cases/case_0001"), None) == _DEFAULT_OUTPUT_ROOT / "case_0001" / "products"
    assert _products_output_dir(Path("/cases/case_0001"), Path("/tmp/out")) == Path("/tmp/out")


def test_access_summary_lines_keep_text_compact() -> None:
    assert _access_summary_lines(
        [
            "sat_dubaisat_1::urban_heyuan_30::0",
            "sat_dubaisat_1::urban_heyuan_30::0",
            "sat_dubaisat_1::urban_heyuan_30::0",
        ]
    ) == ["Access: sat_dubaisat_1 pass 0 (3 obs)"]
