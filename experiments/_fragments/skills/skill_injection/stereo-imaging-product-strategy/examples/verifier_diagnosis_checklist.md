# Verifier Diagnosis Checklist

Use this checklist after each verifier report or after each internal approximation pass. Preserve the best valid `solution.json` before trying risky changes.

## Invalid

Read `violations` first. Repair hard constraints before product quality:

1. JSON shape and required action fields.
2. Known `satellite_id` and `target_id`.
3. Timezone-aware timestamps, strict positive duration, and mission horizon containment.
4. Observation duration inside the satellite min/max limits.
5. Combined off-nadir below the satellite maximum.
6. Full-interval access, including solar elevation and line of sight.
7. Same-satellite half-open interval overlap.
8. Same-satellite slew-plus-settle gap between consecutive observations.

After repair, rerun before adding or upgrading products.

## Valid But Zero Score

This means the raw observations are legal but no valid product was derived.

Check:

- Are there at least two observations for the same target?
- Are same-satellite pairs in the same access interval?
- Are cross-satellite pairs allowed by `mission.allow_cross_satellite_stereo`?
- Are midpoint separations inside `mission.max_stereo_pair_separation_s`?
- Are convergence, overlap, and pixel-scale ratio comfortably inside thresholds?
- For triples, is there a near-nadir anchor and at least two valid constituent pairs?

Fix by adding one robust same-target pair for one target, then repeat.

## Valid But Low Coverage

Use `diagnostics.per_target_best_score` as the scoreboard.

For each target with zero or absent score:

1. Find whether it has zero legal observations, one legal observation, or multiple observations that fail product rules.
2. Prefer a robust pair over a fragile tri-stereo attempt.
3. Prefer products that use underloaded satellites and mid-access times.
4. Insert the whole product and revalidate.

Do not spend much time upgrading a covered target while many targets have no product.

## Valid But Low Quality

Use `diagnostics.pair_evaluations` for the best product on each covered target.

Common causes:

- Convergence is below the scene preference band: increase baseline with a second viewpoint, but protect overlap.
- Convergence is above the preference band or hard maximum: reduce steering extremity or choose a closer viewpoint.
- Overlap is near threshold: move observations toward central access, reduce extreme off-nadir, or prefer wider/slower geometry when available.
- Pixel-scale ratio is high: pair observations with more similar slant range or off-nadir.
- Tri-stereo gives little benefit: add or improve the near-nadir anchor and ensure at least two constituent pairs are valid.

Upgrade one target at a time and keep the old product until the replacement is verified.

## Repair Collapse

If a schedule was valid but a repair step removes many products:

1. Revert to the last valid file.
2. Sort products by target coverage value and timeline cost.
3. Remove or move the whole product that blocks the most uncovered targets.
4. Avoid leaving single observations that no longer participate in a valid product.

The goal is a set of product-shaped observations, not a dense pile of legal images.
