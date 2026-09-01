# Right Ascension / Declination Transformations

Right ascension ($\alpha$) and declination ($\delta$) are the standard spherical coordinates for describing directions in an inertial frame: $\alpha$ is measured eastward in the fundamental plane from a reference direction, and $\delta$ is measured perpendicular to that plane. Brahe's RA/Dec functions are **frame-agnostic** - they convert between the spherical $(\alpha, \delta, r)$ representation and whatever Cartesian inertial frame the caller supplies. For star catalog positions (FK5, Hipparcos, Tycho-2) that frame is ICRS/GCRF; for other applications it can be any inertial frame consistent with the input Cartesian state.

For complete API details, see the [RA/Dec Coordinates API Reference](../../library_api/coordinates/radec.md).

## Position Conversions

A position at range $r$ with right ascension $\alpha$ and declination $\delta$ maps to the Cartesian inertial position:

$$
\vec{r} = r \begin{bmatrix} \cos\delta\cos\alpha \\ \cos\delta\sin\alpha \\ \sin\delta \end{bmatrix}
$$

and the inverse recovers $(\alpha, \delta, r)$ from $\vec{r} = [x, y, z]$:

$$
r = \lVert \vec{r} \rVert, \qquad \delta = \arcsin\left(\frac{z}{r}\right), \qquad \alpha = \operatorname{atan2}(y, x)
$$

Right ascension is normalized to $[0, 360)$ degrees (or $[0, 2\pi)$ radians). At the polar singularity ($x = y = 0$), $\alpha$ is indeterminate from position alone and `position_inertial_to_radec` returns `0`; use the state-based conversion below to resolve it from velocity instead.


```python
import numpy as np
import pytest

import brahe as bh

# Barnard's Star (HIP 87937), J1991.25 Hipparcos catalog values.
ra = 269.45402305  # deg
dec = 4.66828815  # deg

# Convert RA/Dec to an inertial unit vector (range = 1.0)
x_radec = np.array([ra, dec, 1.0])
x_inertial = bh.position_radec_to_inertial(x_radec, bh.AngleFormat.DEGREES)
print(f"Unit vector: [{x_inertial[0]:.6f}, {x_inertial[1]:.6f}, {x_inertial[2]:.6f}]")

# Convert back to RA/Dec
x_radec_back = bh.position_inertial_to_radec(x_inertial, bh.AngleFormat.DEGREES)
print(f"RA: {x_radec_back[0]:.8f} deg, Dec: {x_radec_back[1]:.8f} deg")

assert x_radec_back[0] == pytest.approx(ra, abs=1e-9)
assert x_radec_back[1] == pytest.approx(dec, abs=1e-9)

# Propagate the star's position forward 10 years using its proper motion,
# parallax, and radial velocity (ESA SP-1200 Vol. 1, §1.5.5).
epoch_from = bh.Epoch.from_mjd(48348.5625, bh.TimeSystem.TT)
epoch_to = bh.Epoch.from_mjd(48348.5625 + 10.0 * 365.25, bh.TimeSystem.TT)

ra_new, dec_new = bh.apply_proper_motion(
    ra,
    dec,
    -797.84,  # pm_ra* (mu_alpha* = mu_alpha * cos(dec)), mas/yr
    10326.93,  # pm_dec, mas/yr
    549.30,  # parallax, mas
    -106.8,  # radial_velocity, km/s
    epoch_from,
    epoch_to,
    bh.AngleFormat.DEGREES,
)
print(f"After 10 yr: RA: {ra_new:.6f} deg, Dec: {dec_new:.6f} deg")

assert ra_new != pytest.approx(ra, abs=1e-6)
```


## State Conversions

Including velocity extends the position relations to their rates. Converting $(\alpha, \delta, r, \dot\alpha, \dot\delta, \dot r)$ to Cartesian state:

$$
\dot{x} = \dot r \cos\delta\cos\alpha - r\sin\delta\cos\alpha\,\dot\delta - r\cos\delta\sin\alpha\,\dot\alpha
$$

$$
\dot{y} = \dot r \cos\delta\sin\alpha - r\sin\delta\sin\alpha\,\dot\delta + r\cos\delta\cos\alpha\,\dot\alpha
$$

$$
\dot{z} = \dot r \sin\delta + r\cos\delta\,\dot\delta
$$

with $x, y, z$ given by the Eq. 4-1 position relation above. The inverse (Cartesian state to $\alpha, \delta, r$ and rates) resolves the polar singularity using velocity rather than returning $\alpha = 0$:

$$
\delta = \arcsin\left(\frac{r_k}{r}\right), \qquad
\alpha = \begin{cases}
\operatorname{atan2}(r_j, r_i) & r_i^2 + r_j^2 > \epsilon \\[4pt]
\operatorname{atan2}(v_j, v_i) & r_i^2 + r_j^2 \le \epsilon \ \text{(polar singularity)}
\end{cases}
$$

$$
\dot r = \frac{r_i v_i + r_j v_j + r_k v_k}{r}, \qquad
\dot\alpha = \frac{v_j r_i - v_i r_j}{r_i^2 + r_j^2}, \qquad
\dot\delta = \frac{v_k - \dot r \, (r_k / r)}{\sqrt{r_i^2 + r_j^2}}
$$


```python
# /// script
# dependencies = ["brahe", "numpy", "pytest"]
# ///
"""
Convert a Cartesian inertial state to right ascension/declination/range with
rates and back, then apply the same site-relative subtract-then-convert
pattern to a topocentric line-of-sight state.
"""

import numpy as np
import pytest

import brahe as bh

# --8<-- [start:state_transforms]
# RA/Dec/range and their rates: [ra, dec, range, ra_dot, dec_dot, range_dot]
x_radec = np.array([45.0, 30.0, 7000e3, 0.01, -0.005, 50.0])
x_inertial = bh.state_radec_to_inertial(x_radec, bh.AngleFormat.DEGREES)
print(
    f"Inertial state: pos=[{x_inertial[0]:.3f}, {x_inertial[1]:.3f}, {x_inertial[2]:.3f}] m"
)
print(
    f"                vel=[{x_inertial[3]:.6f}, {x_inertial[4]:.6f}, {x_inertial[5]:.6f}] m/s"
)

x_radec_back = bh.state_inertial_to_radec(x_inertial, bh.AngleFormat.DEGREES)
print(
    f"RA/Dec round-trip: ra={x_radec_back[0]:.6f} deg, dec={x_radec_back[1]:.6f} deg, "
    f"range={x_radec_back[2]:.3f} m"
)
print(
    f"                   ra_dot={x_radec_back[3]:.6f} deg/s, "
    f"dec_dot={x_radec_back[4]:.6f} deg/s, range_dot={x_radec_back[5]:.3f} m/s"
)

assert x_radec_back[0] == pytest.approx(x_radec[0], abs=1e-9)
assert x_radec_back[3] == pytest.approx(x_radec[3], abs=1e-9)
# --8<-- [end:state_transforms]

# --8<-- [start:topocentric]
# A satellite and an observing site, both as Cartesian inertial states (m, m/s)
x_sat = np.array([8000e3, 1000e3, 500e3, -1000.0, 7000.0, 2000.0])
x_site = np.array([6378e3, 0.0, 0.0, 0.0, 0.0, 0.0])

x_topocentric = x_sat - x_site
x_radec_topo = bh.state_inertial_to_radec(x_topocentric, bh.AngleFormat.DEGREES)
print(
    f"\nTopocentric line of sight: ra={x_radec_topo[0]:.6f} deg, "
    f"dec={x_radec_topo[1]:.6f} deg, range={x_radec_topo[2]:.3f} m"
)
# --8<-- [end:topocentric]
```


## Topocentric Right Ascension/Declination

The RA/Dec conversions above assume the input position/state is already relative to the frame's origin. For a ground-based observation, the object's position must first be made relative to the observing site: subtract the site's inertial position (or state) from the object's before converting.

This subtract-then-convert pattern is the vector form of Vallado Algorithm 26 (*Topocentric*): applying `state_inertial_to_radec` to the slant-range vector $\vec{r}_{\text{sat}} - \vec{r}_{\text{site}}$ is equivalent to running Algorithm 25 directly on that vector, because the topocentric frame's axes are parallel to the geocentric inertial frame - only the origin is translated to the site.


```python
# /// script
# dependencies = ["brahe", "numpy", "pytest"]
# ///
"""
Convert a Cartesian inertial state to right ascension/declination/range with
rates and back, then apply the same site-relative subtract-then-convert
pattern to a topocentric line-of-sight state.
"""

import numpy as np
import pytest

import brahe as bh

# --8<-- [start:state_transforms]
# RA/Dec/range and their rates: [ra, dec, range, ra_dot, dec_dot, range_dot]
x_radec = np.array([45.0, 30.0, 7000e3, 0.01, -0.005, 50.0])
x_inertial = bh.state_radec_to_inertial(x_radec, bh.AngleFormat.DEGREES)
print(
    f"Inertial state: pos=[{x_inertial[0]:.3f}, {x_inertial[1]:.3f}, {x_inertial[2]:.3f}] m"
)
print(
    f"                vel=[{x_inertial[3]:.6f}, {x_inertial[4]:.6f}, {x_inertial[5]:.6f}] m/s"
)

x_radec_back = bh.state_inertial_to_radec(x_inertial, bh.AngleFormat.DEGREES)
print(
    f"RA/Dec round-trip: ra={x_radec_back[0]:.6f} deg, dec={x_radec_back[1]:.6f} deg, "
    f"range={x_radec_back[2]:.3f} m"
)
print(
    f"                   ra_dot={x_radec_back[3]:.6f} deg/s, "
    f"dec_dot={x_radec_back[4]:.6f} deg/s, range_dot={x_radec_back[5]:.3f} m/s"
)

assert x_radec_back[0] == pytest.approx(x_radec[0], abs=1e-9)
assert x_radec_back[3] == pytest.approx(x_radec[3], abs=1e-9)
# --8<-- [end:state_transforms]

# --8<-- [start:topocentric]
# A satellite and an observing site, both as Cartesian inertial states (m, m/s)
x_sat = np.array([8000e3, 1000e3, 500e3, -1000.0, 7000.0, 2000.0])
x_site = np.array([6378e3, 0.0, 0.0, 0.0, 0.0, 0.0])

x_topocentric = x_sat - x_site
x_radec_topo = bh.state_inertial_to_radec(x_topocentric, bh.AngleFormat.DEGREES)
print(
    f"\nTopocentric line of sight: ra={x_radec_topo[0]:.6f} deg, "
    f"dec={x_radec_topo[1]:.6f} deg, range={x_radec_topo[2]:.3f} m"
)
# --8<-- [end:topocentric]
```

This continues the same `radec_state_transforms` example above - see its output for the resulting topocentric line of sight.

For stars, which are effectively at infinite range, this correction is unnecessary: the geocentric catalog $(\alpha, \delta)$ and the topocentric $(\alpha, \delta)$ are the same to any achievable precision, so [`position_radec_to_azel`](../../library_api/coordinates/radec.md) can be called directly on the catalog values.

## Right Ascension/Declination ↔ Azimuth-Elevation

`position_radec_to_azel` and `position_azel_to_radec` rotate a topocentric line-of-sight direction between the equatorial $(\alpha, \delta)$ representation and the local horizon azimuth-elevation representation. Both conversions are **direction-only**: no parallax translation between the geocenter and the site is applied (the site's altitude does not affect the result), `range` passes through unchanged, and a global EOP provider must be initialized for the inertial ↔ Earth-fixed rotation.


```python
import numpy as np

import brahe as bh

bh.initialize_eop()

epc = bh.Epoch.from_datetime(2024, 3, 20, 12, 0, 0.0, 0.0, bh.UTC)
site = np.array([-122.17, 37.43, 100.0])  # Stanford, deg/deg/m
x_radec = np.array([101.28, -16.72, 1.0])  # Sirius, deg/deg/(unit range)

x_azel = bh.position_radec_to_azel(x_radec, site, epc, bh.AngleFormat.DEGREES)
print(f"Azimuth: {x_azel[0]:.4f} deg, Elevation: {x_azel[1]:.4f} deg")

x_radec_back = bh.position_azel_to_radec(x_azel, site, epc, bh.AngleFormat.DEGREES)
print(f"RA: {x_radec_back[0]:.6f} deg, Dec: {x_radec_back[1]:.6f} deg")

assert abs(x_radec_back[0] - x_radec[0]) < 1e-6
assert abs(x_radec_back[1] - x_radec[1]) < 1e-6
```


**info**
Azimuth is measured clockwise from North. This is the same convention used by the [Topocentric Coordinates](topocentric_transformations.md) ENZ/SEZ-to-azimuth-elevation functions, so `position_radec_to_azel` results are directly comparable to `position_enz_to_azel`/`position_sez_to_azel` results.

## Proper Motion

Catalog positions are only valid at their reference epoch. `apply_proper_motion` propagates $(\alpha, \delta)$ from a catalog epoch to a target epoch using IAU SOFA's `iauPmsafe` space-motion routine, given the star's proper motion and, when available, its parallax and radial velocity.

`iauPmsafe` reconstructs the star's full barycentric position/velocity (pv-)state from the catalog $(\alpha, \delta)$, proper motion, parallax, and radial velocity; advances it assuming **straight-line motion at constant velocity** - including a light-time correction and the special-relativistic (Doppler) treatment of Stumpff (1985) - and reduces the result back to catalog $(\alpha, \delta)$ at the target epoch. The `pm_ra` argument follows the standard catalog convention $\mu_{\alpha*} = \mu_\alpha \cos\delta$ (matching the `pmRA`/`pmDE` columns of Hipparcos, Tycho-2, Gaia, and most other catalogs), not the raw coordinate rate $\dot\alpha$. When `parallax` or `radial_velocity` is unavailable it is treated as zero; `iauPmsafe` additionally applies a proper-motion-scaled minimum-parallax guard so a star with a missing or tiny parallax still propagates correctly rather than being clamped to a no-op.

### Underlying model

To first order the direction change `iauPmsafe` produces is the rigorous epoch transformation of ESA SP-1200 §1.5.5. The star's unit direction $\hat{u}_0$ moves in the tangent plane spanned by

$$
\hat{u}_0 = \begin{bmatrix} \cos\delta\cos\alpha \\ \cos\delta\sin\alpha \\ \sin\delta \end{bmatrix}, \qquad
\hat{p} = \begin{bmatrix} -\sin\alpha \\ \cos\alpha \\ 0 \end{bmatrix}, \qquad
\hat{q} = \begin{bmatrix} -\sin\delta\cos\alpha \\ -\sin\delta\sin\alpha \\ \cos\delta \end{bmatrix}
$$

driven by the tangential proper-motion vector $\vec{\mu} = \hat{p}\,\mu_{\alpha*} + \hat{q}\,\mu_\delta$ (with $\mu_{\alpha*}$, $\mu_\delta$ converted from mas/yr to rad/yr) and a radial "perspective-acceleration" term $\mu_r$ that captures the change in angular rate as the star's line-of-sight distance changes:

$$
\mu_r = \frac{v_r \, \varpi_{\text{rad}}}{4.740470446\ \text{km/s per AU/yr}} \qquad \left[\text{yr}^{-1}\right]
$$

where $v_r$ is the radial velocity (km/s), $\varpi_{\text{rad}}$ is the parallax in radians, and $4.740470446\ \text{km/s}$ is the speed of one astronomical unit per year. The perspective term is significant only for high radial-velocity, high-parallax stars such as Barnard's Star; when parallax or radial velocity is unknown it vanishes and the propagation reduces to purely linear proper motion. `iauPmsafe` goes beyond this first-order model by carrying the full pv-state and adding the light-time and Doppler corrections noted above.

The worked example above (Position Conversions) continues past the round-trip check to call `apply_proper_motion` on Barnard's Star, propagating it 10 years forward using its Hipparcos catalog proper motion, parallax, and radial velocity - see its output for the resulting $(\alpha, \delta)$ shift.

**Reference**
Proper motion propagation is performed by IAU SOFA's `iauPmsafe` (SOFA Tools for Earth Attitude, 2023); the underlying epoch-transformation theory is ESA, *The Hipparcos and Tycho Catalogues*, ESA SP-1200, Vol. 1, §1.5.5, 1997. The RA/Dec position, state, and topocentric conversions follow D. Vallado, *Fundamentals of Astrodynamics and Applications*, 4th Ed., §4.4 (Eq. 4-1, Eq. 4-2, Algorithm 25, Algorithm 26), 2013.

Star catalog records expose this transformation directly via `radec_at_epoch` - see [Star Catalogs](../datasets/star_catalogs.md).

---

## See Also

- [RA/Dec Coordinates API Reference](../../library_api/coordinates/radec.md) - Complete function documentation
- [Star Catalogs](../datasets/star_catalogs.md) - FK5, Hipparcos, and Tycho-2 catalog records that use these conversions
- [Topocentric Transformations](topocentric_transformations.md) - ENZ/SEZ frames and azimuth-elevation conversions
- [Cartesian Transformations](cartesian_transformations.md) - Orbital elements and Cartesian states