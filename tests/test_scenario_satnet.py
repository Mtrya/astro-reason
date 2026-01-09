"""Sanity tests for the SatNet Scenario (Planner) layer.

These tests call the SatNetScenario class directly, bypassing the MCP server.
This validates that the Scenario returns typed dataclass objects
and raises exceptions appropriately.
"""

import json
import tempfile
from dataclasses import asdict
from pathlib import Path
from datetime import datetime, timezone
from pprint import pprint
import pytest

from satnet_agent.scenario import SatNetScenario
from satnet_agent import (
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

PROBLEMS_PATH = "satnet/data/problems.json"
MAINTENANCE_PATH = "satnet/data/maintenance.csv"
TEST_WEEK = 40

DUMP_RESPONSES = False
OUTPUT_MARKDOWN_PATH = Path(__file__).with_name("_scenario_satnet_sanity_output.md")


def _init_markdown_output() -> None:
    if not DUMP_RESPONSES:
        return

    header_lines = [
        "# SatNet Scenario Sanity Output",
        "",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        f"Week: {TEST_WEEK}",
        "",
    ]
    OUTPUT_MARKDOWN_PATH.write_text("\n".join(header_lines), encoding="utf-8")


def _append_markdown_block(title: str, data) -> None:
    if not DUMP_RESPONSES:
        return

    def default_serializer(o):
        if hasattr(o, "__dataclass_fields__"):
            return asdict(o)
        return repr(o)

    try:
        body = json.dumps(data, indent=2, default=default_serializer)
        code_lang = "json"
    except TypeError:
        body = repr(data)
        code_lang = ""

    with OUTPUT_MARKDOWN_PATH.open("a", encoding="utf-8") as f:
        f.write(f"\n\n## {title}\n\n")
        fence = f"```{code_lang}\n" if code_lang else "```\n"
        f.write(fence)
        f.write(body)
        if not body.endswith("\n"):
            f.write("\n")
        f.write("```\n")


@pytest.fixture
def scenario():
    """Create a fresh SatNetScenario for each test."""
    return SatNetScenario(
        problems_path=PROBLEMS_PATH,
        maintenance_path=MAINTENANCE_PATH,
        week=TEST_WEEK,
    )


class TestGetMethods:
    """Test that get_* methods return typed lists/dicts."""

    def test_list_unsatisfied_requests_returns_typed_list(self, scenario):
        requests = scenario.list_unsatisfied_requests()
        
        assert isinstance(requests, list)
        assert len(requests) > 0
        assert all(isinstance(r, SatNetRequest) for r in requests)
        
        r = requests[0]
        assert hasattr(r, "request_id")
        assert hasattr(r, "mission_id")
        assert hasattr(r, "remaining_hours")
        assert hasattr(r, "min_duration_hours")

    def test_get_antenna_status_returns_typed_dict(self, scenario):
        status = scenario.get_antenna_status()
        
        assert isinstance(status, dict)
        assert len(status) == 12  # 12 DSS antennas
        
        for antenna, s in status.items():
            assert isinstance(s, SatNetAntennaStatus)
            assert hasattr(s, "antenna")
            assert hasattr(s, "hours_available")
            assert hasattr(s, "blocked_ranges")

    def test_find_view_periods_returns_typed_list(self, scenario):
        requests = scenario.list_unsatisfied_requests()
        req = requests[0]
        
        vps = scenario.find_view_periods(req.request_id, min_duration_hours=0.5)
        
        assert isinstance(vps, list)
        assert len(vps) > 0
        assert all(isinstance(vp, SatNetViewPeriod) for vp in vps)
        
        vp = vps[0]
        assert hasattr(vp, "antenna")
        assert hasattr(vp, "start_seconds")
        assert hasattr(vp, "end_seconds")
        assert hasattr(vp, "duration_hours")

    def test_find_view_periods_raises_for_unknown_request(self, scenario):
        with pytest.raises(SatNetNotFoundError):
            scenario.find_view_periods("nonexistent_request_id")


class TestSchedulingOperations:
    """Test scheduling operations return typed results and raise exceptions."""

    def test_schedule_track_returns_schedule_result(self, scenario):
        requests = scenario.list_unsatisfied_requests()
        req = requests[0]
        vps = scenario.find_view_periods(req.request_id, min_duration_hours=0.5)
        vp = vps[0]
        
        trx_on = vp.start_seconds
        track_duration = min(req.remaining_hours, vp.duration_hours)
        trx_off = trx_on + int(track_duration * 3600)
        
        result = scenario.schedule_track(req.request_id, vp.antenna, trx_on, trx_off)
        
        assert isinstance(result, SatNetScheduleResult)
        assert result.action_id is not None
        assert isinstance(result.track, SatNetTrack)

    def test_schedule_track_raises_for_unknown_request(self, scenario):
        with pytest.raises(SatNetNotFoundError):
            scenario.schedule_track("nonexistent", "DSS-14", 0, 3600)

    def test_schedule_track_raises_validation_error_for_bad_times(self, scenario):
        requests = scenario.list_unsatisfied_requests()
        req = requests[0]
        
        with pytest.raises(SatNetValidationError):
            scenario.schedule_track(req.request_id, "DSS-14", 0, 100)

    def test_schedule_track_raises_conflict_error_for_mission_overlap(self, scenario):
        """Test that scheduling overlapping tracks for the same mission raises conflict."""
        requests = scenario.list_unsatisfied_requests()
        req = requests[0]
        vps = scenario.find_view_periods(req.request_id, min_duration_hours=0.5)
        vp = vps[0]
        
        trx_on = vp.start_seconds
        track_duration = min(req.remaining_hours, vp.duration_hours)
        trx_off = trx_on + int(track_duration * 3600)
        
        fake_track = SatNetTrack(
            action_id="test_overlap",
            request_id="fake",
            mission_id=req.mission_id,
            antenna="DSS-14",
            trx_on=trx_on,
            trx_off=trx_off,
            setup_start=trx_on,
            teardown_end=trx_off,
            duration_hours=track_duration,
        )
        scenario._mission_tracks.setdefault(req.mission_id, []).append(fake_track)
        
        try:
            with pytest.raises(SatNetConflictError):
                scenario.schedule_track(req.request_id, vp.antenna, trx_on, trx_off)
        finally:
            scenario._mission_tracks[req.mission_id].pop()

    def test_unschedule_track_returns_unschedule_result(self, scenario):
        requests = scenario.list_unsatisfied_requests()
        req = requests[0]
        vps = scenario.find_view_periods(req.request_id, min_duration_hours=0.5)
        vp = vps[0]
        
        trx_on = vp.start_seconds
        track_duration = min(req.remaining_hours, vp.duration_hours)
        trx_off = trx_on + int(track_duration * 3600)
        
        schedule_result = scenario.schedule_track(req.request_id, vp.antenna, trx_on, trx_off)
        unschedule_result = scenario.unschedule_track(schedule_result.action_id)
        
        assert isinstance(unschedule_result, SatNetUnscheduleResult)
        assert unschedule_result.action_id == schedule_result.action_id

    def test_unschedule_raises_for_unknown_action(self, scenario):
        with pytest.raises(SatNetNotFoundError):
            scenario.unschedule_track("nonexistent_action")


class TestPlanStatus:
    """Test plan status and metrics operations."""

    def test_get_plan_status_returns_typed_result(self, scenario):
        status = scenario.get_plan_status()
        
        assert isinstance(status, SatNetPlanStatus)
        assert isinstance(status.tracks, dict)
        assert isinstance(status.metrics, SatNetMetrics)

    def test_get_plan_status_reflects_scheduled_tracks(self, scenario):
        status_before = scenario.get_plan_status()
        initial_count = len(status_before.tracks)
        
        requests = scenario.list_unsatisfied_requests()
        req = requests[0]
        vps = scenario.find_view_periods(req.request_id, min_duration_hours=0.5)
        vp = vps[0]
        
        trx_on = vp.start_seconds
        track_duration = min(req.remaining_hours, vp.duration_hours)
        trx_off = trx_on + int(track_duration * 3600)
        
        scenario.schedule_track(req.request_id, vp.antenna, trx_on, trx_off)
        
        status_after = scenario.get_plan_status()
        assert len(status_after.tracks) == initial_count + 1

    def test_metrics_update_after_scheduling(self, scenario):
        metrics_before = scenario._compute_metrics()
        
        requests = scenario.list_unsatisfied_requests()
        req = requests[0]
        vps = scenario.find_view_periods(req.request_id, min_duration_hours=0.5)
        vp = vps[0]
        
        trx_on = vp.start_seconds
        track_duration = min(req.remaining_hours, vp.duration_hours)
        trx_off = trx_on + int(track_duration * 3600)
        
        scenario.schedule_track(req.request_id, vp.antenna, trx_on, trx_off)
        
        metrics_after = scenario._compute_metrics()
        assert metrics_after.total_allocated_hours > metrics_before.total_allocated_hours


class TestCommitAndReset:
    """Test commit and reset operations."""

    def test_commit_plan_returns_commit_result(self, scenario):
        result = scenario.commit_plan()
        
        assert isinstance(result, SatNetCommitResult)
        assert isinstance(result.metrics, SatNetMetrics)

    def test_commit_plan_saves_to_file(self, scenario):
        requests = scenario.list_unsatisfied_requests()
        req = requests[0]
        vps = scenario.find_view_periods(req.request_id, min_duration_hours=0.5)
        vp = vps[0]
        
        trx_on = vp.start_seconds
        track_duration = min(req.remaining_hours, vp.duration_hours)
        trx_off = trx_on + int(track_duration * 3600)
        
        scenario.schedule_track(req.request_id, vp.antenna, trx_on, trx_off)
        
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            output_path = f.name
        
        result = scenario.commit_plan(output_path=output_path)
        
        assert result.plan_json_path == output_path
        assert Path(output_path).exists()
        
        with open(output_path) as f:
            schedule = json.load(f)
        
        assert len(schedule) >= 1
        assert "RESOURCE" in schedule[0]
        assert "TRACKING_ON" in schedule[0]

    def test_reset_clears_scheduled_tracks(self, scenario):
        requests = scenario.list_unsatisfied_requests()
        req = requests[0]
        vps = scenario.find_view_periods(req.request_id, min_duration_hours=0.5)
        vp = vps[0]
        
        trx_on = vp.start_seconds
        track_duration = min(req.remaining_hours, vp.duration_hours)
        trx_off = trx_on + int(track_duration * 3600)
        
        scenario.schedule_track(req.request_id, vp.antenna, trx_on, trx_off)
        
        status_before = scenario.get_plan_status()
        assert len(status_before.tracks) > 0
        
        scenario.reset()
        
        status_after = scenario.get_plan_status()
        assert len(status_after.tracks) == 0

    def test_reset_restores_remaining_hours(self, scenario):
        requests = scenario.list_unsatisfied_requests()
        req = requests[0]
        initial_remaining = req.remaining_hours
        
        vps = scenario.find_view_periods(req.request_id, min_duration_hours=0.5)
        vp = vps[0]
        
        trx_on = vp.start_seconds
        track_duration = min(req.remaining_hours, vp.duration_hours)
        trx_off = trx_on + int(track_duration * 3600)
        
        scenario.schedule_track(req.request_id, vp.antenna, trx_on, trx_off)
        
        scenario.reset()
        
        requests_after = scenario.list_unsatisfied_requests()
        req_after = next(r for r in requests_after if r.request_id == req.request_id)
        assert req_after.remaining_hours == initial_remaining


class TestExceptionHierarchy:
    """Test that exceptions follow the defined hierarchy."""

    def test_all_exceptions_inherit_from_base(self):
        from satnet_agent import SatNetScenarioError
        
        assert issubclass(SatNetValidationError, SatNetScenarioError)
        assert issubclass(SatNetConflictError, SatNetScenarioError)
        assert issubclass(SatNetNotFoundError, SatNetScenarioError)

    def test_can_catch_exceptions_by_base_type(self, scenario):
        from satnet_agent import SatNetScenarioError
        
        with pytest.raises(SatNetScenarioError):
            scenario.find_view_periods("nonexistent")


def test_scenario_flow_sanity(scenario):
    """End-to-end sanity run through SatNetScenario with markdown output.

    Flow:
        list_unsatisfied_requests -> get_antenna_status -> find_view_periods ->
        schedule_track -> get_plan_status -> commit_plan -> unschedule_track -> reset
    """
    _init_markdown_output()

    # 1. List unsatisfied requests
    requests = scenario.list_unsatisfied_requests()
    assert len(requests) > 0
    _append_markdown_block("list_unsatisfied_requests()", [asdict(r) for r in requests[:10]])

    if DUMP_RESPONSES:
        print(f"\nFLOW: {len(requests)} unsatisfied requests")

    # 2. Get antenna status
    status = scenario.get_antenna_status()
    assert len(status) == 12
    status_data = {k: asdict(v) for k, v in status.items()}
    _append_markdown_block("get_antenna_status()", status_data)

    if DUMP_RESPONSES:
        print(f"FLOW: {len(status)} antennas")

    # 3. Find view periods for first request
    req = requests[0]
    vps = scenario.find_view_periods(req.request_id, min_duration_hours=0.5)
    assert len(vps) > 0
    _append_markdown_block(f"find_view_periods('{req.request_id}')", [asdict(vp) for vp in vps[:10]])

    if DUMP_RESPONSES:
        print(f"FLOW: {len(vps)} view periods for {req.request_id}")

    # 4. Schedule a track
    vp = vps[0]
    trx_on = vp.start_seconds
    track_duration = min(req.remaining_hours, vp.duration_hours)
    trx_off = trx_on + int(track_duration * 3600)
    
    schedule_result = scenario.schedule_track(req.request_id, vp.antenna, trx_on, trx_off)
    assert schedule_result.action_id is not None
    _append_markdown_block("schedule_track(...)", asdict(schedule_result))

    if DUMP_RESPONSES:
        print(f"FLOW: Scheduled track {schedule_result.action_id}")

    # 5. Get plan status
    plan_status = scenario.get_plan_status()
    assert len(plan_status.tracks) == 1
    plan_status_data = {
        "tracks": {k: asdict(v) for k, v in plan_status.tracks.items()},
        "metrics": asdict(plan_status.metrics),
    }
    _append_markdown_block("get_plan_status()", plan_status_data)

    if DUMP_RESPONSES:
        print(f"FLOW: Plan has {len(plan_status.tracks)} tracks")

    # 6. Commit plan
    commit_result = scenario.commit_plan()
    assert commit_result.metrics is not None
    _append_markdown_block("commit_plan()", asdict(commit_result))

    if DUMP_RESPONSES:
        print(f"FLOW: Commit result: U_max={commit_result.metrics.u_max}")

    # 7. Unschedule track
    unschedule_result = scenario.unschedule_track(schedule_result.action_id)
    assert unschedule_result.action_id == schedule_result.action_id
    _append_markdown_block(f"unschedule_track('{schedule_result.action_id}')", asdict(unschedule_result))

    if DUMP_RESPONSES:
        print("FLOW: Unscheduled track")

    # 8. Reset
    scenario.reset()
    status_after = scenario.get_plan_status()
    assert len(status_after.tracks) == 0
    _append_markdown_block("reset()", {"status": "reset", "tracks_remaining": 0})

    if DUMP_RESPONSES:
        print("FLOW: Reset complete")
