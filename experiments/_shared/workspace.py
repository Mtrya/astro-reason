"""Shared workspace assembly and artifact collection helpers."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Callable


PLACEHOLDER_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def render_template(template: str, replacements: dict[str, str]) -> str:
    """Render known ``{name}`` placeholders while leaving unknown braces intact."""

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return replacements.get(key, match.group(0))

    return PLACEHOLDER_PATTERN.sub(replace, template)


def copy_file_or_directory(
    source: Path,
    destination: Path,
    *,
    render: bool,
    context: dict[str, str],
) -> None:
    if destination.exists():
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()

    if source.is_dir():
        if render:
            raise SystemExit(f"Cannot render directory source: {source}")
        shutil.copytree(source, destination)
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    if render:
        destination.write_text(
            render_template(source.read_text(encoding="utf-8"), context),
            encoding="utf-8",
        )
        return
    shutil.copy2(source, destination)


def source_available(source: Path, *, require_nonempty_dirs: bool) -> bool:
    if not source.exists():
        return False
    if require_nonempty_dirs and source.is_dir():
        return any(source.iterdir())
    return True


def container_path_to_host_path(
    container_path: Path,
    roots: Any,
    *,
    workspace_mount: Path,
    home_mount: Path,
    output_mount: Path,
) -> Path:
    for prefix, host_root in (
        (workspace_mount, roots.workspace),
        (home_mount, roots.home),
        (output_mount, roots.output),
    ):
        try:
            relative = container_path.relative_to(prefix)
        except ValueError:
            continue
        return host_root / relative
    raise SystemExit(f"Container path is outside mounted roots: {container_path}")


def collect_target_host_path(
    target: Path,
    output_dir: Path,
    *,
    repo_root: Path,
    allow_benchmark_alias: bool = False,
) -> Path:
    if not target.parts:
        raise SystemExit(f"Collect target is empty: {target}")
    root = target.parts[0]
    relative = Path(*target.parts[1:]) if len(target.parts) > 1 else Path()
    if root == "results_root":
        return output_dir / relative
    if root == "repo":
        return repo_root / relative
    if allow_benchmark_alias and root == "benchmark":
        return repo_root / "benchmarks" / relative
    if root in {"experiments", "benchmarks"}:
        return repo_root / target
    raise SystemExit(f"Unsupported collect target root: {target}")


def relative_display(path: Path, repo_root: Path) -> str:
    if path.is_relative_to(repo_root):
        return path.relative_to(repo_root).as_posix()
    return str(path)


def assemble_workspace(
    assemble_specs: tuple[Any, ...],
    roots: Any,
    *,
    context: dict[str, str],
    repo_root: Path,
    workspace_mount: Path,
    home_mount: Path,
    output_mount: Path,
    require_nonempty_dirs: bool,
    missing_source_message: Callable[[Any], str],
    validate_source: Callable[[Path], None] | None = None,
    record_rendered_for_missing: bool = True,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for spec in assemble_specs:
        if not source_available(spec.source, require_nonempty_dirs=require_nonempty_dirs):
            if spec.missing_ok:
                record = {
                    "source": relative_display(spec.source, repo_root),
                    "target": spec.target.as_posix(),
                    "present": False,
                }
                if record_rendered_for_missing:
                    record["rendered"] = spec.render
                records.append(record)
                continue
            raise SystemExit(missing_source_message(spec))

        if validate_source is not None:
            validate_source(spec.source)
        destination = container_path_to_host_path(
            spec.target,
            roots,
            workspace_mount=workspace_mount,
            home_mount=home_mount,
            output_mount=output_mount,
        )
        copy_file_or_directory(spec.source, destination, render=spec.render, context=context)
        records.append(
            {
                "source": relative_display(spec.source, repo_root),
                "target": spec.target.as_posix(),
                "present": True,
                "rendered": spec.render,
            }
        )
    return records


def collect_artifacts(
    collect_specs: tuple[Any, ...],
    roots: Any,
    output_dir: Path,
    *,
    repo_root: Path,
    workspace_mount: Path,
    home_mount: Path,
    output_mount: Path,
    allow_benchmark_alias: bool = False,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for spec in collect_specs:
        source = container_path_to_host_path(
            spec.source,
            roots,
            workspace_mount=workspace_mount,
            home_mount=home_mount,
            output_mount=output_mount,
        )
        target = collect_target_host_path(
            spec.target,
            output_dir,
            repo_root=repo_root,
            allow_benchmark_alias=allow_benchmark_alias,
        )
        if not source.exists():
            if spec.missing_ok:
                records.append(
                    {
                        "source": spec.source.as_posix(),
                        "target": spec.target.as_posix(),
                        "present": False,
                    }
                )
                continue
            raise SystemExit(f"Required collected source does not exist: {source}")

        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
        records.append(
            {
                "source": spec.source.as_posix(),
                "target": spec.target.as_posix(),
                "present": True,
            }
        )
    return records
