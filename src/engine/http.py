"""
HTTP client utilities with retry logic for Astrox API calls.
"""

import time
import requests

RETRY_COUNT = 10
RETRY_BASE_DELAY_SEC = 0.1


def post_with_retry(url: str, json: dict, timeout: float = 60) -> requests.Response:
    """
    POST request with exponential backoff retry.
    
    Args:
        url: Target URL.
        json: JSON payload.
        timeout: Request timeout in seconds.
        
    Returns:
        Response object on success.
        
    Raises:
        requests.exceptions.RequestException: After all retries exhausted.
    """
    last_exception = None
    for attempt in range(RETRY_COUNT):
        try:
            resp = requests.post(url, json=json, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            last_exception = e
            if attempt < RETRY_COUNT - 1:
                delay = RETRY_BASE_DELAY_SEC * (2 ** attempt)
                time.sleep(delay)
    raise last_exception
