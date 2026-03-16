#!/usr/bin/env python3
"""Generate AEOS-Bench test dataset from source data.

Usage: cd benchmarks/aeosbench && uv run generator.py [--method random|official] [--num-cases N] [--skip-download] [--local-dir DIR]
"""

import json
import shutil
import sys
import tarfile
from pathlib import Path
from typing import Literal

from huggingface_hub import hf_hub_download


def download_from_huggingface(
    repo_id: str = "MessianX/AEOS-dataset",
    filename: str = "constellation_data.tar",
    local_dir: Path | None = None,
) -> Path:
    """Download dataset file from HuggingFace.

    Args:
        repo_id: HuggingFace dataset repository ID
        filename: File to download from the repo
        local_dir: Directory to save the file. If None, uses the default
            HuggingFace cache directory (~/.cache/huggingface/hub/).

    Returns:
        Path to the downloaded file.
    """
    print(f"📥 Downloading {filename} from HuggingFace...")
    print(f"   Repository: {repo_id}")
    if local_dir is not None:
        local_dir.mkdir(parents=True, exist_ok=True)
        print(f"   Local dir: {local_dir}")

    try:
        path = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            repo_type="dataset",
            local_dir=str(local_dir) if local_dir is not None else None,
        )
        print(f"✓ Downloaded to {path}")
        return Path(path)
    except Exception as e:
        print(f"✗ Download failed: {e}")
        sys.exit(1)


def extract_tar(tar_path: Path, extract_to: Path = Path(".")):
    """Extract tar file.

    Args:
        tar_path: Path to tar file
        extract_to: Directory to extract to
    """
    print(f"\n📦 Extracting {tar_path.name}...")

    def _filter(member, dest_path):
        # Skip symlinks
        if member.issym() or member.islnk():
            return None
        return tarfile.data_filter(member, dest_path)

    with tarfile.open(tar_path, "r") as tar:
        tar.extractall(path=extract_to, filter=_filter)

    print(f"✓ Extracted to {extract_to}/")


def create_test_set(
    method: Literal["official", "random"],
    source_data: Path = Path("data"),
    output_dir: Path = Path("dataset"),
    num_cases: int = 64,
):
    """Create test set using specified methodology.

    Args:
        method: "official" uses the annotations bundled with the source data;
            "random" samples cases with a fixed seed for reproducibility
        source_data: Path to extracted data/ directory from constellation_data.tar
        output_dir: Output directory for test set
        num_cases: Number of cases to include
    """
    print(f"\n🔬 Creating {method.upper()} test set...")

    cases_dir = output_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)

    if method == "official":
        annotations_file = source_data / "annotations" / "test.json"
        if not annotations_file.exists():
            print(f"✗ Official annotations not found at {annotations_file}")
            sys.exit(1)

        with open(annotations_file) as f:
            annotations_data = json.load(f)
            test_ids = annotations_data["ids"][:num_cases]

        print(f"   Using official annotations")
        print(f"   IDs: {test_ids[:5]} ... {test_ids[-5:]}")

    else:
        import random
        random.seed(42)
        test_ids = random.sample(range(1000), num_cases)

        print(f"   Using random selection (seed=42)")
        print(f"   IDs: {test_ids[:5]} ... {test_ids[-5:]}")

    copied = 0
    skipped = 0

    for case_id in test_ids:
        case_id_str = f"{case_id:05d}"
        subdir = f"{case_id // 1000:02d}"
        case_output_dir = cases_dir / case_id_str
        case_output_dir.mkdir(parents=True, exist_ok=True)

        constellation_src = (
            source_data / "constellations" / "test" / subdir / f"{case_id_str}.json"
        )
        taskset_src = source_data / "tasksets" / "test" / subdir / f"{case_id_str}.json"

        constellation_dst = case_output_dir / "constellation.json"
        taskset_dst = case_output_dir / "taskset.json"

        if constellation_src.exists() and taskset_src.exists():
            with open(constellation_src) as f:
                constellation_data = json.load(f)
            with open(taskset_src) as f:
                raw_tasks = json.load(f)

            # Source taskset is a bare list; wrap it to match the verifier schema.
            taskset_data = raw_tasks if isinstance(raw_tasks, dict) else {"tasks": raw_tasks}

            with open(constellation_dst, "w") as f:
                json.dump(constellation_data, f, indent=2)
            with open(taskset_dst, "w") as f:
                json.dump(taskset_data, f, indent=2)

            copied += 1

            if copied % 10 == 0:
                print(f"   Copied {copied}/{len(test_ids)} cases...")
        else:
            print(f"   WARNING: Case {case_id_str} not found!")
            skipped += 1

    print(f"\n✓ Created {method} test set:")
    print(f"   - {copied} cases copied")
    print(f"   - {skipped} cases skipped")
    print(f"   - Output: {output_dir}/")

    return test_ids


def main(skip_download: bool = False, local_dir: Path | None = None, num_cases: int = None, method: str = "random"):
    """Main setup workflow."""
    print("=" * 70)
    print("AEOS-Bench Test Data Setup")
    print("=" * 70)

    source_data = Path("data")

    extracted = False
    if skip_download and source_data.exists():
        print("⏭️  Skipping download (--skip-download flag set)")
    else:
        tar_path = download_from_huggingface(local_dir=local_dir)
        extract_tar(tar_path, extract_to=Path("."))
        extracted = True

    if not source_data.exists():
        print(f"✗ Expected data directory not found: {source_data}")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("Creating test set...")
    print("=" * 70)

    create_test_set(
        method=method,
        source_data=source_data,
        output_dir=Path("dataset"),
        num_cases=num_cases,
    )

    if extracted:
        print(f"\n🗑️  Cleaning up extracted source data ({source_data})...")
        shutil.rmtree(source_data)
        print(f"✓ Removed {source_data}/")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Setup AEOS-Bench test data")
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip download and extraction if data/ already exists locally",
    )
    parser.add_argument(
        "--local-dir",
        type=Path,
        default=None,
        help=(
            "Directory to save the downloaded tar file. "
            "Defaults to the HuggingFace cache directory."
        ),
    )
    parser.add_argument(
        "--num-cases",
        type=int,
        default=10,
        help="Number of cases to generate",
    )
    parser.add_argument(
        "--method",
        choices=["random", "official"],
        default="random",
        help="Test set selection method: 'random' (seed=42) or 'official' (source annotations)",
    )

    args = parser.parse_args()
    main(skip_download=args.skip_download, local_dir=args.local_dir, num_cases=args.num_cases, method=args.method)
