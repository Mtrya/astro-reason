#!/usr/bin/env python3
"""Discover Docker runtime build metadata for GitHub Actions."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIMES_DIR = REPO_ROOT / "runtimes"
MANIFEST_NAME = "runtime.yaml"
TOP_LEVEL_DOCKERFILE = "Dockerfile"


class RuntimeDiscoveryError(ValueError):
    """Raised when runtime metadata cannot be converted into a CI matrix."""


@dataclass(frozen=True)
class RuntimeMatrixEntry:
    name: str
    image: str
    dockerfile: Path
    build_context: Path
    runtime_dir: Path

    def as_matrix_item(self, repo_root: Path) -> dict[str, str]:
        return {
            "name": self.name,
            "image": self.image,
            "dockerfile": _repo_relative_posix(self.dockerfile, repo_root),
            "build_context": _repo_relative_posix(self.build_context, repo_root),
        }


def _repo_relative_posix(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeDiscoveryError(f"runtime manifest does not exist: {path}")
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RuntimeDiscoveryError(f"{path}: failed to parse YAML: {exc}") from exc
    except OSError as exc:
        raise RuntimeDiscoveryError(f"{path}: failed to read manifest: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeDiscoveryError(f"{path}: runtime manifest must be a YAML mapping")
    return payload


def _require_non_empty_string(
    payload: dict[str, Any],
    key: str,
    manifest_path: Path,
) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise RuntimeDiscoveryError(
            f"{manifest_path}: field {key!r} must be a non-empty string"
        )
    return value


def _resolve_manifest_path(
    runtime_dir: Path,
    raw_value: str,
    field: str,
    manifest_path: Path,
) -> Path:
    candidate = (runtime_dir / raw_value).resolve(strict=False)
    runtime_root = runtime_dir.resolve(strict=False)
    if not candidate.is_relative_to(runtime_root):
        raise RuntimeDiscoveryError(
            f"{manifest_path}: field {field!r} must stay inside {runtime_dir}"
        )
    return candidate


def load_runtime_manifest(runtime_dir: Path) -> RuntimeMatrixEntry:
    manifest_path = runtime_dir / MANIFEST_NAME
    payload = _load_yaml_mapping(manifest_path)

    name = _require_non_empty_string(payload, "name", manifest_path)
    image = _require_non_empty_string(payload, "image", manifest_path)
    dockerfile = _resolve_manifest_path(
        runtime_dir,
        _require_non_empty_string(payload, "dockerfile", manifest_path),
        "dockerfile",
        manifest_path,
    )
    build_context = _resolve_manifest_path(
        runtime_dir,
        _require_non_empty_string(payload, "build_context", manifest_path),
        "build_context",
        manifest_path,
    )

    if not dockerfile.is_file():
        raise RuntimeDiscoveryError(
            f"{manifest_path}: dockerfile does not exist: {dockerfile}"
        )
    if not build_context.is_dir():
        raise RuntimeDiscoveryError(
            f"{manifest_path}: build_context must be an existing directory: {build_context}"
        )

    return RuntimeMatrixEntry(
        name=name,
        image=image,
        dockerfile=dockerfile,
        build_context=build_context,
        runtime_dir=runtime_dir.resolve(),
    )


def discover_runtime_matrix(
    runtimes_dir: Path = RUNTIMES_DIR,
    repo_root: Path = REPO_ROOT,
) -> dict[str, list[dict[str, str]]]:
    if not runtimes_dir.is_dir():
        raise RuntimeDiscoveryError(f"runtimes directory does not exist: {runtimes_dir}")

    runtime_dirs = sorted(path for path in runtimes_dir.iterdir() if path.is_dir())
    entries: list[RuntimeMatrixEntry] = []
    errors: list[str] = []

    for runtime_dir in runtime_dirs:
        manifest_path = runtime_dir / MANIFEST_NAME
        top_level_dockerfile = runtime_dir / TOP_LEVEL_DOCKERFILE
        if top_level_dockerfile.is_file() and not manifest_path.is_file():
            errors.append(f"{runtime_dir}: Dockerfile exists without runtime.yaml")
            continue
        if not manifest_path.exists():
            continue
        try:
            entries.append(load_runtime_manifest(runtime_dir))
        except RuntimeDiscoveryError as exc:
            errors.append(str(exc))

    seen_names: dict[str, Path] = {}
    for entry in entries:
        existing = seen_names.get(entry.name)
        if existing is not None:
            errors.append(
                f"{entry.runtime_dir}: duplicate runtime name {entry.name!r}; "
                f"already used by {existing}"
            )
        seen_names[entry.name] = entry.runtime_dir

    if errors:
        raise RuntimeDiscoveryError("\n".join(errors))

    matrix_items = [
        entry.as_matrix_item(repo_root)
        for entry in sorted(
            entries,
            key=lambda item: (item.name, item.runtime_dir.as_posix()),
        )
    ]
    return {"include": matrix_items}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emit a GitHub Actions matrix for Docker runtimes."
    )
    parser.add_argument(
        "--runtimes-dir",
        type=Path,
        default=RUNTIMES_DIR,
        help="Directory containing runtime subdirectories.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        matrix = discover_runtime_matrix(args.runtimes_dir, REPO_ROOT)
    except RuntimeDiscoveryError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(matrix, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
