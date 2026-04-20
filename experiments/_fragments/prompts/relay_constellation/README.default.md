# Relay-Network Augmentation Planning Problem

This workspace contains one relay-network planning problem over a fixed mission horizon.

You are given:

- case-wide timing and hard constraints in `case/manifest.json`
- an existing relay backbone and ground endpoints in `case/network.json`
- demanded communication windows between endpoint pairs in `case/demands.json`

Your job is to produce `solution.json` with:

- any additional relay satellites you want to add
- a time-bounded link-activation plan that improves service across the demanded windows

The existing backbone is fixed. This is an augmentation problem, not a greenfield redesign.

The modeled decision is: add a limited number of relay satellites and choose when physical links are active. You do not submit routes, per-demand service assignments, or latency calculations. Instead, the validator builds a time-varying communication graph from your active links and then computes how much demand can actually be served through that graph.

## What Good Solutions Do

A strong solution should:

- satisfy all hard validity rules
- serve as much demanded communication as possible
- avoid starving the worst-served demand
- reduce path latency when multiple service patterns are feasible
- avoid adding unnecessary satellites once service quality is already strong

In practical terms, valid service comes first, then robustness across demands, then latency, then augmentation efficiency.

## Files In This Workspace

- `case/manifest.json`: mission horizon, routing step, and hard orbit/link constraints
- `case/network.json`: immutable backbone satellites and ground endpoints
- `case/demands.json`: demanded communication windows with weights
- `{example_solution_name}`: example output shape when present
- `{verifier_location}`: local validation helper when present

## Expected Output

Write one JSON object named `solution.json` at the workspace root.

It should contain two top-level arrays:

- `added_satellites`
- `actions`

Each added satellite entry defines one solver-chosen initial state with:

- `satellite_id`
- `x_m`
- `y_m`
- `z_m`
- `vx_m_s`
- `vy_m_s`
- `vz_m_s`

Each action should activate one physical link interval with:

- `action_type`
- `start_time`
- `end_time`

For ground links, also include:

- `endpoint_id`
- `satellite_id`

For inter-satellite links, also include:

- `satellite_id_1`
- `satellite_id_2`

Do not submit end-to-end routes, latency claims, or service claims. Routing and service are derived during validation.

## Important Task Semantics

- Existing backbone satellites are immutable.
- Added satellites must satisfy the orbit constraints in `case/manifest.json`.
- Actions must stay on the public time grid and inside the mission horizon.
- A `ground_link` action turns on one endpoint-to-satellite link; an `inter_satellite_link` action turns on one satellite-to-satellite link.
- Links must be geometrically feasible when active.
- The same physical link cannot be overbooked, and per-sample endpoint/satellite link limits are enforced during validation.
- Ground endpoints are communication endpoints, not arbitrary intermediate relay nodes.
- Service is sampled inside the demanded windows. A demand is served at a sample only if the active links create a feasible end-to-end path between the demanded endpoints at that time.
- Latency is derived from total routed path length, so shorter useful paths matter only after basic service is achieved.

## Validation Notes

If the workspace exposes a verifier helper, use it for local iteration:

- `{verifier_command}`

Treat it as a local correctness check while you refine `solution.json`.
