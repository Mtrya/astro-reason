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

- **Yotsukaido** (ID: `city_yotsukaido_jp`): Requires **4** observations
- **La Carlota** (ID: `city_la_carlota_ph`): Requires **2** observations
- **Lewoleba** (ID: `city_lewoleba_id`): Requires **4** observations
- **Pasarkemis** (ID: `city_pasarkemis_id`): Requires **5** observations
- **Bat Yam** (ID: `city_bat_yam_il`): Requires **2** observations
- **Tokmok** (ID: `city_tokmok_kg`): Requires **5** observations
- **Talara** (ID: `city_talara_pe`): Requires **5** observations
- **Ceara-Mirim** (ID: `city_ceara_mirim_br`): Requires **3** observations
- **Chimalhuacan** (ID: `city_chimalhuacan_mx`): Requires **3** observations
- **San Francisco** (ID: `city_san_francisco_mx`): Requires **3** observations
- **Ramapo** (ID: `city_ramapo_us`): Requires **4** observations
- **Bethel Park** (ID: `city_bethel_park_us`): Requires **3** observations
- **Stockholm** (ID: `city_stockholm_se`): Requires **2** observations
- **Targu-Mures** (ID: `city_targu_mures_ro`): Requires **2** observations
- **Kismaayo** (ID: `city_kismaayo_so`): Requires **5** observations
- **Siyabuswa** (ID: `city_siyabuswa_za`): Requires **2** observations
- **Borehamwood** (ID: `city_borehamwood_gb`): Requires **4** observations
- **South Shields** (ID: `city_south_shields_gb`): Requires **4** observations
- **Choybalsan** (ID: `city_choybalsan_mn`): Requires **5** observations
- **Krasnokamensk** (ID: `city_krasnokamensk_ru`): Requires **5** observations
- **Mission** (ID: `city_mission_ca`): Requires **3** observations
- **Forest Grove** (ID: `city_forest_grove_us`): Requires **3** observations
- **Rio Gallegos** (ID: `city_rio_gallegos_ar`): Requires **5** observations
- **Coyhaique** (ID: `city_coyhaique_cl`): Requires **5** observations
- **Nuku`alofa** (ID: `city_nuku_alofa_to`): Requires **4** observations
- **Apia** (ID: `city_apia_ws`): Requires **2** observations
- **Dunedin** (ID: `city_dunedin_nz`): Requires **4** observations
- **Invercargill** (ID: `city_invercargill_nz`): Requires **3** observations
- **Babila** (ID: `city_babila_sy`): Requires **2** observations
- **Koro** (ID: `city_koro_ml`): Requires **3** observations


### Station Priority Windows (Low-Latency Link Requests)

You must establish the most direct communication path possible between these station pairs during the specified windows:

1. **facility_greenbelt_test_brt_stdn_bltj** ↔ **facility_weilheim**
   - **Window**: 2025-07-18T12:18:00.500659Z to 2025-07-18T18:18:00.500659Z
   - **Objective**: Minimize Latency
2. **facility_ios_stdn_seys** ↔ **facility_vlba_fort_davis**
   - **Window**: 2025-07-18T16:23:18.823116Z to 2025-07-18T22:23:18.823116Z
   - **Objective**: Minimize Latency
3. **facility_punta_arenas_station** ↔ **facility_ras_al_khaimah_spaceport**
   - **Window**: 2025-07-21T00:52:50.201655Z to 2025-07-21T06:52:50.201655Z
   - **Objective**: Minimize Latency


### Ground Stations
(Use `query_stations` to see available downlink options)

## Final Advice

You are the sole authority for this mission. No human operators are available to assist. You must independently query your assets, calculate access windows, and manage resource constraints to build a successful plan. Commit to your decisions and produce a schedule that maximizes the mission objectives. The outcome rests entirely on your ability to autonomously manage these complex trade-offs.
