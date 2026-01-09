"""Sanity tests for the SatNet MCP server.

These tests call the real MCP tool wrappers in ``src/satnet_agent/mcp_server.py`` using
file-backed state. They're intended as smoke tests for the refactored MCP server.
"""

import json
import os
from pathlib import Path
from pprint import pprint
import pytest
import tempfile

from satnet_agent import mcp_server as mcp_server_satnet
from satnet_agent.state import SatNetStateFile
from satnet_agent.scenario import SatNetScenario
from satnet_agent import SatNetTrack

DUMP_RESPONSES = False

OUTPUT_MARKDOWN_PATH = Path(__file__).with_name("_mcp_server_satnet_sanity_output.md")

PROBLEMS_PATH = "satnet/data/problems.json"
MAINTENANCE_PATH = "satnet/data/maintenance.csv"
TEST_WEEK = 40


def _init_markdown_output() -> None:
    if not DUMP_RESPONSES:
        return

    from datetime import datetime, timezone
    header_lines = [
        "# SatNet MCP Server Sanity Output",
        "",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        f"Week: {TEST_WEEK}",
        "",
    ]
    OUTPUT_MARKDOWN_PATH.write_text("\n".join(header_lines), encoding="utf-8")


def _append_markdown_block(title: str, data) -> None:
    if not DUMP_RESPONSES:
        return

    try:
        body = json.dumps(data, indent=2, default=str)
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
def server_with_state(monkeypatch, tmp_path):
    """Provide the mcp_server_satnet module with file-backed state per test."""
    state_path = tmp_path / "scenario.json"
    state_file = SatNetStateFile(state_path)
    state_file.initialize(
        problems_path=PROBLEMS_PATH,
        maintenance_path=MAINTENANCE_PATH,
        week=TEST_WEEK,
        year=2018,
    )

    monkeypatch.setattr(mcp_server_satnet, "STATE_FILE", state_file)

    def load_scenario():
        state = state_file.read()
        return SatNetScenario.from_state(state)

    return mcp_server_satnet, load_scenario


def test_list_unsatisfied_requests_sanity(server_with_state):
    """Smoke-test the list_unsatisfied_requests MCP tool."""

    server, _ = server_with_state

    _init_markdown_output()

    result = server.list_unsatisfied_requests()

    assert isinstance(result, dict)
    assert "total" in result
    assert "items" in result
    assert result["total"] > 0
    
    items = result["items"]
    assert len(items) > 0
    assert all(isinstance(r, dict) for r in items)

    r0 = items[0]
    for field in ["request_id", "mission_id", "total_required_hours", "remaining_hours",
                  "min_duration_hours", "setup_seconds", "teardown_seconds", "summary"]:
        assert field in r0

    _append_markdown_block("list_unsatisfied_requests()", result)

    if DUMP_RESPONSES:
        print("\nUNSATISFIED REQUESTS:")
        pprint(result)


def test_list_unsatisfied_requests_pagination(server_with_state):
    """Test pagination in list_unsatisfied_requests."""
    server, _ = server_with_state
    
    result1 = server.list_unsatisfied_requests(offset=0, limit=5)
    result2 = server.list_unsatisfied_requests(offset=5, limit=5)
    
    assert result1["offset"] == 0
    assert result1["limit"] == 5
    assert len(result1["items"]) <= 5
    
    assert result2["offset"] == 5
    assert len(result2["items"]) <= 5
    
    if result1["total"] > 5:
        assert result1["items"][0]["request_id"] != result2["items"][0]["request_id"]


def test_get_antenna_status_sanity(server_with_state):
    """Smoke-test the get_antenna_status MCP tool."""

    server, _ = server_with_state

    status = server.get_antenna_status()

    assert isinstance(status, dict)
    assert len(status) == 12  # 12 DSS antennas

    for antenna, info in status.items():
        assert antenna.startswith("DSS-")
        assert "hours_available" in info
        assert "summary" in info
        assert "blocked_ranges" not in info  # default is False

    _append_markdown_block("get_antenna_status()", status)

    if DUMP_RESPONSES:
        print("\nANTENNA STATUS:")
        pprint(status)


def test_get_antenna_status_with_blocked_ranges(server_with_state):
    """Test get_antenna_status with include_blocked_ranges=True."""
    server, _ = server_with_state
    
    status = server.get_antenna_status(include_blocked_ranges=True)
    
    for antenna, info in status.items():
        assert "blocked_ranges" in info


def test_find_view_periods_sanity(server_with_state):
    """Smoke-test the find_view_periods MCP tool."""

    server, _ = server_with_state

    requests_result = server.list_unsatisfied_requests()
    req = requests_result["items"][0]

    result = server.find_view_periods(req["request_id"], min_duration_hours=0.5)

    assert isinstance(result, dict)
    assert "total" in result
    assert "items" in result
    assert result["total"] > 0

    vp0 = result["items"][0]
    for field in ["antenna", "start_seconds", "end_seconds", "duration_hours"]:
        assert field in vp0

    _append_markdown_block(f"find_view_periods('{req['request_id']}', min_duration_hours=0.5)", result)

    if DUMP_RESPONSES:
        print(f"\nVIEW PERIODS for {req['request_id']}:")
        pprint(result)


def test_find_view_periods_pagination(server_with_state):
    """Test pagination in find_view_periods."""
    server, _ = server_with_state
    
    requests_result = server.list_unsatisfied_requests()
    req = requests_result["items"][0]
    
    result1 = server.find_view_periods(req["request_id"], offset=0, limit=3)
    result2 = server.find_view_periods(req["request_id"], offset=3, limit=3)
    
    assert result1["offset"] == 0
    assert result1["limit"] == 3
    
    if result1["total"] > 3:
        assert result1["items"][0]["start_seconds"] != result2["items"][0]["start_seconds"]


def test_schedule_track_sanity(server_with_state):
    """Smoke-test the schedule_track MCP tool."""

    server, _ = server_with_state

    requests_result = server.list_unsatisfied_requests()
    req = requests_result["items"][0]
    vps_result = server.find_view_periods(req["request_id"], min_duration_hours=0.5)
    vp = vps_result["items"][0]

    trx_on = vp["start_seconds"]
    track_duration = min(req["remaining_hours"], vp["duration_hours"])
    trx_off = trx_on + int(track_duration * 3600)

    result = server.schedule_track(req["request_id"], vp["antenna"], trx_on, trx_off)

    assert result.get("status") == 0
    assert "action_id" in result
    assert "track" in result
    assert result["dry_run"] == False

    _append_markdown_block(
        f"schedule_track('{req['request_id']}', '{vp['antenna']}', {trx_on}, {trx_off})",
        result
    )

    if DUMP_RESPONSES:
        print("\nSCHEDULE TRACK RESULT:")
        pprint(result)


def test_schedule_track_dry_run(server_with_state):
    """Test dry_run mode for schedule_track."""
    server, _ = server_with_state
    
    requests_result = server.list_unsatisfied_requests()
    req = requests_result["items"][0]
    vps_result = server.find_view_periods(req["request_id"], min_duration_hours=0.5)
    vp = vps_result["items"][0]
    
    trx_on = vp["start_seconds"]
    track_duration = min(req["remaining_hours"], vp["duration_hours"])
    trx_off = trx_on + int(track_duration * 3600)
    
    result = server.schedule_track(req["request_id"], vp["antenna"], trx_on, trx_off, dry_run=True)
    
    assert result["status"] == 0
    assert result["dry_run"] == True
    assert "action_id" not in result
    
    status = server.get_plan_status()
    assert status["num_tracks"] == 0


def test_get_plan_status(server_with_state):
    """Test get_plan_status MCP tool."""
    server, _ = server_with_state
    
    status = server.get_plan_status()
    assert "num_tracks" in status
    assert "tracks" in status
    assert "metrics" in status
    assert status["num_tracks"] == 0
    
    requests_result = server.list_unsatisfied_requests()
    req = requests_result["items"][0]
    vps_result = server.find_view_periods(req["request_id"], min_duration_hours=0.5)
    vp = vps_result["items"][0]
    
    trx_on = vp["start_seconds"]
    track_duration = min(req["remaining_hours"], vp["duration_hours"])
    trx_off = trx_on + int(track_duration * 3600)
    
    server.schedule_track(req["request_id"], vp["antenna"], trx_on, trx_off)
    
    status = server.get_plan_status()
    assert status["num_tracks"] == 1
    assert len(status["tracks"]) == 1


def test_plan_flow_sanity(server_with_state):
    """End-to-end sanity run through all SatNet MCP tools in a single flow.

    Flow:
        list_unsatisfied_requests -> get_antenna_status -> find_view_periods ->
        schedule_track -> get_plan_status -> commit_plan -> unschedule_track -> reset
    """

    server, _ = server_with_state

    _init_markdown_output()

    # 1. List unsatisfied requests
    requests_result = server.list_unsatisfied_requests()
    assert requests_result["total"] > 0
    _append_markdown_block("list_unsatisfied_requests()", requests_result)

    if DUMP_RESPONSES:
        print(f"\nFLOW: {requests_result['total']} unsatisfied requests")

    # 2. Get antenna status
    status = server.get_antenna_status()
    assert len(status) == 12
    _append_markdown_block("get_antenna_status()", status)

    if DUMP_RESPONSES:
        print(f"FLOW: {len(status)} antennas")

    # 3. Find view periods for first request
    req = requests_result["items"][0]
    vps_result = server.find_view_periods(req["request_id"], min_duration_hours=0.5)
    assert vps_result["total"] > 0
    _append_markdown_block(f"find_view_periods('{req['request_id']}')", vps_result)

    if DUMP_RESPONSES:
        print(f"FLOW: {vps_result['total']} view periods for {req['request_id']}")

    # 4. Schedule a track
    vp = vps_result["items"][0]
    trx_on = vp["start_seconds"]
    track_duration = min(req["remaining_hours"], vp["duration_hours"])
    trx_off = trx_on + int(track_duration * 3600)
    
    schedule_result = server.schedule_track(req["request_id"], vp["antenna"], trx_on, trx_off)
    assert schedule_result.get("status") == 0
    action_id = schedule_result["action_id"]
    _append_markdown_block("schedule_track(...)", schedule_result)

    if DUMP_RESPONSES:
        print(f"FLOW: Scheduled track {action_id}")

    # 5. Get plan status
    plan_status = server.get_plan_status()
    assert plan_status["num_tracks"] == 1
    _append_markdown_block("get_plan_status()", plan_status)

    if DUMP_RESPONSES:
        print(f"FLOW: Plan status: {plan_status}")

    # 6. Commit plan
    commit_result = server.commit_plan()
    assert "total_allocated_hours" in commit_result
    assert "u_max" in commit_result
    _append_markdown_block("commit_plan()", commit_result)

    if DUMP_RESPONSES:
        print(f"FLOW: Commit result: {commit_result}")

    # 7. Unschedule track
    unschedule_result = server.unschedule_track(action_id)
    assert unschedule_result.get("status") == 0
    _append_markdown_block(f"unschedule_track('{action_id}')", unschedule_result)

    if DUMP_RESPONSES:
        print("FLOW: Unscheduled track")

    # 8. Reset
    reset_result = server.reset()
    assert reset_result.get("status") == "reset"
    _append_markdown_block("reset()", reset_result)

    if DUMP_RESPONSES:
        print("FLOW: Reset complete")


def test_mcp_server_satnet_name_and_basic_shape():
    """Basic sanity check for the FastMCP server instance."""

    assert mcp_server_satnet.mcp is not None
    assert mcp_server_satnet.mcp.name == "SatNet DSN Scheduler"
