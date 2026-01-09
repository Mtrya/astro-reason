"""State persistence for SatNet scenario with file locking."""

import fcntl
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, Iterator


STATE_VERSION = 1


@dataclass
class SatNetState:
    """Serializable scenario state."""
    problems_path: str
    maintenance_path: str
    week: int
    year: int
    action_counter: int
    scheduled_tracks: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": STATE_VERSION,
            "config": {
                "problems_path": self.problems_path,
                "maintenance_path": self.maintenance_path,
                "week": self.week,
                "year": self.year,
            },
            "action_counter": self.action_counter,
            "scheduled_tracks": self.scheduled_tracks,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SatNetState":
        version = data.get("version", 1)
        if version != STATE_VERSION:
            raise ValueError(f"Unsupported state version: {version}")

        config = data["config"]
        return cls(
            problems_path=config["problems_path"],
            maintenance_path=config["maintenance_path"],
            week=config["week"],
            year=config["year"],
            action_counter=data["action_counter"],
            scheduled_tracks=data.get("scheduled_tracks", {}),
        )


class SatNetStateFile:
    """Thread-safe state file manager with fcntl locking."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    @contextmanager
    def lock(self, exclusive: bool = True) -> Iterator[None]:
        """Acquire file lock. Use exclusive=True for writes, False for reads."""
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.touch(exist_ok=True)

        lock_mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        with open(self.lock_path, "r") as lock_file:
            fcntl.flock(lock_file.fileno(), lock_mode)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def read(self) -> SatNetState | None:
        """Read state from file. Returns None if file doesn't exist."""
        if not self.path.exists():
            return None
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return SatNetState.from_dict(data)

    def write(self, state: SatNetState) -> None:
        """Write state to file atomically."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, indent=2)
        os.rename(tmp_path, self.path)

    def initialize(
        self,
        problems_path: str,
        maintenance_path: str,
        week: int,
        year: int = 2018,
    ) -> None:
        """Initialize a fresh state file."""
        state = SatNetState(
            problems_path=problems_path,
            maintenance_path=maintenance_path,
            week=week,
            year=year,
            action_counter=0,
            scheduled_tracks={},
        )
        self.write(state)

    def exists(self) -> bool:
        """Check if state file exists."""
        return self.path.exists()
