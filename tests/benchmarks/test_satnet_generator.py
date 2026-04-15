from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import benchmarks.satnet.generator as generator_module


def _write_satnet_source_dir(source_dir: Path) -> None:
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "problems.json").write_text(
        json.dumps(
            {
                "W10_2018": [
                    {
                        "subject": 1,
                        "user": "1_0",
                        "week": 10,
                        "year": 2018,
                        "duration": 1.0,
                        "duration_min": 1.0,
                        "resources": [["DSS-34"]],
                        "track_id": "track-1",
                        "setup_time": 10,
                        "teardown_time": 5,
                        "time_window_start": 100,
                        "time_window_end": 200,
                        "resource_vp_dict": {"DSS-34": [{"TRX ON": 110, "TRX OFF": 170}]},
                    }
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (source_dir / "maintenance.csv").write_text(
        "week,year,starttime,endtime,antenna\n10.0,2018,300,360,DSS-14\n",
        encoding="utf-8",
    )
    (source_dir / "mission_color_map.json").write_text('{"1": "#ffffff"}\n', encoding="utf-8")


def test_main_requires_splits_yaml(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["generator.py"])

    with pytest.raises(SystemExit) as exc_info:
        generator_module.main()

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "usage:" in captured.err.lower()


def test_main_builds_dataset_from_local_source_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "source"
    _write_satnet_source_dir(source_dir)

    splits_path = tmp_path / "splits.yaml"
    splits_path.write_text(
        "source:\n"
        "  upstream_ref: master\n"
        "example_smoke_case: test/W10_2018\n"
        "splits:\n"
        "  test:\n"
        "    - W10_2018\n",
        encoding="utf-8",
    )

    output_dir = tmp_path / "output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generator.py",
            str(splits_path),
            "--source-dir",
            str(source_dir),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert generator_module.main() == 0
    assert (output_dir / "cases" / "test" / "W10_2018" / "problem.json").exists()
    index = json.loads((output_dir / "index.json").read_text(encoding="utf-8"))
    assert index["example_smoke_case"] == "test/W10_2018"
    assert index["cases"][0]["path"] == "cases/test/W10_2018"
