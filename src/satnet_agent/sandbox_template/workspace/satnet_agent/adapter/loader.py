"""SatNet data loader: Parse problems.json and maintenance.csv"""

import json
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ViewPeriod:
    antenna: str
    trx_on: int
    trx_off: int

    @property
    def duration_seconds(self) -> int:
        return self.trx_off - self.trx_on

    @property
    def duration_hours(self) -> float:
        return self.duration_seconds / 3600


@dataclass
class Request:
    track_id: str
    subject: int
    duration_hours: float
    duration_min_hours: float
    setup_seconds: int
    teardown_seconds: int
    time_window_start: int
    time_window_end: int
    view_periods: Dict[str, List[ViewPeriod]]

    remaining_hours: float = 0.0

    def __post_init__(self):
        self.remaining_hours = self.duration_hours


@dataclass(frozen=True)
class MaintenanceWindow:
    antenna: str
    start: int
    end: int


@dataclass(frozen=True)
class WeekProblem:
    week: int
    year: int
    requests: List[Request]
    maintenance: List[MaintenanceWindow]


def load_problems(
    problems_path: Path | str, 
    week: int, 
    year: int = 2018
) -> List[Request]:
    with open(problems_path, "r") as f:
        data = json.load(f)

    key = f"W{week}_{year}"
    raw_requests = data[key]

    requests = []
    for r in raw_requests:
        view_periods: Dict[str, List[ViewPeriod]] = {}
        for antenna, vps in r["resource_vp_dict"].items():
            view_periods[antenna] = [
                ViewPeriod(
                    antenna=antenna,
                    trx_on=vp["TRX ON"],
                    trx_off=vp["TRX OFF"],
                )
                for vp in vps
            ]

        requests.append(Request(
            track_id=r["track_id"],
            subject=r["subject"],
            duration_hours=r["duration"],
            duration_min_hours=r["duration_min"],
            setup_seconds=r["setup_time"] * 60,
            teardown_seconds=r["teardown_time"] * 60,
            time_window_start=r["time_window_start"],
            time_window_end=r["time_window_end"],
            view_periods=view_periods,
        ))

    return requests


def load_maintenance(
    maintenance_path: Path | str,
    week: int,
    year: int = 2018,
) -> List[MaintenanceWindow]:
    import csv
    
    windows = []
    with open(maintenance_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if int(float(row["week"])) == week and int(float(row["year"])) == year:
                windows.append(MaintenanceWindow(
                    antenna=row["antenna"],
                    start=int(row["starttime"]),
                    end=int(row["endtime"]),
                ))
    return windows


def load_week_problem(
    problems_path: Path | str,
    maintenance_path: Path | str,
    week: int,
    year: int = 2018,
) -> WeekProblem:
    return WeekProblem(
        week=week,
        year=year,
        requests=load_problems(problems_path, week, year),
        maintenance=load_maintenance(maintenance_path, week, year),
    )


DSS_ANTENNAS = [
    "DSS-14", "DSS-24", "DSS-25", "DSS-26",
    "DSS-34", "DSS-35", "DSS-36", "DSS-43",
    "DSS-54", "DSS-55", "DSS-63", "DSS-65",
]


def get_antenna_list(antenna_key: str) -> List[str]:
    return antenna_key.split("_")


def get_missions(requests: List[Request]) -> Dict[int, List[Request]]:
    missions: Dict[int, List[Request]] = {}
    for req in requests:
        if req.subject not in missions:
            missions[req.subject] = []
        missions[req.subject].append(req)
    return missions
