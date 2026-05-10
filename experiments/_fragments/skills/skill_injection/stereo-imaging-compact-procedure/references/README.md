# Compact Reference

Use this as a quick reminder when the main skill feels too terse.

## Score-Critical Facts

- The submitted file contains raw observation actions, not pair choices or quality claims.
- A target scores only through a valid stereo pair or tri-stereo set.
- Legal single observations can still produce zero coverage.
- Invalid schedules lose before coverage or quality matters.
- Coverage is target-level: several products for one target do not cover several targets.

## Product Checklist

For each intended product, check:

- All observations use the same `target_id`.
- Same-satellite pairs are in the same continuous access interval.
- Cross-satellite pairs use different satellites and are allowed by the mission.
- Pair midpoints are within the mission separation limit.
- Convergence is within hard limits and preferably inside the scene band.
- Overlap and pixel-scale ratio have margin, not boundary luck.
- Tri-stereo has a near-nadir anchor and at least two valid constituent pairs.

## Repair Checklist

- Repair hard action validity first: schema, time, horizon, duration, IDs, off-nadir, access, solar, overlap, slew gap.
- Then repair product validity: same target, product mode, temporal separation, convergence, overlap, pixel-scale ratio.
- Remove or move whole products when possible so orphan observations do not clutter the schedule.
- Keep a valid low-score solution while testing upgrades.
