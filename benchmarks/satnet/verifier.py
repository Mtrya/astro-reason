"""SatNet scheduling benchmark verifier.

This module validates SatNet schedules against the public benchmark dataset
in :mod:`benchmarks.satnet.dataset`. It is a lightweight reimplementation of
the reference SatNet verifier logic, designed to be self‑contained and free of
dependencies on the original `satnet` package.

Key responsibilities:

* Parse problem instances from ``problems.json`` into :class:`Request` objects.
* Parse antenna maintenance from ``maintenance.csv``.
* Parse solution JSON files into :class:`Track` / :class:`Solution` objects.
* Verify that all physical and operational constraints are respected
  (view periods, setup/teardown, non‑overlap, maintenance, durations).
* Compute score (total tracking hours) and fairness metrics (``U_rms``,
  ``U_max``, per‑mission ``U_i``) compatible with the reference
  :class:`SchedulingSimulator`.

The public tests in ``tests/benchmarks/test_satnet_verifier.py`` define the
API surface and error message substrings that this module must expose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import csv
import json
import math
from collections import defaultdict


# Antennas used in the SatNet benchmark (from satnet.envs.DSS_RESOURCES)
ALL_ANTENNAS = {
    f"DSS-{n}" for n in [14, 24, 25, 26, 34, 35, 36, 43, 54, 55, 63, 65]
}


@dataclass
class Request:
    """Single communication request from ``problems.json``.

    Times in this structure follow the dataset conventions:

    * ``duration`` / ``duration_min`` are in **hours**.
    * ``setup_time`` / ``teardown_time`` are in **minutes**.
    * ``time_window_start`` / ``time_window_end`` are UNIX seconds.
    * ``resource_vp_dict`` stores absolute UNIX seconds for (TRX ON, TRX OFF).
    """

    subject: int
    user: str
    week: int
    year: int
    duration: float
    duration_min: float
    resources: List[List[str]]
    track_id: str
    setup_time: float
    teardown_time: float
    time_window_start: int
    time_window_end: int
    # Key is a resource combination string, e.g. "DSS-34" or "DSS-34_DSS-35".
    # Value is a list of (TRX_ON, TRX_OFF) absolute UNIX seconds.
    resource_vp_dict: Dict[str, List[Tuple[int, int]]]


@dataclass
class Track:
    """Single scheduled track from a solution JSON file.

    This is a *per‑antenna* row. Arrayed tracks appear as several rows with
    the same ``track_id`` and times but different ``resource`` values.
    """

    resource: str
    sc: int
    start_time: int
    tracking_on: int
    tracking_off: int
    end_time: int
    track_id: str

    @classmethod
    def from_dict(cls, data: Dict) -> "Track":
        return cls(
            resource=str(data["RESOURCE"]),
            sc=int(data["SC"]),
            start_time=int(data["START_TIME"]),
            tracking_on=int(data["TRACKING_ON"]),
            tracking_off=int(data["TRACKING_OFF"]),
            end_time=int(data["END_TIME"]),
            track_id=str(data["TRACK_ID"]),
        )


@dataclass
class Solution:
    """A complete schedule solution consisting of per‑antenna tracks."""

    tracks: List[Track]

    @property
    def n_tracks(self) -> int:
        return len(self.tracks)


@dataclass
class MaintenanceWindow:
    week: int
    year: int
    start_time: int
    end_time: int
    antenna: str


@dataclass
class Instance:
    """All static data required to verify a solution for one week."""

    week: int
    year: int
    # Mapping from track_id to Request
    requests: Dict[str, Request]
    maintenance: List[MaintenanceWindow]


@dataclass
class VerificationResult:
    """Result of verifying a SatNet solution."""

    is_valid: bool
    score: float = 0.0
    n_tracks: int = 0
    n_satisfied_requests: int = 0
    u_rms: float = 0.0
    u_max: float = 0.0
    per_mission_u_i: Dict[str, float] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def __str__(self) -> str:  # pragma: no cover - formatting helper
        status = "VALID" if self.is_valid else "INVALID"
        lines = [f"Status: {status}"]
        lines.append(f"Score (hours): {self.score:.4f}")
        lines.append(f"Tracks: {self.n_tracks}")
        lines.append(f"Satisfied requests: {self.n_satisfied_requests}")
        lines.append(f"U_rms: {self.u_rms:.6f}")
        lines.append(f"U_max: {self.u_max:.6f}")
        if self.errors:
            lines.append("Errors:")
            for e in self.errors:
                lines.append(f"  - {e}")
        if self.warnings:
            lines.append("Warnings:")
            for w in self.warnings:
                lines.append(f"  - {w}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _normalize_vp_interval(vp: Dict) -> Tuple[int, int]:
    """Extract a (TRX_ON, TRX_OFF) tuple in absolute seconds from a VP dict.

    The dataset sometimes includes RISE/SET and optional TRX ON/OFF fields.
    For verification we only care about the transmission window, so we
    prioritise TRX fields and fall back to RISE/SET when necessary.
    """

    start = vp.get("TRX ON") or vp.get("TRX_ON") or vp.get("RISE")
    end = vp.get("TRX OFF") or vp.get("TRX_OFF") or vp.get("SET")
    if start is None or end is None:
        raise ValueError(f"Invalid VP entry: {vp!r}")
    return int(start), int(end)


def parse_problems(problems_path: str | Path, week: int, year: int) -> Dict[str, Request]:
    """Parse ``problems.json`` for a given week/year into ``Request`` objects.

    Returns a mapping ``track_id -> Request``.
    """

    path = Path(problems_path)
    with path.open("r") as f:
        data = json.load(f)

    key = f"W{week}_{year}"
    if key not in data:
        raise KeyError(f"Week key {key!r} not found in {path}")

    requests: Dict[str, Request] = {}
    for r in data[key]:
        # Basic sanity: all entries under this key should agree on week/year
        if int(r["week"]) != int(week) or int(r["year"]) != int(year):
            continue

        vp_out: Dict[str, List[Tuple[int, int]]] = {}
        for combo_key, vps in r["resource_vp_dict"].items():
            intervals = [_normalize_vp_interval(vp) for vp in vps]
            vp_out[combo_key] = intervals

        req = Request(
            subject=int(r["subject"]),
            user=str(r["user"]),
            week=int(r["week"]),
            year=int(r["year"]),
            duration=float(r["duration"]),
            duration_min=float(r["duration_min"]),
            resources=[[str(a) for a in res] for res in r.get("resources", [])],
            track_id=str(r["track_id"]),
            setup_time=float(r["setup_time"]),
            teardown_time=float(r["teardown_time"]),
            time_window_start=int(r["time_window_start"]),
            time_window_end=int(r["time_window_end"]),
            resource_vp_dict=vp_out,
        )
        requests[req.track_id] = req

    return requests


def parse_maintenance(
    maintenance_path: str | Path, week: int, year: int
) -> List[MaintenanceWindow]:
    """Parse ``maintenance.csv`` for maintenance windows in the given week."""

    path = Path(maintenance_path)
    windows: List[MaintenanceWindow] = []

    with path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                w = int(float(row["week"]))
                y = int(row["year"])
            except (KeyError, ValueError):
                continue
            if w != int(week) or y != int(year):
                continue
            windows.append(
                MaintenanceWindow(
                    week=w,
                    year=y,
                    start_time=int(row["starttime"]),
                    end_time=int(row["endtime"]),
                    antenna=str(row["antenna"]),
                )
            )

    return windows


# ---------------------------------------------------------------------------
# Verification logic
# ---------------------------------------------------------------------------


def _intervals_overlap(a0: int, a1: int, b0: int, b1: int) -> bool:
    """Return True if two half‑open intervals [a0, a1) and [b0, b1) overlap."""

    return not (a1 <= b0 or b1 <= a0)


def verify(instance: Instance, solution: Solution) -> VerificationResult:
    """Verify a :class:`Solution` against a given :class:`Instance`.

    The function always computes metrics (score, fairness) from the provided
    solution; ``is_valid`` simply indicates whether any constraint violations
    were detected.
    """

    errors: List[str] = []
    warnings: List[str] = []

    requests = instance.requests

    # Group maintenance windows by antenna for quick lookup
    maintenance_by_ant: Dict[str, List[MaintenanceWindow]] = defaultdict(list)
    for mw in instance.maintenance:
        maintenance_by_ant[mw.antenna].append(mw)

    # Group tracks per antenna for overlap checks
    tracks_by_ant: Dict[str, List[Track]] = defaultdict(list)
    for t in solution.tracks:
        tracks_by_ant[t.resource].append(t)

    # Group physical rows into logical tracks: one entry per (request, time span)
    logical_tracks: Dict[Tuple[str, int, int, int, int], List[Track]] = defaultdict(list)
    for t in solution.tracks:
        key = (t.track_id, t.start_time, t.tracking_on, t.tracking_off, t.end_time)
        logical_tracks[key].append(t)

    # ------------------------------------------------------------------
    # Per‑row checks: unknown track_id, invalid antenna, maintenance, basic
    # resource availability.
    # ------------------------------------------------------------------

    for t in solution.tracks:
        # Unknown track_id
        if t.track_id not in requests:
            errors.append(f"Unknown track_id '{t.track_id}' in solution")
            continue

        req = requests[t.track_id]

        # Antenna name must be one of the known DSN resources
        if t.resource not in ALL_ANTENNAS:
            errors.append(f"Antenna '{t.resource}' not available")
            continue

        # Antenna must participate in at least one VP combination for this request
        if not any(t.resource in combo.split("_") for combo in req.resource_vp_dict):
            errors.append(
                f"Antenna '{t.resource}' not available for request {t.track_id}"
            )

        # Maintenance conflict check on this physical antenna
        for mw in maintenance_by_ant.get(t.resource, []):
            if _intervals_overlap(t.start_time, t.end_time, mw.start_time, mw.end_time):
                errors.append(
                    f"Track {t.track_id} on {t.resource} overlaps maintenance window"
                )

    # ------------------------------------------------------------------
    # Overlap detection per antenna (including setup/teardown periods).
    # ------------------------------------------------------------------

    for ant, trs in tracks_by_ant.items():
        if len(trs) <= 1:
            continue
        trs_sorted = sorted(trs, key=lambda tr: tr.start_time)
        for prev, curr in zip(trs_sorted, trs_sorted[1:]):
            if _intervals_overlap(
                prev.start_time, prev.end_time, curr.start_time, curr.end_time
            ):
                errors.append(
                    f"Overlap between tracks on {ant}: {prev.track_id} and {curr.track_id}"
                )

    # ------------------------------------------------------------------
    # Combination‑aware VP containment, setup/teardown consistency, and
    # per‑track minimum duration checks, evaluated per logical track.
    # ------------------------------------------------------------------

    for (tid, start, on, off, end), group in logical_tracks.items():
        if tid not in requests:
            continue
        req = requests[tid]

        # Reconstruct actual antenna combination used by this logical track
        resources = sorted({t.resource for t in group})
        combo_key = "_".join(resources)

        # View period containment for the full antenna combination
        vp_intervals = req.resource_vp_dict.get(combo_key)
        if not vp_intervals:
            errors.append(
                f"Antenna combination '{combo_key}' not available for request {tid}"
            )
        else:
            contained = any(vp_start <= on <= off <= vp_end for vp_start, vp_end in vp_intervals)
            if not contained:
                errors.append(
                    f"Track {tid} on {combo_key} not within any View Period"
                )

        # Setup / teardown consistency (use request's nominal times)
        expected_on = start + int(req.setup_time * 60)
        expected_end = off + int(req.teardown_time * 60)

        if on != expected_on:
            errors.append(
                f"Setup time mismatch for {tid}: expected TRACKING_ON = START_TIME + {int(req.setup_time * 60)}s"
            )

        if end != expected_end:
            errors.append(
                f"Teardown time mismatch for {tid}: expected END_TIME = TRACKING_OFF + {int(req.teardown_time * 60)}s"
            )

        # Per‑logical‑track minimum duration check (seconds)
        track_duration = off - on
        # Match reference implementation: float hours * 3600 then truncation.
        req_dur_sec = int(req.duration * 3600.0)
        req_min_sec = int(req.duration_min * 3600.0)

        if req_dur_sec >= 28800:
            # Long requests are splittable; the reference env allows ~4h splits.
            per_track_min_sec = min(req_min_sec, 14400)
        else:
            per_track_min_sec = req_min_sec

        if track_duration < per_track_min_sec:
            errors.append(
                f"Track {tid} duration {track_duration}s below minimum {per_track_min_sec}s"
            )

    # ------------------------------------------------------------------
    # Metrics: score, satisfied requests, and fairness measures.
    # ------------------------------------------------------------------

    # Score is the sum of all per‑row tracking times in hours.
    score_hours = sum(
        (t.tracking_off - t.tracking_on) / 3600.0 for t in solution.tracks
    )

    # Aggregate allocated time per request using logical tracks, so that
    # arrayed tracks are only counted once per request.
    intervals_by_tid: Dict[str, List[Tuple[int, int]]] = defaultdict(list)
    for (tid, _start, on, off, _end), _group in logical_tracks.items():
        if tid not in requests:
            continue
        intervals_by_tid[tid].append((on, off))

    allocated_by_tid: Dict[str, int] = {}
    satisfied_requests: set[str] = set()

    for tid, req in requests.items():
        req_dur_sec = int(req.duration * 3600.0)
        req_min_sec = int(req.duration_min * 3600.0)
        total_alloc = sum(off - on for (on, off) in intervals_by_tid.get(tid, []))
        total_alloc = min(total_alloc, req_dur_sec)
        allocated_by_tid[tid] = total_alloc
        if total_alloc >= req_min_sec:
            satisfied_requests.add(tid)

    # Fairness metrics per mission (subject)
    missions: Dict[int, List[Request]] = defaultdict(list)
    for req in requests.values():
        missions[req.subject].append(req)

    per_mission_u_i: Dict[str, float] = {}
    for mission in sorted(missions.keys()):
        mission_reqs = missions[mission]
        requested_s = sum(
            int(r.duration * 3600.0) for r in mission_reqs
        )
        if requested_s <= 0:
            per_mission_u_i[str(mission)] = 0.0
            continue
        allocated_s = sum(
            allocated_by_tid.get(r.track_id, 0) for r in mission_reqs
        )
        remaining_s = max(requested_s - allocated_s, 0)
        per_mission_u_i[str(mission)] = remaining_s / requested_s

    u_values = list(per_mission_u_i.values())
    if u_values:
        u_max = max(u_values)
        u_rms = math.sqrt(sum(u * u for u in u_values) / len(u_values))
    else:
        u_max = 0.0
        u_rms = 0.0

    result = VerificationResult(
        is_valid=not errors,
        score=score_hours,
        n_tracks=solution.n_tracks,
        n_satisfied_requests=len(satisfied_requests),
        u_rms=u_rms,
        u_max=u_max,
        per_mission_u_i=per_mission_u_i,
        errors=errors,
        warnings=warnings,
    )

    return result


def verify_files(
    problems_path: str | Path,
    maintenance_path: str | Path,
    solution_path: str | Path,
    week: int,
    year: int,
) -> VerificationResult:
    """Convenience wrapper to verify using file paths and week/year."""

    requests = parse_problems(problems_path, week, year)
    maintenance = parse_maintenance(maintenance_path, week, year)
    instance = Instance(week=week, year=year, requests=requests, maintenance=maintenance)

    with Path(solution_path).open("r") as f:
        raw_tracks = json.load(f)

    solution = Solution(tracks=[Track.from_dict(t) for t in raw_tracks])
    return verify(instance, solution)


def main() -> int:  # pragma: no cover - CLI utility
    import argparse

    parser = argparse.ArgumentParser(
        description="Verify SatNet scheduling solutions",
    )
    parser.add_argument("problems", help="Path to problems.json")
    parser.add_argument("maintenance", help="Path to maintenance.csv")
    parser.add_argument("solution", help="Path to solution JSON file")
    parser.add_argument("--week", type=int, required=True, help="Week number")
    parser.add_argument("--year", type=int, required=True, help="Year")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    result = verify_files(
        problems_path=args.problems,
        maintenance_path=args.maintenance,
        solution_path=args.solution,
        week=args.week,
        year=args.year,
    )

    if args.verbose:
        print(result)
    else:
        status = "VALID" if result.is_valid else "INVALID"
        print(f"{status}: score={result.score:.4f}h, tracks={result.n_tracks}")

    return 0 if result.is_valid else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
