#!/usr/bin/env python3
"""Build the AstroReason base runtime image."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import subprocess
import yaml


RUNTIME_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class RuntimeManifest:
    name: str
    image: str
    dockerfile: Path
    build_context: Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the AstroReason base runtime image")
    parser.add_argument("--tag", help="Override the image tag declared in runtime.yaml")
    return parser.parse_args(argv)


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Runtime manifest does not exist: {path}")

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"Failed to parse runtime manifest {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise SystemExit(f"Runtime manifest must contain a mapping: {path}")
    return data


def _require_str(data: dict[str, Any], key: str, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise SystemExit(f"Runtime manifest field '{key}' must be a non-empty string: {path}")
    return value


def load_runtime() -> RuntimeManifest:
    manifest_path = RUNTIME_DIR / "runtime.yaml"
    data = _load_yaml_mapping(manifest_path)

    dockerfile = RUNTIME_DIR / _require_str(data, "dockerfile", manifest_path)
    build_context = RUNTIME_DIR / _require_str(data, "build_context", manifest_path)

    if not dockerfile.exists():
        raise SystemExit(f"Runtime dockerfile does not exist: {dockerfile}")
    if not build_context.exists():
        raise SystemExit(f"Runtime build context does not exist: {build_context}")

    return RuntimeManifest(
        name=_require_str(data, "name", manifest_path),
        image=_require_str(data, "image", manifest_path),
        dockerfile=dockerfile.resolve(),
        build_context=build_context.resolve(),
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    runtime = load_runtime()
    image_tag = args.tag or runtime.image

    cmd = [
        "docker",
        "build",
        "-t",
        image_tag,
        "-f",
        str(runtime.dockerfile),
        str(runtime.build_context),
    ]
    return subprocess.run(cmd, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
