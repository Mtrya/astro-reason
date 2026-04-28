"""Small regressions for the stereo_imaging visualizer."""

from __future__ import annotations

from benchmarks.stereo_imaging.visualizer.run import _select_track_satellites


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
