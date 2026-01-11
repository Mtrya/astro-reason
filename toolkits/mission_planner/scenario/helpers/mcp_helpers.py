"""MCP Server helpers for LLM-friendly data transformation."""

from dataclasses import is_dataclass, fields
from datetime import datetime
from typing import Any, Dict, List, TypeVar

from toolkits.mission_planner.scenario.models.metrics import SatelliteMetrics

T = TypeVar("T")


def to_llm_dict(obj: Any, ndigits: int = 3) -> Dict[str, Any]:
    """Convert dataclass to dict, round floats, remove None values."""
    if obj is None:
        return None

    if is_dataclass(obj) and not isinstance(obj, type):
        result = {}
        for f in fields(obj):
            value = getattr(obj, f.name)
            converted = _convert_value(value, ndigits)
            if converted is not None:
                result[f.name] = converted
        return result

    if isinstance(obj, dict):
        return {k: _convert_value(v, ndigits) for k, v in obj.items() if _convert_value(v, ndigits) is not None}

    return _convert_value(obj, ndigits)


def _convert_value(value: Any, ndigits: int) -> Any:
    """Convert a single value for LLM consumption."""
    if value is None:
        return None
    if isinstance(value, float):
        return round(value, ndigits)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_convert_value(v, ndigits) for v in value]
    if isinstance(value, tuple):
        return [_convert_value(v, ndigits) for v in value]
    if isinstance(value, dict):
        return {k: _convert_value(v, ndigits) for k, v in value.items() if _convert_value(v, ndigits) is not None}
    if is_dataclass(value) and not isinstance(value, type):
        return to_llm_dict(value, ndigits)
    return value


def paginate(items: List[T], offset: int, limit: int) -> List[T]:
    """Apply pagination to a list of items."""
    start = max(0, offset)
    end = start + max(1, limit)
    return items[start:end]


def filter_items(items: List[T], filters: Dict[str, Any], key_fn) -> List[T]:
    """Apply filters to a list of items."""
    from toolkits.mission_planner.scenario.helpers import record_matches_filters

    if not filters:
        return items

    return [item for item in items if record_matches_filters(key_fn(item), filters)]


def format_satellite_summary(metrics: SatelliteMetrics) -> str:
    """Format satellite metrics as human-readable summary string."""
    p_status = "OK"
    if metrics.power_violated:
        p_status = "VIOLATED"
    
    s_status = "OK"
    if metrics.storage_violated:
        s_status = "VIOLATED"

    return f"{metrics.satellite_id}: {metrics.obs_count} obs, {metrics.downlink_count} dls [Pwr: {p_status}, Stor: {s_status}]"
