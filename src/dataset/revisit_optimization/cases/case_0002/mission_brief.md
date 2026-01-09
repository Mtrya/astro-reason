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

- **Ushuaia** (ID: `city_ushuaia_ar`)
  - Location: -54.80°, -68.30°
  - Objective: Minimize Revisit Gap
- **Qincheng** (ID: `city_qincheng_cn`)
  - Location: 34.58°, 105.72°
  - Objective: Minimize Revisit Gap
- **Gravina in Puglia** (ID: `city_gravina_in_puglia_it`)
  - Location: 40.82°, 16.42°
  - Objective: Minimize Revisit Gap
- **Salaberry-de-Valleyfield** (ID: `city_salaberry_de_valleyfield_ca`)
  - Location: 45.25°, -74.13°
  - Objective: Minimize Revisit Gap
- **Manhattan** (ID: `city_manhattan_us_1`)
  - Location: 39.19°, -96.60°
  - Objective: Minimize Revisit Gap
- **Cerquilho Velho** (ID: `city_cerquilho_velho_br`)
  - Location: -23.16°, -47.74°
  - Objective: Minimize Revisit Gap
- **Darhan** (ID: `city_darhan_mn`)
  - Location: 49.49°, 105.92°
  - Objective: Minimize Revisit Gap
- **Kilosa** (ID: `city_kilosa_tz`)
  - Location: -6.83°, 36.99°
  - Objective: Minimize Revisit Gap

### Mapping Targets (Quota-based Observations)

These targets require a minimum number of successful observations during the mission horizon.

- **Edmonton** (ID: `city_edmonton_ca`)
  - Location: 53.53°, -113.49°
  - Required Observations: 2
- **Apia** (ID: `city_apia_ws`)
  - Location: -13.83°, -171.75°
  - Required Observations: 2
- **Multai** (ID: `city_multai_in`)
  - Location: 21.77°, 78.25°
  - Required Observations: 2
- **Suceava** (ID: `city_suceava_ro`)
  - Location: 47.65°, 26.26°
  - Required Observations: 3
- **Bra** (ID: `city_bra_it`)
  - Location: 44.70°, 7.85°
  - Required Observations: 3
- **Bridgwater** (ID: `city_bridgwater_gb`)
  - Location: 51.13°, -2.99°
  - Required Observations: 2
- **Dunedin** (ID: `city_dunedin_nz`)
  - Location: -45.87°, 170.50°
  - Required Observations: 4
- **Cinere** (ID: `city_cinere_id`)
  - Location: -6.33°, 106.78°
  - Required Observations: 4
- **Grand-Lahou** (ID: `city_grand_lahou_ci`)
  - Location: 5.13°, -5.02°
  - Required Observations: 2


### Ground Stations
(Use `query_stations` to see available downlink options)

## Final Advice

You are the sole authority for this mission. No human operators are available to assist. You must independently query your assets, calculate access windows, and manage resource constraints to build a successful plan. Commit to your decisions and produce a schedule that maximizes the mission objectives. The outcome rests entirely on your ability to autonomously manage these complex trade-offs.
