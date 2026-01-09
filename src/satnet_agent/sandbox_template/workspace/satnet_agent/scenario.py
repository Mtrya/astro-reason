"""SatNet Scenario: State machine for DSN scheduling"""

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Any, TYPE_CHECKING
from copy import deepcopy

if TYPE_CHECKING:
    from .state import SatNetState

from satnet_agent.adapter import (
    Request,
    MaintenanceWindow,
    WeekProblem,
    ViewPeriod,
    load_week_problem,
    DSS_ANTENNAS,
    get_antenna_list,
    get_missions,
    Interval,
    subtract_intervals,
    is_overlap,
    filter_by_duration,
    merge_intervals,
    float_gt,
    float_le,
    float_ge,
)

from .models import (
    SatNetRequest,
    SatNetViewPeriod,
    SatNetAntennaStatus,
    SatNetTrack,
    SatNetMetrics,
    SatNetPlanStatus,
    SatNetScheduleResult,
    SatNetUnscheduleResult,
    SatNetCommitResult,
    SatNetValidationError,
    SatNetConflictError,
    SatNetNotFoundError,
)


class SatNetScenario:
    """State machine for DSN scheduling.
    
    This is the planner layer: returns typed dataclasses and raises exceptions.
    """

    def __init__(
        self,
        problems_path: str,
        maintenance_path: str,
        week: int,
        year: int = 2018,
    ):
        self.problems_path = Path(problems_path)
        self.maintenance_path = Path(maintenance_path)
        self.week = week
        self.year = year

        self._problem = load_week_problem(
            self.problems_path,
            self.maintenance_path,
            week,
            year,
        )

        self._requests: Dict[str, Request] = {
            r.track_id: deepcopy(r) for r in self._problem.requests
        }

        self._maintenance: Dict[str, List[MaintenanceWindow]] = {}
        for m in self._problem.maintenance:
            if m.antenna not in self._maintenance:
                self._maintenance[m.antenna] = []
            self._maintenance[m.antenna].append(m)

        self._scheduled_tracks: Dict[str, SatNetTrack] = {}
        self._antenna_tracks: Dict[str, List[SatNetTrack]] = {
            a: [] for a in DSS_ANTENNAS
        }
        self._mission_tracks: Dict[int, List[SatNetTrack]] = {
            req.subject: [] for req in self._problem.requests
        }

        self._action_counter = 0

        self._week_start, self._week_end = self._get_canonical_week_bounds()

    def _get_canonical_week_bounds(self) -> tuple[int, int]:
        """Get canonical week bounds: ISO week start + 7 days + 12 hours.
        
        This mirrors satnet/satnet/utils.py:get_week_bounds() to ensure
        antenna availability math matches the upstream DSN state board.
        """
        from datetime import datetime, timedelta, timezone
        
        start_date = datetime.fromisocalendar(self.year, self.week, day=1).replace(
            tzinfo=timezone.utc
        )
        end_date = start_date + timedelta(weeks=1, hours=12)
        
        epoch = datetime.fromtimestamp(0, tz=timezone.utc)
        start_epoch = int((start_date - epoch).total_seconds())
        end_epoch = int((end_date - epoch).total_seconds())
        
        return start_epoch, end_epoch

    def _next_action_id(self) -> str:
        self._action_counter += 1
        return f"act_{self._action_counter:04d}"

    def list_unsatisfied_requests(self) -> List[SatNetRequest]:
        """Returns requests still needing time allocation."""
        result = []
        for req in self._requests.values():
            if float_gt(req.remaining_hours, 0):
                result.append(SatNetRequest(
                    request_id=req.track_id,
                    mission_id=req.subject,
                    total_required_hours=req.duration_hours,
                    remaining_hours=round(req.remaining_hours, 3),
                    min_duration_hours=req.duration_min_hours,
                    setup_seconds=req.setup_seconds,
                    teardown_seconds=req.teardown_seconds,
                ))
        return result

    def _get_blocked_intervals(self, antenna: str) -> List[Interval]:
        """Get all blocked intervals for an antenna."""
        blocked: List[Interval] = []

        if antenna in self._maintenance:
            for m in self._maintenance[antenna]:
                blocked.append((m.start, m.end))

        for track in self._antenna_tracks.get(antenna, []):
            blocked.append((track.setup_start, track.teardown_end))

        return merge_intervals(blocked)

    def get_antenna_status(self) -> Dict[str, SatNetAntennaStatus]:
        """Returns availability for each antenna."""
        week_seconds = self._week_end - self._week_start

        result = {}
        for antenna in DSS_ANTENNAS:
            blocked = self._get_blocked_intervals(antenna)

            clipped_blocked = []
            for b in blocked:
                clipped_start = max(b[0], self._week_start)
                clipped_end = min(b[1], self._week_end)
                if clipped_start < clipped_end:
                    clipped_blocked.append((clipped_start, clipped_end))

            blocked_seconds = sum(b[1] - b[0] for b in clipped_blocked)
            available = week_seconds - blocked_seconds

            blocked_ranges = []
            for b in clipped_blocked:
                reason = "scheduled"
                if antenna in self._maintenance:
                    for m in self._maintenance[antenna]:
                        if m.start <= b[0] and m.end >= b[1]:
                            reason = "maintenance"
                            break
                blocked_ranges.append({
                    "start": b[0],
                    "end": b[1],
                    "reason": reason,
                })

            result[antenna] = SatNetAntennaStatus(
                antenna=antenna,
                hours_available=round(available / 3600, 2),
                blocked_ranges=blocked_ranges,
            )

        return result

    def find_view_periods(
        self,
        request_id: str,
        min_duration_hours: float = 0,
    ) -> List[SatNetViewPeriod]:
        """Find available view periods for a request."""
        req = self._requests.get(request_id)
        if req is None:
            raise SatNetNotFoundError(f"Request not found: {request_id}")

        min_duration_seconds = int(min_duration_hours * 3600)
        total_min = min_duration_seconds + req.setup_seconds + req.teardown_seconds

        result = []
        for antenna_key, vps in req.view_periods.items():
            antennas = get_antenna_list(antenna_key)

            all_blocked: List[Interval] = []
            for ant in antennas:
                all_blocked.extend(self._get_blocked_intervals(ant))
            all_blocked = merge_intervals(all_blocked)

            for vp in vps:
                base: Interval = (vp.trx_on, vp.trx_off)

                available = subtract_intervals(base, all_blocked)
                available = filter_by_duration(available, total_min)

                for slot in available:
                    valid_trx_on = slot[0] + req.setup_seconds
                    valid_trx_off = slot[1] - req.teardown_seconds
                    usable_duration = valid_trx_off - valid_trx_on
                    
                    if float_ge(usable_duration, min_duration_seconds):
                        result.append(SatNetViewPeriod(
                            antenna=antenna_key,
                            start_seconds=valid_trx_on,
                            end_seconds=valid_trx_off,
                            duration_hours=round(usable_duration / 3600, 3),
                        ))

        result.sort(key=lambda x: -x.duration_hours)
        return result

    def _validate_track(
        self,
        request_id: str,
        antenna: str,
        trx_on: int,
        trx_off: int,
    ) -> None:
        """Validate a proposed track. Raises exceptions on error."""
        req = self._requests.get(request_id)
        if req is None:
            raise SatNetNotFoundError(f"Request not found: {request_id}")

        if float_le(req.remaining_hours, 0):
            raise SatNetValidationError("Request already satisfied")

        antennas = get_antenna_list(antenna)
        for ant in antennas:
            if ant not in DSS_ANTENNAS:
                raise SatNetValidationError(f"Invalid antenna: {ant}")

        if antenna not in req.view_periods:
            raise SatNetValidationError("Antenna not in request's VP dict")

        setup_start = trx_on - req.setup_seconds
        teardown_end = trx_off + req.teardown_seconds
        total_interval: Interval = (setup_start, teardown_end)

        vp_contained = False
        for vp in req.view_periods[antenna]:
            if vp.trx_on <= setup_start and vp.trx_off >= teardown_end:
                vp_contained = True
                break
        if not vp_contained:
            raise SatNetValidationError("Track not contained in view period")

        duration_seconds = trx_off - trx_on
        min_seconds = req.duration_min_hours * 3600
        if duration_seconds < min_seconds:
            raise SatNetValidationError(f"Track too short: {duration_seconds} < {min_seconds}")

        duration_hours = duration_seconds / 3600
        if float_gt(duration_hours, req.remaining_hours):
            raise SatNetValidationError(
                f"Track duration ({duration_hours:.2f}h) exceeds remaining hours ({req.remaining_hours:.2f}h)"
            )

        for ant in antennas:
            blocked = self._get_blocked_intervals(ant)
            for b in blocked:
                if is_overlap(total_interval, b):
                    raise SatNetConflictError(f"Overlap with blocked interval on {ant}")

        mission_tracks = self._mission_tracks.get(req.subject, [])
        for track in mission_tracks:
            if trx_on < track.trx_off and track.trx_on < trx_off:
                raise SatNetConflictError("Mission already has an overlapping track")

    def schedule_track(
        self,
        request_id: str,
        antenna: str,
        trx_on: int,
        trx_off: int,
    ) -> SatNetScheduleResult:
        """Commit a communication track."""
        self._validate_track(request_id, antenna, trx_on, trx_off)

        req = self._requests[request_id]
        action_id = self._next_action_id()

        duration_hours = (trx_off - trx_on) / 3600
        setup_start = trx_on - req.setup_seconds
        teardown_end = trx_off + req.teardown_seconds

        track = SatNetTrack(
            action_id=action_id,
            request_id=request_id,
            mission_id=req.subject,
            antenna=antenna,
            trx_on=trx_on,
            trx_off=trx_off,
            setup_start=setup_start,
            teardown_end=teardown_end,
            duration_hours=duration_hours,
        )

        self._scheduled_tracks[action_id] = track

        for ant in get_antenna_list(antenna):
            self._antenna_tracks[ant].append(track)

        self._mission_tracks.setdefault(req.subject, []).append(track)

        req.remaining_hours -= duration_hours

        return SatNetScheduleResult(action_id=action_id, track=track)

    def unschedule_track(self, action_id: str) -> SatNetUnscheduleResult:
        """Free up time and restore request's remaining hours."""
        track = self._scheduled_tracks.get(action_id)
        if track is None:
            raise SatNetNotFoundError(f"Track not found: {action_id}")

        req = self._requests[track.request_id]
        req.remaining_hours += track.duration_hours

        for ant in get_antenna_list(track.antenna):
            self._antenna_tracks[ant] = [
                t for t in self._antenna_tracks[ant] if t.action_id != action_id
            ]

        mission_tracks = self._mission_tracks.get(track.mission_id)
        if mission_tracks is not None:
            self._mission_tracks[track.mission_id] = [
                t for t in mission_tracks if t.action_id != action_id
            ]

        del self._scheduled_tracks[action_id]

        return SatNetUnscheduleResult(action_id=action_id)

    def get_plan_status(self) -> SatNetPlanStatus:
        """Get current plan status (scheduled tracks + metrics)."""
        metrics = self._compute_metrics()
        return SatNetPlanStatus(
            tracks=dict(self._scheduled_tracks),
            metrics=metrics,
        )

    def _compute_metrics(self) -> SatNetMetrics:
        """Compute current scheduling metrics."""
        total_allocated = sum(t.duration_hours for t in self._scheduled_tracks.values())

        satisfied = 0
        unsatisfied = 0
        mission_remaining: Dict[int, float] = {}
        mission_requested: Dict[int, float] = {}

        for req in self._requests.values():
            if float_le(req.remaining_hours, 0):
                satisfied += 1
            else:
                unsatisfied += 1

            if req.subject not in mission_remaining:
                mission_remaining[req.subject] = 0
                mission_requested[req.subject] = 0

            mission_remaining[req.subject] += max(0, req.remaining_hours)
            mission_requested[req.subject] += req.duration_hours

        u_i = []
        for mission in mission_requested:
            if float_gt(mission_requested[mission], 0):
                u_i.append(mission_remaining[mission] / mission_requested[mission])

        u_max = max(u_i) if u_i else 0
        u_rms = (sum(u**2 for u in u_i) / len(u_i)) ** 0.5 if u_i else 0

        return SatNetMetrics(
            total_allocated_hours=round(total_allocated, 2),
            requests_satisfied=satisfied,
            requests_unsatisfied=unsatisfied,
            u_max=round(u_max, 4),
            u_rms=round(u_rms, 4),
        )

    def commit_plan(self, output_path: str | None = None) -> SatNetCommitResult:
        """Submit the schedule for scoring and optionally save to JSON."""
        metrics = self._compute_metrics()

        if output_path:
            self._save_schedule(output_path)

        return SatNetCommitResult(
            metrics=metrics,
            plan_json_path=output_path,
        )

    def _save_schedule(self, output_path: str) -> None:
        """Save the current schedule to a JSON file in official format.
        
        Note: Track times (trx_on, trx_off, etc.) are already in absolute epoch 
        seconds since they come directly from the upstream view period data.
        """
        tracks = []
        for t in self._scheduled_tracks.values():
            for antenna in t.antenna.split("_"):
                tracks.append({
                    "RESOURCE": antenna,
                    "SC": t.mission_id,
                    "START_TIME": t.setup_start,
                    "TRACKING_ON": t.trx_on,
                    "TRACKING_OFF": t.trx_off,
                    "END_TIME": t.teardown_end,
                    "TRACK_ID": t.request_id,
                })

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(tracks, f, indent=2)

    def reset(self):
        """Reset to initial state."""
        self._requests = {
            r.track_id: deepcopy(r) for r in self._problem.requests
        }
        self._scheduled_tracks.clear()
        self._antenna_tracks = {a: [] for a in DSS_ANTENNAS}
        self._mission_tracks = {req.subject: [] for req in self._problem.requests}
        self._action_counter = 0

    def to_state(self) -> "SatNetState":
        """Export mutable state for persistence."""
        from .state import SatNetState

        scheduled_tracks = {}
        for action_id, track in self._scheduled_tracks.items():
            scheduled_tracks[action_id] = asdict(track)

        return SatNetState(
            problems_path=str(self.problems_path),
            maintenance_path=str(self.maintenance_path),
            week=self.week,
            year=self.year,
            action_counter=self._action_counter,
            scheduled_tracks=scheduled_tracks,
        )

    @classmethod
    def from_state(cls, state: "SatNetState") -> "SatNetScenario":
        """Reconstruct scenario from persisted state."""
        scenario = cls(
            problems_path=state.problems_path,
            maintenance_path=state.maintenance_path,
            week=state.week,
            year=state.year,
        )

        scenario._action_counter = state.action_counter

        for action_id, track_dict in state.scheduled_tracks.items():
            track = SatNetTrack(**track_dict)

            scenario._scheduled_tracks[action_id] = track

            for ant in get_antenna_list(track.antenna):
                scenario._antenna_tracks[ant].append(track)

            scenario._mission_tracks.setdefault(track.mission_id, []).append(track)

            req = scenario._requests.get(track.request_id)
            if req:
                req.remaining_hours -= track.duration_hours

        return scenario
