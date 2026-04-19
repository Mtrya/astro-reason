#!/usr/bin/env python3
"""Resolve the first AstroReason experiment scaffold."""

from __future__ import annotations

import argparse
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
WORKSPACE_MOUNT = Path("/app/workspace")
OUTPUT_MOUNT = Path("/app/run/output")


@dataclass(frozen=True)
class ExperimentManifest:
    name: str
    benchmark: str
    runtime: str
    python_packages: tuple[str, ...]
    required_config_files: tuple[str, ...]
    include_example_solution: bool
    include_verifier: bool
    timeout_seconds_default: int | None
    task_prompt_file: str
    experiment_dir: Path
    workspace_dir: Path
    config_dir: Path


@dataclass(frozen=True)
class RuntimeManifest:
    name: str
    image: str
    dockerfile: Path
    build_context: Path
    runtime_dir: Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve one AstroReason experiment scaffold")
    parser.add_argument("--split", default="test", help="Dataset split (default: test)")
    parser.add_argument("--case", required=True, help="Case ID")
    parser.add_argument(
        "--timeout",
        type=int,
        help="Override the experiment timeout in seconds for a future execution phase",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Resolve the interactive scaffold path instead of the future headless path",
    )
    return parser.parse_args(argv)


def _load_yaml_mapping(path: Path, kind: str) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"{kind} manifest does not exist: {path}")

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"Failed to parse {kind} manifest {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise SystemExit(f"{kind} manifest must contain a mapping: {path}")
    return data


def _require_str(data: dict[str, Any], key: str, kind: str, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise SystemExit(f"{kind} manifest field '{key}' must be a non-empty string: {path}")
    return value


def _optional_bool(data: dict[str, Any], key: str, default: bool, kind: str, path: Path) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise SystemExit(f"{kind} manifest field '{key}' must be a boolean: {path}")
    return value


def _optional_int(
    data: dict[str, Any],
    key: str,
    default: int | None,
    kind: str,
    path: Path,
) -> int | None:
    value = data.get(key, default)
    if value is None:
        return None
    if not isinstance(value, int):
        raise SystemExit(f"{kind} manifest field '{key}' must be an integer: {path}")
    return value


def _string_tuple(data: dict[str, Any], key: str, kind: str, path: Path) -> tuple[str, ...]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise SystemExit(f"{kind} manifest field '{key}' must be a list of strings: {path}")
    return tuple(value)


def load_experiment(experiment_dir: Path) -> ExperimentManifest:
    manifest_path = experiment_dir / "experiment.yaml"
    data = _load_yaml_mapping(manifest_path, "Experiment")

    experiment_name = _require_str(data, "name", "Experiment", manifest_path)
    if experiment_name != experiment_dir.name:
        raise SystemExit(
            f"Experiment manifest name mismatch: expected '{experiment_dir.name}', found '{experiment_name}' in {manifest_path}"
        )

    benchmark = _require_str(data, "benchmark", "Experiment", manifest_path)
    if benchmark != experiment_dir.parent.name:
        raise SystemExit(
            f"Experiment manifest benchmark mismatch: expected '{experiment_dir.parent.name}', found '{benchmark}' in {manifest_path}"
        )

    return ExperimentManifest(
        name=experiment_name,
        benchmark=benchmark,
        runtime=_require_str(data, "runtime", "Experiment", manifest_path),
        python_packages=_string_tuple(data, "python_packages", "Experiment", manifest_path),
        required_config_files=_string_tuple(
            data, "required_config_files", "Experiment", manifest_path
        ),
        include_example_solution=_optional_bool(
            data, "include_example_solution", True, "Experiment", manifest_path
        ),
        include_verifier=_optional_bool(data, "include_verifier", True, "Experiment", manifest_path),
        timeout_seconds_default=_optional_int(
            data, "timeout_seconds_default", None, "Experiment", manifest_path
        ),
        task_prompt_file=_require_str(
            {"task_prompt_file": data.get("task_prompt_file", "TASK.md")},
            "task_prompt_file",
            "Experiment",
            manifest_path,
        ),
        experiment_dir=experiment_dir,
        workspace_dir=experiment_dir / "workspace",
        config_dir=experiment_dir / "config",
    )


def load_runtime(name: str) -> RuntimeManifest:
    manifest_path = REPO_ROOT / "runtimes" / name / "runtime.yaml"
    data = _load_yaml_mapping(manifest_path, "Runtime")

    runtime_name = _require_str(data, "name", "Runtime", manifest_path)
    if runtime_name != name:
        raise SystemExit(
            f"Runtime manifest name mismatch: expected '{name}', found '{runtime_name}' in {manifest_path}"
        )

    runtime_dir = manifest_path.parent
    dockerfile = runtime_dir / _require_str(data, "dockerfile", "Runtime", manifest_path)
    build_context = runtime_dir / _require_str(data, "build_context", "Runtime", manifest_path)
    if not dockerfile.exists():
        raise SystemExit(f"Runtime dockerfile does not exist: {dockerfile}")
    if not build_context.exists():
        raise SystemExit(f"Runtime build context does not exist: {build_context}")

    return RuntimeManifest(
        name=runtime_name,
        image=_require_str(data, "image", "Runtime", manifest_path),
        dockerfile=dockerfile.resolve(),
        build_context=build_context.resolve(),
        runtime_dir=runtime_dir,
    )


def load_adapter(experiment: ExperimentManifest):
    adapter_path = experiment.experiment_dir / "adapter.py"
    if not adapter_path.exists():
        raise SystemExit(f"Experiment adapter does not exist: {adapter_path}")

    module_name = f"astroreason_experiment_{experiment.benchmark}_{experiment.name}_adapter"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Failed to load adapter from {adapter_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    required = (
        "NAME",
        "CONFIG_TARGET_DIR",
        "SESSION_LOG_TARGET_DIR",
        "INTERACTIVE_COMMAND",
        "build_headless_command",
    )
    missing = [name for name in required if not hasattr(module, name)]
    if missing:
        raise SystemExit(f"Adapter is missing required exports {missing}: {adapter_path}")
    return module


def _benchmark_root(benchmark: str) -> Path:
    return REPO_ROOT / "benchmarks" / benchmark


def _case_dir(experiment: ExperimentManifest, split: str, case_id: str) -> Path:
    return _benchmark_root(experiment.benchmark) / "dataset" / "cases" / split / case_id


def _example_solution_path(experiment: ExperimentManifest) -> Path | None:
    dataset_dir = _benchmark_root(experiment.benchmark) / "dataset"
    for candidate in ("example_solution.json", "example_solution.yaml", "example_solution.yml"):
        path = dataset_dir / candidate
        if path.exists():
            return path
    return None


def _verifier_path(experiment: ExperimentManifest) -> Path | None:
    benchmark_dir = _benchmark_root(experiment.benchmark)
    verifier_dir = benchmark_dir / "verifier"
    verifier_py = benchmark_dir / "verifier.py"
    if verifier_dir.is_dir():
        return verifier_dir
    if verifier_py.exists():
        return verifier_py
    return None


def _check_required_paths(
    experiment: ExperimentManifest,
    args: argparse.Namespace,
) -> tuple[Path, Path | None, Path | None]:
    benchmark_dir = _benchmark_root(experiment.benchmark)
    if not benchmark_dir.exists():
        raise SystemExit(f"Benchmark directory does not exist: {benchmark_dir}")

    case_dir = _case_dir(experiment, args.split, args.case)
    if not case_dir.exists():
        raise SystemExit(f"Case directory does not exist: {case_dir}")

    if not experiment.workspace_dir.exists():
        raise SystemExit(f"Experiment workspace directory does not exist: {experiment.workspace_dir}")
    if not experiment.config_dir.exists():
        raise SystemExit(f"Experiment config directory does not exist: {experiment.config_dir}")

    task_prompt_source = experiment.workspace_dir / experiment.task_prompt_file
    if not task_prompt_source.exists():
        raise SystemExit(
            f"Experiment task prompt file does not exist in workspace: {task_prompt_source}"
        )

    example_solution = _example_solution_path(experiment)
    if experiment.include_example_solution and example_solution is None:
        raise SystemExit(
            f"Experiment requests an example solution, but none was found for benchmark {experiment.benchmark}"
        )

    verifier = _verifier_path(experiment)
    if experiment.include_verifier and verifier is None:
        raise SystemExit(
            f"Experiment requests a verifier, but no verifier was found for benchmark {experiment.benchmark}"
        )

    return case_dir, example_solution, verifier


def _print_summary(
    experiment: ExperimentManifest,
    runtime: RuntimeManifest,
    adapter,
    case_dir: Path,
    example_solution: Path | None,
    verifier: Path | None,
    args: argparse.Namespace,
) -> None:
    mode = "interactive" if args.interactive else "headless"
    timeout = args.timeout if args.timeout is not None else experiment.timeout_seconds_default

    print("Phase 2 scaffold resolved successfully.")
    print(f"Mode: {mode}")
    print(f"Experiment: {experiment.experiment_dir}")
    print(f"Benchmark: {experiment.benchmark}")
    print(f"Runtime: {runtime.name} ({runtime.image})")
    print(f"Adapter: {adapter.NAME}")
    print(f"Case: {case_dir}")
    print(f"Workspace template: {experiment.workspace_dir}")
    print(f"Config directory: {experiment.config_dir}")
    print(f"Required config files: {', '.join(experiment.required_config_files)}")
    print(f"Python packages: {', '.join(experiment.python_packages)}")
    print(f"Task prompt file: {experiment.workspace_dir / experiment.task_prompt_file}")
    print(f"Example solution: {example_solution if example_solution is not None else 'not requested'}")
    print(f"Verifier: {verifier if verifier is not None else 'not requested'}")
    print(f"Container workspace mount: {WORKSPACE_MOUNT}")
    print(f"Container output mount: {OUTPUT_MOUNT}")
    print(f"Adapter config target: {adapter.CONFIG_TARGET_DIR}")
    print(f"Adapter session log target: {adapter.SESSION_LOG_TARGET_DIR}")
    print(f"Timeout seconds: {timeout if timeout is not None else 'unset'}")
    print("Execution is intentionally deferred to Phase 3.")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    experiment_dir = Path(__file__).resolve().parent
    experiment = load_experiment(experiment_dir)
    runtime = load_runtime(experiment.runtime)
    adapter = load_adapter(experiment)
    case_dir, example_solution, verifier = _check_required_paths(experiment, args)
    _print_summary(experiment, runtime, adapter, case_dir, example_solution, verifier, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
