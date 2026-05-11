#!/usr/bin/env python3
"""Summarize authority, model, and acceptance signals in trace event exports."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable


SIGNALS: dict[str, tuple[str, ...]] = {
    "root_listing": (
        "ls /app/workspace/",
        "ls -la /app/workspace/",
        "ls /app/workspace/*.json",
        "find /app/workspace -maxdepth",
    ),
    "case_only_listing": (
        "ls /app/workspace/case",
        "find /app/workspace/case",
    ),
    "readme": (
        "README.md",
        "/app/workspace/README.md",
    ),
    "skill_loading": (
        ".agents/skills",
        "SKILL.md",
        "Using skill",
        "brahe",
    ),
    "verifier_help": (
        "verifier --help",
        "./verifier --help",
        "/app/workspace/verifier --help",
    ),
    "verifier_run": (
        "verifier case/ solution.json",
        "./verifier case/ solution.json",
        "/app/workspace/verifier case/ solution.json",
    ),
    "required_actions_schema": (
        '"actions":',
        "['actions']",
        "sol['actions']",
        '"type": "observation"',
        '"type": "strip_observation"',
    ),
    "alternate_observations_schema": (
        '"observations":',
        "['observations']",
        "sol['observations']",
    ),
    "regional_roll_schema": (
        "roll_deg",
        "roll_angle_deg",
        "duration_s",
        "end_time",
        "strip_observation",
    ),
    "private_model": (
        "propagate",
        "kepler",
        "j2",
        "eci",
        "ecef",
        "teme",
        "gmst",
        "azimuth",
        "elevation",
        "off_nadir",
        "access window",
    ),
    "private_acceptance": (
        "verify.py",
        "my verifier",
        "custom verifier",
        "local validator",
        "should pass",
        "valid according",
        "most likely evaluator",
        "AT_FACTOR",
    ),
    "metric_claim": (
        "WCR",
        "weighted coverage",
        "service_fraction",
        "normalized_quality",
        "revisit",
        "coverage_ratio",
        "Validation passed",
        "Valid:",
        "valid:",
    ),
}


def load_events(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"\]\s*=\s*(.*);\s*$", text, re.S)
    if not match:
        raise ValueError(f"could not find TRACE_EVENTS assignment in {path}")
    payload = json.loads(match.group(1))
    if not isinstance(payload, list):
        raise ValueError(f"trace payload is not a list in {path}")
    return payload


def event_text(event: dict) -> str:
    return str(event.get("text") or "")


def find_hits(
    events: Iterable[dict],
    signal_name: str,
    needles: tuple[str, ...],
    limit: int,
) -> list[tuple[int | None, str, str, str]]:
    hits: list[tuple[int | None, str, str, str]] = []
    lower_needles = tuple(needle.lower() for needle in needles)
    for event in events:
        text = event_text(event)
        lower = text.lower()
        if not any(needle in lower for needle in lower_needles):
            continue
        if signal_name in {"root_listing", "case_only_listing", "verifier_help", "verifier_run"} and event.get(
            "event_type"
        ) != "tool_call":
            continue
        if signal_name == "root_listing" and (
            "/app/workspace/case" in lower or "/app/workspace/solution.json" in lower
        ):
            continue
        one_line = " ".join(text.split())
        hits.append(
            (
                event.get("seq"),
                str(event.get("event_type") or ""),
                str(event.get("title") or ""),
                one_line[:220],
            )
        )
        if len(hits) >= limit:
            break
    return hits


def summarize(path: Path, *, limit: int) -> None:
    events = load_events(path)
    print(f"\n=== {path} ===")
    print(f"events: {len(events)}")
    for name, needles in SIGNALS.items():
        hits = find_hits(events, name, needles, limit)
        print(f"{name}: {len(hits)} shown")
        for seq, event_type, title, preview in hits:
            print(f"  seq={seq} {event_type} {title}: {preview}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("traces", nargs="+", type=Path, help="Trace event .js files")
    parser.add_argument("--limit", type=int, default=3, help="Hits to show per signal")
    args = parser.parse_args()

    for path in args.traces:
        summarize(path, limit=args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
