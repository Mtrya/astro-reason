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

- **Ban Sai Ma Tai** (ID: `city_ban_sai_ma_tai_th`): Requires **2** observations
- **Laiwu** (ID: `city_laiwu_cn`): Requires **4** observations
- **New Plymouth** (ID: `city_new_plymouth_nz`): Requires **2** observations
- **Samarinda** (ID: `city_samarinda_id`): Requires **4** observations
- **Naspur** (ID: `city_naspur_in`): Requires **5** observations
- **Point Pedro** (ID: `city_point_pedro_lk`): Requires **5** observations
- **Colonia del Sacramento** (ID: `city_colonia_del_sacramento_uy`): Requires **3** observations
- **Abreu e Lima** (ID: `city_abreu_e_lima_br`): Requires **5** observations
- **Metepec** (ID: `city_metepec_mx`): Requires **4** observations
- **San Miguel Chicaj** (ID: `city_san_miguel_chicaj_gt`): Requires **4** observations
- **Banfora** (ID: `city_banfora_bf`): Requires **3** observations
- **Terga** (ID: `city_terga_dz`): Requires **2** observations
- **Hamminkeln** (ID: `city_hamminkeln_de`): Requires **3** observations
- **Belgorod** (ID: `city_belgorod_ru`): Requires **4** observations
- **Durban** (ID: `city_durban_za`): Requires **2** observations
- **Kisenzi** (ID: `city_kisenzi_cd`): Requires **4** observations
- **Epsom** (ID: `city_epsom_gb`): Requires **2** observations
- **Shrewsbury** (ID: `city_shrewsbury_gb`): Requires **4** observations
- **Qingan** (ID: `city_qingan_cn`): Requires **3** observations
- **Jixi** (ID: `city_jixi_cn`): Requires **4** observations
- **Spokane** (ID: `city_spokane_us`): Requires **3** observations
- **Everett** (ID: `city_everett_us`): Requires **3** observations
- **Ushuaia** (ID: `city_ushuaia_ar`): Requires **2** observations
- **Rio Grande** (ID: `city_rio_grande_ar`): Requires **5** observations
- **Nuku`alofa** (ID: `city_nuku_alofa_to`): Requires **2** observations
- **Apia** (ID: `city_apia_ws`): Requires **4** observations
- **Invercargill** (ID: `city_invercargill_nz`): Requires **3** observations
- **Dunedin** (ID: `city_dunedin_nz`): Requires **2** observations
- **Garibaldi** (ID: `city_garibaldi_br`): Requires **3** observations
- **Perth** (ID: `city_perth_gb`): Requires **4** observations


### Station Priority Windows (Low-Latency Link Requests)

You must establish the most direct communication path possible between these station pairs during the specified windows:

1. **facility_wilkes-barre_station** ↔ **facility_vikram_sarabhai**
   - **Window**: 2025-07-19T09:35:29.408954Z to 2025-07-19T15:35:29.408954Z
   - **Objective**: Minimize Latency
2. **facility_orlando_station** ↔ **facility_kamisaibara_spaceguard_center**
   - **Window**: 2025-07-20T10:03:52.528598Z to 2025-07-20T16:03:52.528598Z
   - **Objective**: Minimize Latency
3. **facility_gila_river_space_fence** ↔ **facility_prts**
   - **Window**: 2025-07-18T12:45:22.575504Z to 2025-07-18T18:45:22.575504Z
   - **Objective**: Minimize Latency


### Ground Stations
(Use `query_stations` to see available downlink options)

## Final Advice

You are the sole authority for this mission. No human operators are available to assist. You must independently query your assets, calculate access windows, and manage resource constraints to build a successful plan. Commit to your decisions and produce a schedule that maximizes the mission objectives. The outcome rests entirely on your ability to autonomously manage these complex trade-offs.
