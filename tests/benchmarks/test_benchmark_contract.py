from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from scripts.validate_benchmark_contract import (
    find_example_solution,
    load_finished_benchmarks,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def _generator_entrypoint(benchmark_root: Path) -> Path:
    for relative in ("generator.py", "generator/run.py"):
        candidate = benchmark_root / relative
        if candidate.exists():
            return candidate
    raise AssertionError(f"missing generator entrypoint for {benchmark_root.name}")


def _verifier_entrypoint(benchmark_root: Path) -> Path:
    for relative in ("verifier.py", "verifier/run.py"):
        candidate = benchmark_root / relative
        if candidate.exists():
            return candidate
    raise AssertionError(f"missing verifier entrypoint for {benchmark_root.name}")


def test_finished_benchmark_metadata_is_nonempty():
    benchmarks = load_finished_benchmarks()
    assert benchmarks
    assert len({benchmark.name for benchmark in benchmarks}) == len(benchmarks)


def test_contract_validator_script_passes():
    result = subprocess.run(
        [sys.executable, "scripts/validate_benchmark_contract.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "passed" in result.stdout.lower()


def test_finished_benchmark_generators_are_runnable_via_help():
    for benchmark in load_finished_benchmarks():
        benchmark_root = REPO_ROOT / "benchmarks" / benchmark.name
        entrypoint = _generator_entrypoint(benchmark_root)
        result = subprocess.run(
            [sys.executable, str(entrypoint), "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        assert "usage:" in result.stdout.lower()


def test_finished_benchmark_verifier_examples_run(tmp_path):
    import json

    env = dict(os.environ)
    env["MPLCONFIGDIR"] = str(tmp_path / "mplconfig")

    for benchmark in load_finished_benchmarks():
        benchmark_root = REPO_ROOT / "benchmarks" / benchmark.name
        verifier_entrypoint = _verifier_entrypoint(benchmark_root)
        dataset_dir = benchmark_root / "dataset"
        solutions_path = find_example_solution(dataset_dir)

        assert solutions_path, f"{benchmark.name} is missing example_solution.json"

        all_solutions = json.loads(solutions_path.read_text())
        assert all_solutions, f"{benchmark.name} has empty example_solution.json"

        cases_dir = dataset_dir / "cases"
        case_dirs = sorted(path for path in cases_dir.iterdir() if path.is_dir())
        assert case_dirs, f"{benchmark.name} has no cases"

        case_solution = None
        case_dir = None
        case_id = None
        for cd in case_dirs:
            cid = cd.name
            if cid in all_solutions:
                case_solution = all_solutions[cid]
                case_dir = cd
                case_id = cid
                break

        assert case_solution is not None, f"{benchmark.name} has no example solution for any case"

        case_solution_path = tmp_path / f"{benchmark.name}_{case_id}_solution.json"
        case_solution_path.write_text(json.dumps(case_solution))

        result = subprocess.run(
            [
                sys.executable,
                str(verifier_entrypoint),
                str(case_dir),
                str(case_solution_path),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip(), f"{benchmark.name} verifier did not produce output"
