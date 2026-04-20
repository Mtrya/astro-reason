# Managing Space Weather Data

Brahe provides a global space weather provider that supplies geomagnetic indices and solar flux data when needed. If you want to skip the details for now, initialize the global provider with defaults:


```python
import brahe as bh

# Initialize with default caching provider (will download data as needed)
bh.initialize_sw()
```


**warning**

Space weather data **MUST** be initialized before using any functionality that requires it. If no data is initialized, brahe will panic and terminate the program.

The data is used by atmospheric drag models to compute density variations.

## Space Weather Providers

Brahe defines three provider types with different use cases.

### StaticSpaceWeatherProvider

A static provider uses fixed values for all space weather parameters. This is useful for testing or when you want reproducible results with known conditions.


```python
import brahe as bh

# Method 1: Static Space Weather Provider - All Zeros
sw_static_zeros = bh.StaticSpaceWeatherProvider.from_zero()
bh.set_global_space_weather_provider(sw_static_zeros)

# Method 2: Static Space Weather Provider - Custom Constant Values
# Parameters: kp, ap, f107_obs, f107_adj, sunspot_number
sw_static_values = bh.StaticSpaceWeatherProvider.from_values(
    3.0, 15.0, 150.0, 150.0, 100
)
bh.set_global_space_weather_provider(sw_static_values)
```


### FileSpaceWeatherProvider

Load space weather data from CSSI format files. Brahe includes a default data file that is updated with each release.


```python
import brahe as bh

# Method 1: Default Provider -> Uses packaged data file within Brahe
sw_file_default = bh.FileSpaceWeatherProvider.from_default_file()
bh.set_global_space_weather_provider(sw_file_default)

# Method 2: Custom File Path -> Replace with actual file path
if False:  # Change to True to enable custom file example
    sw_file_custom = bh.FileSpaceWeatherProvider.from_file(
        "/path/to/sw19571001.txt",  # Replace with actual file path
        "Hold",  # Extrapolation: "Zero", "Hold", or "Error"
    )
    bh.set_global_space_weather_provider(sw_file_custom)
```


### CachingSpaceWeatherProvider

The caching provider automatically downloads and manages space weather data files from CelesTrak. It checks file age and updates when the cache becomes stale.


```python
import brahe as bh

# Method 1: Create with custom settings
# - Downloads to ~/.cache/brahe/
# - Refreshes if file is older than 24 hours
sw_caching = bh.CachingSpaceWeatherProvider(
    max_age_seconds=86400,  # max_age: seconds (86400 = 24 hours)
    auto_refresh=False,  # check on each query
    extrapolate="Hold",  # extrapolation
)
bh.set_global_space_weather_provider(sw_caching)

# Method 2: Use initialize_sw() which creates a caching provider
bh.initialize_sw()
```


## Extrapolation Options

When querying dates outside the available data range, the provider behavior depends on the extrapolation setting:

- **`"Zero"`**: Return zero values for all parameters
- **`"Hold"`**: Return the last (or first) available value
- **`"Error"`**: Panic and terminate the program

## Accessing Space Weather Data

Query space weather data using the global functions:


```python
import brahe as bh

bh.initialize_sw()

# Get data for a specific epoch
epoch = bh.Epoch.from_datetime(2024, 1, 1, 12, 0, 0.0, 0.0, bh.TimeSystem.UTC)
mjd = epoch.mjd()

# Kp/Ap for specific 3-hour interval
kp = bh.get_global_kp(mjd)
ap = bh.get_global_ap(mjd)

# Daily averages
kp_daily = bh.get_global_kp_daily(mjd)
ap_daily = bh.get_global_ap_daily(mjd)

# All 8 values for the day
kp_all = bh.get_global_kp_all(mjd)  # [Kp_00-03, Kp_03-06, ..., Kp_21-24]
ap_all = bh.get_global_ap_all(mjd)

# F10.7 solar flux
f107 = bh.get_global_f107_observed(mjd)
f107_adj = bh.get_global_f107_adjusted(mjd)
f107_avg = bh.get_global_f107_obs_avg81(mjd)  # 81-day centered average

# Sunspot number
isn = bh.get_global_sunspot_number(mjd)

print(f"Kp: {kp}, Ap: {ap}, F10.7: {f107} sfu, ISN: {isn}")
```


## Range Data Access

The space weather providers also support querying data over a date range, returning a vector of values from before the specific time. This is useful to providing the weather history for drag models.


```python
import brahe as bh

bh.initialize_sw()

epoch = bh.Epoch.from_datetime(2024, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)
mjd = epoch.mjd()

# Get last 30 days of F10.7 data
f107_history = bh.get_global_last_f107(mjd, 30)

# Get last 7 days of daily Ap
ap_history = bh.get_global_last_daily_ap(mjd, 7)

# Get epochs for the data points
epochs = bh.get_global_last_daily_epochs(mjd, 7)

print(f"Last 7 daily Ap values: {ap_history}")
print(f"Last 7 epochs: {[str(e) for e in epochs]}")
```


---

## See Also

- [StaticSpaceWeatherProvider API Reference](../../library_api/space_weather/static_provider.md)
- [FileSpaceWeatherProvider API Reference](../../library_api/space_weather/file_provider.md)
- [CachingSpaceWeatherProvider API Reference](../../library_api/space_weather/caching_provider.md)
- [Space Weather Functions](../../library_api/space_weather/functions.md)