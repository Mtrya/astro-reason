# Orbit & Earth Model Implementation

Living document tracking the orbit propagation and Earth rotation model.

## File Inventory

| File | Status | Purpose |
|------|--------|---------|
| `verifier/orbit.py` | Implemented, validated | Orbit propagation using brahe (RK4, 1s fixed step) |
| `verifier/earth.py` | Implemented, **rewritten to use IAU_EARTH** | ECI-ECEF rotation + target coordinate transform |
| `verifier/constants.py` | Implemented | Physical constants, epoch, simulation parameters |
| `tests/test_orbit.py` | Implemented, all 20 cases pass | Validation against GT curves |

## Reference Frames

### ECI (J2000 / ICRF)

The inertial frame used by both Basilisk and the verifier. Basilisk's SPICE interface
uses `"j2000"` as the reference frame string in `sxform_c()`. The GCRF frame (used by
brahe internally) differs from J2000 by only ~70 mas frame bias — negligible.

All satellite positions, velocities, and attitude (MRP σ_BN) are expressed in this frame.

### ECEF / IAU_EARTH (Body-Fixed)

**CRITICAL**: Basilisk does NOT use ITRF for Earth rotation. It uses the **IAU_EARTH**
frame from SPICE's `pck00010.tpc` kernel, accessed via:

```cpp
// spiceInterface.cpp:419-421
sxform_c(this->referenceBase.c_str(),   // "j2000"
         planetFrame.c_str(),            // "IAU_earth"
         this->J2000Current, aux);
```

The IAU_EARTH model is a simple polynomial approximation of Earth rotation with no
nutation-precession corrections. This is fundamentally different from ITRF (which brahe's
`rotation_eci_to_ecef()` computes using the full IAU 2000A model with EOP corrections).

| Property | IAU_EARTH (Basilisk) | ITRF (brahe) |
|----------|---------------------|--------------|
| Source | pck00010.tpc, BODY399 | IAU 2000A + EOP |
| Pole RA | `α = 0.0 - 0.641T` deg | Full precession-nutation |
| Pole Dec | `δ = 90.0 - 0.557T` deg | Full precession-nutation |
| Prime meridian | `W = 190.147 + 360.9856235d` deg | GAST + nutation corrections |
| Accuracy | ~0.07° vs ITRF | Sub-arcsecond |
| **Angular offset** | **~246 arcsec constant** | Reference |

The 246 arcsec offset causes ~659m target position error on Earth's surface, which
propagates to attitude guidance errors at task assignment transitions.

### DCM Convention

```
dcm_PN = R3(W) @ R1(π/2 - δ) @ R3(π/2 + α)
```

- `dcm_PN` transforms vectors from ECI (N) to ECEF (P): `r_P = dcm_PN @ r_N`
- `dcm_PN.T` transforms vectors from ECEF (P) to ECI (N): `r_N = dcm_PN.T @ r_P`
- Matches SPICE's `sxform_c("j2000", "IAU_earth", et)` rotation block to ~5e-12

## Ephemeris Time

The simulation epoch is **2019-01-01 00:00:00 UTC**.

```
ET = UTC_seconds_past_J2000 + delta_AT + 32.184
   = 599572800.0 + 37 + 32.184
   = 599572869.184 s past J2000.0 TDB
```

| Component | Value | Notes |
|-----------|-------|-------|
| JD(UTC) | 2458484.5 | 2019-01-01 00:00:00 UTC |
| JD(J2000.0) | 2451545.0 | 2000-01-01 12:00:00 TT |
| UTC offset | 6939.5 days = 599572800.0 s | JD difference × 86400 |
| delta_AT | 37 s | Leap seconds for 2019 |
| TT-TAI | 32.184 s | Fixed offset |
| TDB-TT | ~1 ms | Negligible |
| **ET_EPOCH** | **599572869.184 s** | Verified against `spiceInterface.J2000Current = 599572869.183915` |

At simulation step `t`, the ephemeris time is `ET = ET_EPOCH + t` (seconds).

## IAU_EARTH Model Parameters (pck00010.tpc, BODY399)

```
Pole right ascension:  α = 0.0 - 0.641T       (degrees, T in Julian centuries)
Pole declination:      δ = 90.0 - 0.557T       (degrees, T in Julian centuries)
Prime meridian:        W = 190.147 + 360.9856235d  (degrees, d in days since J2000.0 TDB)
```

Where:
- `d = ET / 86400.0` (days since J2000.0 TDB)
- `T = d / 36525.0` (Julian centuries since J2000.0 TDB)

## Orbit Propagation

### Force Model

Matches Basilisk's `gravityEffector` configuration:

| Force | Basilisk Source | Verifier (brahe) |
|-------|----------------|-----------------|
| Earth gravity | `createEarth()` — point mass, no harmonics | `ForceModelConfig.two_body()` |
| Sun perturbation | `createSun()` — third-body | `ThirdBodyConfiguration(DE440s, [SUN])` |
| Other | None | None |

### Integrator

| Property | Basilisk | Verifier (brahe) |
|----------|---------|-----------------|
| Method | RK4 (fixed step) | RK4 (fixed step) |
| Step size | 1.0 s (INTERVAL) | 1.0 s (`initial_step=max_step=1.0`) |
| Coupling | Coupled: translation + rotation + RW | Decoupled: translation only |

### Decoupling Error

Basilisk integrates translation, rotation, and RW dynamics as a coupled 6×6 block system.
Our verifier separates orbit propagation (brahe, translation only) from attitude (NumPy,
rotation + RW). The coupling terms `matrixB` and `matrixC` in Basilisk's back-substitution
are dropped.

**Measured error**: ~0.2m position, ~0.001 m/s velocity over 3601 timesteps. This is
negligible for visibility computation (0.2m at 7000km orbital radius ≈ 0.002 arcsec).

### Initial Conditions

From constellation JSON:

| Parameter | Source | Units |
|-----------|--------|-------|
| Semi-major axis | `orbit.semi_major_axis` | meters |
| Eccentricity | `orbit.eccentricity` | dimensionless |
| Inclination | `orbit.inclination` | degrees |
| RAAN | `orbit.raan` | degrees |
| Arg. of perigee | `orbit.argument_of_perigee` | degrees |
| True anomaly | `satellite.true_anomaly` | degrees |

True anomaly is converted to mean anomaly via `brahe.anomaly_true_to_mean()`, then
Keplerian elements are converted to Cartesian ECI via `brahe.state_koe_to_eci()`.

## Target Coordinate Transform

Ground targets are specified as `(latitude_deg, longitude_deg)` in the constellation
JSON. The transform to ECI is:

```python
r_ECEF = R_earth * [cos(lat)*cos(lon), cos(lat)*sin(lon), sin(lat)]
r_ECI  = dcm_PN.T @ r_ECEF
```

Uses spherical Earth (`RADIUS_EARTH = 6378136.6 m`, altitude = 0). This matches
Basilisk's `GroundLocation.specifyLocation(lat, lon, 0)` → `LLA2PCPF` → PCPF,
then at runtime `r_LP_N = dcm_PN.T @ r_LP_P_Init`.

## Timing Alignment

| Time | State Source | Index |
|------|-------------|-------|
| epoch+0 | Initial conditions (Keplerian → ECI) | `orbit_states[sid][0]` |
| epoch+1 | After 1st propagation step | `orbit_states[sid][1]` = `curves[0].position_eci` |
| epoch+t | After t-th propagation step | `orbit_states[sid][t]` = `curves[t-1].position_eci` |
| epoch+3601 | After 3601st propagation step | `orbit_states[sid][3601]` = `curves[3600].position_eci` |

For attitude simulation at step `t`:
- Dynamics integration produces state at `epoch+(t+1)`
- FSW uses orbit position `orbit_states[sid][t+1]` and ECEF rotation `ecef_rots[t+1]`

## Test Results

All 20 fixture cases pass orbit accuracy tests:
- Position: max error < 0.5m, mean error < 0.2m
- Velocity: max error < 0.001 m/s
- Initial state: error < 0.001m (sub-millimeter)
- Error growth: end error < 3x mid error (stable)

## Bug Fix History

| # | Root Cause | Fix | Impact |
|---|-----------|-----|--------|
| 1 | Used brahe ITRF rotation instead of IAU_EARTH | Rewrote `earth.py` with IAU_EARTH model from pck00010.tpc | Fixed 246 arcsec / 659m target position error |
| 2 | Missing Sun third-body perturbation | Added Sun to force model | Fixed ~4m position drift |
| 3 | Used adaptive integrator (DP54) | Switched to RK4 fixed 1s step | Fixed interpolation artifacts |
| 4 | Used `brahe.position_geodetic_to_ecef` (WGS84) | Use spherical Earth formula manually | Fixed ~20m target position error |

## Basilisk Source References

| Module | File | Key Lines |
|--------|------|-----------|
| SPICE interface | `src/simulation/environment/spiceInterface/spiceInterface.cpp` | sxform_c:419-421 |
| GroundLocation | `src/simulation/environment/groundLocation/groundLocation.cpp` | specifyLocation, updateInertialPositions |
| Gravity | `src/simulation/dynamics/gravityEffector/gravityEffector.cpp` | computeField |
| SPICE kernels | `supportData/EphemerisData/pck00010.tpc` | BODY399 (IAU_EARTH params) |
| Satellite setup | `constellation/environments/basilisk/basilisk_satellite.py` | setup_pointing_location:170-210 |
