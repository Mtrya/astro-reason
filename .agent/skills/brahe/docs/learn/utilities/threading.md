# Multithreading

Brahe uses a global thread pool to parallelize computationally intensive operations, such as computing access windows between satellites and ground locations. The threading utilities allow you to configure the number of threads used by the thread pool.

For complete API details, see the [Threading API Reference](../../library_api/utils/threading.md).

## Default Behavior

By default, Brahe automatically configures the thread pool to use **90% of available CPU cores** on first use. This greatly accelerates computations while leaving some resources for other processes to avoid resource-starving other processes on the machine.

For example, on a system with 8 CPU cores, Brahe will use 7 threads by default.

**Lazy Initialization**

The thread pool is initialized on first use, not when you import Brahe. This means the default thread count is determined when you first call a function that uses the thread pool.

You can configure the thread pool before first use to override the default behavior by calling `set_num_threads()` or `set_max_threads()` as shown below.

**Thread Safety**

All Brahe functions are thread-safe. You can safely call Brahe functions from multiple threads simultaneously.

## Setting Thread Count

### Set Specific Number

You can set the thread pool to use a specific number of threads:


```python
# Set a specific number of threads
bh.set_num_threads(4)
threads_after_set = bh.get_max_threads()
print(f"Thread count after setting to 4: {threads_after_set}")
```

### Set Maximum Threads

To use all available CPU cores (100%), use `set_max_threads()`:


```python
# Set to maximum available (100% of CPU cores)
bh.set_max_threads()
max_threads = bh.get_max_threads()
print(f"Maximum thread count: {max_threads}")
```

**When to Use Maximum Threads**

Use `set_max_threads()` when Brahe is the sole computational task running on a server and you want to maximize throughput.

### Ludicrous Speed!

For a bit of fun, there's an alias for `set_max_threads()`:


```python
# Alternative: use the fun alias!
bh.set_ludicrous_speed()
ludicrous_threads = bh.get_max_threads()
print(f"Ludicrous speed thread count: {ludicrous_threads}")
```

## Querying Thread Count

You can check the current thread pool configuration at any time:


```python
# Query the default number of threads
# By default, Brahe uses 90% of available CPU cores
default_threads = bh.get_max_threads()
print(f"Default thread count: {default_threads}")
```

## Reconfiguring the Thread Pool

The thread pool can be reconfigured at any time during program execution. Simply call `set_num_threads()` or `set_max_threads()` again with the new desired configuration:


```python
# The thread pool can be reconfigured at any time
bh.set_num_threads(2)
final_threads = bh.get_max_threads()
print(f"Final thread count: {final_threads}")
```

## Complete Example

Here's a complete example demonstrating all threading configuration functions:


```python
import brahe as bh

bh.initialize_eop()

# Query the default number of threads
# By default, Brahe uses 90% of available CPU cores
default_threads = bh.get_max_threads()
print(f"Default thread count: {default_threads}")

# Set a specific number of threads
bh.set_num_threads(4)
threads_after_set = bh.get_max_threads()
print(f"Thread count after setting to 4: {threads_after_set}")

# Set to maximum available (100% of CPU cores)
bh.set_max_threads()
max_threads = bh.get_max_threads()
print(f"Maximum thread count: {max_threads}")

# Alternative: use the fun alias!
bh.set_ludicrous_speed()
ludicrous_threads = bh.get_max_threads()
print(f"Ludicrous speed thread count: {ludicrous_threads}")

# The thread pool can be reconfigured at any time
bh.set_num_threads(2)
final_threads = bh.get_max_threads()
print(f"Final thread count: {final_threads}")

# Note: Thread pool is used for parallelizable operations like:
# - Computing access windows between satellites and ground locations
# - Processing large batches of orbital calculations
```


---

## See Also

- [Utilities Overview](index.md) - Overview of all utilities
- [Threading API Reference](../../library_api/utils/threading.md) - Complete threading function documentation