"""Sanity tests for the MCP server.

These tests call the real MCP tool wrappers in ``src/mcp_server.py`` using the
actual planner layer and physics engine. They're intended as an interactive
smoke test you can tweak and inspect, not as brittle unit tests.
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from pprint import pprint
import pytest

from toolkits.mission_planner import mcp_server
from toolkits.mission_planner.scenario.scenario import Scenario

# Set to False if you want quieter output from these sanity tests.
DUMP_RESPONSES = False

OUTPUT_MARKDOWN_PATH = Path(__file__).with_name("_mcp_server_sanity_output.md")


def _extract_list_from_paginated(result, key=None):
    """Extract list from paginated MCP response.

    MCP tools return either:
    - A plain list if all results fit
    - A dict like {"key": [...], "warning": "..."} if paginated
    """
    if isinstance(result, dict):
        if key and key in result:
            return result[key]
        # Try common keys
        for k in ["satellites", "targets", "stations", "actions", "windows", "strips", "lighting_windows"]:
            if k in result:
                return result[k]
        # If no known key, return the dict as-is (might be an error)
        return result
    return result


def _init_markdown_output() -> None:
    if not DUMP_RESPONSES:
        return

    header_lines = [
        "# MCP Server Plan Flow Sanity Output",
        "",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
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
def server_with_initial_plan_scenario(monkeypatch, tmp_path):
    """Provide the mcp_server module with a fresh state file and catalogs per test."""
    from toolkits.mission_planner.scenario.state import StateFile

    # Set up catalogs pointing to test fixtures
    test_catalogs = {
        "satellite_file": "tests/fixtures/case_0001/satellites.yaml",
        "target_file": "tests/fixtures/case_0001/targets.yaml",
        "station_file": "tests/fixtures/case_0001/stations.yaml",
        "plan_file": "tests/fixtures/case_0001/initial_plan.json",
    }

    # Create a temporary state file for this test
    state_file = StateFile(str(tmp_path / "test_state.json"))

    # Monkeypatch the globals
    monkeypatch.setattr(mcp_server, "STATE_FILE", state_file)
    monkeypatch.setattr(mcp_server, "CATALOGS", test_catalogs)

    # Load initial scenario and save to state
    scenario = Scenario(**test_catalogs)
    state_file.write(scenario.export_to_state())

    # Update global test params from scenario
    global TEST_SAT_IDS, TEST_TARGET_IDS, TEST_STATION_IDS, ACCESS_START, ACCESS_END
    TEST_SAT_IDS = [next(iter(scenario.satellites))]
    TEST_TARGET_IDS = [next(iter(scenario.targets))]
    TEST_STATION_IDS = [next(iter(scenario.stations))]
    ACCESS_START = scenario.horizon_start.isoformat()
    ACCESS_END = scenario.horizon_end.isoformat()

    return mcp_server, scenario


def test_query_tools_sanity(server_with_initial_plan_scenario):
    """Smoke-test the query_* MCP tools and pretty-print their outputs."""

    server, scenario = server_with_initial_plan_scenario

    sats_result = server.query_satellites({}, offset=0, limit=5)
    targets_result = server.query_targets({}, offset=0, limit=5)
    stations_result = server.query_stations({}, offset=0, limit=5)

    # Handle paginated response format
    sats = _extract_list_from_paginated(sats_result)
    targets = _extract_list_from_paginated(targets_result)
    stations = _extract_list_from_paginated(stations_result)

    assert isinstance(sats, list)
    assert isinstance(targets, list)
    assert isinstance(stations, list)

    if sats:
        assert all(isinstance(s, dict) for s in sats)
        assert any(s["id"] in scenario.satellites for s in sats)
    if targets:
        assert all(isinstance(t, dict) for t in targets)
        assert any(t["id"] in scenario.targets for t in targets)
    if stations:
        assert all(isinstance(s, dict) for s in stations)
        assert any(s["id"] in scenario.stations for s in stations)

    if DUMP_RESPONSES:
        print("\nSATELLITES:")
        pprint(sats)
        print("\nTARGETS:")
        pprint(targets)
        print("\nSTATIONS:")
        pprint(stations)


def test_query_actions_sanity(server_with_initial_plan_scenario):
    """Smoke-test the query_actions MCP tool."""

    server, scenario = server_with_initial_plan_scenario

    _init_markdown_output()

    actions_result = server.query_actions({}, offset=0, limit=5)
    _append_markdown_block("query_actions({}, offset=0, limit=5)", actions_result)

    # Handle paginated response format
    actions = _extract_list_from_paginated(actions_result)

    assert isinstance(actions, list)
    assert len(actions) > 0
    assert all(isinstance(a, dict) for a in actions)

    a0 = actions[0]
    for field in ["action_id", "type", "satellite_id", "start", "end"]:
        assert field in a0

    # Filter by action_id
    filter_action_id = {"action_id": a0["action_id"]}
    by_id = server.query_actions(filter_action_id, limit=5)
    assert len(by_id) == 1
    assert by_id[0]["action_id"] == a0["action_id"]
    _append_markdown_block(f"query_actions({filter_action_id}, limit=5)", by_id)

    # Filter by type
    filter_type = {"type": a0["type"]}
    by_type = server.query_actions(filter_type, limit=10)
    assert all(a["type"] == a0["type"] for a in by_type)
    _append_markdown_block(f"query_actions({filter_type}, limit=10)", by_type)

    # Filter by satellite_id
    sat_id = a0["satellite_id"]
    filter_sat = {"satellite_id": sat_id}
    by_sat = server.query_actions(filter_sat, limit=10)
    assert all(a["satellite_id"] == sat_id for a in by_sat)
    _append_markdown_block(f"query_actions({filter_sat}, limit=10)", by_sat)

    # Filter by start date via regex
    date_prefix = a0["start"][:10]
    filter_start = {"start": {"regex": f"^{date_prefix}"}}
    by_start_regex = server.query_actions(filter_start, limit=20)
    assert len(by_start_regex) > 0
    assert all(str(a["start"]).startswith(date_prefix) for a in by_start_regex)
    _append_markdown_block(f"query_actions({filter_start}, limit=20)", by_start_regex)

    # Filter by end time substring via regex
    time_fragment = a0["end"][11:16]  # HH:MM
    filter_end = {"end": {"regex": time_fragment}}
    by_end_regex = server.query_actions(filter_end, limit=20)
    assert len(by_end_regex) > 0
    assert all(time_fragment in str(a["end"]) for a in by_end_regex)
    _append_markdown_block(f"query_actions({filter_end}, limit=20)", by_end_regex)

    if DUMP_RESPONSES:
        print("\nACTIONS:")
        pprint(actions)


def test_query_windows_sanity(server_with_initial_plan_scenario):
    """Smoke-test the query_windows MCP tool."""

    server, _ = server_with_initial_plan_scenario
    
    # First compute some windows to register them
    windows_computed_result = server.compute_access_windows(
        TEST_SAT_IDS,
        TEST_TARGET_IDS,
        None,
        None,
        ACCESS_START,
        ACCESS_END,
        constraints=None,
    )
    windows_computed = _extract_list_from_paginated(windows_computed_result)

    if not windows_computed:
        pytest.skip("No access windows computed, cannot test query_windows")

    # Now query all registered windows
    windows_result = server.query_windows({}, offset=0, limit=10)
    windows = _extract_list_from_paginated(windows_result)

    assert isinstance(windows, list)
    assert len(windows) > 0
    assert all(isinstance(w, dict) for w in windows)

    # Check structure
    w0 = windows[0]
    assert "window_id" in w0
    assert "satellite_id" in w0
    assert "start" in w0
    assert "end" in w0
    assert "duration_sec" in w0
    assert "counterpart_kind" in w0
    assert w0["counterpart_kind"] in ["target", "station"]

    # Test filtering by satellite
    sat_windows_result = server.query_windows({"satellite_id": TEST_SAT_IDS[0]}, limit=10)
    sat_windows = _extract_list_from_paginated(sat_windows_result)
    assert all(w["satellite_id"] == TEST_SAT_IDS[0] for w in sat_windows)

    # Test filtering by duration
    long_windows_result = server.query_windows({"duration_sec": {"gte": 300}}, limit=10)
    long_windows = _extract_list_from_paginated(long_windows_result)
    assert all(w["duration_sec"] >= 300 for w in long_windows)
    
    if DUMP_RESPONSES:
        print("\nQUERY WINDOWS (ALL):")
        pprint(windows)
        print(f"\nQUERY WINDOWS (satellite_id={TEST_SAT_IDS[0]}):")
        pprint(sat_windows)
        print(f"\nQUERY WINDOWS (duration >= 300s):")
        pprint(long_windows)


def test_compute_lighting_sanity(server_with_initial_plan_scenario):
    """Smoke-test the lighting windows MCP tool (sunlight only)."""

    server, _ = server_with_initial_plan_scenario
    windows_result = server.compute_lighting_windows(
        TEST_SAT_IDS,
        ACCESS_START,
        ACCESS_END,
    )
    windows = _extract_list_from_paginated(windows_result)

    assert isinstance(windows, list)
    if not windows:
        pytest.skip("No lighting windows returned for current configuration")

    w0 = windows[0]
    assert w0["satellite_id"] in TEST_SAT_IDS
    assert "start" in w0 and "end" in w0

    if DUMP_RESPONSES:
        print("\nLIGHTING WINDOWS (SUNLIGHT):")
        print(json.dumps(windows[:5], indent=2))


def test_plan_flow_sanity(server_with_initial_plan_scenario):
    """End-to-end sanity run through all MCP tools in a single flow.

    Flow:
        query_* -> compute_lighting_windows -> compute_access_windows ->
        stage_action (dry + real) -> get_plan_status -> commit_plan ->
        unstage_action -> reset_plan
    """

    server, _ = server_with_initial_plan_scenario

    _init_markdown_output()

    # Query tools
    sats_result = server.query_satellites({}, offset=0, limit=5)
    targets_result = server.query_targets({}, offset=0, limit=5)
    stations_result = server.query_stations({}, offset=0, limit=5)
    actions_initial_result = server.query_actions({}, offset=0, limit=10)

    sats = _extract_list_from_paginated(sats_result)
    targets = _extract_list_from_paginated(targets_result)
    stations = _extract_list_from_paginated(stations_result)
    actions_initial = _extract_list_from_paginated(actions_initial_result)

    assert isinstance(sats, list)
    assert isinstance(targets, list)
    assert isinstance(stations, list)

    if DUMP_RESPONSES:
        print("\nPLAN FLOW: SATELLITES:")
        print(json.dumps(sats, indent=2))
        print("\nPLAN FLOW: TARGETS:")
        print(json.dumps(targets, indent=2))
        print("\nPLAN FLOW: STATIONS:")
        print(json.dumps(stations, indent=2))

    _append_markdown_block("query_satellites({}, offset=0, limit=5)", sats)
    _append_markdown_block("query_targets({}, offset=0, limit=5)", targets)
    _append_markdown_block("query_stations({}, offset=0, limit=5)", stations)
    _append_markdown_block("query_actions({}, offset=0, limit=10)", actions_initial)

    if actions_initial:
        first_action = actions_initial[0]
        filt = {"satellite_id": first_action.get("satellite_id")}
        actions_by_sat_result = server.query_actions(filt, offset=0, limit=10)
        actions_by_sat = _extract_list_from_paginated(actions_by_sat_result)
        _append_markdown_block(f"query_actions({filt}, offset=0, limit=10)", actions_by_sat)

    # Lighting windows tool
    lighting_windows_result = server.compute_lighting_windows(
        TEST_SAT_IDS,
        ACCESS_START,
        ACCESS_END,
    )
    lighting_windows = _extract_list_from_paginated(lighting_windows_result)

    assert isinstance(lighting_windows, list)
    if not lighting_windows:
        _append_markdown_block(
            "compute_lighting_windows(TEST_SAT_IDS, ACCESS_START, ACCESS_END)",
            {"note": "No lighting windows returned for current configuration"},
        )
        pytest.skip("No lighting windows returned for current configuration")

    if DUMP_RESPONSES:
        print("\nPLAN FLOW: LIGHTING WINDOWS (SUNLIGHT):")
        print(json.dumps(lighting_windows[:5], indent=2))

    _append_markdown_block(
        "compute_lighting_windows(TEST_SAT_IDS, ACCESS_START, ACCESS_END)",
        lighting_windows[:5],
    )

    # Access windows and planning tools
    try:
        windows_result = server.compute_access_windows(
            TEST_SAT_IDS,
            TEST_TARGET_IDS,
            None,
            None,
            ACCESS_START,
            ACCESS_END,
            constraints=None,
        )
        windows = _extract_list_from_paginated(windows_result)
    except Exception as exc:  # Network or Astrox backend issues
        _append_markdown_block(
            "compute_access_windows ERROR",
            {"error": repr(exc)},
        )
        pytest.skip(f"compute_access_windows failed: {exc!r} (check Astrox/network)")

    assert isinstance(windows, list)

    if DUMP_RESPONSES:
        print("\nPLAN FLOW: ACCESS WINDOWS:")
        print(json.dumps(windows, indent=2))

    _append_markdown_block(
        "compute_access_windows(TEST_SAT_IDS, TEST_TARGET_IDS, None, ACCESS_START, ACCESS_END)",
        windows,
    )

    # Query the registered windows
    query_all_result = server.query_windows({}, offset=0, limit=10)
    query_all = _extract_list_from_paginated(query_all_result)
    query_filtered_result = server.query_windows({"satellite_id": TEST_SAT_IDS[0]}, offset=0, limit=5)
    query_filtered = _extract_list_from_paginated(query_filtered_result)
    
    if DUMP_RESPONSES:
        print("\nPLAN FLOW: QUERY WINDOWS (ALL):")
        print(json.dumps(query_all, indent=2))
        print("\nPLAN FLOW: QUERY WINDOWS (FILTERED):")
        print(json.dumps(query_filtered, indent=2))

    _append_markdown_block("query_windows({}, offset=0, limit=10)", query_all)
    _append_markdown_block(f"query_windows({{\"satellite_id\": \"{TEST_SAT_IDS[0]}\"}}, offset=0, limit=5)", query_filtered)

    if not windows:
        _append_markdown_block(
            "compute_access_windows(TEST_SAT_IDS, TEST_TARGET_IDS, None, ACCESS_START, ACCESS_END)",
            {"note": "No access windows returned for current configuration"},
        )
        pytest.skip("No access windows returned for current configuration")

    w0 = windows[0]

    # Basic shape sanity
    assert w0["satellite_id"] in TEST_SAT_IDS
    assert w0["target_id"] in TEST_TARGET_IDS

    start_str = w0["start"]
    # Limit duration to 1 minute to avoid storage overflow in test
    start_dt = datetime.fromisoformat(start_str)
    end_dt = start_dt + timedelta(minutes=1)
    end_str = end_dt.isoformat()

    action = {
        "type": "observation",  # must match Scenario._parse_action
        "satellite_id": w0["satellite_id"],
        "target_id": w0["target_id"],
        "window_id": w0["window_id"],
        "start_time": start_str,
        "end_time": end_str,
    }

    # Dry run (successful dry_run returns status="feasible", failure returns feasible=False)
    dry = server.stage_action(action, dry_run=True)
    if dry.get("feasible") is False:
        pprint(dry)
        pytest.fail(f"Dry run failed: {dry.get('reason')}")
    assert dry.get("status") == "feasible" or dry.get("action_id") is not None

    if DUMP_RESPONSES:
        print("\nPLAN FLOW: STAGE ACTION (DRY RUN):")
        print(json.dumps(dry, indent=2))

    _append_markdown_block("stage_action(action, dry_run=True)", dry)

    # Real stage
    staged = server.stage_action(action, dry_run=False)
    assert staged["status"] == "staged"
    action_id = staged["action_id"]

    if DUMP_RESPONSES:
        print("\nPLAN FLOW: STAGE ACTION (REAL):")
        print(json.dumps(staged, indent=2))

    _append_markdown_block("stage_action(action, dry_run=False)", staged)

    status = server.get_plan_status()

    if DUMP_RESPONSES:
        print("\nPLAN FLOW: PLAN STATUS AFTER STAGE:")
        print(json.dumps(status, indent=2))

    _append_markdown_block("get_plan_status()", status)

    commit = server.commit_plan()
    assert commit["valid"] is True

    if DUMP_RESPONSES:
        print("\nPLAN FLOW: COMMIT RESULT:")
        print(json.dumps(commit, indent=2))

    _append_markdown_block("commit_plan()", commit)

    # Unstage and reset sanity
    unstaged = server.unstage_action(action_id)
    assert unstaged["status"] == "unstaged"

    if DUMP_RESPONSES:
        print("\nPLAN FLOW: UNSTAGE ACTION:")
        print(json.dumps(unstaged, indent=2))

    _append_markdown_block("unstage_action(action_id)", unstaged)

    reset = server.reset_plan()
    assert reset["status"] == "reset"
    # New format just has status and message, no actions_cleared
    assert "message" in reset or "status" in reset

    if DUMP_RESPONSES:
        print("\nPLAN FLOW: RESET PLAN:")
        print(json.dumps(reset, indent=2))

    _append_markdown_block("reset_plan()", reset)


def test_strip_tools_sanity(server_with_initial_plan_scenario):
    """Smoke-test the strip management MCP tools."""

    server, scenario = server_with_initial_plan_scenario

    # Register strips
    strips = [
        {"id": "strip_mcp_test", "name": "MCP Test Strip", "points": [(40.0, -75.0), (45.0, -75.0)]},
    ]
    registered = server.register_strips(strips)
    assert isinstance(registered, list)
    assert len(registered) == 1
    assert registered[0]["id"] == "strip_mcp_test"

    if DUMP_RESPONSES:
        print("\nSTRIP: REGISTER STRIPS:")
        print(json.dumps(registered, indent=2))

    # Query strips
    queried_result = server.query_strips(offset=0, limit=10)
    queried = _extract_list_from_paginated(queried_result)
    assert isinstance(queried, list)
    assert len(queried) >= 1
    assert any(s["id"] == "strip_mcp_test" for s in queried)

    if DUMP_RESPONSES:
        print("\nSTRIP: QUERY STRIPS:")
        print(json.dumps(queried, indent=2))

    # Compute strip windows
    sat_id = list(scenario.satellites.keys())[0]
    windows_result = server.compute_strip_windows(
        [sat_id],
        ["strip_mcp_test"],
        ACCESS_START,
        ACCESS_END,
    )
    windows = _extract_list_from_paginated(windows_result)
    assert isinstance(windows, list)
    # Windows may or may not exist depending on satellite/strip geometry

    if DUMP_RESPONSES:
        print("\nSTRIP: COMPUTE STRIP WINDOWS:")
        print(json.dumps(windows[:5] if windows else [], indent=2))

    # Unregister strips
    unregistered = server.unregister_strips(["strip_mcp_test"])
    assert unregistered["status"] == "success"

    if DUMP_RESPONSES:
        print("\nSTRIP: UNREGISTER STRIPS:")
        print(json.dumps(unregistered, indent=2))

    # Verify unregistration
    final_strips_result = server.query_strips(offset=0, limit=10)
    final_strips = _extract_list_from_paginated(final_strips_result)
    assert not any(s["id"] == "strip_mcp_test" for s in final_strips)


def test_mcp_server_name_and_basic_shape():
    """Basic sanity check for the FastMCP server instance."""

    assert mcp_server.mcp is not None
    assert mcp_server.mcp.name == "Satellite Planner"


def test_ground_track_mcp_tool(server_with_initial_plan_scenario):
    """Smoke-test the get_ground_track MCP tool."""

    server, scenario = server_with_initial_plan_scenario

    # Get first satellite
    sat_id = list(scenario.satellites.keys())[0]
    
    # Use a short time window (2 hours)
    start = scenario.horizon_start
    end = start + timedelta(hours=2)
    
    # Test without polygon filter
    track_full = server.get_ground_track(
        satellite_id=sat_id,
        start_time=start.isoformat(),
        end_time=end.isoformat(),
        step_sec=120.0,  # 2-minute steps
    )
    
    # Should return a list of points
    assert isinstance(track_full, (list, dict))
    
    if isinstance(track_full, dict):
        # Truncated response with metadata
        assert "points" in track_full
        assert "total_count" in track_full
        points = track_full["points"]
    else:
        # Direct list of points
        points = track_full
    
    assert len(points) > 0
    assert all(isinstance(p, dict) for p in points)
    
    # Verify fields
    p0 = points[0]
    assert "lat" in p0
    assert "lon" in p0
    assert "time" in p0
    assert -90 <= p0["lat"] <= 90
    assert -180 <= p0["lon"] <= 180
    
    if DUMP_RESPONSES:
        print("\nGROUND TRACK (NO FILTER):")
        print(json.dumps(points[:5], indent=2))
    
    # Test with polygon filter
    polygon = [
        [25.0, -125.0],  # Southwest
        [50.0, -125.0],  # Northwest
        [50.0, -65.0],   # Northeast
        [25.0, -65.0],   # Southeast
    ]
    
    track_filtered = server.get_ground_track(
        satellite_id=sat_id,
        start_time=start.isoformat(),
        end_time=end.isoformat(),
        step_sec=120.0,
        filter_polygon=polygon,
    )
    
    assert isinstance(track_filtered, (list, dict))
    
    if isinstance(track_filtered, dict):
        filtered_points = track_filtered["points"]
    else:
        filtered_points = track_filtered
    
    # Filtered should have fewer or equal points
    assert len(filtered_points) <= len(points)
    
    # All filtered points should be within polygon bounds
    for p in filtered_points:
        assert 25.0 <= p["lat"] <= 50.0
        assert -125.0 <= p["lon"] <= -65.0
    
    if DUMP_RESPONSES:
        print("\nGROUND TRACK (WITH POLYGON FILTER):")
        print(json.dumps(filtered_points[:5], indent=2))
        print(f"Total points: {len(points)}, Filtered points: {len(filtered_points)}")


def test_evaluate_comms_latency_mcp_tool(server_with_initial_plan_scenario):
    """Smoke-test the evaluate_comms_latency MCP tool."""

    server, scenario = server_with_initial_plan_scenario

    stations = list(scenario.stations.keys())
    satellites = list(scenario.satellites.keys())

    if len(stations) < 3:
        pytest.skip("Need at least 3 stations")
    if len(satellites) < 1:
        pytest.skip("Need at least 1 satellite")

    # Use stations[1] and stations[2] as they have good geometry (from test_scenario.py)
    source_id = stations[1]
    dest_id = stations[2]
    relay_ids = [satellites[0]]

    # Use short time window (12 hours)
    start = scenario.horizon_start
    end = start + timedelta(hours=12)

    result = server.evaluate_comms_latency(
        source_station_id=source_id,
        dest_station_id=dest_id,
        start_time=start.isoformat(),
        end_time=end.isoformat(),
    )

    _append_markdown_block(f"evaluate_comms_latency({source_id} -> {dest_id} via 1 relay)", result)

    # Check structure
    assert isinstance(result, dict)
    assert "window_count" in result
    assert "windows" in result
    assert isinstance(result["windows"], list)

    # If windows exist, verify structure
    if result["window_count"] > 0:
        w = result["windows"][0]
        assert "path" in w
        assert "start" in w
        assert "end"in w
        assert "duration_sec" in w
        assert "latency_min_ms" in w
        assert "latency_max_ms" in w
        assert "latency_mean_ms" in w
        assert "sample_count" in w

        # Verify latency values are reasonable
        assert w["latency_min_ms"] > 0
        assert w["latency_max_ms"] < 100  # LEO should be < 100ms
        assert w["latency_min_ms"] <= w["latency_mean_ms"] <= w["latency_max_ms"]

        # Verify path structure
        assert source_id in w["path"]
        assert dest_id in w["path"]
        assert satellites[0] in w["path"]

    if DUMP_RESPONSES:
        print(f"\nCOMMS LATENCY ({result['window_count']} windows):")
        print(json.dumps(result, indent=2))


def test_isl_action_mcp_tools(server_with_initial_plan_scenario):
    """Smoke-test ISL window computation and action staging via MCP tools."""
    
    server, scenario = server_with_initial_plan_scenario
    
    satellites = list(scenario.satellites.keys())
    
    sat_a = satellites[1]
    sat_b = satellites[2]
    
    # Compute ISL windows
    windows_result = server.compute_access_windows(
        [sat_a],
        None,  # target_ids
        None,  # station_ids
        [sat_b],  # peer_satellite_ids
        ACCESS_START,
        ACCESS_END,
        constraints=None,
    )

    windows = _extract_list_from_paginated(windows_result)
    _append_markdown_block(f"compute_access_windows(ISL: {sat_a} -> {sat_b})", windows[:3] if windows else [])

    assert isinstance(windows, list)
    
    assert len(windows) > 0
    
    # Verify ISL window structure
    w0 = windows[0]
    assert "satellite_id" in w0
    assert "peer_satellite_id" in w0
    assert w0["satellite_id"] == sat_a
    assert w0["peer_satellite_id"] == sat_b
    assert w0.get("target_id") is None
    assert w0.get("station_id") is None
    
    # Stage ISL action
    start_str = w0["start"]
    start_dt = datetime.fromisoformat(start_str)
    end_dt = start_dt + timedelta(minutes=1)
    end_str = end_dt.isoformat()
    
    action = {
        "type": "intersatellite_link",
        "satellite_id": sat_a,
        "peer_satellite_id": sat_b,
        "window_id": w0["window_id"],
        "start_time": start_str,
        "end_time": end_str,
    }
    
    # Dry run
    dry = server.stage_action(action, dry_run=True)
    if dry.get("feasible") is False:
        pytest.fail(f"ISL action dry run failed: {dry.get('reason')}")
    assert dry.get("status") == "feasible" or dry.get("action_id") is not None
    
    _append_markdown_block("stage_action(ISL, dry_run=True)", dry)
    
    # Real stage
    staged = server.stage_action(action, dry_run=False)
    assert staged["status"] == "staged"
    action_id = staged["action_id"]
    
    _append_markdown_block("stage_action(ISL, dry_run=False)", staged)
    
    # Verify via query_actions
    actions = server.query_actions({"action_id": action_id}, limit=1)
    assert len(actions) == 1
    assert actions[0]["type"] == "intersatellite_link"
    assert actions[0]["peer_satellite_id"] == sat_b
    
    _append_markdown_block(f"query_actions(ISL action_id={action_id})", actions[0])
    
    if DUMP_RESPONSES:
        print(f"\nISL ACTION STAGED ({action_id}):")
        print(json.dumps(actions[0], indent=2))


def test_evaluate_revisit_gaps_mcp_tool(server_with_initial_plan_scenario):
    """Smoke-test evaluate_revisit_gaps tool."""
    server, scenario = server_with_initial_plan_scenario

    # Clear any initial plan actions and save to state file
    scenario.staged_actions.clear()
    server.STATE_FILE.write(scenario.export_to_state())

    tid = TEST_TARGET_IDS[0]

    # Just call it, no actions staged initially
    result = server.evaluate_revisit_gaps([tid])
    assert isinstance(result, list)
    assert len(result) == 1

    r = result[0]
    assert r["target_id"] == tid
    assert r["max_gap_seconds"] > 0
    assert r["coverage_count"] == 0
    
    _append_markdown_block(f"evaluate_revisit_gaps([{tid}])", result)


def test_evaluate_stereo_coverage_mcp_tool(server_with_initial_plan_scenario):
    """Smoke-test evaluate_stereo_coverage tool."""
    server, scenario = server_with_initial_plan_scenario
    
    tid = TEST_TARGET_IDS[0]
    
    result = server.evaluate_stereo_coverage([tid], min_separation_deg=15.0)
    assert isinstance(result, list)
    assert len(result) == 1
    
    r = result[0]
    assert r["target_id"] == tid
    assert r["has_stereo"] is False
    
    _append_markdown_block(f"evaluate_stereo_coverage([{tid}])", result)


def test_evaluate_polygon_coverage_mcp_tool(server_with_initial_plan_scenario):
    """Smoke-test evaluate_polygon_coverage tool."""
    server, scenario = server_with_initial_plan_scenario
    
    poly = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
    
    # 1. Empty case
    result1 = server.evaluate_polygon_coverage(poly)
    assert isinstance(result1, dict)
    assert result1["coverage_ratio"] == 0.0
    
    # 2. Mock a strip action and swath width
    from dataclasses import replace
    sat_id = TEST_SAT_IDS[0]
    real_sat = scenario.satellites[sat_id]
    mock_sat = replace(real_sat, swath_width_km=100.0)
    scenario.satellites[sat_id] = mock_sat

    scenario.register_strips([
        {"id": "mcp_poly_strip", "points": [(0.5, -0.5), (0.5, 1.5)]}
    ])

    # Manually inject action to bypass validations for test simplicity
    scenario.staged_actions["fake_mcp_action"] = type("FakeAction", (), {
        "action_id": "fake_mcp_action",
        "type": "observation",
        "satellite_id": sat_id,
        "strip_id": "mcp_poly_strip",
        "target_id": None,
        "station_id": None,
        "start_time": datetime.now(timezone.utc),
        "end_time": datetime.now(timezone.utc),
        "peer_satellite_id": None
    })()

    # Save modified scenario to state file
    server.STATE_FILE.write(scenario.export_to_state())

    result2 = server.evaluate_polygon_coverage(poly)
    assert result2["coverage_ratio"] > 0.0
    
    # Cleanup
    del scenario.staged_actions["fake_mcp_action"]
    scenario.satellites[sat_id] = real_sat
    
    _append_markdown_block("evaluate_polygon_coverage(poly)", [result1, result2])
