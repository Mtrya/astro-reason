"""
Computes satellite lighting conditions using the Astrox API.
"""

import requests
from datetime import datetime
from typing import List, Dict, Any

from ..models import Satellite, LightingWindow, LightingCondition

# TODO: Move to a configuration file
ASTROX_API_URL = "http://astrox.cn:8765"


class AstroxAPIError(Exception):
    """Custom exception for Astrox API errors."""

    pass


def _build_lighting_payload(
    satellite: Satellite, start_time: datetime, end_time: datetime
) -> Dict[str, Any]:
    """Helper to construct the JSON payload for the Astrox LightingTimes endpoint.

    LightingTimesInput schema requires:
      - Start / Stop (ISO8601 UTC)
      - Position as IEntityPosition2; for TLE-based satellites we use SGP4.
    """
    start_iso = start_time.isoformat().replace("+00:00", "Z")
    end_iso = end_time.isoformat().replace("+00:00", "Z")
    return {
        "Start": start_iso,
        "Stop": end_iso,
        "Position": {
            "$type": "SGP4",
            "TLEs": [satellite.tle_line1, satellite.tle_line2],
        },
        # OccultationBodies omitted -> API uses defaults (Earth/Moon) per schema docs.
    }


def compute_lighting_windows(
    satellite: Satellite, time_window: tuple[datetime, datetime]
) -> List[LightingWindow]:
    """
    Computes all lighting windows (sunlight, penumbra, umbra) for a satellite.

    Args:
        satellite: The satellite object with TLE data.
        time_window: A tuple containing the start and end datetime objects.

    Returns:
        A list of LightingWindow objects.

    Raises:
        AstroxAPIError: If the API call fails or returns an error.
    """
    start_time, end_time = time_window
    payload = _build_lighting_payload(satellite, start_time, end_time)

    try:
        response = requests.post(
            f"{ASTROX_API_URL}/Lighting/LightingTimes", json=payload, timeout=60
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise AstroxAPIError(f"Astrox API request failed: {e}") from e

    data = response.json()

    if not data.get("IsSuccess"):
        error_message = data.get("Message", "Unknown error")
        raise AstroxAPIError(f"Astrox API returned an error: {error_message}")

    windows = []

    sunlights = data.get("SunLight", None)
    if sunlights is not None and isinstance(sunlights, dict) and "Intervals" in sunlights:
        intervals = sunlights["Intervals"]
        for interval in intervals:
            start = datetime.fromisoformat(interval["Start"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(interval["Stop"].replace("Z", "+00:00"))
            duration = (end - start).total_seconds()
            windows.append(LightingWindow(start=start, end=end, duration_sec=duration, condition=LightingCondition.SUNLIGHT))

    penumbras = data.get("Penumbra", None)
    if penumbras is not None and isinstance(penumbras, dict) and "Intervals" in penumbras:
        intervals = penumbras["Intervals"]
        for interval in intervals:
            start = datetime.fromisoformat(interval["Start"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(interval["Stop"].replace("Z", "+00:00"))
            duration = (end - start).total_seconds()
            windows.append(LightingWindow(start=start, end=end, duration_sec=duration, condition=LightingCondition.PENUMBRA))

    umbras = data.get("Umbra", None)
    if umbras is not None and isinstance(umbras, dict) and "Intervals" in umbras:
        intervals = umbras["Intervals"]
        for interval in intervals:
            start = datetime.fromisoformat(interval["Start"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(interval["Stop"].replace("Z", "+00:00"))
            duration = (end - start).total_seconds()
            windows.append(LightingWindow(start=start, end=end, duration_sec=duration, condition=LightingCondition.UMBRA))

    return windows
