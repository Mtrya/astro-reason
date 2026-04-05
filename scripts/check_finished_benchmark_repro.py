"""Check reproducibility for finished benchmarks with repro CI enabled."""

from __future__ import annotations

import filecmp
from pathlib import Path
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
        if comparison.left_only or comparison.right_only or comparison.diff_files or comparison.funny_files:
            errors.append(
                f"{label}: generated directory differs for {expected.relative_to(REPO_ROOT)}"
            )
            return
        for child in comparison.common_dirs:
            _compare_paths(expected / child, actual / child, label, errors)
        return

    if not actual.is_file():
        errors.append(f"{label}: expected generated file {actual} is missing")
        return
    if expected.read_bytes() != actual.read_bytes():
        errors.append(f"{label}: generated file differs for {expected.relative_to(REPO_ROOT)}")


def _run_generator(entrypoint: Path, output_dir: Path) -> None:
    subprocess.run(
        [sys.executable, str(entrypoint), "--output-dir", str(output_dir)],
        cwd=REPO_ROOT,
        check=True,
    )


def check_reproducibility() -> list[str]:
    errors: list[str] = []
    for benchmark in load_finished_benchmarks():
        if not benchmark.repro_ci:
            continue
        benchmark_root = REPO_ROOT / "benchmarks" / benchmark.name
        entrypoint = _generator_entrypoint(benchmark_root)
        with tempfile.TemporaryDirectory(prefix=f"{benchmark.name}-repro-") as temp_dir_name:
            output_dir = Path(temp_dir_name) / "dataset"
            _run_generator(entrypoint, output_dir)
            for relative_str in benchmark.generated_paths:
                relative = Path(relative_str)
                expected = benchmark_root / relative
                actual = output_dir / relative.relative_to("dataset")
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
