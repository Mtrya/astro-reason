"""Tests for SatNet state persistence."""

import os
import tempfile
from pathlib import Path

import pytest

from satnet_agent.state import SatNetState, SatNetStateFile


PROBLEMS_PATH = Path(__file__).parent.parent / "satnet" / "data" / "problems.json"
MAINTENANCE_PATH = Path(__file__).parent.parent / "satnet" / "data" / "maintenance.csv"


class TestSatNetState:
    """Test SatNetState serialization."""

    def test_to_dict_round_trip(self):
        state = SatNetState(
            problems_path="/data/problems.json",
            maintenance_path="/data/maintenance.csv",
            week=40,
            year=2018,
            action_counter=5,
            scheduled_tracks={
                "act_0001": {
                    "action_id": "act_0001",
                    "request_id": "test-request",
                    "mission_id": 521,
                    "antenna": "DSS-43",
                    "trx_on": 1538640000,
                    "trx_off": 1538647200,
                    "setup_start": 1538639940,
                    "teardown_end": 1538647215,
                    "duration_hours": 2.0,
                }
            },
        )

        data = state.to_dict()
        restored = SatNetState.from_dict(data)

        assert restored.problems_path == state.problems_path
        assert restored.maintenance_path == state.maintenance_path
        assert restored.week == state.week
        assert restored.year == state.year
        assert restored.action_counter == state.action_counter
        assert restored.scheduled_tracks == state.scheduled_tracks


class TestSatNetStateFile:
    """Test SatNetStateFile I/O and locking."""

    def test_write_and_read(self, tmp_path):
        state_path = tmp_path / "state.json"
        state_file = SatNetStateFile(state_path)

        state = SatNetState(
            problems_path="/data/problems.json",
            maintenance_path="/data/maintenance.csv",
            week=40,
            year=2018,
            action_counter=3,
            scheduled_tracks={},
        )

        with state_file.lock(exclusive=True):
            state_file.write(state)

        with state_file.lock(exclusive=False):
            loaded = state_file.read()

        assert loaded is not None
        assert loaded.week == 40
        assert loaded.action_counter == 3

    def test_initialize(self, tmp_path):
        state_path = tmp_path / "state.json"
        state_file = SatNetStateFile(state_path)

        state_file.initialize(
            problems_path="/data/problems.json",
            maintenance_path="/data/maintenance.csv",
            week=30,
            year=2018,
        )

        state = state_file.read()
        assert state is not None
        assert state.week == 30
        assert state.action_counter == 0
        assert state.scheduled_tracks == {}

    def test_read_nonexistent_returns_none(self, tmp_path):
        state_path = tmp_path / "nonexistent.json"
        state_file = SatNetStateFile(state_path)

        assert state_file.read() is None

    def test_exists(self, tmp_path):
        state_path = tmp_path / "state.json"
        state_file = SatNetStateFile(state_path)

        assert not state_file.exists()
        state_file.initialize("/a", "/b", 40)
        assert state_file.exists()


class TestScenarioStatePersistence:
    """Test SatNetScenario to_state/from_state round-trip."""

    @pytest.mark.skipif(
        not PROBLEMS_PATH.exists(),
        reason="SatNet data files not available"
    )
    def test_empty_scenario_round_trip(self):
        from satnet_agent import SatNetScenario

        scenario = SatNetScenario(
            problems_path=str(PROBLEMS_PATH),
            maintenance_path=str(MAINTENANCE_PATH),
            week=40,
            year=2018,
        )

        state = scenario.to_state()
        restored = SatNetScenario.from_state(state)

        assert restored.week == scenario.week
        assert restored.year == scenario.year
        assert len(restored._scheduled_tracks) == 0
        assert restored._action_counter == 0

    @pytest.mark.skipif(
        not PROBLEMS_PATH.exists(),
        reason="SatNet data files not available"
    )
    def test_scenario_with_tracks_round_trip(self):
        from satnet_agent import SatNetScenario

        scenario = SatNetScenario(
            problems_path=str(PROBLEMS_PATH),
            maintenance_path=str(MAINTENANCE_PATH),
            week=40,
            year=2018,
        )

        requests = scenario.list_unsatisfied_requests()
        req = requests[0]

        windows = scenario.find_view_periods(req.request_id, min_duration_hours=0.5)
        window = windows[0]

        duration_secs = min(int(req.remaining_hours * 3600), int(window.duration_hours * 3600))
        trx_off = window.start_seconds + duration_secs

        result = scenario.schedule_track(
            request_id=req.request_id,
            antenna=window.antenna,
            trx_on=window.start_seconds,
            trx_off=trx_off,
        )

        original_remaining = scenario._requests[req.request_id].remaining_hours

        state = scenario.to_state()
        restored = SatNetScenario.from_state(state)

        assert len(restored._scheduled_tracks) == 1
        assert result.action_id in restored._scheduled_tracks
        assert restored._action_counter == scenario._action_counter
        assert restored._requests[req.request_id].remaining_hours == original_remaining

        restored_track = restored._scheduled_tracks[result.action_id]
        assert restored_track.request_id == req.request_id
        assert restored_track.antenna == window.antenna
