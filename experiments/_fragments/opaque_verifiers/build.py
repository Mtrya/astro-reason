#!/usr/bin/env python3
"""Build experiment-owned opaque verifier artifacts."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
from typing import Any

import yaml


SCRIPT_PATH = Path(__file__).resolve()
OPAQUE_DIR = SCRIPT_PATH.parent
REPO_ROOT = SCRIPT_PATH.parents[3]
MANIFEST_PATH = OPAQUE_DIR / "manifest.yaml"
RUNTIME_MANIFEST_PATH = REPO_ROOT / "runtimes" / "base" / "runtime.yaml"
CONTAINER_REPO_ROOT = Path("/repo")
SATNET_COMPACT_PATTERN = re.compile(
    r"(VALID|INVALID):\s+(?:total_hours|score)=([+-]?(?:\d+(?:\.\d*)?|\.\d+))h,\s+tracks=(\d+)"
)
SPOT5_COMPACT_PATTERN = re.compile(
    r"(VALID|INVALID):\s+profit=(\d+),\s+weight=(\d+)"
)
STATUS_PATTERN = re.compile(r"^Status:\s+(VALID|INVALID)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class DataPathSpec:
    source: str
    target: str


@dataclass(frozen=True)
class BenchmarkSpec:
    name: str
    entry_type: str
    entry: str
    source_roots: tuple[str, ...]
    artifact: str
    smoke_case: str
    smoke_solution: str
    hidden_imports: tuple[str, ...]
    data_paths: tuple[DataPathSpec, ...]


@dataclass(frozen=True)
class RuntimeSpec:
    image: str
    dockerfile: Path
    build_context: Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build opaque verifier artifacts")
    parser.add_argument(
        "--benchmark",
        action="append",
        dest="benchmarks",
        help="Benchmark name from manifest.yaml; may be repeated",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force rebuild even if the existing artifact appears fresh",
    )
    return parser.parse_args(argv)


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Manifest does not exist: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - surfaced as fatal CLI error
        raise SystemExit(f"Failed to parse manifest {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"Manifest must contain a mapping: {path}")
    return data


def _require_str(mapping: dict[str, Any], key: str, context: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise SystemExit(f"{context}.{key} must be a non-empty string")
    return value


def _require_list_of_str(mapping: dict[str, Any], key: str, context: str) -> tuple[str, ...]:
    value = mapping.get(key)
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise SystemExit(f"{context}.{key} must be a list of non-empty strings")
    return tuple(value)


def _require_data_paths(mapping: dict[str, Any], context: str) -> tuple[DataPathSpec, ...]:
    value = mapping.get("data_paths")
    if value is None:
        return ()
    if not isinstance(value, list):
        raise SystemExit(f"{context}.data_paths must be a list")

    items: list[DataPathSpec] = []
    for index, payload in enumerate(value):
        item_context = f"{context}.data_paths[{index}]"
        if not isinstance(payload, dict):
            raise SystemExit(f"{item_context} must be a mapping")
        items.append(
            DataPathSpec(
                source=_require_str(payload, "source", item_context),
                target=_require_str(payload, "target", item_context),
            )
        )
    return tuple(items)


def load_manifest() -> dict[str, BenchmarkSpec]:
    data = _load_yaml_mapping(MANIFEST_PATH)
    benchmarks_raw = data.get("benchmarks")
    if not isinstance(benchmarks_raw, dict) or not benchmarks_raw:
        raise SystemExit("manifest.yaml must contain a non-empty benchmarks mapping")

    specs: dict[str, BenchmarkSpec] = {}
    for name, payload in benchmarks_raw.items():
        context = f"benchmarks.{name}"
        if not isinstance(payload, dict):
            raise SystemExit(f"{context} must be a mapping")
        entry_type = _require_str(payload, "entry_type", context)
        if entry_type not in {"module", "script"}:
            raise SystemExit(f"{context}.entry_type must be 'module' or 'script'")
        specs[name] = BenchmarkSpec(
            name=name,
            entry_type=entry_type,
            entry=_require_str(payload, "entry", context),
            source_roots=_require_list_of_str(payload, "source_roots", context),
            artifact=_require_str(payload, "artifact", context),
            smoke_case=_require_str(payload, "smoke_case", context),
            smoke_solution=_require_str(payload, "smoke_solution", context),
            hidden_imports=_require_list_of_str(payload, "hidden_imports", context),
            data_paths=_require_data_paths(payload, context),
        )
        if not specs[name].source_roots:
            raise SystemExit(f"{context}.source_roots must not be empty")
    return specs


def load_runtime() -> RuntimeSpec:
    data = _load_yaml_mapping(RUNTIME_MANIFEST_PATH)
    image = _require_str(data, "image", "runtime")
    dockerfile = REPO_ROOT / "runtimes" / "base" / _require_str(data, "dockerfile", "runtime")
    build_context = REPO_ROOT / "runtimes" / "base" / _require_str(
        data, "build_context", "runtime"
    )
    return RuntimeSpec(
        image=image,
        dockerfile=dockerfile.resolve(),
        build_context=build_context.resolve(),
    )


def resolve_repo_path(relative_path: str) -> Path:
    path = (REPO_ROOT / relative_path).resolve()
    if not path.exists():
        raise SystemExit(f"Path from manifest does not exist: {relative_path}")
    return path


def resolve_artifact_path(spec: BenchmarkSpec) -> Path:
    artifact = (REPO_ROOT / spec.artifact).resolve()
    artifact.parent.mkdir(parents=True, exist_ok=True)
    return artifact


def build_json_path(spec: BenchmarkSpec) -> Path:
    return resolve_artifact_path(spec).parent / "build.json"


def iter_source_files(spec: BenchmarkSpec) -> list[Path]:
    files: list[Path] = []
    for root_text in spec.source_roots:
        root = resolve_repo_path(root_text)
        if root.is_dir():
            for path in sorted(root.rglob("*")):
                if not path.is_file():
                    continue
                if "__pycache__" in path.parts:
                    continue
                files.append(path)
        elif root.is_file():
            files.append(root)
        else:
            raise SystemExit(f"Unsupported source root: {root}")
    return sorted(set(files))


def manifest_entry_payload(spec: BenchmarkSpec) -> dict[str, Any]:
    return {
        "entry_type": spec.entry_type,
        "entry": spec.entry,
        "source_roots": list(spec.source_roots),
        "artifact": spec.artifact,
        "smoke_case": spec.smoke_case,
        "smoke_solution": spec.smoke_solution,
        "hidden_imports": list(spec.hidden_imports),
        "data_paths": [{"source": item.source, "target": item.target} for item in spec.data_paths],
    }


def compute_input_hash(spec: BenchmarkSpec) -> str:
    blob = hashlib.sha256()
    blob.update(json.dumps(manifest_entry_payload(spec), sort_keys=True).encode("utf-8"))
    blob.update(b"\0")
    blob.update(SCRIPT_PATH.read_bytes())
    blob.update(b"\0")
    for path in iter_source_files(spec):
        blob.update(path.relative_to(REPO_ROOT).as_posix().encode("utf-8"))
        blob.update(b"\0")
        blob.update(path.read_bytes())
        blob.update(b"\0")
    return blob.hexdigest()


def _truncate_output(text: str, limit: int = 2000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]..."


def _status_valid(stdout: str) -> bool | None:
    match = STATUS_PATTERN.search(stdout)
    if match is None:
        return None
    return match.group(1) == "VALID"


def _plain_cli_valid(spec: BenchmarkSpec, stdout: str) -> bool | None:
    if spec.name == "satnet":
        valid = _status_valid(stdout)
        if valid is not None:
            return valid
        match = SATNET_COMPACT_PATTERN.search(stdout)
        if match is not None:
            return match.group(1) == "VALID"
        return None

    if spec.name == "spot5":
        valid = _status_valid(stdout)
        if valid is not None:
            return valid
        match = SPOT5_COMPACT_PATTERN.search(stdout)
        if match is not None:
            return match.group(1) == "VALID"
        return None

    return None


def _container_path(host_path: Path) -> str:
    return (CONTAINER_REPO_ROOT / host_path.resolve().relative_to(REPO_ROOT)).as_posix()


def _docker_run(
    runtime: RuntimeSpec,
    command: list[str],
    *,
    workdir: str = "/repo",
) -> subprocess.CompletedProcess[str]:
    user_args: list[str] = []
    if hasattr(os, "getuid") and hasattr(os, "getgid"):
        user_args = ["--user", f"{os.getuid()}:{os.getgid()}"]
    try:
        return subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                *user_args,
                "-v",
                f"{REPO_ROOT}:/repo",
                "-w",
                workdir,
                "-e",
                "HOME=/tmp",
                "-e",
                "XDG_CACHE_HOME=/tmp/xdg-cache",
                "-e",
                "MPLCONFIGDIR=/tmp/mplconfig",
                runtime.image,
                *command,
            ],
            check=False,
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
    except FileNotFoundError as exc:
        raise SystemExit("Docker is required to build opaque verifier artifacts.") from exc


def _docker_image_inspect(runtime: RuntimeSpec) -> str:
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", runtime.image, "--format", "{{.Id}}"],
            check=False,
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
    except FileNotFoundError as exc:
        raise SystemExit("Docker is required to build opaque verifier artifacts.") from exc
    if result.returncode != 0:
        build_command = (
            f"uv run python {RUNTIME_MANIFEST_PATH.relative_to(REPO_ROOT).parent.as_posix()}/build.py"
        )
        raise SystemExit(
            f"Runtime image is not available: {runtime.image}\n"
            f"Build it first with: {build_command}\n"
            f"stderr:\n{_truncate_output(result.stderr)}"
        )
    return result.stdout.strip()


def container_environment_stamp(runtime: RuntimeSpec) -> dict[str, str]:
    image_id = _docker_image_inspect(runtime)
    payload = (
        "import json, platform, sys; "
        "print(json.dumps({"
        "'platform': platform.system().lower(), "
        "'machine': platform.machine().lower(), "
        "'python_major_minor': f'{sys.version_info.major}.{sys.version_info.minor}', "
        "'python_version': platform.python_version()"
        "}, sort_keys=True))"
    )
    result = _docker_run(runtime, ["python", "-c", payload])
    if result.returncode != 0:
        raise SystemExit(
            f"Failed to query runtime environment from {runtime.image}.\n"
            f"stdout:\n{_truncate_output(result.stdout)}\n"
            f"stderr:\n{_truncate_output(result.stderr)}"
        )
    try:
        stamp = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"Runtime environment query emitted malformed JSON: {result.stdout}"
        ) from exc
    if not isinstance(stamp, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in stamp.items()):
        raise SystemExit(f"Runtime environment query emitted unexpected payload: {result.stdout}")
    stamp["runtime_image"] = runtime.image
    stamp["runtime_image_id"] = image_id
    return stamp


def smoke_check(spec: BenchmarkSpec, artifact_path: Path, runtime: RuntimeSpec) -> dict[str, Any]:
    case_path = resolve_repo_path(spec.smoke_case)
    solution_path = resolve_repo_path(spec.smoke_solution)
    result = _docker_run(
        runtime,
        [
            _container_path(artifact_path),
            _container_path(case_path),
            _container_path(solution_path),
        ],
    )
    stdout = result.stdout.strip()
    try:
        parsed = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError:
        parsed = None

    valid = False
    if isinstance(parsed, dict):
        valid = parsed.get("valid") is True or parsed.get("is_valid") is True
    else:
        plain_valid = _plain_cli_valid(spec, stdout)
        if plain_valid is not None:
            valid = plain_valid
    passed = result.returncode == 0 and valid
    return {
        "passed": passed,
        "exit_code": result.returncode,
        "stdout": stdout,
        "stderr": result.stderr.strip(),
        "parsed": parsed if isinstance(parsed, dict) else None,
        "case": spec.smoke_case,
        "solution": spec.smoke_solution,
    }


def load_existing_build_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def freshness_reason(
    spec: BenchmarkSpec,
    input_hash: str,
    runtime_stamp: dict[str, str],
    runtime: RuntimeSpec,
) -> str | None:
    artifact_path = resolve_artifact_path(spec)
    metadata_path = build_json_path(spec)
    metadata = load_existing_build_json(metadata_path)
    if not artifact_path.exists():
        return "artifact missing"
    if metadata is None:
        return "build.json missing or malformed"
    if not os.access(artifact_path, os.X_OK):
        return "artifact is not executable"
    if metadata.get("input_hash") != input_hash:
        return "input hash changed"
    if metadata.get("build_target") != "runtime_docker_image":
        return "build target changed"

    for key, value in runtime_stamp.items():
        if metadata.get(key) != value:
            return f"environment changed: {key}"

    smoke = smoke_check(spec, artifact_path, runtime)
    if not smoke["passed"]:
        return "smoke check failed"
    return None


def pyinstaller_version(runtime: RuntimeSpec) -> str:
    result = _docker_run(runtime, ["python", "-m", "PyInstaller", "--version"])
    if result.returncode != 0:
        raise SystemExit(
            f"Failed to query PyInstaller version from {runtime.image}.\n"
            f"stdout:\n{_truncate_output(result.stdout)}\n"
            f"stderr:\n{_truncate_output(result.stderr)}"
        )
    return result.stdout.strip()


def build_artifact(
    spec: BenchmarkSpec,
    input_hash: str,
    runtime_stamp: dict[str, str],
    runtime: RuntimeSpec,
) -> dict[str, Any]:
    artifact_path = resolve_artifact_path(spec)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifacts_root = OPAQUE_DIR / "artifacts"
    artifacts_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=f"build-{spec.name}-", dir=artifacts_root) as temp_root_text:
        temp_root = Path(temp_root_text)
        entry_path = resolve_repo_path(spec.entry) if spec.entry_type == "script" else temp_root / "entry.py"
        if spec.entry_type == "module":
            entry_path.write_text(
                f"from {spec.entry} import main\nraise SystemExit(main())\n",
                encoding="utf-8",
            )

        dist_dir = temp_root / "dist"
        work_dir = temp_root / "build"
        spec_dir = temp_root / "spec"

        cmd = [
            "python",
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--name",
            "verifier",
            "--distpath",
            _container_path(dist_dir),
            "--workpath",
            _container_path(work_dir),
            "--specpath",
            _container_path(spec_dir),
            "--paths",
            "/repo",
        ]
        for hidden_import in spec.hidden_imports:
            cmd.extend(["--hidden-import", hidden_import])
        for data_path in spec.data_paths:
            source = resolve_repo_path(data_path.source)
            cmd.extend(["--add-data", f"{_container_path(source)}:{data_path.target}"])
        cmd.append(_container_path(entry_path))

        result = _docker_run(runtime, cmd)
        if result.returncode != 0:
            raise SystemExit(
                f"PyInstaller build failed for {spec.name} in {runtime.image}.\n"
                f"stdout:\n{_truncate_output(result.stdout)}\n"
                f"stderr:\n{_truncate_output(result.stderr)}"
            )

        built_artifact = dist_dir / "verifier"
        if not built_artifact.exists():
            raise SystemExit(f"PyInstaller did not produce the expected artifact: {built_artifact}")

        shutil.move(str(built_artifact), artifact_path)
        artifact_path.chmod(artifact_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    smoke = smoke_check(spec, artifact_path, runtime)
    smoke_valid = False
    smoke_metrics = None
    if smoke["parsed"]:
        smoke_valid = smoke["parsed"].get("valid") is True or smoke["parsed"].get("is_valid") is True
        smoke_metrics = smoke["parsed"].get("metrics")
    metadata = {
        "benchmark": spec.name,
        "artifact_path": artifact_path.relative_to(REPO_ROOT).as_posix(),
        "build_target": "runtime_docker_image",
        "entry_type": spec.entry_type,
        "entry": spec.entry,
        "source_roots": list(spec.source_roots),
        "input_hash": input_hash,
        **runtime_stamp,
        "pyinstaller_version": pyinstaller_version(runtime),
        "built_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "build_command": [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{REPO_ROOT}:/repo",
            runtime.image,
            "python",
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--name",
            "verifier",
        ],
        "smoke_case": spec.smoke_case,
        "smoke_solution": spec.smoke_solution,
        "smoke_exit_code": smoke["exit_code"],
        "smoke_passed": smoke["passed"],
        "smoke_valid": smoke_valid,
        "smoke_metrics": smoke_metrics,
    }

    build_json_path(spec).write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if not smoke["passed"]:
        raise SystemExit(
            f"Smoke check failed for {spec.name}.\n"
            f"stdout:\n{_truncate_output(smoke['stdout'])}\n"
            f"stderr:\n{_truncate_output(smoke['stderr'])}"
        )
    return metadata


def selected_specs(specs: dict[str, BenchmarkSpec], names: list[str] | None) -> list[BenchmarkSpec]:
    if not names:
        return [specs[name] for name in sorted(specs)]
    missing = [name for name in names if name not in specs]
    if missing:
        raise SystemExit(f"Unknown benchmark(s): {', '.join(sorted(missing))}")
    ordered_unique_names = list(dict.fromkeys(names))
    return [specs[name] for name in ordered_unique_names]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    specs = load_manifest()
    runtime = load_runtime()
    runtime_stamp = container_environment_stamp(runtime)
    targets = selected_specs(specs, args.benchmarks)

    for spec in targets:
        input_hash = compute_input_hash(spec)
        stale_reason = (
            "forced rebuild"
            if args.force
            else freshness_reason(spec, input_hash, runtime_stamp, runtime)
        )
        if stale_reason is None:
            print(f"[reuse] {spec.name}: artifact is fresh and container smoke check passed")
            continue

        print(f"[build] {spec.name}: {stale_reason}")
        metadata = build_artifact(spec, input_hash, runtime_stamp, runtime)
        print(
            f"[built] {spec.name}: {metadata['artifact_path']} "
            f"(smoke_case={metadata['smoke_case']}, smoke_passed={metadata['smoke_passed']})"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
