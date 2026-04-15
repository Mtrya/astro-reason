"""Check reproducibility for finished benchmarks with repro CI enabled."""

from __future__ import annotations

import filecmp
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from validate_benchmark_contract import (
    generator_entrypoint,
    load_finished_benchmarks,
    load_splits_config,
    python_cmd_for_entrypoint,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


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


def _copy_benchmark_without_dataset(src: Path, dst: Path) -> None:
    shutil.copytree(
        src,
        dst,
        ignore=shutil.ignore_patterns("dataset", "__pycache__", "*.pyc"),
        dirs_exist_ok=True,
    )


def _stage_benchmark_copy(benchmark_root: Path, temp_root: Path) -> tuple[Path, Path]:
    entrypoint = generator_entrypoint(benchmark_root)
    if entrypoint is None:
        raise FileNotFoundError(f"No generator entrypoint found for {benchmark_root.name}")

    if entrypoint.parent.name == "generator" and entrypoint.name == "run.py":
        benchmarks_pkg = temp_root / "benchmarks"
        benchmarks_pkg.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / "benchmarks" / "__init__.py", benchmarks_pkg / "__init__.py")
        temp_benchmark_root = benchmarks_pkg / benchmark_root.name
    else:
        temp_benchmark_root = temp_root / benchmark_root.name

    _copy_benchmark_without_dataset(benchmark_root, temp_benchmark_root)
    temp_entrypoint = temp_benchmark_root / entrypoint.relative_to(benchmark_root)
    return temp_benchmark_root, temp_entrypoint


def _run_generator(
    benchmark_name: str,
    benchmark_root: Path,
    entrypoint: Path,
    splits_path: Path,
    temp_root: Path,
) -> None:
    env = dict(os.environ)
    if entrypoint.parent.name == "generator" and entrypoint.name == "run.py":
        env["PYTHONPATH"] = str(temp_root)
        cwd = temp_root
    else:
        cwd = benchmark_root

    subprocess.run(
        python_cmd_for_entrypoint(benchmark_name, entrypoint, benchmark_root, [str(splits_path)]),
        cwd=cwd,
        env=env,
        check=True,
    )


def check_reproducibility() -> list[str]:
    errors: list[str] = []
    for benchmark in load_finished_benchmarks():
        if not benchmark.repro_ci:
            continue
        benchmark_root = REPO_ROOT / "benchmarks" / benchmark.name
        splits_path = benchmark_root / "splits.yaml"
        try:
            load_splits_config(splits_path)
        except (FileNotFoundError, ValueError) as exc:
            errors.append(f"{benchmark.name}: {exc}")
            continue

        entrypoint = generator_entrypoint(benchmark_root)
        if entrypoint is None:
            errors.append(f"{benchmark.name}: No generator entrypoint found")
            continue
        with tempfile.TemporaryDirectory(prefix=f"{benchmark.name}-repro-") as temp_dir_name:
            temp_root = Path(temp_dir_name)
            temp_benchmark_root, temp_entrypoint = _stage_benchmark_copy(benchmark_root, temp_root)
            temp_splits_path = temp_benchmark_root / "splits.yaml"
            try:
                _run_generator(
                    benchmark.name,
                    temp_benchmark_root,
                    temp_entrypoint,
                    temp_splits_path,
                    temp_root,
                )
            except subprocess.CalledProcessError as exc:
                stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
                stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
                detail = stderr.strip() or stdout.strip() or f"exit code {exc.returncode}"
                errors.append(f"{benchmark.name}: generator failed when run with explicit splits.yaml path: {detail}")
                continue
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
