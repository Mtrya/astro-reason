# Mission Update: Revisit Optimization

## Your Task

You are controlling **47 satellites** from the DMSP constellation. Your mission is to minimize the **revisit gap** (time between observations) for high-priority targets over a calculated period (2025-07-17T12:00:00Z to 2025-07-21T12:00:00Z).

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

- **Villejuif** (ID: `city_villejuif_fr`)
  - Location: 48.79°, 2.36°
  - Objective: Minimize Revisit Gap
- **Klerksdorp** (ID: `city_klerksdorp_za`)
  - Location: -26.87°, 26.67°
  - Objective: Minimize Revisit Gap
- **Narela** (ID: `city_narela_in`)
  - Location: 28.85°, 77.10°
  - Objective: Minimize Revisit Gap
- **Zhaodong** (ID: `city_zhaodong_cn`)
  - Location: 46.05°, 125.96°
  - Objective: Minimize Revisit Gap
- **Aguilares** (ID: `city_aguilares_sv`)
  - Location: 13.95°, -89.18°
  - Objective: Minimize Revisit Gap

### Mapping Targets (Quota-based Observations)

These targets require a minimum number of successful observations during the mission horizon.

- **Alexandria** (ID: `city_alexandria_us_1`)
  - Location: 31.29°, -92.47°
  - Required Observations: 3
- **Nelson** (ID: `city_nelson_gb`)
  - Location: 53.83°, -2.22°
  - Required Observations: 2
- **Guaranda** (ID: `city_guaranda_ec`)
  - Location: -1.60°, -79.00°
  - Required Observations: 2
- **Majene** (ID: `city_majene_id`)
  - Location: -3.54°, 118.97°
  - Required Observations: 4
- **Ramsey** (ID: `city_ramsey_us`)
  - Location: 45.26°, -93.45°
  - Required Observations: 3
- **Pontevedra** (ID: `city_pontevedra_ph_1`)
  - Location: 11.48°, 122.83°
  - Required Observations: 3


### Ground Stations
(Use `query_stations` to see available downlink options)

## Final Advice

You are the sole authority for this mission. No human operators are available to assist. You must independently query your assets, calculate access windows, and manage resource constraints to build a successful plan. Commit to your decisions and produce a schedule that maximizes the mission objectives. The outcome rests entirely on your ability to autonomously manage these complex trade-offs.
