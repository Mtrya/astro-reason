from __future__ import annotations

from pathlib import Path

import pytest

from scripts import discover_runtime_matrix as runtime_discovery


def _write_runtime_manifest(
    runtime_dir: Path,
    *,
    name: str = "demo",
    image: str = "astroreason-demo:latest",
    dockerfile: str = "Dockerfile",
    build_context: str = ".",
) -> None:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "runtime.yaml").write_text(
        f"name: {name}\n"
        f"image: {image}\n"
        f"dockerfile: {dockerfile}\n"
        f"build_context: {build_context}\n",
        encoding="utf-8",
    )


def _write_dockerfile(runtime_dir: Path) -> None:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")


def test_discover_runtime_matrix_emits_compact_actions_shape(tmp_path: Path) -> None:
    repo_root = tmp_path
    runtimes_dir = repo_root / "runtimes"
    alpha = runtimes_dir / "alpha"
    zeta = runtimes_dir / "zeta"
    _write_runtime_manifest(zeta, name="zeta", image="astroreason-zeta:latest")
    _write_dockerfile(zeta)
    _write_runtime_manifest(alpha, name="alpha", image="astroreason-alpha:latest")
    _write_dockerfile(alpha)

    matrix = runtime_discovery.discover_runtime_matrix(runtimes_dir, repo_root)

    assert matrix == {
        "include": [
            {
                "name": "alpha",
                "image": "astroreason-alpha:latest",
                "dockerfile": "runtimes/alpha/Dockerfile",
                "build_context": "runtimes/alpha",
            },
            {
                "name": "zeta",
                "image": "astroreason-zeta:latest",
                "dockerfile": "runtimes/zeta/Dockerfile",
                "build_context": "runtimes/zeta",
            },
        ]
    }


def test_discover_runtime_matrix_includes_base_runtime_from_manifest(tmp_path: Path) -> None:
    repo_root = tmp_path
    runtimes_dir = repo_root / "runtimes"
    base = runtimes_dir / "base"
    _write_runtime_manifest(base, name="base", image="astroreason-base:latest")
    _write_dockerfile(base)

    matrix = runtime_discovery.discover_runtime_matrix(runtimes_dir, repo_root)

    assert {
        "name": "base",
        "image": "astroreason-base:latest",
        "dockerfile": "runtimes/base/Dockerfile",
        "build_context": "runtimes/base",
    } in matrix["include"]


def test_discovery_rejects_dockerfile_without_manifest(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtimes" / "orphan"
    _write_dockerfile(runtime_dir)

    with pytest.raises(
        runtime_discovery.RuntimeDiscoveryError,
        match="without runtime.yaml",
    ):
        runtime_discovery.discover_runtime_matrix(tmp_path / "runtimes", tmp_path)


def test_discovery_rejects_manifest_paths_that_escape_runtime_dir(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtimes" / "escape"
    _write_runtime_manifest(runtime_dir, dockerfile="../Dockerfile")
    _write_dockerfile(tmp_path / "runtimes")

    with pytest.raises(
        runtime_discovery.RuntimeDiscoveryError,
        match="must stay inside",
    ):
        runtime_discovery.discover_runtime_matrix(tmp_path / "runtimes", tmp_path)


def test_discovery_rejects_missing_required_fields(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtimes" / "missing"
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (runtime_dir / "runtime.yaml").write_text(
        "name: missing\n"
        "dockerfile: Dockerfile\n"
        "build_context: .\n",
        encoding="utf-8",
    )

    with pytest.raises(runtime_discovery.RuntimeDiscoveryError, match="'image'"):
        runtime_discovery.discover_runtime_matrix(tmp_path / "runtimes", tmp_path)


def test_discovery_rejects_duplicate_runtime_names(tmp_path: Path) -> None:
    runtimes_dir = tmp_path / "runtimes"
    first = runtimes_dir / "first"
    second = runtimes_dir / "second"
    _write_runtime_manifest(first, name="same")
    _write_dockerfile(first)
    _write_runtime_manifest(second, name="same", image="astroreason-same-2:latest")
    _write_dockerfile(second)

    with pytest.raises(
        runtime_discovery.RuntimeDiscoveryError,
        match="duplicate runtime name",
    ):
        runtime_discovery.discover_runtime_matrix(runtimes_dir, tmp_path)
