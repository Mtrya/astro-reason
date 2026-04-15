"""Validate benchmark contract rules for finished benchmarks."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import shutil
import subprocess
import sys
import tempfile

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
FINISHED_BENCHMARKS_PATH = REPO_ROOT / "benchmarks" / "finished_benchmarks.json"
ALLOWED_ROOT_FILES = {
    "README.md",
    "__init__.py",
    "generator.py",
    "verifier.py",
    "visualizer.py",
    "splits.yaml",
}
ALLOWED_ROOT_DIRS = {"dataset", "generator", "verifier", "visualizer"}
BANNED_CODE_SNIPPETS = {
    "sys.path.insert": "contains a sys.path hack",
    "from benchmarks.": "imports through the benchmarks package path",
}
ROOT_ENTRY_REQUIRED_GROUPS = (
    ("README.md",),
    ("dataset",),
    ("splits.yaml",),
    ("generator.py", "generator"),
    ("verifier.py", "verifier"),
)
EXAMPLE_SOLUTION_FILENAMES = (
    "example_solution.json",
    "example_solution.yaml",
    "example_solution.yml",
)
SPLITS_FILENAME = "splits.yaml"
SMOKE_CASE_FIELD = "example_smoke_case"
LEGACY_SMOKE_CASE_FIELD = "example_smoke_case_id"


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


def generator_entrypoint(benchmark_root: Path) -> Path | None:
    for relative in ("generator.py", "generator/run.py"):
        candidate = benchmark_root / relative
        if candidate.exists():
            return candidate
    return None


def verifier_entrypoint(benchmark_root: Path) -> Path | None:
    for relative in ("verifier.py", "verifier/run.py"):
        candidate = benchmark_root / relative
        if candidate.exists():
            return candidate
    return None


def _is_nested_run_py(entrypoint: Path, benchmark_root: Path) -> bool:
    try:
        rel = entrypoint.relative_to(benchmark_root)
    except ValueError:
        return False
    return (
        len(rel.parts) == 2
        and rel.parts[1] == "run.py"
        and rel.parts[0] in ("generator", "verifier", "visualizer")
    )


def python_cmd_for_entrypoint(
    benchmark_name: str,
    entrypoint: Path,
    benchmark_root: Path,
    extra_args: list[str],
) -> list[str]:
    """Build argv for generator/verifier/visualizer per layout policy."""
    if _is_nested_run_py(entrypoint, benchmark_root):
        subpkg = entrypoint.relative_to(benchmark_root).parts[0]
        return [sys.executable, "-m", f"benchmarks.{benchmark_name}.{subpkg}.run", *extra_args]
    return [sys.executable, str(entrypoint), *extra_args]


def _is_valid_path_segment(value: object) -> bool:
    return isinstance(value, str) and value not in {"", ".", ".."} and "/" not in value and "\\" not in value


def _normalize_assignment_case_id(value: object) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        candidate = str(value)
    elif isinstance(value, str):
        candidate = value
    else:
        return None
    if not _is_valid_path_segment(candidate):
        return None
    return candidate


def validate_splits_payload(payload: object, source: Path | str) -> list[str]:
    label = str(source)
    if not isinstance(payload, dict):
        return [f"{label}: splits config must be a YAML mapping with a top-level 'splits' key"]

    splits = payload.get("splits")
    if not isinstance(splits, dict) or not splits:
        return [f"{label}: splits config must include a non-empty top-level 'splits' mapping"]

    errors: list[str] = []
    schema_kind: str | None = None
    for split_name, split_value in splits.items():
        if not _is_valid_path_segment(split_name):
            errors.append(
                f"{label}: split name {split_name!r} must be a non-empty single path segment"
            )
            continue

        if isinstance(split_value, dict):
            kind = "parameters"
            for key in split_value:
                if not isinstance(key, str) or not key:
                    errors.append(
                        f"{label}: split {split_name!r} has a non-string or empty parameter key"
                    )
        elif isinstance(split_value, list):
            kind = "assignments"
            seen_case_ids: set[str] = set()
            for case_id in split_value:
                normalized_case_id = _normalize_assignment_case_id(case_id)
                if normalized_case_id is None:
                    errors.append(
                        f"{label}: split {split_name!r} has invalid case id {case_id!r}; "
                        "case ids must be non-empty single path segments"
                    )
                    continue
                if normalized_case_id in seen_case_ids:
                    errors.append(
                        f"{label}: split {split_name!r} lists case id {normalized_case_id!r} more than once"
                    )
                seen_case_ids.add(normalized_case_id)
        else:
            kind = None
            errors.append(
                f"{label}: split {split_name!r} must map to either a parameter mapping "
                "or a list of case ids"
            )

        if kind is None:
            continue
        if schema_kind is None:
            schema_kind = kind
        elif kind != schema_kind:
            errors.append(
                f"{label}: all 'splits' entries must use one schema, not mixed "
                f"{schema_kind} and {kind} values"
            )

    return errors


def load_splits_config(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"missing required {path.name}")
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"{path}: failed to load YAML: {exc}") from exc

    errors = validate_splits_payload(payload, path)
    if errors:
        raise ValueError("; ".join(errors))
    splits = payload["splits"]
    if isinstance(splits, dict):
        normalized_splits: dict[str, object] = {}
        for split_name, split_value in splits.items():
            if isinstance(split_value, list):
                normalized_splits[split_name] = [
                    _normalize_assignment_case_id(case_id)
                    for case_id in split_value
                ]
            else:
                normalized_splits[split_name] = split_value
        payload["splits"] = normalized_splits
    return payload


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


def _iter_case_directories(cases_dir: Path) -> list[Path]:
    case_dirs: list[Path] = []
    if not cases_dir.is_dir():
        return case_dirs
    for split_dir in sorted(path for path in cases_dir.iterdir() if path.is_dir()):
        case_dirs.extend(sorted(path for path in split_dir.iterdir() if path.is_dir()))
    return case_dirs


def _validate_smoke_case_relative_path(value: str) -> tuple[str, str] | None:
    parts = PurePosixPath(value).parts
    if len(parts) != 2:
        return None
    split_name, case_id = parts
    if not _is_valid_path_segment(split_name) or not _is_valid_path_segment(case_id):
        return None
    return split_name, case_id


def resolve_smoke_case_dir(dataset_dir: Path) -> tuple[Path | None, list[str]]:
    cases_dir = dataset_dir / "cases"
    case_dirs = _iter_case_directories(cases_dir)
    if not case_dirs:
        return None, []

    index_path = dataset_dir / "index.json"
    if not index_path.is_file():
        return case_dirs[0], []

    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        return case_dirs[0], [f"{index_path}: failed to parse JSON: {exc}"]

    errors: list[str] = []

    smoke_case = index.get(SMOKE_CASE_FIELD)
    if smoke_case is not None:
        if not isinstance(smoke_case, str) or not smoke_case:
            errors.append(
                f"{index_path}: {SMOKE_CASE_FIELD!r} must be a non-empty string like 'test/case_0001'"
            )
        else:
            parsed = _validate_smoke_case_relative_path(smoke_case)
            if parsed is None:
                errors.append(
                    f"{index_path}: {SMOKE_CASE_FIELD!r} must be a relative path of the form "
                    "'<split>/<case_id>'"
                )
            else:
                candidate = cases_dir / parsed[0] / parsed[1]
                if candidate.is_dir():
                    return candidate, errors
                errors.append(
                    f"{index_path}: {SMOKE_CASE_FIELD!r} points to missing case directory {smoke_case!r}"
                )

    legacy_smoke_case = index.get(LEGACY_SMOKE_CASE_FIELD)
    if legacy_smoke_case is not None:
        errors.append(
            f"{index_path}: use {SMOKE_CASE_FIELD!r} instead of legacy {LEGACY_SMOKE_CASE_FIELD!r}"
        )
        if isinstance(legacy_smoke_case, str) and legacy_smoke_case:
            matches = [case_dir for case_dir in case_dirs if case_dir.name == legacy_smoke_case]
            if len(matches) == 1:
                return matches[0], errors
            if len(matches) > 1:
                errors.append(
                    f"{index_path}: legacy {LEGACY_SMOKE_CASE_FIELD!r} value {legacy_smoke_case!r} "
                    "is ambiguous under split layout"
                )
            else:
                errors.append(
                    f"{index_path}: legacy {LEGACY_SMOKE_CASE_FIELD!r} value {legacy_smoke_case!r} "
                    "does not resolve under split layout"
                )

    return case_dirs[0], errors


def _check_splits_file(benchmark_root: Path, errors: list[str]) -> None:
    splits_path = benchmark_root / SPLITS_FILENAME
    try:
        load_splits_config(splits_path)
    except (FileNotFoundError, ValueError) as exc:
        errors.append(f"{benchmark_root.name}: {exc}")


def _check_dataset_layout(benchmark_root: Path, errors: list[str]) -> None:
    dataset_dir = benchmark_root / "dataset"
    cases_dir = dataset_dir / "cases"
    if not cases_dir.is_dir():
        errors.append(f"{benchmark_root.name}: dataset/cases is required")
        return

    direct_files = sorted(path.name for path in cases_dir.iterdir() if path.is_file())
    if direct_files:
        errors.append(
            f"{benchmark_root.name}: dataset/cases must contain only split directories, not files at its root"
        )

    split_dirs = sorted(path for path in cases_dir.iterdir() if path.is_dir())
    if not split_dirs:
        errors.append(f"{benchmark_root.name}: dataset/cases must contain at least one split directory")

    case_dirs = _iter_case_directories(cases_dir)
    if not case_dirs:
        errors.append(
            f"{benchmark_root.name}: dataset/cases must contain at least one case directory under "
            "dataset/cases/<split>/"
        )

    for split_dir in split_dirs:
        if any(path.is_file() for path in split_dir.iterdir()):
            errors.append(
                f"{benchmark_root.name}: split directory dataset/cases/{split_dir.name} must contain "
                "case directories, not files directly"
            )
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
            if len(relative.parts) < 4:
                errors.append(
                    f"{benchmark_root.name}: tracked case content must live under "
                    "dataset/cases/<split>/<case_id>/..."
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
    entrypoint = generator_entrypoint(benchmark_root)
    if entrypoint is None:
        errors.append(f"{benchmark_root.name}: missing generator entrypoint")
        return
    result = subprocess.run(
        python_cmd_for_entrypoint(benchmark_root.name, entrypoint, benchmark_root, ["--help"]),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        errors.append(f"{benchmark_root.name}: generator --help failed: {result.stderr}")
    elif "usage:" not in result.stdout.lower():
        errors.append(f"{benchmark_root.name}: generator --help missing usage information")


def _copy_benchmark_without_dataset(src: Path, dst: Path) -> None:
    shutil.copytree(
        src,
        dst,
        ignore=shutil.ignore_patterns("dataset", "__pycache__", "*.pyc"),
        dirs_exist_ok=True,
    )


def _stage_generator_temp_copy(benchmark_root: Path, temp_root: Path) -> tuple[Path, Path]:
    entrypoint = generator_entrypoint(benchmark_root)
    if entrypoint is None:
        raise FileNotFoundError(f"missing generator entrypoint for {benchmark_root.name}")

    if _is_nested_run_py(entrypoint, benchmark_root):
        benchmarks_pkg = temp_root / "benchmarks"
        benchmarks_pkg.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / "benchmarks" / "__init__.py", benchmarks_pkg / "__init__.py")
        temp_benchmark_root = benchmarks_pkg / benchmark_root.name
        _copy_benchmark_without_dataset(benchmark_root, temp_benchmark_root)
    else:
        temp_benchmark_root = temp_root / benchmark_root.name
        _copy_benchmark_without_dataset(benchmark_root, temp_benchmark_root)

    temp_entrypoint = temp_benchmark_root / entrypoint.relative_to(benchmark_root)
    return temp_benchmark_root, temp_entrypoint


def _generator_run_env(
    benchmark_name: str,
    benchmark_root: Path,
    entrypoint: Path,
    temp_root: Path,
) -> tuple[list[str], Path, dict[str, str]]:
    command = python_cmd_for_entrypoint(benchmark_name, entrypoint, benchmark_root, [])
    env = dict(os.environ)
    if _is_nested_run_py(entrypoint, benchmark_root):
        env["PYTHONPATH"] = str(temp_root)
        cwd = temp_root
    else:
        cwd = benchmark_root
    return command, cwd, env


def _check_generator_requires_config_path(benchmark_root: Path, errors: list[str]) -> None:
    entrypoint = generator_entrypoint(benchmark_root)
    if entrypoint is None:
        errors.append(f"{benchmark_root.name}: missing generator entrypoint")
        return

    with tempfile.TemporaryDirectory(prefix=f"{benchmark_root.name}-generator-contract-") as temp_dir_name:
        temp_root = Path(temp_dir_name)
        temp_benchmark_root, temp_entrypoint = _stage_generator_temp_copy(benchmark_root, temp_root)
        command, cwd, env = _generator_run_env(
            benchmark_root.name,
            temp_benchmark_root,
            temp_entrypoint,
            temp_root,
        )
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
                env=env,
                timeout=5,
            )
        except subprocess.TimeoutExpired:
            errors.append(
                f"{benchmark_root.name}: generator must fail immediately when invoked without the "
                f"required {SPLITS_FILENAME} path"
            )
            return

    combined_output = "\n".join(part for part in (result.stdout, result.stderr) if part).lower()
    if result.returncode == 0:
        errors.append(
            f"{benchmark_root.name}: generator must require an explicit {SPLITS_FILENAME} path and "
            "must fail when invoked without arguments"
        )
    elif "usage:" not in combined_output:
        errors.append(
            f"{benchmark_root.name}: generator missing-argument failure must include usage information"
        )


def _check_verifier_smoke(benchmark_root: Path, errors: list[str]) -> None:
    verifier_cmd_entrypoint = verifier_entrypoint(benchmark_root)
    if verifier_cmd_entrypoint is None:
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
        _load_example_solution_payload(solutions_path)
    except (json.JSONDecodeError, yaml.YAMLError, OSError, UnicodeDecodeError, ValueError) as e:
        errors.append(f"{benchmark_root.name}: failed to parse {label}: {e}")
        return

    case_dir, smoke_errors = resolve_smoke_case_dir(dataset_dir)
    errors.extend(f"{benchmark_root.name}: {message}" for message in smoke_errors)
    if case_dir is None:
        errors.append(f"{benchmark_root.name}: no cases found for smoke test")
        return

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        env = dict(os.environ)
        env["MPLCONFIGDIR"] = str(tmp_path / "mplconfig")

        result = subprocess.run(
            python_cmd_for_entrypoint(
                benchmark_root.name,
                verifier_cmd_entrypoint,
                benchmark_root,
                [str(case_dir), str(solutions_path)],
            ),
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
        _check_splits_file(benchmark_root, errors)
        _check_dataset_layout(benchmark_root, errors)
        _check_public_code(benchmark_root, errors)
        _check_generator_help(benchmark_root, errors)
        _check_generator_requires_config_path(benchmark_root, errors)
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
