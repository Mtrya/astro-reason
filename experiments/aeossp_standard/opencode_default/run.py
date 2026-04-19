#!/usr/bin/env python3
"""Run the OpenCode default experiment for one AEOSSP Standard case."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
WORKSPACE_MOUNT = Path("/app/workspace")
OUTPUT_MOUNT = Path("/app/run/output")
CONTAINER_HOME = Path("/tmp/astroreason-home")
CONTAINER_XDG_CONFIG_HOME = Path("/tmp/astroreason-xdg-config")
CONTAINER_XDG_DATA_HOME = Path("/tmp/astroreason-xdg-data")
CONTAINER_USER_NAME = "korolev"
CONTAINER_GROUP_NAME = "korolev"
RESULTS_ROOT = REPO_ROOT / "results" / "agent_runs"
INTERACTIVE_WORKSPACES_ROOT = REPO_ROOT / ".runtime" / "interactive_workspaces"


@dataclass(frozen=True)
class ExperimentManifest:
    name: str
    benchmark: str
    runtime: str
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


@dataclass(frozen=True)
class VerifierOutcome:
    status: str
    result: dict[str, Any]


@dataclass(frozen=True)
class ContainerIdentity:
    username: str
    group_name: str
    passwd_file: Path
    group_file: Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one AstroReason experiment case")
    parser.add_argument("--split", default="test", help="Dataset split (default: test)")
    parser.add_argument("--case", required=True, help="Case ID")
    parser.add_argument(
        "--timeout",
        type=int,
        help="Override the experiment timeout in seconds for headless mode",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prepare the workspace and open an interactive shell instead of running headless",
    )
    return parser.parse_args(argv)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime) -> str:
    return value.isoformat()


def _duration_seconds(start: datetime, end: datetime) -> float:
    return round((end - start).total_seconds(), 3)


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


def _benchmark_dir(experiment: ExperimentManifest) -> Path:
    return _benchmark_root(experiment.benchmark)


def _experiment_relpath(experiment: ExperimentManifest) -> Path:
    return experiment.experiment_dir.relative_to(REPO_ROOT)


def _output_dir(experiment: ExperimentManifest, split: str, case_id: str) -> Path:
    return RESULTS_ROOT / _experiment_relpath(experiment) / split / case_id


def _interactive_workspace_dir(experiment: ExperimentManifest, split: str, case_id: str) -> Path:
    return INTERACTIVE_WORKSPACES_ROOT / _experiment_relpath(experiment) / split / case_id


def _existing_config_files(config_dir: Path) -> list[Path]:
    if not config_dir.exists():
        return []

    files: list[Path] = []
    for path in config_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.name == ".gitignore" or path.name.endswith(".example"):
            continue
        files.append(path)
    return sorted(files)


def _copy_filtered_config(experiment: ExperimentManifest, destination: Path) -> list[str]:
    config_files = _existing_config_files(experiment.config_dir)
    if not config_files:
        raise SystemExit(
            "No real experiment config files were found. Copy the matching .example file and fill it in."
        )

    existing_rel_paths = {
        path.relative_to(experiment.config_dir).as_posix() for path in config_files
    }
    missing = [
        rel_path for rel_path in experiment.required_config_files if rel_path not in existing_rel_paths
    ]
    if missing:
        raise SystemExit(
            "Missing required experiment config file(s): "
            + ", ".join(str(experiment.config_dir / rel_path) for rel_path in missing)
        )

    copied_files: list[str] = []
    for source in config_files:
        rel_path = source.relative_to(experiment.config_dir)
        target = destination / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied_files.append(rel_path.as_posix())
    return copied_files


def _example_solution_path(experiment: ExperimentManifest) -> Path | None:
    dataset_dir = _benchmark_root(experiment.benchmark) / "dataset"
    for candidate in ("example_solution.json", "example_solution.yaml", "example_solution.yml"):
        path = dataset_dir / candidate
        if path.exists():
            return path
    return None


def _verifier_path(experiment: ExperimentManifest) -> Path | None:
    benchmark_dir = _benchmark_dir(experiment)
    verifier_dir = benchmark_dir / "verifier"
    verifier_py = benchmark_dir / "verifier.py"
    if verifier_dir.is_dir():
        return verifier_dir
    if verifier_py.exists():
        return verifier_py
    return None


def _benchmark_has_verifier(experiment: ExperimentManifest) -> bool:
    return _verifier_path(experiment) is not None


def _template_context(
    experiment: ExperimentManifest,
    split: str,
    case_id: str,
    example_solution_name: str,
    verifier_location: str,
    verifier_command: str,
) -> dict[str, str]:
    return {
        "benchmark": experiment.benchmark,
        "case_id": case_id,
        "split": split,
        "example_solution_name": example_solution_name,
        "verifier_location": verifier_location,
        "verifier_command": verifier_command,
    }


def _render_workspace_templates(
    template_dir: Path,
    workspace_dir: Path,
    context: dict[str, str],
) -> None:
    for source in sorted(template_dir.rglob("*")):
        rel_path = source.relative_to(template_dir)
        destination = workspace_dir / rel_path
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue

        rendered = source.read_text(encoding="utf-8").format(**context)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")


def _copy_verifier_into_workspace(
    experiment: ExperimentManifest,
    workspace_dir: Path,
) -> tuple[str, str]:
    benchmark_dir = _benchmark_dir(experiment)
    verifier_py = benchmark_dir / "verifier.py"
    verifier_dir = benchmark_dir / "verifier"
    if verifier_dir.exists():
        shutil.copytree(verifier_dir, workspace_dir / "verifier")
        return "verifier/", "python -m verifier.run case/ solution.json"
    if verifier_py.exists():
        shutil.copy2(verifier_py, workspace_dir / "verifier.py")
        return "verifier.py", "python verifier.py case/ solution.json"
    raise SystemExit(f"No verifier found for benchmark {experiment.benchmark}")


def _prepare_workspace(
    experiment: ExperimentManifest,
    args: argparse.Namespace,
    workspace_dir: Path,
) -> None:
    if workspace_dir.exists():
        shutil.rmtree(workspace_dir)
    workspace_dir.mkdir(parents=True, exist_ok=True)

    shutil.copytree(_case_dir(experiment, args.split, args.case), workspace_dir / "case")

    example_solution_name = "No example solution is provided for this benchmark."
    example_solution = _example_solution_path(experiment)
    if experiment.include_example_solution and example_solution is not None:
        example_solution_name = example_solution.name
        shutil.copy2(example_solution, workspace_dir / example_solution.name)

    verifier_location = "Verifier is not exposed in this experiment."
    verifier_command = "No verifier helper is available in this workspace."
    if experiment.include_verifier:
        verifier_location, verifier_command = _copy_verifier_into_workspace(experiment, workspace_dir)

    _render_workspace_templates(
        experiment.workspace_dir,
        workspace_dir,
        _template_context(
            experiment,
            args.split,
            args.case,
            example_solution_name,
            verifier_location,
            verifier_command,
        ),
    )


def _prepare_session_log_mount(output_dir: Path) -> Path:
    session_logs_dir = output_dir / "session_logs"
    if session_logs_dir.exists():
        shutil.rmtree(session_logs_dir)
    session_logs_dir.mkdir(parents=True, exist_ok=True)
    return session_logs_dir


def _build_container_identity(temp_dir: Path) -> ContainerIdentity:
    uid = os.getuid()
    gid = os.getgid()
    username = CONTAINER_USER_NAME
    group_name = CONTAINER_GROUP_NAME

    passwd_file = temp_dir / "passwd"
    group_file = temp_dir / "group"

    passwd_file.write_text(
        "\n".join(
            [
                "root:x:0:0:root:/root:/bin/bash",
                f"{username}:x:{uid}:{gid}:AstroReason User:{CONTAINER_HOME}:/bin/bash",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    group_file.write_text(
        "\n".join(
            [
                "root:x:0:",
                f"{group_name}:x:{gid}:",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return ContainerIdentity(
        username=username,
        group_name=group_name,
        passwd_file=passwd_file,
        group_file=group_file,
    )


def _build_container_script(
    experiment: ExperimentManifest,
    adapter,
    timeout: int,
    task_prompt: str,
    interactive: bool,
) -> str:
    lines = [
        "set -euo pipefail",
        f"mkdir -p {shlex.quote(str(CONTAINER_HOME))}",
        f"mkdir -p {shlex.quote(str(CONTAINER_XDG_CONFIG_HOME))}",
        f"mkdir -p {shlex.quote(str(CONTAINER_XDG_DATA_HOME))}",
        f"cd {shlex.quote(str(WORKSPACE_MOUNT))}",
    ]

    if interactive:
        lines.append(f"exec {shlex.join(adapter.INTERACTIVE_COMMAND)}")
        return "\n".join(lines)

    agent_command = adapter.build_headless_command(task_prompt)
    lines.append(f"exec timeout --signal=TERM {timeout} {shlex.join(agent_command)}")
    return "\n".join(lines)


def _build_docker_command(
    experiment: ExperimentManifest,
    runtime: RuntimeManifest,
    adapter,
    args: argparse.Namespace,
    workspace_dir: Path,
    config_dir: Path,
    output_dir: Path,
    session_logs_dir: Path,
    container_identity: ContainerIdentity,
    timeout: int,
) -> list[str]:
    cmd = ["docker", "run", "--rm", "-w", str(WORKSPACE_MOUNT)]
    cmd.extend(["--user", f"{os.getuid()}:{os.getgid()}"])
    cmd.extend(["-e", f"HOME={CONTAINER_HOME}"])
    cmd.extend(["-e", f"USER={container_identity.username}"])
    cmd.extend(["-e", f"LOGNAME={container_identity.username}"])
    cmd.extend(["-e", f"XDG_CONFIG_HOME={CONTAINER_XDG_CONFIG_HOME}"])
    cmd.extend(["-e", f"XDG_DATA_HOME={CONTAINER_XDG_DATA_HOME}"])
    if args.interactive:
        cmd.append("-i")
        if sys.stdin.isatty() and sys.stdout.isatty():
            cmd.append("-t")

    cmd.extend(
        [
            "-v",
            f"{workspace_dir.resolve()}:{WORKSPACE_MOUNT}",
            "-v",
            f"{output_dir.resolve()}:{OUTPUT_MOUNT}",
            "-v",
            f"{config_dir.resolve()}:{adapter.CONFIG_TARGET_DIR}",
            "-v",
            f"{session_logs_dir.resolve()}:{adapter.SESSION_LOG_TARGET_DIR}",
            "-v",
            f"{container_identity.passwd_file.resolve()}:/etc/passwd:ro",
            "-v",
            f"{container_identity.group_file.resolve()}:/etc/group:ro",
        ]
    )

    task_prompt = (workspace_dir / experiment.task_prompt_file).read_text(encoding="utf-8")
    shell_script = _build_container_script(
        experiment,
        adapter,
        timeout,
        task_prompt,
        args.interactive,
    )

    cmd.append(runtime.image)
    cmd.extend(["/bin/bash", "-lc", shell_script])
    return cmd


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

    if experiment.include_verifier and not _benchmark_has_verifier(experiment):
        raise SystemExit(f"No verifier found for benchmark {experiment.benchmark}")

    return case_dir, example_solution, _verifier_path(experiment)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _copy_solution_artifact(workspace_dir: Path, output_dir: Path) -> bool:
    solution_src = workspace_dir / "solution.json"
    solution_dst = output_dir / "solution.json"
    if not solution_src.exists():
        return False
    shutil.copy2(solution_src, solution_dst)
    return True


def _run_process(
    cmd: list[str],
    *,
    capture_output: bool,
    cwd: Path | None = None,
) -> tuple[int, str, str, bool]:
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            cwd=cwd,
        )
    except FileNotFoundError as exc:
        return 127, "", f"Failed to launch process: {exc}", False

    if capture_output:
        return result.returncode, result.stdout or "", result.stderr or "", True
    return result.returncode, "", "", True


def _agent_status(agent_exit_code: int, solution_present: bool, launched: bool) -> str:
    if not launched:
        return "runner_error"
    if agent_exit_code == 124:
        return "timeout"
    if agent_exit_code != 0:
        return "agent_failed"
    if not solution_present:
        return "no_solution"
    return "success"


def _verifier_command(experiment: ExperimentManifest, case_dir: Path, solution_path: Path) -> list[str]:
    verifier_path = _verifier_path(experiment)
    if verifier_path is None:
        raise SystemExit(f"No verifier found for benchmark {experiment.benchmark}")

    if verifier_path.is_dir():
        return [
            "uv",
            "run",
            "python",
            "-m",
            f"benchmarks.{experiment.benchmark}.verifier.run",
            str(case_dir),
            str(solution_path),
        ]
    return [
        "uv",
        "run",
        "python",
        str(verifier_path),
        str(case_dir),
        str(solution_path),
    ]


def _run_external_verifier(
    experiment: ExperimentManifest,
    case_dir: Path,
    output_dir: Path,
    *,
    solution_present: bool,
) -> VerifierOutcome:
    if not solution_present:
        return VerifierOutcome(
            status="no_solution",
            result={"present": False, "status": "no_solution"},
        )

    solution_path = output_dir / "solution.json"
    cmd = _verifier_command(experiment, case_dir, solution_path)
    exit_code, stdout, stderr, launched = _run_process(
        cmd,
        capture_output=True,
        cwd=REPO_ROOT,
    )
    if not launched:
        return VerifierOutcome(
            status="error",
            result={"status": "error", "error": stderr.strip() or "Failed to launch verifier."},
        )

    try:
        parsed = json.loads(stdout) if stdout.strip() else {}
    except json.JSONDecodeError as exc:
        return VerifierOutcome(
            status="error",
            result={
                "status": "error",
                "error": f"Verifier output was not valid JSON: {exc}",
                "exit_code": exit_code,
            },
        )

    if not isinstance(parsed, dict):
        return VerifierOutcome(
            status="error",
            result={
                "status": "error",
                "error": "Verifier output JSON must be an object.",
                "exit_code": exit_code,
            },
        )

    if exit_code in (0, 1):
        valid = bool(parsed.get("valid"))
        return VerifierOutcome(
            status="valid" if valid else "invalid",
            result=parsed,
        )

    return VerifierOutcome(
        status="error",
        result={
            "status": "error",
            "exit_code": exit_code,
            "error": stderr.strip() or "Verifier exited unexpectedly.",
        },
    )


def _overall_status(agent_status: str, verifier_status: str, interactive: bool) -> str:
    if interactive:
        if agent_status == "interactive_failed":
            return "interactive_failed"
        if agent_status == "interactive_no_solution":
            return "interactive_no_solution"
        return "interactive_completed"

    if agent_status != "success":
        return agent_status
    if verifier_status == "valid":
        return "success"
    if verifier_status == "invalid":
        return "verifier_invalid"
    return "verifier_error"


def _write_run_metadata(
    experiment: ExperimentManifest,
    runtime: RuntimeManifest,
    adapter,
    args: argparse.Namespace,
    output_dir: Path,
    copied_config_files: list[str],
    start_time: datetime,
    end_time: datetime,
    agent_exit_code: int,
    agent_status: str,
    verifier_outcome: VerifierOutcome,
    *,
    interactive: bool,
) -> None:
    session_log_dir = output_dir / "session_logs"
    artifacts = {
        "solution.json": (output_dir / "solution.json").exists(),
        "agent_stdout.txt": (output_dir / "agent_stdout.txt").exists(),
        "agent_stderr.txt": (output_dir / "agent_stderr.txt").exists(),
        "run.json": True,
        "session_logs": session_log_dir.exists() and any(session_log_dir.iterdir()),
    }
    run_data = {
        "benchmark": experiment.benchmark,
        "experiment": _experiment_relpath(experiment).as_posix(),
        "runtime": runtime.name,
        "case_id": args.case,
        "split": args.split,
        "overall_status": _overall_status(agent_status, verifier_outcome.status, interactive),
        "agent_status": agent_status,
        "verifier_status": verifier_outcome.status,
        "start_time": _isoformat(start_time),
        "end_time": _isoformat(end_time),
        "duration_seconds": _duration_seconds(start_time, end_time),
        "container_image": runtime.image,
        "agent_exit_code": agent_exit_code,
        "artifacts": artifacts,
        "session_logs": {
            "source_path": adapter.SESSION_LOG_TARGET_DIR,
            "copied_path": "session_logs" if artifacts["session_logs"] else None,
        },
        "config_source": {
            "repo_dir": experiment.config_dir.relative_to(REPO_ROOT).as_posix(),
            "copied_files": copied_config_files,
        },
        "verifier": verifier_outcome.result,
    }
    _write_text(output_dir / "run.json", json.dumps(run_data, indent=2, sort_keys=True) + "\n")


def _headless_exit_code(overall_status: str) -> int:
    return 0 if overall_status == "success" else 1


def _print_run_summary(output_dir: Path, overall_status: str) -> None:
    print(f"Results written to {output_dir}")
    print(f"Run status: {overall_status}")


def _run_interactive(
    experiment: ExperimentManifest,
    runtime: RuntimeManifest,
    adapter,
    args: argparse.Namespace,
    case_dir: Path,
    output_dir: Path,
) -> int:
    timeout = args.timeout or experiment.timeout_seconds_default or 1800
    workspace_dir = _interactive_workspace_dir(experiment, args.split, args.case)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Preparing interactive workspace at {workspace_dir}")
    with tempfile.TemporaryDirectory(prefix=f"astroreason-{experiment.name}-config-") as config_tmp:
        config_dir = Path(config_tmp)
        container_identity = _build_container_identity(config_dir)
        copied_config_files = _copy_filtered_config(experiment, config_dir)
        _prepare_workspace(experiment, args, workspace_dir)
        session_logs_dir = _prepare_session_log_mount(output_dir)
        cmd = _build_docker_command(
            experiment,
            runtime,
            adapter,
            args,
            workspace_dir,
            config_dir,
            output_dir,
            session_logs_dir,
            container_identity,
            timeout,
        )
        print(f"Workspace ready at {workspace_dir}")
        print(f"Loaded config files: {', '.join(copied_config_files)}")
        start_time = _utc_now()
        exit_code, _, _, launched = _run_process(cmd, capture_output=False)
        end_time = _utc_now()

        solution_present = _copy_solution_artifact(workspace_dir, output_dir)
        if launched:
            if exit_code != 0:
                agent_status = "interactive_failed"
            elif solution_present:
                agent_status = "interactive_completed"
            else:
                agent_status = "interactive_no_solution"
        else:
            agent_status = "interactive_failed"

        verifier_outcome = VerifierOutcome(
            status="manual",
            result={"status": "manual", "present": solution_present},
        )
        _write_run_metadata(
            experiment,
            runtime,
            adapter,
            args,
            output_dir,
            copied_config_files,
            start_time,
            end_time,
            exit_code,
            agent_status,
            verifier_outcome,
            interactive=True,
        )
        overall_status = _overall_status(agent_status, verifier_outcome.status, True)
        _print_run_summary(output_dir, overall_status)
        return exit_code


def _run_headless(
    experiment: ExperimentManifest,
    runtime: RuntimeManifest,
    adapter,
    args: argparse.Namespace,
    case_dir: Path,
    output_dir: Path,
) -> int:
    timeout = args.timeout or experiment.timeout_seconds_default or 1800
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=f"astroreason-{experiment.name}-workspace-") as workspace_tmp:
        with tempfile.TemporaryDirectory(prefix=f"astroreason-{experiment.name}-config-") as config_tmp:
            workspace_dir = Path(workspace_tmp)
            config_dir = Path(config_tmp)
            container_identity = _build_container_identity(config_dir)
            copied_config_files = _copy_filtered_config(experiment, config_dir)
            _prepare_workspace(experiment, args, workspace_dir)
            session_logs_dir = _prepare_session_log_mount(output_dir)
            cmd = _build_docker_command(
                experiment,
                runtime,
                adapter,
                args,
                workspace_dir,
                config_dir,
                output_dir,
                session_logs_dir,
                container_identity,
                timeout,
            )

            start_time = _utc_now()
            exit_code, stdout, stderr, launched = _run_process(cmd, capture_output=True)
            end_time = _utc_now()

            _write_text(output_dir / "agent_stdout.txt", stdout)
            _write_text(output_dir / "agent_stderr.txt", stderr)
            solution_present = _copy_solution_artifact(workspace_dir, output_dir)
            agent_status = _agent_status(exit_code, solution_present, launched)
            verifier_outcome = _run_external_verifier(
                experiment,
                case_dir,
                output_dir,
                solution_present=solution_present,
            )
            _write_run_metadata(
                experiment,
                runtime,
                adapter,
                args,
                output_dir,
                copied_config_files,
                start_time,
                end_time,
                exit_code,
                agent_status,
                verifier_outcome,
                interactive=False,
            )
            overall_status = _overall_status(agent_status, verifier_outcome.status, False)
            _print_run_summary(output_dir, overall_status)
            return _headless_exit_code(overall_status)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    experiment_dir = Path(__file__).resolve().parent
    experiment = load_experiment(experiment_dir)
    runtime = load_runtime(experiment.runtime)
    adapter = load_adapter(experiment)
    case_dir, _, _ = _check_required_paths(experiment, args)
    output_dir = _output_dir(experiment, args.split, args.case)

    if args.interactive:
        return _run_interactive(experiment, runtime, adapter, args, case_dir, output_dir)
    return _run_headless(experiment, runtime, adapter, args, case_dir, output_dir)


if __name__ == "__main__":
    raise SystemExit(main())
