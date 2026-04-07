"""Regenerate the canonical SPOT-5 case-by-case dataset.

By default this script downloads the upstream Mendeley dataset ZIP and rewrites
it into the canonical case layout used by this repository:

    dataset/
      index.json
      cases/<case_id>/<case_id>.spot

The generator can also consume a local directory of raw ``.spot`` files via
``--source-dir`` or a previously downloaded ZIP via ``--zip-path``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen


UPSTREAM_DATASET_URL = "https://data.mendeley.com/public-api/zip/2kbzg9nw3b/download/1"
UPSTREAM_DATASET_PAGE = "https://data.mendeley.com/datasets/2kbzg9nw3b/1"
MULTI_ORBIT_INSTANCES = {"1021", "1401", "1403", "1405", "1502", "1504", "1506"}
DOWNLOAD_USER_AGENT = "Mozilla/5.0 AstroReason-Bench/1.0"


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def download_upstream_zip(destination: Path) -> Path:
    """Download the published SPOT-5 dataset ZIP from Mendeley Data."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(
        UPSTREAM_DATASET_URL,
        headers={"User-Agent": DOWNLOAD_USER_AGENT},
    )
    with urlopen(request) as response, destination.open("wb") as output_file:  # noqa: S310 - fixed public dataset URL
        shutil.copyfileobj(response, output_file)
    return destination


def collect_spot_files(source_dir: Path) -> list[Path]:
    """Return all raw ``.spot`` files from a local source tree."""

    spot_files = sorted(source_dir.rglob("*.spot"))
    if not spot_files:
        raise FileNotFoundError(f"No .spot files found under {source_dir}")
    return spot_files


def build_upstream_provenance() -> dict:
    """Return metadata describing the published SPOT-5 source dataset."""

    return {
        "kind": "upstream_zip",
        "dataset_page": UPSTREAM_DATASET_PAGE,
        "download_url": UPSTREAM_DATASET_URL,
    }


def build_local_directory_provenance(source_dir: Path) -> dict:
    """Return metadata describing a local source directory."""

    return {
        "kind": "local_directory",
        "source_dir_name": source_dir.name,
    }


def build_local_zip_provenance(zip_path: Path) -> dict:
    """Return metadata describing a local ZIP archive."""

    return {
        "kind": "local_zip",
        "zip_name": zip_path.name,
    }


def extract_zip_tree(zip_path: Path, destination: Path) -> None:
    """Extract a ZIP archive and any nested ZIPs into ``destination``."""

    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(destination)

    nested_archives = sorted(destination.rglob("*.zip"))
    for nested_archive in nested_archives:
        nested_destination = nested_archive.with_suffix("")
        if nested_destination.exists():
            continue
        with zipfile.ZipFile(nested_archive) as archive:
            archive.extractall(nested_destination)


def build_example_solution(case_id: str, n_candidates: int) -> dict:
    """Return a minimal example solution for smoke tests."""
    return {
        "claimed_profit": 0,
        "claimed_weight": 0,
        "n_candidates": n_candidates,
        "n_selected": 0,
        "assignments": [0] * n_candidates,
    }


def build_case_dataset(
    spot_files: list[Path],
    output_dir: Path,
    provenance: dict,
) -> None:
    """Write the canonical SPOT-5 case-by-case dataset."""

    cases_dir = output_dir / "cases"
    shutil.rmtree(cases_dir, ignore_errors=True)
    index: dict = {
        "benchmark": "spot5",
        "case_id_format": "instance_stem",
        "source": provenance,
        "cases": [],
    }
    example_solution: dict | None = None

    for source_path in sorted(spot_files, key=lambda path: path.stem):
        case_id = source_path.stem
        case_dir = cases_dir / case_id
        case_dir.mkdir(parents=True, exist_ok=True)

        destination = case_dir / f"{case_id}.spot"
        shutil.copyfile(source_path, destination)

        # Parse n_candidates from the spot file for the example solution
        spot_content = destination.read_text()
        lines = spot_content.strip().splitlines()
        n_vars = int(lines[0].strip()) if lines else 0

        if case_id == "8":
            example_solution = build_example_solution(case_id, n_vars)
            index["example_smoke_case_id"] = "8"

        index["cases"].append(
            {
                "case_id": case_id,
                "path": f"cases/{case_id}",
                "instance_file": f"{case_id}.spot",
                "is_multi_orbit": case_id in MULTI_ORBIT_INSTANCES,
            }
        )

    _write_json(output_dir / "index.json", index)
    if example_solution is None:
        raise RuntimeError("Expected at least one case with id '8' for example_solution.json")
    _write_json(output_dir / "example_solution.json", example_solution)


def main() -> int:  # pragma: no cover - CLI wrapper
    parser = argparse.ArgumentParser(description="Regenerate the SPOT-5 dataset")
    parser.add_argument(
        "--output-dir",
        default=Path(__file__).resolve().parent / "dataset",
        type=Path,
        help="Directory where the canonical dataset should be written",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        help="Optional local directory containing raw .spot files",
    )
    parser.add_argument(
        "--zip-path",
        type=Path,
        help="Optional local copy of the upstream dataset ZIP",
    )
    args = parser.parse_args()

    if args.source_dir is not None and args.zip_path is not None:
        raise ValueError("Use either --source-dir or --zip-path, not both")

    if args.source_dir is not None:
        spot_files = collect_spot_files(args.source_dir)
        provenance = build_local_directory_provenance(args.source_dir)
        build_case_dataset(
            spot_files=spot_files,
            output_dir=args.output_dir,
            provenance=provenance,
        )
    else:
        with tempfile.TemporaryDirectory(prefix="spot5-generator-") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            zip_path = args.zip_path or (temp_dir / "spot5.zip")

            if args.zip_path is None:
                download_upstream_zip(zip_path)
                provenance = build_upstream_provenance()
            else:
                provenance = build_local_zip_provenance(args.zip_path)

            extract_dir = temp_dir / "source"
            extract_zip_tree(zip_path, extract_dir)
            spot_files = collect_spot_files(extract_dir)
            build_case_dataset(
                spot_files=spot_files,
                output_dir=args.output_dir,
                provenance=provenance,
            )
    print(f"Wrote SPOT-5 dataset to {args.output_dir}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
