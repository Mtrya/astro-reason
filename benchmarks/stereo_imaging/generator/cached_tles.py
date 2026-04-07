"""Vendored Earth-resources TLE snapshot for `SATELLITE_CATALOG` NORAD IDs.

Frozen from CelesTrak Earth Resources GP (`gp.php?GROUP=resource&FORMAT=tle`).
The generator writes `dataset/source_data/celestrak/` from this list so dataset
rebuilds do not depend on live element sets or network fetches for TLEs.

When `SATELLITE_CATALOG` gains satellites, add matching rows here (same CSV
schema as `normalize.parse_tle_text` / `sources.download_celestrak` output).
"""

from __future__ import annotations

from typing import Any

# Sorted by norad_catalog_id for stable CSV output and checksums.
CACHED_CELESTRAK_ROWS: list[dict[str, Any]] = [
    {
        "name": "PLEIADES 1A",
        "norad_catalog_id": "38012",
        "tle_line1": "1 38012U 11076F   26096.23539690  .00000494  00000+0  11617-3 0  9994",
        "tle_line2": "2 38012  98.2002 172.2949 0001342  74.1943  10.7084 14.58565955761501",
        "epoch_iso": "2026-04-06T05:38:58.292160Z",
    },
    {
        "name": "SPOT 6",
        "norad_catalog_id": "38755",
        "tle_line1": "1 38755U 12047A   26096.23426606  .00000498  00000+0  11693-3 0  9997",
        "tle_line2": "2 38755  98.2167 164.3679 0001434  83.0887 277.0475 14.58566315722563",
        "epoch_iso": "2026-04-06T05:37:20.587584Z",
    },
    {
        "name": "DEIMOS-2",
        "norad_catalog_id": "40013",
        "tle_line1": "1 40013U 14033D   26096.23274010  .00000166  00000+0  20863-4 0  9996",
        "tle_line2": "2 40013  97.5927 333.2192 0001272 107.9672 252.1687 14.93525641626988",
        "epoch_iso": "2026-04-06T05:35:08.744640Z",
    },
    {
        "name": "SPOT 7",
        "norad_catalog_id": "40053",
        "tle_line1": "1 40053U 14034A   26096.26650635  .00000571  00000+0  12606-3 0  9990",
        "tle_line2": "2 40053  98.0687 160.5936 0001636  90.3404 269.7985 14.60896284626635",
        "epoch_iso": "2026-04-06T06:23:46.148640Z",
    },
    {
        "name": "GAOFEN-2",
        "norad_catalog_id": "40118",
        "tle_line1": "1 40118U 14049A   26096.28245968  .00001468  00000+0  19713-3 0  9991",
        "tle_line2": "2 40118  98.0167 160.5417 0008774 103.7901 256.4289 14.80819438628590",
        "epoch_iso": "2026-04-06T06:46:44.516352Z",
    },
    {
        "name": "ZIYUAN 3-02 (ZY 3-02)",
        "norad_catalog_id": "41556",
        "tle_line1": "1 41556U 16033A   26096.29981155  .00008085  00000+0  36271-3 0  9999",
        "tle_line2": "2 41556  97.3856 173.4419 0013709 182.6366 177.4800 15.21376229547058",
        "epoch_iso": "2026-04-06T07:11:43.717920Z",
    },
]

__all__ = ["CACHED_CELESTRAK_ROWS"]
