# Mission Update: Stereo Imaging

## Your Task

You are controlling **5 satellites** from the TERRASAR, TANDEM, ZIYUAN constellations. Your mission is to capture **stereo pairs** (two images of the same target from different angles) for a set of high-value targets. Horizon: 2025-07-17T12:00:00Z to 2025-07-21T12:00:00Z.

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

- **Yotsukaido** (ID: `city_yotsukaido_jp`)
  - Location: 35.67°, 140.17°
- **Saparua** (ID: `city_saparua_id`)
  - Location: -3.57°, 128.65°
- **Shiyali** (ID: `city_shiyali_in`)
  - Location: 11.24°, 79.74°
- **Catende** (ID: `city_catende_br`)
  - Location: -8.67°, -35.72°
- **San Andres Tuxtla** (ID: `city_san_andres_tuxtla_mx`)
  - Location: 18.45°, -95.21°


### Ground Stations
(Use `query_stations` to see available downlink options)

## Final Advice

You are the sole authority for this mission. No human operators are available to assist. You must independently query your assets, calculate access windows, and manage resource constraints to build a successful plan. Commit to your decisions and produce a schedule that maximizes the mission objectives. The outcome rests entirely on your ability to autonomously manage these complex trade-offs.
