# JPL Small-Body Database (SBDB) Lookup

The `brahe.datasets.sbdb` module resolves a small-body search string (name or
designation) to its NAIF/SPK ID and SI physical parameters via the
[JPL Small-Body Database Lookup API](https://ssd-api.jpl.nasa.gov/doc/sbdb.html).
Its primary use is obtaining the NAIF ID needed to request a targeted SPK from
[Horizons](horizons.md) and to define a body via `CentralBody.Custom`.

`SBDBClient.lookup(sstr)` returns an `SBDBObject`. Responses are cached under
`$BRAHE_CACHE/sbdb` (default `~/.cache/brahe/sbdb`) and reused until the cache
age exceeds the client's `cache_max_age` (default 30 days); pass
`cache_max_age=0` to always refetch. Setting `BRAHE_NETWORK_MODE=offline`
serves cached data without any request; see [Environment
Variables](../utilities/environment_variables.md). Ambiguous search strings
and unknown objects raise an error.

**Ephemerides for bodies outside the DE distributions**
Pair SBDB with the [Horizons](horizons.md) client to obtain SPK files for
bodies that are not included in the major DE or planetary-system SPK
distributions: resolve the body's NAIF/SPK ID here, then request a targeted
SPK for that ID from Horizons and load it into the SPICE registry.

## Resolving an Object


```python
import brahe as bh

client = bh.datasets.sbdb.SBDBClient()
ceres = client.lookup("Ceres")

print(f"NAIF ID: {ceres.naif_id()}")
print(f"Full name: {ceres.full_name}")
print(f"GM: {ceres.gm:.6e} m^3/s^2")
print(f"Radius: {ceres.radius:.1f} m")
```

## SBDBObject Fields

`spkid`/`naif_id()` (int), `full_name` (str), `des` (str), `shortname`
(str | None), `kind` (str), `neo` (bool), `gm` (float | None, m³/s²), and
`radius` (float | None, m). `gm` and `radius` are populated only when the
database catalogues them, and are converted from the database's km-based units
to SI on parse.

## See Also

- [Horizons SPK (Learn)](horizons.md) - Generate an SPK for a resolved body
- [SBDB Lookup API (Library API)](../../library_api/datasets/sbdb.md) - Full class reference
- [Dawn at Ceres (Example)](../../examples/dawn_ceres_orbit.md) - SBDB → Horizons → perturbed propagation