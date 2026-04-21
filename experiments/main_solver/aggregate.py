from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_ROOT = REPO_ROOT / "results" / "main_solver"


def _read_run_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _metric(payload: dict[str, Any], key: str) -> Any:
    verifier = payload.get("verifier") or {}
    reported = payload.get("reported_metrics") or {}
    if key in verifier:
        return verifier[key]
    return reported.get(key)


def _rows(results_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run_path in sorted(results_root.glob("*/*/*/run.json")):
        payload = _read_run_json(run_path)
        if payload is None:
            continue
        rows.append(
            {
                "benchmark": payload.get("benchmark"),
                "solver": payload.get("solver"),
                "case_id": payload.get("case_id"),
                "status": payload.get("status"),
                "evidence_type": payload.get("evidence_type"),
                "runnable": payload.get("runnable"),
                "valid": _metric(payload, "valid"),
                "computed_profit": _metric(payload, "computed_profit"),
                "computed_weight": _metric(payload, "computed_weight"),
                "score": _metric(payload, "score"),
                "n_tracks": _metric(payload, "n_tracks"),
                "n_satisfied_requests": _metric(payload, "n_satisfied_requests"),
                "u_rms": _metric(payload, "u_rms"),
                "u_max": _metric(payload, "u_max"),
                "run_json": str(run_path),
            }
        )
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "benchmark",
        "solver",
        "case_id",
        "status",
        "evidence_type",
        "runnable",
        "valid",
        "computed_profit",
        "computed_weight",
        "score",
        "n_tracks",
        "n_satisfied_requests",
        "u_rms",
        "u_max",
        "run_json",
    ]
    with path.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate main solver results")
    parser.add_argument("--results-root", default=str(DEFAULT_RESULTS_ROOT))
    args = parser.parse_args()

    results_root = Path(args.results_root)
    rows = _rows(results_root)
    summary = {
        "results_root": str(results_root),
        "row_count": len(rows),
        "rows": rows,
    }
    (results_root / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_csv(results_root / "summary.csv", rows)
    print(f"wrote {len(rows)} rows to {results_root / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
