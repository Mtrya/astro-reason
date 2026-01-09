"""Main interface between MCP server and physics engine.

This module provides the Scenario class, which is the central interface for all
planning operations. It returns typed dataclass objects and raises exceptions
on errors.
"""

from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Tuple, Union

from engine.orbital.access import compute_accessibility, compute_strip_accessibility
from engine.orbital.lighting import compute_lighting_windows as engine_lighting
from engine.orbital.ephemeris import compute_ground_track
from engine.orbital.chain import compute_chain_access_with_latency, ChainAccessResult
from engine.models import RangeConstraint, ElevationAngleConstraint
from engine.analytics import compute_revisit_stats, compute_stereo_compliance, compute_polygon_coverage
from engine.resources.power import simulate_power
from engine.resources.storage import simulate_storage
from engine.resources.common import simulate_resource_curve
from engine.temporal import format_for_astrox, parse_iso
from engine.orbital.attitude import calculate_quaternion_series, calculate_pointing_quaternion

from planner.models import (
    PlannerAction,
    PlannerSatellite,
    PlannerTarget,
    PlannerStation,
    PlannerStrip,
    PlannerAccessWindow,
    PlannerLightingWindow,
    SatelliteMetrics,
    PlanMetrics,
    Violation,
    PlanStatus,
    StageResult,
    UnstageResult,
    CommitResult,
    GroundTrackPoint,
    RevisitAnalysis,
    StereoAnalysis,
    PolygonCoverageAnalysis,
    ObservationInfo,
    GridCell,
    ScenarioError,
    ValidationError,
    ConflictError,
    ResourceViolationError,
)
from planner.helpers import (
    check_time_conflicts,
    format_conflict_message,
    get_storage_params,
    get_power_params,
    convert_to_power_events,
    convert_to_storage_events,
    check_power_capacity,
    check_storage_capacity,
    export_plan_to_json,
    parse_constraints,
    parse_action,
    validate_action_feasibility,
)
from planner.helpers.data_registry import (
    load_satellites,
    load_targets,
    load_stations,
    load_plan,
    load_horizon,
    to_engine_satellite,
    to_engine_station,
    to_engine_target,
)


def _generate_time_points(start: datetime, end: datetime, step_minutes: int = 5) -> List[datetime]:
    """Generate evenly spaced time points within a range."""
    points = []
    current = start
    step = timedelta(minutes=step_minutes)
    while current <= end:
        points.append(current)
        current += step
    return points


class Scenario:
    """
    Persistent state container for satellite mission planning.

    Returns typed dataclass objects. Raises exceptions on errors.
    MCP layer handles pagination, filtering, and LLM formatting.
    """

    def __init__(self, satellite_file: str, target_file: str, station_file: str, plan_file: str):
        self.satellites: Dict[str, PlannerSatellite] = load_satellites(satellite_file)
        self.targets: Dict[str, PlannerTarget] = load_targets(target_file)
        self.stations: Dict[str, PlannerStation] = load_stations(station_file)

        self.initial_plan: Dict[str, PlannerAction] = load_plan(plan_file)
        self.staged_actions: Dict[str, PlannerAction] = self.initial_plan.copy()
        
        self.horizon_start, self.horizon_end = load_horizon(plan_file)
        self._time_points: List[datetime] = _generate_time_points(self.horizon_start, self.horizon_end)

        self.windows: Dict[str, PlannerAccessWindow] = {}
        self._window_counter = 0

        self.strips: Dict[str, PlannerStrip] = {}

        # Metrics Cache: sat_id -> (action_signature_hash, SatelliteMetrics)
        self._metrics_cache: Dict[str, Tuple[int, SatelliteMetrics]] = {}

        # Quaternion Cache: action_id -> (start_quat, end_quat)
        self._quaternion_cache: Dict[str, Tuple[Tuple[float, float, float, float], Tuple[float, float, float, float]]] = {}

    # ==========================================================================
    # Query Methods (Read-Only) - Return ALL records as typed objects
    # ==========================================================================

    def query_satellites(self) -> List[PlannerSatellite]:
        """Get all available satellites."""
        return list(self.satellites.values())

    def query_targets(self) -> List[PlannerTarget]:
        """Get all available targets."""
        return list(self.targets.values())

    def query_stations(self) -> List[PlannerStation]:
        """Get all available ground stations."""
        return list(self.stations.values())

    def query_windows(self) -> List[PlannerAccessWindow]:
        """Get all registered access windows."""
        return list(self.windows.values())

    def query_actions(self) -> List[PlannerAction]:
        """Get all staged actions."""
        return list(self.staged_actions.values())

    def query_strips(self) -> List[PlannerStrip]:
        """Get all registered strips."""
        return list(self.strips.values())

    # ==========================================================================
    # Strip Management
    # ==========================================================================

    def register_strips(self, strips: List[Dict[str, Any]]) -> List[PlannerStrip]:
        """Register strip targets from a list of dicts."""
        registered = []
        for strip_data in strips:
            strip = PlannerStrip(
                id=strip_data["id"],
                name=strip_data.get("name", strip_data["id"]),
                points=strip_data["points"],
            )
            self.strips[strip.id] = strip
            registered.append(strip)
        return registered

    def unregister_strips(self, strip_ids: List[str]) -> None:
        """Remove strips from the scenario."""
        for strip_id in strip_ids:
            if strip_id in self.strips:
                del self.strips[strip_id]

    def compute_strip_windows(
        self,
        sat_ids: List[str],
        strip_ids: List[str],
        start_time: str | None = None,
        end_time: str | None = None,
        constraints: List[Any] | None = None,
    ) -> List[PlannerAccessWindow]:
        """Compute access windows for strip targets."""
        start_dt = parse_iso(start_time) if start_time else self.horizon_start
        end_dt = parse_iso(end_time) if end_time else self.horizon_end
        parsed_constraints = parse_constraints(constraints)

        formatted_start = format_for_astrox(start_dt)
        formatted_end = format_for_astrox(end_dt)

        planner_windows: List[PlannerAccessWindow] = []
        for sat_id in sat_ids:
            sat = self.satellites[sat_id]
            engine_sat = to_engine_satellite(sat)

            for strip_id in strip_ids:
                strip = self.strips[strip_id]
                engine_windows = compute_strip_accessibility(
                    engine_sat,
                    strip.points,
                    (formatted_start, formatted_end),
                    constraints=parsed_constraints,
                )
                for ew in engine_windows:
                    pw = PlannerAccessWindow.from_engine_window(
                        ew, sat_id, strip_id=strip_id
                    )
                    planner_windows.append(pw)

        return planner_windows

    # ==========================================================================
    # Window Registration
    # ==========================================================================

    def register_windows(self, windows: List[PlannerAccessWindow]) -> List[PlannerAccessWindow]:
        """Register windows with auto-assigned IDs. Auto-register the reverse windows if intersatellite windows."""
        from dataclasses import replace
        registered = []
        for window in windows:
            win = window
            if win.window_id is None:
                self._window_counter += 1
                win_id = f"win_{self._window_counter:03d}"
                win = replace(win, window_id=win_id)
            self.windows[win.window_id] = win
            registered.append(win)
            
            if win.peer_satellite_id:
                reverse_win = replace(win, satellite_id=win.peer_satellite_id, peer_satellite_id=win.satellite_id)
                if reverse_win not in self.windows:
                    self._window_counter += 1
                    win_id = f"win_{self._window_counter:03d}"
                    reverse_win = replace(reverse_win, window_id=win_id)
                    self.windows[reverse_win.window_id] = reverse_win
                registered.append(reverse_win)
        return registered

    # ==========================================================================
    # Compute Methods - Return typed objects, DO NOT auto-register
    # ==========================================================================

    def _generate_action_signature(self, actions: List[PlannerAction]) -> int:
        """Generate a hash signature for a list of actions."""
        # Sort by action_id to ensure deterministic order (action_id is unique)
        # Using a tuple of (action_id, start_time, end_time, type, target/station) to be safe
        sorted_actions = sorted(actions, key=lambda a: a.action_id)
        
        sig_items = []
        for a in sorted_actions:
            sig_items.append((
                a.action_id,
                a.type,
                a.satellite_id,
                a.target_id,
                a.station_id,
                a.start_time.timestamp(),
                a.end_time.timestamp()
            ))
        return hash(tuple(sig_items))

    def compute_access_windows(
        self,
        sat_ids: List[str],
        target_ids: List[str] | None = None,
        station_ids: List[str] | None = None,
        peer_satellite_ids: List[str] | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        constraints: List[Any] | None = None,
    ) -> List[PlannerAccessWindow]:
        """Compute access windows between satellites and targets/stations/satellites."""
        start_dt = parse_iso(start_time) if start_time else self.horizon_start
        end_dt = parse_iso(end_time) if end_time else self.horizon_end
        parsed_constraints = parse_constraints(constraints)

        formatted_start = format_for_astrox(start_dt)
        formatted_end = format_for_astrox(end_dt)

        planner_windows: List[PlannerAccessWindow] = []
        for sat_id in sat_ids:
            sat = self.satellites[sat_id]
            engine_sat = to_engine_satellite(sat)

            if target_ids:
                for target_id in target_ids:
                    target = self.targets[target_id]
                    engine_target = to_engine_target(target)
                    engine_windows = compute_accessibility(
                        engine_sat,
                        engine_target,
                        (formatted_start, formatted_end),
                        constraints=parsed_constraints,
                    )
                    for ew in engine_windows:
                        pw = PlannerAccessWindow.from_engine_window(
                            ew, sat_id, target_id=target_id, station_id=None, peer_satellite_id=None,
                        )
                        planner_windows.append(pw)

            if station_ids:
                for station_id in station_ids:
                    station = self.stations[station_id]
                    engine_station = to_engine_station(station)
                    engine_windows = compute_accessibility(
                        engine_sat,
                        engine_station,
                        (formatted_start, formatted_end),
                        constraints=parsed_constraints,
                    )
                    for ew in engine_windows:
                        pw = PlannerAccessWindow.from_engine_window(
                            ew, sat_id, target_id=None, station_id=station_id, peer_satellite_id=None,
                        )
                        planner_windows.append(pw)

            if peer_satellite_ids:
                for peer_sat_id in peer_satellite_ids:
                    if peer_sat_id == sat_id:
                        continue
                    
                    peer_sat = self.satellites[peer_sat_id]
                    engine_peer_sat = to_engine_satellite(peer_sat)
                    
                    engine_windows = compute_accessibility(
                        engine_sat,
                        engine_peer_sat,
                        (formatted_start, formatted_end),
                        constraints=parsed_constraints,
                    )
                    
                    for ew in engine_windows:
                        pw = PlannerAccessWindow.from_engine_window(
                            ew, sat_id, target_id=None, station_id=None, peer_satellite_id=peer_sat_id
                        )
                        planner_windows.append(pw)

        return planner_windows

    def compute_lighting_windows(
        self,
        sat_ids: List[str],
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> List[PlannerLightingWindow]:
        """Compute lighting windows for satellites (includes SUNLIGHT, PENUMBRA, UMBRA)."""
        start_dt = parse_iso(start_time) if start_time else self.horizon_start
        end_dt = parse_iso(end_time) if end_time else self.horizon_end

        results: List[PlannerLightingWindow] = []
        for sat_id in sat_ids:
            sat = self.satellites[sat_id]
            engine_sat = to_engine_satellite(sat)
            windows = engine_lighting(engine_sat, (start_dt, end_dt))
            for w in windows:
                results.append(PlannerLightingWindow.from_engine_window(w, sat_id))
        return results

    def get_ground_track(
        self,
        satellite_id: str,
        start_time: str | None = None,
        end_time: str | None = None,
        step_sec: float = 60.0,
        filter_polygon: List[Tuple[float, float]] | None = None,
    ) -> List[GroundTrackPoint]:
        """
        Compute satellite ground track (subsatellite points).
        
        Args:
            satellite_id: ID of satellite to compute ground track for
            start_time: Start time (ISO format), defaults to horizon start
            end_time: End time (ISO format), defaults to horizon end
            step_sec: Time step between points in seconds
            filter_polygon: Optional polygon [(lat, lon), ...] to filter points
            
        Returns:
            List of GroundTrackPoint objects representing the ground track
        """
        if satellite_id not in self.satellites:
            raise ScenarioError(f"Satellite '{satellite_id}' not found")
            
        start_dt = parse_iso(start_time) if start_time else self.horizon_start
        end_dt = parse_iso(end_time) if end_time else self.horizon_end
        
        sat = self.satellites[satellite_id]
        engine_sat = to_engine_satellite(sat)
        
        track_tuples = compute_ground_track(
            engine_sat,
            (start_dt, end_dt),
            step_sec=step_sec,
            polygon=filter_polygon
        )
        
        return [
            GroundTrackPoint(lat=lat, lon=lon, time=time)
            for lat, lon, time in track_tuples
        ]

    def evaluate_comms_latency(
        self,
        source_station_id: str,
        dest_station_id: str,
        start_time: str | None = None,
        end_time: str | None = None,
        sample_step_sec: float = 60.0,
    ) -> ChainAccessResult:
        """
        Evaluate communication latency using dynamic topology from staged actions.
        
        Builds time-varying connection graph from staged ISL and downlink actions,
        then computes chain access for each topology interval.
        
        Args:
            source_station_id: ID of source ground station
            dest_station_id: ID of destination ground station
            start_time: Start time (ISO format), defaults to horizon start
            end_time: End time (ISO format), defaults to horizon end
            sample_step_sec: Sampling interval for latency calculation (seconds)
            
        Returns:
            ChainAccessResult with windows containing latency time series
        """
        if source_station_id not in self.stations:
            raise ScenarioError(f"Source station '{source_station_id}' not found")
        if dest_station_id not in self.stations:
            raise ScenarioError(f"Destination station '{dest_station_id}' not found")
        
        start_dt = parse_iso(start_time) if start_time else self.horizon_start
        end_dt = parse_iso(end_time) if end_time else self.horizon_end
        
        # Extract all link actions (ISL + downlink)
        link_actions = [
            a for a in self.staged_actions.values()
            if a.type in ("intersatellite_link", "downlink")
        ]
        
        # Build topology change timeline
        events = []
        for action in link_actions:
            if action.start_time >= start_dt and action.start_time <= end_dt:
                events.append((action.start_time, "start", action))
            if action.end_time >= start_dt and action.end_time <= end_dt:
                events.append((action.end_time, "end", action))
        
        # Sort events chronologically
        events.sort(key=lambda x: x[0])
        
        # Build intervals
        intervals = []
        if not events:
            # No actions, single interval with no connections
            intervals.append((start_dt, end_dt, []))
        else:
            current_time = start_dt
            active_actions = set()
            
            for event_time, event_type, action in events:
                if current_time < event_time:
                    # Emit interval with current topology
                    intervals.append((current_time, event_time, list(active_actions)))
                
                if event_type == "start":
                    active_actions.add(action)
                else:
                    active_actions.discard(action)
                
                current_time = event_time
            
            # Final interval
            if current_time < end_dt:
                intervals.append((current_time, end_dt, list(active_actions)))
        
        # Collect all participating nodes
        all_node_ids = {source_station_id, dest_station_id}
        for action in link_actions:
            all_node_ids.add(action.satellite_id)
            if action.type == "intersatellite_link":
                all_node_ids.add(action.peer_satellite_id)
            elif action.type == "downlink":
                all_node_ids.add(action.station_id)
        
        all_nodes = {}
        for node_id in all_node_ids:
            if node_id in self.satellites:
                all_nodes[node_id] = to_engine_satellite(self.satellites[node_id])
            elif node_id in self.stations:
                all_nodes[node_id] = to_engine_station(self.stations[node_id])
        
        # Compute chain access for each interval
        all_windows = []
        for interval_start, interval_end, active_actions in intervals:
            if not active_actions:
                continue  # No connectivity in this interval
            
            # Build connections from active actions
            connections = []
            for action in active_actions:
                if action.type == "intersatellite_link":
                    sat_a = action.satellite_id
                    sat_b = action.peer_satellite_id
                    # ISL is bidirectional
                    connections.append((sat_a, sat_b))
                    connections.append((sat_b, sat_a))
                elif action.type == "downlink":
                    sat = action.satellite_id
                    station = action.station_id
                    # Downlink is bidirectional
                    connections.append((sat, station))
                    connections.append((station, sat))
            
            formatted_start = format_for_astrox(interval_start)
            formatted_end = format_for_astrox(interval_end)
            
            result = compute_chain_access_with_latency(
                start_node=all_nodes[source_station_id],
                end_node=all_nodes[dest_station_id],
                all_nodes=all_nodes,
                connections=connections,
                time_window=(formatted_start, formatted_end),
                sample_step_sec=sample_step_sec,
            )
            
            all_windows.extend(result.windows)
        
        return ChainAccessResult(windows=all_windows)

    # ==========================================================================
    # Analytics Methods
    # ==========================================================================

    def evaluate_revisit_gaps(
        self,
        target_ids: List[str],
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> List[RevisitAnalysis]:
        """Evaluate revisit gaps for specified targets based on staged actions."""
        start_dt = parse_iso(start_time) if start_time else self.horizon_start
        end_dt = parse_iso(end_time) if end_time else self.horizon_end
        
        results = []
        for tid in target_ids:
            if tid not in self.targets:
                raise ScenarioError(f"Target '{tid}' not found")

            # Collect observation intervals for this target
            intervals = []
            obs_times = []
            for action in self.staged_actions.values():
                if (
                    action.type == "observation" 
                    and action.target_id == tid
                    and action.end_time >= start_dt 
                    and action.start_time <= end_dt
                ):
                    intervals.append((action.start_time, action.end_time))
                    obs_times.append(action.start_time)

            stats = compute_revisit_stats(intervals, start_dt, end_dt)
            results.append(RevisitAnalysis(
                target_id=tid,
                observation_times=sorted(obs_times),
                gaps_seconds=stats["gaps"],
                max_gap_seconds=stats["max_gap"],
                mean_gap_seconds=stats["mean_gap"],
                coverage_count=stats["coverage_count"],
            ))
        return results

    def evaluate_stereo_coverage(
        self,
        target_ids: List[str],
        min_separation_deg: float = 10.0,
    ) -> List[StereoAnalysis]:
        """Evaluate stereo coverage (multi-angle observation) for targets."""
        results = []
        for tid in target_ids:
            if tid not in self.targets:
                raise ScenarioError(f"Target '{tid}' not found")

            observations = []
            obs_info_list = []
            
            for action in self.staged_actions.values():
                if action.type == "observation" and action.target_id == tid:
                    # Find matching window to get azimuth
                    # We need to scan ALL windows because action doesn't store window_id directly per se
                    # But parse_action uses matching logic. Ideally action should link to window?
                    # For now, we search windows that match time and target.
                    found_az = None
                    found_el = None
                    
                    # Optimization: Look up windows for this target/sat
                    # This could be slow if many windows.
                    for win in self.windows.values():
                        if (
                            win.satellite_id == action.satellite_id
                            and win.target_id == tid
                            and abs((win.start - action.start_time).total_seconds()) < 1.0
                        ):
                             if win.max_elevation_point:
                                 found_az = win.max_elevation_point.azimuth_deg
                                 found_el = win.max_elevation_point.elevation_deg
                             break
                    
                    if found_az is not None:
                        # Construct observation dict for updated compute_stereo_compliance
                        obs_entry = {
                            "id": action.action_id,
                            "azimuth_deg": found_az,
                            "elevation_deg": found_el,
                            "time": action.start_time
                        }
                        observations.append(obs_entry)
                        
                        obs_info_list.append(ObservationInfo(
                            action_id=action.action_id,
                            time=action.start_time,
                            satellite_id=action.satellite_id,
                            azimuth_deg=found_az,
                            elevation_deg=found_el
                        ))

            stats = compute_stereo_compliance(observations, min_separation_deg)
            
            stereo_pairs = []
            if stats["best_pair"]:
                stereo_pairs.append(stats["best_pair"])

            results.append(StereoAnalysis(
                target_id=tid,
                observations=obs_info_list,
                has_stereo=stats["has_stereo"],
                best_pair_azimuth_diff_deg=stats["max_separation_deg"],
                stereo_pairs=stereo_pairs
            ))
        return results

    def evaluate_polygon_coverage(
        self,
        polygon: List[Tuple[float, float]],
    ) -> PolygonCoverageAnalysis:
        """
        Evaluate coverage of a polygon by staged strip observations.
        
        Args:
            polygon: List of (lat, lon) vertices defining the area of interest.
        """
        # Collect strips from actions with their specific swath widths
        observed_strips_with_width = []
        for action in self.staged_actions.values():
            if action.type == "observation" and action.strip_id:
                if action.strip_id in self.strips:
                    strip = self.strips[action.strip_id]
                    
                    if action.satellite_id not in self.satellites:
                         # Should not happen given integrity checks, but safe to skip
                         continue
                         
                    sat = self.satellites[action.satellite_id]
                    if sat.swath_width_km is None:
                        raise ScenarioError(f"Satellite '{sat.id}' missing swath_width_km")
                        
                    observed_strips_with_width.append((strip.points, sat.swath_width_km))
        
        stats = compute_polygon_coverage(polygon, observed_strips_with_width)
        
        cells = [
            GridCell(lat=c["lat"], lon=c["lon"], is_covered=c["is_covered"])
            for c in stats["grid_cells"]
        ]
        
        return PolygonCoverageAnalysis(
            total_area_km2=stats["total_area_km2"],
            covered_area_km2=stats["covered_area_km2"],
            coverage_ratio=stats["coverage_ratio"],
            coverage_grid=cells
        )

    # ==========================================================================
    # Metrics Computation
    # ==========================================================================

    def compute_metrics(self, actions: Dict[str, PlannerAction] | None = None) -> PlanMetrics:
        """Compute per-satellite metrics with resource curves and quaternions."""
        if actions is None:
            actions = self.staged_actions

        sat_obs_counts: Dict[str, int] = {}
        sat_dl_counts: Dict[str, int] = {}
        sat_isl_counts: Dict[str, int] = {}

        for action in actions.values():
            # Check initiator
            sat_id = action.satellite_id
            if action.type == "observation":
                sat_obs_counts[sat_id] = sat_obs_counts.get(sat_id, 0) + 1
            elif action.type == "downlink":
                sat_dl_counts[sat_id] = sat_dl_counts.get(sat_id, 0) + 1
            elif action.type == "intersatellite_link":
                sat_isl_counts[sat_id] = sat_isl_counts.get(sat_id, 0) + 1

        satellite_metrics: Dict[str, SatelliteMetrics] = {}
        # Ensure all satellites involved as initiator OR peer are processed
        satellites_used = set(sat_obs_counts.keys()) | set(sat_dl_counts.keys()) | set(sat_isl_counts.keys())
        for a in actions.values():
            satellites_used.add(a.satellite_id)
            if a.peer_satellite_id:
                satellites_used.add(a.peer_satellite_id)

        for sat_id in satellites_used:
            # Include actions where this satellite is EITHER initiator OR peer
            sat_all_actions = [a for a in actions.values() 
                               if a.satellite_id == sat_id or a.peer_satellite_id == sat_id]
            
            signature = self._generate_action_signature(sat_all_actions)

            # Check cache
            cached = self._metrics_cache.get(sat_id)
            if cached and cached[0] == signature:
                satellite_metrics[sat_id] = cached[1]
                continue

            # Cache miss - compute
            obs_count = sat_obs_counts.get(sat_id, 0)
            dl_count = sat_dl_counts.get(sat_id, 0)
            isl_count = sat_isl_counts.get(sat_id, 0)

            sat = self.satellites[sat_id]
            engine_sat = to_engine_satellite(sat)
            
            power_events = convert_to_power_events(sat_all_actions, sat_id, {sat_id: sat})
            power_params = get_power_params(sat)
            p_stats = simulate_power(
                power_events, engine_sat,
                (self.horizon_start, self.horizon_end),
                power_params
            )
            power_violated = p_stats.get("violated_low", False) or p_stats.get("violated_high", False)

            storage_events = convert_to_storage_events(sat_all_actions, sat_id, {sat_id: sat})
            cap, _, _, initial = get_storage_params(sat)
            s_stats = simulate_storage(storage_events, cap, initial)
            storage_violated = s_stats["peak"] > s_stats["capacity"]

            power_curve = simulate_resource_curve(
                power_events,
                self._time_points,
                power_params[5],
                capacity=power_params[0],
                saturate=True,
            )

            storage_curve = simulate_resource_curve(
                storage_events,
                self._time_points,
                initial,
                capacity=cap,
                saturate=False,
            )

            target_obs_actions = [
                (a.start_time, a.end_time, 
                 self.targets[a.target_id].latitude_deg, 
                 self.targets[a.target_id].longitude_deg,
                 self.targets[a.target_id].altitude_m)
                for a in sat_all_actions if a.type == "observation" and a.target_id
            ]

            strip_obs_actions = [
                (a.start_time, a.end_time,
                 self.strips[a.strip_id].points)
                for a in sat_all_actions if a.type == "observation" and a.strip_id
            ]

            quaternions = calculate_quaternion_series(
                sat.tle_line1,
                sat.tle_line2,
                target_obs_actions,
                strip_obs_actions,
                self._time_points,
            )

            metrics = SatelliteMetrics(
                satellite_id=sat_id,
                obs_count=obs_count,
                downlink_count=dl_count,
                isl_count=isl_count,
                power_violated=power_violated,
                storage_violated=storage_violated,
                power_curve=power_curve,
                storage_curve=storage_curve,
                quaternions=quaternions,
            )
            
            # Update cache
            self._metrics_cache[sat_id] = (signature, metrics)
            satellite_metrics[sat_id] = metrics

        total_obs = sum(m.obs_count for m in satellite_metrics.values())
        total_dls = sum(m.downlink_count for m in satellite_metrics.values())
        total_isls = sum(1 for a in actions.values() if a.type == "intersatellite_link")

        return PlanMetrics(
            satellites=satellite_metrics,
            total_actions=len(actions),
            total_observations=total_obs,
            total_downlinks=total_dls,
            total_isls=total_isls,
        )

    def get_plan_status(self) -> PlanStatus:
        """Get current plan status (staged actions + metrics)."""
        return PlanStatus(
            actions=dict(self.staged_actions),
            metrics=self.compute_metrics(),
        )

    # ==========================================================================
    # Staging Operations
    # ==========================================================================



    def stage_action(self, action_dict: Dict[str, Any]) -> StageResult:
        """Stage a single action. Auto-creates reverse action for ISLs."""
        action = parse_action(
            action_dict,
            self.windows,
            self.staged_actions,
            self.horizon_start,
            self.horizon_end,
        )
        validate_action_feasibility(
            action,
            self.staged_actions,
            self.satellites,
            self.targets,
            self.stations,
            self.strips,
            self.windows,
            self._quaternion_cache,
            self.horizon_start,
            self.horizon_end,
        )
        self.staged_actions[action.action_id] = action
        
        # Auto-register reverse ISL action (bidirectional)
        if action.type == "intersatellite_link" and action.peer_satellite_id:
            from dataclasses import replace
            reverse_action = replace(
                action,
                action_id=f"{action.action_id}_rev",
                satellite_id=action.peer_satellite_id,
                peer_satellite_id=action.satellite_id,
            )
            self.staged_actions[reverse_action.action_id] = reverse_action
        
        return StageResult(action_id=action.action_id, staged=True)

    def unstage_action(self, action_id: str) -> UnstageResult:
        """Unstage a single action. Auto-removes reverse ISL action if present."""
        if action_id not in self.staged_actions:
            raise ValidationError(f"Action '{action_id}' not found")

        action = self.staged_actions[action_id]
        del self.staged_actions[action_id]
        if action_id in self._quaternion_cache:
            del self._quaternion_cache[action_id]
        
        # Auto-remove reverse ISL action if it exists
        if action.type == "intersatellite_link":
            reverse_id = f"{action_id}_rev"
            if reverse_id in self.staged_actions:
                del self.staged_actions[reverse_id]
                if reverse_id in self._quaternion_cache:
                    del self._quaternion_cache[reverse_id]
            
            # Also handle case where this IS the reverse action
            if action_id.endswith("_rev"):
                original_id = action_id[:-4]  # Remove "_rev" suffix
                if original_id in self.staged_actions:
                    del self.staged_actions[original_id]
                    if original_id in self._quaternion_cache:
                        del self._quaternion_cache[original_id]
            
        return UnstageResult(action_id=action_id, unstaged=True)

    # ==========================================================================
    # Commit / Reset
    # ==========================================================================

    def commit_plan(self, path: str | None = None) -> CommitResult:
        """Validate and commit all staged actions."""
        violations: List[Violation] = []

        for action_id, action in self.staged_actions.items():
            sat = self.satellites[action.satellite_id]
            conflicts = check_time_conflicts(
                action,
                self.staged_actions,
                planner_satellite=sat,
                exclude_self=action_id,
                satellites=self.satellites,
                targets=self.targets,
                strips=self.strips,
                stations=self.stations,
                quaternion_cache=self._quaternion_cache,
            )
            if conflicts:
                violations.append(Violation(
                    action_id=action_id,
                    violation_type="time_conflict",
                    message=f"Action conflicts with: {', '.join(conflicts)}",
                    conflicting_action_ids=conflicts,
                ))

        satellites_checked = set()
        for action in self.staged_actions.values():
            sat_id = action.satellite_id
            if sat_id in satellites_checked:
                continue
            satellites_checked.add(sat_id)

            sat = self.satellites[sat_id]
            engine_sat = to_engine_satellite(sat)
            sat_all_actions = [a for a in self.staged_actions.values() 
                               if a.satellite_id == sat_id or a.peer_satellite_id == sat_id]

            power_events = convert_to_power_events(sat_all_actions, sat_id, {sat_id: sat})
            power_params = get_power_params(sat)
            p_stats = simulate_power(
                power_events, engine_sat,
                (self.horizon_start, self.horizon_end),
                power_params
            )
            if p_stats.get("violated_low") or p_stats.get("violated_high"):
                violations.append(Violation(
                    action_id=sat_id,
                    violation_type="power",
                    message=f"Power violation: min={p_stats['min']:.1f}Wh, max={p_stats['max']:.1f}Wh",
                ))

            cap, _, _, initial = get_storage_params(sat)
            storage_events = convert_to_storage_events(sat_all_actions, sat_id, {sat_id: sat})
            s_stats = simulate_storage(storage_events, cap, initial)
            if s_stats["peak"] > s_stats["capacity"]:
                violations.append(Violation(
                    action_id=sat_id,
                    violation_type="storage",
                    message=f"Storage overflow: peak={s_stats['peak']:.1f}MB, capacity={s_stats['capacity']:.1f}MB",
                ))

        is_valid = len(violations) == 0
        plan_json_path = None

        if is_valid:
            import os
            output_path_env = os.environ.get("ASTROX_OUTPUT_PATH")
            export_path = path or output_path_env or "plan.json"
            
            plan_export = {
                "metadata": {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "status": "COMMITTED",
                    "valid": True,
                    "horizon_start": self.horizon_start.isoformat(),
                    "horizon_end": self.horizon_end.isoformat(),
                },
                "actions": [
                    {
                        "action_id": a.action_id,
                        "type": a.type,
                        "satellite_id": a.satellite_id,
                        "target_id": a.target_id,
                        "station_id": a.station_id,
                        "peer_satellite_id": a.peer_satellite_id,
                        "strip_id": a.strip_id,
                        "start": a.start_time.isoformat(),
                        "end": a.end_time.isoformat(),
                    }
                    for a in self.staged_actions.values()
                ],
                "registered_strips": [
                    {
                        "id": s.id,
                        "name": s.name,
                        "points": s.points,
                    }
                    for s in self.strips.values()
                ],
            }
            plan_json_path = str(export_plan_to_json(plan_export, path=export_path))

        metrics = self.compute_metrics()

        return CommitResult(
            valid=is_valid,
            violations=violations,
            metrics=metrics,
            plan_json_path=plan_json_path,
        )

    def reset_plan(self) -> None:
        """Reset staged actions to initial plan."""
        self.staged_actions = dict(self.initial_plan)
        self._metrics_cache.clear()

    # ==========================================================================
    # State Serialization (for file-backed persistence)
    # ==========================================================================

    def export_to_state(self) -> Dict[str, Any]:
        """Export dynamic state to a serializable dictionary.
        
        Returns state dict containing:
        - version: State format version
        - horizon: Planning horizon times
        - staged_actions: List of staged action dicts
        - registered_windows: List of registered window dicts
        - registered_strips: List of registered strip dicts
        - window_counter: Internal counter for window ID generation
        """
        return {
            "version": 1,
            "horizon": {
                "start": self.horizon_start.isoformat(),
                "end": self.horizon_end.isoformat(),
            },
            "staged_actions": [
                {
                    "action_id": a.action_id,
                    "type": a.type,
                    "satellite_id": a.satellite_id,
                    "target_id": a.target_id,
                    "station_id": a.station_id,
                    "peer_satellite_id": a.peer_satellite_id,
                    "strip_id": a.strip_id,
                    "start_time": a.start_time.isoformat(),
                    "end_time": a.end_time.isoformat(),
                }
                for a in self.staged_actions.values()
            ],
            "registered_windows": [
                {
                    "window_id": w.window_id,
                    "satellite_id": w.satellite_id,
                    "target_id": w.target_id,
                    "station_id": w.station_id,
                    "peer_satellite_id": w.peer_satellite_id,
                    "strip_id": w.strip_id,
                    "start": w.start.isoformat(),
                    "end": w.end.isoformat(),
                    "duration_sec": w.duration_sec,
                    "max_elevation_point": {
                        "time": w.max_elevation_point.time.isoformat(),
                        "elevation_deg": w.max_elevation_point.elevation_deg,
                        "azimuth_deg": w.max_elevation_point.azimuth_deg,
                        "range_m": w.max_elevation_point.range_m,
                    } if w.max_elevation_point else None,
                }
                for w in self.windows.values()
            ],
            "registered_strips": [
                {
                    "id": s.id,
                    "name": s.name,
                    "points": s.points,
                }
                for s in self.strips.values()
            ],
            "window_counter": self._window_counter,
        }

    @classmethod
    def from_state(
        cls,
        satellite_file: str,
        target_file: str,
        station_file: str,
        plan_file: str,
        state_dict: Dict[str, Any],
    ) -> "Scenario":
        """Load scenario from YAML files and restore dynamic state from state dict.
        
        Args:
            satellite_file: Path to satellites YAML
            target_file: Path to targets YAML
            station_file: Path to stations YAML
            plan_file: Path to initial plan JSON (for horizon, used as fallback)
            state_dict: State dictionary from export_to_state()
            
        Returns:
            Scenario instance with restored state
        """
        from dataclasses import replace
        
        # Create base scenario
        scenario = cls(satellite_file, target_file, station_file, plan_file)
        
        # Restore horizon (override from state if present)
        if "horizon" in state_dict:
            scenario.horizon_start = parse_iso(state_dict["horizon"]["start"])
            scenario.horizon_end = parse_iso(state_dict["horizon"]["end"])
            scenario._time_points = _generate_time_points(scenario.horizon_start, scenario.horizon_end)
        
        # Restore strips
        scenario.strips = {}
        for strip_data in state_dict.get("registered_strips", []):
            strip = PlannerStrip(
                id=strip_data["id"],
                name=strip_data["name"],
                points=strip_data["points"],
            )
            scenario.strips[strip.id] = strip
        
        # Restore windows
        scenario.windows = {}
        for win_data in state_dict.get("registered_windows", []):
            max_elev = None
            if win_data.get("max_elevation_point"):
                from engine.models import AccessAERPoint
                max_elev = AccessAERPoint(
                    time=parse_iso(win_data["max_elevation_point"]["time"]),
                    elevation_deg=win_data["max_elevation_point"]["elevation_deg"],
                    azimuth_deg=win_data["max_elevation_point"]["azimuth_deg"],
                    range_m=win_data["max_elevation_point"]["range_m"],
                )
            
            window = PlannerAccessWindow(
                window_id=win_data["window_id"],
                satellite_id=win_data["satellite_id"],
                target_id=win_data.get("target_id"),
                station_id=win_data.get("station_id"),
                peer_satellite_id=win_data.get("peer_satellite_id"),
                strip_id=win_data.get("strip_id"),
                start=parse_iso(win_data["start"]),
                end=parse_iso(win_data["end"]),
                duration_sec=win_data["duration_sec"],
                max_elevation_point=max_elev,
            )
            scenario.windows[window.window_id] = window
        
        scenario._window_counter = state_dict.get("window_counter", 0)
        
        # Restore staged actions
        scenario.staged_actions = {}
        for action_data in state_dict.get("staged_actions", []):
            action = PlannerAction(
                action_id=action_data["action_id"],
                type=action_data["type"],
                satellite_id=action_data["satellite_id"],
                target_id=action_data.get("target_id"),
                station_id=action_data.get("station_id"),
                peer_satellite_id=action_data.get("peer_satellite_id"),
                strip_id=action_data.get("strip_id"),
                start_time=parse_iso(action_data["start_time"]),
                end_time=parse_iso(action_data["end_time"]),
            )
            scenario.staged_actions[action.action_id] = action
        
        return scenario