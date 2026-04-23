# Managing EOP Data

Generally, users of brahe will not need to directly manage Earth orientation data. The package provides default data files and the `CachingEOPProvider` to automatically update data as needed. However, for advanced users or those with specific data requirements, brahe provides functionality to load and manage Earth orientation data manually.

To make the package interface ergonommic, brahe functions do not explicitly accept Earth orientation data as input parameters. Instead, there is a single, global Earth orientation provider used internally by brahe functions. This global provider can be initialized using one of the provided loading functions.

If you want to skip understanding Earth orientation data for now, you can initialize the global provider with zeroed values using the `initialize_eop()` function:


```python
import brahe as bh

bh.initialize_eop()
```


**warning**

Earth orientation data **MUST** be initialized before using any functionality in brahe that requires Earth orientation data. If no data is initialized, brahe will panic and terminate the program when Earth orientation data is requested.

## Earth Orientation Providers

Brahe defines the `EarthOrientationProvider` trait to provide a common interface for accessing Earth orientation data. There are multiple different types of providers, each with their own use cases. The package includes default data files for ease of use that are sufficient for most purposes.

For the most accurate Earth orientation data modeling in scripts, you should download the latest available Earth orientation data for the desired model and the using the file-based loading methods. Alternatively you can the `CachingEOPProvider` to initialize the Earth orientation data which will automatically download and update the latest data files as needed.

### StaticEOPProvider

A static provider is one that just uses fixed values for Earth orientation parameters. This provider is useful for testing and development or if your application only requires low accuracy.


```python
import brahe as bh


# Method 1: Static EOP Provider - All Zeros
eop_static_zeros = bh.StaticEOPProvider.from_zero()
bh.set_global_eop_provider(eop_static_zeros)

# Method 2: Static EOP Provider - Constant Values
eop_static_values = bh.StaticEOPProvider.from_values(
    0.001, 0.002, 0.003, 0.004, 0.005, 0.006
)
bh.set_global_eop_provider(eop_static_values)
```


### FileEOPProvider

If you want to use high-accuracy Earth orientation data, you can load data from IERS files using the `FileEOPProvider`. Brahe provides functions to load default IERS data files provided with the package, or you can specify your own file paths.

When creating any new file-based data provider there are two parameters that are set at loading time which will determine how the EOP instances handles data returns for times not in the loaded data.

The first parameter is the `interpolate` setting. When `interpolate` is set to `True` and data set will be linearly interpolated to the desired time. When set to `False`, the function call will return the last value prior to the requested data. Given that IERS data is typically provided at daily intervals, it is generally recommended to enable interpolation for most applications.

The second parameter is the `extrapolate` parameter, which can have a value of `Zero`, `Hold`, or `Error`. This value will determine how requests for data points beyond the end of the loaded data are handled. The possible behaviors are

- `Zero`: Returned values will be `0.0` where data is not available
- `Hold`: Will return the last available returned value when data is not available
- `Error`: Data access attempts where data is not present will panic and terminate the program

You can create a file-based Earth orientation provider by specifying the file paths to the desired data files as follows:


```python
import brahe as bh

# Method 1: Default Providers -> These are packaged data files within Brahe

# File-based EOP Provider - Default IERS Standard with Hold Extrapolation
eop_file_default = bh.FileEOPProvider.from_default_standard(
    True,  # Interpolation -> if True times between data points are interpolated
    "Hold",  # Extrapolation method -> How accesses outside data range are handled
)
bh.set_global_eop_provider(eop_file_default)

# File-based EOP Provider - Default C04 Standard with Zero Extrapolation
eop_file_c04 = bh.FileEOPProvider.from_default_c04(False, "Zero")
bh.set_global_eop_provider(eop_file_c04)

# Method 2: Custom File Paths -> Replace 'path_to_file.txt' with actual file paths

if False:  # Change to True to enable custom file examples
    # File-based EOP Provider - Custom Standard File
    eop_file_custom = bh.FileEOPProvider.from_standard_file(
        "path_to_standard_file.txt",  # Replace with actual file path
        True,  # Interpolation
        "Hold",  # Extrapolation
    )
    bh.set_global_eop_provider(eop_file_custom)

    # File-based EOP Provider - Custom C04 File
    eop_file_custom_c04 = bh.FileEOPProvider.from_c04_file(
        "path_to_c04_file.txt",  # Replace with actual file path
        True,  # Interpolation
        "Hold",  # Extrapolation
    )
    bh.set_global_eop_provider(eop_file_custom_c04)
```


### CachingEOPProvider

The `CachingEOPProvider` is a `FileEOPProvider` that automatically downloads and caches the latest Earth orientation data files from the IERS website as needed. It checks the age of the cached data and if the data is older than a specified value, it downloads the latest files, then loads them for use. This provider can also be configured to check for a stale cache on use and update the data if needed, which is useful for long-running applications.

The `CachingEOPProvider` is the recommended provider for most applications as it provides high-accuracy Earth orientation data without requiring manual management of data files. `initialize_eop()` uses this provider by default.

The interpolation and extrapolation parameters are also available when creating a `CachingEOPProvider`, with the same behavior as described for the `FileEOPProvider`.


```python
from pathlib import Path
import brahe as bh

# Method 1: Initialize from Caching EOP Provider -> Internally caches data to ~/.cache/brahe/eop
provider = bh.CachingEOPProvider(
    eop_type="StandardBulletinA",
    max_age_seconds=7 * 86400,  # Maximum age of file before refreshing
    auto_refresh=False,  # Check staleness of every access
    interpolate=True,
    extrapolate="Hold",
)
bh.set_global_eop_provider(provider)

# Method 2: Initialize from Caching EOP Provider with custom location
provider_custom = bh.CachingEOPProvider(
    filepath=str(
        Path(bh.get_brahe_cache_dir()) / "my_eop.txt"
    ),  # Replace with desired file path to load / save from
    eop_type="StandardBulletinA",
    max_age_seconds=7 * 86400,  # Maximum age of file before refreshing
    auto_refresh=False,  # Check staleness of every access
    interpolate=True,
    extrapolate="Hold",
)
bh.set_global_eop_provider(provider_custom)
```


## Downloading EOP Data Files

If you want to manually download Earth orientation data files to store or save them, brahe provides two means of doing so. The first is through the command-line interface (CLI) tool included with brahe. The second is through direct function calls in either the Rust or Python APIs.

### CLI

The brahe CLI command includes an `eop download` subcommand which can be used to download the latest Earth orientation data files from IERS servers.

To download the latest standard product file, use the following command:

```
brahe eop download --product standard <output_filepath>
```

To download the latest C04 final product file, use the following command:

```
brahe eop download --product c04 <output_filepath>
```

### Functions

You can also download Earth orientation data files directly using the `download_standard_eop_file` and `download_c04_eop_file` functions in the `brahe.eop` module.

You can download the latest standard EOP data file as follows:


```python
import brahe as bh

# Download latest standard EOP data
bh.download_standard_eop_file("./eop_data/standard_eop.txt")
```

Or download the latest C04 final product file as follows:


```python
import brahe as bh

# Download latest C04 EOP data
bh.download_c04_eop_file("./eop_data/finals2000A.all.csv")
```

## Accessing EOP Parameters

While not common it is possible to directly access Earth orientation parameters from the currently loaded global Earth orientation provider. This can be useful for debugging or analysis purposes.


```python
import brahe as bh

bh.initialize_eop()

# Get current time
epc = bh.Epoch.now()

xp, yp, dut1, lod, dX, dY = bh.get_global_eop(epc.mjd())

print(f"At epoch {epc}:")
print(f"  x_pole: {xp} arcseconds")
print(f"  y_pole: {yp} arcseconds")
print(f"  dut1: {dut1} seconds")
print(f"  length of day: {lod} seconds")
print(f"  dX: {dX} arcseconds")
print(f"  dY: {dY} arcseconds")
```


You can find more functions to access specific subsets of Earth orientation data in the [API Reference](../../library_api/eop/functions.md).

---

## See Also

- [StaticEOPProvider API Reference](../../library_api/eop/static_provider.md)
- [FileEOPProvider API Reference](../../library_api/eop/file_provider.md)
- [CachingEOPProvider API Reference](../../library_api/eop/caching_provider.md)