---
name: relay-constellation-service-strategy
description: Use when solving AstroReason relay_constellation cases and you need service-first relay augmentation strategy, complete demand-path construction, verifier-guided link repair, and worst-demand improvement tactics.
---

# Relay Constellation Service Strategy

Use this after the compact procedure has produced a valid file. The workspace `README.md` and verifier report remain the authorities.

## What To Do Next

| State | Next action |
|---|---|
| Valid but `service_fraction=0` | Pick one demand and build one complete source-to-destination path for a few grid samples. |
| Links are rejected | Shorten, retime, or replace the rejected link interval before adding more links. |
| Service is nonzero but some demand is zero | Use `metrics.per_demand` to choose the next starved demand. |
| Many links compete at one sample | Keep the path that serves a demand and respects endpoint/satellite link caps. |
| Service is high | Preserve service before trying to reduce satellites or latency. |

## Think In Complete Demand Paths

A feasible link is not enough. A demand sample is served only when active links form a complete path from the demand source endpoint to its destination endpoint.

For one demand and one short grid interval, sketch:

```text
source endpoint --ground_link-- satellite --optional ISLs-- satellite --ground_link-- destination endpoint
```

Then convert that sketch into physical `ground_link` and `inter_satellite_link` actions. Do not submit the route sketch itself.

## Seed One Served Demand

Before adding a large constellation:

1. Pick one demanded window, preferably high weight or easy-looking geometry.
2. Choose a small candidate relay set within manifest orbit limits.
3. Test short grid-aligned ground links from the source and destination endpoints.
4. Add inter-satellite links only when needed to connect ingress and egress satellites.
5. Run the verifier.
6. Save the first file with `service_fraction > 0`.

If `valid=true` and `service_fraction=0`, the next move is not latency optimization. The next move is to complete one served path.

## Schedule Links Per Sample, Then Compact

Work on a few routing samples first:

1. For each active demand sample, choose one complete path.
2. Check endpoint and satellite link caps before adding competing paths through the same node.
3. Prefer paths that serve a demand over isolated high-visibility links.
4. After verifier success, compact consecutive samples using the same physical link into one interval action.
5. Verify the compacted interval.

Short accepted intervals can be widened. Long guessed intervals often fail geometry or cap checks.

## Use Verifier Feedback

| Report signal | Next move |
|---|---|
| `valid=false` with action failures | Remove, shorten, retime, or replace the rejected links. |
| `action_counts` shows few validated links | Fix link schema, IDs, grid times, and geometry before adding satellites. |
| `allocation.served_demand_sample_count=0` | Build a complete source-to-destination path for one demand. |
| `metrics.per_demand` has zero-service demands | Pick one zero-service demand and build a short path for it. |
| Service is high but latency is weak | Try shorter paths only if service remains stable. |

Private propagation or visibility code is a candidate generator, not proof. If the verifier disagrees, change the candidate.

## Improve Worst Demand

After service is nonzero:

1. Sort `metrics.per_demand` by `service_fraction`.
2. Choose the worst demand that still has requested samples.
3. Add a short complete path for that demand.
4. Verify service and link-cap validity.
5. Keep the move if `worst_demand_service_fraction` or `service_fraction` improves.

Only reduce `num_added_satellites`, `mean_latency_ms`, or `latency_p95_ms` after service and worst-demand service are meaningful.

## Final Check

- Every action is a physical link activation.
- Every planned service improvement has source ingress, any needed ISLs, and destination egress.
- No ground endpoint is being used as a transit node.
- The schedule respects grid times and link caps.
- The final answer is the best verifier-confirmed nonzero-service incumbent.
