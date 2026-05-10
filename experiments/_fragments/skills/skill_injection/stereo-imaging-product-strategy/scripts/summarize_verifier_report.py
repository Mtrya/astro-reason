#!/usr/bin/env python3
"""Summarize a stereo_imaging verifier-like JSON report without benchmark imports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def summarize(report: dict[str, Any]) -> dict[str, Any]:
    metrics = _as_dict(report.get("metrics"))
    diagnostics = _as_dict(report.get("diagnostics"))
    observations = _as_list(report.get("derived_observations"))
    violations = _as_list(report.get("violations"))
    pair_evaluations = _as_list(diagnostics.get("pair_evaluations"))
    per_target = _as_dict(diagnostics.get("per_target_best_score"))

    valid_pairs = [
        item for item in pair_evaluations
        if isinstance(item, dict) and item.get("valid") is True
    ]
    invalid_pairs = [
        item for item in pair_evaluations
        if isinstance(item, dict) and item.get("valid") is False
    ]
    covered_targets = [
        target_id for target_id, score in per_target.items()
        if isinstance(score, (int, float)) and score > 0
    ]
    zero_targets = [
        target_id for target_id, score in per_target.items()
        if not isinstance(score, (int, float)) or score <= 0
    ]

    return {
        "valid": report.get("valid", metrics.get("valid")),
        "coverage_ratio": metrics.get("coverage_ratio"),
        "normalized_quality": metrics.get("normalized_quality"),
        "violation_count": len(violations),
        "derived_observation_count": len(observations),
        "pair_evaluation_count": len(pair_evaluations),
        "valid_pair_count": len(valid_pairs),
        "invalid_pair_count": len(invalid_pairs),
        "covered_target_count": len(covered_targets),
        "zero_or_missing_target_count": len(zero_targets),
        "zero_or_missing_targets": sorted(str(target_id) for target_id in zero_targets),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="Path to a verifier-like JSON report.")
    args = parser.parse_args()

    with args.report.open("r", encoding="utf-8") as handle:
        report = json.load(handle)

    print(json.dumps(summarize(report), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
