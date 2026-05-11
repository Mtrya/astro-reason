---
name: stereo-imaging-product-strategy
description: Use when solving AstroReason stereo_imaging cases and you need stereo-product strategy, verifier-report diagnosis, pair/tri-stereo improvement tactics, and guidance for turning valid raw observations into covered, high-quality targets.
---

# Stereo Imaging Product Strategy

After the case schema is clear, improve `solution.json` based on product behavior. The case prompt remains the authority for exact thresholds, units, and output fields.

If you have a verifier JSON report, `scripts/summarize_verifier_report.py` can summarize it using only the JSON fields. If you are stuck choosing the next product, use `examples/product_ranking_table.md`; if you are stuck after a failed check, use `examples/verifier_diagnosis_checklist.md`.

## Product Mindset

You submit raw observations, but the score comes from derived stereo products:

- A legal single observation gives no coverage by itself.
- A target is covered only when at least one valid pair or tri-stereo product exists.
- Each target contributes its best product score, so duplicate lower-quality products on the same target are useful only if they enable repair or a later upgrade.
- Add, remove, and repair observations in pair/triple units whenever possible.

Before scheduling a product, ask: which target does it cover, which product mode does it use, why should the pair/triple pass overlap, convergence, and pixel-scale checks, and which same-satellite timeline conflicts can it create?

Keep the product library deliberately small until you have a valid nonzero solution. Stereo imaging has many tempting observation times and pair combinations; most are redundant or fragile. Build a product-first candidate set with strong filters, not a dense all-observations pool.

## Choose The Next Move

| Current state | Next move |
|---|---|
| Invalid `solution.json` | Repair hard action violations before reading product metrics. |
| Valid but zero score | Add one robust same-target pair; do not add unrelated singles. |
| Many zero-score targets | Seed robust pairs for zero-score targets before polishing duplicates. |
| Candidate count is exploding | Prune by target, mode, time margin, convergence band, overlap margin, pixel-scale ratio, and timeline slack before using an optimizer. |
| Most targets covered | Upgrade the best product per target by normalized-quality gain. |
| Pair failures near thresholds | Move inward in access time, reduce extreme steering, or choose a more similar pixel-scale view. |
| Schedule repair removes many products | Revert to the last valid file and reinsert fewer whole products. |

## Product Modes

Use the mode that gives reliable coverage with the least timeline damage:

- **Same-satellite same-pass pair:** two observations of the same target by one satellite in the same access interval. This can be compact but must survive same-satellite overlap and slew/settle constraints.
- **Cross-satellite pair:** two observations of the same target by different satellites within the mission's pair separation limit. This avoids inter-satellite scheduling conflicts but still requires each satellite's own action to be valid.
- **Tri-stereo set:** three observations of the same target whose constituent pairs obey mode and time rules, with common overlap, at least two valid pairs, and a near-nadir anchor. Treat this as an upgrade after pair coverage is stable.

If cross-satellite stereo is allowed, it is often the safer first product mode for weak schedules because it reduces same-satellite retargeting pressure.

## Candidate Pruning First

Start with a bounded product library:

1. For each target, generate only a few robust candidate pairs per mode before widening the search.
2. Prefer mid-window observations with solar/access slack over edge-of-window samples.
3. Keep convergence inside the scene preference band before trying extreme baselines.
4. Reject pairs with weak overlap, extreme pixel-scale ratio, or near-threshold duration unless they are the only way to cover a target.
5. Limit same-satellite dense sampling; same-pass pairs create many timeline conflicts and slew repairs.
6. Keep at most the best few products per target for the first schedule. Add more only after preserving a valid incumbent.

A useful first schedule usually needs broad robust coverage, not every possible product. If an optimizer or script reports tens of thousands of candidate observations or products, stop and tighten pruning. Do not spend the whole run building a huge CP-SAT model before a valid incumbent exists.

## Quality Strategy

After validity, optimize best-per-target product quality. Use broad first-pass coverage as a practical way to avoid zero-contribution targets, then compare upgrades by their effect on normalized quality:

- Match convergence to the target `scene_type` preference band when possible.
- Avoid barely-valid products near convergence, overlap, pixel-scale, access, solar, duration, and slew thresholds.
- Similar effective pixel scales reduce resolution penalty; extremely asymmetric off-nadir views risk pixel-scale failures.
- High overlap is usually worth more than aggressive baseline because overlap has a large quality weight and also protects validity.
- For tri-stereo, include one near-nadir observation as the anchor and two additional views that still form at least two valid pairs.
- Treat near-threshold candidates as upgrade material, not baseline material. First solve with comfortable margins.

Scene preferences:

| scene_type | convergence preference |
|---|---|
| `urban_structured` | moderate baseline, typically 8-18 deg |
| `vegetated` | narrower moderate baseline, typically 8-14 deg |
| `rugged` | moderate-strong baseline, typically 10-20 deg |
| `open` | stronger baseline, typically 15-25 deg |

Do not chase an extreme convergence angle if it damages overlap or pixel-scale ratio. A comfortable product on an uncovered target often improves normalized quality more reliably than a fragile high-baseline duplicate.

## Verifier Diagnosis Loop

After every verifier run, classify the outcome:

- **Invalid:** fix `violations` first. Do not interpret product metrics until hard constraints pass.
- **Valid, zero score:** observations are legal singles but no valid products were derived. Add same-target pairs/triples or adjust product geometry.
- **Valid, low coverage:** inspect which target IDs are absent or zero in `diagnostics.per_target_best_score`; add robust products for zero-score targets, then compare upgrades by quality gain.
- **Valid, low quality:** inspect `diagnostics.pair_evaluations` for products that passed but have weak convergence, overlap, or pixel-scale quality components; replace only when coverage stays intact.
- **Repair collapse:** if fixes remove many observations, preserve the last valid solution and re-add products one target at a time.

Keep the best valid `solution.json` while experimenting. When trying a risky upgrade, make the smallest product-level change that can explain the expected metric movement.

If a sophisticated solver path is slower than the pruning and verifier loop, switch back to a deterministic greedy product inserter. A valid product-level greedy schedule is a better final artifact than an unfinished exact model.

## Diagnostic Fields

Use these verifier report fields when available:

- `violations`: hard failures such as bad timestamps, unknown IDs, duration, horizon, access, overlap on a satellite, or insufficient slew/settle gap.
- `derived_observations`: per-action derived geometry, including access interval, off-nadir, solar, slant range, pixel scale, and boresight-derived values. Use it to find legal observations that are poor product material.
- `diagnostics.pair_evaluations`: pair/tri product evidence such as convergence, overlap fraction, pixel-scale ratio, B/H proxy, bisector elevation, and asymmetry. Use it to tell whether failure is baseline, overlap, resolution, mode, or timing.
- `diagnostics.per_target_best_score`: the target-level scoreboard. Use it to choose the next target to cover or upgrade.

If a field is absent in a compact or no-verifier workspace, reproduce the same reasoning from your own candidate tables.

## Repair Playbook

1. For invalid schedules, repair in this order: schema and IDs, timestamps and duration, mission horizon, combined off-nadir, access/solar, same-satellite overlap, same-satellite slew gap.
2. For valid-zero schedules, group observations by `target_id`; each covered target needs at least two compatible observations or three for tri-stereo.
3. For failed pairs, change one cause at a time: move midpoint times inward, reduce extreme steering, choose a different satellite, or increase baseline only if convergence is too low.
4. For low coverage, add a robust pair for an uncovered target before polishing duplicates, then compare future moves by best-per-target quality gain.
5. For low quality, upgrade the best product for a target, not every product touching that target.
6. For tri-stereo, first keep a valid pair, then add the near-nadir anchor or third view; do not let the upgrade break the pair baseline.

When removing conflicts, remove the weakest whole product that frees the most timeline space, not an arbitrary single action that leaves an orphan observation behind.

## Final Check

Before finalizing:

- `solution.json` contains only raw observation actions.
- Every intended product shares one target ID.
- Same-satellite pair products are same-pass, not merely same-day.
- Cross-satellite products are within the pair separation limit and allowed by the mission.
- Tri-stereo has a near-nadir anchor and enough valid constituent pairs.
- Uncovered targets are intentional because they lack usable opportunities or would break better products.
- The final solution came from the best valid incumbent, not from the last unfinished optimizer attempt.
