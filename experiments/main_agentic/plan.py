#!/usr/bin/env python3
"""Plan concrete runs for the main agentic experiment family."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
FAMILY_DIR = Path(__file__).resolve().parent
DEFAULT_BATCH_CONFIG = FAMILY_DIR / "configs" / "matrix.yaml"
DEFAULT_INTERACTIVE_CONFIG = FAMILY_DIR / "configs" / "interactive.yaml"
SHARED_AGENTS_FRAGMENT = (
    REPO_ROOT / "experiments" / "_fragments" / "prompts" / "_shared" / "AGENTS.main_agentic.default.md"
)
INTERACTIVE_WORKSPACES_ROOT = REPO_ROOT / ".runtime" / "interactive_workspaces"


@dataclass(frozen=True)
class LogicalPath:
    root: str
    relative: Path


@dataclass(frozen=True)
class AssembleTemplate:
    source_template: str
    target_template: str
    render: bool
    missing_ok: bool
    example_template: str | None


@dataclass(frozen=True)
class AssembleSpec:
    source: Path
    target: LogicalPath
    render: bool
    missing_ok: bool
    example: Path | None


@dataclass(frozen=True)
class CollectSpec:
    source: LogicalPath
    target: Path
    missing_ok: bool


@dataclass(frozen=True)
class ResourceLimits:
    cpus: str | None
    memory: str | None
    shm_size: str | None


@dataclass(frozen=True)
class BatchSettings:
    batch_size: int
    max_concurrency: int
    max_retries: int
    skip_completed: bool
    retry_statuses: tuple[str, ...]


@dataclass(frozen=True)
class ResultSettings:
    root: Path
    aggregate_dir: Path


@dataclass(frozen=True)
class BatchConfig:
    name: str
    mode: str
    benchmarks: tuple[str, ...]
    harnesses: tuple[str, ...]
    split: str
    timeout_seconds: int
    batch: BatchSettings
    resources: ResourceLimits
    results: ResultSettings
    config_path: Path


@dataclass(frozen=True)
class InteractiveConfig:
    name: str
    mode: str
    benchmark: str
    harnesses: tuple[str, ...]
    split: str
    case_id: str
    timeout_seconds: int
    resources: ResourceLimits
    config_path: Path


@dataclass(frozen=True)
class BenchmarkProfile:
    benchmark: str
    readme_fragment: Path
    prompt_fragment: Path
    assemble: tuple[AssembleTemplate, ...]
    verifier_kind: str
    profile_path: Path


@dataclass(frozen=True)
class HarnessProfile:
    harness: str
    runtime: str
    config_target: LogicalPath
    real_file: Path
    example_file: Path | None
    headless_shell_command: str
    interactive_command: tuple[str, ...]
    collect: tuple[CollectSpec, ...]
    profile_path: Path


@dataclass(frozen=True)
class RuntimeManifest:
    name: str
    image: str
    dockerfile: Path
    build_context: Path
    runtime_dir: Path


@dataclass(frozen=True)
class RunItem:
    config_name: str
    config_path: Path
    benchmark: str
    harness: str
    split: str
    case_id: str
    timeout_seconds: int
    resources: ResourceLimits
    results_root: Path
    benchmark_profile: BenchmarkProfile
    harness_profile: HarnessProfile


@dataclass(frozen=True)
class BatchPlan:
    config: BatchConfig
    selected_benchmarks: tuple[str, ...]
    selected_harnesses: tuple[str, ...]
    items: tuple[RunItem, ...]
    unavailable_configs: tuple[tuple[str, Path], ...]


@dataclass(frozen=True)
class InteractivePlan:
    config: InteractiveConfig
    benchmark_profile: BenchmarkProfile
    harnesses: tuple[HarnessProfile, ...]
    runtime_name: str
    interactive_identity: str
    results_root: Path
    unavailable_configs: tuple[tuple[str, Path], ...]


def family_relpath() -> Path:
    return FAMILY_DIR.relative_to(REPO_ROOT)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan the main agentic benchmark x harness matrix"
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Override the family config path. Defaults to matrix.yaml or interactive.yaml.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Use interactive defaults instead of the batch matrix defaults.",
    )
    parser.add_argument(
        "--benchmark",
        action="append",
        default=[],
        help="Limit planning to a benchmark name. May be repeated.",
    )
    parser.add_argument(
        "--harness",
        action="append",
        default=[],
        help="Limit planning to a harness name. May be repeated.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Accepted for compatibility; planning is always dry-run only.",
    )
    return parser.parse_args(argv)


def _load_yaml_mapping(path: Path, kind: str) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"{kind} file does not exist: {path}")

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"Failed to parse {kind} file {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise SystemExit(f"{kind} file must contain a mapping: {path}")
    return data


def _require_str(data: dict[str, Any], key: str, kind: str, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise SystemExit(f"{kind} field '{key}' must be a non-empty string: {path}")
    return value


def _optional_bool(data: dict[str, Any], key: str, default: bool, kind: str, path: Path) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise SystemExit(f"{kind} field '{key}' must be a boolean: {path}")
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
        raise SystemExit(f"{kind} field '{key}' must be an integer: {path}")
    return value


def _optional_string(
    data: dict[str, Any],
    key: str,
    default: str | None,
    kind: str,
    path: Path,
) -> str | None:
    value = data.get(key, default)
    if value is None:
        return None
    if not isinstance(value, (str, int, float)) or value == "":
        raise SystemExit(f"{kind} field '{key}' must be a non-empty string or number: {path}")
    return str(value)


def _string_tuple(data: dict[str, Any], key: str, kind: str, path: Path) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise SystemExit(f"{kind} field '{key}' must be a list of strings: {path}")
    return tuple(value)


def _resolve_repo_path(path_value: str) -> Path:
    candidate = Path(path_value)
    if candidate.is_absolute():
        return candidate.resolve()
    return (REPO_ROOT / candidate).resolve()


def _parse_logical_path(path_value: str, *, label: str, path: Path) -> LogicalPath:
    pure = PurePosixPath(path_value)
    if pure.is_absolute():
        raise SystemExit(f"{label} must use a logical root, not an absolute path: {path}")
    if not pure.parts:
        raise SystemExit(f"{label} must be non-empty: {path}")

    root = pure.parts[0]
    if root not in {"workspace", "xdg_config", "xdg_data", "home", "output"}:
        raise SystemExit(
            f"{label} must start with one of workspace/, xdg_config/, xdg_data/, home/, output/: {path}"
        )
    relative = Path(*pure.parts[1:]) if len(pure.parts) > 1 else Path()
    return LogicalPath(root=root, relative=relative)


def _load_resource_limits(data: dict[str, Any], config_path: Path) -> ResourceLimits:
    resources = data.get("resources", {})
    if not isinstance(resources, dict):
        raise SystemExit(f"Config field 'resources' must be a mapping: {config_path}")
    return ResourceLimits(
        cpus=_optional_string(resources, "cpus", None, "Resources", config_path),
        memory=_optional_string(resources, "memory", None, "Resources", config_path),
        shm_size=_optional_string(resources, "shm_size", None, "Resources", config_path),
    )


def _parse_collect_specs(items: Any, config_path: Path) -> tuple[CollectSpec, ...]:
    if not isinstance(items, list):
        raise SystemExit(f"Collect field must be a list: {config_path}")

    specs: list[CollectSpec] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise SystemExit(f"Collect spec #{index} must be a mapping: {config_path}")
        source_value = _require_str(item, "source", "Collect spec", config_path)
        target_value = _require_str(item, "target", "Collect spec", config_path)
        target = Path(PurePosixPath(target_value))
        if target.is_absolute():
            raise SystemExit(f"Collect spec #{index} target must be relative: {config_path}")
        specs.append(
            CollectSpec(
                source=_parse_logical_path(
                    source_value,
                    label=f"Collect spec #{index} source",
                    path=config_path,
                ),
                target=target,
                missing_ok=_optional_bool(item, "missing_ok", True, "Collect spec", config_path),
            )
        )
    return tuple(specs)


def _parse_assemble_templates(items: Any, config_path: Path) -> tuple[AssembleTemplate, ...]:
    if not isinstance(items, list) or not items:
        raise SystemExit(f"Assemble field must be a non-empty list: {config_path}")

    specs: list[AssembleTemplate] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise SystemExit(f"Assemble spec #{index} must be a mapping: {config_path}")
        example_value = item.get("example")
        if example_value is not None and (not isinstance(example_value, str) or not example_value):
            raise SystemExit(
                f"Assemble spec #{index} field 'example' must be a non-empty string when present: {config_path}"
            )
        specs.append(
            AssembleTemplate(
                source_template=_require_str(item, "source", "Assemble spec", config_path),
                target_template=_require_str(item, "target", "Assemble spec", config_path),
                render=_optional_bool(item, "render", False, "Assemble spec", config_path),
                missing_ok=_optional_bool(item, "missing_ok", False, "Assemble spec", config_path),
                example_template=example_value,
            )
        )
    return tuple(specs)


def load_batch_config(config_path: Path) -> BatchConfig:
    data = _load_yaml_mapping(config_path, "Family config")
    mode = _require_str(data, "mode", "Family config", config_path)
    if mode != "batch":
        raise SystemExit(f"Expected a batch family config, found mode '{mode}': {config_path}")

    benchmarks = tuple(_string_tuple(data, "benchmarks", "Family config", config_path))
    harnesses = tuple(_string_tuple(data, "harnesses", "Family config", config_path))
    defaults = data.get("defaults")
    if not isinstance(defaults, dict):
        raise SystemExit(f"Family config field 'defaults' must be a mapping: {config_path}")
    batch = data.get("batch")
    if not isinstance(batch, dict):
        raise SystemExit(f"Family config field 'batch' must be a mapping: {config_path}")
    results = data.get("results")
    if not isinstance(results, dict):
        raise SystemExit(f"Family config field 'results' must be a mapping: {config_path}")

    batch_size = _optional_int(batch, "batch_size", None, "Batch config", config_path)
    max_concurrency = _optional_int(batch, "max_concurrency", None, "Batch config", config_path)
    max_retries = _optional_int(batch, "max_retries", None, "Batch config", config_path)
    if batch_size is None or batch_size <= 0:
        raise SystemExit(f"Batch config field 'batch_size' must be a positive integer: {config_path}")
    if max_concurrency is None or max_concurrency <= 0:
        raise SystemExit(
            f"Batch config field 'max_concurrency' must be a positive integer: {config_path}"
        )
    if max_retries is None or max_retries < 0:
        raise SystemExit(
            f"Batch config field 'max_retries' must be a non-negative integer: {config_path}"
        )

    retry_statuses_value = batch.get("retry_statuses")
    if not isinstance(retry_statuses_value, list) or not all(
        isinstance(item, str) and item for item in retry_statuses_value
    ):
        raise SystemExit(
            f"Batch config field 'retry_statuses' must be a list of non-empty strings: {config_path}"
        )

    return BatchConfig(
        name=_require_str(data, "name", "Family config", config_path),
        mode=mode,
        benchmarks=benchmarks,
        harnesses=harnesses,
        split=_require_str(defaults, "split", "Family defaults", config_path),
        timeout_seconds=_optional_int(
            defaults, "timeout_seconds", None, "Family defaults", config_path
        )
        or 3600,
        batch=BatchSettings(
            batch_size=batch_size,
            max_concurrency=max_concurrency,
            max_retries=max_retries,
            skip_completed=_optional_bool(
                batch, "skip_completed", True, "Batch config", config_path
            ),
            retry_statuses=tuple(retry_statuses_value),
        ),
        resources=_load_resource_limits(data, config_path),
        results=ResultSettings(
            root=_resolve_repo_path(_require_str(results, "root", "Results config", config_path)),
            aggregate_dir=Path(
                _require_str(results, "aggregate_dir", "Results config", config_path)
            ),
        ),
        config_path=config_path.resolve(),
    )


def load_interactive_config(config_path: Path) -> InteractiveConfig:
    data = _load_yaml_mapping(config_path, "Family config")
    mode = _require_str(data, "mode", "Family config", config_path)
    if mode != "interactive":
        raise SystemExit(f"Expected an interactive family config, found mode '{mode}': {config_path}")

    return InteractiveConfig(
        name=_require_str(data, "name", "Family config", config_path),
        mode=mode,
        benchmark=_require_str(data, "benchmark", "Family config", config_path),
        harnesses=_string_tuple(data, "harnesses", "Family config", config_path),
        split=_require_str(data, "split", "Family config", config_path),
        case_id=_require_str(data, "case", "Family config", config_path),
        timeout_seconds=_optional_int(
            data, "timeout_seconds", None, "Family config", config_path
        )
        or 3600,
        resources=_load_resource_limits(data, config_path),
        config_path=config_path.resolve(),
    )


def load_benchmark_profile(name: str) -> BenchmarkProfile:
    profile_path = FAMILY_DIR / "benchmarks" / f"{name}.yaml"
    data = _load_yaml_mapping(profile_path, "Benchmark profile")
    benchmark = _require_str(data, "benchmark", "Benchmark profile", profile_path)
    if benchmark != name:
        raise SystemExit(
            f"Benchmark profile name mismatch: expected '{name}', found '{benchmark}' in {profile_path}"
        )

    prompts = data.get("prompts")
    if not isinstance(prompts, dict):
        raise SystemExit(f"Benchmark profile field 'prompts' must be a mapping: {profile_path}")
    workspace = data.get("workspace")
    if not isinstance(workspace, dict):
        raise SystemExit(f"Benchmark profile field 'workspace' must be a mapping: {profile_path}")
    aggregation = data.get("aggregation")
    if not isinstance(aggregation, dict):
        raise SystemExit(f"Benchmark profile field 'aggregation' must be a mapping: {profile_path}")

    readme_fragment = _resolve_repo_path(
        _require_str(prompts, "readme", "Benchmark prompts", profile_path)
    )
    prompt_fragment = _resolve_repo_path(
        _require_str(prompts, "prompt", "Benchmark prompts", profile_path)
    )
    if not readme_fragment.exists():
        raise SystemExit(f"Benchmark README fragment does not exist: {readme_fragment}")
    if not prompt_fragment.exists():
        raise SystemExit(f"Benchmark PROMPT fragment does not exist: {prompt_fragment}")

    return BenchmarkProfile(
        benchmark=benchmark,
        readme_fragment=readme_fragment,
        prompt_fragment=prompt_fragment,
        assemble=_parse_assemble_templates(workspace.get("assemble"), profile_path),
        verifier_kind=_require_str(aggregation, "verifier_kind", "Aggregation config", profile_path),
        profile_path=profile_path.resolve(),
    )


def load_harness_profile(name: str) -> HarnessProfile:
    profile_path = FAMILY_DIR / "harnesses" / f"{name}.yaml"
    data = _load_yaml_mapping(profile_path, "Harness profile")
    harness = _require_str(data, "harness", "Harness profile", profile_path)
    if harness != name:
        raise SystemExit(
            f"Harness profile name mismatch: expected '{name}', found '{harness}' in {profile_path}"
        )

    config = data.get("config")
    if not isinstance(config, dict):
        raise SystemExit(f"Harness profile field 'config' must be a mapping: {profile_path}")
    commands = data.get("commands")
    if not isinstance(commands, dict):
        raise SystemExit(f"Harness profile field 'commands' must be a mapping: {profile_path}")
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, dict):
        raise SystemExit(f"Harness profile field 'artifacts' must be a mapping: {profile_path}")

    real_file = _resolve_repo_path(_require_str(config, "real_file", "Harness config", profile_path))
    example_value = config.get("example_file")
    if example_value is not None and (not isinstance(example_value, str) or not example_value):
        raise SystemExit(
            f"Harness config field 'example_file' must be a non-empty string when present: {profile_path}"
        )
    example_file = _resolve_repo_path(example_value) if isinstance(example_value, str) else None
    if example_file is not None and not example_file.exists():
        raise SystemExit(f"Harness example config does not exist: {example_file}")

    return HarnessProfile(
        harness=harness,
        runtime=_require_str(data, "runtime", "Harness profile", profile_path),
        config_target=_parse_logical_path(
            _require_str(config, "target", "Harness config", profile_path),
            label="Harness config target",
            path=profile_path,
        ),
        real_file=real_file,
        example_file=example_file,
        headless_shell_command=_require_str(
            commands, "headless_shell_command", "Harness commands", profile_path
        ),
        interactive_command=_string_tuple(
            commands, "interactive_command", "Harness commands", profile_path
        ),
        collect=_parse_collect_specs(artifacts.get("collect", []), profile_path),
        profile_path=profile_path.resolve(),
    )


def load_runtime(name: str) -> RuntimeManifest:
    manifest_path = REPO_ROOT / "runtimes" / name / "runtime.yaml"
    data = _load_yaml_mapping(manifest_path, "Runtime manifest")
    runtime_name = _require_str(data, "name", "Runtime manifest", manifest_path)
    if runtime_name != name:
        raise SystemExit(
            f"Runtime manifest name mismatch: expected '{name}', found '{runtime_name}' in {manifest_path}"
        )

    runtime_dir = manifest_path.parent
    dockerfile = runtime_dir / _require_str(data, "dockerfile", "Runtime manifest", manifest_path)
    build_context = runtime_dir / _require_str(
        data, "build_context", "Runtime manifest", manifest_path
    )
    if not dockerfile.exists():
        raise SystemExit(f"Runtime dockerfile does not exist: {dockerfile}")
    if not build_context.exists():
        raise SystemExit(f"Runtime build context does not exist: {build_context}")

    return RuntimeManifest(
        name=runtime_name,
        image=_require_str(data, "image", "Runtime manifest", manifest_path),
        dockerfile=dockerfile.resolve(),
        build_context=build_context.resolve(),
        runtime_dir=runtime_dir.resolve(),
    )


def format_template_string(
    template: str,
    replacements: dict[str, str],
    *,
    label: str,
    path: Path,
) -> str:
    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace(f"{{{key}}}", value)

    if "{" in rendered or "}" in rendered:
        raise SystemExit(f"{label} contains unresolved placeholders in {path}: {template}")
    return rendered


def materialize_assemble_templates(
    templates: tuple[AssembleTemplate, ...],
    replacements: dict[str, str],
    *,
    owner_path: Path,
) -> tuple[AssembleSpec, ...]:
    specs: list[AssembleSpec] = []
    for index, template in enumerate(templates):
        source_value = format_template_string(
            template.source_template,
            replacements,
            label=f"Assemble spec #{index} source",
            path=owner_path,
        )
        target_value = format_template_string(
            template.target_template,
            replacements,
            label=f"Assemble spec #{index} target",
            path=owner_path,
        )
        example_value = (
            format_template_string(
                template.example_template,
                replacements,
                label=f"Assemble spec #{index} example",
                path=owner_path,
            )
            if template.example_template is not None
            else None
        )
        specs.append(
            AssembleSpec(
                source=_resolve_repo_path(source_value),
                target=_parse_logical_path(
                    target_value,
                    label=f"Assemble spec #{index} target",
                    path=owner_path,
                ),
                render=template.render,
                missing_ok=template.missing_ok,
                example=_resolve_repo_path(example_value) if example_value is not None else None,
            )
        )
    return tuple(specs)


def _select_names(
    configured: tuple[str, ...],
    requested: tuple[str, ...],
    *,
    label: str,
) -> tuple[str, ...]:
    if not requested:
        return configured

    unknown = [name for name in requested if name not in configured]
    if unknown:
        available = ", ".join(configured)
        unknown_text = ", ".join(unknown)
        raise SystemExit(f"Unknown {label}(s): {unknown_text}. Available {label}s: {available}")

    seen: set[str] = set()
    selected: list[str] = []
    requested_set = set(requested)
    for name in configured:
        if name in requested_set and name not in seen:
            selected.append(name)
            seen.add(name)
    return tuple(selected)


def _enumerate_case_ids(benchmark: str, split: str) -> tuple[str, ...]:
    cases_dir = REPO_ROOT / "benchmarks" / benchmark / "dataset" / "cases" / split
    if not cases_dir.is_dir():
        raise SystemExit(f"Case directory does not exist: {cases_dir}")
    case_ids = sorted(path.name for path in cases_dir.iterdir() if path.is_dir())
    if not case_ids:
        raise SystemExit(f"No cases found under {cases_dir}")
    return tuple(case_ids)


def _collect_missing_configs(harnesses: tuple[HarnessProfile, ...]) -> tuple[tuple[str, Path], ...]:
    missing: list[tuple[str, Path]] = []
    for harness in harnesses:
        if not harness.real_file.exists():
            missing.append((harness.harness, harness.real_file))
    return tuple(missing)


def build_batch_plan(
    *,
    config_path: Path,
    benchmark_filters: tuple[str, ...] = (),
    harness_filters: tuple[str, ...] = (),
    require_real_configs: bool = False,
) -> BatchPlan:
    config = load_batch_config(config_path.resolve())
    selected_benchmarks = _select_names(
        config.benchmarks,
        benchmark_filters,
        label="benchmark",
    )
    selected_harnesses = _select_names(
        config.harnesses,
        harness_filters,
        label="harness",
    )
    if not selected_benchmarks:
        raise SystemExit("No benchmarks selected for planning.")
    if not selected_harnesses:
        raise SystemExit("No harnesses selected for planning.")

    benchmark_profiles = {
        benchmark: load_benchmark_profile(benchmark) for benchmark in selected_benchmarks
    }
    harness_profiles = {
        harness: load_harness_profile(harness) for harness in selected_harnesses
    }
    unavailable = _collect_missing_configs(tuple(harness_profiles.values()))
    if require_real_configs and unavailable:
        lines = ["Missing required harness config files:"]
        for harness, path in unavailable:
            lines.append(f"- {harness}: {path}")
        raise SystemExit("\n".join(lines))

    items: list[RunItem] = []
    for benchmark in selected_benchmarks:
        case_ids = _enumerate_case_ids(benchmark, config.split)
        benchmark_profile = benchmark_profiles[benchmark]
        for harness in selected_harnesses:
            harness_profile = harness_profiles[harness]
            for case_id in case_ids:
                items.append(
                    RunItem(
                        config_name=config.config_path.stem,
                        config_path=config.config_path,
                        benchmark=benchmark,
                        harness=harness,
                        split=config.split,
                        case_id=case_id,
                        timeout_seconds=config.timeout_seconds,
                        resources=config.resources,
                        results_root=config.results.root,
                        benchmark_profile=benchmark_profile,
                        harness_profile=harness_profile,
                    )
                )

    return BatchPlan(
        config=config,
        selected_benchmarks=selected_benchmarks,
        selected_harnesses=selected_harnesses,
        items=tuple(items),
        unavailable_configs=unavailable,
    )


def build_interactive_plan(
    *,
    config_path: Path,
    benchmark_filters: tuple[str, ...] = (),
    harness_filters: tuple[str, ...] = (),
    require_real_configs: bool = False,
) -> InteractivePlan:
    config = load_interactive_config(config_path.resolve())
    if benchmark_filters:
        filtered = _select_names((config.benchmark,), benchmark_filters, label="benchmark")
        if filtered != (config.benchmark,):
            raise SystemExit("Interactive planning requires exactly one selected benchmark.")

    selected_harness_names = _select_names(
        config.harnesses,
        harness_filters,
        label="harness",
    )
    if not selected_harness_names:
        raise SystemExit("No harnesses selected for interactive planning.")

    benchmark_profile = load_benchmark_profile(config.benchmark)
    harnesses = tuple(load_harness_profile(name) for name in selected_harness_names)
    unavailable = _collect_missing_configs(harnesses)
    if require_real_configs and unavailable:
        lines = ["Missing required harness config files:"]
        for harness, path in unavailable:
            lines.append(f"- {harness}: {path}")
        raise SystemExit("\n".join(lines))

    runtimes = {harness.runtime for harness in harnesses}
    if len(runtimes) != 1:
        runtime_list = ", ".join(sorted(runtimes))
        raise SystemExit(
            "Interactive mode currently requires all selected harnesses to share one runtime. "
            f"Found: {runtime_list}"
        )

    runtime_name = next(iter(runtimes))
    interactive_identity = harnesses[0].harness if len(harnesses) == 1 else "all_harnesses"
    return InteractivePlan(
        config=config,
        benchmark_profile=benchmark_profile,
        harnesses=harnesses,
        runtime_name=runtime_name,
        interactive_identity=interactive_identity,
        results_root=REPO_ROOT / "results" / "agent_runs" / family_relpath(),
        unavailable_configs=unavailable,
    )


def batch_chunks(plan: BatchPlan) -> tuple[tuple[RunItem, ...], ...]:
    size = plan.config.batch.batch_size
    return tuple(
        tuple(plan.items[index : index + size]) for index in range(0, len(plan.items), size)
    )


def run_output_dir(item: RunItem) -> Path:
    return (
        item.results_root
        / item.config_name
        / item.benchmark
        / item.harness
        / item.split
        / item.case_id
    )


def interactive_workspace_dir(plan: InteractivePlan) -> Path:
    return (
        INTERACTIVE_WORKSPACES_ROOT
        / family_relpath()
        / plan.config.config_path.stem
        / plan.config.benchmark
        / plan.interactive_identity
        / plan.config.split
        / plan.config.case_id
    )


def interactive_output_dir(plan: InteractivePlan) -> Path:
    return (
        plan.results_root
        / plan.config.config_path.stem
        / plan.config.benchmark
        / plan.interactive_identity
        / plan.config.split
        / plan.config.case_id
    )


def describe_batch_plan(plan: BatchPlan) -> str:
    chunks = batch_chunks(plan)
    benchmark_case_counts = {
        benchmark: len(_enumerate_case_ids(benchmark, plan.config.split))
        for benchmark in plan.selected_benchmarks
    }
    lines = [
        f"Config: {plan.config.config_path}",
        "Mode: batch",
        f"Benchmarks: {', '.join(plan.selected_benchmarks)}",
        f"Harnesses: {', '.join(plan.selected_harnesses)}",
        f"Split: {plan.config.split}",
        f"Cases per benchmark: "
        + ", ".join(f"{benchmark}={benchmark_case_counts[benchmark]}" for benchmark in plan.selected_benchmarks),
        f"Total concrete runs: {len(plan.items)}",
        f"Chunk size: {plan.config.batch.batch_size}",
        f"Chunk count: {len(chunks)}",
        f"Max concurrency: {plan.config.batch.max_concurrency}",
        f"Max retries: {plan.config.batch.max_retries}",
    ]
    if plan.unavailable_configs:
        lines.append("Unavailable harness configs:")
        for harness, path in plan.unavailable_configs:
            lines.append(f"  - {harness}: {path}")
    else:
        lines.append("Unavailable harness configs: none")
    lines.append("Concrete runs:")
    for item in plan.items:
        lines.append(
            f"  - {item.benchmark} / {item.harness} / {item.split} / {item.case_id} -> {run_output_dir(item)}"
        )
    return "\n".join(lines)


def describe_interactive_plan(plan: InteractivePlan) -> str:
    lines = [
        f"Config: {plan.config.config_path}",
        "Mode: interactive",
        f"Benchmark: {plan.config.benchmark}",
        f"Harnesses: {', '.join(harness.harness for harness in plan.harnesses)}",
        f"Runtime: {plan.runtime_name}",
        f"Split: {plan.config.split}",
        f"Case: {plan.config.case_id}",
        f"Interactive identity: {plan.interactive_identity}",
        f"Workspace path: {interactive_workspace_dir(plan)}",
        f"Result path: {interactive_output_dir(plan)}",
    ]
    if plan.unavailable_configs:
        lines.append("Unavailable harness configs:")
        for harness, path in plan.unavailable_configs:
            lines.append(f"  - {harness}: {path}")
    else:
        lines.append("Unavailable harness configs: none")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    default_config = DEFAULT_INTERACTIVE_CONFIG if args.interactive else DEFAULT_BATCH_CONFIG
    config_path = (args.config or default_config).resolve()
    benchmark_filters = tuple(args.benchmark)
    harness_filters = tuple(args.harness)

    if args.interactive:
        plan = build_interactive_plan(
            config_path=config_path,
            benchmark_filters=benchmark_filters,
            harness_filters=harness_filters,
            require_real_configs=False,
        )
        print(describe_interactive_plan(plan))
        return 0

    plan = build_batch_plan(
        config_path=config_path,
        benchmark_filters=benchmark_filters,
        harness_filters=harness_filters,
        require_real_configs=False,
    )
    print(describe_batch_plan(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
