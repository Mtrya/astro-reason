"""Upload canonical benchmark datasets to a single Hugging Face Dataset repository.

Each benchmark becomes a separate config (subset) in the HF Dataset.
Splits are mapped transparently to HF Dataset splits.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from datasets import Dataset, DatasetDict
from huggingface_hub import HfApi


REPO_ROOT = Path(__file__).resolve().parents[1]
FINISHED_BENCHMARKS_PATH = REPO_ROOT / "benchmarks" / "finished_benchmarks.json"


def _load_finished_benchmarks() -> list[dict[str, object]]:
    payload = json.loads(FINISHED_BENCHMARKS_PATH.read_text(encoding="utf-8"))
    return payload.get("benchmarks", [])


def _read_case_files(case_dir: Path) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    if not case_dir.is_dir():
        return files
    for file_path in sorted(case_dir.rglob("*")):
        if file_path.is_file() and not file_path.name.startswith("."):
            rel = file_path.relative_to(case_dir).as_posix()
            try:
                files.append({"path": rel, "content": file_path.read_text(encoding="utf-8")})
            except UnicodeDecodeError:
                # Skip binary files; benchmarks use text-only case data
                continue
    return files


def _build_benchmark_dataset_dict(benchmark_name: str) -> DatasetDict:
    dataset_dir = REPO_ROOT / "benchmarks" / benchmark_name / "dataset"
    index_path = dataset_dir / "index.json"

    if not index_path.is_file():
        raise FileNotFoundError(f"{benchmark_name}: missing dataset/index.json")

    index = json.loads(index_path.read_text(encoding="utf-8"))
    cases = index.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError(f"{benchmark_name}: index.json 'cases' must be a list")

    rows_by_split: dict[str, list[dict[str, object]]] = {}
    for case in cases:
        if not isinstance(case, dict):
            continue
        case_id = case.get("case_id")
        split = case.get("split") or "default"
        case_path = case.get("path")
        if not case_id or not case_path:
            continue

        case_dir = dataset_dir / case_path
        row = {
            "case_id": str(case_id),
            "split": str(split),
            "benchmark": benchmark_name,
            "index_metadata": case,
            "files": _read_case_files(case_dir),
        }
        rows_by_split.setdefault(str(split), []).append(row)

    if not rows_by_split:
        raise ValueError(f"{benchmark_name}: no valid cases found")

    return DatasetDict({split: Dataset.from_list(rows) for split, rows in rows_by_split.items()})


def _upload_benchmark(
    benchmark_name: str,
    repo_id: str,
    token: str | None,
    dry_run: bool,
) -> None:
    dataset_dict = _build_benchmark_dataset_dict(benchmark_name)
    if dry_run:
        print(f"[{benchmark_name}] dry-run:")
        for split, ds in dataset_dict.items():
            print(f"  split={split!r}, rows={len(ds)}")
        return

    for split, ds in dataset_dict.items():
        ds.push_to_hub(repo_id, config_name=benchmark_name, split=split, token=token)
    print(f"[{benchmark_name}] uploaded to {repo_id} (config={benchmark_name})")


def _upload_dataset_card(repo_id: str, token: str | None, dry_run: bool) -> None:
    card_path = REPO_ROOT / "scripts" / "dataset_card.md"
    if not card_path.is_file():
        print(f"Warning: dataset card not found at {card_path}", file=os.sys.stderr)
        return
    if dry_run:
        print(f"[readme] dry-run: would upload {card_path} to {repo_id}/README.md")
        return
    api = HfApi()
    api.upload_file(
        path_or_fileobj=str(card_path),
        path_in_repo="README.md",
        repo_id=repo_id,
        repo_type="dataset",
        token=token,
    )
    print(f"[readme] uploaded dataset card to {repo_id}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Upload canonical benchmark datasets to Hugging Face Datasets"
    )
    parser.add_argument(
        "--repo-id",
        default=os.environ.get("HF_DATASET_REPO_ID", "AstroReason-Bench/datasets"),
        help="Target Hugging Face Dataset repository ID (env: HF_DATASET_REPO_ID)",
    )
    parser.add_argument(
        "--benchmarks",
        nargs="+",
        help="Specific benchmarks to upload (defaults to all finished benchmarks)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print what would be uploaded without pushing",
    )
    args = parser.parse_args()

    token = os.environ.get("HF_TOKEN")
    if not token and not args.dry_run:
        print("Error: HF_TOKEN environment variable is required", file=os.sys.stderr)
        return 1

    benchmarks = _load_finished_benchmarks()
    available_names = {b["name"] for b in benchmarks if "name" in b}

    if args.benchmarks:
        selected = []
        for name in args.benchmarks:
            if name not in available_names:
                print(f"Error: benchmark {name!r} not found in finished_benchmarks.json", file=os.sys.stderr)
                return 1
            selected.append({"name": name})
        benchmarks = selected

    for benchmark in benchmarks:
        name = str(benchmark["name"])
        try:
            _upload_benchmark(name, args.repo_id, token, args.dry_run)
        except Exception as exc:
            print(f"Error uploading {name}: {exc}", file=os.sys.stderr)
            return 1

    _upload_dataset_card(args.repo_id, token, args.dry_run)
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
