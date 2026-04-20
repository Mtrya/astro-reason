# CDM — Conjunction Data Message

A Conjunction Data Message (CDM) describes a close approach between two space objects, providing state vectors, covariance matrices, and collision probability data at the Time of Closest Approach (TCA). It is the standard format used by conjunction assessment services (e.g., 18th Space Defense Squadron) to communicate collision risk to satellite operators.

## Parsing a CDM

Parse from KVN, XML, or JSON files and access conjunction data:

```python
from brahe.ccsds import CDM

cdm = CDM.from_file("conjunction.cdm")

# Conjunction-level data
print(f"TCA: {cdm.tca}")
print(f"Miss distance: {cdm.miss_distance} m")
print(f"Collision probability: {cdm.collision_probability}")

# Object states (in meters and m/s)
print(f"Object 1: {cdm.object1_name}")
print(f"Object 1 state: {cdm.object1_state}")
print(f"Object 2: {cdm.object2_name}")
print(f"Object 2 state: {cdm.object2_state}")

# Covariance matrix (6x6, in m², m²/s, m²/s²)
cov = cdm.object1_covariance
print(f"Position variance (R,R): {cov[0][0]} m²")
```

## Creating a CDM

Build a CDM programmatically by constructing state vectors, covariance matrices, and object metadata, then combining them into a message:

```python
import numpy as np
import brahe as bh
from brahe.ccsds import CDM, CDMObject, CDMRTNCovariance, CDMStateVector

# Define state vectors at TCA for both objects (meters, m/s)
sv1 = CDMStateVector(
    position=[bh.R_EARTH + 500e3, 0.0, 0.0],
    velocity=[0.0, 7612.0, 0.0],
)
sv2 = CDMStateVector(
    position=[bh.R_EARTH + 500.5e3, 10.0, -5.0],
    velocity=[0.0, -7612.0, 0.0],
)

# Define 6x6 RTN covariance matrices (m², m²/s, m²/s²)
cov1 = CDMRTNCovariance(matrix=(np.eye(6) * 1e4).tolist())
cov2 = CDMRTNCovariance(matrix=(np.eye(6) * 2e4).tolist())

# Build object metadata + data
obj1 = CDMObject(
    designator="12345",
    catalog_name="SATCAT",
    name="SATELLITE A",
    international_designator="2020-001A",
    ephemeris_name="NONE",
    covariance_method="CALCULATED",
    maneuverable="YES",
    ref_frame="EME2000",
    state_vector=sv1,
    rtn_covariance=cov1,
)
obj2 = CDMObject(
    designator="67890",
    catalog_name="SATCAT",
    name="DEBRIS FRAGMENT",
    international_designator="2019-050ZZ",
    ephemeris_name="NONE",
    covariance_method="CALCULATED",
    maneuverable="NO",
    ref_frame="EME2000",
    state_vector=sv2,
    rtn_covariance=cov2,
)

# Create CDM message
tca = bh.Epoch.from_datetime(2024, 6, 15, 14, 30, 0.0, 0.0, bh.TimeSystem.UTC)
cdm = CDM(
    originator="BRAHE_EXAMPLE",
    message_id="CDM-2024-001",
    tca=tca,
    miss_distance=502.3,
    object1=obj1,
    object2=obj2,
)

# Set optional collision probability
cdm.collision_probability = 1.5e-04
cdm.collision_probability_method = "FOSTER-1992"

print(f"CDM: {cdm.object1_name} vs {cdm.object2_name}")
print(f"Miss distance: {cdm.miss_distance} m")
print(f"Collision probability: {cdm.collision_probability}")

# Write to KVN
kvn = cdm.to_string("KVN")
print(f"\nKVN output ({len(kvn)} chars)")

# Verify round-trip
cdm2 = CDM.from_str(kvn)
print(f"Round-trip: {cdm2.object1_name} vs {cdm2.object2_name}")
```


## What a CDM Contains

Every CDM has a **header** (version, creation date, originator, message ID), **relative metadata** (TCA, miss distance, optional collision probability and screening volume), and exactly **two object sections**.

Each object section contains **metadata** (object identity, reference frame, covariance method, force model info), **OD parameters** (observation spans, residuals), **additional parameters** (mass, drag/SRP areas, hard-body radius), a **state vector** at TCA, and a **covariance matrix** in the RTN frame.

The covariance matrix is always specified in the Radial-Transverse-Normal (RTN) frame centered on the object. The standard 6$\times$6 matrix covers position and velocity uncertainty. CDM also supports extended 7$\times$7 through 9$\times$9 matrices that include drag coefficient, solar radiation pressure, and thrust uncertainty correlations.

## Format Support

CDM supports three encoding formats:

- **KVN** (`.cdm`, `.txt`) — keyword=value text, the most common format from conjunction screening services
- **XML** (`.xml`) — structured XML following the CCSDS NDM XML schema
- **JSON** — programmatic convenience format (not in the CCSDS standard)

All three formats are auto-detected on parse. Specify the format explicitly when writing:

```
cdm = CDM.from_file("conjunction.cdm")  # Auto-detect
kvn = cdm.to_string("KVN")
xml = cdm.to_string("XML")
json_str = cdm.to_string("JSON")
```

## See Also

- [CDM API Reference](../../library_api/ccsds/cdm.md) — Full API documentation
- [OPM Format Guide](opm.md) — Single-state messages (closest analog)
- [CCSDS Module](index.md) — Module overview