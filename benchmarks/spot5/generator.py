"""Regenerate the canonical SPOT-5 split-aware dataset.

By default this script downloads the upstream Mendeley dataset ZIP and rewrites
it into the canonical case layout used by this repository:

    dataset/
      index.json
      cases/<split>/<case_id>/<case_id>.spot

The generator requires a benchmark-local ``splits.yaml`` that records the
canonical split assignments. A local directory of raw ``.spot`` files or a
previously downloaded ZIP may still be supplied for maintenance workflows via
``--source-dir`` or ``--zip-path``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

import yaml


UPSTREAM_DATASET_URL = "https://data.mendeley.com/public-api/zip/2kbzg9nw3b/download/1"
UPSTREAM_DATASET_PAGE = "https://data.mendeley.com/datasets/2kbzg9nw3b/1"
DOWNLOAD_USER_AGENT = "Mozilla/5.0 AstroReason-Bench/1.0"


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


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

    normalized_splits: dict[str, list[str]] = {}
    for split_name, case_ids in splits.items():
        _validate_path_segment(split_name, "split name")
        if not isinstance(case_ids, list) or not case_ids:
            raise ValueError(f"split {split_name!r} must list at least one case id")
        normalized_case_ids: list[str] = []
        for case_id in case_ids:
            normalized_case_id = _validate_path_segment(
                str(case_id),
                f"case id in split {split_name!r}",
            )
            normalized_case_ids.append(normalized_case_id)
        normalized_splits[split_name] = normalized_case_ids
    payload["splits"] = normalized_splits

    smoke_split, smoke_case_id = _parse_smoke_case(payload)
    if smoke_case_id not in payload["splits"].get(smoke_split, []):
        raise ValueError(
            f"example_smoke_case {smoke_split}/{smoke_case_id} is not present in the configured split assignments"
        )

    return payload


def is_multi_orbit_case(case_id: str) -> bool:
    """Return whether an instance id belongs to the multi-orbit family."""
    return int(case_id) > 1000


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
    split_assignments: dict[str, list[str]],
    example_smoke_case: str,
) -> None:
    """Write the canonical SPOT-5 split-aware dataset."""

    smoke_split, smoke_case_id = example_smoke_case.split("/")
    source_by_case_id: dict[str, Path] = {}
    for source_path in spot_files:
        case_id = source_path.stem
        if case_id in source_by_case_id:
            raise ValueError(f"Duplicate SPOT-5 source instance id: {case_id}")
        source_by_case_id[case_id] = source_path

    cases_dir = output_dir / "cases"
    shutil.rmtree(cases_dir, ignore_errors=True)
    index: dict = {
        "benchmark": "spot5",
        "case_id_format": "instance_stem",
        "source": provenance,
        "example_smoke_case": example_smoke_case,
        "cases": [],
    }
    example_solution: dict | None = None

    for split_name, case_ids in split_assignments.items():
        for case_id in case_ids:
            try:
                source_path = source_by_case_id[case_id]
            except KeyError as exc:
                raise KeyError(
                    f"split {split_name!r} references unknown SPOT-5 case {case_id!r}"
                ) from exc

            case_dir = cases_dir / split_name / case_id
            case_dir.mkdir(parents=True, exist_ok=True)

            destination = case_dir / f"{case_id}.spot"
            shutil.copyfile(source_path, destination)

            spot_content = destination.read_text()
            lines = spot_content.strip().splitlines()
            n_vars = int(lines[0].strip()) if lines else 0

            if split_name == smoke_split and case_id == smoke_case_id:
                example_solution = build_example_solution(case_id, n_vars)

            index["cases"].append(
                {
                    "split": split_name,
                    "case_id": case_id,
                    "path": f"cases/{split_name}/{case_id}",
                    "instance_file": f"{case_id}.spot",
                    "is_multi_orbit": is_multi_orbit_case(case_id),
                }
            )

    _write_json(output_dir / "index.json", index)
    if example_solution is None:
        raise RuntimeError(
            f"Expected configured smoke case {example_smoke_case} for example_solution.json"
        )
    _write_json(output_dir / "example_solution.json", example_solution)


def main() -> int:  # pragma: no cover - CLI wrapper
    parser = argparse.ArgumentParser(description="Regenerate the SPOT-5 dataset")
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
        help="Optional local directory containing raw .spot files",
    )
    parser.add_argument(
        "--zip-path",
        type=Path,
        help="Optional local copy of the upstream dataset ZIP",
    )
    args = parser.parse_args()
    config = load_generator_config(args.splits_config)

    if args.source_dir is not None and args.zip_path is not None:
        raise ValueError("Use either --source-dir or --zip-path, not both")

    if args.source_dir is not None:
        spot_files = collect_spot_files(args.source_dir)
        provenance = build_local_directory_provenance(args.source_dir)
        build_case_dataset(
            spot_files=spot_files,
            output_dir=args.output_dir,
            provenance=provenance,
            split_assignments=config["splits"],
            example_smoke_case=config["example_smoke_case"],
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
                split_assignments=config["splits"],
                example_smoke_case=config["example_smoke_case"],
            )
    print(f"Wrote SPOT-5 dataset to {args.output_dir}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
