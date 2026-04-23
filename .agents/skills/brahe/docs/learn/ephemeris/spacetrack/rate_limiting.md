# Rate Limiting

Space-Track.org enforces rate limits of **30 requests per minute** and **300 requests per hour**. Exceeding these limits results in temporary account suspension. Brahe's `RateLimitConfig` controls a sliding-window rate limiter built into `SpaceTrackClient` that automatically delays requests to stay within the configured thresholds.

By default, the client uses conservative limits of **25 requests per minute** and **250 requests per hour** (~83% of the actual limits), providing safety margin for clock drift and shared accounts. Most users do not need to configure rate limiting at all -- the defaults are applied automatically.

For the complete API reference, see the [RateLimitConfig Reference](../../../library_api/ephemeris/spacetrack/rate_limiting.md).

## Configuration

`RateLimitConfig` supports three modes: default conservative limits, custom limits, and disabled (no limiting).


```python
import brahe as bh

# Default conservative limits (25/min, 250/hour)
config = bh.RateLimitConfig()
print(f"Default config: {config.max_per_minute}/min, {config.max_per_hour}/hour")

# Custom limits
config = bh.RateLimitConfig(max_per_minute=10, max_per_hour=100)
print(f"Custom config:  {config.max_per_minute}/min, {config.max_per_hour}/hour")

# Disable rate limiting entirely
config = bh.RateLimitConfig.disabled()
print(f"Disabled config: {config.max_per_minute}/min, {config.max_per_hour}/hour")

# Create a client with default rate limiting (no config needed)
client = bh.SpaceTrackClient("user@example.com", "password")
print("\nClient with default rate limiting created")

# Create a client with custom rate limiting
config = bh.RateLimitConfig(max_per_minute=10, max_per_hour=100)
client = bh.SpaceTrackClient("user@example.com", "password", rate_limit=config)
print("Client with custom rate limiting created")

# Create a client with rate limiting disabled
config = bh.RateLimitConfig.disabled()
client = bh.SpaceTrackClient("user@example.com", "password", rate_limit=config)
print("Client with disabled rate limiting created")
```


**Defaults Are Automatic**
Creating a `SpaceTrackClient` without specifying a `RateLimitConfig` applies the default conservative limits (25/min, 250/hour). You only need `RateLimitConfig` if you want to change or disable the limits.

## How It Works

The rate limiter tracks request timestamps in two sliding windows (1-minute and 1-hour). Before each HTTP request, the client checks whether the configured limit has been reached in either window. If a limit would be exceeded, the calling thread sleeps until enough time has passed for the oldest request in the window to expire. This is transparent to the caller -- queries simply take longer when the limit is approached.

The limiter applies to all client operations: authentication, queries, file operations, and public file downloads.

---

## See Also

- [RateLimitConfig Reference](../../../library_api/ephemeris/spacetrack/rate_limiting.md) -- Complete API documentation
- [Client](client.md) -- Client creation and query execution
- [Space-Track API Overview](index.md) -- Module architecture and type catalog