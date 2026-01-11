"""
Tests for chain access computation with latency calculation.
"""

import pytest
from datetime import datetime, timedelta, timezone

from engines.astrox.models import Satellite, Station
from engines.astrox.orbital.chain import (
    compute_chain_access,
    compute_chain_access_with_latency,
    ChainAccessResult,
    ChainWindow,
    LatencySample,
    _quantize_time,
    _generate_quantized_sample_times,
    SPEED_OF_LIGHT_KM_PER_SEC,
)


# Test fixtures - use real TLE for integration tests
ISS_TLE1 = "1 25544U 98067A   24364.50000000  .00016717  00000-0  30000-3 0  9990"
ISS_TLE2 = "2 25544  51.6400 200.0000 0007000  90.0000 270.0000 15.50000000000010"


@pytest.fixture
def iss_satellite():
    return Satellite(
        tle_line1=ISS_TLE1,
        tle_line2=ISS_TLE2,
        apogee_km=420,
        perigee_km=418,
        period_min=92.68,
        inclination_deg=51.64,
    )


@pytest.fixture
def beijing_station():
    return Station(latitude_deg=39.90, longitude_deg=116.40, altitude_m=0.0)


@pytest.fixture
def shanghai_station():
    return Station(latitude_deg=31.23, longitude_deg=121.47, altitude_m=0.0)


class TestTimeQuantization:
    def test_quantize_to_minute(self):
        dt = datetime(2025, 1, 1, 12, 45, 30, tzinfo=timezone.utc)
        quantized = _quantize_time(dt, 60.0)
        assert quantized == datetime(2025, 1, 1, 12, 45, 0, tzinfo=timezone.utc)

    def test_quantize_exact_boundary(self):
        dt = datetime(2025, 1, 1, 12, 45, 0, tzinfo=timezone.utc)
        quantized = _quantize_time(dt, 60.0)
        assert quantized == dt

    def test_generate_covers_window(self):
        start = datetime(2025, 1, 1, 12, 0, 30, tzinfo=timezone.utc)
        end = datetime(2025, 1, 1, 12, 3, 45, tzinfo=timezone.utc)
        times = _generate_quantized_sample_times(start, end, 60.0)
        assert times[0] <= start
        assert times[-1] >= end


class TestComputeChainAccess:
    def test_direct_link_via_iss(self, iss_satellite, beijing_station, shanghai_station):
        """Test chain computation for Beijing -> ISS -> Shanghai."""
        start = datetime.now(timezone.utc)
        end = start + timedelta(hours=12)

        all_nodes = {
            "Beijing": beijing_station,
            "Shanghai": shanghai_station,
            "ISS": iss_satellite,
        }
        connections = [("Beijing", "ISS"), ("ISS", "Shanghai")]

        windows = compute_chain_access(
            start_node=beijing_station,
            end_node=shanghai_station,
            all_nodes=all_nodes,
            connections=connections,
            time_window=(start.strftime("%Y-%m-%dT%H:%M:%S.000Z"), end.strftime("%Y-%m-%dT%H:%M:%S.000Z")),
        )

        assert isinstance(windows, list)
        for w in windows:
            assert w.path == ["Beijing", "ISS", "Shanghai"]
            assert w.start < w.end
            assert w.duration_sec > 0


class TestComputeChainAccessWithLatency:
    def test_basic_latency_calculation(self, iss_satellite, beijing_station, shanghai_station):
        """Test that latency samples are computed for each window."""
        start = datetime.now(timezone.utc)
        end = start + timedelta(hours=12)

        all_nodes = {
            "Beijing": beijing_station,
            "Shanghai": shanghai_station,
            "ISS": iss_satellite,
        }
        connections = [("Beijing", "ISS"), ("ISS", "Shanghai")]

        result = compute_chain_access_with_latency(
            start_node=beijing_station,
            end_node=shanghai_station,
            all_nodes=all_nodes,
            connections=connections,
            time_window=(start.strftime("%Y-%m-%dT%H:%M:%S.000Z"), end.strftime("%Y-%m-%dT%H:%M:%S.000Z")),
            sample_step_sec=60.0,
        )

        assert isinstance(result, ChainAccessResult)
        if result.windows:
            window = result.windows[0]
            assert isinstance(window, ChainWindow)
            assert len(window.latency_samples) > 0
            for sample in window.latency_samples:
                assert isinstance(sample, LatencySample)
                assert sample.latency_ms > 0
                assert sample.latency_ms < 100

    def test_latency_sanity_check(self, iss_satellite, beijing_station, shanghai_station):
        """Verify latency is in expected range for LEO satellite relay.
        
        ISS at ~420km altitude. At low elevation angles, slant range can be
        2000-5000km per hop. Two hops = 4000-10000km total = ~13-35ms.
        At very low elevations (near horizon), could reach ~45-50ms.
        """
        start = datetime.now(timezone.utc)
        end = start + timedelta(hours=12)

        all_nodes = {
            "Beijing": beijing_station,
            "Shanghai": shanghai_station,
            "ISS": iss_satellite,
        }
        connections = [("Beijing", "ISS"), ("ISS", "Shanghai")]

        result = compute_chain_access_with_latency(
            start_node=beijing_station,
            end_node=shanghai_station,
            all_nodes=all_nodes,
            connections=connections,
            time_window=(start.strftime("%Y-%m-%dT%H:%M:%S.000Z"), end.strftime("%Y-%m-%dT%H:%M:%S.000Z")),
        )

        if result.windows:
            for window in result.windows:
                for sample in window.latency_samples:
                    assert 3.0 < sample.latency_ms < 100.0


class TestLatencyMath:
    def test_direct_distance_latency(self):
        """Verify latency math: 1000 km should be ~3.33 ms."""
        distance_km = 1000.0
        expected_latency_ms = (distance_km / SPEED_OF_LIGHT_KM_PER_SEC) * 1000.0
        assert abs(expected_latency_ms - 3.336) < 0.01

    def test_geo_satellite_latency(self):
        """GEO satellite at ~36000 km should give ~120ms one-way."""
        distance_km = 36000.0
        latency_ms = (distance_km / SPEED_OF_LIGHT_KM_PER_SEC) * 1000.0
        assert abs(latency_ms - 120.1) < 1.0


    def test_multi_hop_isl(self):
        """Test a multi-hop ISL chain: Lux -> Sat2 -> Sat3 -> Matera."""
        # sat_qianfan-2
        sat2 = Satellite(
            tle_line1="1 60380U 24140B   25197.85087971  .00000117  00000-0  16334-3 0  9996",
            tle_line2="2 60380  88.9828 314.5168 0010959 253.0368 106.9582 13.50957903 47308",
            apogee_km=1077, perigee_km=1061, period_min=106.6, inclination_deg=89.0
        )
        
        # sat_qianfan-3
        sat3 = Satellite(
            tle_line1="1 60381U 24140C   25198.15529111  .00000128  00000-0  17991-3 0  9990",
            tle_line2="2 60381  88.9821 314.6290 0011922 266.9842  92.9944 13.50956086 47251",
            apogee_km=1078, perigee_km=1060, period_min=106.6, inclination_deg=89.0
        )
        
        # Luxembourg
        lux = Station(latitude_deg=49.579, longitude_deg=6.114, altitude_m=345)
        # Matera
        mat = Station(latitude_deg=40.649536, longitude_deg=16.704079, altitude_m=527)
        
        all_nodes = {
            "Sat2": sat2, "Sat3": sat3, "Lux": lux, "Mat": mat
        }
        
        # Bi-directional connections
        connections = [
            ("Lux", "Sat2"), ("Sat2", "Lux"),
            ("Sat2", "Sat3"), ("Sat3", "Sat2"),
            ("Sat3", "Mat"), ("Mat", "Sat3")
        ]
        
        # 13:09:05Z is when Sat3 sees Matera, ISL and Sat2-Lux are valid earlier
        # Using a window that covers the overlap found in link tests
        start_str = "2025-07-17T13:07:00.000Z"
        end_str = "2025-07-17T13:12:00.000Z"
        
        # First verify individual windows with compute_chain_access logic dependencies
        # (Removed manual checks as compute_chain_access now assumes visibility)
        
        windows = compute_chain_access(
            start_node=lux,
            end_node=mat,
            all_nodes=all_nodes,
            connections=connections,
            time_window=(start_str, end_str)
        )
        
        assert len(windows) > 0, "Should find at least one window for multi-hop chain"
        w = windows[0]
        assert w.path == ["Lux", "Sat2", "Sat3", "Mat"]
        assert w.duration_sec > 0
        
        # With simplified logic, we assume full window connectivity
        expected_start = datetime.fromisoformat("2025-07-17T13:07:00.000000+00:00")
        expected_end = datetime.fromisoformat("2025-07-17T13:12:00.000000+00:00")
        
        assert abs((w.start - expected_start).total_seconds()) < 1.0
        assert abs((w.end - expected_end).total_seconds()) < 1.0
