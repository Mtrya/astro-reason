# Mission Update: Regional Coverage

## Your Task

You are controlling **15 satellites** from the SKYSAT constellation. Your mission is to maximize the area collected over specific geographic regions (polygons). Horizon: 2025-07-17T12:00:00Z to 2025-07-21T12:00:00Z.

## Mission Objectives

**Primary Goal**: Maximize the total effective area covered within the defined priority polygons using overlapping observation strips where necessary.

### Scoring Metrics

Your plan will receive a score based on the following criteria:


1.  **Polygon Coverage**: The total percentage of the area within the priority polygons that is covered by at least one valid observation strip (maximized).
2.  **Plan Validity**: Your plan must satisfy all physical constraints (battery, storage, slew time).


## Constraints (Hard Physical Limits)

These will invalidate your plan if violated:
- **Battery**: Must satisfy `capacity_wh > 0`.
- **Storage**: Must satisfy `storage_used_mb <= capacity_mb`.
- **Slew**: Satellite must have enough time to slew between targets or scanning strips.

## Mission-Specific Data

### Priority Geographic Regions (Polygons)

The following polygons represent the areas of interest for this mission. You must plan observation strips to cover as much area as possible within these boundaries:

- **Amazon Basin North** (ID: `amazon_north`)
  - **Vertices** (Lat, Lon):
    - (0.0000, -60.0000)
    - (0.0000, -50.0000)
    - (-5.0000, -50.0000)
    - (-5.0000, -60.0000)

- **Gulf of Mexico** (ID: `gulf_of_mexico`)
  - **Vertices** (Lat, Lon):
    - (30.0000, -97.0000)
    - (25.0000, -95.0000)
    - (20.0000, -90.0000)
    - (25.0000, -85.0000)
    - (30.0000, -88.0000)

- **Bay of Bengal** (ID: `bay_of_bengal`)
  - **Vertices** (Lat, Lon):
    - (22.0000, 88.0000)
    - (20.0000, 94.0000)
    - (15.0000, 97.0000)
    - (8.0000, 95.0000)
    - (10.0000, 88.0000)
    - (15.0000, 85.0000)



### Ground Stations
(Use `query_stations` to see available downlink options)

## Final Advice

You are the sole authority for this mission. No human operators are available to assist. You must independently query your assets, calculate access windows, and manage resource constraints to build a successful plan. Commit to your decisions and produce a schedule that maximizes the mission objectives. The outcome rests entirely on your ability to autonomously manage these complex trade-offs.
