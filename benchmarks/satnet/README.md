# SatNet: Interplanetary Satellite Scheduling Benchmark

A reinforcement learning benchmark for the **Deep Space Network (DSN) Scheduling Problem**. This challenge involves optimally allocating ground station antenna time to communicate with spacecraft across the solar system, respecting strict physical and operational constraints.

## Problem Overview

The Deep Space Network is NASA/JPL's international array of giant radio antennas that supports interplanetary spacecraft missions. The scheduling problem requires allocating successful communication tracks over a 1-week period while respecting:

- **View Period (VP) constraints**: Communication is only possible when a satellite has line-of-sight to a ground station (determined by orbital mechanics)
- **Setup/Teardown requirements**: Each track requires calibration time before and after transmission
- **Non-overlapping constraints**: Antennas cannot handle multiple transmissions simultaneously
- **Maintenance schedules**: Antennas have scheduled downtime for repairs and upgrades

This maps to a complex constrained scheduling problem with physical constraints derived from astrodynamics.

## Historical Context & Provenance

| Year | Event |
|------|-------|
| 1963 | NASA establishes the Deep Space Network |
| 2000s | Development of automated scheduling systems for DSN operations |
| 2021 | Chien et al. publish RL baseline for satellite scheduling (IEEE Aerospace Conference) |
| 2021 | Release of SatNet benchmark dataset derived from DSN operations |

**Data License**: The dataset is derived from NASA/JPL operations research and academic papers. Used for research and educational purposes.

**Available Weeks**: 5 weeks from 2018 (W10, W20, W30, W40, W50) with 1,452 total requests

## Problem Formulation

### Decision Variables

For each communication request, decide:
- **Whether** to schedule it (may be partially satisfied or unsatisfied)
- **Which antenna** to use (from the request's compatible antennas)
- **When** to schedule it (within valid View Periods)
- **How long** to allocate (between `duration_min` and `duration`)

### Constraints

1. **View Period Constraint**: Each track must be fully contained within a View Period
   ```
   ∀ track: ∃ VP ∈ request.resource_vp_dict[track.antenna]:
       VP.trx_on ≤ track.tracking_on ∧ track.tracking_off ≤ VP.trx_off
   ```

2. **No Overlap Constraint**: Tracks on the same antenna cannot overlap
   ```
   ∀ track_i, track_j on same antenna (i ≠ j):
       track_i.end_time ≤ track_j.start_time ∨ track_j.end_time ≤ track_i.start_time
   ```

3. **Setup/Teardown Constraint**: Timing consistency
   ```
   track.start_time + request.setup_time × 60 = track.tracking_on
   track.tracking_off + request.teardown_time × 60 = track.end_time
   ```

4. **Maintenance Constraint**: No overlap with antenna downtime
   ```
   ∀ track, maintenance on same antenna:
       track.end_time ≤ maintenance.start ∨ maintenance.end ≤ track.start_time
   ```

5. **Minimum Duration Constraint**: Each track must meet minimum duration
   ```
   (track.tracking_off - track.tracking_on) / 3600 ≥ request.duration_min
   ```

### Objective

Maximize total communication hours:
```
maximize: Σ (track.tracking_off - track.tracking_on) / 3600
```

Published SatNet comparisons also emphasize fairness across missions. The principal literature metrics are `U_rms` and `U_max`, which measure the root mean square and worst-case unsatisfied time fraction across missions.

## Data Format Specifications

### Problem Instance Format (`cases/<CASE_ID>/problem.json`)

Each canonical SatNet case is stored in its own directory under
`benchmarks/satnet/dataset/cases/test/`. The verifier remains split-agnostic
and accepts a direct case directory path. The `problem.json` file in a case
directory contains a JSON array of requests for exactly one week/year pair:

```json
[
  {
    "subject": 521,
    "user": "521_0",
    "week": 10,
    "year": 2018,
    "duration": 1.0,
    "duration_min": 1.0,
    "resources": [["DSS-34"], ["DSS-36"]],
    "track_id": "fc9bbb54-3-1",
    "setup_time": 60,
    "teardown_time": 15,
    "time_window_start": 1520286007,
    "time_window_end": 1520471551,
    "resource_vp_dict": {
      "DSS-34": [
        {
          "RISE": 1520286007,
          "SET": 1520318699,
          "TRX ON": 1520286007,
          "TRX OFF": 1520318699
        }
      ],
      "DSS-36": []
    }
  }
]
```

**Field Definitions:**

- **subject**: Mission ID (e.g., 521 = Voyager)
- **track_id**: Unique request identifier (UUID)
- **duration**: Requested communication time (hours)
- **duration_min**: Minimum acceptable duration (hours)
- **setup_time**: Pre-transmission calibration (minutes)
- **teardown_time**: Post-transmission cleanup (minutes)
- **time_window_start/end**: Request validity window (Unix timestamp)
- **resource_vp_dict**: Maps antenna IDs to View Period arrays
  - **TRX ON/OFF**: Transmission window bounds (Unix timestamp)
  - **RISE/SET**: Satellite rise/set times (Unix timestamp)

**Special Case - Arraying**: Some requests can use multiple antennas simultaneously (e.g., `"DSS-34_DSS-35"`). This improves signal strength for distant spacecraft.

### Solution Format (JSON)

An array of scheduled tracks:

```json
[
  {
    "RESOURCE": "DSS-34",
    "SC": "521",
    "START_TIME": 1520286007,
    "TRACKING_ON": 1520289607,
    "TRACKING_OFF": 1520293207,
    "END_TIME": 1520294107,
    "TRACK_ID": "fc9bbb54-3-1"
  }
]
```

**Field Definitions:**

- **RESOURCE**: Antenna ID
- **SC**: Spacecraft/Mission ID (parsed by the verifier but not validated against the request's `subject`)
- **START_TIME**: Track start including setup (Unix timestamp)
- **TRACKING_ON**: Actual transmission start (Unix timestamp)
- **TRACKING_OFF**: Actual transmission end (Unix timestamp)
- **END_TIME**: Track end including teardown (Unix timestamp)
- **TRACK_ID**: Must match a request's `track_id`

**Timing Relationships:**
```
START_TIME --[setup_time]--> TRACKING_ON --[actual_comms]--> TRACKING_OFF --[teardown_time]--> END_TIME
```

### Maintenance Schedule Format (`cases/<CASE_ID>/maintenance.csv`)

Each case directory also contains a maintenance CSV filtered to that same
week/year instance:

```csv
week,year,starttime,endtime,antenna
10.0,2018,1520286000,1520300000,DSS-14
```

**Field Definitions:**

- **week/year**: ISO week number and year
- **starttime/endtime**: Maintenance window (Unix timestamp)
- **antenna**: Antenna ID (e.g., "DSS-14")

## Validation Rules

The verifier (`verifier.py`) checks:

### 1. View Period Validation
Each track's `[TRACKING_ON, TRACKING_OFF]` interval must be fully contained within at least one View Period for that antenna-request pair.

### 2. Overlap Detection
No two tracks on the same antenna can have overlapping `[START_TIME, END_TIME]` intervals (including setup/teardown).

### 3. Setup/Teardown Verification
- `TRACKING_ON = START_TIME + setup_time × 60`
- `END_TIME = TRACKING_OFF + teardown_time × 60`

### 4. Maintenance Violation Check
No track's `[START_TIME, END_TIME]` can overlap with any maintenance window on the same antenna.

### 5. Minimum Duration Check
- `(TRACKING_OFF - TRACKING_ON) / 3600 ≥ duration_min`
- **Special cap**: for requests whose `duration ≥ 8` hours, the verifier silently caps the per-track minimum at **4 hours** (`per_track_min_sec = min(req_min_sec, 14400)`). This means a single track for a long request only needs to provide 4 hours of actual transmission time, not the full `duration_min`.

### 6. Request Existence
Each `TRACK_ID` must correspond to a valid request in the problem instance.

### 7. Antenna Availability
The `RESOURCE` must be in the request's `resource_vp_dict`.

## Scoring Methodology

**Tracking Hours**: Total scheduled communication time
```python
total_hours = sum((track['TRACKING_OFF'] - track['TRACKING_ON']) / 3600.0 for track in solution)
```

**Note**: Setup and teardown times consume antenna availability but do **not** count toward total tracking hours.

**Fairness Metrics** (also computed and reported by the verifier):

- **Requests Satisfied**: Number of requests whose total allocated duration (summed across all tracks for that `track_id`) is at least `duration_min`
- **Fairness (U_max)**: Maximum unsatisfied fraction across all missions
  ```
  U_m = (requested_duration_m - allocated_duration_m) / requested_duration_m
  U_max = max(U_m for all missions)
  ```
- **Fairness (U_rms)**: Root-mean-square of unsatisfied fractions
  ```
  U_rms = sqrt(mean(U_m² for all missions))
  ```

For fairness accounting, the verifier groups requests by `subject`. Per-request allocated duration is capped at `duration` before mission totals are computed.

## Instance Classification

### Dataset Statistics

| Week | Requests | Total Requested Hours | Unique Missions |
|------|----------|----------------------|-----------------|
| W10_2018 | 257 | 1191.5h | 30 |
| W20_2018 | 294 | 1406.5h | 33 |
| W30_2018 | 293 | 1464.0h | 32 |
| W40_2018 | 333 | 1736.7h | 34 |
| W50_2018 | 275 | 1292.2h | 29 |

**Complexity Factors:**
- **View Period Fragmentation**: Some satellites have many short VPs vs few long VPs
- **Arraying Requirements**: Multi-antenna requests are harder to schedule
- **Setup/Teardown Overhead**: High overhead reduces effective antenna utilization
- **Maintenance Density**: More downtime increases scheduling difficulty

## Verification Usage

### Command Line

```bash
uv run python benchmarks/satnet/verifier.py \
    benchmarks/satnet/dataset/cases/test/W10_2018 \
    solution.json \
    --verbose
```

**Output (verbose):**
```
Status: VALID
U_rms: 0.32
U_max: 0.65
Total tracking hours: 234.5678
Tracks: 145
Satisfied requests: 132
```

**Output (compact):**
```
VALID: total_hours=234.5678h, tracks=145
```

## Baseline Performance

Published SatNet baselines report both total scheduled hours (`T_S`) and mission-level fairness metrics. These rows are citation-backed literature results, not outputs reproduced by this repository.

| Method | Source | Week | T_S / T_R (hours) | Satisfied Requests | U_rms | U_max |
|--------|--------|------|-------------------|--------------------|-------|-------|
| Delta-MILP | Goh et al. (2021), Table 2 | W10_2018 | 822 / 1192 | 203 | 0.26 | 0.48 |
| Delta-MILP | Goh et al. (2021), Table 2 | W20_2018 | 1059 / 1406 | 249 | 0.21 | 0.64 |
| Delta-MILP | Goh et al. (2021), Table 2 | W30_2018 | 983 / 1464 | 231 | 0.29 | 0.64 |
| Delta-MILP | Goh et al. (2021), Table 2 | W40_2018 | 949 / 1737 | 223 | 0.40 | 1.00 |
| Delta-MILP | Goh et al. (2021), Table 2 | W50_2018 | 816 / 1292 | 197 | 0.35 | 0.60 |
| RL (PPO) | Goh et al. (2021), Table 3 | W10_2018 | 886 / 1192 | 204 | 0.28 | 0.71 |
| RL (PPO) | Goh et al. (2021), Table 3 | W20_2018 | 1000 / 1406 | 223 | 0.27 | 0.81 |
| RL (PPO) | Goh et al. (2021), Table 3 | W30_2018 | 1100 / 1464 | 229 | 0.28 | 0.85 |
| RL (PPO) | Goh et al. (2021), Table 3 | W40_2018 | 1058 / 1737 | 216 | 0.39 | 0.82 |
| RL (PPO) | Goh et al. (2021), Table 3 | W50_2018 | 879 / 1292 | 185 | 0.36 | 0.67 |

The RL rows are selected from 1,000 stochastic inference runs after training convergence, choosing the highest `T_S` candidate with `U_max < 1`.

## File Locations

- **Case manifest**: `benchmarks/satnet/dataset/index.json`
- **Canonical cases**: `benchmarks/satnet/dataset/cases/test/W##_YYYY/`
- **Shared metadata**: `benchmarks/satnet/dataset/mission_color_map.json`
- **Verifier**: `benchmarks/satnet/verifier.py`
- **Generator**: `uv run python benchmarks/satnet/generator.py benchmarks/satnet/splits.yaml`
- **Test fixtures**: `tests/fixtures/satnet_mock_solutions/`

## Key Technical Concepts

### View Periods (VPs)

View Periods are time windows when a satellite has line-of-sight to a ground station. They are pre-computed based on:
- **Orbital Mechanics**: Satellite ephemeris (position/velocity over time)
- **Ground Station Location**: Latitude, longitude, elevation
- **Elevation Angle**: Minimum angle above horizon (typically 10-15°)
- **Atmospheric Constraints**: Radio frequency propagation limits

VPs are **hard constraints** - you cannot schedule communication outside these windows regardless of antenna availability.

### Arraying

Multiple antennas can be combined to receive from a single spacecraft, improving:
- **Signal-to-Noise Ratio**: Especially critical for deep space missions (Voyager, New Horizons)
- **Data Rate**: Higher combined bandwidth

In the dataset, arrayed requests appear as hyphenated antenna IDs (e.g., `"DSS-34_DSS-35"`). All antennas in the array must be free simultaneously.

### Setup and Teardown

Before each transmission:
- **Setup**: Antenna slewing, receiver tuning, frequency lock acquisition
- **Teardown**: System reset, logging, antenna repositioning

These times are **physically necessary** and consume antenna availability, but **do not count** toward total tracking hours (only actual transmission time counts).

## License & Attribution

**Data Source**: Derived from NASA/JPL Deep Space Network operations research

**Academic References:**
1. Goh, Edwin, Venkataram, Hamsa Shwetha, Balaji, Bharathan, Wilson, Brian D, and Johnston, Mark D. "SatNet: A benchmark for satellite scheduling optimization." AAAI-22 workshop on Machine Learning for Operations Research (ML4OR), 2021.
2. Claudet, Thomas, Ryan Alimo, Edwin Goh, Mark D. Johnston, Ramtin Madani, and Brian Wilson. "Delta-MILP: Deep Space Network Scheduling via Mixed-Integer Linear Programming." IEEE Access, 2022.

**Acknowledgments**: This benchmark is based on the open-source SatNet implementation and dataset provided by NASA JPL and the multi-agent learning community.

## References

1. Chien S, Sherwood R, Tran D, et al. "The EO-1 autonomous science agent." Autonomous Agents and Multi-Agent Systems, 2005.
2. Rabideau G, Chien S, Galer D, Nespoli F. "Managing communications for the Deep Space Network." SpaceOps Conference, 2010.
3. Chien S, Johnston M, Policella N, et al. "A Generalized Timeline Representation for Planning and Scheduling." ICAPS, 2013.
4. Beaumet G, Verfaillie G, Charmeau MC. "Feasibility of Autonomous Decision Making on Board an Agile Earth-Observing Satellite." Computational Intelligence, 2011.
