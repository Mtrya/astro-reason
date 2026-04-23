# Common Queries

This page shows practical query patterns for everyday Space-Track tasks: fetching current ephemeris data, filtering the active catalog, and monitoring upcoming decays.

For the query builder API and operator reference, see [Query Builder](query_builder.md). For executing queries against the API, see [Client](client.md).

## Latest Ephemeris for a Single Object

The most common query retrieves the latest GP record for a specific satellite. Filter by `NORAD_CAT_ID`, order by `EPOCH` descending, and limit to 1 to get the most recent element set.


```python
import brahe as bh

# Get the latest GP record for the ISS (NORAD 25544)
# Order by EPOCH descending so the most recent is first, limit to 1
query = (
    bh.SpaceTrackQuery(bh.RequestClass.GP)
    .filter("NORAD_CAT_ID", "25544")
    .order_by("EPOCH", bh.SortOrder.DESC)
    .limit(1)
)

url_path = query.build()
print(f"Latest GP for ISS:\n  {url_path}")

# Get the latest GP for a Starlink satellite (NORAD 48274)
query = (
    bh.SpaceTrackQuery(bh.RequestClass.GP)
    .filter("NORAD_CAT_ID", "48274")
    .order_by("EPOCH", bh.SortOrder.DESC)
    .limit(1)
)

url_path = query.build()
print(f"\nLatest GP for Starlink-2541:\n  {url_path}")
```


## Latest Ephemeris for Non-Decayed Objects

To query the full active catalog, filter where `DECAY_DATE` equals `null_val()`. This excludes objects that have already reentered. Combine with additional filters like `OBJECT_TYPE` or `PERIOD` to narrow the results.


```python
import brahe as bh
from brahe.spacetrack import operators as op

# Get latest GP for all non-decayed objects
# DECAY_DATE = null-val means the object has not decayed
query = (
    bh.SpaceTrackQuery(bh.RequestClass.GP)
    .filter("DECAY_DATE", op.null_val())
    .order_by("NORAD_CAT_ID", bh.SortOrder.ASC)
)

url_path = query.build()
print(f"All non-decayed objects:\n  {url_path}")

# Filter to only active payloads (exclude debris and rocket bodies)
query = (
    bh.SpaceTrackQuery(bh.RequestClass.GP)
    .filter("DECAY_DATE", op.null_val())
    .filter("OBJECT_TYPE", "PAYLOAD")
    .order_by("NORAD_CAT_ID", bh.SortOrder.ASC)
)

url_path = query.build()
print(f"\nActive payloads only:\n  {url_path}")

# Filter to active objects in LEO (period under 128 minutes)
query = (
    bh.SpaceTrackQuery(bh.RequestClass.GP)
    .filter("DECAY_DATE", op.null_val())
    .filter("PERIOD", op.less_than("128"))
    .order_by("NORAD_CAT_ID", bh.SortOrder.ASC)
)

url_path = query.build()
print(f"\nActive LEO objects:\n  {url_path}")
```


**Catalog Size**
The full non-decayed catalog contains tens of thousands of records. Consider adding `OBJECT_TYPE`, orbit regime filters, or `limit()` to keep response sizes manageable.

## Objects Decaying Soon

The `Decay` request class provides reentry predictions and historical decay records. Use `inclusive_range` with `now()` and `now_offset()` to query a time window.


```python
import brahe as bh
from brahe.spacetrack import operators as op

# Get objects predicted to decay within the next 30 days
# The Decay request class provides reentry predictions
query = (
    bh.SpaceTrackQuery(bh.RequestClass.DECAY)
    .filter("DECAY_EPOCH", op.inclusive_range(op.now(), op.now_offset(30)))
    .order_by("DECAY_EPOCH", bh.SortOrder.ASC)
)

url_path = query.build()
print(f"Decaying within 30 days:\n  {url_path}")

# Get recent actual decays from the past 7 days
query = (
    bh.SpaceTrackQuery(bh.RequestClass.DECAY)
    .filter("DECAY_EPOCH", op.inclusive_range(op.now_offset(-7), op.now()))
    .filter("MSG_TYPE", "Decay")
    .order_by("DECAY_EPOCH", bh.SortOrder.DESC)
)

url_path = query.build()
print(f"\nRecent decays (last 7 days):\n  {url_path}")
```


---

## See Also

- [Query Builder](query_builder.md) -- Filters, ordering, limits, and output formats
- [Conjunction Data Messages](cdm.md) -- Querying CDM collision risk data
- [Client](client.md) -- Authentication and query execution
- [Operators Reference](../../../library_api/ephemeris/spacetrack/operators.md) -- All operator functions