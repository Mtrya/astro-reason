# Mission Update: Stereo Imaging

## Your Task

You are controlling **43 satellites** from the SPOT, TERRASAR, GAOFEN constellations. Your mission is to capture **stereo pairs** (two images of the same target from different angles) for a set of high-value targets. Horizon: 2025-07-17T12:00:00Z to 2025-07-21T12:00:00Z.

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

- **Ban Sai Ma Tai** (ID: `city_ban_sai_ma_tai_th`)
  - Location: 13.86°, 100.47°
- **Laiwu** (ID: `city_laiwu_cn`)
  - Location: 36.18°, 117.67°
- **Escalante** (ID: `city_escalante_ph`)
  - Location: 10.83°, 123.50°
- **Samarinda** (ID: `city_samarinda_id`)
  - Location: -0.50°, 117.14°
- **Mojokerto** (ID: `city_mojokerto_id`)
  - Location: -7.47°, 112.43°
- **Mildura** (ID: `city_mildura_au`)
  - Location: -34.19°, 142.16°
- **Al Manaqil** (ID: `city_al_manaqil_sd`)
  - Location: 14.25°, 32.98°
- **Kurivikod** (ID: `city_kurivikod_in`)
  - Location: 8.32°, 77.11°
- **Ano Liosia** (ID: `city_ano_liosia_gr`)
  - Location: 38.08°, 23.70°
- **Ivirgarzama** (ID: `city_ivirgarzama_bo`)
  - Location: -17.03°, -64.85°
- **Cusco** (ID: `city_cusco_pe`)
  - Location: -13.53°, -71.97°
- **Mogi das Cruzes** (ID: `city_mogi_das_cruzes_br`)
  - Location: -23.52°, -46.19°
- **Shreveport** (ID: `city_shreveport_us`)
  - Location: 32.47°, -93.80°
- **South San Francisco** (ID: `city_south_san_francisco_us`)
  - Location: 37.65°, -122.42°
- **San Jeronimo** (ID: `city_san_jeronimo_gt`)
  - Location: 15.06°, -90.24°
- **Valladolid** (ID: `city_valladolid_es`)
  - Location: 41.65°, -4.72°
- **Akron** (ID: `city_akron_us`)
  - Location: 41.08°, -81.52°
- **Ibarra** (ID: `city_ibarra_ec`)
  - Location: 0.36°, -78.13°
- **Oullins** (ID: `city_oullins_fr`)
  - Location: 45.72°, 4.81°
- **Vyshniy Volochek** (ID: `city_vyshniy_volochek_ru`)
  - Location: 57.58°, 34.57°
- **Semiluki** (ID: `city_semiluki_ru`)
  - Location: 51.68°, 39.03°
- **Antalaha** (ID: `city_antalaha_mg`)
  - Location: -14.88°, 50.28°
- **Mahambo** (ID: `city_mahambo_mg`)
  - Location: -17.49°, 49.45°
- **Sumbe** (ID: `city_sumbe_ao`)
  - Location: -11.21°, 13.84°
- **Bangor** (ID: `city_bangor_gb`)
  - Location: 54.66°, -5.67°
- **Bridlington** (ID: `city_bridlington_gb`)
  - Location: 54.08°, -0.19°
- **Stratford** (ID: `city_stratford_gb`)
  - Location: 51.54°, -0.00°
- **Shuangcheng** (ID: `city_shuangcheng_cn`)
  - Location: 45.35°, 126.28°
- **Ulan-Ude** (ID: `city_ulan_ude_ru`)
  - Location: 51.83°, 107.60°
- **Linkou** (ID: `city_linkou_cn`)
  - Location: 45.28°, 130.25°
- **Moose Jaw** (ID: `city_moose_jaw_ca`)
  - Location: 50.39°, -105.55°
- **Vancouver** (ID: `city_vancouver_us`)
  - Location: 45.64°, -122.60°
- **Leduc** (ID: `city_leduc_ca`)
  - Location: 53.26°, -113.55°
- **Coyhaique** (ID: `city_coyhaique_cl`)
  - Location: -45.57°, -72.07°
- **Caleta Olivia** (ID: `city_caleta_olivia_ar`)
  - Location: -46.43°, -67.53°
- **Ushuaia** (ID: `city_ushuaia_ar`)
  - Location: -54.80°, -68.30°
- **Nuku`alofa** (ID: `city_nuku_alofa_to`)
  - Location: -21.13°, -175.20°
- **Papeete** (ID: `city_papeete_pf`)
  - Location: -17.53°, -149.57°
- **Apia** (ID: `city_apia_ws`)
  - Location: -13.83°, -171.75°
- **Invercargill** (ID: `city_invercargill_nz`)
  - Location: -46.43°, 168.36°
- **Dunedin** (ID: `city_dunedin_nz`)
  - Location: -45.87°, 170.50°
- **Ganderkesee** (ID: `city_ganderkesee_de`)
  - Location: 53.04°, 8.55°
- **Pilibangan** (ID: `city_pilibangan_in`)
  - Location: 29.49°, 74.07°


### Ground Stations
(Use `query_stations` to see available downlink options)

## Final Advice

You are the sole authority for this mission. No human operators are available to assist. You must independently query your assets, calculate access windows, and manage resource constraints to build a successful plan. Commit to your decisions and produce a schedule that maximizes the mission objectives. The outcome rests entirely on your ability to autonomously manage these complex trade-offs.
