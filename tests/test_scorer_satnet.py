"""Tests for the official SatNet Scorer."""

import json
import tempfile
from pathlib import Path
import pytest
import numpy as np

from satnet_agent.scorer import (
    initialize_simulator,
    replay_schedule,
    score_plan,
    SatNetScore,
)

TEST_WEEK = 40
PROBLEMS_PATH = "satnet/data/problems.json"
MAINTENANCE_PATH = "satnet/data/maintenance.csv"


@pytest.fixture
def sim():
    """Create a fresh simulator instance for each test."""
    return initialize_simulator(week=TEST_WEEK)


@pytest.fixture
def temp_schedule_path():
    """Provide a temporary file path for schedules."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    yield path
    Path(path).unlink(missing_ok=True)


def test_initialize_simulator():
    """Test that simulator initializes correctly."""
    sim = initialize_simulator(week=TEST_WEEK)
    assert sim is not None
    assert sim.start_date is not None
    assert sim.num_requests > 0


def test_load_empty_schedule(temp_schedule_path):
    """Test loading an empty schedule JSON."""
    with open(temp_schedule_path, "w") as f:
        json.dump([], f)
    
    score = score_plan(temp_schedule_path, week=TEST_WEEK)
    assert score.requests_satisfied == 0
    assert score.valid == True
    assert len(score.errors) == 0


def test_replay_empty_schedule(sim):
    """Test replaying an empty schedule."""
    errors = replay_schedule(sim, [])
    assert len(errors) == 0


def test_score_empty_plan(temp_schedule_path):
    """Test scoring a completely empty plan."""
    with open(temp_schedule_path, "w") as f:
        json.dump([], f)
    
    score = score_plan(temp_schedule_path, week=TEST_WEEK)
    
    # Should be valid but have poor request satisfaction
    assert score.valid == True
    assert score.requests_satisfied == 0
    assert score.u_max > 0
    assert score.hours_allocated == 0


def test_schedule_and_score_single_track(temp_schedule_path):
    """End-to-end test: Create a track with scenario, save it, and score it."""
    # 1. Create a minimal plan with 1 track
    from satnet_agent.scenario import SatNetScenario
    scenario = SatNetScenario(PROBLEMS_PATH, MAINTENANCE_PATH, TEST_WEEK)
    
    requests = scenario.list_unsatisfied_requests()
    req = requests[0]
    vps = scenario.find_view_periods(req.request_id, min_duration_hours=0.5)
    vp = vps[0]
    
    trx_on = vp.start_seconds
    track_duration = min(req.remaining_hours, vp.duration_hours)
    trx_off = trx_on + int(track_duration * 3600)
    
    scenario.schedule_track(req.request_id, vp.antenna, trx_on, trx_off)
    scenario.commit_plan(output_path=temp_schedule_path)
    
    # 2. Score the plan
    score = score_plan(temp_schedule_path, week=TEST_WEEK)
    
    assert score.valid == True
    assert score.hours_allocated > 0
    assert score.requests_satisfied > 0  # At least one request satisfied


def test_schedule_multiple_tracks_and_score(temp_schedule_path):
    """Test scoring a plan with multiple tracks."""
    from satnet_agent.scenario import SatNetScenario
    scenario = SatNetScenario(PROBLEMS_PATH, MAINTENANCE_PATH, TEST_WEEK)
    
    # Schedule first two requests
    for i in range(2):
        requests = scenario.list_unsatisfied_requests()
        req = requests[i]
        vps = scenario.find_view_periods(req.request_id, min_duration_hours=0.5)
        # Avoid conflict by picking different antennas if possible, or just checking simple availability
        # For simplicity, just pick first valid one
        vp = vps[0]
        trx_on = vp.start_seconds
        track_duration = min(req.remaining_hours, vp.duration_hours)
        trx_off = trx_on + int(track_duration * 3600)
        
        try:
            scenario.schedule_track(req.request_id, vp.antenna, trx_on, trx_off)
        except Exception:
            continue # Skip if conflict for this simple test
            
    scenario.commit_plan(output_path=temp_schedule_path)
    
    score = score_plan(temp_schedule_path, week=TEST_WEEK)
    assert score.valid == True
    assert score.hours_allocated > 0


def test_scorer_detects_invalid_track():
    """Test that scorer detects an invalid track configuration."""
    sim = initialize_simulator(week=TEST_WEEK)
    
    invalid_schedule = [{
        "RESOURCE": "DSS-14",
        "SC": 999999,  # Non-existent spacecraft
        "START_TIME": int(sim.start_date) + 1000,
        "TRACKING_ON": int(sim.start_date) + 1000,
        "TRACKING_OFF": int(sim.start_date) + 5000,
        "END_TIME": int(sim.start_date) + 5000,
        "TRACK_ID": "nonexistent_track",
    }]
    
    errors = replay_schedule(sim, invalid_schedule)
    assert len(errors) > 0  # Should have errors for invalid track


def test_score_plan_returns_correct_structure(temp_schedule_path):
    """Test that SatNetScore object has all expected fields populated."""
    with open(temp_schedule_path, "w") as f:
        json.dump([], f)
        
    score = score_plan(temp_schedule_path, week=TEST_WEEK)
    
    assert isinstance(score, SatNetScore)
    assert isinstance(score.u_max, float)
    assert isinstance(score.u_rms, float)
    assert isinstance(score.requests_satisfied, int)
    assert isinstance(score.valid, bool)
    assert isinstance(score.errors, list)


def test_scorer_handles_split_multi_antenna_tracks(temp_schedule_path):
    """
    Test that the scorer correctly handles multi-antenna tracks that are split 
    into separate entries in the JSON (like in fair_schedule.json).
    Target track: 35495ac9-7-1 requires split antennas.
    """
    # From fair_schedule.json analysis:
    # Track 35495ac9-7-1 needs multiple antennas (e.g. DSS-54_DSS-65)
    
    sim = initialize_simulator(week=TEST_WEEK)
    
    # Use the exact times from fair_schedule.json which we know are valid
    # Start: 1538391674 (setup)
    # On: 1538393474
    # Off: 1538429474
    # End: 1538430374
    
    split_schedule = [
        {
            "RESOURCE": "DSS-54",
            "SC": 648,
            "START_TIME": 1538391674,
            "TRACKING_ON": 1538393474,
            "TRACKING_OFF": 1538429474,
            "END_TIME": 1538430374,
            "TRACK_ID": "35495ac9-7-1"
        },
        {
            "RESOURCE": "DSS-65",
            "SC": 648,
            "START_TIME": 1538391674,
            "TRACKING_ON": 1538393474,
            "TRACKING_OFF": 1538429474,
            "END_TIME": 1538430374,
            "TRACK_ID": "35495ac9-7-1"
        }
    ]
    
    with open(temp_schedule_path, "w") as f:
        json.dump(split_schedule, f)
        
    score = score_plan(temp_schedule_path, week=TEST_WEEK)
    
    # This specific track configuration is known to be valid
    assert score.valid == True
    assert len(score.errors) == 0

