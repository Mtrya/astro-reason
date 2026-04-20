# Groundstation Datasets

## Overview

Groundstation datasets provide geographic locations and metadata for commercial satellite ground facilities worldwide. This data is essential for:

- **Computing contact opportunities**: Determine when satellites are visible from ground stations
- **Network planning**: Analyze coverage and redundancy across multiple providers
- **Mission design**: Evaluate downlink opportunities for different orbit configurations

Brahe includes embedded GeoJSON data for 6 major commercial groundstation providers, totaling 50+ facilities globally. All data is:

- **Offline-capable**: No network requests required
- **Comprehensive**: Global coverage across multiple providers
- **Standardized**: Consistent format with geographic coordinates and metadata
- **Up-to-date**: Maintained as provider networks evolve

### When to Use

Use groundstation datasets when you need to:

- Compute visibility windows for satellite-to-ground contacts
- Plan downlink schedules for data collection
- Analyze network coverage and redundancy
- Compare provider capabilities across different locations

## Available Providers

Brahe includes groundstation data from six major commercial providers:

| Provider | Description |
|----------|-------------|
| **Atlas** | Atlas Space Operations |
| **AWS** | Amazon Web Services Ground Station |
| **KSAT** | Kongsberg Satellite Services |
| **Leaf** | Leaf Space |
| **NASA DSN** | NASA Deep Space Network |
| **NASA NEN** | NASA Near Earth Network |
| **SSC** | Swedish Space Corporation |
| **Viasat** | Viasat |

## Usage

### Loading Groundstations

Load groundstation data from one or more providers:


```python
import brahe as bh

# Initialize EOP data
bh.initialize_eop()

# Load groundstations from a single provider
ksat_stations = bh.datasets.groundstations.load("ksat")
print(f"KSAT stations: {len(ksat_stations)}")

# Load all available providers at once
all_stations = bh.datasets.groundstations.load_all()
print(f"Total stations (all providers): {len(all_stations)}")

# List available providers
providers = bh.datasets.groundstations.list_providers()
print(f"\nAvailable providers: {', '.join(providers)}")

# Load multiple specific providers
aws_stations = bh.datasets.groundstations.load("aws")
ssc_stations = bh.datasets.groundstations.load("ssc")
combined = aws_stations + ssc_stations
print(f"\nCombined AWS + SSC: {len(combined)} stations")
```


### Accessing Properties

Each groundstation includes geographic coordinates and metadata:


```python
import brahe as bh

# Initialize EOP data
bh.initialize_eop()

# Load KSAT groundstations
stations = bh.datasets.groundstations.load("ksat")

# Access the first station
station = stations[0]

# Geographic coordinates (degrees and meters)
name = station.get_name() if station.get_name() else "Unknown"
print(f"Station: {name}")
print(f"Latitude: {station.lat:.4f}°")
print(f"Longitude: {station.lon:.4f}°")
print(f"Altitude: {station.alt:.1f} m")

# Access metadata properties
props = station.properties
print(f"\nProvider: {props['provider']}")
print(f"Frequency bands: {', '.join(props['frequency_bands'])}")

# Show all stations with their locations
print(f"\n{len(stations)} KSAT Stations:")
for i, gs in enumerate(stations, 1):
    gs_name = gs.get_name() if gs.get_name() else "Unknown"
    print(f"{i:2d}. {gs_name:30s} ({gs.lat:7.3f}°, {gs.lon:8.3f}°)")
```


### Computing Access Windows

Use groundstation data with brahe's access computation to find contact opportunities:


```python
import brahe as bh
import numpy as np

# Initialize EOP data
bh.initialize_eop()

# Load groundstations from a provider
stations = bh.datasets.groundstations.load("ksat")
print(f"Computing access for {len(stations)} KSAT stations")

# Create a sun-synchronous orbit satellite
epoch = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
oe = np.array([bh.R_EARTH + 600e3, 0.001, 97.8, 0.0, 0.0, 0.0])
state = bh.state_koe_to_eci(oe, bh.AngleFormat.DEGREES)
propagator = bh.KeplerianPropagator.from_eci(epoch, state, 60.0).with_name("EO-Sat")

# Define access constraint (minimum 5° elevation)
constraint = bh.ElevationConstraint(min_elevation_deg=5.0)

# Compute access windows for 24 hours
duration = 24.0 * 3600.0  # seconds
windows = bh.location_accesses(
    stations, [propagator], epoch, epoch + duration, constraint
)

# Display results
print(f"\nTotal access windows: {len(windows)}")
print("\nFirst 5 windows:")
for i, window in enumerate(windows[:5], 1):
    duration_min = (window.end - window.start) / 60.0
    print(f"{i}. {window.location_name:20s} -> {window.satellite_name:10s}")
    print(f"   Start: {window.start}")
    print(f"   Duration: {duration_min:.1f} minutes")
```


## Data Format

Each groundstation is represented as a `PointLocation` with standardized properties:

```
import brahe as bh

stations = bh.datasets.groundstations.load("ksat")
station = stations[0]

# Geographic coordinates (WGS84)
lon = station.lon()      # Longitude in degrees
lat = station.lat()      # Latitude in degrees
alt = station.alt()      # Altitude in meters

# Metadata properties
props = station.properties
name = station.get_name()              # Station name
provider = props["provider"]            # Provider name (e.g., "KSAT")
bands = props["frequency_bands"]        # Supported bands (e.g., ["S", "X"])
```

All groundstations include these standard properties:

- **`provider`**: Provider name (string, e.g., "KSAT", "Atlas")
- **`frequency_bands`**: List of supported frequency bands (e.g., `["S", "X", "Ka"]`)

Additional properties may be included in future releases as data becomes available.

---

## See Also

- [Datasets Overview](index.md) - Understanding datasets in Brahe
- [Groundstation API Reference](../../library_api/datasets/groundstations.md) - Complete function documentation