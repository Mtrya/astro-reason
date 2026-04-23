# Epoch

The Epoch class is the fundamental time representation in Brahe. It encapsulates a specific instant in time, defined by both a time representation and a time scale. The Epoch class provides methods for converting between different time representations and time scales, as well as for performing arithmetic operations on time instances.

There are even more capabilities and features of the Epoch class beyond what is covered in this guide. For a complete reference of all available methods and properties, please refer to the [Epoch API Reference](../../library_api/time/epoch.md).

## Initialization

There are all sorts of ways you can initialize an Epoch instance. The most common methods are described below.

### Date Time

The most common way to create an Epoch is from date and time components. You can specify just a date (which defaults to midnight), or provide the full date and time including fractional seconds.


```python
import brahe as bh

bh.initialize_eop()

# Create epoch from date only (midnight)
epc1 = bh.Epoch(2024, 1, 1)
print(f"Date only: {epc1}")

# Create epoch from full datetime components
epc2 = bh.Epoch(2024, 6, 15, 14, 30, 45.5, 0.0)
print(f"Full datetime: {epc2}")

# Create epoch with different time system
epc3 = bh.Epoch(2024, 12, 25, 18, 0, 0.0, 0.0, time_system=bh.TimeSystem.GPS)
print(f"GPS time system: {epc3}")

# In Python you can also use the direct datetime constant
epc4 = bh.Epoch(2024, 12, 25, 18, 0, 0.0, 0.0, time_system=bh.TAI)
print(f"GPS time system: {epc4}")
```


### MJD

Modified Julian Date (MJD) is a commonly used time representation in astronomy and astrodynamics. MJD is defined as JD - 2400000.5, which makes it more convenient for modern dates.


```python
import brahe as bh

bh.initialize_eop()

# Create epoch from MJD
mjd = 61041.5
epc2 = bh.Epoch.from_mjd(mjd, bh.UTC)
print(f"MJD {mjd}: {epc2}")

# Verify round-trip conversion
mjd_out = epc2.mjd()
print(f"Round-trip MJD: {mjd_out:.6f}")
```


### JD

Julian Date (JD) is a continuous count of days since the beginning of the Julian Period. It's widely used in astronomy for precise time calculations.


```python
import brahe as bh

bh.initialize_eop()

# Create epoch from JD
jd = 2460310.5
epc = bh.Epoch.from_jd(jd, bh.UTC)
print(f"JD {jd}: {epc}")

# Verify round-trip conversion
jd_out = epc.jd()
print(f"Round-trip JD: {jd_out:.10f}")
```


### String

Epoch instances can be created from ISO 8601 formatted strings or simple date-time strings. The time system can be specified in the string.


```python
import brahe as bh

bh.initialize_eop()

# The string can be an ISO 8601 format
epc1 = bh.Epoch.from_string("2025-01-02T04:56:54.123Z")
print(f"ISO 8601: {epc1}")

# It can be a simple space-separated format with a time system
epc2 = bh.Epoch.from_string("2024-06-15 14:30:45.500 GPS")
print(f"Simple format: {epc2}")

# It can be a datetime without a time system (defaults to UTC)
epc3 = bh.Epoch.from_string("2023-12-31 23:59:59")
print(f"Datetime without time system: {epc3}")

# Or it can just be a date
epc4 = bh.Epoch.from_string("2022-07-04")
print(f"Date only: {epc4}")
```


### GPS Week and Seconds

For GPS applications, you can create epochs from GPS week number and seconds into the week, or from GPS seconds since the GPS epoch (January 6, 1980).


```python
import brahe as bh

bh.initialize_eop()

# Create epoch from GPS week and seconds
# Week 2390, day 2 (October 28, 2025)
week = 2390
seconds = 2 * 86400.0
epc1 = bh.Epoch.from_gps_date(week, seconds)
print(f"GPS Week {week}, Seconds {seconds}: {epc1}")

# Verify round-trip conversion
week_out, sec_out = epc1.gps_date()
print(f"Round-trip: Week {week_out}, Seconds {sec_out:.1f}")

# Create from GPS seconds since GPS epoch
gps_seconds = week * 7 * 86400.0 + seconds
epc2 = bh.Epoch.from_gps_seconds(gps_seconds)
print(f"GPS Seconds {gps_seconds}: {epc2}")
```


## Operations

Once you have an epoch class instance you can add and subtract time as you would expect.

**info**

When performing arithmetic the other operand is always interpreted as a time duration in **seconds**.

### Addition

You can add a time duration (in seconds) to an Epoch to get a new Epoch at a later time.


```python
import brahe as bh

bh.initialize_eop()

# Create an epoch
epc = bh.Epoch(2025, 1, 1, 12, 0, 0.0, 0.0)
print(f"Original epoch: {epc}")

# You can add time in seconds to an Epoch and get a new Epoch back

# Add 1 hour (3600 seconds)
epc_plus_hour = epc + 3600.0
print(f"Plus 1 hour: {epc_plus_hour}")

# Add 1 day (86400 seconds)
epc_plus_day = epc + 86400.0
print(f"Plus 1 day: {epc_plus_day}")

# You can also do in-place addition

# Add 1 second in-place
epc += 1.0
print(f"In-place plus 1 second: {epc}")

# Add 1 milisecond in-place
epc += 0.001
print(f"In-place plus 1 millisecond: {epc}")
```


### Subtraction

Subtracting two Epoch instances returns the time difference between them in seconds.


```python
import brahe as bh

bh.initialize_eop()

# You can subtract two Epoch instances to get the time difference in seconds
epc1 = bh.Epoch(2024, 1, 1, 12, 0, 0.0, 0.0)
epc2 = bh.Epoch(2024, 1, 2, 12, 1, 1.0, 0.0)

dt = epc2 - epc1
print(f"Time difference: {dt:.1f} seconds")

# You can also subtract a float (in seconds) from an Epoch to get a new Epoch
epc = bh.Epoch(2024, 6, 15, 10, 30, 0.0, 0.0)

# Subtract 1 hour (3600 seconds)
epc_minus_hour = epc - 3600.0
print(f"Minus 1 hour: {epc_minus_hour}")

# You can also update an Epoch in-place by subtracting seconds
epc = bh.Epoch(2024, 1, 1, 0, 0, 0.0, 0.0)
epc -= 61.0  # Subtract 61 seconds
print(f"In-place minus 61 seconds: {epc}")
```


### Other Operations

The Epoch class also supports comparison operations (e.g., equality, less than, greater than) to compare different time instances. It also supports methods for getting string representations using language-specific formatting options.


```python
import brahe as bh

bh.initialize_eop()

# Create an epoch
epc_1 = bh.Epoch(2024, 1, 1, 12, 0, 0.0, 0.0)
epc_2 = bh.Epoch(2024, 1, 1, 12, 0, 0.0, 1.0)
epc_3 = bh.Epoch(2024, 1, 1, 12, 0, 0.0, 0.0)

# You can compare two Epoch instances for equality
print(f"epc_1 == epc_2: {epc_1 == epc_2}")
print(f"epc_1 == epc_3: {epc_1 == epc_3}")

# You can also use inequality and comparison operators
print(f"epc_1 != epc_2: {epc_1 != epc_2}")
print(f"epc_1 < epc_2: {epc_1 < epc_2}")
print(f"epc_2 < epc_1: {epc_2 < epc_1}")
print(f"epc_2 > epc_1: {epc_2 > epc_1}")
print(f"epc_1 <= epc_3: {epc_1 <= epc_3}")
print(f"epc_2 >= epc_1: {epc_2 >= epc_1}")
```


## Output and Formatting

Finally, you can take any Epoch instance and then output it in different representations.

### Date Time

You can extract the date and time components from an Epoch, optionally converting to a different time system.


```python
import brahe as bh

bh.initialize_eop()

# Create an epoch
epc = bh.Epoch(2024, 6, 15, 14, 30, 45.5, 0.0)
print(f"Epoch: {epc}")

# Output the equivalent Julian Date
jd = epc.jd()
print(f"Julian Date: {jd:.6f}")

# Get the Julian Date in a different time system (e.g., TT)
jd_tt = epc.jd_as_time_system(time_system=bh.TT)
print(f"Julian Date (TT): {jd_tt:.6f}")

# Output the equivalent Modified Julian Date
mjd = epc.mjd()
print(f"Modified Julian Date: {mjd:.6f}")

# Get the Modified Julian Date in a different time system (e.g., GPS)
mjd_gps = epc.mjd_as_time_system(time_system=bh.GPS)
print(f"Modified Julian Date (GPS): {mjd_gps:.6f}")

# Get the GPS Week and Seconds of Week
gps_week, gps_sow = epc.gps_date()
print(f"GPS Week: {gps_week}, Seconds of Week: {gps_sow:.3f}")

# The Epoch as GPS seconds since the GPS epoch
gps_seconds = epc.gps_seconds()
print(f"GPS Seconds since epoch: {gps_seconds:.3f}")
```


### String Representation

Epochs can be converted to human-readable strings in various formats and time systems.


```python
import brahe as bh

bh.initialize_eop()

# Create an epoch
epc = bh.Epoch(2024, 6, 15, 14, 30, 45.123456789, 0.0)

# Default string representation
print(f"Default: {epc}")

# Explicit string conversion
print(f"String: {str(epc)}")

# Debug representation
print(f"Debug: {repr(epc)}")

# Get string in a different time system
print(f"TT: {epc.to_string_as_time_system(bh.TimeSystem.TT)}")

# Get as ISO 8601 formatted string
print(f"ISO 8601: {epc.isostring()}")

# Get as ISO 8601 with different number of decimal places
print(f"ISO 8601 (0 decimal places): {epc.isostring_with_decimals(0)}")
print(f"ISO 8601 (3 decimal places): {epc.isostring_with_decimals(3)}")
print(f"ISO 8601 (6 decimal places): {epc.isostring_with_decimals(6)}")
```


---

## See Also

- [Epoch API Reference](../../library_api/time/epoch.md)