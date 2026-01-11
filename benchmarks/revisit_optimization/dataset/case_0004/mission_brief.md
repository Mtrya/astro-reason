# Mission Update: Revisit Optimization

## Your Task

You are controlling **29 satellites** from the NOAA constellation. Your mission is to minimize the **revisit gap** (time between observations) for high-priority targets over a calculated period (2025-07-17T12:00:00Z to 2025-07-21T12:00:00Z).

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

- **Hoboken** (ID: `city_hoboken_be`)
  - Location: 51.17°, 4.37°
  - Objective: Minimize Revisit Gap
- **Rotorua** (ID: `city_rotorua_nz`)
  - Location: -38.14°, 176.25°
  - Objective: Minimize Revisit Gap
- **Guanambi** (ID: `city_guanambi_br`)
  - Location: -14.22°, -42.78°
  - Objective: Minimize Revisit Gap

### Mapping Targets (Quota-based Observations)

These targets require a minimum number of successful observations during the mission horizon.

- **Fremont** (ID: `city_fremont_us`)
  - Location: 37.53°, -121.98°
  - Required Observations: 2
- **Bao Loc** (ID: `city_bao_loc_vn`)
  - Location: 11.55°, 107.81°
  - Required Observations: 4
- **Taunton** (ID: `city_taunton_us`)
  - Location: 41.90°, -71.09°
  - Required Observations: 2
- **Khachrod** (ID: `city_khachrod_in`)
  - Location: 23.42°, 75.28°
  - Required Observations: 2


### Ground Stations
(Use `query_stations` to see available downlink options)

## Final Advice

You are the sole authority for this mission. No human operators are available to assist. You must independently query your assets, calculate access windows, and manage resource constraints to build a successful plan. Commit to your decisions and produce a schedule that maximizes the mission objectives. The outcome rests entirely on your ability to autonomously manage these complex trade-offs.
