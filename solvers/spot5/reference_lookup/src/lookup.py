from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path


SOLVER_DIR = Path(__file__).resolve().parents[1]
ASSETS_DIR = SOLVER_DIR / "assets"
MANIFEST_PATH = ASSETS_DIR / "manifest.json"
SOLUTIONS_DIR = ASSETS_DIR / "solutions"


def _find_spot_file(case_dir: Path) -> Path:
    if case_dir.is_file() and case_dir.suffix == ".spot":
        return case_dir
    if not case_dir.exists():
        raise FileNotFoundError(f"case path does not exist: {case_dir}")
    if not case_dir.is_dir():
        raise ValueError(f"case path must be a directory or .spot file: {case_dir}")

    spot_files = sorted(case_dir.glob("*.spot"))
    if len(spot_files) != 1:
        raise ValueError(f"expected exactly one .spot file in {case_dir}, found {len(spot_files)}")
    return spot_files[0]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_status(solution_dir: Path, payload: dict) -> None:
    solution_dir.mkdir(parents=True, exist_ok=True)
    (solution_dir / "status.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Lookup a known SPOT5 reference solution")
    parser.add_argument("--case-dir", required=True)
    parser.add_argument("--config-dir", default="")
    parser.add_argument("--solution-dir", required=True)
    args = parser.parse_args()

    case_dir = Path(args.case_dir)
    solution_dir = Path(args.solution_dir)
    config_dir = Path(args.config_dir) if args.config_dir else None

    try:
        spot_file = _find_spot_file(case_dir)
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        digest = _sha256(spot_file)
    except Exception as exc:
        _write_status(
            solution_dir,
            {
                "status": "error",
                "error": str(exc),
                "case_dir": str(case_dir),
            },
        )
        print(f"error: {exc}", file=sys.stderr)
        return 2

    match = manifest["solutions"].get(digest)
    if match is None:
        _write_status(
            solution_dir,
            {
                "status": "unsupported_case",
                "case_dir": str(case_dir),
                "instance_file": str(spot_file),
                "sha256": digest,
            },
        )
        print(f"unsupported_case: {spot_file} sha256={digest}", file=sys.stderr)
        return 3

    source = SOLUTIONS_DIR / match["solution_file"]
    target = solution_dir / "solution.spot_sol.txt"
    if not source.exists():
        _write_status(
            solution_dir,
            {
                "status": "error",
                "error": f"missing lookup solution asset: {source}",
                "case_dir": str(case_dir),
                "sha256": digest,
            },
        )
        print(f"error: missing lookup solution asset: {source}", file=sys.stderr)
        return 2

    solution_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    _write_status(
        solution_dir,
        {
            "status": "solved",
            "case_dir": str(case_dir),
            "config_dir": str(config_dir) if config_dir else None,
            "instance_file": str(spot_file),
            "sha256": digest,
            "case_id": match["case_id"],
            "known_paths": match["known_paths"],
            "source_solution": str(source),
            "solution": str(target),
        },
    )
    print(f"solved: {match['case_id']} -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
