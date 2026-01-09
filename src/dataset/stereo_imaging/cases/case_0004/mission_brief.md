# Mission Update: Stereo Imaging

## Your Task

You are controlling **8 satellites** from the WORLDVIEW, TERRASAR, ZIYUAN constellations. Your mission is to capture **stereo pairs** (two images of the same target from different angles) for a set of high-value targets. Horizon: 2025-07-17T12:00:00Z to 2025-07-21T12:00:00Z.

## Mission Objectives

**Primary Goal**: Maximize the mission utility by acquiring high-quality stereo pairs for as many targets as possible within the physical constraints of the platform.

### Scoring Metrics

Your plan will receive a score based on the following criteria:


1.  **Stereo Yield**: The percentage of high-value targets for which at least one valid stereo pair (two observations meeting angle/time constraints) is successfully acquired.
2.  **Plan Validity**: Your plan must satisfy all physical constraints (battery, storage, slew time).


## Constraints (Hard Physical Limits)

These will invalidate your plan if violated:
- **Battery**: Must satisfy `capacity_wh > 0`.
- **Storage**: Must satisfy `storage_used_mb <= capacity_mb`.
- **Slew**: Satellite must have enough time to slew between targets. Agility is critical for stereo acquisition.

## Mission-Specific Data

### Stereo Target List (High-Priority)

For each target below, you must attempt to collect a **stereo pair**. A valid pair consists of two observations that satisfy the following physical constraints:

**Physical Constraints for Stereo Pairs**:
- **Azimuth Separation**: Between 15.0° and 60.0°
- **Max Temporal Gap**: 2.0 hours between the two observations
- **Min Elevation**: 30.0°

- **Bao Loc** (ID: `city_bao_loc_vn`)
  - Location: 11.55°, 107.81°
- **Rotorua** (ID: `city_rotorua_nz`)
  - Location: -38.14°, 176.25°
- **Khachrod** (ID: `city_khachrod_in`)
  - Location: 23.42°, 75.28°
- **Guanambi** (ID: `city_guanambi_br`)
  - Location: -14.22°, -42.78°
- **Fremont** (ID: `city_fremont_us`)
  - Location: 37.53°, -121.98°
- **Taunton** (ID: `city_taunton_us`)
  - Location: 41.90°, -71.09°
- **Hoboken** (ID: `city_hoboken_be`)
  - Location: 51.17°, 4.37°
- **Mwanza** (ID: `city_mwanza_tz`)
  - Location: -2.52°, 32.90°


### Ground Stations
(Use `query_stations` to see available downlink options)

## Final Advice

You are the sole authority for this mission. No human operators are available to assist. You must independently query your assets, calculate access windows, and manage resource constraints to build a successful plan. Commit to your decisions and produce a schedule that maximizes the mission objectives. The outcome rests entirely on your ability to autonomously manage these complex trade-offs.
