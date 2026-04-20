# Time Range

The `TimeRange` class provides an easy way to iterate over a range of time instances. You can specify a start and end `Epoch`, along with a time step in seconds, and the `TimeRange` will generate all the `Epoch` instances within that range at the specified intervals.


```python
import brahe as bh

bh.initialize_eop()

for epc in bh.TimeRange(
    bh.Epoch(2024, 1, 1, 0, 0, 0.0, time_system=bh.UTC),
    bh.Epoch(2024, 1, 2, 0, 0, 0.0, time_system=bh.UTC),
    3600.0,
):
    print(epc)
```
