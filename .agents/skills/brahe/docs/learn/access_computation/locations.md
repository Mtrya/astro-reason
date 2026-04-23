# Locations

Locations represent ground positions or areas that satellites can access. Brahe provides two fundamental location types—points and polygons—with full GeoJSON interoperability and extensible metadata support.

All location types implement the `AccessibleLocation` trait, which provides a common interface for coordinate access, property management, and GeoJSON import/export. This design allows you to work with different location geometries through a unified API.

**Coordinate Units**
All coordinates are specified in geodetic longitude (λ), latitude (φ), and altitude (h) using the WGS84 reference frame. All units are in degrees (for λ and φ) and meters (for h) for consistency with the GeoJSON standard.

## PointLocation

A `PointLocation` represents a single geodetic point on Earth's surface. This is the most common location type, used for ground stations, cities, or specific observation points.

### Initialization from Coordinates

Create a point location from geodetic coordinates (longitude, latitude, altitude):


```python
import brahe as bh

bh.initialize_eop()

# Create location (longitude, latitude, altitude in meters)
# San Francisco, CA
sf = bh.PointLocation(-122.4194, 37.7749, 0.0)

# Add an identifier for clarity
sf = sf.with_name("San Francisco")

print(f"Location: {sf.get_name()}")
print(f"Longitude: {sf.longitude(bh.AngleFormat.DEGREES):.4f} deg")
print(f"Latitude: {sf.latitude(bh.AngleFormat.DEGREES):.4f} deg")
```


**Coordinate Units**
Python uses degrees for input convenience. Rust uses radians (SI standard). Both use meters for altitude.

### Initialization from GeoJSON

Load locations from GeoJSON strings or files:


```python
import brahe as bh
import json

bh.initialize_eop()

# GeoJSON Point feature
geojson_str = """
{
    "type": "Feature",
    "properties": {"name": "Svalbard Station"},
    "geometry": {
        "type": "Point",
        "coordinates": [15.4038, 78.2232, 458.0]
    }
}
"""

location = bh.PointLocation.from_geojson(json.loads(geojson_str))
print(f"Loaded: {location.get_name()}")
print(f"Longitude: {location.longitude(bh.AngleFormat.DEGREES):.4f} deg")
print(f"Latitude: {location.latitude(bh.AngleFormat.DEGREES):.4f} deg")
print(f"Altitude: {location.altitude():.1f} m")
```


### Accessing Coordinates

Retrieve coordinates in different formats:


```python
import brahe as bh

bh.initialize_eop()

location = bh.PointLocation(-122.4194, 37.7749, 0.0)

# Access in degrees
print(f"Longitude: {location.longitude(bh.AngleFormat.DEGREES)} deg")
print(f"Latitude: {location.latitude(bh.AngleFormat.DEGREES)} deg")
print(f"Altitude: {location.altitude()} m")

# Shorthand access (in degrees)
print(f"Lon (deg): {location.lon:.6f}")
print(f"Lat (deg): {location.lat:.6f}")

# Get geodetic array [lat, lon, alt] in radians and meters
geodetic = location.center_geodetic()
print(f"Geodetic: [{geodetic[0]:.6f}, {geodetic[1]:.6f}, {geodetic[2]:.1f}]")

# Get ECEF Cartesian position [x, y, z] in meters
ecef = location.center_ecef()
print(f"ECEF: [{ecef[0]:.1f}, {ecef[1]:.1f}, {ecef[2]:.1f}] m")
```


## PolygonLocation

A `PolygonLocation` represents a closed polygon area on Earth's surface. This is useful for imaging regions, coverage zones, or geographic areas of interest.

### Initialization from Vertices

Create a polygon from a list of vertices:


```python
import brahe as bh

bh.initialize_eop()

# Define polygon vertices (longitude, latitude, altitude)
# Simple rectangular region
vertices = [
    [-122.5, 37.7, 0.0],
    [-122.35, 37.7, 0.0],
    [-122.35, 37.8, 0.0],
    [-122.5, 37.8, 0.0],
    [-122.5, 37.7, 0.0],  # Close the polygon
]

polygon = bh.PolygonLocation(vertices).with_name("SF Region")

print(f"Name: {polygon.get_name()}")
print(f"Vertices: {polygon.num_vertices}")
print(
    f"Center: ({polygon.longitude(bh.AngleFormat.DEGREES):.4f}, {polygon.latitude(bh.AngleFormat.DEGREES):.4f})"
)
```


### Initialization from GeoJSON

Load polygon areas from GeoJSON:


```python
import brahe as bh
import json

bh.initialize_eop()

# GeoJSON Polygon feature
geojson_str = """
{
    "type": "Feature",
    "properties": {"name": "Target Area"},
    "geometry": {
        "type": "Polygon",
        "coordinates": [[
            [-122.5, 37.7, 0],
            [-122.35, 37.7, 0],
            [-122.35, 37.8, 0],
            [-122.5, 37.8, 0],
            [-122.5, 37.7, 0]
        ]]
    }
}
"""

polygon = bh.PolygonLocation.from_geojson(json.loads(geojson_str))

print(f"Name: {polygon.get_name()}")
print(f"Vertices: {polygon.num_vertices}")
print(
    f"Center: ({polygon.longitude(bh.AngleFormat.DEGREES):.4f}, {polygon.latitude(bh.AngleFormat.DEGREES):.4f})"
)
```


## Working with Properties

Both location types support custom properties for storing metadata:


```python
import brahe as bh

bh.initialize_eop()

location = bh.PointLocation(-122.4194, 37.7749, 0.0)

# Add scalar properties
location.add_property("antenna_gain_db", 42.5)
location.add_property("frequency_mhz", 8450.0)

# Add string properties
location.add_property("operator", "NOAA")

# Add boolean flags
location.add_property("uplink_enabled", True)

# Retrieve properties
props = location.properties
gain = props.get("antenna_gain_db")
operator = props.get("operator")
uplink = props.get("uplink_enabled")

print(f"Antenna Gain: {gain}")
print(f"Operator: {operator}")
print(f"Uplink Enabled: {uplink}")
```


## Exporting to GeoJSON

Convert locations back to GeoJSON format:


```python
import brahe as bh

bh.initialize_eop()

location = (
    bh.PointLocation(-122.4194, 37.7749, 0.0).with_name("San Francisco").with_id(1)
)

# Export to GeoJSON dict
geojson = location.to_geojson()
print("Exported GeoJSON:")
print(geojson)

# The output includes all properties and identifiers
# Can be loaded back with from_geojson()
reloaded = bh.PointLocation.from_geojson(geojson)
print(f"\nReloaded: {reloaded.get_name()} (ID: {reloaded.get_id()})")
```


---

## See Also

- [Constraints](constraints.md) - Defining access criteria for locations
- [Computation](computation.md) - Access algorithms and property computation
- [Tessellation](tessellation.md) - Dividing locations into satellite imaging tiles
- [API Reference: Locations](../../library_api/access/locations.md)
- [Example: Predicting Ground Contacts](../../examples/ground_contacts.md)