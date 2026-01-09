"""Catalog filtering utilities."""

import re
from difflib import SequenceMatcher
from typing import Any, Dict, List


def _match_string(value: str, criterion: Dict[str, Any] | str | List[str]) -> bool:
    """Match strings using exact, regex, contains, or fuzzy (SequenceMatcher) logic."""
    if isinstance(criterion, list):
        return value in criterion
    if isinstance(criterion, str):
        # Check if the string contains regex special characters
        if re.search(r'[.^$*+?{}[\]\\|()]', criterion):
            return re.search(criterion, value, re.IGNORECASE) is not None
        else:
            return value == criterion
    if not isinstance(criterion, dict):
        return False

    ignore_case = criterion.get("ignore_case", True)
    haystack = value.lower() if ignore_case else value

    if "regex" in criterion and isinstance(criterion["regex"], str):
        flags = re.IGNORECASE if ignore_case else 0
        return re.search(criterion["regex"], value, flags) is not None

    if "contains" in criterion and isinstance(criterion["contains"], str):
        needle = criterion["contains"].lower() if ignore_case else criterion["contains"]
        return needle in haystack

    if "fuzzy" in criterion and isinstance(criterion["fuzzy"], str):
        cutoff = float(criterion.get("min_ratio", 0.6))
        ratio = SequenceMatcher(
            None,
            haystack,
            criterion["fuzzy"].lower() if ignore_case else criterion["fuzzy"],
        ).ratio()
        return ratio >= cutoff

    return False


def _match_numeric(value: Any, criterion: Dict[str, Any] | float | int) -> bool:
    """Match numeric fields with optional inequality operators."""
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return False

    if isinstance(criterion, dict):
        if "gt" in criterion and not numeric_value > float(criterion["gt"]):
            return False
        if "gte" in criterion and not numeric_value >= float(criterion["gte"]):
            return False
        if "lt" in criterion and not numeric_value < float(criterion["lt"]):
            return False
        if "lte" in criterion and not numeric_value <= float(criterion["lte"]):
            return False
        if "eq" in criterion and not numeric_value == float(criterion["eq"]):
            return False
        return True

    if isinstance(criterion, (int, float)):
        return numeric_value == float(criterion)

    return False


def _match_value(value: Any, criterion: Any) -> bool:
    """Dispatch matcher based on value type."""
    if value is None:
        return False

    if isinstance(value, (int, float)):
        return _match_numeric(value, criterion)

    if isinstance(value, str):
        if isinstance(criterion, dict):
            return _match_string(value, criterion)
        if isinstance(criterion, list):
            return value in criterion
        return value == criterion

    return value == criterion


def record_matches_filters(record: Dict[str, Any], filters: Dict[str, Any]) -> bool:
    """
    Check if a record matches all filters.
    
    - exact matches for scalars
    - regex / contains / fuzzy for strings
    - gt/gte/lt/lte for numerics
    - list values mean membership
    """
    if not filters:
        return True

    for key, criterion in filters.items():
        if key == "names":
            if not _match_string(record.get("name", ""), criterion):
                return False
            continue

        if key not in record:
            return False

        if not _match_value(record[key], criterion):
            return False

    return True


def filter_catalog(
    records: Dict[str, Dict[str, Any]], filters: Dict[str, Any] | None
) -> List[Dict[str, Any]]:
    """Apply filter logic and return shallow copies of matching records."""
    if not filters:
        return [dict(rec) for rec in records.values()]

    results: List[Dict[str, Any]] = []
    for rec in records.values():
        if record_matches_filters(rec, filters):
            results.append(dict(rec))
    return results