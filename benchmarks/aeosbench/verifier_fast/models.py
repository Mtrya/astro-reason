"""Data models and JSON loaders for AEOS-Bench verifier.

Dataclasses for Orbit, Satellite, Task, Constellation, TaskSet, Solution,
and VerificationResult, plus JSON loading functions.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .constants import RPM_TO_RAD_PER_SEC


# ---------------------------------------------------------------------------
# Orbit
# ---------------------------------------------------------------------------

@dataclass
class Orbit:
    id: int
    semi_major_axis: float  # meters
    eccentricity: float
    inclination: float  # degrees
    raan: float  # degrees (right ascension of ascending node)
    argument_of_perigee: float  # degrees


# ---------------------------------------------------------------------------
# Reaction Wheel
# ---------------------------------------------------------------------------

@dataclass
class ReactionWheel:
    rw_type: str
    direction: np.ndarray  # unit vector (3,)
    max_momentum: float  # Nms
    speed_init: float  # rad/s (converted from RPM at load time)
    power: float  # watts
    efficiency: float


# ---------------------------------------------------------------------------
# MRP Control gains
# ---------------------------------------------------------------------------

@dataclass
class MRPControl:
    k: float
    ki: float
    p: float
    integral_limit: float


# ---------------------------------------------------------------------------
# Sensor
# ---------------------------------------------------------------------------

@dataclass
class Sensor:
    enabled: bool
    half_field_of_view: float  # degrees
    power: float  # watts
    type: int


# ---------------------------------------------------------------------------
# SolarPanel
# ---------------------------------------------------------------------------

@dataclass
class SolarPanel:
    direction: np.ndarray  # unit vector (3,)
    area: float  # m²
    efficiency: float


# ---------------------------------------------------------------------------
# Battery
# ---------------------------------------------------------------------------

@dataclass
class Battery:
    capacity: float  # Wh
    percentage: float  # 0-1 initial charge fraction


# ---------------------------------------------------------------------------
# Satellite
# ---------------------------------------------------------------------------

@dataclass
class Satellite:
    id: int
    orbit_id: int
    mass: float  # kg
    inertia: np.ndarray  # (3,3) inertia tensor
    center_of_mass: np.ndarray  # (3,)
    solar_panel: SolarPanel
    sensor: Sensor
    battery: Battery
    reaction_wheels: list[ReactionWheel]
    mrp_control: MRPControl
    true_anomaly: float  # degrees (initial)
    mrp_attitude_bn: np.ndarray  # (3,) initial MRP


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------

@dataclass
class Task:
    id: int
    release_time: int  # timestep
    due_time: int  # timestep
    duration: int  # timesteps needed for completion
    coordinate: tuple[float, float]  # (latitude_deg, longitude_deg)
    sensor_type: int


# ---------------------------------------------------------------------------
# Constellation & TaskSet
# ---------------------------------------------------------------------------

@dataclass
class Constellation:
    orbits: list[Orbit]
    satellites: list[Satellite]

    def orbit_for(self, sat: Satellite) -> Orbit:
        """Get the orbit object for a satellite."""
        for o in self.orbits:
            if o.id == sat.orbit_id:
                return o
        raise ValueError(f"Orbit {sat.orbit_id} not found for satellite {sat.id}")


@dataclass
class TaskSet:
    tasks: list[Task]


# ---------------------------------------------------------------------------
# Solution
# ---------------------------------------------------------------------------

@dataclass
class Solution:
    case_id: int
    algorithm: str
    assignments: dict[int, list[int]]  # sat_id -> [task_id_per_timestep]


# ---------------------------------------------------------------------------
# Verification Result
# ---------------------------------------------------------------------------

@dataclass
class Metrics:
    CR: float = 0.0   # Completion Rate
    WCR: float = 0.0  # Weighted Completion Rate
    PCR: float = 0.0  # Partial Completion Rate
    WPCR: float = 0.0 # Weighted Partial Completion Rate
    TAT: float = 0.0  # Turn-Around Time
    PC: float = 0.0   # Power Consumption
    num_succeeded: int = 0
    num_failed: int = 0
    num_total: int = 0


@dataclass
class Curves:
    """Optional simulation curves for detailed comparison."""
    satellites: dict[int, dict[str, Any]] = field(default_factory=dict)
    tasks: dict[str, Any] = field(default_factory=dict)


@dataclass
class VerificationResult:
    metrics: Metrics
    curves: Curves | None = None


# ---------------------------------------------------------------------------
# JSON Loaders
# ---------------------------------------------------------------------------

def _parse_orbit(data: dict) -> Orbit:
    return Orbit(
        id=data["id"],
        semi_major_axis=data["semi_major_axis"],
        eccentricity=data["eccentricity"],
        inclination=data["inclination"],
        raan=data["right_ascension_of_the_ascending_node"],
        argument_of_perigee=data["argument_of_perigee"],
    )


def _parse_reaction_wheel(data: dict) -> ReactionWheel:
    return ReactionWheel(
        rw_type=data["rw_type"],
        direction=np.array(data["rw_direction"], dtype=np.float64),
        max_momentum=data["max_momentum"],
        speed_init=data["rw_speed_init"] * RPM_TO_RAD_PER_SEC,
        power=data["power"],
        efficiency=data["efficiency"],
    )


def _parse_satellite(data: dict) -> Satellite:
    inertia_flat = data["inertia"]
    inertia = np.array(inertia_flat, dtype=np.float64).reshape(3, 3)

    sensor_data = data.get("sensor", {})
    sensor = Sensor(
        enabled=sensor_data.get("enabled", False),
        half_field_of_view=sensor_data.get("half_field_of_view", 0.0),
        power=sensor_data.get("power", 0.0),
        type=sensor_data.get("type", 0),
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
        k=ctrl["k"], ki=ctrl["ki"], p=ctrl["p"],
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
    return Task(
        id=data["id"],
        release_time=data["release_time"],
        due_time=data["due_time"],
        duration=data["duration"],
        coordinate=tuple(data["coordinate"]),
        sensor_type=data["sensor_type"],
    )


def load_constellation(path: str | Path) -> Constellation:
    """Load constellation from JSON file."""
    with open(path) as f:
        data = json.load(f)
    orbits = [_parse_orbit(o) for o in data["orbits"]]
    satellites = [_parse_satellite(s) for s in data["satellites"]]
    return Constellation(orbits=orbits, satellites=satellites)


def load_taskset(path: str | Path) -> TaskSet:
    """Load task set from JSON file."""
    with open(path) as f:
        data = json.load(f)
    tasks = [_parse_task(t) for t in data["tasks"]]
    return TaskSet(tasks=tasks)


def load_solution(path: str | Path) -> Solution:
    """Load solution from JSON file."""
    with open(path) as f:
        data = json.load(f)
    assignments = {int(k): v for k, v in data["assignments"].items()}
    return Solution(
        case_id=data["case_id"],
        algorithm=data["algorithm"],
        assignments=assignments,
    )


def load_metrics(path: str | Path) -> Metrics:
    """Load ground-truth metrics from JSON file."""
    with open(path) as f:
        data = json.load(f)
    m = data["metrics"]
    return Metrics(
        CR=m["CR"], WCR=m["WCR"], PCR=m["PCR"], WPCR=m["WPCR"],
        TAT=m["TAT"], PC=m["PC"],
        num_succeeded=data["num_succeeded"],
        num_failed=data["num_failed"],
        num_total=data["num_total"],
    )


def load_curves(path: str | Path) -> dict:
    """Load ground-truth curves from JSON file (raw dict for comparison)."""
    with open(path) as f:
        return json.load(f)


def load_fixture_index(fixtures_dir: str | Path) -> list[dict]:
    """Load the fixture index.json."""
    with open(Path(fixtures_dir) / "index.json") as f:
        return json.load(f)["fixtures"]
