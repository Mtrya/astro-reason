"""CLI entry point for the revisit_constellation verifier."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys
import types


def _load_runtime_modules():
    package_name = "_revisit_constellation_verifier_runtime"
    package_dir = Path(__file__).resolve().parent

    package = sys.modules.get(package_name)
    if package is None:
        package = types.ModuleType(package_name)
        package.__path__ = [str(package_dir)]
        sys.modules[package_name] = package

    loaded = {}
    for module_name in ("models", "io", "engine"):
        qualified_name = f"{package_name}.{module_name}"
        module = sys.modules.get(qualified_name)
        if module is None:
            spec = importlib.util.spec_from_file_location(
                qualified_name,
                package_dir / f"{module_name}.py",
            )
            if spec is None or spec.loader is None:
                raise ImportError(f"Unable to load {qualified_name}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[qualified_name] = module
            spec.loader.exec_module(module)
        loaded[module_name] = module
    return loaded["engine"]


if __package__ in {None, ""}:  # pragma: no cover - script-path import support
    _engine_module = _load_runtime_modules()
    verify_solution = _engine_module.verify_solution
else:  # pragma: no cover - exercised through the same runtime path
    from .engine import verify_solution


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify a revisit_constellation solution against one case directory."
    )
    parser.add_argument(
        "case_dir",
        help="Path to the case directory containing assets.json and mission.json",
    )
    parser.add_argument(
        "solution_path",
        help="Path to the solver-produced solution.json file",
    )
    args = parser.parse_args(argv)

    result = verify_solution(args.case_dir, args.solution_path)
    print(result)
    return 0 if result.is_valid else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
