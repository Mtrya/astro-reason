These fixtures lock the standalone `relay_constellation` verifier behavior.

Principles:

- keep cases tiny and interpretable
- prefer one behavior per fixture
- assert only stable, behavior-defining report fields
- use the canonical benchmark case files:
  - `manifest.json`
  - `network.json`
  - `demands.json`
  - `solution.json`
  - `expected.json`

Fixture set:

- `full_service_valid`
  - one demand, one backbone satellite, fully served
- `served_time_only_latency_valid`
  - one demand, partially served, latency computed only on served samples
- `ground_visibility_invalid`
  - scheduled ground link fails geometry validation
- `isl_occultation_invalid`
  - scheduled ISL fails Earth-occultation validation
- `concurrency_cap_invalid`
  - geometrically feasible actions exceed concurrency caps
- `contention_deterministic_valid`
  - two demands contend for one bottleneck edge and deterministic allocation picks one
- `ground_transit_forbidden_valid`
  - an apparent route through an intermediate ground endpoint is not considered service
