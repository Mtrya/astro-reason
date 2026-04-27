from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "solvers" / "finished_solvers.json"
ENTRY_KEYS = {
    "benchmark",
    "solver",
    "repro_ci",
    "repro_ci_reason",
    "case_and_fixture_paths",
}
CASE_FIXTURE_KEYS = {"case_path", "fixture_path"}
PYTHON_IMPORT_PATTERN = re.compile(
    r"^\s*(?:from|import)\s+(benchmarks|experiments|runtimes|solvers)(?:\.|\s|$)",
    re.MULTILINE,
)
EXECUTION_PATTERNS = (
    re.compile(r"python(?:3)?\s+-m\s+(benchmarks|experiments|runtimes|solvers)\b"),
    re.compile(r"\b(benchmarks|experiments|runtimes)\.[A-Za-z0-9_]"),
)
GENERATED_DIR_NAMES = {
    ".gradle",
    ".julia",
    ".m2",
    ".minizinc",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "debug",
    "dist",
    "env",
    "node_modules",
    "solution",
    "target",
    "venv",
}
DEFAULT_SETUP_TIMEOUT_S = 600.0
DEFAULT_SOLVE_TIMEOUT_S = 600.0
DEFAULT_TEST_TIMEOUT_S = 600.0


def _load_registry(errors: list[str]) -> dict[str, Any]:
    try:
        payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{REGISTRY_PATH}: invalid JSON: {exc}")
        return {}
    if not isinstance(payload, dict):
        errors.append(f"{REGISTRY_PATH}: top-level value must be an object")
        return {}
    unexpected = set(payload) - {"solvers"}
    if unexpected:
        errors.append(
            f"{REGISTRY_PATH}: unsupported top-level keys: {', '.join(sorted(unexpected))}"
        )
    if not isinstance(payload.get("solvers"), list):
        errors.append(f"{REGISTRY_PATH}: 'solvers' must be a list")
        return {}
    return payload


def _solver_path(entry: dict[str, Any]) -> Path:
    return REPO_ROOT / "solvers" / str(entry["benchmark"]) / str(entry["solver"])


def _is_executable(path: Path) -> bool:
    return path.exists() and path.is_file() and os.access(path, os.X_OK)


def _validate_case_fixture_paths(
    entry: dict[str, Any], solver_label: str, errors: list[str]
) -> None:
    values = entry.get("case_and_fixture_paths")
    if not isinstance(values, list):
        errors.append(f"{solver_label}: case_and_fixture_paths must be a list")
        return
    if entry.get("repro_ci") is True and not values:
        errors.append(f"{solver_label}: repro_ci true requires at least one case path")
    for index, item in enumerate(values):
        where = f"{solver_label}: case_and_fixture_paths[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{where} must be an object")
            continue
        unexpected = set(item) - CASE_FIXTURE_KEYS
        missing = CASE_FIXTURE_KEYS - set(item)
        if unexpected:
            errors.append(f"{where}: unsupported keys: {', '.join(sorted(unexpected))}")
        if missing:
            errors.append(f"{where}: missing keys: {', '.join(sorted(missing))}")
            continue
        case_path = item["case_path"]
        fixture_path = item["fixture_path"]
        if not isinstance(case_path, str) or not case_path:
            errors.append(f"{where}: case_path must be a non-empty string")
        elif not (REPO_ROOT / case_path).exists():
            errors.append(f"{where}: case_path does not exist: {case_path}")
        if not isinstance(fixture_path, str):
            errors.append(f"{where}: fixture_path must be a string, or empty if unused")
        elif fixture_path and not (REPO_ROOT / fixture_path).exists():
            errors.append(f"{where}: fixture_path does not exist: {fixture_path}")


def _validate_registry(errors: list[str]) -> list[dict[str, Any]]:
    payload = _load_registry(errors)
    entries = payload.get("solvers", [])
    if not isinstance(entries, list):
        return []

    seen: set[tuple[str, str]] = set()
    normalized: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        where = f"{REGISTRY_PATH}: solvers[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{where}: entry must be an object")
            continue
        unexpected = set(entry) - ENTRY_KEYS
        if unexpected:
            errors.append(f"{where}: unsupported keys: {', '.join(sorted(unexpected))}")
        required = {"benchmark", "solver", "repro_ci", "case_and_fixture_paths"}
        missing = required - set(entry)
        if missing:
            errors.append(f"{where}: missing keys: {', '.join(sorted(missing))}")
            continue
        benchmark = entry["benchmark"]
        solver = entry["solver"]
        if not isinstance(benchmark, str) or not benchmark:
            errors.append(f"{where}: benchmark must be a non-empty string")
            continue
        if not isinstance(solver, str) or not solver:
            errors.append(f"{where}: solver must be a non-empty string")
            continue
        label = f"{benchmark}/{solver}"
        key = (benchmark, solver)
        if key in seen:
            errors.append(f"{where}: duplicate solver entry {label}")
        seen.add(key)

        repro_ci = entry["repro_ci"]
        if not isinstance(repro_ci, bool):
            errors.append(f"{label}: repro_ci must be a boolean")

        solver_dir = _solver_path(entry)
        if not solver_dir.is_dir():
            errors.append(f"{label}: expected solver directory at {solver_dir.relative_to(REPO_ROOT)}")
        elif not (solver_dir / "README.md").is_file():
            errors.append(f"{label}: missing README.md")
        if repro_ci is True:
            for script in ("setup.sh", "solve.sh"):
                script_path = solver_dir / script
                if not _is_executable(script_path):
                    errors.append(f"{label}: {script} must exist and be executable")
        test_script = solver_dir / "test.sh"
        if test_script.exists() and not _is_executable(test_script):
            errors.append(f"{label}: test.sh exists but is not executable")
        _validate_case_fixture_paths(entry, label, errors)
        normalized.append(entry)
    return normalized


def _iter_solver_runtime_files() -> list[Path]:
    root = REPO_ROOT / "solvers"
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in GENERATED_DIR_NAMES and name != "tests"
        ]
        current = Path(dirpath)
        for filename in filenames:
            path = current / filename
            if path.name == "test.sh":
                continue
            if path.suffix == ".py" or path.suffix in {".sh", ".bash"}:
                files.append(path)
    return files


def _validate_boundaries(errors: list[str]) -> None:
    for path in _iter_solver_runtime_files():
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(REPO_ROOT)
        if path.suffix == ".py":
            for match in PYTHON_IMPORT_PATTERN.finditer(text):
                layer = match.group(1)
                errors.append(f"{rel}: solver runtime must not import {layer}/")
        for pattern in EXECUTION_PATTERNS:
            for match in pattern.finditer(text):
                layer = match.group(1)
                errors.append(f"{rel}: solver runtime must not execute or reference {layer}/")


def _validate_pytest_boundary(errors: list[str]) -> None:
    pytest_ini = REPO_ROOT / "pytest.ini"
    if not pytest_ini.exists():
        errors.append("pytest.ini is required so top-level pytest collection is explicit")
        return
    text = pytest_ini.read_text(encoding="utf-8")
    if re.search(r"(?m)^\s*testpaths\s*=", text) is None:
        errors.append("pytest.ini must define testpaths so top-level pytest is scoped")
    testpaths_match = re.search(r"(?ms)^\s*testpaths\s*=\s*(.+?)(?:\n\S|\Z)", text)
    if testpaths_match:
        for token in testpaths_match.group(1).split():
            first_component = token.strip("'\"").rstrip("/").split("/", 1)[0]
            if first_component == "solvers":
                errors.append("pytest.ini testpaths must not include solvers/")
                break
    solver_tests = sorted((REPO_ROOT / "tests" / "solvers").glob("test_*.py"))
    if solver_tests:
        listed = ", ".join(str(path.relative_to(REPO_ROOT)) for path in solver_tests)
        errors.append(f"top-level tests/solvers must be empty; use solver-local test.sh: {listed}")


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _run_command(
    command: list[str],
    *,
    cwd: Path,
    timeout_s: float | None = 600.0,
) -> tuple[int | None, str | None]:
    print(f"+ ({_display_path(cwd)}) {' '.join(command)}", flush=True)
    try:
        completed = subprocess.run(command, cwd=cwd, check=False, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout_s}s"
    except OSError as exc:
        return None, str(exc)
    return int(completed.returncode), None


def _run_solver_tests(entries: list[dict[str, Any]], errors: list[str]) -> None:
    for entry in entries:
        solver_dir = _solver_path(entry)
        test_script = solver_dir / "test.sh"
        if not test_script.exists():
            continue
        setup_script = solver_dir / "setup.sh"
        if setup_script.exists():
            setup_returncode, setup_error = _run_command(
                ["./setup.sh"],
                cwd=solver_dir,
                timeout_s=DEFAULT_SETUP_TIMEOUT_S,
            )
            if setup_error is not None:
                errors.append(
                    f"{entry['benchmark']}/{entry['solver']}: setup.sh could not complete before test.sh: {setup_error}"
                )
                continue
            if setup_returncode != 0:
                errors.append(
                    f"{entry['benchmark']}/{entry['solver']}: setup.sh failed before test.sh"
                )
                continue
        returncode, launch_error = _run_command(
            ["./test.sh"],
            cwd=solver_dir,
            timeout_s=DEFAULT_TEST_TIMEOUT_S,
        )
        if launch_error is not None:
            errors.append(
                f"{entry['benchmark']}/{entry['solver']}: test.sh could not complete: {launch_error}"
            )
        elif returncode != 0:
            errors.append(f"{entry['benchmark']}/{entry['solver']}: test.sh failed")


def _compare_fixture(solution_dir: Path, fixture_path: Path, label: str, errors: list[str]) -> None:
    outputs = sorted(
        path for path in solution_dir.iterdir() if path.is_file() and path.name != "status.json"
    )
    if not outputs:
        errors.append(f"{label}: repro run wrote no primary solution file")
        return
    if len(outputs) == 1:
        actual = outputs[0]
    else:
        actual = solution_dir / fixture_path.name
        if not actual.exists():
            names = ", ".join(path.name for path in outputs)
            errors.append(f"{label}: cannot match fixture to outputs: {names}")
            return
    if actual.read_bytes() != fixture_path.read_bytes():
        errors.append(f"{label}: solution output does not match fixture {fixture_path}")


def _run_repro_ci(entries: list[dict[str, Any]], errors: list[str]) -> None:
    for entry in entries:
        if entry.get("repro_ci") is not True:
            continue
        label = f"{entry['benchmark']}/{entry['solver']}"
        solver_dir = _solver_path(entry)
        returncode, launch_error = _run_command(
            ["./setup.sh"],
            cwd=solver_dir,
            timeout_s=DEFAULT_SETUP_TIMEOUT_S,
        )
        if launch_error is not None:
            errors.append(f"{label}: setup.sh could not complete: {launch_error}")
            continue
        if returncode != 0:
            errors.append(f"{label}: setup.sh failed")
            continue
        with tempfile.TemporaryDirectory(prefix="astroreason-solver-ci-") as tmp:
            tmp_root = Path(tmp)
            for index, item in enumerate(entry["case_and_fixture_paths"]):
                run_dir = tmp_root / f"case_{index}"
                config_dir = run_dir / "config"
                solution_dir = run_dir / "solution"
                config_dir.mkdir(parents=True)
                solution_dir.mkdir(parents=True)
                case_path = (REPO_ROOT / item["case_path"]).resolve()
                command = [
                    "./solve.sh",
                    str(case_path),
                    str(config_dir.resolve()),
                    str(solution_dir.resolve()),
                ]
                returncode, launch_error = _run_command(
                    command,
                    cwd=solver_dir,
                    timeout_s=DEFAULT_SOLVE_TIMEOUT_S,
                )
                if launch_error is not None:
                    errors.append(
                        f"{label}: solve.sh could not complete for {item['case_path']}: {launch_error}"
                    )
                    continue
                if returncode != 0:
                    errors.append(f"{label}: solve.sh failed for {item['case_path']}")
                    continue
                fixture = item.get("fixture_path", "")
                if fixture:
                    _compare_fixture(solution_dir, REPO_ROOT / fixture, label, errors)


def main() -> int:
    errors: list[str] = []
    entries = _validate_registry(errors)
    _validate_boundaries(errors)
    _validate_pytest_boundary(errors)
    _run_repro_ci(entries, errors)
    _run_solver_tests(entries, errors)

    if errors:
        print("Solver contract validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Solver contract validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
