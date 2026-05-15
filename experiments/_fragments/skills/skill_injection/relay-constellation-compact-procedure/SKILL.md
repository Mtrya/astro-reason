---
name: relay-constellation-compact-procedure
description: Use when solving AstroReason relay_constellation cases and you need a compact procedure for producing valid added_satellites and link actions that serve at least one demanded communication window.
---

# Relay Constellation Compact Procedure

Use this while solving the case. The workspace `README.md` is the authority for exact units, validity rules, and output schema.

## What To Do First

| State | Next action |
|---|---|
| No `solution.json` yet | Write `{"added_satellites": [], "actions": []}` and run `./verifier case/ solution.json`. |
| Empty file is valid | Pick one demand from `case/demands.json`; do not stop at valid zero service. |
| You have isolated links but `service_fraction=0` | Add the missing ingress, ISL, or egress link so one source endpoint connects to its destination endpoint. |
| Any verifier run gives `service_fraction > 0` | Save that file as the incumbent before adding more satellites or longer intervals. |

A legal relay file with no served demand is only a fallback. The first real goal is one verifier-confirmed served demand sample.

## Exact Solution Shape

Start with:

```json
{"added_satellites": [], "actions": []}
```

Added satellites use Cartesian state fields. The numbers below are shape placeholders; fill real states that satisfy `case/manifest.json` orbit limits.

```json
{
  "satellite_id": "new_relay_001",
  "x_m": 0.0,
  "y_m": 0.0,
  "z_m": 0.0,
  "vx_m_s": 0.0,
  "vy_m_s": 0.0,
  "vz_m_s": 0.0
}
```

Actions activate physical links. Use timestamps on the `routing_step_s` grid.

```json
{
  "action_type": "ground_link",
  "start_time": "ISO time on the routing_step_s grid",
  "end_time": "ISO time on the routing_step_s grid",
  "endpoint_id": "endpoint id from case/network.json",
  "satellite_id": "known satellite id"
}
```

```json
{
  "action_type": "inter_satellite_link",
  "start_time": "ISO time on the routing_step_s grid",
  "end_time": "ISO time on the routing_step_s grid",
  "satellite_id_1": "known satellite id",
  "satellite_id_2": "different known satellite id"
}
```

Do not submit routes, latency claims, or service claims. The verifier builds routes from your active physical links.

## Service Before Scale

Before optimizing latency or satellite count:

1. Pick one demand from `case/demands.json`.
2. Build a complete physical path from its source endpoint to destination endpoint for a few routing-grid samples.
3. Use ground links for endpoint-to-satellite ingress and egress.
4. Use inter-satellite links only when needed between satellites.
5. Run the verifier and keep the first file with `service_fraction > 0`.

Short verifier-confirmed intervals are better than long guessed intervals.

## Diagnose The Verifier Result

| State | What it means | Next move |
|---|---|---|
| `valid=false` | Orbit, schema, timing, link geometry, overlap, or link-cap rule failed. | Fix `violations`. Remove, shorten, retime, or replace rejected links. |
| `valid=true`, `service_fraction=0` | Links are legal but no demanded sample has a complete served path. | Choose one demand and build a complete source-to-destination path. |
| Nonzero service, `worst_demand_service_fraction=0` | At least one demand is still starved. | Use `metrics.per_demand` to choose the next unserved demand. |
| High service | Service is meaningful. | Preserve it before reducing satellites or latency. |

## Improve Service

Use this loop:

1. Keep the best nonzero-service `solution.json`.
2. Add or adjust a small set of links for one demanded window.
3. Run the verifier.
4. Compare `service_fraction`, `worst_demand_service_fraction`, `num_added_satellites`, `mean_latency_ms`, and `latency_p95_ms`.
5. Keep the change only if service improves or service stays stable while secondary metrics improve.

Private visibility calculations are only candidate generators. If the verifier rejects a link interval, trust the verifier and change the interval.

## Final Check

- `added_satellites` and `actions` are both arrays.
- Added satellite IDs are unique and do not collide with backbone IDs.
- Link times are on the routing grid and inside the horizon.
- Every intended demand service has active links forming a complete endpoint-to-endpoint path.
- `service_fraction` is nonzero unless time ran out before finding a served sample.
- The final file is the best verifier-confirmed nonzero-service incumbent.
