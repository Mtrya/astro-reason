from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validate_benchmark_contract import load_splits_config, resolve_smoke_case_dir


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _mkdir_case(dataset_dir: Path, split_name: str, case_id: str) -> Path:
    case_dir = dataset_dir / "cases" / split_name / case_id
    case_dir.mkdir(parents=True)
    return case_dir


def test_load_splits_config_accepts_split_parameters_schema(tmp_path: Path) -> None:
    splits_path = tmp_path / "splits.yaml"
    splits_path.write_text(
        "splits:\n"
        "  test:\n"
        "    seed: 42\n"
        "    case_count: 3\n"
        "  hard:\n"
        "    seed: 142\n"
        "    case_count: 5\n",
        encoding="utf-8",
    )

    payload = load_splits_config(splits_path)

    assert payload["splits"]["test"]["seed"] == 42
    assert payload["splits"]["hard"]["case_count"] == 5


def test_load_splits_config_accepts_split_assignments_schema(tmp_path: Path) -> None:
    splits_path = tmp_path / "splits.yaml"
    splits_path.write_text(
        "splits:\n"
        "  test:\n"
        "    - case_001\n"
        "    - case_002\n"
        "  train:\n"
        "    - case_003\n",
        encoding="utf-8",
    )

    payload = load_splits_config(splits_path)

    assert payload["splits"]["test"] == ["case_001", "case_002"]
    assert payload["splits"]["train"] == ["case_003"]


def test_load_splits_config_rejects_mixed_split_schemas(tmp_path: Path) -> None:
    splits_path = tmp_path / "splits.yaml"
    splits_path.write_text(
        "splits:\n"
        "  test:\n"
        "    seed: 42\n"
        "  train:\n"
        "    - case_001\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must use one schema"):
        load_splits_config(splits_path)


def test_resolve_smoke_case_dir_prefers_split_relative_metadata(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset"
    _mkdir_case(dataset_dir, "test", "case_0001")
    target_case = _mkdir_case(dataset_dir, "test", "case_0002")
    _write_json(dataset_dir / "index.json", {"example_smoke_case": "test/case_0002"})

    case_dir, errors = resolve_smoke_case_dir(dataset_dir)

    assert case_dir == target_case
    assert errors == []


def test_resolve_smoke_case_dir_reports_legacy_field_but_still_resolves(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset"
    target_case = _mkdir_case(dataset_dir, "test", "case_0005")
    _write_json(dataset_dir / "index.json", {"example_smoke_case_id": "case_0005"})

    case_dir, errors = resolve_smoke_case_dir(dataset_dir)

    assert case_dir == target_case
    assert any("example_smoke_case" in message for message in errors)


def test_resolve_smoke_case_dir_falls_back_to_first_case_when_metadata_missing(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset"
    first_case = _mkdir_case(dataset_dir, "alpha", "case_0001")
    _mkdir_case(dataset_dir, "test", "case_0002")

    case_dir, errors = resolve_smoke_case_dir(dataset_dir)

    assert case_dir == first_case
    assert errors == []
