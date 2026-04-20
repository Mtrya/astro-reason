# Caching

Brahe automatically manages a local cache directory to store downloaded data such as Earth Orientation Parameters (EOP) and TLE data. The caching utilities provide functions to locate and manage these cache directories.

For complete API details, see the [Caching API Reference](../../library_api/utils/caching.md).

## Default Cache Location

By default, Brahe stores cache data in a platform-specific location:

- **Unix/Linux/macOS**: `~/.cache/brahe`
- **Windows**: `%LOCALAPPDATA%\brahe\cache`

All cache directories are automatically created on first access, so you don't need to manually create them.

## Environment Variable Override

You can customize the cache location by setting the `BRAHE_CACHE` environment variable:

```
export BRAHE_CACHE=/custom/path/to/cache
```

This is useful for:

- Using a different storage location with more space
- Sharing cache data across multiple users
- Testing with isolated cache directories

## Getting Cache Directories

### Main Cache Directory

The main cache directory is the root location for all Brahe cache data:


```python
# Get main cache directory
cache_dir = bh.get_brahe_cache_dir()
print(f"Main cache directory: {cache_dir}")
```

### EOP Cache Directory

Earth Orientation Parameters are stored in a dedicated subdirectory:


```python
# Get cache subdirectory for EOP data
eop_cache = bh.get_eop_cache_dir()
print(f"EOP cache directory: {eop_cache}")
```

### CelesTrak Cache Directory

Satellite TLE data downloaded from CelesTrak is stored in its own subdirectory:


```python
# Get cache subdirectory for CelesTrak data
celestrak_cache = bh.get_celestrak_cache_dir()
print(f"CelesTrak cache directory: {celestrak_cache}")
```

### Custom Subdirectories

You can create custom subdirectories within the cache for your own data:


```python
# Get a custom subdirectory within the cache
custom_cache = bh.get_brahe_cache_dir_with_subdir("custom_data")
print(f"Custom cache subdirectory: {custom_cache}")
```

## Complete Example

Here's a complete example demonstrating all cache directory functions:


```python
import brahe as bh

bh.initialize_eop()

# Get main cache directory
cache_dir = bh.get_brahe_cache_dir()
print(f"Main cache directory: {cache_dir}")

# Get cache subdirectory for EOP data
eop_cache = bh.get_eop_cache_dir()
print(f"EOP cache directory: {eop_cache}")

# Get cache subdirectory for CelesTrak data
celestrak_cache = bh.get_celestrak_cache_dir()
print(f"CelesTrak cache directory: {celestrak_cache}")

# Get a custom subdirectory within the cache
custom_cache = bh.get_brahe_cache_dir_with_subdir("custom_data")
print(f"Custom cache subdirectory: {custom_cache}")

# Note: All directories are automatically created if they don't exist
# You can override the default location by setting the BRAHE_CACHE
# environment variable
```


## Cache Management

**Automatic Cleanup**

Brahe does not automatically clean up old cache files. If you need to free up disk space, you can manually delete files from the cache directory. Brahe will re-download any needed data on the next request.

**Sharing Cache Between Users**

If you're working on server with multiple users using Brahe, you can share the same cache directory by setting the `BRAHE_CACHE` environment variable to a common location. This avoids duplicate downloads of EOP and TLE data.

---

## See Also

- [Utilities Overview](index.md) - Overview of all utilities
- [Caching API Reference](../../library_api/utils/caching.md) - Complete caching function documentation