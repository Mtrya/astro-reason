"""Load archived YAML catalogs for benchmarks.

This module provides functions to load satellite, target, and station catalogs
from the archived YAML files in src/benchmark/config/.

Note: These load raw dictionaries (not engine model objects) to preserve metadata
fields like id, name, constellation, etc. that are needed for filtering and YAML output.
"""

from pathlib import Path
from typing import List, Dict, Any
import yaml


BENCHMARK_DATA_DIR = Path(__file__).parent.parent / "config"


def load_archived_satellites() -> List[Dict[str, Any]]:
    """Load all satellites from archived catalog.
    
    Returns:
        List of satellite dictionaries with all metadata fields.
    """
    catalog_path = BENCHMARK_DATA_DIR / "archived_satellites.yaml"
    with open(catalog_path) as f:
        data = yaml.safe_load(f)
    
    return data


def load_archived_targets() -> List[Dict[str, Any]]:
    """Load all targets (cities) from archived catalog.
    
    Returns:
        List of target dictionaries with all metadata fields.
    """
    catalog_path = BENCHMARK_DATA_DIR / "archived_cities.yaml"
    with open(catalog_path) as f:
        data = yaml.safe_load(f)
    
    return data


def load_archived_stations() -> List[Dict[str, Any]]:
    """Load all ground stations from archived catalog.
    
    Returns:
        List of station dictionaries with all metadata fields.
    """
    catalog_path = BENCHMARK_DATA_DIR / "archived_facilities.yaml"
    with open(catalog_path) as f:
        data = yaml.safe_load(f)
    
    return data
