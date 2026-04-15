"""Regenerate the canonical SatNet split-aware dataset.

By default this script downloads the upstream aggregate SatNet data from
https://github.com/edwinytgoh/satnet/tree/master/data and rewrites it into the
canonical case layout used by this repository:

    dataset/
      mission_color_map.json
      index.json
      cases/test/W10_2018/{problem.json,maintenance.csv,metadata.json}
      ...

The generator requires a benchmark-local ``splits.yaml`` that records the
canonical split assignment and smoke-test pairing. A local copy of the upstream
aggregate ``data/`` directory may still be supplied via ``--source-dir`` as an
operational override for maintenance workflows.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import shutil
from typing import Iterable
from urllib.request import urlopen

import yaml


UPSTREAM_REPOSITORY = "https://github.com/edwinytgoh/satnet"
UPSTREAM_RAW_BASE = "https://raw.githubusercontent.com/edwinytgoh/satnet/{ref}/data"
CSV_FIELDNAMES = ["week", "year", "starttime", "endtime", "antenna"]


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def _write_csv(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _download_text(url: str) -> str:
    with urlopen(url) as response:  # noqa: S310 - explicit benchmark source URL
        return response.read().decode("utf-8")


def _validate_path_segment(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "/" in value or "\\" in value:
        raise ValueError(f"{label} must be a non-empty single path segment")
    return value


def _parse_smoke_case(config: dict) -> tuple[str, str]:
    smoke_case = config.get("example_smoke_case")
    if not isinstance(smoke_case, str) or not smoke_case:
        raise ValueError("splits config must include example_smoke_case")
    parts = smoke_case.split("/")
    if len(parts) != 2:
        raise ValueError("example_smoke_case must be formatted as <split>/<case_id>")
    return (
        _validate_path_segment(parts[0], "example_smoke_case split"),
        _validate_path_segment(parts[1], "example_smoke_case case_id"),
    )


def load_generator_config(path: Path) -> dict:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"missing required splits config: {path}") from exc
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"failed to load splits config {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("splits config must be a YAML mapping")

    splits = payload.get("splits")
    if not isinstance(splits, dict) or not splits:
        raise ValueError("splits config must contain a non-empty top-level 'splits' mapping")

    for split_name, case_ids in splits.items():
        _validate_path_segment(split_name, "split name")
        if not isinstance(case_ids, list) or not case_ids:
            raise ValueError(f"split {split_name!r} must list at least one case id")
        for case_id in case_ids:
            _validate_path_segment(case_id, f"case id in split {split_name!r}")

    smoke_split, smoke_case_id = _parse_smoke_case(payload)
    if smoke_case_id not in splits.get(smoke_split, []):
        raise ValueError(
            f"example_smoke_case {smoke_split}/{smoke_case_id} is not present in the configured split assignments"
        )

    source = payload.get("source", {})
    if source and not isinstance(source, dict):
        raise ValueError("source must be a mapping when present in splits config")
    upstream_ref = source.get("upstream_ref", "master")
    if not isinstance(upstream_ref, str) or not upstream_ref:
        raise ValueError("source.upstream_ref must be a non-empty string")

    return payload


def load_upstream_inputs(ref: str) -> tuple[dict, list[dict], dict]:
    """Download aggregate SatNet inputs from the upstream repository."""

    base = UPSTREAM_RAW_BASE.format(ref=ref)
    problems = json.loads(_download_text(f"{base}/problems.json"))
    maintenance_rows = list(csv.DictReader(_download_text(f"{base}/maintenance.csv").splitlines()))
    mission_color_map = json.loads(_download_text(f"{base}/mission_color_map.json"))
    return problems, maintenance_rows, mission_color_map


def load_local_inputs(source_dir: Path) -> tuple[dict, list[dict], dict]:
    """Read aggregate SatNet inputs from a local ``data/`` directory."""

    problems = json.loads((source_dir / "problems.json").read_text())
    with (source_dir / "maintenance.csv").open(newline="") as file_obj:
        maintenance_rows = list(csv.DictReader(file_obj))
    mission_color_map = json.loads((source_dir / "mission_color_map.json").read_text())
    return problems, maintenance_rows, mission_color_map


def build_upstream_provenance(ref: str) -> dict:
    """Return metadata describing an upstream SatNet data source."""

    return {
        "kind": "upstream",
        "repository": UPSTREAM_REPOSITORY,
        "ref": ref,
        "problems_path": "data/problems.json",
        "maintenance_path": "data/maintenance.csv",
        "mission_color_map_path": "data/mission_color_map.json",
    }


def build_local_provenance(source_dir: Path, description: str | None = None) -> dict:
    """Return metadata describing a local SatNet data source."""

    provenance = {
        "kind": "local_directory",
        "source_dir_name": source_dir.name,
        "problems_path": "problems.json",
        "maintenance_path": "maintenance.csv",
        "mission_color_map_path": "mission_color_map.json",
    }
    if description:
        provenance["description"] = description
    return provenance


def build_case_dataset(
    problems: dict,
    maintenance_rows: list[dict],
    mission_color_map: dict,
    output_dir: Path,
    provenance: dict,
    split_assignments: dict[str, list[str]],
    example_smoke_case: str,
) -> None:
    """Write the canonical SatNet split-aware dataset."""

    smoke_split, smoke_case_id = example_smoke_case.split("/")
    cases_dir = output_dir / "cases"
    shutil.rmtree(cases_dir, ignore_errors=True)
    index = {
        "benchmark": "satnet",
        "case_id_format": "W##_YYYY",
        "shared_files": ["mission_color_map.json"],
        "source": provenance,
        "example_smoke_case": example_smoke_case,
        "cases": [],
    }
    example_solution: list | None = None

    for split_name, case_ids in split_assignments.items():
        for case_id in case_ids:
            if case_id not in problems:
                raise KeyError(f"split {split_name!r} references unknown SatNet case {case_id!r}")

            week = int(case_id.split("_")[0][1:])
            year = int(case_id.split("_")[1])
            requests = [
                row
                for row in problems[case_id]
                if int(row["week"]) == week and int(row["year"]) == year
            ]
            case_maintenance = [
                row
                for row in maintenance_rows
                if int(float(row["week"])) == week and int(row["year"]) == year
            ]

            case_dir = cases_dir / split_name / case_id
            _write_json(case_dir / "problem.json", requests)
            _write_csv(case_dir / "maintenance.csv", case_maintenance)

            metadata = {
                "case_id": case_id,
                "split": split_name,
                "week": week,
                "year": year,
                "request_count": len(requests),
                "mission_count": len({int(row["subject"]) for row in requests}),
                "maintenance_window_count": len(case_maintenance),
                "total_requested_hours": sum(float(row["duration"]) for row in requests),
            }
            _write_json(case_dir / "metadata.json", metadata)

            if split_name == smoke_split and case_id == smoke_case_id:
                example_solution = []

            index["cases"].append(
                {
                    "split": split_name,
                    "case_id": case_id,
                    "path": f"cases/{split_name}/{case_id}",
                    "week": week,
                    "year": year,
                    "request_count": len(requests),
                    "maintenance_window_count": len(case_maintenance),
                }
            )

    _write_json(output_dir / "index.json", index)
    _write_json(output_dir / "mission_color_map.json", mission_color_map)
    if example_solution is None:
        raise RuntimeError(
            f"Expected configured smoke case {example_smoke_case} for example_solution.json"
        )
    _write_json(output_dir / "example_solution.json", example_solution)


def main() -> int:  # pragma: no cover - CLI wrapper
    parser = argparse.ArgumentParser(description="Regenerate the SatNet dataset")
    parser.add_argument(
        "splits_config",
        type=Path,
        help="Path to the benchmark-local splits.yaml describing canonical split assignments",
    )
    parser.add_argument(
        "--output-dir",
        default=Path(__file__).resolve().parent / "dataset",
        type=Path,
        help="Directory where the canonical dataset should be written",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        help="Optional local copy of the upstream satnet/data directory",
    )
    parser.add_argument(
        "--source-description",
        help="Optional provenance note to record when --source-dir is used",
    )
    args = parser.parse_args()
    config = load_generator_config(args.splits_config)

    if args.source_dir is not None:
        problems, maintenance_rows, mission_color_map = load_local_inputs(args.source_dir)
        provenance = build_local_provenance(
            args.source_dir,
            description=args.source_description,
        )
    else:
        upstream_ref = config.get("source", {}).get("upstream_ref", "master")
        problems, maintenance_rows, mission_color_map = load_upstream_inputs(upstream_ref)
        provenance = build_upstream_provenance(upstream_ref)

    build_case_dataset(
        problems=problems,
        maintenance_rows=maintenance_rows,
        mission_color_map=mission_color_map,
        output_dir=args.output_dir,
        provenance=provenance,
        split_assignments=config["splits"],
        example_smoke_case=config["example_smoke_case"],
    )
    print(f"Wrote SatNet dataset to {args.output_dir}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
