"""Sandbox API for agent scripts.

This module provides a simple interface for agent-generated Python scripts
to interact with the SatNet scenario through file-based state persistence.

Usage:
    from satnet_agent.sandbox import satnet_session
    
    with satnet_session() as scenario:
        requests = scenario.list_unsatisfied_requests()
        for req in requests:
            windows = scenario.find_view_periods(req.request_id)
            if windows:
                scenario.schedule_track(
                    request_id=req.request_id,
                    antenna=windows[0].antenna,
                    trx_on=windows[0].start_seconds,
                    trx_off=windows[0].end_seconds,
                )
        scenario.commit_plan()
    # State is automatically saved on context exit
"""

import os
from contextlib import contextmanager
from typing import Iterator

from .state import SatNetStateFile
from .scenario import SatNetScenario


def get_state_file() -> SatNetStateFile:
    """Get state file path.
    
    Uses $HOME/state/scenario.json by default, consistent with mcp_server.py.
    This ensures local testing and benchmarking use the same path resolution.
    """
    home = os.environ.get("HOME", ".")
    path = os.environ.get("SATNET_STATE_PATH", f"{home}/state/scenario.json")
    return SatNetStateFile(path)


@contextmanager
def satnet_session() -> Iterator[SatNetScenario]:
    """Context manager for atomic scenario operations.
    
    Acquires exclusive file lock, loads state, yields scenario instance,
    and saves state on CLEAN exit only. If an exception is raised within
    the context, state changes are discarded.
    
    All operations within the context are atomic with respect to 
    concurrent MCP tool calls.
    
    Example:
        with satnet_session() as scenario:
            scenario.schedule_track(...)
            scenario.schedule_track(...)
        # State automatically saved here (only if no exception)
    
    Raises:
        RuntimeError: If state file is not initialized.
    
    Note:
        This context manager always acquires an EXCLUSIVE lock, which
        blocks concurrent MCP read operations. If you only need to
        inspect state without mutations, use load_scenario_readonly()
        instead to allow concurrent access.
    """
    state_file = get_state_file()
    with state_file.lock(exclusive=True):
        state = state_file.read()
        if state is None:
            raise RuntimeError(
                "State file not initialized. The MCP server should have "
                "initialized it on startup."
            )
        scenario = SatNetScenario.from_state(state)
        
        # Track whether we should save state
        save_state = False
        try:
            yield scenario
            # Only mark for save if no exception occurred
            save_state = True
        finally:
            # Only write if the context exited cleanly
            if save_state:
                state_file.write(scenario.to_state())


def load_scenario_readonly() -> SatNetScenario:
    """Load scenario for read-only access (no automatic save).
    
    Use this when you only need to query the current state without making changes.
    Note: Changes made to the returned scenario will NOT be persisted.
    
    Returns:
        SatNetScenario: A scenario instance loaded from current state.
    """
    state_file = get_state_file()
    with state_file.lock(exclusive=False):
        state = state_file.read()
        if state is None:
            raise RuntimeError("State file not initialized.")
        return SatNetScenario.from_state(state)
