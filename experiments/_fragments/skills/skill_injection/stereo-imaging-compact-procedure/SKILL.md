---
name: stereo-imaging-compact-procedure
description: Use when solving AstroReason stereo_imaging cases and you need a compact procedure for turning access opportunities into valid stereo or tri-stereo observation schedules.
---

# Stereo Imaging Compact Procedure

Use this as a short working recipe. The case prompt is the authority for exact
units, validity thresholds, and output schema.

## First Make A Valid Skeleton

Start by writing a minimal `solution.json` with an `actions` array, even if it
is empty. Then add observations in small batches and validate often. A valid
low-score file is easier to improve than a large invalid schedule.

Every action is only a raw observation. Do not submit pair choices, footprint
claims, or scores; the validator derives stereo products from your actions.

## Think In Products Before Scheduling

For each target, look for candidate observations that are comfortably inside an
access window. Prefer mid-window times and modest steering margins over edge
cases. Avoid riding thresholds for access, solar elevation, off-nadir, slew
gap, convergence, overlap, or pixel-scale ratio.

Build candidate stereo products before committing them to the final schedule:

1. Pair or triple observations for the same target.
2. Keep pairs close enough in midpoint time.
3. Favor viewpoint diversity, but not extreme off-nadir geometry.
4. For tri-stereo, include one near-nadir anchor when possible.
5. Rank products by new target coverage first, then expected quality.

If a target has many single observations but no score, the likely failure is
that those observations never form a valid stereo or tri-stereo product.

## Insert Products Atomically

Schedule a product as one unit. Tentatively insert all observations for that
pair or triple into the per-satellite timelines. If any observation conflicts,
causes same-satellite overlap, or leaves too little slew-plus-settle time,
reject or move the whole product rather than leaving orphaned single images.

Keep each satellite's actions sorted by start time. After each insertion, check
only the neighboring actions on that satellite for overlap and transition gap
problems. Cross-satellite observations do not conflict with each other, but each
satellite still has its own timeline constraints.

## Coverage First, Quality Second

The safest growth loop is:

1. Seed one valid product for as many targets as possible.
2. Repair conflicts by removing the lowest-value whole product, not a random
   single observation.
3. Upgrade covered targets only when the replacement keeps validity.
4. Add tri-stereo upgrades after pair coverage is stable.

Do not spend the whole run polishing one target while many targets have no
valid product. Normalized quality is averaged over all targets, so uncovered
targets contribute zero.

## Fast Diagnosis

- Invalid file: check timestamp format, duration limits, horizon containment,
  known IDs, same-satellite overlap, and slew gaps first.
- Valid but zero score: your observations are legal singles but fail product
  rules. Add same-target pairs/triples with better viewpoint separation.
- Many pair failures: back away from thresholds. Use more central access times,
  less extreme steering, and similar pixel scale.
- Repair collapse: insert fewer products per satellite or remove low-quality
  products that block several uncovered targets.

For a worked workflow, read `examples/product_first_workflow.md`.
