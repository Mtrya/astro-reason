# Mission Update: Stereo Imaging

## Your Task

You are controlling **45 satellites** from the ZIYUAN, SPOT, GAOFEN constellations. Your mission is to capture **stereo pairs** (two images of the same target from different angles) for a set of high-value targets. Horizon: 2025-07-17T12:00:00Z to 2025-07-21T12:00:00Z.

## Mission Objectives

**Primary Goal**: Maximize the mission utility by acquiring high-quality stereo pairs for as many targets as possible within the physical constraints of the platform.

### Scoring Metrics

Your plan will receive a score based on the following criteria:


1.  **Stereo Yield**: The percentage of high-value targets for which at least one valid stereo pair (two observations meeting angle/time constraints) is successfully acquired.
2.  **Plan Validity**: Your plan must satisfy all physical constraints (battery, storage, slew time).


## Constraints (Hard Physical Limits)

These will invalidate your plan if violated:
- **Battery**: Must satisfy `capacity_wh > 0`.
- **Storage**: Must satisfy `storage_used_mb <= capacity_mb`.
- **Slew**: Satellite must have enough time to slew between targets. Agility is critical for stereo acquisition.

## Mission-Specific Data

### Stereo Target List (High-Priority)

For each target below, you must attempt to collect a **stereo pair**. A valid pair consists of two observations that satisfy the following physical constraints:

**Physical Constraints for Stereo Pairs**:
- **Azimuth Separation**: Between 15.0° and 60.0°
- **Max Temporal Gap**: 2.0 hours between the two observations
- **Min Elevation**: 30.0°

- **Pontevedra** (ID: `city_pontevedra_ph_1`)
  - Location: 11.48°, 122.83°
- **Taihe** (ID: `city_taihe_cn`)
  - Location: 30.87°, 105.39°
- **Hengshui** (ID: `city_hengshui_cn`)
  - Location: 37.74°, 115.67°
- **Pangkalan Bun** (ID: `city_pangkalan_bun_id`)
  - Location: -2.68°, 111.62°
- **Indramayu** (ID: `city_indramayu_id`)
  - Location: -6.35°, 108.32°
- **Adonara** (ID: `city_adonara_id`)
  - Location: -8.25°, 123.15°
- **Al Qurayyat** (ID: `city_al_qurayyat_sa`)
  - Location: 31.32°, 37.37°
- **Tarrasa** (ID: `city_tarrasa_es`)
  - Location: 41.57°, 2.01°
- **Perumbalam** (ID: `city_perumbalam_in`)
  - Location: 10.83°, 76.04°
- **Careiro** (ID: `city_careiro_br`)
  - Location: -3.77°, -60.37°
- **Sao Miguel do Guama** (ID: `city_sao_miguel_do_guama_br`)
  - Location: -1.63°, -47.48°
- **Divinopolis** (ID: `city_divinopolis_br`)
  - Location: -20.14°, -44.88°
- **Lawndale** (ID: `city_lawndale_us`)
  - Location: 33.89°, -118.35°
- **Salina** (ID: `city_salina_us`)
  - Location: 38.81°, -97.61°
- **Des Moines** (ID: `city_des_moines_us`)
  - Location: 41.57°, -93.61°
- **Lisbon** (ID: `city_lisbon_pt`)
  - Location: 38.71°, -9.13°
- **Seixal** (ID: `city_seixal_pt`)
  - Location: 38.64°, -9.11°
- **Panzos** (ID: `city_panzos_gt`)
  - Location: 15.40°, -89.67°
- **Veszprem** (ID: `city_veszprem_hu`)
  - Location: 47.10°, 17.92°
- **Boxmeer** (ID: `city_boxmeer_nl`)
  - Location: 51.65°, 5.94°
- **Bryansk** (ID: `city_bryansk_ru`)
  - Location: 53.24°, 34.37°
- **Same** (ID: `city_same_tz`)
  - Location: -4.07°, 37.78°
- **Gitega** (ID: `city_gitega_bi`)
  - Location: -3.43°, 29.93°
- **Giyani** (ID: `city_giyani_za`)
  - Location: -23.31°, 30.71°
- **Wokingham** (ID: `city_wokingham_gb`)
  - Location: 51.41°, -0.84°
- **Accrington** (ID: `city_accrington_gb`)
  - Location: 53.75°, -2.36°
- **Inverness** (ID: `city_inverness_gb`)
  - Location: 57.48°, -4.22°
- **Mositai** (ID: `city_mositai_cn`)
  - Location: 45.53°, 119.65°
- **Beian** (ID: `city_beian_cn`)
  - Location: 48.25°, 126.52°
- **Kansk** (ID: `city_kansk_ru`)
  - Location: 56.20°, 95.72°
- **Tumwater** (ID: `city_tumwater_us`)
  - Location: 46.99°, -122.92°
- **Great Falls** (ID: `city_great_falls_us`)
  - Location: 47.50°, -111.30°
- **Vancouver** (ID: `city_vancouver_ca`)
  - Location: 49.25°, -123.10°
- **Caleta Olivia** (ID: `city_caleta_olivia_ar`)
  - Location: -46.43°, -67.53°
- **Punta Arenas** (ID: `city_punta_arenas_cl`)
  - Location: -53.17°, -70.93°
- **Rio Gallegos** (ID: `city_rio_gallegos_ar`)
  - Location: -51.62°, -69.22°
- **Apia** (ID: `city_apia_ws`)
  - Location: -13.83°, -171.75°
- **Nuku`alofa** (ID: `city_nuku_alofa_to`)
  - Location: -21.13°, -175.20°
- **Papeete** (ID: `city_papeete_pf`)
  - Location: -17.53°, -149.57°
- **Invercargill** (ID: `city_invercargill_nz`)
  - Location: -46.43°, 168.36°
- **Dunedin** (ID: `city_dunedin_nz`)
  - Location: -45.87°, 170.50°
- **Dongning** (ID: `city_dongning_cn`)
  - Location: 44.12°, 130.82°
- **Qostanay** (ID: `city_qostanay_kz`)
  - Location: 53.20°, 63.62°
- **Grabouw** (ID: `city_grabouw_za`)
  - Location: -34.15°, 19.02°
- **Toledo** (ID: `city_toledo_ph`)
  - Location: 10.38°, 123.65°


### Ground Stations
(Use `query_stations` to see available downlink options)

## Final Advice

You are the sole authority for this mission. No human operators are available to assist. You must independently query your assets, calculate access windows, and manage resource constraints to build a successful plan. Commit to your decisions and produce a schedule that maximizes the mission objectives. The outcome rests entirely on your ability to autonomously manage these complex trade-offs.
