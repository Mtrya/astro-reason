# ICGEM Gravity Models

The [International Centre for Global Earth Models (ICGEM)](https://icgem.gfz.de), hosted at GFZ Potsdam, maintains the de facto catalog of published spherical harmonic gravity models for Earth and other solar system bodies. Brahe's `brahe.datasets.icgem` interface mirrors that catalog in code: list the available models for a body, download a specific `.gfc` file into a local cache, and refresh stale indexes on demand.

**Why a download interface?**
Brahe ships three packaged Earth models (EGM2008 truncated to 120, GGM05S, JGM3). The ICGEM catalog publishes hundreds more — newer high-degree Earth fields, lunar models like GRGM1200B, planetary models for Mars/Venus/Ceres, and asteroid fields. The dataset interface gives access to any of them without bundling tens of megabytes of model data into the library.

## Supported Bodies

The `body` argument accepts case-insensitive names. The five known bodies have dedicated routing:

| Body     | Source page                | Example model |
|----------|----------------------------|---------------|
| `earth`  | `tom_longtime` (Earth list) | `EGM2008`, `JGM3`, `GGM05S` |
| `moon`   | `tom_celestial`             | `GRGM1200B`   |
| `mars`   | `tom_celestial`             | `MRO120F`     |
| `venus`  | `tom_celestial`             | `MGNP180U`    |
| `ceres`  | `tom_celestial`             | `sphericalRFM_CERES_2519`     |

Any other name (e.g. `"pluto"`, `"bennu"`) is treated as a custom celestial body and matched case-insensitively against ICGEM's celestial catalog. This keeps the catalog open-ended: ICGEM can add new bodies and they remain reachable without a Brahe release.

## Caching Behavior

ICGEM downloads are cached under the Brahe cache directory:

| Path                                                | Contents                                   |
|-----------------------------------------------------|--------------------------------------------|
| `$BRAHE_CACHE/icgem/index_earth.json`               | Parsed listing of Earth models             |
| `$BRAHE_CACHE/icgem/index_celestial.json`           | Parsed listing of all non-Earth bodies     |
| `$BRAHE_CACHE/icgem/models/<body>/<name>-<degree>-<hashprefix>.gfc` | Downloaded `.gfc` files |

- **Index TTL**: 30 days. After expiry, `list_models()` and `download_model()` transparently refresh the listing on the next call.
- **Stale-cache fallback**: if a refresh attempt fails (no network, ICGEM down), the previous cached index is reused and a warning is printed. This keeps offline use working from a populated cache.
- **Hash-suffixed filenames**: each cached `.gfc` carries a short prefix of the ICGEM URL hash, so a republished model with the same `(name, degree)` but a fresh upstream URL is fetched cleanly instead of being shadowed by the old cache entry.
- **Model files**: downloads are permanent — `.gfc` coefficient sets do not change after publication.

## Listing Available Models

`datasets.icgem.list_models(body)` returns a list of `ICGEMIndexEntry` records. Each entry has `body`, `name`, `degree`, `year`, and the opaque `download_path` ICGEM uses internally.


```python
import brahe.datasets as datasets

# List all Earth gravity models in the catalog
earth_models = datasets.icgem.list_models("earth")
print(f"Earth models available: {len(earth_models)}")
for entry in earth_models[:3]:
    print(f"  {entry.name:30s} degree={entry.degree:<6d} year={entry.year}")

# Each entry is a plain ICGEMIndexEntry, so standard Python filtering works
egm_family = [e for e in earth_models if e.name.startswith("EGM")]
print(f"\nEGM-family Earth models: {len(egm_family)}")

# The same call works for other bodies — Moon, Mars, Venus, Ceres, or any
# custom celestial body present in the ICGEM celestial catalog.
moon_models = datasets.icgem.list_models("moon")
print(f"\nLunar models available: {len(moon_models)}")
for entry in moon_models[:3]:
    print(f"  {entry.name:30s} degree={entry.degree:<6d} year={entry.year}")
```


The first call hits ICGEM and writes the index to disk. Subsequent calls within 30 days read straight from the cached JSON.

## Downloading a Model

`datasets.icgem.download_model(body, name, output_path=None)` returns the path to the resulting `.gfc` file. Behaviors worth knowing:

- **Largest-degree resolution**: passing just a name like `"EGM2008"` selects the largest-degree variant ICGEM publishes for that name.
- **Explicit degree**: append `-<DEGREE>` (e.g. `"EGM2008-2190"`) to pin a specific variant.
- **Cache reuse**: if the model is already on disk for that `(name, degree, hash)`, no network call is made.
- **Optional copy**: pass `output_path` to additionally copy the file to a chosen location; the return value then points at that copy.


```python
import brahe.datasets as datasets

# JGM3 is small (~70x70) and stable — a good demonstration target.
# Passing just the name selects the largest published degree variant.
path = datasets.icgem.download_model("earth", "JGM3")
print(f"Cached at: {path}")

# Optionally also copy the file to a chosen location (cache still populated)
copied = datasets.icgem.download_model(
    "earth", "JGM3", output_path="/tmp/icgem_jgm3.gfc"
)
print(f"Copied to: {copied}")

# Lunar model — body name routes to the celestial catalog
moon_path = datasets.icgem.download_model("moon", "GLGM-1")
print(f"Lunar model cached at: {moon_path}")
```


### Error messages

`download_model` resolves the requested name against the cached index and gives a useful hint when something doesn't match:

- Unknown name → suggests the three nearest names by edit distance.
- Known name but missing degree → lists the available degrees for that name.

This makes typos and degree mismatches cheap to debug without consulting the website.

## Refreshing the Index

`datasets.icgem.refresh_index(body)` forces a fresh fetch of the listing page for a single body, regardless of TTL. `datasets.icgem.refresh_all_indexes()` refreshes both the Earth listing and the celestial listing (which covers all non-Earth bodies in one file).


```python
import brahe.datasets as datasets

# Refresh a single body's listing. The Earth listing comes from ICGEM's
# `tom_longtime` page; all non-Earth bodies share the `tom_celestial` index.
datasets.icgem.refresh_index("earth")
print("Refreshed Earth index")

# Refresh both index files in one call — equivalent to refreshing Earth plus
# any non-Earth body (since the celestial listing covers Moon/Mars/Venus/Ceres/...).
datasets.icgem.refresh_all_indexes()
print("Refreshed all ICGEM indexes")

# Confirm the refresh took effect by listing a known body
earth_models = datasets.icgem.list_models("earth")
print(f"\n{len(earth_models)} Earth models after refresh")
```


Reach for these when ICGEM publishes a new model and you don't want to wait for the 30-day TTL to expire.

## Offline & Stale Cache Behavior

The dataset interface is designed to remain useful with no network:

1. **Cold start, no network**: `list_models()` returns the error from the failed fetch — there is nothing cached to fall back on yet.
2. **Populated cache, no network, within TTL**: served straight from cache, no fetch attempted.
3. **Populated cache, no network, past TTL**: refresh fails, the existing (stale) entries are returned, and a warning is logged. This is the key offline-friendly path — once a deployment has populated the cache, it keeps working.
4. **`download_model` for a previously downloaded model**: served from disk; no network call.

Setting the `BRAHE_CACHE` environment variable to a checked-in or shipped cache directory is a clean way to make the ICGEM interface fully offline-capable from the first call.

## Using a Downloaded Model in a Propagator

The `brahe.datasets.icgem` API focuses on *fetching* gravity models. To *use* one as the central-body field in a numerical propagator, build a `GravityModelType` that points at the same body/name pair and wire it through `GravityConfiguration` into a `ForceModelConfig`:


```python
import brahe as bh
import numpy as np

# Initialize EOP data (required for any numerical propagation)
bh.initialize_eop()

# Reference an ICGEM Earth model. Use bh.datasets.icgem.list_models("earth")
# to discover the full catalog. Append "-<DEGREE>" to pin a specific variant.
grav_type = bh.GravityModelType.icgem("earth", "JGM3")

gravity_cfg = bh.GravityConfiguration.spherical_harmonic(
    degree=20, order=20, model_type=grav_type
)

# Minimal force model: ICGEM-sourced spherical-harmonic gravity only
force_cfg = bh.ForceModelConfig(gravity=gravity_cfg)

# Build an initial state for a LEO satellite
epoch = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
oe = np.array(
    [
        bh.R_EARTH + 500e3,  # a (m)
        0.001,  # e
        np.radians(97.8),  # i (rad)
        np.radians(15.0),  # RAAN (rad)
        np.radians(30.0),  # arg perigee (rad)
        np.radians(45.0),  # true anomaly (rad)
    ]
)
state0 = bh.state_koe_to_eci(oe, bh.AngleFormat.RADIANS)

# Construct the propagator — this is where the ICGEM model is downloaded
# (if not cached) and loaded into the force evaluator.
prop = bh.NumericalOrbitPropagator.builder(epoch, state0, force_cfg).build()

# Step one minute forward
prop.step_by(60.0)
state1 = prop.current_state()

drift = float(np.linalg.norm(np.asarray(state1[:3]) - np.asarray(state0[:3])))
print(f"Propagated 60 s with JGM3 (ICGEM source); position drift = {drift:.1f} m")
```

The first `GravityModel.from_model_type` call backing this configuration will download the file if it isn't already cached, then load and cache the parsed `GravityModel` in memory. See the [Force Models guide](../orbit_propagation/numerical_propagation/force_models.md#using-an-icgem-gravity-model) for the full propagator wiring.

## Command Line

The same operations are exposed via the CLI under `brahe datasets icgem`. See the [Datasets CLI guide](../cli/datasets.md#icgem-commands) for `list`, `download`, and `refresh` subcommands.

---

## See Also

- [ICGEM Website](https://icgem.gfz.de) - Official ICGEM model catalog
- [Gravity Models (Learn)](../orbital_dynamics/gravity.md) - Geopotential theory and dominant terms
- [Force Models (Learn)](../orbit_propagation/numerical_propagation/force_models.md) - Configuring gravity in a numerical propagator
- [ICGEM API Reference](../../library_api/datasets/icgem.md) - `brahe.datasets.icgem` function reference
- [GravityModelType (API)](../../library_api/orbit_dynamics/gravity.md#gravity-model-type) - All constructors for selecting a gravity model