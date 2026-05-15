---
name: regional-coverage-strip-strategy
description: Use when solving AstroReason regional_coverage cases and you need strip candidate generation, marginal unique-coverage strategy, satellite-local insertion, repair, and bounded local-search tactics beyond the compact procedure.
---

# Regional Coverage Strip Strategy

Use this after the compact procedure has produced a verifier-parsed action. The workspace `README.md` and verifier report remain the authorities.

## What To Do Next

| State | Next action |
|---|---|
| No nonzero incumbent | Go back to the compact procedure and make one strip cover a region. |
| Valid nonzero but weak | Build a small candidate table and add one fresh-coverage strip at a time. |
| Candidate count is growing fast | Stop widening; keep a few candidates per satellite, region, roll sign, and time bucket. |
| Schedule became invalid | Roll back to the saved incumbent and repair only the named action or same-satellite cluster. |
| Many actions but little score movement | Replace repeated-coverage strips with undercovered-region candidates. |
| Considering CP-SAT | Use it only for a tiny pruned repair set after saving a valid nonzero incumbent. |

## Candidate Table

Build a small candidate table before dense sweeps:

- satellite id
- start time on `manifest.time_step_s`
- duration
- signed roll
- verifier result for a one-action or small-batch test
- estimated or observed regions touched
- current marginal verifier gain when tested

Start coarse. Keep a few alternatives per satellite, region, and roll sign. Widen time stride, roll grid, or duration choices only after you have saved a valid nonzero incumbent.

## Marginal Coverage Mindset

The useful score is fresh weighted coverage:

- A strip that covers new samples is valuable.
- A strip that repeats already covered samples is usually weak.
- A strip that helps an undercovered or required region can be worth keeping even if its global gain is modest.

When comparing candidate moves, use this order after each verifier run:

1. validity
2. higher `weighted_coverage_ratio`
3. higher `coverage_ratio` and better `region_coverages`
4. fewer actions only after coverage is comparable
5. healthier `min_battery_wh` after coverage is comparable

## Satellite-Local Insertion

Keep accepted actions sorted by `satellite_id` and start time.

Before testing a candidate in the full file:

1. Find its same-satellite predecessor and successor.
2. Check obvious interval overlap.
3. Leave comfortable time for roll retargeting and settling.
4. Insert one candidate.
5. Run the verifier.
6. Roll back if validity breaks or coverage does not improve.

Most invalid schedule bugs come from adding many same-satellite actions before checking local neighbors.

## Repair And Local Search

Use small neighborhoods:

- **Invalid repair:** remove or retime the action named in `violations`.
- **Low-gain repair:** remove the selected strip with the smallest unique coverage loss.
- **Same-satellite window:** choose one satellite and one crowded time window, remove weak strips, then greedily refill.
- **Region rescue:** choose the lowest `region_coverages` entry and test strips aimed at that region before polishing already covered regions.
- **Swap:** replace one weak strip with one stronger strip if the verifier confirms improvement.

Always keep the best valid nonzero file before trying a neighborhood move.

## Optional Tiny CP-SAT Repair

Use CP-SAT only after you already have:

- a valid nonzero incumbent
- a small trusted candidate set
- clear pairwise conflicts
- a deterministic greedy fallback

Model only a tiny subset repair: one Boolean per candidate and simple conflict constraints. If CP-SAT times out or returns no feasible selected set, keep the saved incumbent. Do not build a giant exact model before the first nonzero verifier score.

## Stop Conditions

Stop widening and repair the model if:

- `num_actions=0`
- many valid actions still give zero `weighted_coverage_ratio`
- adding actions does not move `region_coverages`
- repair removes many strips
- the run is spending more time generating candidates than preserving improved `solution.json`

The final answer should come from the best verifier-confirmed incumbent, not from an unfinished search script.
