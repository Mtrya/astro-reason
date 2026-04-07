"""Regenerate the canonical SatNet case-by-case dataset.

By default this script downloads the upstream aggregate SatNet data from
https://github.com/edwinytgoh/satnet/tree/master/data and rewrites it into the
canonical case layout used by this repository:

    dataset/
      mission_color_map.json
      index.json
      cases/W10_2018/{problem.json,maintenance.csv,metadata.json}
      ...

The generator can also consume a local copy of the upstream ``data/``
directory via ``--source-dir``.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Iterable
from urllib.request import urlopen


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
) -> None:
    """Write the canonical SatNet case-by-case dataset."""

    cases_dir = output_dir / "cases"
    index = {
        "benchmark": "satnet",
        "case_id_format": "W##_YYYY",
        "shared_files": ["mission_color_map.json"],
        "source": provenance,
        "cases": [],
    }
    example_solution: list | None = None

    for case_id in sorted(problems):
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

        case_dir = cases_dir / case_id
        _write_json(case_dir / "problem.json", requests)
        _write_csv(case_dir / "maintenance.csv", case_maintenance)

        metadata = {
            "case_id": case_id,
            "week": week,
            "year": year,
            "request_count": len(requests),
            "mission_count": len({int(row["subject"]) for row in requests}),
            "maintenance_window_count": len(case_maintenance),
            "total_requested_hours": sum(float(row["duration"]) for row in requests),
        }
        _write_json(case_dir / "metadata.json", metadata)

        if case_id == "W10_2018":
            example_solution = []

        index["cases"].append(
            {
                "case_id": case_id,
                "path": f"cases/{case_id}",
                "week": week,
                "year": year,
                "request_count": len(requests),
                "maintenance_window_count": len(case_maintenance),
            }
        )

    _write_json(output_dir / "index.json", index)
    _write_json(output_dir / "mission_color_map.json", mission_color_map)
    if example_solution is None:
        raise RuntimeError("Expected W10_2018 case for example_solution.json")
    _write_json(output_dir / "example_solution.json", example_solution)


def main() -> int:  # pragma: no cover - CLI wrapper
    parser = argparse.ArgumentParser(description="Regenerate the SatNet dataset")
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
        "--upstream-ref",
        default="master",
        help="Upstream SatNet git ref to download when --source-dir is not used",
    )
    parser.add_argument(
        "--source-description",
        help="Optional provenance note to record when --source-dir is used",
    )
    args = parser.parse_args()

    if args.source_dir is not None:
        problems, maintenance_rows, mission_color_map = load_local_inputs(args.source_dir)
        provenance = build_local_provenance(
            args.source_dir,
            description=args.source_description,
        )
    else:
        problems, maintenance_rows, mission_color_map = load_upstream_inputs(args.upstream_ref)
        provenance = build_upstream_provenance(args.upstream_ref)

    build_case_dataset(
        problems=problems,
        maintenance_rows=maintenance_rows,
        mission_color_map=mission_color_map,
        output_dir=args.output_dir,
        provenance=provenance,
    )
    print(f"Wrote SatNet dataset to {args.output_dir}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
