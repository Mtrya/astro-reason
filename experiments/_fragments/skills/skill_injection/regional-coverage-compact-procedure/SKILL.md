---
name: regional-coverage-compact-procedure
description: Use when solving AstroReason regional_coverage cases and you need a compact procedure for creating valid strip_observation schedules with nonzero weighted regional coverage.
---

# Regional Coverage Compact Procedure

Use this while solving the case. The workspace `README.md` is the authority for exact units, validity rules, and output schema.

## What To Do First

| State | Next action |
|---|---|
| No `solution.json` yet | Write `{"actions": []}` and run `./verifier case/ solution.json`. |
| Empty file is valid | Add one schema-correct `strip_observation` and verify `metrics.num_actions` becomes `1`. |
| One action is parsed but score is zero | Move that one action in time, roll sign, roll magnitude, or duration until one region gets coverage. |
| Any action gives nonzero score | Save that file as the incumbent before trying larger batches. |

Do not start with a dense script. First make the verifier parse one action, then make one action cover something.

## Exact Action Shape

Start with a complete `solution.json`:

```json
{"actions": []}
```

Then add one action with exactly these fields. Fill values from `case/manifest.json` and `case/satellites.yaml`.

```json
{
  "type": "strip_observation",
  "satellite_id": "satellite id from case/satellites.yaml",
  "start_time": "ISO time on the case time_step_s grid",
  "duration_s": 20,
  "roll_deg": 20.0
}
```

Do not submit polygons, centerlines, coverage claims, or access-window ids. You choose time, duration, satellite, and signed roll; the verifier derives strip geometry and coverage.

## Build A Small Strip Table

After the verifier parses one action, make a modest table of candidate strips:

1. Choose satellites from `case/satellites.yaml`.
2. Use times aligned to `manifest.time_step_s`.
3. Use durations inside each satellite's strip-duration limits.
4. Try both roll signs. Positive and negative look to opposite sides of the ground track.
5. Avoid roll values near sensor edge limits until you have a valid nonzero incumbent.

Verify a few candidates or small batches. The first goal is not a dense table; it is one valid strip that gives nonzero `weighted_coverage_ratio`.

## Diagnose The Verifier Result

| State | What it means | Next move |
|---|---|---|
| `valid=false` | A hard rule failed. | Fix `violations` first: schema, grid time, horizon, duration, roll band, overlap, slew gap, battery, duty, or region minimum. |
| `valid=true`, `num_actions=0` | The verifier ignored your rows as strip observations. | Rewrite one action with the exact five action fields. |
| `valid=true`, `num_actions>0`, `weighted_coverage_ratio=0` | Legal strips missed all scoring samples. | Change one action's time, roll sign, roll magnitude, or duration until one region receives coverage. |
| Valid and nonzero | You have an incumbent. | Keep this file and only replace it when verifier metrics improve. |

## Improve Coverage

Regional score is mostly unique coverage. Covering the same samples again does not help much.

Use this loop:

1. Keep the best valid nonzero `solution.json`.
2. Add or replace one strip.
3. Run the verifier.
4. Compare `weighted_coverage_ratio`, `coverage_ratio`, `region_coverages`, `num_actions`, and `min_battery_wh`.
5. Keep the change only if coverage improves or it repairs a required region.

Prefer strips that add fresh weighted coverage or help an undercovered region. Treat `num_actions` and `min_battery_wh` as secondary after coverage is nonzero.

## Final Check

- `solution.json` has only an `actions` array.
- Every action has `type: "strip_observation"`.
- Times and durations are on the public grid and inside the horizon.
- Same-satellite actions are sorted and have enough retargeting gap.
- `weighted_coverage_ratio` is nonzero unless time ran out before finding any coverage.
- The final file is the best valid nonzero verifier-confirmed incumbent, not the last risky candidate batch.
