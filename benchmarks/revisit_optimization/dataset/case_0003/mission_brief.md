# Mission Update: Revisit Optimization

## Your Task

You are controlling **100 satellites** from the COSMOS constellation. Your mission is to minimize the **revisit gap** (time between observations) for high-priority targets over a calculated period (2025-07-17T12:00:00Z to 2025-07-21T12:00:00Z).

## Mission Objectives

**Primary Goal**: Maximize the mission utility by ensuring all mapping targets meet their required observation counts while minimizing the revisit gap for all monitoring targets.

### Scoring Metrics

Your plan will receive a score based on how well you minimize gaps for monitoring targets and fulfill quotas for mapping targets:


1.  **Monitoring Quality (Revisit Gap)**: For high-priority monitoring targets, minimize the maximum and average time gaps between consecutive observations. Smaller gaps indicate better responsiveness.
2.  **Mapping Completeness (Coverage Ratio)**: For mapping targets, ensure at least the required number of observations are completed.
3.  **Plan Validity**: Your plan must satisfy all physical constraints (battery, storage, slew time).


## Constraints (Hard Physical Limits)

These will invalidate your plan if violated:
- **Battery**: Must satisfy `capacity_wh > 0`.
- **Storage**: Must satisfy `storage_used_mb <= capacity_mb`.
- **Slew**: Satellite must have enough time to slew between targets.

## Mission-Specific Data

### Monitoring Targets (Continuous Monitoring Required)

These targets require continuous monitoring. Your goal is to **minimize the revisit gap** (time between any two consecutive observations) as much as possible.

Note: The revisit gap calculation includes the time from the start of the mission to the first observation, and from the last observation to the end of the mission horizon.

- **Sakarya** (ID: `city_sakarya_tr`)
  - Location: 40.78°, 30.40°
  - Objective: Minimize Revisit Gap
- **Comodoro Rivadavia** (ID: `city_comodoro_rivadavia_ar`)
  - Location: -45.86°, -67.48°
  - Objective: Minimize Revisit Gap
- **Gloria** (ID: `city_gloria_ph`)
  - Location: 12.97°, 121.48°
  - Objective: Minimize Revisit Gap
- **Nuku`alofa** (ID: `city_nuku_alofa_to`)
  - Location: -21.13°, -175.20°
  - Objective: Minimize Revisit Gap
- **Invercargill** (ID: `city_invercargill_nz`)
  - Location: -46.43°, 168.36°
  - Objective: Minimize Revisit Gap
- **Arraijan** (ID: `city_arraijan_pa`)
  - Location: 8.94°, -79.64°
  - Objective: Minimize Revisit Gap
- **Kettering** (ID: `city_kettering_us`)
  - Location: 39.70°, -84.15°
  - Objective: Minimize Revisit Gap
- **Xai-Xai** (ID: `city_xai_xai_mz`)
  - Location: -25.05°, 33.65°
  - Objective: Minimize Revisit Gap
- **Sunrise Manor** (ID: `city_sunrise_manor_us`)
  - Location: 36.18°, -115.05°
  - Objective: Minimize Revisit Gap
- **Czechowice-Dziedzice** (ID: `city_czechowice_dziedzice_pl`)
  - Location: 49.91°, 19.01°
  - Objective: Minimize Revisit Gap
- **Jobabo** (ID: `city_jobabo_cu`)
  - Location: 20.91°, -77.28°
  - Objective: Minimize Revisit Gap
- **Yotsukaido** (ID: `city_yotsukaido_jp`)
  - Location: 35.67°, 140.17°
  - Objective: Minimize Revisit Gap

### Mapping Targets (Quota-based Observations)

These targets require a minimum number of successful observations during the mission horizon.

- **San Andres Tuxtla** (ID: `city_san_andres_tuxtla_mx`)
  - Location: 18.45°, -95.21°
  - Required Observations: 3
- **Moncton** (ID: `city_moncton_ca`)
  - Location: 46.13°, -64.77°
  - Required Observations: 3
- **Saparua** (ID: `city_saparua_id`)
  - Location: -3.57°, 128.65°
  - Required Observations: 4
- **Redmond** (ID: `city_redmond_us`)
  - Location: 47.68°, -122.12°
  - Required Observations: 3
- **Southall** (ID: `city_southall_gb`)
  - Location: 51.51°, -0.38°
  - Required Observations: 4
- **Hanyu** (ID: `city_hanyu_jp`)
  - Location: 36.17°, 139.55°
  - Required Observations: 4
- **San Pascual** (ID: `city_san_pascual_ph_1`)
  - Location: 13.13°, 122.98°
  - Required Observations: 2
- **Shiyali** (ID: `city_shiyali_in`)
  - Location: 11.24°, 79.74°
  - Required Observations: 2
- **Norwood** (ID: `city_norwood_us`)
  - Location: 42.19°, -71.19°
  - Required Observations: 3
- **Catende** (ID: `city_catende_br`)
  - Location: -8.67°, -35.72°
  - Required Observations: 3
- **Ejido** (ID: `city_ejido_ve`)
  - Location: 8.33°, -71.40°
  - Required Observations: 4
- **San Felipe** (ID: `city_san_felipe_gt`)
  - Location: 14.62°, -91.60°
  - Required Observations: 4
- **Daqing** (ID: `city_daqing_cn`)
  - Location: 46.59°, 125.10°
  - Required Observations: 3


### Ground Stations
(Use `query_stations` to see available downlink options)

## Final Advice

You are the sole authority for this mission. No human operators are available to assist. You must independently query your assets, calculate access windows, and manage resource constraints to build a successful plan. Commit to your decisions and produce a schedule that maximizes the mission objectives. The outcome rests entirely on your ability to autonomously manage these complex trade-offs.
