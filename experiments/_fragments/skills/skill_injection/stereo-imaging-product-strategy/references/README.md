# Stereo Imaging Product Strategy References

Product and verifier-report reminders for stereo-imaging schedules.

## Product Facts

- You submit observation actions; the validator derives products.
- Coverage comes from valid pair or tri-stereo products, not from individual observations.
- Per-target score is the best valid product for that target.
- Extra products for an already-covered target help only if they improve that target's best score or preserve alternatives during repair.
- Same-satellite and cross-satellite products have different scheduling risks.

## Product Modes

- **Same-satellite same-pass:** same target, same satellite, same continuous access interval. Watch same-satellite overlap and slew/settle gaps.
- **Cross-satellite:** same target, different satellites, within the mission pair separation limit, and allowed by mission settings. Watch each satellite timeline separately.
- **Tri-stereo:** three observations of one target, pair mode/time rules for all constituent pairs, common overlap, at least two valid pairs, and one near-nadir anchor.

## Scene-Aware Convergence

Scene preferences are quality preferences, not just validity gates:

| scene_type | useful convergence band |
|---|---|
| `urban_structured` | 8-18 deg |
| `vegetated` | 8-14 deg |
| `rugged` | 10-20 deg |
| `open` | 15-25 deg |

If overlap or pixel-scale ratio becomes fragile, prefer a more conservative product over an extreme baseline.

## Verifier Fields

Look for these fields when a verifier report is available:

- `valid`: whether hard constraints passed.
- `metrics.coverage_ratio`: fraction of targets with at least one valid product.
- `metrics.normalized_quality`: mean best-per-target product score.
- `violations`: hard failures to repair before reading product quality.
- `derived_observations`: per-action geometry and access information.
- `diagnostics.pair_evaluations`: product-level evidence such as convergence, overlap fraction, pixel-scale ratio, and validity.
- `diagnostics.per_target_best_score`: target-level scoreboard for coverage and quality.

## Typical Diagnosis

- Invalid file: fix hard constraints first.
- Valid but zero score: legal observations are not forming products.
- Low coverage: prioritize zero-score targets before polishing covered targets.
- Low quality: use pair evaluations to identify whether convergence, overlap, or pixel-scale ratio is the weak component.
- Tri-stereo failure: check near-nadir anchor, common overlap, and valid constituent pairs.
