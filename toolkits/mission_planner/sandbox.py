"""Sandbox utilities for agent Python scripts.

This module provides helper functions for agent-generated Python scripts
to interact with the planner Scenario with file-backed state persistence.

Usage:
    from toolkits.mission_planner.scenario.sandbox import satellite_session
    
    with satellite_session() as scenario:
        # Query and plan
        satellites = scenario.get_satellites()
        for sat in satellites[:3]:
            windows = scenario.compute_access_windows(
                sat_ids=[sat.id],
                target_ids=[...],
                station_ids=None,
                peer_satellite_ids=None,
                start_time="2024-01-01T00:00:00Z",
                end_time="2024-01-02T00:00:00Z"
            )
            scenario.register_windows(windows)
            
            for window in windows[:5]:
                scenario.stage_action({
                    "type": "observation",
                    "satellite_id": sat.id,
                    "target_id": window.target_id,
                    "window_id": window.window_id
                })
        
        # Commit is optional - state auto-saves on clean exit
        scenario.commit_plan()
    # State is automatically saved on context exit
"""

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from toolkits.mission_planner.scenario.scenario import Scenario
from toolkits.mission_planner.scenario.state import StateFile


def get_case_path() -> Path:
    """Get the case directory path from environment.
    
    Returns Path to case directory containing YAML files.
    
    Raises:
        RuntimeError: If neither CASE_PATH nor ASTROX_CASE_PATH set.
    """
    case_path = os.environ.get("CASE_PATH") or os.environ.get("ASTROX_CASE_PATH")
    if not case_path:
        raise RuntimeError(
            "Neither CASE_PATH nor ASTROX_CASE_PATH environment variable set. "
            "Set it to the case directory containing YAML files."
        )
    
    case_dir = Path(case_path)
    if not case_dir.exists():
        raise RuntimeError(f"Case directory not found: {case_dir}")
    
    return case_dir


def get_state_path() -> Path:
    """Get state file path.
    
    Priority:
    1. ASTROX_STATE_PATH environment variable
    2. HOME/state/scenario.json
    
    Returns:
        Path to state file
    """
    path = os.environ.get("ASTROX_STATE_PATH")
    if path:
        return Path(path)
    
    return Path.home() / "state" / "scenario.json"


@contextmanager
def satellite_session() -> Iterator[Scenario]:
    """Context manager for atomic scenario operations.
    
    Acquires exclusive file lock, loads state, yields scenario instance,
    and saves state on CLEAN exit only. If an exception is raised within
    the context, state changes are discarded.
    
    All operations within the context are atomic with respect to 
    concurrent MCP tool calls or other scripts.
    
    Example:
        with satellite_session() as scenario:
            scenario.stage_action({...})
            scenario.stage_action({...})
        # State automatically saved here (only if no exception)
    
    Raises:
        RuntimeError: If CASE_PATH not set or case directory doesn't exist.
    
    Note:
        This context manager always acquires an EXCLUSIVE lock, which
        blocks concurrent MCP read operations. If you only need to
        inspect state without mutations, use load_scenario_readonly()
        instead to allow concurrent access.
    """
    case_dir = get_case_path()
    state_path = get_state_path()
    
    satellite_file = case_dir / "satellites.yaml"
    target_file = case_dir / "targets.yaml"
    station_file = case_dir / "stations.yaml"
    plan_file = case_dir / "initial_plan.json"
    
    # Check required files
    for f, name in [(satellite_file, "satellites.yaml"), 
                     (target_file, "targets.yaml"),
                     (station_file, "stations.yaml")]:
        if not f.exists():
            raise RuntimeError(f"Required file not found: {name} in {case_dir}")
    
    # initial_plan.json is optional but must exist for base scenario
    if not plan_file.exists():
        raise RuntimeError(f"Required file not found: initial_plan.json in {case_dir}")
    
    state_file = StateFile(state_path)
    
    with state_file.lock(exclusive=True):
        # Load state if exists, otherwise create fresh
        state_dict = state_file.read()
        
        if state_dict:
            # Restore from state
            scenario = Scenario.from_state(
                satellite_file=str(satellite_file),
                target_file=str(target_file),
                station_file=str(station_file),
                plan_file=str(plan_file),
                state_dict=state_dict,
            )
        else:
            # Initialize fresh scenario
            scenario = Scenario(
                satellite_file=str(satellite_file),
                target_file=str(target_file),
                station_file=str(station_file),
                plan_file=str(plan_file),
            )
        
        # Track whether we should save state
        save_state = False
        try:
            yield scenario
            # Only mark for save if no exception occurred
            save_state = True
        finally:
            # Only write if the context exited cleanly
            if save_state:
                state_file.write(scenario.export_to_state())


def load_scenario_readonly() -> Scenario:
    """Load scenario for read-only access (no automatic save).
    
    Use this when you only need to query the current state without making changes.
    Acquires a shared lock, allowing concurrent read access.
    
    Note: Changes made to the returned scenario will NOT be persisted.
    
    Returns:
        Scenario: A scenario instance loaded from current state or fresh if no state exists.
        
    Raises:
        RuntimeError: If CASE_PATH not set or case directory doesn't exist.
    """
    case_dir = get_case_path()
    state_path = get_state_path()
    
    satellite_file = case_dir / "satellites.yaml"
    target_file = case_dir / "targets.yaml"
    station_file = case_dir / "stations.yaml"
    plan_file = case_dir / "initial_plan.json"
    
    # Check required files
    for f, name in [(satellite_file, "satellites.yaml"), 
                     (target_file, "targets.yaml"),
                     (station_file, "stations.yaml"),
                     (plan_file, "initial_plan.json")]:
        if not f.exists():
            raise RuntimeError(f"Required file not found: {name} in {case_dir}")
    
    state_file = StateFile(state_path)
    
    with state_file.lock(exclusive=False):
        state_dict = state_file.read()
        
        if state_dict:
            return Scenario.from_state(
                satellite_file=str(satellite_file),
                target_file=str(target_file),
                station_file=str(station_file),
                plan_file=str(plan_file),
                state_dict=state_dict,
            )
        else:
            return Scenario(
                satellite_file=str(satellite_file),
                target_file=str(target_file),
                station_file=str(station_file),
                plan_file=str(plan_file),
            )


def load_scenario() -> Scenario:
    """Load scenario from case directory (legacy, no locking).
    
    DEPRECATED: Use satellite_session() for write operations or
    load_scenario_readonly() for read operations instead.
    
    This function provides backward compatibility but does NOT
    use file locking or state persistence. Changes will NOT be
    saved automatically.
    
    The case directory should contain:
    - satellites.yaml
    - targets.yaml
    - stations.yaml
    - initial_plan.json
    
    Returns:
        Scenario: Initialized scenario instance.
    
    Raises:
        RuntimeError: If CASE_PATH not set or required files missing.
    
    Example:
        scenario = load_scenario()
        satellites = scenario.get_satellites()
        targets = scenario.get_targets()
        
        # Compute access windows
        windows = scenario.compute_access_windows(...)
        scenario.register_windows(windows)
        
        # Stage actions
        scenario.stage_action({...})
        
        # Commit plan (writes to plan.json but without locking)
        scenario.commit_plan()
    """
    case_dir = get_case_path()
    
    satellite_file = case_dir / "satellites.yaml"
    target_file = case_dir / "targets.yaml"
    station_file = case_dir / "stations.yaml"
    plan_file = case_dir / "initial_plan.json"
    
    # Check required files
    for f, name in [(satellite_file, "satellites.yaml"), 
                     (target_file, "targets.yaml"),
                     (station_file, "stations.yaml")]:
        if not f.exists():
            raise RuntimeError(f"Required file not found: {name} in {case_dir}")
    
    # initial_plan.json is optional
    if not plan_file.exists():
        plan_file = None
    
    return Scenario(
        satellite_file=str(satellite_file),
        target_file=str(target_file),
        station_file=str(station_file),
        plan_file=str(plan_file) if plan_file else None,
    )
