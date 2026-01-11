"""
Data loading utils.
"""

from pathlib import Path
from typing import Dict, Any

import json
import yaml

from engines.astrox.temporal import parse_iso
from engines.astrox.models import Satellite, Target, Station
from toolkits.mission_planner.scenario.models import PlannerSatellite, PlannerTarget, PlannerStation, PlannerAction

def load_satellites(satellite_path: str):
    """
    Load satellite data from yaml file,
    Returns:
        satellites: Dict[str, PlannerSatellite] - Dictionary of satellites (planner model)
    """
    with Path(satellite_path).open("r", encoding="utf-8") as f:
        sat_data = yaml.safe_load(f) or []
    
    satellites = {}
    for sat in sat_data:
        satellites[sat["id"]] = PlannerSatellite(**sat)
    return satellites

def to_engine_satellite(planner_satellite: PlannerSatellite) -> Satellite:
    return Satellite(
        tle_line1=planner_satellite.tle_line1,
        tle_line2=planner_satellite.tle_line2,
        apogee_km=planner_satellite.apogee_km,
        perigee_km=planner_satellite.perigee_km,
        period_min=planner_satellite.period_min,
        inclination_deg=planner_satellite.inclination_deg,

        storage_capacity_mb=planner_satellite.storage_capacity_mb,
        obs_store_rate_mb_per_min=planner_satellite.obs_store_rate_mb_per_min,
        downlink_release_rate_mb_per_min=planner_satellite.downlink_release_rate_mb_per_min,
        battery_capacity_wh=planner_satellite.battery_capacity_wh,
        charge_rate_w=planner_satellite.charge_rate_w,
        obs_discharge_rate_w=planner_satellite.obs_discharge_rate_w,
        downlink_discharge_rate_w=planner_satellite.downlink_discharge_rate_w,
        idle_discharge_rate_w=planner_satellite.idle_discharge_rate_w,
        initial_storage_mb=planner_satellite.initial_storage_mb,
        initial_battery_wh=planner_satellite.initial_battery_wh,
        max_slew_velocity_deg_per_sec=planner_satellite.max_slew_velocity_deg_per_sec,
        max_slew_acceleration_deg_per_sec2=planner_satellite.max_slew_acceleration_deg_per_sec2,
        max_slew_jerk_deg_per_sec3=planner_satellite.max_slew_jerk_deg_per_sec3,
        settling_time_sec=planner_satellite.settling_time_sec,
        num_terminal=planner_satellite.num_terminal,
    )

def load_targets(target_path: str):
    """
    Load target data from yaml file,
    Returns:
        targets: Dict[str, PlannerTarget] - Dictionary of targets (planner model)
    """
    with Path(target_path).open("r", encoding="utf-8") as f:
        tar_data = yaml.safe_load(f) or []
    return {tar["id"]: PlannerTarget(**tar) for tar in tar_data}

def to_engine_target(planner_target: PlannerTarget) -> Target:
    return Target(
        latitude_deg=round(planner_target.latitude_deg, 3),
        longitude_deg=round(planner_target.longitude_deg, 3),
        altitude_m=round(planner_target.altitude_m, 3),
    )

def load_stations(station_path: str):
    """
    Load station data from yaml file,
    Returns:
        stations: Dict[str, PlannerStation] - Dictionary of stations (planner model)
    """
    with Path(station_path).open("r", encoding="utf-8") as f:
        sta_data = yaml.safe_load(f) or []
    stations = {sta["id"]: PlannerStation(**sta) for sta in sta_data}
    return stations

def to_engine_station(planner_station: PlannerStation) -> Station:
    return Station(
        latitude_deg=round(planner_station.latitude_deg, 3),
        longitude_deg=round(planner_station.longitude_deg, 3),
        altitude_m=round(planner_station.altitude_m, 3),
    )

def load_plan(plan_path: str):
    """
    Load plan data from json file,
    Returns:
        plan: Dict[str, PlannerAction] - Dictionary of actions (planner model)
    """
    with Path(plan_path).open("r", encoding="utf-8") as f:
        plan_data = json.load(f) or {}
    
    act_data = plan_data.get("actions", [])
    plan: Dict[str, PlannerAction] = {}
    for idx, act in enumerate(act_data):
        # Normalize fields
        if "start" in act and "start_time" not in act:
            act["start_time"] = act.pop("start")
        if "end" in act and "end_time" not in act:
            act["end_time"] = act.pop("end")

        start_time = parse_iso(act["start_time"])
        end_time = parse_iso(act["end_time"])

        # Override original action_id with planner's internal action_id
        action_id = f"action_{idx:03d}"

        plan[action_id] = PlannerAction(
            action_id=action_id,
            type=act["type"],
            satellite_id=act["satellite_id"],
            target_id=act.get("target_id"),
            station_id=act.get("station_id"),
            peer_satellite_id=act.get("peer_satellite_id"),
            strip_id=act.get("strip_id"),
            start_time=start_time,
            end_time=end_time,
        )
    return plan

def load_horizon(plan_path: str):
    """
    Load horizon from json file,
    Returns:
        horizon: Tuple[datetime, datetime] - Tuple of start and end times
    """

    with Path(plan_path).open("r", encoding="utf-8") as f:
        plan_data = json.load(f) or {}
    metadata = plan_data.get("metadata", {})
    return parse_iso(metadata["horizon_start"]), parse_iso(metadata["horizon_end"])




if __name__ == "__main__":
    satellite_path = "tests/fixtures/case_0001/satellites.yaml"
    load_satellites(satellite_path)
