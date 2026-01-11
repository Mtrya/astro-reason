# Mission Update: Stereo Imaging

## Your Task

You are controlling **15 satellites** from the SPOT, WORLDVIEW, ALOS constellations. Your mission is to capture **stereo pairs** (two images of the same target from different angles) for a set of high-value targets. Horizon: 2025-07-17T12:00:00Z to 2025-07-21T12:00:00Z.

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

- **Qincheng** (ID: `city_qincheng_cn`)
  - Location: 34.58°, 105.72°
- **Cinere** (ID: `city_cinere_id`)
  - Location: -6.33°, 106.78°
- **Multai** (ID: `city_multai_in`)
  - Location: 21.77°, 78.25°
- **Cerquilho Velho** (ID: `city_cerquilho_velho_br`)
  - Location: -23.16°, -47.74°
- **Manhattan** (ID: `city_manhattan_us_1`)
  - Location: 39.19°, -96.60°
- **Grand-Lahou** (ID: `city_grand_lahou_ci`)
  - Location: 5.13°, -5.02°
- **Mariupol** (ID: `city_mariupol_ua`)
  - Location: 47.10°, 37.55°
- **Kilosa** (ID: `city_kilosa_tz`)
  - Location: -6.83°, 36.99°
- **Salaberry-de-Valleyfield** (ID: `city_salaberry_de_valleyfield_ca`)
  - Location: 45.25°, -74.13°
- **Darhan** (ID: `city_darhan_mn`)
  - Location: 49.49°, 105.92°
- **Edmonton** (ID: `city_edmonton_ca`)
  - Location: 53.53°, -113.49°
- **Ushuaia** (ID: `city_ushuaia_ar`)
  - Location: -54.80°, -68.30°
- **Apia** (ID: `city_apia_ws`)
  - Location: -13.83°, -171.75°
- **Dunedin** (ID: `city_dunedin_nz`)
  - Location: -45.87°, 170.50°
- **Sumilao** (ID: `city_sumilao_ph`)
  - Location: 8.33°, 124.98°


### Ground Stations
(Use `query_stations` to see available downlink options)

## Final Advice

You are the sole authority for this mission. No human operators are available to assist. You must independently query your assets, calculate access windows, and manage resource constraints to build a successful plan. Commit to your decisions and produce a schedule that maximizes the mission objectives. The outcome rests entirely on your ability to autonomously manage these complex trade-offs.
