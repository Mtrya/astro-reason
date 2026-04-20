# Query Builder

`SpaceTrackQuery` provides a fluent builder API for constructing Space-Track.org API queries. Each builder method returns a new query instance, allowing method chaining. Call `build()` to produce the URL path string that the client appends to the base URL.

For the complete API reference, see the [SpaceTrackQuery Reference](../../../library_api/ephemeris/spacetrack/query.md).

## Basic Queries

Create a query by specifying the request class. The default controller is selected automatically based on the class -- `GP` and `SATCAT` use `BasicSpaceData`, while `CDMPublic` uses `ExpandedSpaceData`. Add filters with the `filter()` method using Space-Track field names.


```python
import brahe as bh

# Build a GP query for the ISS by NORAD catalog ID
query = bh.SpaceTrackQuery(bh.RequestClass.GP).filter("NORAD_CAT_ID", "25544")

url_path = query.build()
print(f"GP query URL path:\n  {url_path}")

# Build a SATCAT query for US-owned objects
query = bh.SpaceTrackQuery(bh.RequestClass.SATCAT).filter("COUNTRY", "US")

url_path = query.build()
print(f"\nSATCAT query URL path:\n  {url_path}")

# The default controller is inferred from the request class
query = bh.SpaceTrackQuery(bh.RequestClass.CDM_PUBLIC)
url_path = query.build()
print(f"\nCDM query URL path (uses expandedspacedata controller):\n  {url_path}")
```


## Filters and Operators

The `operators` module provides functions that generate operator-prefixed strings for filter values. These compose naturally -- `greater_than(now_offset(-7))` nests the time offset inside the comparison operator.


```python
import brahe as bh
from brahe.spacetrack import operators as op

# Filter by NORAD ID range using inclusive_range
query = bh.SpaceTrackQuery(bh.RequestClass.GP).filter(
    "NORAD_CAT_ID", op.inclusive_range("25544", "25600")
)
print(f"Range filter:\n  {query.build()}")

# Filter for objects with low eccentricity using less_than
query = (
    bh.SpaceTrackQuery(bh.RequestClass.GP)
    .filter("ECCENTRICITY", op.less_than("0.01"))
    .filter("OBJECT_TYPE", "PAYLOAD")
)
print(f"\nMultiple filters:\n  {query.build()}")

# Filter for recently launched objects using greater_than + now_offset
query = bh.SpaceTrackQuery(bh.RequestClass.SATCAT).filter(
    "LAUNCH", op.greater_than(op.now_offset(-30))
)
print(f"\nRecent launches (last 30 days):\n  {query.build()}")

# Search by name pattern using like
query = bh.SpaceTrackQuery(bh.RequestClass.SATCAT).filter(
    "SATNAME", op.like("STARLINK")
)
print(f"\nName pattern match:\n  {query.build()}")

# Filter for multiple NORAD IDs using or_list
query = bh.SpaceTrackQuery(bh.RequestClass.GP).filter(
    "NORAD_CAT_ID", op.or_list(["25544", "48274", "54216"])
)
print(f"\nMultiple IDs:\n  {query.build()}")
```


**Operator Composition**
Operators are string-generating functions. You can compose them by nesting:

- `greater_than(now_offset(-7))` produces `">now-7"` (epoch after 7 days ago)
- `inclusive_range(now_offset(-30), now())` produces `"now-30--now"` (within last 30 days)

## Ordering, Limits, and Options

Control result ordering, pagination, and field selection. Multiple `order_by` calls are cumulative -- results are sorted by the first field, then by subsequent fields for ties.


```python
import brahe as bh

# Order results by epoch descending and limit to 5 records
query = (
    bh.SpaceTrackQuery(bh.RequestClass.GP)
    .filter("NORAD_CAT_ID", "25544")
    .order_by("EPOCH", bh.SortOrder.DESC)
    .limit(5)
)
print(f"Ordered and limited:\n  {query.build()}")

# Use limit with offset for pagination
query = (
    bh.SpaceTrackQuery(bh.RequestClass.GP)
    .filter("OBJECT_TYPE", "PAYLOAD")
    .order_by("NORAD_CAT_ID", bh.SortOrder.ASC)
    .limit_offset(10, 20)
)
print(f"\nPaginated results:\n  {query.build()}")

# Select specific fields with predicates_filter
query = (
    bh.SpaceTrackQuery(bh.RequestClass.GP)
    .filter("NORAD_CAT_ID", "25544")
    .predicates_filter(["OBJECT_NAME", "EPOCH", "INCLINATION", "PERIOD"])
)
print(f"\nFiltered fields:\n  {query.build()}")

# Enable metadata and distinct results
query = (
    bh.SpaceTrackQuery(bh.RequestClass.SATCAT)
    .filter("COUNTRY", "US")
    .distinct(True)
    .metadata(True)
)
print(f"\nDistinct with metadata:\n  {query.build()}")
```


## Output Formats

The default output format is JSON, which works with `query_json()`, `query_gp()`, and `query_satcat()`. Other formats like TLE, CSV, and KVN are useful with `query_raw()` for direct text output.


```python
import brahe as bh

# Default format is JSON
query = bh.SpaceTrackQuery(bh.RequestClass.GP).filter("NORAD_CAT_ID", "25544")
print(f"Default (JSON):\n  {query.build()}")

# Request TLE format for direct TLE text output
query = (
    bh.SpaceTrackQuery(bh.RequestClass.GP)
    .filter("NORAD_CAT_ID", "25544")
    .format(bh.OutputFormat.TLE)
)
print(f"\nTLE format:\n  {query.build()}")

# Request CSV format for spreadsheet-compatible output
query = (
    bh.SpaceTrackQuery(bh.RequestClass.SATCAT)
    .filter("COUNTRY", "US")
    .limit(10)
    .format(bh.OutputFormat.CSV)
)
print(f"\nCSV format:\n  {query.build()}")

# Request KVN (CCSDS Keyword-Value Notation) format
query = (
    bh.SpaceTrackQuery(bh.RequestClass.GP)
    .filter("NORAD_CAT_ID", "25544")
    .format(bh.OutputFormat.KVN)
)
print(f"\nKVN format:\n  {query.build()}")
```


**Format and Query Method Compatibility**
The typed query methods (`query_gp()`, `query_satcat()`, `query_json()`) require JSON format. If you set a non-JSON format, use `query_raw()` to get the raw response string.

---

## See Also

- [Space-Track API Overview](index.md) -- Module architecture and type catalog
- [Client Usage](client.md) -- Authentication and query execution
- [SpaceTrackQuery Reference](../../../library_api/ephemeris/spacetrack/query.md) -- Complete method documentation
- [Operators Reference](../../../library_api/ephemeris/spacetrack/operators.md) -- All operator functions
- [Enumerations Reference](../../../library_api/ephemeris/spacetrack/enums.md) -- RequestClass, OutputFormat, etc.