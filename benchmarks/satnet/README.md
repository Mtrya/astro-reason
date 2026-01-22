# SatNet: Interplanetary Satellite Scheduling Benchmark

A reinforcement learning benchmark for the **Deep Space Network (DSN) Scheduling Problem**. This challenge involves optimally allocating ground station antenna time to communicate with spacecraft across the solar system, respecting strict physical and operational constraints.

## Problem Overview

The Deep Space Network is NASA/JPL's international array of giant radio antennas that supports interplanetary spacecraft missions. The scheduling problem requires maximizing the total duration of successful communication tracks over a 1-week period while respecting:

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

## Data Format Specifications

### Problem Instance Format (problems.json)

A JSON object with week keys mapping to arrays of requests:

```json
{
  "W10_2018": [
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
        "DSS-36": [...]
      }
    }
  ]
}
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
- **SC**: Spacecraft/Mission ID (should match request's `subject`)
- **START_TIME**: Track start including setup (Unix timestamp)
- **TRACKING_ON**: Actual transmission start (Unix timestamp)
- **TRACKING_OFF**: Actual transmission end (Unix timestamp)
- **END_TIME**: Track end including teardown (Unix timestamp)
- **TRACK_ID**: Must match a request's `track_id`

**Timing Relationships:**
```
START_TIME --[setup_time]--> TRACKING_ON --[actual_comms]--> TRACKING_OFF --[teardown_time]--> END_TIME
```

### Maintenance Schedule Format (maintenance.csv)

CSV format with antenna downtime windows:

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

### 6. Request Existence
Each `TRACK_ID` must correspond to a valid request in the problem instance.

### 7. Antenna Availability
The `RESOURCE` must be in the request's `resource_vp_dict`.

## Scoring Methodology

**Primary Metric**: Total communication hours
```python
score = sum((track['TRACKING_OFF'] - track['TRACKING_ON']) / 3600.0 for track in solution)
```

**Note**: Setup and teardown times consume antenna availability but do **not** count toward the score.

**Secondary Metrics** (not computed by verifier, but used in RL baselines):

- **Requests Satisfied**: Number of unique `track_id`s in solution
- **Fairness (U_max)**: Maximum unsatisfied fraction across all requests
  ```
  U_i = (requested_duration - allocated_duration) / requested_duration
  U_max = max(U_i for all requests)
  ```
- **Fairness (U_rms)**: Root-mean-square of unsatisfied fractions
  ```
  U_rms = sqrt(mean(U_i² for all requests))
  ```

## Instance Classification

### Dataset Statistics

| Week | Requests | Total Requested Hours | Unique Missions |
|------|----------|----------------------|-----------------|
| W10_2018 | 292 | ~500h | ~30 |
| W20_2018 | 290 | ~490h | ~30 |
| W30_2018 | 290 | ~485h | ~30 |
| W40_2018 | 290 | ~495h | ~30 |
| W50_2018 | 290 | ~490h | ~30 |

**Complexity Factors:**
- **View Period Fragmentation**: Some satellites have many short VPs vs few long VPs
- **Arraying Requirements**: Multi-antenna requests are harder to schedule
- **Setup/Teardown Overhead**: High overhead reduces effective antenna utilization
- **Maintenance Density**: More downtime increases scheduling difficulty

## Verification Usage

### Command Line

```bash
python benchmarks/satnet/verifier.py \
    benchmarks/satnet/dataset/problems.json \
    benchmarks/satnet/dataset/maintenance.csv \
    solution.json \
    --week 10 --year 2018
```

**Output (verbose):**
```
Status: VALID
Score: 234.5678 hours
Tracks: 145
Satisfied Requests: 132
```

**Output (compact):**
```
VALID: score=234.5678h, tracks=145
```

### Python API

```python
from benchmarks.satnet.verifier import verify_files

result = verify_files(
    problems_path="benchmarks/satnet/dataset/problems.json",
    maintenance_path="benchmarks/satnet/dataset/maintenance.csv",
    solution_path="solution.json",
    week=10,
    year=2018
)

print(f"Valid: {result.is_valid}")
print(f"Score: {result.score:.4f} hours")
print(f"Errors: {result.errors}")
```

## Baseline Performance

From the original RL implementation (Chien et al., 2021):

| Method | Avg Hours Allocated | Avg Requests Satisfied | U_rms | U_max |
|--------|--------------------|-----------------------|-------|-------|
| Random | ~180h | ~120 | 0.45 | 0.85 |
| Greedy | ~210h | ~140 | 0.38 | 0.72 |
| PPO (RL) | ~235h | ~155 | 0.32 | 0.65 |

**Note**: Exact numbers depend on the specific week and random seed.

## File Locations

- **Instance files**: `benchmarks/satnet/dataset/problems.json`
- **Maintenance schedule**: `benchmarks/satnet/dataset/maintenance.csv`
- **Simple test cases**: `benchmarks/satnet/dataset/smallest_array_prob.json`, `small_longVP_prob.json`
- **Verifier**: `benchmarks/satnet/verifier.py`
- **Test fixtures**: `tests/fixtures/satnet_solutions/` (if available)

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

These times are **physically necessary** and consume antenna availability, but **do not count** toward the objective score (only actual transmission time counts).

## License & Attribution

**Data Source**: Derived from NASA/JPL Deep Space Network operations research

**Academic References:**
1. Chien, S., et al. "Reinforcement Learning for Scheduling Deep Space Network Communications." IEEE Aerospace Conference, 2021. [DOI: 10.1109/AERO50100.2021.9438519](https://ieeexplore.ieee.org/abstract/document/9438519/)
2. Chien, S., et al. "Learning Satellite Scheduling Policies using Deep Reinforcement Learning." AAAI ML4OR Workshop, 2021. [OpenReview](https://openreview.net/forum?id=buIUxK7F-Bx)

**Acknowledgments**: This benchmark is based on the open-source SatNet implementation and dataset provided by NASA JPL and the multi-agent learning community.

## References

1. Chien S, Sherwood R, Tran D, et al. "The EO-1 autonomous science agent." Autonomous Agents and Multi-Agent Systems, 2005.
2. Rabideau G, Chien S, Galer D, Nespoli F. "Managing communications for the Deep Space Network." SpaceOps Conference, 2010.
3. Chien S, Johnston M, Policella N, et al. "A Generalized Timeline Representation for Planning and Scheduling." ICAPS, 2013.
4. Beaumet G, Verfaillie G, Charmeau MC. "Feasibility of Autonomous Decision Making on Board an Agile Earth-Observing Satellite." Computational Intelligence, 2011.
