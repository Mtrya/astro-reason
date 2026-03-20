"""SatNet scheduling benchmark verifier.

This module validates SatNet schedules against the public benchmark dataset in
``benchmarks/satnet/dataset``. The canonical dataset is organized as
case-by-case week/year instances under ``dataset/cases/``.

Key responsibilities:

* Parse single-case problem instances into :class:`Request` objects.
* Parse case-local antenna maintenance schedules.
* Parse solution JSON files into :class:`Track` / :class:`Solution` objects.
* Verify that all physical and operational constraints are respected.
* Compute score and fairness metrics compatible with the public fixtures.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

import csv
import json
import math


DEFAULT_DATASET_DIR = Path(__file__).resolve().parent / "dataset"


# Antennas used in the SatNet benchmark (from satnet.envs.DSS_RESOURCES)
ALL_ANTENNAS = {
    f"DSS-{n}" for n in [14, 15, 24, 25, 26, 34, 35, 36, 43, 45, 54, 55, 63, 65]
}


@dataclass
class Request:
    """Single communication request from a case ``problem.json`` file."""

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
    """Single scheduled track from a solution JSON file."""

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
    """A complete schedule solution consisting of per-antenna tracks."""

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
    """All static data required to verify a solution for one SatNet case."""

    week: int
    year: int
    requests: Dict[str, Request]
    maintenance: List[MaintenanceWindow]
    case_id: str | None = None
    metadata: Dict[str, object] = field(default_factory=dict)


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
            for error in self.errors:
                lines.append(f"  - {error}")
        if self.warnings:
            lines.append("Warnings:")
            for warning in self.warnings:
                lines.append(f"  - {warning}")
        return "\n".join(lines)


def make_case_id(week: int, year: int) -> str:
    """Return the canonical SatNet case identifier for a week/year pair."""

    return f"W{int(week)}_{int(year)}"


def _normalize_vp_interval(vp: Dict) -> Tuple[int, int]:
    """Extract a ``(TRX_ON, TRX_OFF)`` tuple in absolute seconds."""

    start = vp.get("TRX ON") or vp.get("TRX_ON") or vp.get("RISE")
    end = vp.get("TRX OFF") or vp.get("TRX_OFF") or vp.get("SET")
    if start is None or end is None:
        raise ValueError(f"Invalid VP entry: {vp!r}")
    return int(start), int(end)


def _load_json(path: str | Path):
    with Path(path).open("r") as file_obj:
        return json.load(file_obj)


def _infer_week_year_from_requests(rows: List[Dict]) -> Tuple[int, int]:
    if not rows:
        raise ValueError("Problem file does not contain any requests")

    week = int(rows[0]["week"])
    year = int(rows[0]["year"])
    for row in rows:
        if int(row["week"]) != week or int(row["year"]) != year:
            raise ValueError("Problem file contains multiple week/year combinations")
    return week, year


def parse_problems(problems_path: str | Path) -> Dict[str, Request]:
    """Parse a canonical SatNet case ``problem.json`` into ``track_id -> Request``."""

    data = _load_json(problems_path)
    if not isinstance(data, list):
        raise ValueError(
            f"SatNet problem files must be case-local JSON arrays, got {problems_path}"
        )

    rows = data
    week, year = _infer_week_year_from_requests(rows)

    requests: Dict[str, Request] = {}
    for row in rows:
        if int(row["week"]) != int(week) or int(row["year"]) != int(year):
            continue

        vp_out: Dict[str, List[Tuple[int, int]]] = {}
        for combo_key, vps in row["resource_vp_dict"].items():
            vp_out[combo_key] = [_normalize_vp_interval(vp) for vp in vps]

        request = Request(
            subject=int(row["subject"]),
            user=str(row["user"]),
            week=int(row["week"]),
            year=int(row["year"]),
            duration=float(row["duration"]),
            duration_min=float(row["duration_min"]),
            resources=[[str(a) for a in resource] for resource in row.get("resources", [])],
            track_id=str(row["track_id"]),
            setup_time=float(row["setup_time"]),
            teardown_time=float(row["teardown_time"]),
            time_window_start=int(row["time_window_start"]),
            time_window_end=int(row["time_window_end"]),
            resource_vp_dict=vp_out,
        )
        requests[request.track_id] = request

    return requests


def parse_maintenance(maintenance_path: str | Path) -> List[MaintenanceWindow]:
    """Parse a canonical SatNet case ``maintenance.csv`` file."""

    path = Path(maintenance_path)
    windows: List[MaintenanceWindow] = []

    with path.open("r", newline="") as file_obj:
        reader = csv.DictReader(file_obj)
        for row in reader:
            try:
                row_week = int(float(row["week"]))
                row_year = int(row["year"])
            except (KeyError, ValueError):
                continue

            windows.append(
                MaintenanceWindow(
                    week=row_week,
                    year=row_year,
                    start_time=int(row["starttime"]),
                    end_time=int(row["endtime"]),
                    antenna=str(row["antenna"]),
                )
            )

    return windows


def list_case_directories(dataset_dir: str | Path = DEFAULT_DATASET_DIR) -> List[Path]:
    """Return all SatNet case directories in canonical order."""

    root = Path(dataset_dir)
    index_path = root / "index.json"
    if index_path.exists():
        index = _load_json(index_path)
        return [root / item["path"] for item in index.get("cases", [])]

    cases_dir = root / "cases"
    return sorted(path for path in cases_dir.iterdir() if path.is_dir())


def resolve_case_directory(
    case_id: str, dataset_dir: str | Path = DEFAULT_DATASET_DIR
) -> Path:
    """Resolve a SatNet case id like ``W10_2018`` to its case directory."""

    case_dir = Path(dataset_dir) / "cases" / case_id
    if not case_dir.exists():
        raise FileNotFoundError(f"SatNet case directory not found: {case_dir}")
    return case_dir


def load_case(case_path: str | Path) -> Instance:
    """Load a canonical SatNet case directory into an :class:`Instance`."""

    case_dir = Path(case_path)
    metadata_path = case_dir / "metadata.json"
    metadata = _load_json(metadata_path) if metadata_path.exists() else {}

    problem_path = case_dir / "problem.json"
    maintenance_path = case_dir / "maintenance.csv"
    requests = parse_problems(problem_path)
    if not requests:
        raise ValueError(f"No requests found in SatNet case: {case_dir}")

    any_request = next(iter(requests.values()))
    week = int(metadata.get("week", any_request.week))
    year = int(metadata.get("year", any_request.year))
    maintenance = parse_maintenance(maintenance_path)

    return Instance(
        week=week,
        year=year,
        requests=requests,
        maintenance=maintenance,
        case_id=str(metadata.get("case_id") or case_dir.name),
        metadata=metadata,
    )


def load_solution(solution_path: str | Path) -> Solution:
    """Load a SatNet solution JSON file."""

    with Path(solution_path).open("r") as file_obj:
        raw_tracks = json.load(file_obj)
    return Solution(tracks=[Track.from_dict(track) for track in raw_tracks])


def _intervals_overlap(a0: int, a1: int, b0: int, b1: int) -> bool:
    """Return True if two half-open intervals ``[a0, a1)`` and ``[b0, b1)`` overlap."""

    return not (a1 <= b0 or b1 <= a0)


def verify(instance: Instance, solution: Solution) -> VerificationResult:
    """Verify a :class:`Solution` against a given :class:`Instance`."""

    errors: List[str] = []
    warnings: List[str] = []
    requests = instance.requests

    maintenance_by_ant: Dict[str, List[MaintenanceWindow]] = defaultdict(list)
    for window in instance.maintenance:
        maintenance_by_ant[window.antenna].append(window)

    tracks_by_ant: Dict[str, List[Track]] = defaultdict(list)
    for track in solution.tracks:
        tracks_by_ant[track.resource].append(track)

    logical_tracks: Dict[Tuple[str, int, int, int, int], List[Track]] = defaultdict(list)
    for track in solution.tracks:
        key = (
            track.track_id,
            track.start_time,
            track.tracking_on,
            track.tracking_off,
            track.end_time,
        )
        logical_tracks[key].append(track)

    for track in solution.tracks:
        if track.track_id not in requests:
            errors.append(f"Unknown track_id '{track.track_id}' in solution")
            continue

        request = requests[track.track_id]

        if track.resource not in ALL_ANTENNAS:
            errors.append(f"Antenna '{track.resource}' not available")
            continue

        if not any(track.resource in combo.split("_") for combo in request.resource_vp_dict):
            errors.append(
                f"Antenna '{track.resource}' not available for request {track.track_id}"
            )

        for window in maintenance_by_ant.get(track.resource, []):
            if _intervals_overlap(
                track.start_time, track.end_time, window.start_time, window.end_time
            ):
                errors.append(
                    f"Track {track.track_id} on {track.resource} overlaps maintenance window"
                )

    for antenna, antenna_tracks in tracks_by_ant.items():
        if len(antenna_tracks) <= 1:
            continue
        sorted_tracks = sorted(antenna_tracks, key=lambda track: track.start_time)
        for prev, curr in zip(sorted_tracks, sorted_tracks[1:]):
            if _intervals_overlap(
                prev.start_time, prev.end_time, curr.start_time, curr.end_time
            ):
                errors.append(
                    f"Overlap between tracks on {antenna}: {prev.track_id} and {curr.track_id}"
                )

    for (track_id, start, on, off, end), group in logical_tracks.items():
        if track_id not in requests:
            continue
        request = requests[track_id]

        resources = sorted({track.resource for track in group})
        combo_key = "_".join(resources)
        vp_intervals = request.resource_vp_dict.get(combo_key)
        if not vp_intervals:
            errors.append(
                f"Antenna combination '{combo_key}' not available for request {track_id}"
            )
        else:
            contained = any(
                vp_start <= on <= off <= vp_end for vp_start, vp_end in vp_intervals
            )
            if not contained:
                errors.append(f"Track {track_id} on {combo_key} not within any View Period")

        expected_on = start + int(request.setup_time * 60)
        expected_end = off + int(request.teardown_time * 60)
        if on != expected_on:
            errors.append(
                f"Setup time mismatch for {track_id}: expected TRACKING_ON = START_TIME + {int(request.setup_time * 60)}s"
            )
        if end != expected_end:
            errors.append(
                f"Teardown time mismatch for {track_id}: expected END_TIME = TRACKING_OFF + {int(request.teardown_time * 60)}s"
            )

        track_duration = off - on
        req_dur_sec = int(request.duration * 3600.0)
        req_min_sec = int(request.duration_min * 3600.0)
        if req_dur_sec >= 28800:
            per_track_min_sec = min(req_min_sec, 14400)
        else:
            per_track_min_sec = req_min_sec

        if track_duration < per_track_min_sec:
            errors.append(
                f"Track {track_id} duration {track_duration}s below minimum {per_track_min_sec}s"
            )

    score_hours = sum(
        (track.tracking_off - track.tracking_on) / 3600.0 for track in solution.tracks
    )

    intervals_by_tid: Dict[str, List[Tuple[int, int]]] = defaultdict(list)
    for (track_id, _start, on, off, _end), _group in logical_tracks.items():
        if track_id not in requests:
            continue
        intervals_by_tid[track_id].append((on, off))

    allocated_by_tid: Dict[str, int] = {}
    satisfied_requests: set[str] = set()
    for track_id, request in requests.items():
        req_dur_sec = int(request.duration * 3600.0)
        req_min_sec = int(request.duration_min * 3600.0)
        total_alloc = sum(off - on for (on, off) in intervals_by_tid.get(track_id, []))
        total_alloc = min(total_alloc, req_dur_sec)
        allocated_by_tid[track_id] = total_alloc
        if total_alloc >= req_min_sec:
            satisfied_requests.add(track_id)

    missions: Dict[int, List[Request]] = defaultdict(list)
    for request in requests.values():
        missions[request.subject].append(request)

    per_mission_u_i: Dict[str, float] = {}
    for mission in sorted(missions):
        mission_requests = missions[mission]
        requested_s = sum(int(request.duration * 3600.0) for request in mission_requests)
        if requested_s <= 0:
            per_mission_u_i[str(mission)] = 0.0
            continue
        allocated_s = sum(
            allocated_by_tid.get(request.track_id, 0) for request in mission_requests
        )
        remaining_s = max(requested_s - allocated_s, 0)
        per_mission_u_i[str(mission)] = remaining_s / requested_s

    u_values = list(per_mission_u_i.values())
    if u_values:
        u_max = max(u_values)
        u_rms = math.sqrt(sum(value * value for value in u_values) / len(u_values))
    else:
        u_max = 0.0
        u_rms = 0.0

    return VerificationResult(
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


def verify_case(case_path: str | Path, solution_path: str | Path) -> VerificationResult:
    """Verify a solution against a canonical SatNet case directory."""

    instance = load_case(case_path)
    solution = load_solution(solution_path)
    return verify(instance, solution)


def _print_cli_result(result: VerificationResult, verbose: bool) -> None:
    if verbose:
        print(result)
    else:
        status = "VALID" if result.is_valid else "INVALID"
        print(f"{status}: score={result.score:.4f}h, tracks={result.n_tracks}")


def main() -> int:  # pragma: no cover - CLI utility
    import argparse

    parser = argparse.ArgumentParser(description="Verify SatNet scheduling solutions")
    parser.add_argument(
        "case",
        help="Path to a canonical SatNet case directory",
    )
    parser.add_argument("solution", help="Path to a solution JSON file")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    result = verify_case(args.case, args.solution)
    _print_cli_result(result, verbose=args.verbose)

    return 0 if result.is_valid else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
