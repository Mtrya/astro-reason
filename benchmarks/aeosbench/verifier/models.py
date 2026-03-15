"""Lightweight data models for parsing AEOS-Bench JSON files.

Adapted from verifier/models.py without brahe/torch dependencies.
Uses numpy arrays for vector data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class Orbit:
    """Orbital elements for a satellite."""
    id: int
    semi_major_axis: float  # meters
    eccentricity: float
    inclination: float  # degrees
    raan: float  # degrees (right ascension of ascending node)
    argument_of_perigee: float  # degrees


@dataclass
class ReactionWheel:
    """Reaction wheel configuration."""
    rw_type: str
    direction: np.ndarray  # unit vector (3,)
    max_momentum: float  # Nms
    speed_init: float  # RPM (passed directly to rwFactory.create)
    power: float  # watts
    efficiency: float


@dataclass
class MRPControl:
    """MRP feedback control gains."""
    k: float
    ki: float
    p: float
    integral_limit: float


@dataclass
class Sensor:
    """Sensor configuration."""
    type: int  # 0=VISIBLE, 1=NEAR_INFRARED
    enabled: bool
    half_field_of_view: float  # degrees
    power: float  # watts


@dataclass
class SolarPanel:
    """Solar panel configuration."""
    direction: np.ndarray  # unit vector (3,)
    area: float  # m²
    efficiency: float


@dataclass
class Battery:
    """Battery configuration."""
    capacity: float  # joules (or Wh depending on usage)
    percentage: float  # 0-1 initial charge fraction


@dataclass
class Satellite:
    """Satellite configuration with all subsystems."""
    id: int
    orbit_id: int
    mass: float  # kg
    inertia: tuple[float, ...]  # 9-element tuple (flattened 3x3 inertia tensor)
    center_of_mass: np.ndarray  # (3,)
    solar_panel: SolarPanel
    sensor: Sensor
    battery: Battery
    reaction_wheels: list[ReactionWheel]
    mrp_control: MRPControl
    true_anomaly: float  # degrees (initial)
    mrp_attitude_bn: np.ndarray  # (3,) initial MRP


@dataclass
class Task:
    """Task to be scheduled."""
    id: int
    release_time: int  # timestep
    due_time: int  # timestep
    duration: int  # timesteps needed for completion
    coordinate: tuple[float, float]  # (latitude_deg, longitude_deg)
    sensor_type: int


@dataclass
class Constellation:
    """Collection of orbits and satellites."""
    orbits: list[Orbit]
    satellites: list[Satellite]

    def get_orbit(self, orbit_id: int) -> Orbit:
        """Get orbit by ID."""
        for orbit in self.orbits:
            if orbit.id == orbit_id:
                return orbit
        raise ValueError(f"Orbit {orbit_id} not found")

    def get_satellite(self, sat_id: int) -> Satellite:
        """Get satellite by ID."""
        for sat in self.satellites:
            if sat.id == sat_id:
                return sat
        raise ValueError(f"Satellite {sat_id} not found")


@dataclass
class TaskSet:
    """Collection of tasks."""
    tasks: list[Task]

    def get_task(self, task_id: int) -> Task:
        """Get task by ID."""
        for task in self.tasks:
            if task.id == task_id:
                return task
        raise ValueError(f"Task {task_id} not found")


# -----------------------------------------------------------------------------
# JSON Loaders
# -----------------------------------------------------------------------------

def _parse_orbit(data: dict) -> Orbit:
    """Parse orbit from JSON dict."""
    return Orbit(
        id=data["id"],
        semi_major_axis=data["semi_major_axis"],
        eccentricity=data["eccentricity"],
        inclination=data["inclination"],
        raan=data["right_ascension_of_the_ascending_node"],
        argument_of_perigee=data["argument_of_perigee"],
    )


def _parse_reaction_wheel(data: dict) -> ReactionWheel:
    """Parse reaction wheel from JSON dict."""
    return ReactionWheel(
        rw_type=data["rw_type"],
        direction=np.array(data["rw_direction"], dtype=np.float64),
        max_momentum=data["max_momentum"],
        speed_init=data["rw_speed_init"],
        power=data["power"],
        efficiency=data["efficiency"],
    )


def _parse_satellite(data: dict, orbits: dict[int, Orbit]) -> Satellite:
    """Parse satellite from JSON dict."""
    # Inertia is stored as flat tuple of 9 elements (not numpy array)
    # This matches the original constellation data format
    inertia = tuple(data["inertia"])  # type: ignore

    sensor_data = data.get("sensor", {})
    sensor = Sensor(
        type=sensor_data.get("type", 0),
        enabled=sensor_data.get("enabled", False),
        half_field_of_view=sensor_data.get("half_field_of_view", 0.0),
        power=sensor_data.get("power", 0.0),
    )

    sp = data["solar_panel"]
    solar_panel = SolarPanel(
        direction=np.array(sp["direction"], dtype=np.float64),
        area=sp["area"],
        efficiency=sp["efficiency"],
    )

    bat = data["battery"]
    battery = Battery(capacity=bat["capacity"], percentage=bat["percentage"])

    ctrl = data["mrp_control"]
    mrp_control = MRPControl(
        k=ctrl["k"],
        ki=ctrl["ki"],
        p=ctrl["p"],
        integral_limit=ctrl["integral_limit"],
    )

    return Satellite(
        id=data["id"],
        orbit_id=data["orbit"],
        mass=data["mass"],
        inertia=inertia,
        center_of_mass=np.array(data["center_of_mass"], dtype=np.float64),
        solar_panel=solar_panel,
        sensor=sensor,
        battery=battery,
        reaction_wheels=[_parse_reaction_wheel(rw) for rw in data["reaction_wheels"]],
        mrp_control=mrp_control,
        true_anomaly=data["true_anomaly"],
        mrp_attitude_bn=np.array(data["mrp_attitude_bn"], dtype=np.float64),
    )


def _parse_task(data: dict) -> Task:
    """Parse task from JSON dict."""
    return Task(
        id=data["id"],
        release_time=data["release_time"],
        due_time=data["due_time"],
        duration=data["duration"],
        coordinate=tuple(data["coordinate"]),
        sensor_type=data["sensor_type"],
    )


def load_constellation(json_dict: dict) -> Constellation:
    """Load constellation from parsed JSON dict.

    Args:
        json_dict: Parsed JSON dict with 'orbits' and 'satellites' keys.

    Returns:
        Constellation object.
    """
    orbits = [_parse_orbit(o) for o in json_dict["orbits"]]
    orbit_map = {o.id: o for o in orbits}
    satellites = [_parse_satellite(s, orbit_map) for s in json_dict["satellites"]]
    return Constellation(orbits=orbits, satellites=satellites)


def load_taskset(json_dict: dict) -> TaskSet:
    """Load task set from parsed JSON dict.

    Args:
        json_dict: Parsed JSON dict with 'tasks' key.

    Returns:
        TaskSet object.
    """
    tasks = [_parse_task(t) for t in json_dict["tasks"]]
    return TaskSet(tasks=tasks)
