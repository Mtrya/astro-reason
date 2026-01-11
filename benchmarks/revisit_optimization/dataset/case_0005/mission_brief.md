# Mission Update: Revisit Optimization

## Your Task

You are controlling **70 satellites** from the METEOR constellation. Your mission is to minimize the **revisit gap** (time between observations) for high-priority targets over a calculated period (2025-07-17T12:00:00Z to 2025-07-21T12:00:00Z).

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

- **Metpalli** (ID: `city_metpalli_in`)
  - Location: 18.85°, 78.63°
  - Objective: Minimize Revisit Gap
- **Invercargill** (ID: `city_invercargill_nz`)
  - Location: -46.43°, 168.36°
  - Objective: Minimize Revisit Gap
- **Ulan-Ude** (ID: `city_ulan_ude_ru`)
  - Location: 51.83°, 107.60°
  - Objective: Minimize Revisit Gap
- **Szczecin** (ID: `city_szczecin_pl`)
  - Location: 53.43°, 14.55°
  - Objective: Minimize Revisit Gap
- **Papeete** (ID: `city_papeete_pf`)
  - Location: -17.53°, -149.57°
  - Objective: Minimize Revisit Gap
- **Cuenca** (ID: `city_cuenca_ec`)
  - Location: -2.90°, -79.00°
  - Objective: Minimize Revisit Gap
- **Superior** (ID: `city_superior_us`)
  - Location: 46.69°, -92.08°
  - Objective: Minimize Revisit Gap
- **Ushuaia** (ID: `city_ushuaia_ar`)
  - Location: -54.80°, -68.30°
  - Objective: Minimize Revisit Gap

### Mapping Targets (Quota-based Observations)

These targets require a minimum number of successful observations during the mission horizon.

- **Antsampandrano** (ID: `city_antsampandrano_mg`)
  - Location: -19.92°, 47.57°
  - Required Observations: 4
- **Meaux** (ID: `city_meaux_fr`)
  - Location: 48.96°, 2.89°
  - Required Observations: 3
- **Christchurch** (ID: `city_christchurch_nz`)
  - Location: -43.53°, 172.64°
  - Required Observations: 2
- **O'Fallon** (ID: `city_o_fallon_us_1`)
  - Location: 38.60°, -89.91°
  - Required Observations: 2
- **San Bernardo** (ID: `city_san_bernardo_cl`)
  - Location: -33.58°, -70.70°
  - Required Observations: 4
- **Baramati** (ID: `city_baramati_in`)
  - Location: 18.15°, 74.58°
  - Required Observations: 3
- **Rimouski** (ID: `city_rimouski_ca`)
  - Location: 48.45°, -68.53°
  - Required Observations: 2
- **Cuauhtemoc** (ID: `city_cuauhtemoc_mx_1`)
  - Location: 19.33°, -103.60°
  - Required Observations: 4
- **Ban Sai Ma Tai** (ID: `city_ban_sai_ma_tai_th`)
  - Location: 13.86°, 100.47°
  - Required Observations: 3


### Ground Stations
(Use `query_stations` to see available downlink options)

## Final Advice

You are the sole authority for this mission. No human operators are available to assist. You must independently query your assets, calculate access windows, and manage resource constraints to build a successful plan. Commit to your decisions and produce a schedule that maximizes the mission objectives. The outcome rests entirely on your ability to autonomously manage these complex trade-offs.
