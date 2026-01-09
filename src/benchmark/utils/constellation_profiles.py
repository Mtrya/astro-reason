"""Load and query constellation profiles.

This module provides functions to load constellation profiles from the YAML configuration
and query specific profiles by name.
"""

from pathlib import Path
from typing import Dict, Any
import yaml


CONFIG_DIR = Path(__file__).parent.parent / "config"


def load_constellation_profiles() -> Dict[str, Dict[str, Any]]:
    """Load constellation profiles from YAML configuration.
    
    Returns:
        Dictionary mapping constellation names to profile dictionaries.
    """
    profile_path = CONFIG_DIR / "constellation_profiles.yaml"
    with open(profile_path) as f:
        profiles = yaml.safe_load(f)
    
    return profiles


def get_profile(name: str) -> Dict[str, Any]:
    """Get a specific constellation profile by name.
    
    Args:
        name: Constellation name (e.g., "METEOR", "SPOT", "SKYLINK").
    
    Returns:
        Profile dictionary with physical parameters.
        
    Raises:
        KeyError: If profile name not found.
    """
    profiles = load_constellation_profiles()
    
    if name in profiles:
        return profiles[name]
    
    return profiles["DEFAULT"]
