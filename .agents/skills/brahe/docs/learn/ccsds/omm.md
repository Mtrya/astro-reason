# OMM — Orbit Mean-elements Message

An Orbit Mean-elements Message (OMM) is the CCSDS-standardized representation of TLE/GP data — the same orbital elements traditionally distributed as Two-Line Element sets, in a structured, self-describing format. Data sources like CelesTrak and Space-Track distribute GP data as OMM. The typical workflow is to parse an OMM and initialize an SGP4 propagator.

## Parse and Propagate with SGP4

Extract OMM mean elements and TLE parameters to create an `SGPPropagator`:

```python
import brahe as bh
from brahe.ccsds import OMM

bh.initialize_eop()

# Parse OMM
omm = OMM.from_file("test_assets/ccsds/omm/OMMExample1.txt")
print(f"Object: {omm.object_name} ({omm.object_id})")
print(f"Theory: {omm.mean_element_theory}")
print(f"Epoch:  {omm.epoch}")

# Extract mean elements for SGP4
# The epoch string is needed in ISO format for from_omm_elements
d = omm.to_dict()
epoch_str = d["mean_elements"]["epoch"]

# Initialize SGP propagator from OMM elements
prop = bh.SGPPropagator.from_omm_elements(
    epoch=epoch_str,
    mean_motion=omm.mean_motion,
    eccentricity=omm.eccentricity,
    inclination=omm.inclination,
    raan=omm.ra_of_asc_node,
    arg_of_pericenter=omm.arg_of_pericenter,
    mean_anomaly=omm.mean_anomaly,
    norad_id=omm.norad_cat_id,
    object_name=omm.object_name,
    object_id=omm.object_id,
    classification=omm.classification_type,
    bstar=omm.bstar,
    mean_motion_dot=omm.mean_motion_dot,
    mean_motion_ddot=omm.mean_motion_ddot,
    ephemeris_type=omm.ephemeris_type,
    element_set_no=omm.element_set_no,
    rev_at_epoch=omm.rev_at_epoch,
)

print("\nSGP Propagator created:")
print(f"  NORAD ID: {prop.norad_id}")
print(f"  Name:     {prop.satellite_name}")
print(f"  Epoch:    {prop.epoch}")

# Propagate 1 day forward
target = prop.epoch + 86400.0
state = prop.state(target)
print(f"\nState after 1 day ({target}):")
print(
    f"  Position: [{state[0] / 1e3:.3f}, {state[1] / 1e3:.3f}, {state[2] / 1e3:.3f}] km"
)
print(f"  Velocity: [{state[3]:.3f}, {state[4]:.3f}, {state[5]:.3f}] m/s")

# Propagate to several epochs
print("\nState every 6 hours:")
for hours in range(0, 25, 6):
    t = prop.epoch + hours * 3600.0
    s = prop.state(t)
    r = (s[0] ** 2 + s[1] ** 2 + s[2] ** 2) ** 0.5
    print(f"  +{hours:2d}h: r={r / 1e3:.1f} km")
```


## Accessing Mean Elements and TLE Parameters

Parse from file or string, then access metadata, mean elements, and TLE parameters. The message carries two main data sections: **mean elements** (epoch, mean motion, eccentricity, inclination, RAAN, argument of pericenter, mean anomaly) and **TLE parameters** (NORAD catalog ID, classification, element set number, revolution count, $B^*$ drag term, mean motion derivatives):

```python
import brahe as bh
from brahe.ccsds import OMM

bh.initialize_eop()

# Parse OMM file
omm = OMM.from_file("test_assets/ccsds/omm/OMMExample1.txt")

# Header
print(f"Format version: {omm.format_version}")
print(f"Originator:     {omm.originator}")
print(f"Creation date:  {omm.creation_date}")

# Metadata
print(f"\nObject name:          {omm.object_name}")
print(f"Object ID:            {omm.object_id}")
print(f"Center name:          {omm.center_name}")
print(f"Ref frame:            {omm.ref_frame}")
print(f"Time system:          {omm.time_system}")
print(f"Mean element theory:  {omm.mean_element_theory}")

# Mean orbital elements (CCSDS/TLE-native units)
print(f"\nEpoch:               {omm.epoch}")
print(f"Mean motion:         {omm.mean_motion} rev/day")
print(f"Eccentricity:        {omm.eccentricity}")
print(f"Inclination:         {omm.inclination} deg")
print(f"RAAN:                {omm.ra_of_asc_node} deg")
print(f"Arg of pericenter:   {omm.arg_of_pericenter} deg")
print(f"Mean anomaly:        {omm.mean_anomaly} deg")
print(f"GM:                  {omm.gm:.4e} m³/s²")

# TLE parameters
print(f"\nNORAD catalog ID:    {omm.norad_cat_id}")
print(f"Classification:      {omm.classification_type}")
print(f"Ephemeris type:      {omm.ephemeris_type}")
print(f"Element set no:      {omm.element_set_no}")
print(f"Rev at epoch:        {omm.rev_at_epoch}")
print(f"BSTAR:               {omm.bstar}")
print(f"Mean motion dot:     {omm.mean_motion_dot} rev/day²")
print(f"Mean motion ddot:    {omm.mean_motion_ddot} rev/day³")

# Serialization
d = omm.to_dict()
print(f"\nDict keys: {list(d.keys())}")
```


**Unit Convention for OMM**
Mean motion, angles, and TLE drag terms are kept in their CCSDS/TLE-native units (rev/day, degrees, etc.) because these values are needed as-is for TLE generation and SGP4 initialization. Only GM is converted to SI (m$^3$/s$^2$).

## OMM and GPRecord

Brahe's `GPRecord` type — returned by both `CelestrakClient` and `SpaceTrackClient` when querying GP data — has a bidirectional relationship with OMM. A `GPRecord` can be converted to an OMM via `to_omm()` for CCSDS-compliant export, and an OMM can be converted to a `GPRecord` via `to_gp_record()` for use with brahe's ephemeris infrastructure.

This means you can move freely between the two representations: query CelesTrak for a satellite, get a `GPRecord`, and export it as a standards-compliant OMM file for distribution. Or parse an OMM file received from an external system and convert it to a `GPRecord` to use the same downstream code you would with a CelesTrak or Space-Track query. Both conversions preserve all shared fields, so switching between formats introduces no data loss.

## KVN Format Example

A minimal OMM KVN file:

```
CCSDS_OMM_VERS = 3.0
CREATION_DATE = 2024-01-15T00:00:00
ORIGINATOR = EXAMPLE

OBJECT_NAME = ISS (ZARYA)
OBJECT_ID = 1998-067A
CENTER_NAME = EARTH
REF_FRAME = TEME
TIME_SYSTEM = UTC
MEAN_ELEMENT_THEORY = SGP/SGP4

EPOCH = 2024-01-15T12:00:00
MEAN_MOTION = 15.50100000
ECCENTRICITY = 0.0006180
INCLINATION = 51.6413
RA_OF_ASC_NODE = 289.5820
ARG_OF_PERICENTER = 36.5102
MEAN_ANOMALY = 323.6298

EPHEMERIS_TYPE = 0
CLASSIFICATION_TYPE = U
NORAD_CAT_ID = 25544
ELEMENT_SET_NO = 999
REV_AT_EPOCH = 43210
BSTAR = 0.000035000
MEAN_MOTION_DOT = 0.00001200
MEAN_MOTION_DDOT = 0.0
```

Note that OMM KVN does not use `META_START`/`META_STOP` markers — all keywords appear in a flat sequence.

---

## See Also

- [API Reference — OMM](../../library_api/ccsds/omm.md)
- [CCSDS Data Formats](index.md) — Overview of all message types
- [Two-Line Elements](../orbits/two_line_elements.md) — Traditional TLE format
- [Ephemeris Data Sources](../ephemeris/index.md) — CelesTrak and Space-Track clients
- [SGP Propagation](../orbit_propagation/sgp_propagation.md) — SGP4/SDP4 propagation theory and usage