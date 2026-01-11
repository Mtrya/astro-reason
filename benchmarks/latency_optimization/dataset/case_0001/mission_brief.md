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

- **Pontevedra** (ID: `city_pontevedra_ph_1`): Requires **5** observations
- **Taihe** (ID: `city_taihe_cn`): Requires **2** observations
- **Auckland** (ID: `city_auckland_nz`): Requires **4** observations
- **Pangkalan Bun** (ID: `city_pangkalan_bun_id`): Requires **4** observations
- **Ain M'Lila** (ID: `city_ain_m_lila_dz`): Requires **4** observations
- **Debre Zeyit** (ID: `city_debre_zeyit_et`): Requires **2** observations
- **Alagoinhas** (ID: `city_alagoinhas_br`): Requires **5** observations
- **Cicero Dantas** (ID: `city_cicero_dantas_br`): Requires **2** observations
- **San Cristobal** (ID: `city_san_cristobal_mx`): Requires **5** observations
- **Siquinala** (ID: `city_siquinala_gt`): Requires **2** observations
- **Toumoukro** (ID: `city_toumoukro_ci`): Requires **4** observations
- **Ocala** (ID: `city_ocala_us`): Requires **4** observations
- **Sid** (ID: `city_sid_rs`): Requires **3** observations
- **Nizhniy Tagil** (ID: `city_nizhniy_tagil_ru`): Requires **2** observations
- **Pietermaritzburg** (ID: `city_pietermaritzburg_za`): Requires **2** observations
- **Sumbe** (ID: `city_sumbe_ao`): Requires **3** observations
- **Sutton Coldfield** (ID: `city_sutton_coldfield_gb`): Requires **4** observations
- **Bedford** (ID: `city_bedford_gb`): Requires **2** observations
- **Darhan** (ID: `city_darhan_mn_1`): Requires **3** observations
- **Zelenogorsk** (ID: `city_zelenogorsk_ru`): Requires **2** observations
- **Surrey** (ID: `city_surrey_ca`): Requires **5** observations
- **Fort Saskatchewan** (ID: `city_fort_saskatchewan_ca`): Requires **4** observations
- **Punta Arenas** (ID: `city_punta_arenas_cl`): Requires **5** observations
- **Coyhaique** (ID: `city_coyhaique_cl`): Requires **4** observations
- **Nuku`alofa** (ID: `city_nuku_alofa_to`): Requires **3** observations
- **Apia** (ID: `city_apia_ws`): Requires **4** observations
- **Invercargill** (ID: `city_invercargill_nz`): Requires **4** observations
- **Dunedin** (ID: `city_dunedin_nz`): Requires **3** observations
- **Mint Hill** (ID: `city_mint_hill_us`): Requires **4** observations
- **Khagaul** (ID: `city_khagaul_in`): Requires **2** observations


### Station Priority Windows (Low-Latency Link Requests)

You must establish the most direct communication path possible between these station pairs during the specified windows:

1. **facility_queensland_transmitter** ↔ **facility_greenbelt_test_brt_stdn_bltj**
   - **Window**: 2025-07-18T07:22:41.658923Z to 2025-07-18T13:22:41.658923Z
   - **Objective**: Minimize Latency
2. **facility_tangua_station** ↔ **facility_globus_ii**
   - **Window**: 2025-07-20T08:42:52.097798Z to 2025-07-20T14:42:52.097798Z
   - **Objective**: Minimize Latency
3. **facility_tilla** ↔ **facility_ral_station_12m**
   - **Window**: 2025-07-17T21:11:56.129592Z to 2025-07-18T03:11:56.129592Z
   - **Objective**: Minimize Latency


### Ground Stations
(Use `query_stations` to see available downlink options)

## Final Advice

You are the sole authority for this mission. No human operators are available to assist. You must independently query your assets, calculate access windows, and manage resource constraints to build a successful plan. Commit to your decisions and produce a schedule that maximizes the mission objectives. The outcome rests entirely on your ability to autonomously manage these complex trade-offs.
