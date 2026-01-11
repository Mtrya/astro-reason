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

- **Bao Loc** (ID: `city_bao_loc_vn`): Requires **2** observations
- **Koka** (ID: `city_koka_jp`): Requires **2** observations
- **Cakung** (ID: `city_cakung_id`): Requires **4** observations
- **Rawajaya** (ID: `city_rawajaya_id`): Requires **4** observations
- **Satna** (ID: `city_satna_in`): Requires **5** observations
- **Tripunittura** (ID: `city_tripunittura_in`): Requires **4** observations
- **Januaria** (ID: `city_januaria_br`): Requires **2** observations
- **Chiclayo** (ID: `city_chiclayo_pe`): Requires **5** observations
- **Santa Clarita** (ID: `city_santa_clarita_us`): Requires **4** observations
- **Nueva Santa Rosa** (ID: `city_nueva_santa_rosa_gt`): Requires **3** observations
- **Santiago** (ID: `city_santiago_do`): Requires **4** observations
- **Matanzas** (ID: `city_matanzas_cu`): Requires **3** observations
- **Herzogenrath** (ID: `city_herzogenrath_de`): Requires **2** observations
- **Noyabrsk** (ID: `city_noyabrsk_ru`): Requires **3** observations
- **Kabarore** (ID: `city_kabarore_rw`): Requires **5** observations
- **Mampikony** (ID: `city_mampikony_mg`): Requires **5** observations
- **Coventry** (ID: `city_coventry_gb`): Requires **4** observations
- **Ashford** (ID: `city_ashford_gb_1`): Requires **3** observations
- **Neryungri** (ID: `city_neryungri_ru`): Requires **5** observations
- **Shuangyashan** (ID: `city_shuangyashan_cn`): Requires **5** observations
- **Everett** (ID: `city_everett_us`): Requires **5** observations
- **Mount Vernon** (ID: `city_mount_vernon_us_1`): Requires **3** observations
- **Caleta Olivia** (ID: `city_caleta_olivia_ar`): Requires **5** observations
- **Coyhaique** (ID: `city_coyhaique_cl`): Requires **2** observations
- **Papeete** (ID: `city_papeete_pf`): Requires **5** observations
- **Nuku`alofa** (ID: `city_nuku_alofa_to`): Requires **2** observations
- **Dunedin** (ID: `city_dunedin_nz`): Requires **2** observations
- **Invercargill** (ID: `city_invercargill_nz`): Requires **4** observations
- **Ciudad Dario** (ID: `city_ciudad_dario_ni`): Requires **4** observations
- **Bingol** (ID: `city_bingol_tr`): Requires **4** observations


### Station Priority Windows (Low-Latency Link Requests)

You must establish the most direct communication path possible between these station pairs during the specified windows:

1. **facility_cstars_20m** ↔ **facility_baikonur_cosmodrome_lc_165**
   - **Window**: 2025-07-20T09:45:30.130253Z to 2025-07-20T15:45:30.130253Z
   - **Objective**: Minimize Latency
2. **facility_triunfo_pass_station** ↔ **facility_st_hubert**
   - **Window**: 2025-07-21T02:38:25.826179Z to 2025-07-21T08:38:25.826179Z
   - **Objective**: Minimize Latency
3. **facility_mojave_air_and_space_port** ↔ **facility_lushan_station**
   - **Window**: 2025-07-17T20:26:16.492838Z to 2025-07-18T02:26:16.492838Z
   - **Objective**: Minimize Latency


### Ground Stations
(Use `query_stations` to see available downlink options)

## Final Advice

You are the sole authority for this mission. No human operators are available to assist. You must independently query your assets, calculate access windows, and manage resource constraints to build a successful plan. Commit to your decisions and produce a schedule that maximizes the mission objectives. The outcome rests entirely on your ability to autonomously manage these complex trade-offs.
