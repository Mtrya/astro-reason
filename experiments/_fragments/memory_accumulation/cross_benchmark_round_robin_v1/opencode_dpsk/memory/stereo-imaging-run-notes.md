# Stereo Imaging Run Notes

## Final Metrics (v15)
- Valid: True
- Coverage: 15/144 (10.42%) - maximum achievable (all reachable targets covered)
- Normalized Quality: 0.06062
- Violations: 0
- Derived Observations: 96
- Pair Evaluations: 96 (63 valid)
- Average Overlap: 0.98

## Output Schema
```json
{
  "actions": [
    {
      "type": "observation",
      "satellite_id": "...",
      "target_id": "...",
      "start_time": "2026-04-22T...Z",
      "end_time": "2026-04-22T...Z",
      "off_nadir_along_deg": 0.0,
      "off_nadir_across_deg": 0.0
    }
  ]
}
```

## Key Findings

### Critical Bug: Across Sign Convention
The verifier uses `across = along × nadir` (right of flight), NOT `across = nadir × along` (left of flight). Flipping the across sign was the single most impactful fix, turning 0% overlap into 98% average overlap.

### Boresight Pointing
Off-nadir angles must point the boresight at the target surface (on WGS84 ellipsoid, alt=0). The combined off-nadir is computed correctly, but the across sign must match the verifier's convention.

### Access Windows
- Brahe's `location_accesses` with `OffNadirConstraint` returns ~49K raw windows
- Only ~175 are reachable (line-of-sight not through Earth)
- Only 15/144 targets have at least one reachable window
- Most reachable windows are 50-150s duration

### Slew/Settle Gaps
- Between same-satellite observations, must compute slew time using the formula
- Theta between boresight vectors at prev_end and next_start is approximately the convergence angle (20-40 deg)
- Required gaps: 12-30s depending on satellite and convergence angle
- Must use actual boresight computation, not estimates

### Tri-Stereo
- Require window >= 90s for 3 observations
- Average tri-stereo quality boost: 0.10-0.20 (adds scene_type bonus)
- Need at least one near-nadir observation (off-nadir <= 10 deg)

### Overlap
- Overlap is near 1.0 when boresight points at target and across sign is correct
- Sample points at 8-second intervals; boresight intersection slides at ~8 km/s
- Short observations (16-48s) with target-pointing give good overlap

## Solver Approach (What Works)

1. **Access Computation**:
   - `bh.location_accesses` with `OffNadirConstraint(max_off_nadir_deg)`
   - Filter: solar elevation >= 10 deg, line-of-sight (target not behind Earth)
   - Only 175 reachable windows across all sat-target pairs

2. **Boresight Pointing**:
   - LVLH: `nadir = -pos/|pos|`, `along = vel - (vel·nadir)nadir` (normalized)
   - `across = along × nadir` (RIGHT of flight - matches verifier)
   - Compute `off_nadir_along/across` from target direction decomposition

3. **Candidate Generation**:
   - Stereo pairs: 2 observations per access window
   - Tri-stereo: 3 observations for windows >= 90s
   - Observation durations: 16-48s (multiples of 8 for sample alignment)
   - Gap computation: actual slew gap between consecutive obs

4. **Scheduling**:
   - Phase 1: Coverage-first (ensure all 15 reachable targets covered)
   - Phase 2: Tri-stereo upgrades where they fit without conflicts
   - Greedy conflict resolution per satellite

5. **Command Pattern**:
```bash
./verifier case/ solution.json
```

## Failed Approaches
- Using `nadir × along` for across (wrong convention) → 0 overlap
- Long observations (48-59s) with sample misalignment → low overlap
- Conservative gap estimation (underestimating theta) → slew violations
- Too-strict boresight intersection checks → too few candidates
- Global greedy without coverage-first → missed targets
- Manual pair addition without proper gap computation → violations

## Maximum Achievable Quality
- 15 reachable targets out of 144
- Max theoretical quality ≈ 0.078 (all tri-stereo max scores)
- Achieved: 0.0606 (78% of theoretical max)
