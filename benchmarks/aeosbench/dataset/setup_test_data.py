#!/usr/bin/env python3
"""Setup AEOS-Bench test data with full transparency about selection methodology.
"""

import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Literal


def download_from_huggingface(
    repo_id: str = "MessianX/AEOS-dataset",
    filename: str = "constellation_data.tar",
    local_dir: Path = Path("."),
):
    """Download dataset from HuggingFace using CLI.

    Args:
        repo_id: HuggingFace dataset repository ID
        filename: File to download from the repo
        local_dir: Local directory to store the downloaded file
    """
    print(f"📥 Downloading {filename} from HuggingFace...")
    print(f"   Repository: {repo_id}")
    print(f"   Local dir: {local_dir}")

    local_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "uv",
        "run",
        "hf",
        "download",
        repo_id,
        filename,
        "--repo-type",
        "dataset",
        "--local-dir",
        str(local_dir),
    ]

    try:
        subprocess.run(cmd, check=True)
        print(f"✓ Downloaded successfully")
        return local_dir / filename
    except subprocess.CalledProcessError as e:
        print(f"✗ Download failed: {e}")
        sys.exit(1)


def extract_tar(tar_path: Path, extract_to: Path = Path(".")):
    """Extract tar file.

    Args:
        tar_path: Path to tar file
        extract_to: Directory to extract to
    """
    print(f"\n📦 Extracting {tar_path.name}...")

    with tarfile.open(tar_path, "r") as tar:
        tar.extractall(path=extract_to)

    print(f"✓ Extracted to {extract_to}/")


def create_test_set(
    method: Literal["official", "random"],
    source_data: Path = Path("constellation_data/data"),
    output_dir: Path = Path("dataset"),
    num_cases: int = 64,
):
    """Create test set using specified methodology.

    Args:
        method: "official" or "random"
        source_data: Path to extracted constellation_data/data/
        output_dir: Output directory for test set
        num_cases: Number of cases to include
    """
    print(f"\n🔬 Creating {method.upper()} test set...")

    # Create output structure
    cases_dir = output_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)

    # Get case IDs based on method
    if method == "official":
        # Load (suspectibly) cherry-picked annotations
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
        # First 64 cases in sequential order
        import random
        random.seed(42)
        test_ids = random.sample(range(1000), 64)

        print(f"   Using fair (first-64) selection")
        print(f"   IDs: {test_ids[:5]} ... {test_ids[-5:]}")

    # Copy constellation and taskset files
    copied = 0
    skipped = 0

    for case_id in test_ids:
        case_id_str = f"{case_id:05d}"
        subdir = f"{case_id // 1000:02d}"
        case_output_dir = cases_dir / case_id_str
        case_output_dir.mkdir(parents=True, exist_ok=True)

        # Source paths
        constellation_src = (
            source_data / "constellations" / "test" / subdir / f"{case_id_str}.json"
        )
        taskset_src = source_data / "tasksets" / "test" / subdir / f"{case_id_str}.json"

        # Destination paths
        constellation_dst = case_output_dir / "constellation.json"
        taskset_dst = case_output_dir / "taskset.json"

        if constellation_src.exists() and taskset_src.exists():
            shutil.copy2(constellation_src, constellation_dst)
            shutil.copy2(taskset_src, taskset_dst)
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


def main():
    """Main setup workflow."""
    print("=" * 70)
    print("AEOS-Bench Test Data Setup")
    print("=" * 70)

    # Step 1: Download from HuggingFace
    tar_path = download_from_huggingface(
        repo_id="MessianX/AEOS-dataset",
        filename="constellation_data.tar",
        local_dir=Path("."),
    )

    # Step 2: Extract
    extract_tar(tar_path, extract_to=Path("."))

    # Verify extraction
    source_data = Path("constellation_data/data")
    if not source_data.exists():
        print(f"✗ Expected data directory not found: {source_data}")
        sys.exit(1)

    # Step 3: Create dataset with new format
    print("\n" + "=" * 70)
    print("Creating test sets...")
    print("=" * 70)

    """create_test_set(
        method="official",
        source_data=source_data,
        output_dir=Path("dataset_official"),
        num_cases=64,
    )"""

    create_test_set(
        method="random",
        source_data=source_data,
        output_dir=Path("dataset"),
        num_cases=64,
    )

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Setup AEOS-Bench test data with transparent methodology"
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip download if constellation_data.tar already exists",
    )

    args = parser.parse_args()

    if args.skip_download and Path("constellation_data.tar").exists():
        print("⏭️  Skipping download (--skip-download flag set)")
        if not Path("constellation_data/data").exists():
            extract_tar(Path("constellation_data.tar"), Path("."))
        source_data = Path("constellation_data/data")
        #create_test_set("official", source_data, Path("dataset_official"), 64)
        create_test_set("random", source_data, Path("dataset"), 64)
    else:
        main()
