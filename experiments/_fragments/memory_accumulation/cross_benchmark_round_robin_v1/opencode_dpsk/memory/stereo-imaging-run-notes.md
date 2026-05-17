# Stereo Imaging Run Notes

## Final Metrics
- Normalized quality: 0.232
- Coverage ratio: 0.348 (48/138 targets)
- Valid: true (0 violations)
- 745 observation actions across 11 satellites
- 136/138 targets have at least 1 observation (2 unobservable: rugged_046, vegetated_030 - solar elevation never reaches 10°)

## Key Findings

### Across-Track Sign Convention
The verifier uses `across_hat = cross(along_hat, nadir_hat)` (left-handed), NOT `cross(nadir_hat, along_hat)` (right-handed). Getting this wrong causes all overlap fractions to be exactly 0.0, making all stereo pairs invalid. This was the critical bug fix.

### Slew Computation
Must compute boresight angle using actual satellite ECEF states at the epoch boundaries (`prev_end_time` and `next_start_time`). Simple small-angle approximation fails because even with identical commanded angles (0,0), the along/across frame shifts due to Earth rotation between epochs, creating ~0.1-0.2 deg non-zero angle differences.

### Solar Elevation
Filter access windows by solar elevation at window midpoint (use `bh.sun_position()` + conversion to ENZ frame). The `EllipsoidalConversionType.GEOCENTRIC` gives closer match to verifier than `GEODETIC` for solar elevation computation.

### Steering Computation
Point boresight at target's elevated ECEF position (including `elevation_ref_m`). Use `position_geodetic_to_ecef([lon, lat, alt], DEGREES)`. The `position_geodetic_to_ecef` expects `[longitude, latitude, altitude]` order.

### Brahe API Patterns
- `bh.Epoch(year, month, day, hour, minute, second)` for epoch creation
- `bh.propagators.SGPPropagator.from_tle(line1, line2, step_size=60.0)` for SGP4 propagation
- `bh.location_accesses(locations, props, start_epoch, end_epoch, constraint)` for access windows
- `prop.propagate_to(epoch)` to propagate to a target epoch
- Epoch subtraction returns seconds: `gap_s = epoch2 - epoch1`
- `str(epc)` format: `"YYYY-MM-DD HH:MM:SS.fff UTC"` → replace with `T` and `Z` for ISO

### Unobservable Targets
- `rugged_046` (lat=-67°S, Antarctica): solar elevation -35° to +6° (never above 10°)
- `vegetated_030` (lat=50°N): access windows during night only

## Approach
1. Compute brahe access windows for all satellite-target pairs (w/ solar elev ≥ 10° filter)
2. Schedule 1 observation per window at center (50% window duration for single, 35% for pairs)
3. For windows ≥ 2*obs_dur + slew_gap + 10s, schedule 2 observations for along-track stereo
4. Slew constraint filtering with proper state-based boresight angle computation
5. Iterative repair: remove actions with access-interval violations

## Output Schema
```json
{"actions": [{"type": "observation", "satellite_id": "...", "target_id": "...",
  "start_time": "ISO8601Z", "end_time": "ISO8601Z",
  "off_nadir_along_deg": float, "off_nadir_across_deg": float}, ...]}
```
