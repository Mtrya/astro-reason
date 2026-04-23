# Conjunction Data Messages

Conjunction Data Messages (CDMs) are collision risk assessments published by the 18th Space Defense Squadron. Each CDM describes a predicted close approach between two cataloged objects, including the time of closest approach (TCA), miss distance, and probability of collision ($P_c$).

Space-Track publishes CDMs through the `CDMPublic` request class, which uses the `expandedspacedata` controller. Unlike GP or SATCAT data, CDMs do not have a dedicated typed response struct -- use `query_json()` to receive results as a list of dictionaries (Python) or `Vec<serde_json::Value>` (Rust).

## CDM Fields

The following table lists commonly used CDM fields for filtering and analysis:


| Field | Description |
|-------|-------------|
| `CDM_ID` | Unique CDM identifier |
| `CREATED` | CDM creation timestamp |
| `EMERGENCY_REPORTABLE` | Emergency reportable flag (`Y`/`N`) |
| `TCA` | Time of Closest Approach |
| `MIN_RNG` | Minimum range at TCA (km) |
| `PC` | Probability of Collision |
| `SAT_1_ID` | NORAD catalog ID of the first object |
| `SAT_2_ID` | NORAD catalog ID of the second object |
| `SAT_1_NAME` | Name of the first object |
| `SAT_2_NAME` | Name of the second object |
| `SAT1_OBJECT_TYPE` | Object type of the first object (e.g., `PAYLOAD`, `DEBRIS`) |
| `SAT2_OBJECT_TYPE` | Object type of the second object |
| `SAT1_RCS` | Radar cross-section of the first object |
| `SAT2_RCS` | Radar cross-section of the second object |
| `SAT_1_EXCL_VOL` | Exclusion volume of the first object |
| `SAT_2_EXCL_VOL` | Exclusion volume of the second object |


**JSON-Only Responses**
CDM queries return unstructured JSON. Use `query_json()` on the client to parse the response as `list[dict]` (Python) or `Vec<serde_json::Value>` (Rust). There is no typed `CDMRecord` struct.

## Query Examples

The examples below demonstrate building CDM queries. Each query constructs a URL path; execute it with `SpaceTrackClient.query_json()`.


```python
import brahe as bh
from brahe.spacetrack import operators as op

# Query high-probability conjunction events (Pc > 1e-3)
# CDMPublic uses the expandedspacedata controller automatically
query = (
    bh.SpaceTrackQuery(bh.RequestClass.CDM_PUBLIC)
    .filter("PC", op.greater_than("1.0e-3"))
    .order_by("TCA", bh.SortOrder.DESC)
    .limit(25)
)

url_path = query.build()
print(f"High-probability CDMs:\n  {url_path}")

# Query CDMs for a specific satellite (e.g., ISS, NORAD 25544)
query = (
    bh.SpaceTrackQuery(bh.RequestClass.CDM_PUBLIC)
    .filter("SAT_1_ID", "25544")
    .order_by("TCA", bh.SortOrder.DESC)
    .limit(10)
)

url_path = query.build()
print(f"\nCDMs involving ISS:\n  {url_path}")

# Query upcoming conjunctions within the next 7 days
query = (
    bh.SpaceTrackQuery(bh.RequestClass.CDM_PUBLIC)
    .filter("TCA", op.inclusive_range(op.now(), op.now_offset(7)))
    .order_by("TCA", bh.SortOrder.ASC)
)

url_path = query.build()
print(f"\nUpcoming conjunctions (next 7 days):\n  {url_path}")
```


### Working with CDM Results

After executing a CDM query with `query_json()`, each element in the returned list is a dictionary with string keys matching the field names above:

```
# Example: iterating over CDM results (after query execution)
for cdm in results:
    tca = cdm["TCA"]
    pc = float(cdm["PC"])
    sat1 = cdm["SAT_1_NAME"]
    sat2 = cdm["SAT_2_NAME"]
    miss_km = float(cdm["MIN_RNG"])
    print(f"{tca}: {sat1} vs {sat2}, Pc={pc:.2e}, miss={miss_km:.1f} km")
```

---

## See Also

- [Common Queries](common_queries.md) -- GP, SATCAT, and Decay query patterns
- [Query Builder](query_builder.md) -- Filters, ordering, limits, and output formats
- [Client](client.md) -- Authentication and query execution
- [Operators Reference](../../../library_api/ephemeris/spacetrack/operators.md) -- All operator functions