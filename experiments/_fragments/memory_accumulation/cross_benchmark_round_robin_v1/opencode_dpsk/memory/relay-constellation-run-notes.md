# Relay-Network Augmentation Run Notes

## Previous Case (8-sat backbone)

### Final Metrics
- service_fraction: 0.8189 (81.89%)
- worst_demand_service_fraction: 0.6778 (demand_006)
- mean_latency_ms: 187.35
- latency_p95_ms: 258.62
- num_added_satellites: 3

... (see below for approach)

---

## Case 0002 (6-sat backbone, 55° inclination, 12000 km altitude)

### Final Metrics
- service_fraction: 0.4422 (44.22%)
- worst_demand_service_fraction: 0.1000 (demand_006)
- mean_latency_ms: 165.57
- latency_p95_ms: 216.52
- num_added_satellites: 6

### Key Insight: Two Disconnected Backbone Subnetworks

The 6 backbone sats form two disconnected networks ("triangles"):
- Triangle A: {backbone_001, backbone_004, backbone_005} (planes 0,1,2)
- Triangle B: {backbone_002, backbone_003, backbone_006} (planes 0,1,2)

Cross-plane ISLs (6 pairs) are geometrically feasible ~39-52% of the time, connecting sats within each triangle. But same-plane opposite sats are 36,750 km apart (>> 20,000 km max ISL), so the two triangles are permanently disconnected.

Demands that cross triangles (007 and 006) REQUIRE augmentation satellites to bridge the gap.

### Solver Approach

1. **Propagation**: Use brahe NumericalOrbitPropagator with J2-only gravity, static EOP from_zero().
2. **ISL feasibility**: Check BOTH range (<= max_isl_m - 200m margin) AND Earth clearance (line segment must not intersect Earth sphere): use perpendicular distance when closest point is on segment, otherwise endpoint distance.
3. **Ground visibility**: ECEF elevation check with ENZ local frame.
4. **Path search**: For each demand, find path (src_ep -> src_sat -> [ISL] -> dst_sat -> dst_ep) maximizing simultaneous feasible samples (intersection of all link feasibility masks).
5. **Conflict handling**: Overlapping demands at shared endpoints MUST use same satellite (max_links_per_endpoint=1). The router handles unit-capacity allocation (typically giving all to the lower-latency demand).
6. **LEO configuration**: 3 sats at 55° incl (for backbone bridging) + 3 sats at 25° incl (for equatorial ground coverage), all at 800 km altitude, near-circular.

### Critical Lessons

1. **Simultaneous vs average feasibility**: Average visibility percentage is NOT enough. Must compute intersection (AND) of all link feasibility masks to count truly simultaneous feasible samples.
2. **Earth clearance for ISL**: The Earth clearance check must correctly handle the closest-point-on-segment test: P1 + t*(P2-P1), t = -P1·D/|D|^2. If 0<=t<=1, use perpendicular distance; otherwise use min(|P1|, |P2|). Add 200m margin for propagation differences.
3. **Degree constraint**: max_links_per_endpoint=1 is the tightest constraint. Overlapping demands sharing an endpoint MUST use the same satellite (one physical link). The verifier router maximizes total weight → lower-latency demand gets all capacity.
4. **Two-hop LEO bridges only**: LEO-to-backbone ISLs rarely bridge both triangles simultaneously for long periods due to fast LEO motion (~100 min period vs ~413 min for backbone).
5. **LEO-ground links**: LEO sats at 600-1000 km, even at low inclination (25°), only see equatorial ground stations (like Singapore) ~5-13% of the time during demand windows, not better than backbone sats.

### Output Schema
- added_satellites: [{satellite_id, x_m, y_m, z_m, vx_m_s, vy_m_s, vz_m_s}, ...]
- actions: [{action_type: "ground_link"|"inter_satellite_link", start_time, end_time, ...}, ...]
- Times must be on the 60s routing grid; start_time/end_time are ISO 8601
