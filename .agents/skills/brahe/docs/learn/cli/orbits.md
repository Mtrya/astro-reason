# Orbits Commands

The `orbits` command group provides calculations for:
- Orbital period and semi-major axis
- Mean motion
- Anomaly conversions (mean, eccentric, true)
- Sun-synchronous orbit design
- Perigee and apogee velocities

All commands support constant expressions (e.g., `R_EARTH+500e3`).

## Commands

### `orbital-period`

Calculate the orbital period from semi-major axis.

**Syntax:**
```
brahe orbits orbital-period <SEMI_MAJOR_AXIS> [OPTIONS]
```

**Arguments:**
- `SEMI_MAJOR_AXIS` - Semi-major axis in meters (supports constants)

**Options:**
- `--gm <value>` - Gravitational parameter (m³/s²). Default: `GM_EARTH`
- `--units [seconds|minutes|hours|days|years]` - Output time units (default: `seconds`)
- `--format <fmt>` - Output format string (default: `f`)

**Examples:**

LEO orbit period (500km altitude):
```
brahe orbits orbital-period "R_EARTH+500e3"
```
Output:
```
# 5676.977164
```
(Period: ~94.6 minutes)

With different units:
```
brahe orbits orbital-period "R_EARTH+500e3" --units minutes
```
Output:
```
# 94.616286
```

GEO orbit period (should be ~24 hours):
```
brahe orbits orbital-period "R_EARTH+35786e3" --units hours
```
Output:
```
# 23.934441
```

Moon's orbit (using GM_EARTH):
```
brahe orbits orbital-period 384400e3 --units days
```
Output:
```
# 27.451894
```

Mars orbit (using GM_SUN):
```
brahe orbits orbital-period 227.9e9 --gm GM_SUN --units days
```
Output:
```
# 686.794481
```

---

### `sma-from-period`

Calculate semi-major axis from orbital period.

**Syntax:**
```
brahe orbits sma-from-period <PERIOD> [OPTIONS]
```

**Arguments:**
- `PERIOD` - Orbital period (supports expressions)

**Options:**
- `--units [seconds|minutes|hours|days|years]` - Input time units (default: `seconds`)
- `--gm <value>` - Gravitational parameter (m³/s²). Default: `GM_EARTH`
- `--format <fmt>` - Output format string (default: `f`)

**Examples:**

Find altitude for 90-minute orbit:
```
brahe orbits sma-from-period 90 --units minutes
```
Output:
```
# 6652555.699659
```
(Semi-major axis: ~6653 km → altitude ~275 km)

Find GEO altitude (24-hour period):
```
brahe orbits sma-from-period 24 --units hours
```
Output:
```
# 42241095.663660
```
(Semi-major axis: ~42164 km → altitude ~35786 km above Earth surface)

Calculate altitude:
```
# SMA - R_EARTH = altitude
echo "scale=2; ($(brahe orbits sma-from-period 90 --units minutes) - 6378137) / 1000" | bc
```
Output:
```
# 274.41
```

---

### `mean-motion`

Calculate mean motion (radians per second).

**Syntax:**
```
brahe orbits mean-motion <SEMI_MAJOR_AXIS> [OPTIONS]
```

**Arguments:**
- `SEMI_MAJOR_AXIS` - Semi-major axis in meters (supports constants)

**Options:**
- `--gm <value>` - Gravitational parameter (m³/s²). Default: `GM_EARTH`
- `--format <fmt>` - Output format string (default: `f`)

**Examples:**

Mean motion for LEO (500km):
```
brahe orbits mean-motion "R_EARTH+500e3"
```
Output:
```
# 0.001107
```

---

### `anomaly-conversion`

Convert between mean, eccentric, and true anomaly.

**Syntax:**
```
brahe orbits anomaly-conversion <ANOMALY> <ECCENTRICITY> <INPUT_ANOMALY> <OUTPUT_ANOMALY> [OPTIONS]
```

**Arguments:**
- `ANOMALY` - Anomaly value to convert (supports expressions)
- `ECCENTRICITY` - Orbital eccentricity (supports expressions)
- `INPUT_ANOMALY` - Input type: `mean`, `eccentric`, or `true`
- `OUTPUT_ANOMALY` - Output type: `mean`, `eccentric`, or `true`

**Options:**
- `--as-degrees / --no-as-degrees` - Use degrees (default: `--no-as-degrees` = radians)
- `--format <fmt>` - Output format string (default: `f`)

**Examples:**

Mean anomaly to true anomaly (circular orbit):
```
brahe orbits anomaly-conversion 0.785 0.0 mean true
```
Output:
```
# 0.785000
```
(For circular orbit, mean = eccentric = true)

Mean to true (eccentric orbit):
```
brahe orbits anomaly-conversion --as-degrees 45.0 0.1 mean true
```
Output:
```
# 53.849399
```

True to mean anomaly:
```
brahe orbits anomaly-conversion --as-degrees 90.0 0.05 true mean
```
Output:
```
# 84.272810
```

Eccentric to true anomaly:
```
brahe orbits anomaly-conversion --as-degrees 60.0 0.2 eccentric true
```
Output:
```
# 70.528779
```

---

### `sun-sync-inclination`

Calculate the inclination required for a sun-synchronous orbit.

**Syntax:**
```
brahe orbits sun-sync-inclination <SEMI_MAJOR_AXIS> <ECCENTRICITY> [OPTIONS]
```

**Arguments:**
- `SEMI_MAJOR_AXIS` - Semi-major axis in meters (supports constants)
- `ECCENTRICITY` - Eccentricity (supports expressions)

**Options:**
- `--as-degrees / --no-as-degrees` - Output in degrees (default: `--as-degrees`)
- `--format <fmt>` - Output format string (default: `f`)

**Examples:**

Sun-sync inclination for 500km circular orbit:
```
brahe orbits sun-sync-inclination "R_EARTH+500e3" 0.0
```
Output:
```
# 97.401744
```
(Inclination: ~97.42°)

Sun-sync for 600km orbit:
```
brahe orbits sun-sync-inclination "R_EARTH+600e3" 0.001
```
Output:
```
# 97.787587
```

Sun-sync for 800km orbit:
```
brahe orbits sun-sync-inclination "R_EARTH+800e3" 0.0
```
Output:
```
# 98.603036
```

Output in radians:
```
brahe orbits sun-sync-inclination "R_EARTH+500e3" 0.0 --no-as-degrees
```
Output:
```
# 1.699981
```

---

### `perigee-velocity`

Calculate orbital velocity at perigee (closest approach).

**Syntax:**
```
brahe orbits perigee-velocity <SEMI_MAJOR_AXIS> <ECCENTRICITY> [OPTIONS]
```

**Arguments:**
- `SEMI_MAJOR_AXIS` - Semi-major axis in meters (supports constants)
- `ECCENTRICITY` - Eccentricity (supports expressions)

**Options:**
- `--format <fmt>` - Output format string (default: `f`)

**Examples:**

Circular orbit velocity (500km):
```
brahe orbits perigee-velocity "R_EARTH+500e3" 0.0
```
Output:
```
# 7612.608558
```


Eccentric orbit perigee velocity:
```
brahe orbits perigee-velocity "R_EARTH+500e3" 0.1
```
Output:
```
# 8416.055421
```

GTO perigee velocity (highly eccentric):
```
brahe orbits perigee-velocity "R_EARTH+24000e3" 0.73
```
Output:
```
# 9169.158794
```

---

### `apogee-velocity`

Calculate orbital velocity at apogee (farthest point).

**Syntax:**
```
brahe orbits apogee-velocity <SEMI_MAJOR_AXIS> <ECCENTRICITY> [OPTIONS]
```

**Arguments:**
- `SEMI_MAJOR_AXIS` - Semi-major axis in meters (supports constants)
- `ECCENTRICITY` - Eccentricity (supports expressions)

**Options:**
- `--format <fmt>` - Output format string (default: `f`)

**Examples:**

Circular orbit (apogee = perigee):
```
brahe orbits apogee-velocity "R_EARTH+500e3" 0.0
```
Output:
```
# 7612.608558
```

Eccentric orbit apogee velocity:
```
brahe orbits apogee-velocity "R_EARTH+500e3" 0.1
```
Output:
```
# 6885.863526
```
(Lower velocity at apogee)

Compare perigee vs apogee:
```
echo "Perigee: $(brahe orbits perigee-velocity 'R_EARTH+500e3' 0.1) m/s"
echo "Apogee:  $(brahe orbits apogee-velocity 'R_EARTH+500e3' 0.1) m/s"
```
Output:
```
# Perigee: 8416.055421 m/s
# Apogee:  6885.863526 m/s
```

---

---

## See Also

- [Anomaly Conversions](../orbits/anomalies.md) - True, eccentric, and mean anomaly conversions
- [Orbital Properties](../orbits/properties.md) - Orbital period, sun-synchronous inclination, etc.
- [Orbits API](../../library_api/orbits/index.md) - Python orbital mechanics functions
- [Transform CLI](transform.md) - Coordinate conversions
- [Constants](../constants.md) - Physical constants for calculations