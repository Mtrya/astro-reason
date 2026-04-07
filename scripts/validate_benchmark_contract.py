"""Validate benchmark contract rules for finished benchmarks."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
FINISHED_BENCHMARKS_PATH = REPO_ROOT / "benchmarks" / "finished_benchmarks.json"
ALLOWED_ROOT_FILES = {"README.md", "generator.py", "verifier.py", "visualizer.py"}
ALLOWED_ROOT_DIRS = {"dataset", "generator", "verifier", "visualizer"}
BANNED_CODE_SNIPPETS = {
    "sys.path.insert": "contains a sys.path hack",
    "from benchmarks.": "imports through the benchmarks package path",
}
ROOT_ENTRY_REQUIRED_GROUPS = (
    ("README.md",),
    ("dataset",),
    ("generator.py", "generator"),
    ("verifier.py", "verifier"),
)
EXAMPLE_SOLUTION_FILENAMES = (
    "example_solution.json",
    "example_solution.yaml",
    "example_solution.yml",
)


@dataclass(frozen=True)
class FinishedBenchmark:
    name: str
    repro_ci: bool
    generated_paths: tuple[str, ...]


def load_finished_benchmarks(path: Path = FINISHED_BENCHMARKS_PATH) -> list[FinishedBenchmark]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    benchmarks = []
    for item in payload["benchmarks"]:
        benchmarks.append(
            FinishedBenchmark(
                name=item["name"],
                repro_ci=bool(item["repro_ci"]),
                generated_paths=tuple(item.get("generated_paths", [])),
            )
        )
    return benchmarks


def find_example_solution(dataset_dir: Path) -> Path | None:
    for filename in EXAMPLE_SOLUTION_FILENAMES:
        solutions_path = dataset_dir / filename
        if solutions_path.is_file():
            return solutions_path
    return None


def _load_example_solution_payload(path: Path) -> object:
    """Load dataset-level example solution from JSON or YAML (contract allows both)."""
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        return json.loads(text)
    if suffix in (".yaml", ".yml"):
        return yaml.safe_load(text)
    raise ValueError(f"unsupported example solution extension {suffix!r} for {path.name}")


def _generator_entrypoint(benchmark_root: Path) -> Path | None:
    for relative in ("generator.py", "generator/run.py"):
        candidate = benchmark_root / relative
        if candidate.exists():
            return candidate
    return None


def _verifier_entrypoint(benchmark_root: Path) -> Path | None:
    for relative in ("verifier.py", "verifier/run.py"):
        candidate = benchmark_root / relative
        if candidate.exists():
            return candidate
    return None


def _git_tracked_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", str(root.relative_to(REPO_ROOT))],
        cwd=REPO_ROOT,
        capture_output=True,
        text=False,
        check=True,
    )
    output = result.stdout.decode("utf-8")
    paths = [Path(item) for item in output.split("\x00") if item]
    return [REPO_ROOT / path for path in paths if (REPO_ROOT / path).exists()]


def _check_required_root_entries(benchmark_root: Path, errors: list[str]) -> None:
    tracked_files = _git_tracked_files(benchmark_root)
    top_level_entries = {
        path.relative_to(benchmark_root).parts[0]
        for path in tracked_files
        if path != benchmark_root
    }

    for allowed_group in ROOT_ENTRY_REQUIRED_GROUPS:
        if not any(entry in top_level_entries for entry in allowed_group):
            joined = " or ".join(allowed_group)
            errors.append(f"{benchmark_root.name}: missing required root entry {joined}")

    for entry in sorted(top_level_entries):
        if entry in ALLOWED_ROOT_FILES or entry in ALLOWED_ROOT_DIRS:
            continue
        errors.append(f"{benchmark_root.name}: unexpected tracked root entry {entry}")


def _check_dataset_layout(benchmark_root: Path, errors: list[str]) -> None:
    dataset_dir = benchmark_root / "dataset"
    cases_dir = dataset_dir / "cases"
    if not cases_dir.is_dir():
        errors.append(f"{benchmark_root.name}: dataset/cases is required")
        return

    case_dirs = sorted(path for path in cases_dir.iterdir() if path.is_dir())
    if not case_dirs:
        errors.append(f"{benchmark_root.name}: dataset/cases must contain at least one case directory")
    if find_example_solution(dataset_dir) is None:
        errors.append(
            f"{benchmark_root.name}: dataset must include example_solution.json, "
            "example_solution.yaml, or example_solution.yml"
        )

    for tracked_path in _git_tracked_files(dataset_dir):
        relative = tracked_path.relative_to(dataset_dir)
        top = relative.parts[0]
        if top == "source_data":
            errors.append(f"{benchmark_root.name}: dataset/source_data must not be tracked")
            continue
        if tracked_path.name.endswith("~"):
            errors.append(f"{benchmark_root.name}: editor backup artifact must not be tracked: {relative}")
            continue
        if top == "cases":
            if len(relative.parts) < 3:
                errors.append(
                    f"{benchmark_root.name}: tracked case content must live under dataset/cases/<case_id>/..."
                )


def _iter_public_code_files(benchmark_root: Path) -> list[Path]:
    code_paths: list[Path] = []
    for entry_name in ("generator.py", "verifier.py", "visualizer.py"):
        path = benchmark_root / entry_name
        if path.is_file():
            code_paths.append(path)
    for entry_name in ("generator", "verifier", "visualizer"):
        directory = benchmark_root / entry_name
        if directory.is_dir():
            code_paths.extend(sorted(path for path in directory.rglob("*.py") if path.is_file()))
    return code_paths


def _check_public_code(benchmark_root: Path, errors: list[str]) -> None:
    for path in _iter_public_code_files(benchmark_root):
        text = path.read_text(encoding="utf-8")
        for snippet, explanation in BANNED_CODE_SNIPPETS.items():
            if snippet in text:
                relative = path.relative_to(REPO_ROOT)
                errors.append(f"{relative}: {explanation}")


def _check_generator_help(benchmark_root: Path, errors: list[str]) -> None:
    entrypoint = _generator_entrypoint(benchmark_root)
    if entrypoint is None:
        errors.append(f"{benchmark_root.name}: missing generator entrypoint")
        return
    result = subprocess.run(
        [sys.executable, str(entrypoint), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        errors.append(f"{benchmark_root.name}: generator --help failed: {result.stderr}")
    elif "usage:" not in result.stdout.lower():
        errors.append(f"{benchmark_root.name}: generator --help missing usage information")


def _example_solution_shape_ok(parsed: object) -> bool:
    """True if parsed example solution matches a single-solution file (not a legacy case-id mapping)."""
    if parsed == {}:
        return False
    if isinstance(parsed, list):
        return True
    if not isinstance(parsed, dict):
        return False
    if any(
        key in parsed
        for key in ("actions", "claimed_profit", "assignments", "satellites")
    ):
        return True
    return False


def _resolve_smoke_case_dir(dataset_dir: Path) -> Path | None:
    cases_dir = dataset_dir / "cases"
    case_dirs = sorted(path for path in cases_dir.iterdir() if path.is_dir())
    if not case_dirs:
        return None
    index_path = dataset_dir / "index.json"
    if index_path.is_file():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            index = {}
        else:
            cid = index.get("example_smoke_case_id")
            if isinstance(cid, str) and cid:
                candidate = cases_dir / cid
                if candidate.is_dir():
                    return candidate
    return case_dirs[0]


def _check_verifier_smoke(benchmark_root: Path, errors: list[str]) -> None:
    verifier_entrypoint = _verifier_entrypoint(benchmark_root)
    if verifier_entrypoint is None:
        errors.append(f"{benchmark_root.name}: missing verifier entrypoint")
        return

    dataset_dir = benchmark_root / "dataset"
    solutions_path = find_example_solution(dataset_dir)
    if solutions_path is None:
        errors.append(
            f"{benchmark_root.name}: missing example solution file for smoke test "
            "(example_solution.json, example_solution.yaml, or example_solution.yml)"
        )
        return

    label = solutions_path.name
    try:
        parsed = _load_example_solution_payload(solutions_path)
    except (json.JSONDecodeError, yaml.YAMLError, OSError, UnicodeDecodeError, ValueError) as e:
        errors.append(f"{benchmark_root.name}: failed to parse {label}: {e}")
        return

    if not _example_solution_shape_ok(parsed):
        errors.append(
            f"{benchmark_root.name}: {label} must be a single solution "
            "(same schema as a per-case solution file), not a mapping of case IDs"
        )
        return

    case_dir = _resolve_smoke_case_dir(dataset_dir)
    if case_dir is None:
        errors.append(f"{benchmark_root.name}: no cases found for smoke test")
        return

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        env = dict(os.environ)
        env["MPLCONFIGDIR"] = str(tmp_path / "mplconfig")

        result = subprocess.run(
            [
                sys.executable,
                str(verifier_entrypoint),
                str(case_dir),
                str(solutions_path),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )

        if result.returncode != 0:
            errors.append(f"{benchmark_root.name}: verifier smoke test failed: {result.stderr}")
        elif not result.stdout.strip():
            errors.append(f"{benchmark_root.name}: verifier produced no output")


def validate_finished_benchmarks(repo_root: Path = REPO_ROOT) -> list[str]:
    errors: list[str] = []
    for benchmark in load_finished_benchmarks(repo_root / "benchmarks" / "finished_benchmarks.json"):
        benchmark_root = repo_root / "benchmarks" / benchmark.name
        if not benchmark_root.is_dir():
            errors.append(f"{benchmark.name}: benchmark directory does not exist")
            continue
        _check_required_root_entries(benchmark_root, errors)
        _check_dataset_layout(benchmark_root, errors)
        _check_public_code(benchmark_root, errors)
        _check_generator_help(benchmark_root, errors)
        _check_verifier_smoke(benchmark_root, errors)
    return errors


def main() -> int:
    errors = validate_finished_benchmarks()
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("Finished benchmark contract validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
