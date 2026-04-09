"""Small smoke tests for the relay_constellation generator."""

from __future__ import annotations

import json
from pathlib import Path

from benchmarks.relay_constellation.generator.build import CANONICAL_SEED, generate_dataset
from benchmarks.relay_constellation.generator.run import main


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_generate_dataset_writes_canonical_layout(tmp_path: Path) -> None:
    summaries = generate_dataset(tmp_path, seed=CANONICAL_SEED, num_cases=2)

    assert len(summaries) == 2
    index_payload = _read_json(tmp_path / "index.json")
    example_solution = _read_json(tmp_path / "example_solution.json")

    assert example_solution == {"actions": [], "added_satellites": []}
    assert index_payload["benchmark"] == "relay_constellation"
    assert index_payload["generator_seed"] == CANONICAL_SEED
    assert len(index_payload["cases"]) == 2

    for case_row in index_payload["cases"]:
        case_dir = tmp_path / case_row["path"]
        manifest = _read_json(case_dir / "manifest.json")
        network = _read_json(case_dir / "network.json")
        demands = _read_json(case_dir / "demands.json")

        assert manifest["benchmark"] == "relay_constellation"
        assert manifest["routing_step_s"] == 60
        assert "max_actions_total" not in manifest["constraints"]
        assert case_row["horizon_hours"] == 96
        assert 24 <= len(network["backbone_satellites"]) <= 32
        assert 4 <= len(network["ground_endpoints"]) <= 6
        assert 4 <= len(demands["demands"]) <= 8


def test_generate_dataset_is_deterministic_for_same_seed(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    generate_dataset(first_dir, seed=CANONICAL_SEED, num_cases=2)
    generate_dataset(second_dir, seed=CANONICAL_SEED, num_cases=2)

    first_index = _read_json(first_dir / "index.json")
    second_index = _read_json(second_dir / "index.json")
    assert first_index == second_index

    for case_row in first_index["cases"]:
        relative_path = Path(case_row["path"])
        assert _read_json(first_dir / relative_path / "manifest.json") == _read_json(
            second_dir / relative_path / "manifest.json"
        )
        assert _read_json(first_dir / relative_path / "network.json") == _read_json(
            second_dir / relative_path / "network.json"
        )
        assert _read_json(first_dir / relative_path / "demands.json") == _read_json(
            second_dir / relative_path / "demands.json"
        )


def test_main_wires_requested_directory(monkeypatch, tmp_path: Path) -> None:
    out_dir = tmp_path / "dataset"
    captured: dict[str, object] = {}

    def fake_generate_dataset(*, output_dir: Path, seed: int) -> list[dict[str, object]]:
        captured["output_dir"] = output_dir
        captured["seed"] = seed
        return []

    monkeypatch.setattr("benchmarks.relay_constellation.generator.run.generate_dataset", fake_generate_dataset)
    exit_code = main(["--dataset-dir", str(out_dir)])

    assert exit_code == 0
    assert captured["output_dir"] == out_dir
    assert captured["seed"] == CANONICAL_SEED
