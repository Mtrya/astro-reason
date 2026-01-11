
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone
from engines.astrox.orbital.attitude import calculate_quaternion_series, quaternion_eci_to_ecef

# Mock data
TLE1 = "1 25544U 98067A   21159.48833119  .00001095  00000-0  28172-4 0  9993"
TLE2 = "2 25544  51.6441 213.6163 0003461 144.1706 339.6975 15.48842144287955"

@pytest.fixture
def mock_propagate():
    with patch("engines.astrox.orbital.attitude.propagate_satellite") as m:
        yield m

@pytest.fixture
def mock_lla_to_eci():
    with patch("engines.astrox.orbital.attitude.lla_to_eci") as m:
        yield m

def test_strip_attitude_forward(mock_propagate, mock_lla_to_eci):
    """
    Test strip attitude logic for a forward pass (Head->Tail).
    Geometry:
      Sat Pos: (0, 0, 10)
      Sat Vel: (0, 1, 0)  -> Moving +Y
      Head: (0, 5, 0)
      Tail: (0, 15, 0)
      Vector H->T: (0, 10, 0). Dot(Vel, H->T) = 10 > 0. Forward.
      
    Expectation:
      t=Start -> Look at Head (0, 5, 0)
      t=Mid   -> Look at Mid (0, 10, 0)
      t=End   -> Look at Tail (0, 15, 0)
    """
    start_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    duration = 100  # seconds
    end_time = start_time + timedelta(seconds=duration)
    mid_time = start_time + timedelta(seconds=duration/2)
    
    time_points = [start_time, mid_time, end_time]
    
    # Mock Propagation: Constant position/velocity for simplicity
    # Note: propagate_satellite is called twice (one for output times, one for direction check)
    # We return the same state for all calls
    sat_pos = [0.0, 0.0, 10.0]
    sat_vel = [0.0, 1.0, 0.0]
    
    # propagate_satellite returns list of (pos, vel)
    # It will be called with list of times. We just return matching length list.
    def side_effect(t1, t2, times):
        return [(sat_pos, sat_vel) for _ in times]
    mock_propagate.side_effect = side_effect
    
    # Mock lla_to_eci
    # Map (lat, lon) to Cartesian
    # Head: (0, 0) -> (0, 5, 0)
    # Tail: (10, 0) -> (0, 15, 0)
    # Mid: (5, 0) -> (0, 10, 0)
    def lla_side_effect(lat, lon, alt, t):
        if lat == 0 and lon == 0: return [0.0, 5.0, 0.0]
        if lat == 10 and lon == 0: return [0.0, 15.0, 0.0]
        # Linear interp of lat/lon from _sample_polyline
        # Midpoint of (0,0) and (10,0) is (5,0)
        if abs(lat - 5.0) < 0.001 and lon == 0: return [0.0, 10.0, 0.0]
        return [0.0, 0.0, 0.0]
    mock_lla_to_eci.side_effect = lla_side_effect
    
    head_pt = (0.0, 0.0)
    tail_pt = (10.0, 0.0)
    strip_points = [head_pt, tail_pt]
    
    strip_actions = [(start_time, end_time, strip_points)]
    
    quats = calculate_quaternion_series(
        TLE1, TLE2,
        target_obs_actions=[],
        strip_obs_actions=strip_actions,
        time_points=time_points
    )
    
    assert len(quats) == 3
    
    # Helper to rotate vector by quaternion
    def rotate_vector(q, v):
        # q * v * q_conj
        # v is pure quaternion (x, y, z, 0)
        # implementation skipped, check result behavior
        pass
    
    # We can check q directly or check derived direction
    # Here we trust calculate_quaternion_series calls _look_at_quaternion with correct target
    # We can verify _look_at_quaternion calls by checking what lla_to_eci was called with at each time
    
    # We expect lla_to_eci to be called with:
    # 1. Head/Tail for direction check (at start_time)
    # 2. t=Start: Head (0,0)
    # 3. t=Mid: Mid (5,0)
    # 4. t=End: Tail (10,0)
    
    # Verify calls to lla_to_eci
    # Note: calls 1 & 2 might be same time, but Python mock stores all calls
    
    # Filter calls that happened during the loop (output generation)
    # The output generation loop calls lla_to_eci with the interpolated lat/lon
    
    # Collect (lat, lon) args from calls
    calls = mock_lla_to_eci.call_args_list
    
    # The first 2 calls are for direction check: Head and Tail
    # We expect (0, 0, 0, start_time) and (10, 0, 0, start_time)
    
    # Subsequent calls are for the loop
    # Call for t=Start: Should normally close to Head
    # Call for t=Mid: Should be close to (5, 0)
    # Call for t=End: Should be close to Tail
    
    lat_args = [args[0] for args, kwargs in calls]
    
    # Check strict values
    # Direction check
    assert 0.0 in lat_args 
    assert 10.0 in lat_args 
    assert 5.0 in lat_args
    
    # Check sequence roughly
    # We want to ensure 5.0 (Mid) was requested
    assert abs(lat_args[-2] - 5.0) < 0.001 # 2nd to last call (Mid)
    assert abs(lat_args[-1] - 10.0) < 0.001 # Last call (End) or close
    
    # Actually, let's just inspect the calls corresponding to main loop
    # main loop has 3 points.
    loop_calls = calls[-3:] 
    
    # Start: (0,0)
    assert abs(loop_calls[0][0][0] - 0.0) < 0.001
    # Mid: (5,0)
    assert abs(loop_calls[1][0][0] - 5.0) < 0.001
    # End: (10,0)
    assert abs(loop_calls[2][0][0] - 10.0) < 0.001


def test_strip_attitude_backward(mock_propagate, mock_lla_to_eci):
    """
    Test strip attitude logic for a backward pass (Tail->Head).
    Geometry:
      Sat Pos: (0, 0, 10)
      Sat Vel: (0, -1, 0)  -> Moving -Y
      Head: (0, 5, 0)
      Tail: (0, 15, 0)
      Vector H->T: (0, 10, 0). Dot(Vel, H->T) = -10 < 0. Backward.
      
    Expectation:
      t=Start -> Look at Tail (0, 15, 0)
      t=Mid   -> Look at Mid (0, 10, 0)
      t=End   -> Look at Head (0, 5, 0)
    """
    start_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    duration = 100
    end_time = start_time + timedelta(seconds=duration)
    mid_time = start_time + timedelta(seconds=duration/2)
    time_points = [start_time, mid_time, end_time]
    
    sat_pos = [0.0, 0.0, 10.0]
    sat_vel = [0.0, -1.0, 0.0] # Moving -Y
    
    mock_propagate.side_effect = lambda t1, t2, times: [(sat_pos, sat_vel) for _ in times]
    
    def lla_side_effect(lat, lon, alt, t):
        if lat == 0 and lon == 0: return [0.0, 5.0, 0.0]
        if lat == 10 and lon == 0: return [0.0, 15.0, 0.0]
        if abs(lat - 5.0) < 0.001 and lon == 0: return [0.0, 10.0, 0.0]
        return [0.0, 0.0, 0.0]
    mock_lla_to_eci.side_effect = lla_side_effect
    
    head_pt = (0.0, 0.0)
    tail_pt = (10.0, 0.0)
    strip_points = [head_pt, tail_pt]
    
    strip_actions = [(start_time, end_time, strip_points)]
    
    quats = calculate_quaternion_series(
        TLE1, TLE2,
        target_obs_actions=[],
        strip_obs_actions=strip_actions,
        time_points=time_points
    )
    
    calls = mock_lla_to_eci.call_args_list
    loop_calls = calls[-3:]
    
    # Backward pass means:
    # Start -> Tail (10.0)
    assert abs(loop_calls[0][0][0] - 10.0) < 0.001
    
    # Mid -> Mid (5.0)
    assert abs(loop_calls[1][0][0] - 5.0) < 0.001
    
    # End -> Head (0.0)
    assert abs(loop_calls[2][0][0] - 0.0) < 0.001
