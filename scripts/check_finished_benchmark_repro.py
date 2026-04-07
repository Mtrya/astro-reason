"""Check reproducibility for finished benchmarks with repro CI enabled."""

from __future__ import annotations

import filecmp
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from validate_benchmark_contract import load_finished_benchmarks


REPO_ROOT = Path(__file__).resolve().parents[1]


def _generator_entrypoint(benchmark_root: Path) -> Path:
    for relative in ("generator.py", "generator/run.py"):
        candidate = benchmark_root / relative
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No generator entrypoint found for {benchmark_root.name}")


def _compare_paths(expected: Path, actual: Path, label: str, errors: list[str]) -> None:
    if expected.is_dir():
        if not actual.is_dir():
            errors.append(f"{label}: expected generated directory {actual} is missing")
            return
        comparison = filecmp.dircmp(expected, actual)
        # Check for files/directories that only exist on one side
        if comparison.left_only or comparison.right_only or comparison.funny_files:
            errors.append(
                f"{label}: generated directory differs for {expected.relative_to(REPO_ROOT)}"
            )
            return
        # Verify diff_files actually have different content (not just different mtime)
        for filename in comparison.diff_files:
            if not filecmp.cmp(expected / filename, actual / filename, shallow=False):
                errors.append(
                    f"{label}: generated file differs for {(expected / filename).relative_to(REPO_ROOT)}"
                )
                return
        for child in comparison.common_dirs:
            _compare_paths(expected / child, actual / child, label, errors)
        return

    if not actual.is_file():
        errors.append(f"{label}: expected generated file {actual} is missing")
        return
    # Use filecmp.cmp with shallow=False for efficient content comparison
    if not filecmp.cmp(expected, actual, shallow=False):
        errors.append(f"{label}: generated file differs for {expected.relative_to(REPO_ROOT)}")


def _run_generator_top_level(entrypoint: Path, cwd: Path) -> None:
    subprocess.run(
        [sys.executable, str(entrypoint)],
        cwd=cwd,
        check=True,
    )


def _prepare_nested_generator_package_layout(temp_root: Path, benchmark_name: str) -> None:
    """Lay out benchmarks.<name>.generator so `python -m` can run (matches contract)."""
    (temp_root / "benchmarks").mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "benchmarks" / "__init__.py", temp_root / "benchmarks" / "__init__.py")
    src_bench = REPO_ROOT / "benchmarks" / benchmark_name
    dst_bench = temp_root / "benchmarks" / benchmark_name
    dst_bench.mkdir(parents=True)
    shutil.copy2(src_bench / "__init__.py", dst_bench / "__init__.py")
    shutil.copytree(
        src_bench / "generator",
        dst_bench / "generator",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


def _run_nested_generator_module(temp_root: Path, benchmark_name: str) -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(temp_root)
    subprocess.run(
        [sys.executable, "-m", f"benchmarks.{benchmark_name}.generator.run"],
        cwd=temp_root,
        env=env,
        check=True,
    )


def _copy_generator(benchmark_root: Path, temp_benchmark_root: Path, entrypoint: Path) -> Path:
    """Copy generator files to temp directory."""
    temp_entrypoint = temp_benchmark_root / entrypoint.relative_to(benchmark_root)
    temp_entrypoint.parent.mkdir(parents=True, exist_ok=True)
    
    # If entrypoint is in a generator/ directory, copy the whole directory
    if entrypoint.parent.name == "generator":
        generator_dir = entrypoint.parent
        temp_generator_dir = temp_entrypoint.parent
        shutil.copytree(generator_dir, temp_generator_dir, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    else:
        # Single-file generator, just copy the entrypoint
        shutil.copy2(entrypoint, temp_entrypoint)
    
    return temp_entrypoint


def check_reproducibility() -> list[str]:
    errors: list[str] = []
    for benchmark in load_finished_benchmarks():
        if not benchmark.repro_ci:
            continue
        benchmark_root = REPO_ROOT / "benchmarks" / benchmark.name
        entrypoint = _generator_entrypoint(benchmark_root)
        with tempfile.TemporaryDirectory(prefix=f"{benchmark.name}-repro-") as temp_dir_name:
            temp_root = Path(temp_dir_name)
            nested_run = entrypoint.name == "run.py" and entrypoint.parent.name == "generator"
            if nested_run:
                _prepare_nested_generator_package_layout(temp_root, benchmark.name)
                _run_nested_generator_module(temp_root, benchmark.name)
                benchmark_out = temp_root / "benchmarks" / benchmark.name
            else:
                temp_benchmark_root = temp_root / benchmark.name
                temp_benchmark_root.mkdir(parents=True)
                temp_entrypoint = _copy_generator(benchmark_root, temp_benchmark_root, entrypoint)
                _run_generator_top_level(temp_entrypoint, temp_benchmark_root)
                benchmark_out = temp_benchmark_root
            # Compare generated paths
            for relative_str in benchmark.generated_paths:
                relative = Path(relative_str)
                expected = benchmark_root / relative
                actual = benchmark_out / relative
                _compare_paths(expected, actual, benchmark.name, errors)
    return errors


def main() -> int:
    errors = check_reproducibility()
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("Finished benchmark reproducibility checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
