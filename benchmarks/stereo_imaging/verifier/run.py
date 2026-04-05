"""CLI entry point for the stereo_imaging v3 verifier."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import types


def _load_engine_module():
    package_name = "_stereo_imaging_verifier_runtime"
    package_dir = Path(__file__).resolve().parent

    package = sys.modules.get(package_name)
    if package is None:
        package = types.ModuleType(package_name)
        package.__path__ = [str(package_dir)]
        sys.modules[package_name] = package

    qualified_name = f"{package_name}.engine"
    module = sys.modules.get(qualified_name)
    if module is None:
        spec = importlib.util.spec_from_file_location(
            qualified_name,
            package_dir / "engine.py",
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to load {qualified_name}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[qualified_name] = module
        spec.loader.exec_module(module)
    return module


if __package__ in {None, ""}:  # pragma: no cover - script-path import support
    _engine = _load_engine_module()
    verify_solution = _engine.verify_solution
else:  # pragma: no cover
    from .engine import verify_solution


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify a stereo_imaging v3 solution against one canonical case directory.",
    )
    parser.add_argument(
        "case_dir",
        help="Path to dataset/cases/<case_id> (contains mission.yaml, satellites.yaml, targets.yaml)",
    )
    parser.add_argument(
        "solution_path",
        help="Path to solution JSON (per-case object or dataset/example_solution.json mapping)",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Print only valid flag and core metrics (default prints full JSON report)",
    )
    args = parser.parse_args(argv)

    report = verify_solution(args.case_dir, args.solution_path)
    if args.compact:
        print(
            json.dumps(
                {
                    "valid": report.valid,
                    "metrics": report.metrics,
                    "violations": report.violations,
                },
                indent=2,
            )
        )
    else:
        print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.valid else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
