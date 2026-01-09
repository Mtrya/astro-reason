# Mission Update: Latency Optimization

## Your Task

You are controlling **90 satellites** from the QIANFAN constellation. Your mission is to establish low-latency communication links between specific ground stations and observe required targets. Horizon: 2025-07-17T12:00:00Z to 2025-07-21T12:00:00Z.

## Mission Objectives

**Primary Goal**: Maximize the total minutes of low-latency connection between designated station pairs within their specific request windows, while simultaneously fulfilling observation quotas for ground targets.

> **Important**: Due to orbital geometry, continuous coverage for the entire request window is often infeasible. Your objective is to maximize the *total connected time* within each window, not necessarily to achieve 100% coverage. A plan that provides 15 minutes of connection in a 30-minute window is successful; one that provides 0 minutes is not.

> **Real-Time Requirement**: This mission requires **real-time, low-latency data transfer**, not store-and-forward. You cannot upload data to a satellite, wait for it to orbit to another station, and then downlink. Instead, you must establish a **simultaneous multi-hop relay chain** where all links (station-to-satellite, satellite-to-satellite, satellite-to-station) are active at the same time.

### Scoring Metrics

Your plan will receive a score based on the following criteria:


1.  **Communication Latency**: The average and maximum communication latency (signal propagation delay) between designated station pairs during their priority windows (minimized).
2.  **Target Coverage**: The percentage of required observations completed for ground targets (maximized).
3.  **Plan Validity**: Your plan must satisfy all physical constraints (battery, storage, terminal limits).


## Constraints (Hard Physical Limits)

These will invalidate your plan if violated:
- **Battery**: Must satisfy `capacity_wh > 0`.
- **Storage**: Must satisfy `storage_used_mb <= capacity_mb`.
- **Links**: Satellites have a limit on concurrent links (`num_terminal`).
- **Slew**: Satellite must have enough time to slew between targets.

## Mission-Specific Data

### Target Cities (Priority Observation Quotas)

The following cities must be observed the specified number of times to fulfill mission requirements:

- **Qincheng** (ID: `city_qincheng_cn`): Requires **2** observations
- **Danzao** (ID: `city_danzao_cn`): Requires **3** observations
- **Northcote** (ID: `city_northcote_nz`): Requires **4** observations
- **Rantepao** (ID: `city_rantepao_id`): Requires **4** observations
- **Tivoli** (ID: `city_tivoli_it`): Requires **2** observations
- **Agia Varvara** (ID: `city_agia_varvara_gr`): Requires **2** observations
- **Lajedo** (ID: `city_lajedo_br`): Requires **2** observations
- **Baradero** (ID: `city_baradero_ar`): Requires **2** observations
- **Santa Barbara** (ID: `city_santa_barbara_us`): Requires **5** observations
- **Campbell** (ID: `city_campbell_us`): Requires **4** observations
- **Jerez** (ID: `city_jerez_gt`): Requires **4** observations
- **Tucker** (ID: `city_tucker_us`): Requires **5** observations
- **Orenburg** (ID: `city_orenburg_ru`): Requires **3** observations
- **Koprivnica** (ID: `city_koprivnica_hr`): Requires **3** observations
- **Manono** (ID: `city_manono_cd`): Requires **2** observations
- **Ceres** (ID: `city_ceres_za`): Requires **4** observations
- **Mitcham** (ID: `city_mitcham_gb`): Requires **2** observations
- **Kopavogur** (ID: `city_kopavogur_is`): Requires **4** observations
- **E'erguna** (ID: `city_e_erguna_cn`): Requires **4** observations
- **Arvayheer** (ID: `city_arvayheer_mn`): Requires **3** observations
- **Graham** (ID: `city_graham_us`): Requires **2** observations
- **Issaquah** (ID: `city_issaquah_us`): Requires **2** observations
- **Punta Arenas** (ID: `city_punta_arenas_cl`): Requires **4** observations
- **Comodoro Rivadavia** (ID: `city_comodoro_rivadavia_ar`): Requires **5** observations
- **Papeete** (ID: `city_papeete_pf`): Requires **4** observations
- **Nuku`alofa** (ID: `city_nuku_alofa_to`): Requires **5** observations
- **Dunedin** (ID: `city_dunedin_nz`): Requires **2** observations
- **Invercargill** (ID: `city_invercargill_nz`): Requires **5** observations
- **Arroyo Naranjo** (ID: `city_arroyo_naranjo_cu`): Requires **5** observations
- **Uruguaiana** (ID: `city_uruguaiana_br`): Requires **2** observations


### Station Priority Windows (Low-Latency Link Requests)

You must establish the most direct communication path possible between these station pairs during the specified windows:

1. **facility_cyberjaya_station** ↔ **facility_goonhilly_satellite_earth_station**
   - **Window**: 2025-07-18T21:55:23.760198Z to 2025-07-19T03:55:23.760198Z
   - **Objective**: Minimize Latency
2. **facility_leuk** ↔ **facility_riverside_teleport**
   - **Window**: 2025-07-17T16:24:09.996296Z to 2025-07-17T22:24:09.996296Z
   - **Objective**: Minimize Latency
3. **facility_echostar_monee_station** ↔ **facility_stockholm_teleport**
   - **Window**: 2025-07-17T17:30:32.259807Z to 2025-07-17T23:30:32.259807Z
   - **Objective**: Minimize Latency


### Ground Stations
(Use `query_stations` to see available downlink options)

## Final Advice

You are the sole authority for this mission. No human operators are available to assist. You must independently query your assets, calculate access windows, and manage resource constraints to build a successful plan. Commit to your decisions and produce a schedule that maximizes the mission objectives. The outcome rests entirely on your ability to autonomously manage these complex trade-offs.
