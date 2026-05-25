# Panel C Trace Transcription: Case-Adaptive Search

## Summary

This report selectively transcribes the Relay Constellation trace for `Codex CLI + GPT-5.4` on `case_0003`. The mechanism is case-adaptive search: the evaluated system reads the relay-network contract, preserves a valid empty solution, constructs a valid backbone-only contact plan, identifies exactly which demand-window samples remain unserved, changes its search policy around those local bottlenecks, handles an official altitude-boundary rejection, preserves a full-service incumbent, and then performs a narrow local refinement for latency without giving up full service.

The main finding is that the final success is not ordinary parameter sweeping. The trace shows the system shrinking the problem from "search relay constellations" to "close 55 unserved routing-grid samples," with the main holes concentrated in `demand_001`, `demand_003`, and `demand_005`, while the verifier also shows one `demand_002` miss. It abandons an expensive broad sweep, introduces candidate scoring by incumbent miss closure, coarsens the orbital grid when propagation remains too costly, refines near promising relay seeds, and uses the official verifier to accept or reject the resulting plans. The final plan uses two added relays and 61 validated link actions; the verifier reports `service_fraction = 1.0` and `worst_demand_service_fraction = 1.0`.

## Plain-English Task Contract

Relay Constellation is a network-augmentation task. The case provides a fixed 96-hour planning horizon, an immutable medium-Earth-orbit relay backbone, fixed ground endpoints, demanded communication windows between endpoint pairs, and hard constraints on added relays and link activations. The evaluated system may add a limited number of relay satellites and must submit a time-bounded contact plan: ground-link and inter-satellite-link actions that say when physical links are active.

The system does not submit routes, per-demand service assignments, or latency claims. The official checker constructs a time-varying communication graph from the submitted link activations. At each routing-grid sample, it checks whether the source endpoint and destination endpoint for an active demand window are connected through feasible ground links and inter-satellite links. `ISL` means inter-satellite link. A demand window is a requested interval during which one ground endpoint must be connected to another. The service objective is the fraction of demanded samples served, with the worst-demand service fraction as the key robustness metric. The case also has a hard altitude ceiling: added relays must stay below `max_altitude_m`.

For `case_0003`, the manifest visible in the trace says there are at most 8 added relays, an altitude ceiling of 1,500,000 meters, a 60-second routing step, and five demanded windows. The final solution is compact because it reaches full service with two added relays rather than filling the allowed budget.

## Methodology

Evidence basis: the chronological beats below were checked against the event export from `seq 0` through `seq 554`. The trace is the evidence for what the evaluated system saw and did. The benchmark README is used only to explain terms and contract context.

The beats below focus on evidence that the search policy changed in response to current-case bottlenecks. I include failed variants and boundary-condition rejections because they make the final compact full-service plan intelligible.

## Chronological Selective Transcription

### Beat 1: The evaluated system acquires the relay contract and sees that routes are verifier-derived

**Trace anchors:** command at `seq 23`, output at `seq 28`.

**Event type:** contract acquisition.

**Exact snippet:**

```text
# Relay-Network Augmentation Planning Problem
...
Your job is to produce `solution.json` with:

- any additional relay satellites you want to add
- a time-bounded link-activation plan that improves service across the demanded windows
...
You do not submit routes, per-demand service assignments, or latency calculations. Instead, the validator builds a time-varying communication graph
```

This matters because the later private path search is not treated as a submitted authority. The official artifact is still link activation. Routes and service are derived by the verifier.

### Beat 2: The manifest and demands define a small, hard-constrained current case

**Trace anchors:** `seq 25`, `seq 27`.

**Event type:** case inspection.

**Exact snippets:**

```json
{
  "benchmark": "relay_constellation",
  "case_id": "case_0003",
  "constraints": {
    "max_added_satellites": 8,
    "max_altitude_m": 1500000.0,
    "max_eccentricity": 0.02,
    "max_inclination_deg": 85.0,
    "max_isl_range_m": 20000000.0,
    "max_links_per_endpoint": 1,
    "max_links_per_satellite": 3,
    "min_altitude_m": 500000.0,
    "min_inclination_deg": 20.0
  },
  "routing_step_s": 60,
  "scoring": {
    "primary_metric": "service_fraction",
    "secondary_metric": "worst_demand_service_fraction"
  }
}
```

```text
demand_004: ground_002 -> ground_005, 2026-01-02T11:50:00Z to 2026-01-02T12:35:00Z
demand_003: ground_002 -> ground_003, 2026-01-03T12:20:00Z to 2026-01-03T13:50:00Z
demand_001: ground_001 -> ground_004, 2026-01-03T12:40:00Z to 2026-01-03T13:40:00Z
demand_002: ground_001 -> ground_004, 2026-01-03T17:35:00Z to 2026-01-03T18:35:00Z
demand_005: ground_002 -> ground_005, 2026-01-04T05:25:00Z to 2026-01-04T06:55:00Z
```

The trace later shows all five demanded windows. The key point is that the system is solving a small set of concrete windows with a hard relay budget and a hard altitude ceiling.

### Beat 3: It creates an empty valid baseline before optimizing

**Trace anchors:** `seq 36-41`, verifier output at `seq 49`.

**Event type:** baseline construction and official verifier.

**Exact snippets:**

```text
I have enough structure to create a baseline deliverable now. I’m writing an empty but valid `solution.json` first, then I’ll iterate with generated candidates and the verifier to improve service.
```

```json
{
  "added_satellites": [],
  "actions": []
}
```

```json
{
  "valid": true,
  "diagnostics": {
    "allocation": {
      "sample_count_with_active_demands": 285,
      "served_demand_sample_count": 0,
      "unserved_demand_sample_count": 345
    },
    "per_demand_served_sample_counts": {
      "demand_001": 0,
      "demand_002": 0,
      "demand_003": 0,
      "demand_004": 0,
      "demand_005": 0
    }
  },
  "metrics": {
    "service_fraction": 0.0,
    "worst_demand_service_fraction": 0.0
  }
}
```

This establishes a valid incumbent immediately. It is empty and useless for service, but it satisfies the artifact shape and prevents the run from depending on a late file creation.

### Beat 4: It switches from black-box probing to direct geometry

**Trace anchor:** `seq 51`.

**Event type:** search-policy statement.

**Exact snippet:**

```text
I’m switching from black-box probing to direct geometry computation now. The next step is to propagate the backbone, measure which ground and inter-satellite links are feasible on the routing grid, and then synthesize active links only where they can improve demanded connectivity.
```

This is the first explicit policy shift. The system will not randomly mutate JSON and re-run the verifier; it will build a local model of feasible graph connectivity and use the verifier for confirmation.

### Beat 5: It computes a backbone-only service estimate per demand window

**Trace anchors:** command at `seq 129`, output at `seq 139`.

**Event type:** private link-graph analysis.

**Exact snippet:**

```text
demand_004 45 / 45 1.0
demand_003 76 / 90 0.8444444444444444
demand_001 30 / 60 0.5
demand_002 60 / 60 1.0
demand_005 80 / 90 0.8888888888888888
```

This is the first bottleneck map. The existing backbone appears to fully serve `demand_004` and `demand_002`, partially serve `demand_003` and `demand_005`, and serve only half of `demand_001`. The search target is already narrower than the whole problem.

### Beat 6: The system localizes misses to disconnected ISL graph periods

**Trace anchors:** command at `seq 143`, output at `seq 153`, summary at `seq 155`.

**Event type:** bottleneck diagnosis.

**Exact snippets:**

```text
demand_004 bad 0 of 45

demand_003 bad 14 of 90
 idx 2180 src ['backbone_002', 'backbone_008'] dst ['backbone_007'] isl [('backbone_001', 'backbone_006'), ('backbone_002', 'backbone_008'), ('backbone_003', 'backbone_008'), ('backbone_004', 'backbone_006')]
...
```

```text
I’ve narrowed the problem: the existing backbone is mostly adequate, and the misses come from brief disconnected periods in the ISL graph. I’m writing a solver script now that builds per-minute feasible paths, emits a valid action plan, and then I’ll layer in added satellites through a focused candidate search.
```

This is the case-adaptive core. The system does not decide to add relays because "more relays are good." It identifies the current case's unserved samples and the graph components that fail to connect during those samples.

### Beat 7: It introduces a per-minute path abstraction

**Trace anchor:** solver creation at `seq 162`.

**Event type:** solver code.

**Exact snippet:**

```python
@dataclass(frozen=True)
class Demand:
    demand_id: str
    source: str
    destination: str
    start_idx: int
    end_idx: int

@dataclass
class PathChoice:
    demand_id: str
    nodes: List[str]
    length_m: float
    edge_keys: Tuple[Tuple[str, ...], ...]
    sat_degree: Counter
```

This internal representation mirrors the official routing-grid problem: for each demand and sample, it needs a feasible path through a graph. The submitted artifact will still be link activations, but the search abstraction is now path-based.

### Beat 8: The first solver variant fails on no-path cases and is repaired

**Trace anchors:** run at `seq 168`, failure at `seq 178`, repair at `seq 182`.

**Event type:** failed variant and code repair.

**Exact snippet:**

```text
networkx.exception.NetworkXNoPath: No path between ground_002 and ground_003.
```

The event export then shows a targeted code repair:

```text
The first run failed on a normal no-path case from `networkx.shortest_simple_paths`. I’m patching the helper to treat that as “no path” instead of crashing, then rerunning the search.
```

The subsequent patch changes `shortest_simple_paths` so `NetworkXNoPath` during path iteration returns the paths collected so far:

```python
try:
    for path in iterator:
        results.append(make_path_choice(demand.demand_id, graph, path))
        if len(results) >= MAX_PATHS:
            break
except nx.NetworkXNoPath:
    return results
```

This failure is not the central mechanism, but it matters because it shows the search code being made robust to exactly the condition the case contains: some source-destination pairs are disconnected at some samples.

### Beat 9: The official verifier confirms a non-empty backbone incumbent and quantifies remaining gaps

**Trace anchors:** `seq 256-275`, especially verifier result `seq 269`.

**Event type:** official verifier output.

**Exact snippet:**

```json
{
  "valid": true,
  "diagnostics": {
    "action_counts": {
      "ground_link_actions": 21,
      "inter_satellite_link_actions": 6,
      "total": 27,
      "validated_actions": 27
    },
    "allocation": {
      "sample_count_with_active_demands": 285,
      "served_demand_sample_count": 290,
      "unserved_demand_sample_count": 55
    },
    "per_demand_served_sample_counts": {
      "demand_001": 30,
      "demand_002": 59,
      "demand_003": 76,
      "demand_004": 45,
      "demand_005": 80
    }
  },
  "metrics": {
    "service_fraction": 0.8433333333333334,
    "worst_demand_service_fraction": 0.5
  }
}
```

Then the system summarizes:

```text
The backbone baseline verifies at `service_fraction = 0.8433`, with the main holes concentrated in `demand_001`, `demand_003`, and `demand_005`. The augmentation search is still running, and those three windows are exactly what it’s trying to bridge.
```

This is stronger than the earlier private estimate because the official verifier confirms both validity and the gap population. The remaining problem is 55 unserved demand-samples, not an undefined relay-design challenge.

### Beat 10: It probes uncovered minutes directly

**Trace anchors:** `seq 287-289`.

**Event type:** targeted diagnostic probe.

**Exact snippet from the command body:**

```python
# uncovered sample requirements from earlier analysis
# demand_003 gaps 2180-2193
# demand_001 gaps 2209-2238
# demand_005 gaps roughly 3235-3239 and 3253-3257
```

The agent says:

```text
I’m also probing the uncovered minutes directly to see whether a single low-orbit relay can bridge the disconnected backbone components. That gives me a fast read on whether the search should keep favoring one-satellite or two-satellite designs.
```

The search has now become explicitly local to gap samples. It is not merely scanning all orbital parameters for aggregate score.

### Beat 11: It rejects the broad exhaustive scorer as too expensive for the real bottleneck size

**Trace anchors:** `seq 329`, `seq 332`, kill command at `seq 334`.

**Event type:** search-policy change.

**Exact snippets:**

```text
The exhaustive scorer is likely too broad relative to the real problem size, so I’m preparing to pivot if needed: rank candidate relays only on the 55 currently unserved samples, then run full verification on the best few combinations.
```

```text
I’m cutting off the broad sweep and switching to a focused gap-driven search. The exhaustive scorer is too expensive relative to the fact that only 55 samples remain unserved.
```

This is the clearest "case-adaptive search" moment. The system uses the current case's gap count to change the search algorithm, not just its parameters.

### Beat 12: Candidate ranking becomes a function of incumbent miss closure

**Trace anchor:** patch at `seq 340`.

**Event type:** solver code.

**Exact snippet:**

```python
def unserved_demand_samples(evaluation):
    misses = []
    ...
    if demand_id not in served_here:
        misses.append((sample_idx, demand_id))
    return misses

def gap_gain_score(...):
    gain = 0
    ...
    if demand_id in options:
        gain += 1
    return gain
```

The search no longer ranks a relay by generic visibility or broad graph quality. It ranks by whether that relay opens paths for currently unserved demand samples in the incumbent solution.

### Beat 13: A 720-candidate focused pass is still too expensive, so the grid becomes coarse-to-refine

**Trace anchors:** output at `seq 360`, policy change at `seq 396`, patches at `seq 402-410`.

**Event type:** failed expensive variant and search compression.

**Exact snippets:**

```text
Baseline score: (290, 0.5, -8401909853.25765, 0) actions: 27
Baseline misses: 55
Propagating 720 candidate satellites...
```

```text
The 30-degree orbit grid is too expensive for the J2 propagator. I’m shrinking to a coarse 60-degree search, then refining only around the most promising relays instead of spending time on weak candidates.
```

```python
REFINE_STEP_DEG = 30
REFINE_SEEDS = 6
RAAN_DEG = list(range(0, 360, 60))
MEAN_ANOMALY_DEG = list(range(0, 360, 60))
```

This is another policy adaptation. The target remains gap closure, but the search budget is reduced by using a coarse orbital grid and local refinement around promising seeds.

### Beat 14: The focused search finds a full-service two-relay pair internally

**Trace anchor:** `seq 442`.

**Event type:** solver output.

**Exact snippet:**

```text
propagated 180/180
Scoring candidates on baseline misses...
Top coarse gap scorers: [(53, 'augment_85_120_120'), (53, 'augment_75_120_120'), (53, 'augment_65_180_120'), ...]
Propagating 74 refinement candidates...
...
Running full evaluation on top pairs...
New best pair: augment_75_150_120 augment_55_180_150 (345, 1.0, -10172912301.709002, -2)
New best pair: augment_55_180_150 augment_65_120_120 (345, 1.0, -10131095280.868984, -2)
Best combo: ['augment_55_180_150', 'augment_65_120_120']
Best score: (345, 1.0, -10131095280.868984, -2)
```

The tuple is private, but its meaning is visible in context: 345 served demand-samples, worst-demand service 1.0, a path-length or latency proxy, and 2 added relays. The important part is that the internal search has found a compact full-service plan.

### Beat 15: The official verifier rejects the first full-service pair on a hard altitude boundary

**Trace anchors:** verifier call at `seq 446`, output at `seq 454`.

**Event type:** official verifier failure.

**Exact snippet:**

```json
{
  "valid": false,
  "diagnostics": {
    "orbit_summaries": [
      {
        "apogee_altitude_m": 1500000.0000000047,
        "satellite_id": "augment_55_180_150"
      }
    ]
  },
  "violations": [
    "Satellite augment_55_180_150 apogee altitude 1500000.000 m exceeds max_altitude_m 1500000.000 m"
  ]
}
```

This is a boundary-condition rejection, not a service-search failure. The relay is exactly at the altitude ceiling in the private construction, and floating-point propagation or element conversion puts it a few nanometers over.

### Beat 16: The repair lowers the relay shell below the altitude ceiling

**Trace anchors:** `seq 456-458`.

**Event type:** diagnosis and code patch.

**Exact snippets:**

```text
The verifier caught a hard-boundary issue, not a structural one: one added relay sat sat exactly on the altitude ceiling and rounded a few nanometers high. I’m moving the candidate shell slightly below the max altitude and rerunning the focused search.
```

```python
ALTITUDE_M = 1_499_000.0
```

The repair is targeted. It does not abandon the two-relay structure; it changes the candidate shell to respect the official boundary with margin.

### Detail under Beat 16: The repaired two-relay plan reaches full service under the verifier

**Trace anchors:** rerun output at `seq 481`, verifier output at `seq 495`.

**Event type:** solver output and official verifier success.

**Exact snippet:**

```text
Best combo: ['augment_45_180_150', 'augment_65_120_120']
```

```json
{
  "valid": true,
  "diagnostics": {
    "action_counts": {
      "ground_link_actions": 37,
      "inter_satellite_link_actions": 18,
      "total": 55,
      "validated_actions": 55
    },
    "allocation": {
      "served_demand_sample_count": 345,
      "unserved_demand_sample_count": 0
    }
  },
  "metrics": {
    "service_fraction": 1.0,
    "worst_demand_service_fraction": 1.0
  }
}
```

This is the first official full-service solution after the altitude repair. The case-specific search has closed every previously unserved demand sample with two relays.

### Detail under Beat 16: The system preserves full service and refines only for lower latency

**Trace anchors:** `seq 497-523`, final local output at `seq 535`.

**Event type:** incumbent-preserving local refinement.

**Exact snippets:**

```text
I have a valid full-service plan now. I’m doing one narrow local search around the winning two relays to see if there’s a lower-latency pair nearby without giving up service.
```

```python
base_ids=['augment_45_180_150','augment_65_120_120']
...
neighborhood(inc0, raan0, mean0)
```

```text
new best augment_35_210_120 augment_55_090_120 (345, 1.0, -9937089898.122602, -2)
...
FINAL augment_35_210_120 augment_55_090_120 (345, 1.0, -9937089898.122602, -2)
```

The search now has a hierarchy: do not sacrifice full service; compare two-relay full-service candidates by path-length or latency proxy. That is incumbent preservation, not a reset.

### Detail under Beat 16: The final verifier accepts the refined two-relay plan

**Trace anchors:** verifier call at `seq 539`, output at `seq 549`, final message at `seq 551`.

**Event type:** official verifier success and final claim.

**Exact snippet:**

```json
{
  "valid": true,
  "diagnostics": {
    "action_counts": {
      "ground_link_actions": 39,
      "inter_satellite_link_actions": 22,
      "total": 61,
      "validated_actions": 61
    },
    "allocation": {
      "served_demand_sample_count": 345,
      "unserved_demand_sample_count": 0
    },
    "orbit_summaries": [
      {
        "satellite_id": "augment_35_210_120",
        "apogee_altitude_m": 1499000.0,
        "inclination_deg": 35.0
      },
      {
        "satellite_id": "augment_55_090_120",
        "apogee_altitude_m": 1499000.0000000019,
        "inclination_deg": 55.00000000000001
      }
    ]
  },
  "metrics": {
    "service_fraction": 1.0,
    "worst_demand_service_fraction": 1.0
  }
}
```

```text
`./verifier case/ solution.json` returns `valid: true` with `service_fraction = 1.0`, `worst_demand_service_fraction = 1.0`, `mean_latency_ms = 96.077`, and `latency_p95_ms = 163.790`. The final augmentation uses 2 added relays: `augment_35_210_120` and `augment_55_090_120`.
```

The final authority is the official verifier, not the private score tuple. The final plan closes all 345 demanded service samples and uses only two added relays.

## Findings

First, the trace supports case-adaptive search because the search policy changes in response to a measured current-case bottleneck. The system starts with an empty valid artifact, builds a backbone plan, sees 55 unserved demand samples, identifies the affected windows, and then ranks candidate relays by their ability to close those specific misses.

Second, the trace includes real failed variants and repairs. The initial path enumeration can crash when no path exists. The broad candidate propagation is too expensive. The focused but still 720-candidate pass is too slow. The first internally full-service pair fails the official altitude ceiling by a boundary rounding amount. These failures are not hidden; each one changes the next action.

Third, the official verifier remains the final arbiter. Private geometry and path search guide candidate generation, but verifier output controls acceptance. The altitude failure is especially useful for a figure because it shows a hard-boundary repair: full-service in the private model is not enough until the official checker accepts the orbit.

Fourth, the final success is compact and case-specific. The system does not use the allowed 8-relay budget. It finds two relays that bridge the current case's disconnected periods, then locally refines the pair while preserving full service.

## Per-Trace Appendix

- Trace: `experiments/main_agentic/reports/traces/data/events/relay_constellation__codex__test__case_0003.js`
- Evaluated system: `Codex CLI + GPT-5.4`
- Task family and case: Relay Constellation, `case_0003`
- Contract acquisition: `seq 23-28`
- Empty valid baseline: `seq 36-49`
- Backbone-only private estimate: `seq 129-139`
- Bottleneck diagnosis: `seq 143-155`
- Per-minute path solver: `seq 162`
- Official backbone incumbent: `seq 258-275`
- Focused gap-driven search pivot: `seq 329-340`
- Coarse-to-refine pivot: `seq 360-410`
- First internally full-service pair: `seq 442`
- Altitude-boundary rejection: `seq 446-456`
- Repaired official full-service incumbent: `seq 481-495`
- Local refinement and final accepted plan: `seq 497-551`

## Figure-Design Usable Snippets

1. Bridge: The official artifact is link activation, not route claims. Suggested snippet: `You do not submit routes... validator builds a time-varying communication graph`. Highlight: `do not submit routes`.

2. Bridge: The official checker accepted the empty artifact as a valid baseline. Suggested snippet: `"added_satellites": [], "actions": []`. Highlight: `empty baseline`.

3. Bridge: The backbone has specific partial-service gaps. Suggested snippet: `demand_001 30 / 60 0.5`, `demand_003 76 / 90`. Highlight: `30 / 60`.

4. Bridge: The current-case bottleneck is graph disconnection. Suggested snippet: `misses come from brief disconnected periods in the ISL graph`. Highlight: `disconnected`.

5. Bridge: The official verifier quantifies the incumbent. Suggested snippet: `unserved_demand_sample_count: 55`. Highlight: `55`.

6. Bridge: The search becomes gap-driven. Suggested snippet: `rank candidate relays only on the 55 currently unserved samples`. Highlight: `55`.

7. Bridge: The grid adapts to runtime cost. Suggested snippet: `shrinking to a coarse 60-degree search`. Highlight: `60-degree`.

8. Bridge: The first full-service plan fails a hard boundary. Suggested snippet: `apogee altitude ... exceeds max_altitude_m`. Highlight: `exceeds`.

9. Bridge: The repair is targeted. Suggested snippet: `ALTITUDE_M = 1_499_000.0`. Highlight: `1_499_000`.

10. Bridge: The final verifier accepts full service. Suggested snippet: `service_fraction = 1.0`, `worst_demand_service_fraction = 1.0`. Highlight: `1.0`.
