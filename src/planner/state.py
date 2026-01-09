"""State persistence for planner scenario with file locking."""

import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator


class StateFile:
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

    def read(self) -> Dict[str, Any] | None:
        """Read state from file. Returns None if file doesn't exist."""
        if not self.path.exists():
            return None
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data

    def write(self, state: Dict[str, Any]) -> None:
        """Write state to file atomically."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.rename(tmp_path, self.path)

    def exists(self) -> bool:
        """Check if state file exists."""
        return self.path.exists()
