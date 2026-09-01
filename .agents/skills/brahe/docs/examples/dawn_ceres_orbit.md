# Dawn at Ceres

In this example we'll define Ceres as a fully user-supplied central body and
fly an orbit inspired by the Dawn spacecraft's Low Altitude Mapping Orbit
(LAMO) around it. Unlike Earth, the Moon, and Mars, Ceres has no built-in
constants in brahe: no built-in [`CentralBody`](../library_api/propagators/force_model_config.md#central-body) variant, no named
inertial/fixed frame pair, no spin model. Its gravitational parameter and
radius are resolved from the JPL Small-Body Database (SBDB); its spin pole,
prime meridian, and body-fixed frame - which SBDB does not provide - are
supplied by the user via [`CentralBody.Custom`](../library_api/propagators/force_model_config.md#brahe.CentralBody.Custom) and
`register_custom_frame`. The same recipe applies to any body brahe doesn't
have built-in constants for: another dwarf planet, an asteroid, or a comet
nucleus.

NASA's Dawn spacecraft orbited Ceres from 2015 to 2018, spending much of its
final year in LAMO: a ~375 km, near-circular polar orbit used for its
highest-resolution gravity and neutron/gamma-ray mapping. This example is
inspired by that LAMO phase rather than reproducing its exact mission
parameters.

---

## Body Definition

Ceres's orientation model is an IAU-style pole (right ascension,
declination), a prime-meridian angle at J2000, and a spin rate, which
together define the rotation of the body-fixed frame at any epoch. SBDB
doesn't provide these, so they're set here from the IAU WGCCRE 2015 values.
The gravitational parameter and mean radius, which SBDB does provide, are
resolved separately below.

```python
#!/usr/bin/env python
# /// script
# dependencies = ["brahe", "plotly", "numpy"]
# ///
"""
Dawn at Ceres: a user-defined rotating central body

This example demonstrates how to:
1. Resolve a small body (Ceres) in the JPL Small-Body Database (SBDB) to get
   its NAIF/SPK ID and SI physical parameters (GM, radius)
2. Fetch and load a targeted Ceres SPK from JPL Horizons so third-body and
   solar radiation pressure perturbations resolve around the body
3. Define a user-supplied central body (GM, radius, spin pole, prime meridian)
   and register a custom body-fixed frame from an IAU-style pole/prime-meridian
   rotation model
4. Propagate the Dawn spacecraft's LAMO (Low Altitude Mapping Orbit) around
   Ceres with point-mass gravity plus solar/Jovian third-body and solar
   radiation pressure perturbations
5. Report the body-fixed state through the custom frame and visualize the
   trajectory in 3D around a textured Ceres

Unlike Earth, the Moon, and Mars, Ceres has no built-in constants in brahe:
no built-in `CentralBody` variant, no named inertial/fixed frame pair, and no
spin model. Its gravitational parameter and radius are read from SBDB, while
its spin pole, prime meridian, and body-fixed frame - which SBDB does not
provide - are supplied by the user via `CentralBody.Custom` and
`register_custom_frame`. The same recipe applies to any body brahe doesn't
have built-in constants for: another dwarf planet, an asteroid, or a comet
nucleus.

NASA's Dawn spacecraft orbited Ceres from 2015 to 2018, spending much of its
final year in LAMO: a ~375 km, near-circular polar orbit used for its highest
resolution gravity and neutron/gamma-ray mapping. This example is inspired by
that LAMO phase rather than reproducing its exact mission parameters.

The propagator integrates in a Ceres-centered inertial frame whose axes are
ICRF-aligned: its z-axis is the ICRF pole, which sits ~23 deg from Ceres's
spin pole. An inclination passed straight to state_koe_to_eci would therefore
be measured against the wrong pole. Instead, state_koe_to_inertial_for_body
references the elements to Ceres's mean equator at J2000 -- and because Ceres
is a Custom body, it reads the pole from the user-registered body-fixed frame
-- so the 90 deg polar inclination is referenced to Ceres's equator as intended.
"""

# --8<-- [start:all]
# --8<-- [start:preamble]
import os
import pathlib
import sys

import numpy as np

import brahe as bh

# No `bh.initialize_eop()` call is needed here: this example never converts
# to or from Earth-relative frames, so it has no dependency on Earth
# orientation data. SPICE kernels are loaded below (de440s for Sun/Jupiter
# positions plus a Ceres SPK from Horizons) so that the third-body and solar
# radiation pressure perturbations resolve around Ceres.
# --8<-- [end:preamble]

# Configuration for output files
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# --8<-- [start:body_resolution]
# Resolve Ceres in the JPL Small-Body Database to get its NAIF/SPK ID and SI
# physical parameters, then generate and load a targeted SPK from Horizons so
# third-body and SRP perturbations resolve around Ceres. Both the SBDB query
# and the SPK are cached under the brahe cache directory and reused on repeat
# runs, so this hits the network only once per machine.
ceres_obj = bh.datasets.sbdb.SBDBClient().lookup("Ceres")
CERES_NAIF_ID = ceres_obj.naif_id()  # 20000001 (SBDB SPK-ID scheme)
GM_CERES = ceres_obj.gm  # m^3/s^2
R_CERES = ceres_obj.radius  # m
print(f"Ceres: {ceres_obj.full_name}, NAIF ID {CERES_NAIF_ID}")
print(f"  GM = {GM_CERES:.6e} m^3/s^2, radius = {R_CERES / 1e3:.1f} km")

# Load the common SPICE kernels (includes de440s) so Sun/Jupiter positions are
# available, then fetch and load a Ceres SPK covering the propagation span.
bh.load_common_spice_kernels()
spk_t0 = bh.Epoch.from_datetime(2015, 12, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.TDB)
spk_t1 = bh.Epoch.from_datetime(2016, 3, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.TDB)
spk = bh.datasets.horizons.HorizonsClient().get_spk(
    bh.datasets.horizons.HorizonsSPKRequest.for_spkid(CERES_NAIF_ID, spk_t0, spk_t1)
)
spk.load()
print(f"Loaded Ceres SPK: {spk.path}")
# --8<-- [end:body_resolution]

# --8<-- [start:body_definition]
# Ceres orientation model (IAU WGCCRE 2015 pole/rotation). SBDB does not
# supply spin-pole or prime-meridian constants, so they are set here:
CERES_POLE_RA = 291.418  # deg, ICRF right ascension of the spin pole
CERES_POLE_DEC = 66.764  # deg, ICRF declination of the spin pole
CERES_W0 = 170.650  # deg, prime meridian angle at J2000 TT
CERES_W_RATE = 952.1532635  # deg/day
# --8<-- [end:body_definition]

# --8<-- [start:body_fixed_frame]
# A body-fixed frame from the IAU-style pole/prime-meridian model, registered
# as a custom frame: rotation(epoch) -> ICRF-to-body DCM.
_J2000_TT_MJD = 51544.5


def ceres_rotation(epc):
    d = epc.mjd_as_time_system(bh.TimeSystem.TT) - _J2000_TT_MJD
    alpha = np.radians(CERES_POLE_RA)
    delta = np.radians(CERES_POLE_DEC)
    w = np.radians((CERES_W0 + CERES_W_RATE * d) % 360.0)
    return (
        bh.Rz(w, bh.AngleFormat.RADIANS)
        @ bh.Rx(np.pi / 2 - delta, bh.AngleFormat.RADIANS)
        @ bh.Rz(np.pi / 2 + alpha, bh.AngleFormat.RADIANS)
    )


def ceres_omega(epc=None):
    return np.array([0.0, 0.0, np.radians(CERES_W_RATE) / 86400.0])


# The `1` is an arbitrarily chosen registry key for this custom frame; it
# just needs to be unique among registered custom frames.
bh.register_custom_frame(1, ceres_rotation, ceres_omega)
ceres_fixed = bh.ReferenceFrame.BodyFixedCustom(CERES_NAIF_ID, 1)
# --8<-- [end:body_fixed_frame]

# --8<-- [start:force_model]
ceres = bh.CentralBody.Custom(
    "Ceres",
    CERES_NAIF_ID,
    GM_CERES,
    radius=R_CERES,
    omega=ceres_omega(),
    fixed_frame=ceres_fixed,
)

# With the Ceres SPK loaded, enable solar and Jovian third-body perturbations
# and solar radiation pressure. The Sun dominates the third-body signal at
# Ceres; Jupiter is added via the built-in `ThirdBody.JUPITER_BARYCENTER`. The
# occulting body for eclipse geometry is Ceres itself (an SRP shadow cast by
# Earth is meaningless 2.8 AU away), supplied as a Custom occulting body.
SPACECRAFT_MASS = 750.0  # kg (Dawn dry mass, approximate)
SRP_AREA = 20.0  # m^2 (solar-array-dominated cross section, approximate)
CR = 1.3  # reflectivity coefficient

srp = bh.SolarRadiationPressureConfiguration(
    area=bh.ParameterSource.value(SRP_AREA),
    cr=bh.ParameterSource.value(CR),
    eclipse_model=bh.EclipseModel.CONICAL,
    occulting_bodies=[
        bh.OccultingBody.Custom(name="Ceres", naif_id=CERES_NAIF_ID, radius=R_CERES)
    ],
)

force_config = bh.ForceModelConfig.for_body(
    ceres,
    bh.GravityConfiguration.point_mass(),
    srp=srp,
    third_body=[
        bh.ThirdBody.SUN,
        bh.ThirdBody.JUPITER_BARYCENTER,
    ],
    mass=bh.ParameterSource.value(SPACECRAFT_MASS),
)
# --8<-- [end:force_model]

# --8<-- [start:orbit_setup]
# Dawn LAMO (Low Altitude Mapping Orbit): ~375 km circular polar orbit.
epoch = bh.Epoch.from_datetime(2016, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)

oe = np.array(
    [R_CERES + 375e3, 0.001, 90.0, 0.0, 0.0, 0.0]
)  # [a [m], e [-], i [deg], RAAN [deg], argp [deg], M [deg]]

state0 = bh.state_koe_to_inertial_for_body(oe, ceres, bh.AngleFormat.DEGREES)

# Ceres spin pole (ICRF) from the IAU pole constants, used below to confirm the
# orbit geometry (declination / right ascension -> unit pole vector). This is
# the same pole the registered frame carries, evaluated directly here.
_pole_ra = np.radians(CERES_POLE_RA)
_pole_dec = np.radians(CERES_POLE_DEC)
ceres_pole = np.array(
    [
        np.cos(_pole_dec) * np.cos(_pole_ra),
        np.cos(_pole_dec) * np.sin(_pole_ra),
        np.sin(_pole_dec),
    ]
)

print(f"LAMO altitude: {(oe[0] - R_CERES) / 1e3:.1f} km, inclination: {oe[2]:.1f} deg")
print(f"Ceres spin pole (ICRF): {np.array2string(ceres_pole, precision=4)}")
# --8<-- [end:orbit_setup]

# --8<-- [start:propagation]
prop = bh.NumericalOrbitPropagator.builder(epoch, state0, force_config).build()
duration = 2 * 86400.0
print(f"\nPropagating {duration / 86400.0:.0f} days...")
prop.propagate_to(epoch + duration)
print("  Complete!")

# state_bci returns the propagator's native state in the central body's
# body-centered inertial frame (here, Ceres-centered) -- the frame the orbit
# was actually integrated in. state_eci would instead re-center the state onto
# Earth via SPK ephemeris (now possible since the Ceres SPK is loaded), which
# is not the frame we want here.
dt = 120.0
epochs = [epoch + t for t in np.arange(0.0, duration, dt)]
radii_km = np.array([np.linalg.norm(prop.state_bci(epc)[:3]) for epc in epochs]) / 1e3
print(f"\nMin radius: {radii_km.min():.2f} km, max radius: {radii_km.max():.2f} km")
print(f"(Ceres radius: {R_CERES / 1e3:.1f} km)")

# Body-fixed position through the registered frame:
x_fixed = prop.state_in_frame(ceres_fixed, epoch + duration)
print(
    f"\nBody-fixed state at t+{duration / 86400.0:.0f} d: {np.array2string(x_fixed, precision=1)}"
)
# --8<-- [end:propagation]

# --8<-- [start:plot_3d]
fig_3d = bh.plot_trajectory_3d(
    [{"trajectory": prop.trajectory, "color": "cyan", "label": "Dawn (LAMO)"}],
    central_body="ceres",
    backend="plotly",
)
# --8<-- [end:plot_3d]

# --8<-- [start:baseline_comparison]
# Quantify the perturbations by propagating a two-body (point-mass, no
# third-body, no SRP) baseline from the same initial state and comparing. The
# solar/Jovian third-body and SRP accelerations are small at a ~375 km, ~5.4 h
# LAMO orbit, so over 2 days (~9 revolutions) they perturb the trajectory by
# tens of meters rather than reshaping it -- but the divergence is measurable
# and grows with time, which a pure two-body run cannot reproduce.
baseline_config = bh.ForceModelConfig.for_body(
    ceres, bh.GravityConfiguration.point_mass()
)
baseline = bh.NumericalOrbitPropagator.builder(epoch, state0, baseline_config).build()
baseline.propagate_to(epoch + duration)

pos_divergence_m = np.array(
    [
        np.linalg.norm(prop.state_bci(epc)[:3] - baseline.state_bci(epc)[:3])
        for epc in epochs
    ]
)
vel_divergence_mps = np.array(
    [
        np.linalg.norm(prop.state_bci(epc)[3:] - baseline.state_bci(epc)[3:])
        for epc in epochs
    ]
)
max_divergence_m = pos_divergence_m.max()
print(
    f"\nMax perturbed-vs-two-body position divergence: {max_divergence_m:.2f} m "
    f"(0 for a two-body-only run)"
)
# --8<-- [end:baseline_comparison]

# --8<-- [start:plot_divergence]
# Perturbation signature: the perturbed run's position and velocity divergence
# from the two-body baseline, growing over the propagation. A pure two-body run
# would sit at zero; the growth is the solar/Jovian third-body and SRP signal.
import plotly.graph_objects as go

hours = np.arange(0.0, duration, dt) / 3600.0
fig_div = go.Figure()
fig_div.add_trace(
    go.Scatter(x=hours, y=pos_divergence_m, name="Position (m)", mode="lines")
)
fig_div.add_trace(
    go.Scatter(
        x=hours,
        y=vel_divergence_mps * 1e3,
        name="Velocity (mm/s)",
        mode="lines",
        yaxis="y2",
    )
)
fig_div.update_layout(
    title="Perturbed vs two-body divergence",
    xaxis_title="Time since epoch (hours)",
    yaxis={"title": "Position divergence (m)"},
    yaxis2={"title": "Velocity divergence (mm/s)", "overlaying": "y", "side": "right"},
    legend={"x": 0.02, "y": 0.98},
)
# --8<-- [end:plot_divergence]

# Validation
# Inclination relative to the Ceres spin pole confirms the orbit plane was
# built about the Ceres equator, not the ICRF pole. The perturbations barely
# tilt the plane over 2 days (a few 1e-5 deg), so the orbit stays polar; the
# measurable signature of the perturbations is the position divergence above.
incs_deg = []
for epc in epochs:
    x = prop.state_bci(epc)
    h = np.cross(x[:3], x[3:])
    h /= np.linalg.norm(h)
    incs_deg.append(np.degrees(np.arccos(np.clip(np.dot(h, ceres_pole), -1.0, 1.0))))
incs_deg = np.array(incs_deg)
max_excursion = np.max(np.abs(incs_deg - 90.0))
print(f"Inclination rel. Ceres pole: {incs_deg.min():.6f} to {incs_deg.max():.6f} deg")
print(f"Max excursion from 90 deg polar design: {max_excursion:.6f} deg")

# The perturbations move the trajectory measurably off the two-body baseline
# (they are active) while staying small over 2 days: the orbit remains polar to
# well under a hundredth of a degree and inside the LAMO altitude band, and the
# body-fixed state is finite.
print(
    f"\nPerturbations active: {max_divergence_m:.1f} m divergence from the "
    f"two-body baseline; orbit stays polar (excursion {max_excursion:.1e} deg) "
    f"and bounded ({radii_km.min():.1f}-{radii_km.max():.1f} km radius)."
)
# --8<-- [end:all]

# ============================================================================
# Plot Output Section (for documentation generation)
# ============================================================================

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "plots"))
from brahe_theme import save_themed_html

# Save themed figures
light_path, dark_path = save_themed_html(fig_3d, OUTDIR / f"{SCRIPT_NAME}_3d")
print(f"\n✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")

light_path_div, dark_path_div = save_themed_html(
    fig_div, OUTDIR / f"{SCRIPT_NAME}_divergence"
)
print(f"✓ Generated {light_path_div}")
print(f"✓ Generated {dark_path_div}")

print("\nDawn at Ceres Example Complete!")
```

```python
#!/usr/bin/env python
# /// script
# dependencies = ["brahe", "plotly", "numpy"]
# ///
"""
Dawn at Ceres: a user-defined rotating central body

This example demonstrates how to:
1. Resolve a small body (Ceres) in the JPL Small-Body Database (SBDB) to get
   its NAIF/SPK ID and SI physical parameters (GM, radius)
2. Fetch and load a targeted Ceres SPK from JPL Horizons so third-body and
   solar radiation pressure perturbations resolve around the body
3. Define a user-supplied central body (GM, radius, spin pole, prime meridian)
   and register a custom body-fixed frame from an IAU-style pole/prime-meridian
   rotation model
4. Propagate the Dawn spacecraft's LAMO (Low Altitude Mapping Orbit) around
   Ceres with point-mass gravity plus solar/Jovian third-body and solar
   radiation pressure perturbations
5. Report the body-fixed state through the custom frame and visualize the
   trajectory in 3D around a textured Ceres

Unlike Earth, the Moon, and Mars, Ceres has no built-in constants in brahe:
no built-in `CentralBody` variant, no named inertial/fixed frame pair, and no
spin model. Its gravitational parameter and radius are read from SBDB, while
its spin pole, prime meridian, and body-fixed frame - which SBDB does not
provide - are supplied by the user via `CentralBody.Custom` and
`register_custom_frame`. The same recipe applies to any body brahe doesn't
have built-in constants for: another dwarf planet, an asteroid, or a comet
nucleus.

NASA's Dawn spacecraft orbited Ceres from 2015 to 2018, spending much of its
final year in LAMO: a ~375 km, near-circular polar orbit used for its highest
resolution gravity and neutron/gamma-ray mapping. This example is inspired by
that LAMO phase rather than reproducing its exact mission parameters.

The propagator integrates in a Ceres-centered inertial frame whose axes are
ICRF-aligned: its z-axis is the ICRF pole, which sits ~23 deg from Ceres's
spin pole. An inclination passed straight to state_koe_to_eci would therefore
be measured against the wrong pole. Instead, state_koe_to_inertial_for_body
references the elements to Ceres's mean equator at J2000 -- and because Ceres
is a Custom body, it reads the pole from the user-registered body-fixed frame
-- so the 90 deg polar inclination is referenced to Ceres's equator as intended.
"""

# --8<-- [start:all]
# --8<-- [start:preamble]
import os
import pathlib
import sys

import numpy as np

import brahe as bh

# No `bh.initialize_eop()` call is needed here: this example never converts
# to or from Earth-relative frames, so it has no dependency on Earth
# orientation data. SPICE kernels are loaded below (de440s for Sun/Jupiter
# positions plus a Ceres SPK from Horizons) so that the third-body and solar
# radiation pressure perturbations resolve around Ceres.
# --8<-- [end:preamble]

# Configuration for output files
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# --8<-- [start:body_resolution]
# Resolve Ceres in the JPL Small-Body Database to get its NAIF/SPK ID and SI
# physical parameters, then generate and load a targeted SPK from Horizons so
# third-body and SRP perturbations resolve around Ceres. Both the SBDB query
# and the SPK are cached under the brahe cache directory and reused on repeat
# runs, so this hits the network only once per machine.
ceres_obj = bh.datasets.sbdb.SBDBClient().lookup("Ceres")
CERES_NAIF_ID = ceres_obj.naif_id()  # 20000001 (SBDB SPK-ID scheme)
GM_CERES = ceres_obj.gm  # m^3/s^2
R_CERES = ceres_obj.radius  # m
print(f"Ceres: {ceres_obj.full_name}, NAIF ID {CERES_NAIF_ID}")
print(f"  GM = {GM_CERES:.6e} m^3/s^2, radius = {R_CERES / 1e3:.1f} km")

# Load the common SPICE kernels (includes de440s) so Sun/Jupiter positions are
# available, then fetch and load a Ceres SPK covering the propagation span.
bh.load_common_spice_kernels()
spk_t0 = bh.Epoch.from_datetime(2015, 12, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.TDB)
spk_t1 = bh.Epoch.from_datetime(2016, 3, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.TDB)
spk = bh.datasets.horizons.HorizonsClient().get_spk(
    bh.datasets.horizons.HorizonsSPKRequest.for_spkid(CERES_NAIF_ID, spk_t0, spk_t1)
)
spk.load()
print(f"Loaded Ceres SPK: {spk.path}")
# --8<-- [end:body_resolution]

# --8<-- [start:body_definition]
# Ceres orientation model (IAU WGCCRE 2015 pole/rotation). SBDB does not
# supply spin-pole or prime-meridian constants, so they are set here:
CERES_POLE_RA = 291.418  # deg, ICRF right ascension of the spin pole
CERES_POLE_DEC = 66.764  # deg, ICRF declination of the spin pole
CERES_W0 = 170.650  # deg, prime meridian angle at J2000 TT
CERES_W_RATE = 952.1532635  # deg/day
# --8<-- [end:body_definition]

# --8<-- [start:body_fixed_frame]
# A body-fixed frame from the IAU-style pole/prime-meridian model, registered
# as a custom frame: rotation(epoch) -> ICRF-to-body DCM.
_J2000_TT_MJD = 51544.5


def ceres_rotation(epc):
    d = epc.mjd_as_time_system(bh.TimeSystem.TT) - _J2000_TT_MJD
    alpha = np.radians(CERES_POLE_RA)
    delta = np.radians(CERES_POLE_DEC)
    w = np.radians((CERES_W0 + CERES_W_RATE * d) % 360.0)
    return (
        bh.Rz(w, bh.AngleFormat.RADIANS)
        @ bh.Rx(np.pi / 2 - delta, bh.AngleFormat.RADIANS)
        @ bh.Rz(np.pi / 2 + alpha, bh.AngleFormat.RADIANS)
    )


def ceres_omega(epc=None):
    return np.array([0.0, 0.0, np.radians(CERES_W_RATE) / 86400.0])


# The `1` is an arbitrarily chosen registry key for this custom frame; it
# just needs to be unique among registered custom frames.
bh.register_custom_frame(1, ceres_rotation, ceres_omega)
ceres_fixed = bh.ReferenceFrame.BodyFixedCustom(CERES_NAIF_ID, 1)
# --8<-- [end:body_fixed_frame]

# --8<-- [start:force_model]
ceres = bh.CentralBody.Custom(
    "Ceres",
    CERES_NAIF_ID,
    GM_CERES,
    radius=R_CERES,
    omega=ceres_omega(),
    fixed_frame=ceres_fixed,
)

# With the Ceres SPK loaded, enable solar and Jovian third-body perturbations
# and solar radiation pressure. The Sun dominates the third-body signal at
# Ceres; Jupiter is added via the built-in `ThirdBody.JUPITER_BARYCENTER`. The
# occulting body for eclipse geometry is Ceres itself (an SRP shadow cast by
# Earth is meaningless 2.8 AU away), supplied as a Custom occulting body.
SPACECRAFT_MASS = 750.0  # kg (Dawn dry mass, approximate)
SRP_AREA = 20.0  # m^2 (solar-array-dominated cross section, approximate)
CR = 1.3  # reflectivity coefficient

srp = bh.SolarRadiationPressureConfiguration(
    area=bh.ParameterSource.value(SRP_AREA),
    cr=bh.ParameterSource.value(CR),
    eclipse_model=bh.EclipseModel.CONICAL,
    occulting_bodies=[
        bh.OccultingBody.Custom(name="Ceres", naif_id=CERES_NAIF_ID, radius=R_CERES)
    ],
)

force_config = bh.ForceModelConfig.for_body(
    ceres,
    bh.GravityConfiguration.point_mass(),
    srp=srp,
    third_body=[
        bh.ThirdBody.SUN,
        bh.ThirdBody.JUPITER_BARYCENTER,
    ],
    mass=bh.ParameterSource.value(SPACECRAFT_MASS),
)
# --8<-- [end:force_model]

# --8<-- [start:orbit_setup]
# Dawn LAMO (Low Altitude Mapping Orbit): ~375 km circular polar orbit.
epoch = bh.Epoch.from_datetime(2016, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)

oe = np.array(
    [R_CERES + 375e3, 0.001, 90.0, 0.0, 0.0, 0.0]
)  # [a [m], e [-], i [deg], RAAN [deg], argp [deg], M [deg]]

state0 = bh.state_koe_to_inertial_for_body(oe, ceres, bh.AngleFormat.DEGREES)

# Ceres spin pole (ICRF) from the IAU pole constants, used below to confirm the
# orbit geometry (declination / right ascension -> unit pole vector). This is
# the same pole the registered frame carries, evaluated directly here.
_pole_ra = np.radians(CERES_POLE_RA)
_pole_dec = np.radians(CERES_POLE_DEC)
ceres_pole = np.array(
    [
        np.cos(_pole_dec) * np.cos(_pole_ra),
        np.cos(_pole_dec) * np.sin(_pole_ra),
        np.sin(_pole_dec),
    ]
)

print(f"LAMO altitude: {(oe[0] - R_CERES) / 1e3:.1f} km, inclination: {oe[2]:.1f} deg")
print(f"Ceres spin pole (ICRF): {np.array2string(ceres_pole, precision=4)}")
# --8<-- [end:orbit_setup]

# --8<-- [start:propagation]
prop = bh.NumericalOrbitPropagator.builder(epoch, state0, force_config).build()
duration = 2 * 86400.0
print(f"\nPropagating {duration / 86400.0:.0f} days...")
prop.propagate_to(epoch + duration)
print("  Complete!")

# state_bci returns the propagator's native state in the central body's
# body-centered inertial frame (here, Ceres-centered) -- the frame the orbit
# was actually integrated in. state_eci would instead re-center the state onto
# Earth via SPK ephemeris (now possible since the Ceres SPK is loaded), which
# is not the frame we want here.
dt = 120.0
epochs = [epoch + t for t in np.arange(0.0, duration, dt)]
radii_km = np.array([np.linalg.norm(prop.state_bci(epc)[:3]) for epc in epochs]) / 1e3
print(f"\nMin radius: {radii_km.min():.2f} km, max radius: {radii_km.max():.2f} km")
print(f"(Ceres radius: {R_CERES / 1e3:.1f} km)")

# Body-fixed position through the registered frame:
x_fixed = prop.state_in_frame(ceres_fixed, epoch + duration)
print(
    f"\nBody-fixed state at t+{duration / 86400.0:.0f} d: {np.array2string(x_fixed, precision=1)}"
)
# --8<-- [end:propagation]

# --8<-- [start:plot_3d]
fig_3d = bh.plot_trajectory_3d(
    [{"trajectory": prop.trajectory, "color": "cyan", "label": "Dawn (LAMO)"}],
    central_body="ceres",
    backend="plotly",
)
# --8<-- [end:plot_3d]

# --8<-- [start:baseline_comparison]
# Quantify the perturbations by propagating a two-body (point-mass, no
# third-body, no SRP) baseline from the same initial state and comparing. The
# solar/Jovian third-body and SRP accelerations are small at a ~375 km, ~5.4 h
# LAMO orbit, so over 2 days (~9 revolutions) they perturb the trajectory by
# tens of meters rather than reshaping it -- but the divergence is measurable
# and grows with time, which a pure two-body run cannot reproduce.
baseline_config = bh.ForceModelConfig.for_body(
    ceres, bh.GravityConfiguration.point_mass()
)
baseline = bh.NumericalOrbitPropagator.builder(epoch, state0, baseline_config).build()
baseline.propagate_to(epoch + duration)

pos_divergence_m = np.array(
    [
        np.linalg.norm(prop.state_bci(epc)[:3] - baseline.state_bci(epc)[:3])
        for epc in epochs
    ]
)
vel_divergence_mps = np.array(
    [
        np.linalg.norm(prop.state_bci(epc)[3:] - baseline.state_bci(epc)[3:])
        for epc in epochs
    ]
)
max_divergence_m = pos_divergence_m.max()
print(
    f"\nMax perturbed-vs-two-body position divergence: {max_divergence_m:.2f} m "
    f"(0 for a two-body-only run)"
)
# --8<-- [end:baseline_comparison]

# --8<-- [start:plot_divergence]
# Perturbation signature: the perturbed run's position and velocity divergence
# from the two-body baseline, growing over the propagation. A pure two-body run
# would sit at zero; the growth is the solar/Jovian third-body and SRP signal.
import plotly.graph_objects as go

hours = np.arange(0.0, duration, dt) / 3600.0
fig_div = go.Figure()
fig_div.add_trace(
    go.Scatter(x=hours, y=pos_divergence_m, name="Position (m)", mode="lines")
)
fig_div.add_trace(
    go.Scatter(
        x=hours,
        y=vel_divergence_mps * 1e3,
        name="Velocity (mm/s)",
        mode="lines",
        yaxis="y2",
    )
)
fig_div.update_layout(
    title="Perturbed vs two-body divergence",
    xaxis_title="Time since epoch (hours)",
    yaxis={"title": "Position divergence (m)"},
    yaxis2={"title": "Velocity divergence (mm/s)", "overlaying": "y", "side": "right"},
    legend={"x": 0.02, "y": 0.98},
)
# --8<-- [end:plot_divergence]

# Validation
# Inclination relative to the Ceres spin pole confirms the orbit plane was
# built about the Ceres equator, not the ICRF pole. The perturbations barely
# tilt the plane over 2 days (a few 1e-5 deg), so the orbit stays polar; the
# measurable signature of the perturbations is the position divergence above.
incs_deg = []
for epc in epochs:
    x = prop.state_bci(epc)
    h = np.cross(x[:3], x[3:])
    h /= np.linalg.norm(h)
    incs_deg.append(np.degrees(np.arccos(np.clip(np.dot(h, ceres_pole), -1.0, 1.0))))
incs_deg = np.array(incs_deg)
max_excursion = np.max(np.abs(incs_deg - 90.0))
print(f"Inclination rel. Ceres pole: {incs_deg.min():.6f} to {incs_deg.max():.6f} deg")
print(f"Max excursion from 90 deg polar design: {max_excursion:.6f} deg")

# The perturbations move the trajectory measurably off the two-body baseline
# (they are active) while staying small over 2 days: the orbit remains polar to
# well under a hundredth of a degree and inside the LAMO altitude band, and the
# body-fixed state is finite.
print(
    f"\nPerturbations active: {max_divergence_m:.1f} m divergence from the "
    f"two-body baseline; orbit stays polar (excursion {max_excursion:.1e} deg) "
    f"and bounded ({radii_km.min():.1f}-{radii_km.max():.1f} km radius)."
)
# --8<-- [end:all]

# ============================================================================
# Plot Output Section (for documentation generation)
# ============================================================================

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "plots"))
from brahe_theme import save_themed_html

# Save themed figures
light_path, dark_path = save_themed_html(fig_3d, OUTDIR / f"{SCRIPT_NAME}_3d")
print(f"\n✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")

light_path_div, dark_path_div = save_themed_html(
    fig_div, OUTDIR / f"{SCRIPT_NAME}_divergence"
)
print(f"✓ Generated {light_path_div}")
print(f"✓ Generated {dark_path_div}")

print("\nDawn at Ceres Example Complete!")
```

## Resolving Ceres and Loading an Ephemeris

Ceres's NAIF/SPK ID and SI physical parameters - gravitational parameter and
mean radius - come from the JPL Small-Body Database (SBDB) rather than being
hardcoded. A targeted SPK covering the propagation span is then generated and
loaded from JPL Horizons, so the Sun/Jupiter third-body accelerations and the
solar radiation pressure model below have an ephemeris to resolve Ceres's
position against.

```python
#!/usr/bin/env python
# /// script
# dependencies = ["brahe", "plotly", "numpy"]
# ///
"""
Dawn at Ceres: a user-defined rotating central body

This example demonstrates how to:
1. Resolve a small body (Ceres) in the JPL Small-Body Database (SBDB) to get
   its NAIF/SPK ID and SI physical parameters (GM, radius)
2. Fetch and load a targeted Ceres SPK from JPL Horizons so third-body and
   solar radiation pressure perturbations resolve around the body
3. Define a user-supplied central body (GM, radius, spin pole, prime meridian)
   and register a custom body-fixed frame from an IAU-style pole/prime-meridian
   rotation model
4. Propagate the Dawn spacecraft's LAMO (Low Altitude Mapping Orbit) around
   Ceres with point-mass gravity plus solar/Jovian third-body and solar
   radiation pressure perturbations
5. Report the body-fixed state through the custom frame and visualize the
   trajectory in 3D around a textured Ceres

Unlike Earth, the Moon, and Mars, Ceres has no built-in constants in brahe:
no built-in `CentralBody` variant, no named inertial/fixed frame pair, and no
spin model. Its gravitational parameter and radius are read from SBDB, while
its spin pole, prime meridian, and body-fixed frame - which SBDB does not
provide - are supplied by the user via `CentralBody.Custom` and
`register_custom_frame`. The same recipe applies to any body brahe doesn't
have built-in constants for: another dwarf planet, an asteroid, or a comet
nucleus.

NASA's Dawn spacecraft orbited Ceres from 2015 to 2018, spending much of its
final year in LAMO: a ~375 km, near-circular polar orbit used for its highest
resolution gravity and neutron/gamma-ray mapping. This example is inspired by
that LAMO phase rather than reproducing its exact mission parameters.

The propagator integrates in a Ceres-centered inertial frame whose axes are
ICRF-aligned: its z-axis is the ICRF pole, which sits ~23 deg from Ceres's
spin pole. An inclination passed straight to state_koe_to_eci would therefore
be measured against the wrong pole. Instead, state_koe_to_inertial_for_body
references the elements to Ceres's mean equator at J2000 -- and because Ceres
is a Custom body, it reads the pole from the user-registered body-fixed frame
-- so the 90 deg polar inclination is referenced to Ceres's equator as intended.
"""

# --8<-- [start:all]
# --8<-- [start:preamble]
import os
import pathlib
import sys

import numpy as np

import brahe as bh

# No `bh.initialize_eop()` call is needed here: this example never converts
# to or from Earth-relative frames, so it has no dependency on Earth
# orientation data. SPICE kernels are loaded below (de440s for Sun/Jupiter
# positions plus a Ceres SPK from Horizons) so that the third-body and solar
# radiation pressure perturbations resolve around Ceres.
# --8<-- [end:preamble]

# Configuration for output files
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# --8<-- [start:body_resolution]
# Resolve Ceres in the JPL Small-Body Database to get its NAIF/SPK ID and SI
# physical parameters, then generate and load a targeted SPK from Horizons so
# third-body and SRP perturbations resolve around Ceres. Both the SBDB query
# and the SPK are cached under the brahe cache directory and reused on repeat
# runs, so this hits the network only once per machine.
ceres_obj = bh.datasets.sbdb.SBDBClient().lookup("Ceres")
CERES_NAIF_ID = ceres_obj.naif_id()  # 20000001 (SBDB SPK-ID scheme)
GM_CERES = ceres_obj.gm  # m^3/s^2
R_CERES = ceres_obj.radius  # m
print(f"Ceres: {ceres_obj.full_name}, NAIF ID {CERES_NAIF_ID}")
print(f"  GM = {GM_CERES:.6e} m^3/s^2, radius = {R_CERES / 1e3:.1f} km")

# Load the common SPICE kernels (includes de440s) so Sun/Jupiter positions are
# available, then fetch and load a Ceres SPK covering the propagation span.
bh.load_common_spice_kernels()
spk_t0 = bh.Epoch.from_datetime(2015, 12, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.TDB)
spk_t1 = bh.Epoch.from_datetime(2016, 3, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.TDB)
spk = bh.datasets.horizons.HorizonsClient().get_spk(
    bh.datasets.horizons.HorizonsSPKRequest.for_spkid(CERES_NAIF_ID, spk_t0, spk_t1)
)
spk.load()
print(f"Loaded Ceres SPK: {spk.path}")
# --8<-- [end:body_resolution]

# --8<-- [start:body_definition]
# Ceres orientation model (IAU WGCCRE 2015 pole/rotation). SBDB does not
# supply spin-pole or prime-meridian constants, so they are set here:
CERES_POLE_RA = 291.418  # deg, ICRF right ascension of the spin pole
CERES_POLE_DEC = 66.764  # deg, ICRF declination of the spin pole
CERES_W0 = 170.650  # deg, prime meridian angle at J2000 TT
CERES_W_RATE = 952.1532635  # deg/day
# --8<-- [end:body_definition]

# --8<-- [start:body_fixed_frame]
# A body-fixed frame from the IAU-style pole/prime-meridian model, registered
# as a custom frame: rotation(epoch) -> ICRF-to-body DCM.
_J2000_TT_MJD = 51544.5


def ceres_rotation(epc):
    d = epc.mjd_as_time_system(bh.TimeSystem.TT) - _J2000_TT_MJD
    alpha = np.radians(CERES_POLE_RA)
    delta = np.radians(CERES_POLE_DEC)
    w = np.radians((CERES_W0 + CERES_W_RATE * d) % 360.0)
    return (
        bh.Rz(w, bh.AngleFormat.RADIANS)
        @ bh.Rx(np.pi / 2 - delta, bh.AngleFormat.RADIANS)
        @ bh.Rz(np.pi / 2 + alpha, bh.AngleFormat.RADIANS)
    )


def ceres_omega(epc=None):
    return np.array([0.0, 0.0, np.radians(CERES_W_RATE) / 86400.0])


# The `1` is an arbitrarily chosen registry key for this custom frame; it
# just needs to be unique among registered custom frames.
bh.register_custom_frame(1, ceres_rotation, ceres_omega)
ceres_fixed = bh.ReferenceFrame.BodyFixedCustom(CERES_NAIF_ID, 1)
# --8<-- [end:body_fixed_frame]

# --8<-- [start:force_model]
ceres = bh.CentralBody.Custom(
    "Ceres",
    CERES_NAIF_ID,
    GM_CERES,
    radius=R_CERES,
    omega=ceres_omega(),
    fixed_frame=ceres_fixed,
)

# With the Ceres SPK loaded, enable solar and Jovian third-body perturbations
# and solar radiation pressure. The Sun dominates the third-body signal at
# Ceres; Jupiter is added via the built-in `ThirdBody.JUPITER_BARYCENTER`. The
# occulting body for eclipse geometry is Ceres itself (an SRP shadow cast by
# Earth is meaningless 2.8 AU away), supplied as a Custom occulting body.
SPACECRAFT_MASS = 750.0  # kg (Dawn dry mass, approximate)
SRP_AREA = 20.0  # m^2 (solar-array-dominated cross section, approximate)
CR = 1.3  # reflectivity coefficient

srp = bh.SolarRadiationPressureConfiguration(
    area=bh.ParameterSource.value(SRP_AREA),
    cr=bh.ParameterSource.value(CR),
    eclipse_model=bh.EclipseModel.CONICAL,
    occulting_bodies=[
        bh.OccultingBody.Custom(name="Ceres", naif_id=CERES_NAIF_ID, radius=R_CERES)
    ],
)

force_config = bh.ForceModelConfig.for_body(
    ceres,
    bh.GravityConfiguration.point_mass(),
    srp=srp,
    third_body=[
        bh.ThirdBody.SUN,
        bh.ThirdBody.JUPITER_BARYCENTER,
    ],
    mass=bh.ParameterSource.value(SPACECRAFT_MASS),
)
# --8<-- [end:force_model]

# --8<-- [start:orbit_setup]
# Dawn LAMO (Low Altitude Mapping Orbit): ~375 km circular polar orbit.
epoch = bh.Epoch.from_datetime(2016, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)

oe = np.array(
    [R_CERES + 375e3, 0.001, 90.0, 0.0, 0.0, 0.0]
)  # [a [m], e [-], i [deg], RAAN [deg], argp [deg], M [deg]]

state0 = bh.state_koe_to_inertial_for_body(oe, ceres, bh.AngleFormat.DEGREES)

# Ceres spin pole (ICRF) from the IAU pole constants, used below to confirm the
# orbit geometry (declination / right ascension -> unit pole vector). This is
# the same pole the registered frame carries, evaluated directly here.
_pole_ra = np.radians(CERES_POLE_RA)
_pole_dec = np.radians(CERES_POLE_DEC)
ceres_pole = np.array(
    [
        np.cos(_pole_dec) * np.cos(_pole_ra),
        np.cos(_pole_dec) * np.sin(_pole_ra),
        np.sin(_pole_dec),
    ]
)

print(f"LAMO altitude: {(oe[0] - R_CERES) / 1e3:.1f} km, inclination: {oe[2]:.1f} deg")
print(f"Ceres spin pole (ICRF): {np.array2string(ceres_pole, precision=4)}")
# --8<-- [end:orbit_setup]

# --8<-- [start:propagation]
prop = bh.NumericalOrbitPropagator.builder(epoch, state0, force_config).build()
duration = 2 * 86400.0
print(f"\nPropagating {duration / 86400.0:.0f} days...")
prop.propagate_to(epoch + duration)
print("  Complete!")

# state_bci returns the propagator's native state in the central body's
# body-centered inertial frame (here, Ceres-centered) -- the frame the orbit
# was actually integrated in. state_eci would instead re-center the state onto
# Earth via SPK ephemeris (now possible since the Ceres SPK is loaded), which
# is not the frame we want here.
dt = 120.0
epochs = [epoch + t for t in np.arange(0.0, duration, dt)]
radii_km = np.array([np.linalg.norm(prop.state_bci(epc)[:3]) for epc in epochs]) / 1e3
print(f"\nMin radius: {radii_km.min():.2f} km, max radius: {radii_km.max():.2f} km")
print(f"(Ceres radius: {R_CERES / 1e3:.1f} km)")

# Body-fixed position through the registered frame:
x_fixed = prop.state_in_frame(ceres_fixed, epoch + duration)
print(
    f"\nBody-fixed state at t+{duration / 86400.0:.0f} d: {np.array2string(x_fixed, precision=1)}"
)
# --8<-- [end:propagation]

# --8<-- [start:plot_3d]
fig_3d = bh.plot_trajectory_3d(
    [{"trajectory": prop.trajectory, "color": "cyan", "label": "Dawn (LAMO)"}],
    central_body="ceres",
    backend="plotly",
)
# --8<-- [end:plot_3d]

# --8<-- [start:baseline_comparison]
# Quantify the perturbations by propagating a two-body (point-mass, no
# third-body, no SRP) baseline from the same initial state and comparing. The
# solar/Jovian third-body and SRP accelerations are small at a ~375 km, ~5.4 h
# LAMO orbit, so over 2 days (~9 revolutions) they perturb the trajectory by
# tens of meters rather than reshaping it -- but the divergence is measurable
# and grows with time, which a pure two-body run cannot reproduce.
baseline_config = bh.ForceModelConfig.for_body(
    ceres, bh.GravityConfiguration.point_mass()
)
baseline = bh.NumericalOrbitPropagator.builder(epoch, state0, baseline_config).build()
baseline.propagate_to(epoch + duration)

pos_divergence_m = np.array(
    [
        np.linalg.norm(prop.state_bci(epc)[:3] - baseline.state_bci(epc)[:3])
        for epc in epochs
    ]
)
vel_divergence_mps = np.array(
    [
        np.linalg.norm(prop.state_bci(epc)[3:] - baseline.state_bci(epc)[3:])
        for epc in epochs
    ]
)
max_divergence_m = pos_divergence_m.max()
print(
    f"\nMax perturbed-vs-two-body position divergence: {max_divergence_m:.2f} m "
    f"(0 for a two-body-only run)"
)
# --8<-- [end:baseline_comparison]

# --8<-- [start:plot_divergence]
# Perturbation signature: the perturbed run's position and velocity divergence
# from the two-body baseline, growing over the propagation. A pure two-body run
# would sit at zero; the growth is the solar/Jovian third-body and SRP signal.
import plotly.graph_objects as go

hours = np.arange(0.0, duration, dt) / 3600.0
fig_div = go.Figure()
fig_div.add_trace(
    go.Scatter(x=hours, y=pos_divergence_m, name="Position (m)", mode="lines")
)
fig_div.add_trace(
    go.Scatter(
        x=hours,
        y=vel_divergence_mps * 1e3,
        name="Velocity (mm/s)",
        mode="lines",
        yaxis="y2",
    )
)
fig_div.update_layout(
    title="Perturbed vs two-body divergence",
    xaxis_title="Time since epoch (hours)",
    yaxis={"title": "Position divergence (m)"},
    yaxis2={"title": "Velocity divergence (mm/s)", "overlaying": "y", "side": "right"},
    legend={"x": 0.02, "y": 0.98},
)
# --8<-- [end:plot_divergence]

# Validation
# Inclination relative to the Ceres spin pole confirms the orbit plane was
# built about the Ceres equator, not the ICRF pole. The perturbations barely
# tilt the plane over 2 days (a few 1e-5 deg), so the orbit stays polar; the
# measurable signature of the perturbations is the position divergence above.
incs_deg = []
for epc in epochs:
    x = prop.state_bci(epc)
    h = np.cross(x[:3], x[3:])
    h /= np.linalg.norm(h)
    incs_deg.append(np.degrees(np.arccos(np.clip(np.dot(h, ceres_pole), -1.0, 1.0))))
incs_deg = np.array(incs_deg)
max_excursion = np.max(np.abs(incs_deg - 90.0))
print(f"Inclination rel. Ceres pole: {incs_deg.min():.6f} to {incs_deg.max():.6f} deg")
print(f"Max excursion from 90 deg polar design: {max_excursion:.6f} deg")

# The perturbations move the trajectory measurably off the two-body baseline
# (they are active) while staying small over 2 days: the orbit remains polar to
# well under a hundredth of a degree and inside the LAMO altitude band, and the
# body-fixed state is finite.
print(
    f"\nPerturbations active: {max_divergence_m:.1f} m divergence from the "
    f"two-body baseline; orbit stays polar (excursion {max_excursion:.1e} deg) "
    f"and bounded ({radii_km.min():.1f}-{radii_km.max():.1f} km radius)."
)
# --8<-- [end:all]

# ============================================================================
# Plot Output Section (for documentation generation)
# ============================================================================

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "plots"))
from brahe_theme import save_themed_html

# Save themed figures
light_path, dark_path = save_themed_html(fig_3d, OUTDIR / f"{SCRIPT_NAME}_3d")
print(f"\n✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")

light_path_div, dark_path_div = save_themed_html(
    fig_div, OUTDIR / f"{SCRIPT_NAME}_divergence"
)
print(f"✓ Generated {light_path_div}")
print(f"✓ Generated {dark_path_div}")

print("\nDawn at Ceres Example Complete!")
```

The returned SPK segment is centered on the Sun (NAIF ID 10), not the solar
system barycenter. Chaining it through the `de440s` kernel loaded above -
which does carry the Sun's position relative to the barycenter - is what lets
brahe resolve Ceres's position relative to the Sun, Jupiter, or any other
body with a loaded ephemeris.

## Body-Fixed Frame

`register_custom_frame` takes two callbacks: `rotation(epoch)`, returning the
3x3 ICRF-to-body-fixed direction cosine matrix, and an optional
`omega(epoch)`, returning the body-fixed angular velocity vector used for the
velocity transport term (if omitted, it's derived numerically from
`rotation` by central differencing). Here both are built from the standard
IAU pole/prime-meridian rotation

$$R = R_z(W) \, R_x\!\left(\frac{\pi}{2} - \delta\right) \, R_z\!\left(\frac{\pi}{2} + \alpha\right)$$

where $\alpha$, $\delta$ are the pole's ICRF right ascension and declination
and $W$ is the prime-meridian angle, which advances linearly with time at the
body's spin rate. The x-axis of the underlying equatorial basis (used below
to compute the orbit's initial state) is the ascending node of the body's
equator on the ICRF equator - the standard IAU orientation convention
([Archinal et al., 2018](https://doi.org/10.1007/s10569-017-9805-5)) - since
$\hat{z}_{\text{ICRF}} \times \hat{p}$ is perpendicular to both poles, hence
lies in both equatorial planes: the line of nodes. Once registered under an
integer key, `ReferenceFrame.BodyFixedCustom(naif_id, key)` is usable
anywhere a [`ReferenceFrame`](../library_api/frames/router.md#referenceframe) is accepted:

```python
#!/usr/bin/env python
# /// script
# dependencies = ["brahe", "plotly", "numpy"]
# ///
"""
Dawn at Ceres: a user-defined rotating central body

This example demonstrates how to:
1. Resolve a small body (Ceres) in the JPL Small-Body Database (SBDB) to get
   its NAIF/SPK ID and SI physical parameters (GM, radius)
2. Fetch and load a targeted Ceres SPK from JPL Horizons so third-body and
   solar radiation pressure perturbations resolve around the body
3. Define a user-supplied central body (GM, radius, spin pole, prime meridian)
   and register a custom body-fixed frame from an IAU-style pole/prime-meridian
   rotation model
4. Propagate the Dawn spacecraft's LAMO (Low Altitude Mapping Orbit) around
   Ceres with point-mass gravity plus solar/Jovian third-body and solar
   radiation pressure perturbations
5. Report the body-fixed state through the custom frame and visualize the
   trajectory in 3D around a textured Ceres

Unlike Earth, the Moon, and Mars, Ceres has no built-in constants in brahe:
no built-in `CentralBody` variant, no named inertial/fixed frame pair, and no
spin model. Its gravitational parameter and radius are read from SBDB, while
its spin pole, prime meridian, and body-fixed frame - which SBDB does not
provide - are supplied by the user via `CentralBody.Custom` and
`register_custom_frame`. The same recipe applies to any body brahe doesn't
have built-in constants for: another dwarf planet, an asteroid, or a comet
nucleus.

NASA's Dawn spacecraft orbited Ceres from 2015 to 2018, spending much of its
final year in LAMO: a ~375 km, near-circular polar orbit used for its highest
resolution gravity and neutron/gamma-ray mapping. This example is inspired by
that LAMO phase rather than reproducing its exact mission parameters.

The propagator integrates in a Ceres-centered inertial frame whose axes are
ICRF-aligned: its z-axis is the ICRF pole, which sits ~23 deg from Ceres's
spin pole. An inclination passed straight to state_koe_to_eci would therefore
be measured against the wrong pole. Instead, state_koe_to_inertial_for_body
references the elements to Ceres's mean equator at J2000 -- and because Ceres
is a Custom body, it reads the pole from the user-registered body-fixed frame
-- so the 90 deg polar inclination is referenced to Ceres's equator as intended.
"""

# --8<-- [start:all]
# --8<-- [start:preamble]
import os
import pathlib
import sys

import numpy as np

import brahe as bh

# No `bh.initialize_eop()` call is needed here: this example never converts
# to or from Earth-relative frames, so it has no dependency on Earth
# orientation data. SPICE kernels are loaded below (de440s for Sun/Jupiter
# positions plus a Ceres SPK from Horizons) so that the third-body and solar
# radiation pressure perturbations resolve around Ceres.
# --8<-- [end:preamble]

# Configuration for output files
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# --8<-- [start:body_resolution]
# Resolve Ceres in the JPL Small-Body Database to get its NAIF/SPK ID and SI
# physical parameters, then generate and load a targeted SPK from Horizons so
# third-body and SRP perturbations resolve around Ceres. Both the SBDB query
# and the SPK are cached under the brahe cache directory and reused on repeat
# runs, so this hits the network only once per machine.
ceres_obj = bh.datasets.sbdb.SBDBClient().lookup("Ceres")
CERES_NAIF_ID = ceres_obj.naif_id()  # 20000001 (SBDB SPK-ID scheme)
GM_CERES = ceres_obj.gm  # m^3/s^2
R_CERES = ceres_obj.radius  # m
print(f"Ceres: {ceres_obj.full_name}, NAIF ID {CERES_NAIF_ID}")
print(f"  GM = {GM_CERES:.6e} m^3/s^2, radius = {R_CERES / 1e3:.1f} km")

# Load the common SPICE kernels (includes de440s) so Sun/Jupiter positions are
# available, then fetch and load a Ceres SPK covering the propagation span.
bh.load_common_spice_kernels()
spk_t0 = bh.Epoch.from_datetime(2015, 12, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.TDB)
spk_t1 = bh.Epoch.from_datetime(2016, 3, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.TDB)
spk = bh.datasets.horizons.HorizonsClient().get_spk(
    bh.datasets.horizons.HorizonsSPKRequest.for_spkid(CERES_NAIF_ID, spk_t0, spk_t1)
)
spk.load()
print(f"Loaded Ceres SPK: {spk.path}")
# --8<-- [end:body_resolution]

# --8<-- [start:body_definition]
# Ceres orientation model (IAU WGCCRE 2015 pole/rotation). SBDB does not
# supply spin-pole or prime-meridian constants, so they are set here:
CERES_POLE_RA = 291.418  # deg, ICRF right ascension of the spin pole
CERES_POLE_DEC = 66.764  # deg, ICRF declination of the spin pole
CERES_W0 = 170.650  # deg, prime meridian angle at J2000 TT
CERES_W_RATE = 952.1532635  # deg/day
# --8<-- [end:body_definition]

# --8<-- [start:body_fixed_frame]
# A body-fixed frame from the IAU-style pole/prime-meridian model, registered
# as a custom frame: rotation(epoch) -> ICRF-to-body DCM.
_J2000_TT_MJD = 51544.5


def ceres_rotation(epc):
    d = epc.mjd_as_time_system(bh.TimeSystem.TT) - _J2000_TT_MJD
    alpha = np.radians(CERES_POLE_RA)
    delta = np.radians(CERES_POLE_DEC)
    w = np.radians((CERES_W0 + CERES_W_RATE * d) % 360.0)
    return (
        bh.Rz(w, bh.AngleFormat.RADIANS)
        @ bh.Rx(np.pi / 2 - delta, bh.AngleFormat.RADIANS)
        @ bh.Rz(np.pi / 2 + alpha, bh.AngleFormat.RADIANS)
    )


def ceres_omega(epc=None):
    return np.array([0.0, 0.0, np.radians(CERES_W_RATE) / 86400.0])


# The `1` is an arbitrarily chosen registry key for this custom frame; it
# just needs to be unique among registered custom frames.
bh.register_custom_frame(1, ceres_rotation, ceres_omega)
ceres_fixed = bh.ReferenceFrame.BodyFixedCustom(CERES_NAIF_ID, 1)
# --8<-- [end:body_fixed_frame]

# --8<-- [start:force_model]
ceres = bh.CentralBody.Custom(
    "Ceres",
    CERES_NAIF_ID,
    GM_CERES,
    radius=R_CERES,
    omega=ceres_omega(),
    fixed_frame=ceres_fixed,
)

# With the Ceres SPK loaded, enable solar and Jovian third-body perturbations
# and solar radiation pressure. The Sun dominates the third-body signal at
# Ceres; Jupiter is added via the built-in `ThirdBody.JUPITER_BARYCENTER`. The
# occulting body for eclipse geometry is Ceres itself (an SRP shadow cast by
# Earth is meaningless 2.8 AU away), supplied as a Custom occulting body.
SPACECRAFT_MASS = 750.0  # kg (Dawn dry mass, approximate)
SRP_AREA = 20.0  # m^2 (solar-array-dominated cross section, approximate)
CR = 1.3  # reflectivity coefficient

srp = bh.SolarRadiationPressureConfiguration(
    area=bh.ParameterSource.value(SRP_AREA),
    cr=bh.ParameterSource.value(CR),
    eclipse_model=bh.EclipseModel.CONICAL,
    occulting_bodies=[
        bh.OccultingBody.Custom(name="Ceres", naif_id=CERES_NAIF_ID, radius=R_CERES)
    ],
)

force_config = bh.ForceModelConfig.for_body(
    ceres,
    bh.GravityConfiguration.point_mass(),
    srp=srp,
    third_body=[
        bh.ThirdBody.SUN,
        bh.ThirdBody.JUPITER_BARYCENTER,
    ],
    mass=bh.ParameterSource.value(SPACECRAFT_MASS),
)
# --8<-- [end:force_model]

# --8<-- [start:orbit_setup]
# Dawn LAMO (Low Altitude Mapping Orbit): ~375 km circular polar orbit.
epoch = bh.Epoch.from_datetime(2016, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)

oe = np.array(
    [R_CERES + 375e3, 0.001, 90.0, 0.0, 0.0, 0.0]
)  # [a [m], e [-], i [deg], RAAN [deg], argp [deg], M [deg]]

state0 = bh.state_koe_to_inertial_for_body(oe, ceres, bh.AngleFormat.DEGREES)

# Ceres spin pole (ICRF) from the IAU pole constants, used below to confirm the
# orbit geometry (declination / right ascension -> unit pole vector). This is
# the same pole the registered frame carries, evaluated directly here.
_pole_ra = np.radians(CERES_POLE_RA)
_pole_dec = np.radians(CERES_POLE_DEC)
ceres_pole = np.array(
    [
        np.cos(_pole_dec) * np.cos(_pole_ra),
        np.cos(_pole_dec) * np.sin(_pole_ra),
        np.sin(_pole_dec),
    ]
)

print(f"LAMO altitude: {(oe[0] - R_CERES) / 1e3:.1f} km, inclination: {oe[2]:.1f} deg")
print(f"Ceres spin pole (ICRF): {np.array2string(ceres_pole, precision=4)}")
# --8<-- [end:orbit_setup]

# --8<-- [start:propagation]
prop = bh.NumericalOrbitPropagator.builder(epoch, state0, force_config).build()
duration = 2 * 86400.0
print(f"\nPropagating {duration / 86400.0:.0f} days...")
prop.propagate_to(epoch + duration)
print("  Complete!")

# state_bci returns the propagator's native state in the central body's
# body-centered inertial frame (here, Ceres-centered) -- the frame the orbit
# was actually integrated in. state_eci would instead re-center the state onto
# Earth via SPK ephemeris (now possible since the Ceres SPK is loaded), which
# is not the frame we want here.
dt = 120.0
epochs = [epoch + t for t in np.arange(0.0, duration, dt)]
radii_km = np.array([np.linalg.norm(prop.state_bci(epc)[:3]) for epc in epochs]) / 1e3
print(f"\nMin radius: {radii_km.min():.2f} km, max radius: {radii_km.max():.2f} km")
print(f"(Ceres radius: {R_CERES / 1e3:.1f} km)")

# Body-fixed position through the registered frame:
x_fixed = prop.state_in_frame(ceres_fixed, epoch + duration)
print(
    f"\nBody-fixed state at t+{duration / 86400.0:.0f} d: {np.array2string(x_fixed, precision=1)}"
)
# --8<-- [end:propagation]

# --8<-- [start:plot_3d]
fig_3d = bh.plot_trajectory_3d(
    [{"trajectory": prop.trajectory, "color": "cyan", "label": "Dawn (LAMO)"}],
    central_body="ceres",
    backend="plotly",
)
# --8<-- [end:plot_3d]

# --8<-- [start:baseline_comparison]
# Quantify the perturbations by propagating a two-body (point-mass, no
# third-body, no SRP) baseline from the same initial state and comparing. The
# solar/Jovian third-body and SRP accelerations are small at a ~375 km, ~5.4 h
# LAMO orbit, so over 2 days (~9 revolutions) they perturb the trajectory by
# tens of meters rather than reshaping it -- but the divergence is measurable
# and grows with time, which a pure two-body run cannot reproduce.
baseline_config = bh.ForceModelConfig.for_body(
    ceres, bh.GravityConfiguration.point_mass()
)
baseline = bh.NumericalOrbitPropagator.builder(epoch, state0, baseline_config).build()
baseline.propagate_to(epoch + duration)

pos_divergence_m = np.array(
    [
        np.linalg.norm(prop.state_bci(epc)[:3] - baseline.state_bci(epc)[:3])
        for epc in epochs
    ]
)
vel_divergence_mps = np.array(
    [
        np.linalg.norm(prop.state_bci(epc)[3:] - baseline.state_bci(epc)[3:])
        for epc in epochs
    ]
)
max_divergence_m = pos_divergence_m.max()
print(
    f"\nMax perturbed-vs-two-body position divergence: {max_divergence_m:.2f} m "
    f"(0 for a two-body-only run)"
)
# --8<-- [end:baseline_comparison]

# --8<-- [start:plot_divergence]
# Perturbation signature: the perturbed run's position and velocity divergence
# from the two-body baseline, growing over the propagation. A pure two-body run
# would sit at zero; the growth is the solar/Jovian third-body and SRP signal.
import plotly.graph_objects as go

hours = np.arange(0.0, duration, dt) / 3600.0
fig_div = go.Figure()
fig_div.add_trace(
    go.Scatter(x=hours, y=pos_divergence_m, name="Position (m)", mode="lines")
)
fig_div.add_trace(
    go.Scatter(
        x=hours,
        y=vel_divergence_mps * 1e3,
        name="Velocity (mm/s)",
        mode="lines",
        yaxis="y2",
    )
)
fig_div.update_layout(
    title="Perturbed vs two-body divergence",
    xaxis_title="Time since epoch (hours)",
    yaxis={"title": "Position divergence (m)"},
    yaxis2={"title": "Velocity divergence (mm/s)", "overlaying": "y", "side": "right"},
    legend={"x": 0.02, "y": 0.98},
)
# --8<-- [end:plot_divergence]

# Validation
# Inclination relative to the Ceres spin pole confirms the orbit plane was
# built about the Ceres equator, not the ICRF pole. The perturbations barely
# tilt the plane over 2 days (a few 1e-5 deg), so the orbit stays polar; the
# measurable signature of the perturbations is the position divergence above.
incs_deg = []
for epc in epochs:
    x = prop.state_bci(epc)
    h = np.cross(x[:3], x[3:])
    h /= np.linalg.norm(h)
    incs_deg.append(np.degrees(np.arccos(np.clip(np.dot(h, ceres_pole), -1.0, 1.0))))
incs_deg = np.array(incs_deg)
max_excursion = np.max(np.abs(incs_deg - 90.0))
print(f"Inclination rel. Ceres pole: {incs_deg.min():.6f} to {incs_deg.max():.6f} deg")
print(f"Max excursion from 90 deg polar design: {max_excursion:.6f} deg")

# The perturbations move the trajectory measurably off the two-body baseline
# (they are active) while staying small over 2 days: the orbit remains polar to
# well under a hundredth of a degree and inside the LAMO altitude band, and the
# body-fixed state is finite.
print(
    f"\nPerturbations active: {max_divergence_m:.1f} m divergence from the "
    f"two-body baseline; orbit stays polar (excursion {max_excursion:.1e} deg) "
    f"and bounded ({radii_km.min():.1f}-{radii_km.max():.1f} km radius)."
)
# --8<-- [end:all]

# ============================================================================
# Plot Output Section (for documentation generation)
# ============================================================================

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "plots"))
from brahe_theme import save_themed_html

# Save themed figures
light_path, dark_path = save_themed_html(fig_3d, OUTDIR / f"{SCRIPT_NAME}_3d")
print(f"\n✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")

light_path_div, dark_path_div = save_themed_html(
    fig_div, OUTDIR / f"{SCRIPT_NAME}_divergence"
)
print(f"✓ Generated {light_path_div}")
print(f"✓ Generated {dark_path_div}")

print("\nDawn at Ceres Example Complete!")
```

**The angular-velocity callback drives the velocity transport term**
`register_custom_frame` accepts an optional `omega(epoch)` callback
returning the body-fixed angular velocity. When it is omitted, the rate is
recovered by central-differencing `rotation(epoch)`, which costs extra
rotation evaluations per query and is only as accurate as the
finite-difference step. Supplying `omega` analytically - as this example
does from the constant IAU spin rate - makes the velocity transport term
exact and avoids that overhead. See
[Reference Frame Router](../learn/frames/frame_transformations.md) and
[Propagation Around Other Central Bodies](../learn/orbit_propagation/numerical_propagation/other_central_bodies.md).

## Force Model

`CentralBody.Custom` bundles the body's GM, radius, spin vector, and
body-fixed frame into the object [`ForceModelConfig`](../library_api/propagators/force_model_config.md#forcemodelconfig) propagates relative to.
ICGEM's only cataloged Ceres model, `sphericalRFM_CERES_2519`, is a
degree-2519 crustal forward-modeling research product - impractically large
to download for this purpose and not normalized to the body's true GM (its
$C_{0,0} \approx 0.126$, not the conventional 1.0) - so it isn't a drop-in
gravity field here. This example models Ceres's gravity as a point mass
instead, which is the standard starting point when defining your own body.

With the Ceres SPK loaded above, third-body and solar radiation pressure
perturbations resolve around Ceres. The Sun (`ThirdBody.SUN`) and Jupiter -
added as a `ThirdBody.Custom` barycenter (NAIF ID 5), since Jupiter has no
built-in `ThirdBody` variant - dominate the third-body signal at Ceres's
distance from the Sun. The SRP occulting body is Ceres itself, supplied as an
`OccultingBody.Custom`: an SRP shadow cast by Earth is meaningless 2.8 AU
away:

```python
#!/usr/bin/env python
# /// script
# dependencies = ["brahe", "plotly", "numpy"]
# ///
"""
Dawn at Ceres: a user-defined rotating central body

This example demonstrates how to:
1. Resolve a small body (Ceres) in the JPL Small-Body Database (SBDB) to get
   its NAIF/SPK ID and SI physical parameters (GM, radius)
2. Fetch and load a targeted Ceres SPK from JPL Horizons so third-body and
   solar radiation pressure perturbations resolve around the body
3. Define a user-supplied central body (GM, radius, spin pole, prime meridian)
   and register a custom body-fixed frame from an IAU-style pole/prime-meridian
   rotation model
4. Propagate the Dawn spacecraft's LAMO (Low Altitude Mapping Orbit) around
   Ceres with point-mass gravity plus solar/Jovian third-body and solar
   radiation pressure perturbations
5. Report the body-fixed state through the custom frame and visualize the
   trajectory in 3D around a textured Ceres

Unlike Earth, the Moon, and Mars, Ceres has no built-in constants in brahe:
no built-in `CentralBody` variant, no named inertial/fixed frame pair, and no
spin model. Its gravitational parameter and radius are read from SBDB, while
its spin pole, prime meridian, and body-fixed frame - which SBDB does not
provide - are supplied by the user via `CentralBody.Custom` and
`register_custom_frame`. The same recipe applies to any body brahe doesn't
have built-in constants for: another dwarf planet, an asteroid, or a comet
nucleus.

NASA's Dawn spacecraft orbited Ceres from 2015 to 2018, spending much of its
final year in LAMO: a ~375 km, near-circular polar orbit used for its highest
resolution gravity and neutron/gamma-ray mapping. This example is inspired by
that LAMO phase rather than reproducing its exact mission parameters.

The propagator integrates in a Ceres-centered inertial frame whose axes are
ICRF-aligned: its z-axis is the ICRF pole, which sits ~23 deg from Ceres's
spin pole. An inclination passed straight to state_koe_to_eci would therefore
be measured against the wrong pole. Instead, state_koe_to_inertial_for_body
references the elements to Ceres's mean equator at J2000 -- and because Ceres
is a Custom body, it reads the pole from the user-registered body-fixed frame
-- so the 90 deg polar inclination is referenced to Ceres's equator as intended.
"""

# --8<-- [start:all]
# --8<-- [start:preamble]
import os
import pathlib
import sys

import numpy as np

import brahe as bh

# No `bh.initialize_eop()` call is needed here: this example never converts
# to or from Earth-relative frames, so it has no dependency on Earth
# orientation data. SPICE kernels are loaded below (de440s for Sun/Jupiter
# positions plus a Ceres SPK from Horizons) so that the third-body and solar
# radiation pressure perturbations resolve around Ceres.
# --8<-- [end:preamble]

# Configuration for output files
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# --8<-- [start:body_resolution]
# Resolve Ceres in the JPL Small-Body Database to get its NAIF/SPK ID and SI
# physical parameters, then generate and load a targeted SPK from Horizons so
# third-body and SRP perturbations resolve around Ceres. Both the SBDB query
# and the SPK are cached under the brahe cache directory and reused on repeat
# runs, so this hits the network only once per machine.
ceres_obj = bh.datasets.sbdb.SBDBClient().lookup("Ceres")
CERES_NAIF_ID = ceres_obj.naif_id()  # 20000001 (SBDB SPK-ID scheme)
GM_CERES = ceres_obj.gm  # m^3/s^2
R_CERES = ceres_obj.radius  # m
print(f"Ceres: {ceres_obj.full_name}, NAIF ID {CERES_NAIF_ID}")
print(f"  GM = {GM_CERES:.6e} m^3/s^2, radius = {R_CERES / 1e3:.1f} km")

# Load the common SPICE kernels (includes de440s) so Sun/Jupiter positions are
# available, then fetch and load a Ceres SPK covering the propagation span.
bh.load_common_spice_kernels()
spk_t0 = bh.Epoch.from_datetime(2015, 12, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.TDB)
spk_t1 = bh.Epoch.from_datetime(2016, 3, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.TDB)
spk = bh.datasets.horizons.HorizonsClient().get_spk(
    bh.datasets.horizons.HorizonsSPKRequest.for_spkid(CERES_NAIF_ID, spk_t0, spk_t1)
)
spk.load()
print(f"Loaded Ceres SPK: {spk.path}")
# --8<-- [end:body_resolution]

# --8<-- [start:body_definition]
# Ceres orientation model (IAU WGCCRE 2015 pole/rotation). SBDB does not
# supply spin-pole or prime-meridian constants, so they are set here:
CERES_POLE_RA = 291.418  # deg, ICRF right ascension of the spin pole
CERES_POLE_DEC = 66.764  # deg, ICRF declination of the spin pole
CERES_W0 = 170.650  # deg, prime meridian angle at J2000 TT
CERES_W_RATE = 952.1532635  # deg/day
# --8<-- [end:body_definition]

# --8<-- [start:body_fixed_frame]
# A body-fixed frame from the IAU-style pole/prime-meridian model, registered
# as a custom frame: rotation(epoch) -> ICRF-to-body DCM.
_J2000_TT_MJD = 51544.5


def ceres_rotation(epc):
    d = epc.mjd_as_time_system(bh.TimeSystem.TT) - _J2000_TT_MJD
    alpha = np.radians(CERES_POLE_RA)
    delta = np.radians(CERES_POLE_DEC)
    w = np.radians((CERES_W0 + CERES_W_RATE * d) % 360.0)
    return (
        bh.Rz(w, bh.AngleFormat.RADIANS)
        @ bh.Rx(np.pi / 2 - delta, bh.AngleFormat.RADIANS)
        @ bh.Rz(np.pi / 2 + alpha, bh.AngleFormat.RADIANS)
    )


def ceres_omega(epc=None):
    return np.array([0.0, 0.0, np.radians(CERES_W_RATE) / 86400.0])


# The `1` is an arbitrarily chosen registry key for this custom frame; it
# just needs to be unique among registered custom frames.
bh.register_custom_frame(1, ceres_rotation, ceres_omega)
ceres_fixed = bh.ReferenceFrame.BodyFixedCustom(CERES_NAIF_ID, 1)
# --8<-- [end:body_fixed_frame]

# --8<-- [start:force_model]
ceres = bh.CentralBody.Custom(
    "Ceres",
    CERES_NAIF_ID,
    GM_CERES,
    radius=R_CERES,
    omega=ceres_omega(),
    fixed_frame=ceres_fixed,
)

# With the Ceres SPK loaded, enable solar and Jovian third-body perturbations
# and solar radiation pressure. The Sun dominates the third-body signal at
# Ceres; Jupiter is added via the built-in `ThirdBody.JUPITER_BARYCENTER`. The
# occulting body for eclipse geometry is Ceres itself (an SRP shadow cast by
# Earth is meaningless 2.8 AU away), supplied as a Custom occulting body.
SPACECRAFT_MASS = 750.0  # kg (Dawn dry mass, approximate)
SRP_AREA = 20.0  # m^2 (solar-array-dominated cross section, approximate)
CR = 1.3  # reflectivity coefficient

srp = bh.SolarRadiationPressureConfiguration(
    area=bh.ParameterSource.value(SRP_AREA),
    cr=bh.ParameterSource.value(CR),
    eclipse_model=bh.EclipseModel.CONICAL,
    occulting_bodies=[
        bh.OccultingBody.Custom(name="Ceres", naif_id=CERES_NAIF_ID, radius=R_CERES)
    ],
)

force_config = bh.ForceModelConfig.for_body(
    ceres,
    bh.GravityConfiguration.point_mass(),
    srp=srp,
    third_body=[
        bh.ThirdBody.SUN,
        bh.ThirdBody.JUPITER_BARYCENTER,
    ],
    mass=bh.ParameterSource.value(SPACECRAFT_MASS),
)
# --8<-- [end:force_model]

# --8<-- [start:orbit_setup]
# Dawn LAMO (Low Altitude Mapping Orbit): ~375 km circular polar orbit.
epoch = bh.Epoch.from_datetime(2016, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)

oe = np.array(
    [R_CERES + 375e3, 0.001, 90.0, 0.0, 0.0, 0.0]
)  # [a [m], e [-], i [deg], RAAN [deg], argp [deg], M [deg]]

state0 = bh.state_koe_to_inertial_for_body(oe, ceres, bh.AngleFormat.DEGREES)

# Ceres spin pole (ICRF) from the IAU pole constants, used below to confirm the
# orbit geometry (declination / right ascension -> unit pole vector). This is
# the same pole the registered frame carries, evaluated directly here.
_pole_ra = np.radians(CERES_POLE_RA)
_pole_dec = np.radians(CERES_POLE_DEC)
ceres_pole = np.array(
    [
        np.cos(_pole_dec) * np.cos(_pole_ra),
        np.cos(_pole_dec) * np.sin(_pole_ra),
        np.sin(_pole_dec),
    ]
)

print(f"LAMO altitude: {(oe[0] - R_CERES) / 1e3:.1f} km, inclination: {oe[2]:.1f} deg")
print(f"Ceres spin pole (ICRF): {np.array2string(ceres_pole, precision=4)}")
# --8<-- [end:orbit_setup]

# --8<-- [start:propagation]
prop = bh.NumericalOrbitPropagator.builder(epoch, state0, force_config).build()
duration = 2 * 86400.0
print(f"\nPropagating {duration / 86400.0:.0f} days...")
prop.propagate_to(epoch + duration)
print("  Complete!")

# state_bci returns the propagator's native state in the central body's
# body-centered inertial frame (here, Ceres-centered) -- the frame the orbit
# was actually integrated in. state_eci would instead re-center the state onto
# Earth via SPK ephemeris (now possible since the Ceres SPK is loaded), which
# is not the frame we want here.
dt = 120.0
epochs = [epoch + t for t in np.arange(0.0, duration, dt)]
radii_km = np.array([np.linalg.norm(prop.state_bci(epc)[:3]) for epc in epochs]) / 1e3
print(f"\nMin radius: {radii_km.min():.2f} km, max radius: {radii_km.max():.2f} km")
print(f"(Ceres radius: {R_CERES / 1e3:.1f} km)")

# Body-fixed position through the registered frame:
x_fixed = prop.state_in_frame(ceres_fixed, epoch + duration)
print(
    f"\nBody-fixed state at t+{duration / 86400.0:.0f} d: {np.array2string(x_fixed, precision=1)}"
)
# --8<-- [end:propagation]

# --8<-- [start:plot_3d]
fig_3d = bh.plot_trajectory_3d(
    [{"trajectory": prop.trajectory, "color": "cyan", "label": "Dawn (LAMO)"}],
    central_body="ceres",
    backend="plotly",
)
# --8<-- [end:plot_3d]

# --8<-- [start:baseline_comparison]
# Quantify the perturbations by propagating a two-body (point-mass, no
# third-body, no SRP) baseline from the same initial state and comparing. The
# solar/Jovian third-body and SRP accelerations are small at a ~375 km, ~5.4 h
# LAMO orbit, so over 2 days (~9 revolutions) they perturb the trajectory by
# tens of meters rather than reshaping it -- but the divergence is measurable
# and grows with time, which a pure two-body run cannot reproduce.
baseline_config = bh.ForceModelConfig.for_body(
    ceres, bh.GravityConfiguration.point_mass()
)
baseline = bh.NumericalOrbitPropagator.builder(epoch, state0, baseline_config).build()
baseline.propagate_to(epoch + duration)

pos_divergence_m = np.array(
    [
        np.linalg.norm(prop.state_bci(epc)[:3] - baseline.state_bci(epc)[:3])
        for epc in epochs
    ]
)
vel_divergence_mps = np.array(
    [
        np.linalg.norm(prop.state_bci(epc)[3:] - baseline.state_bci(epc)[3:])
        for epc in epochs
    ]
)
max_divergence_m = pos_divergence_m.max()
print(
    f"\nMax perturbed-vs-two-body position divergence: {max_divergence_m:.2f} m "
    f"(0 for a two-body-only run)"
)
# --8<-- [end:baseline_comparison]

# --8<-- [start:plot_divergence]
# Perturbation signature: the perturbed run's position and velocity divergence
# from the two-body baseline, growing over the propagation. A pure two-body run
# would sit at zero; the growth is the solar/Jovian third-body and SRP signal.
import plotly.graph_objects as go

hours = np.arange(0.0, duration, dt) / 3600.0
fig_div = go.Figure()
fig_div.add_trace(
    go.Scatter(x=hours, y=pos_divergence_m, name="Position (m)", mode="lines")
)
fig_div.add_trace(
    go.Scatter(
        x=hours,
        y=vel_divergence_mps * 1e3,
        name="Velocity (mm/s)",
        mode="lines",
        yaxis="y2",
    )
)
fig_div.update_layout(
    title="Perturbed vs two-body divergence",
    xaxis_title="Time since epoch (hours)",
    yaxis={"title": "Position divergence (m)"},
    yaxis2={"title": "Velocity divergence (mm/s)", "overlaying": "y", "side": "right"},
    legend={"x": 0.02, "y": 0.98},
)
# --8<-- [end:plot_divergence]

# Validation
# Inclination relative to the Ceres spin pole confirms the orbit plane was
# built about the Ceres equator, not the ICRF pole. The perturbations barely
# tilt the plane over 2 days (a few 1e-5 deg), so the orbit stays polar; the
# measurable signature of the perturbations is the position divergence above.
incs_deg = []
for epc in epochs:
    x = prop.state_bci(epc)
    h = np.cross(x[:3], x[3:])
    h /= np.linalg.norm(h)
    incs_deg.append(np.degrees(np.arccos(np.clip(np.dot(h, ceres_pole), -1.0, 1.0))))
incs_deg = np.array(incs_deg)
max_excursion = np.max(np.abs(incs_deg - 90.0))
print(f"Inclination rel. Ceres pole: {incs_deg.min():.6f} to {incs_deg.max():.6f} deg")
print(f"Max excursion from 90 deg polar design: {max_excursion:.6f} deg")

# The perturbations move the trajectory measurably off the two-body baseline
# (they are active) while staying small over 2 days: the orbit remains polar to
# well under a hundredth of a degree and inside the LAMO altitude band, and the
# body-fixed state is finite.
print(
    f"\nPerturbations active: {max_divergence_m:.1f} m divergence from the "
    f"two-body baseline; orbit stays polar (excursion {max_excursion:.1e} deg) "
    f"and bounded ({radii_km.min():.1f}-{radii_km.max():.1f} km radius)."
)
# --8<-- [end:all]

# ============================================================================
# Plot Output Section (for documentation generation)
# ============================================================================

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "plots"))
from brahe_theme import save_themed_html

# Save themed figures
light_path, dark_path = save_themed_html(fig_3d, OUTDIR / f"{SCRIPT_NAME}_3d")
print(f"\n✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")

light_path_div, dark_path_div = save_themed_html(
    fig_div, OUTDIR / f"{SCRIPT_NAME}_divergence"
)
print(f"✓ Generated {light_path_div}")
print(f"✓ Generated {dark_path_div}")

print("\nDawn at Ceres Example Complete!")
```

## Propagation

Dawn's LAMO is a ~375 km circular polar orbit. The propagator integrates in a
Ceres-centered inertial frame whose axes are ICRF-aligned, so its z-axis is
the ICRF pole - about 23 degrees from Ceres's spin pole. We use
[`state_koe_to_inertial_for_body`](../library_api/coordinates/cartesian.md#brahe.coordinates.state_koe_to_inertial_for_body) to reference the elements to the body's mean
equator at J2000 and compute the state in the Ceres-centered, ICRF-aligned
inertial frame. Because `ceres` is a `CentralBody.Custom` that carries a
body-fixed frame (`ceres_fixed`), the function reads Ceres's pole from that
registered frame - the same recipe works for any user-defined body - so the
90 degree inclination is placed against Ceres's equator with no manual basis
construction:

```python
#!/usr/bin/env python
# /// script
# dependencies = ["brahe", "plotly", "numpy"]
# ///
"""
Dawn at Ceres: a user-defined rotating central body

This example demonstrates how to:
1. Resolve a small body (Ceres) in the JPL Small-Body Database (SBDB) to get
   its NAIF/SPK ID and SI physical parameters (GM, radius)
2. Fetch and load a targeted Ceres SPK from JPL Horizons so third-body and
   solar radiation pressure perturbations resolve around the body
3. Define a user-supplied central body (GM, radius, spin pole, prime meridian)
   and register a custom body-fixed frame from an IAU-style pole/prime-meridian
   rotation model
4. Propagate the Dawn spacecraft's LAMO (Low Altitude Mapping Orbit) around
   Ceres with point-mass gravity plus solar/Jovian third-body and solar
   radiation pressure perturbations
5. Report the body-fixed state through the custom frame and visualize the
   trajectory in 3D around a textured Ceres

Unlike Earth, the Moon, and Mars, Ceres has no built-in constants in brahe:
no built-in `CentralBody` variant, no named inertial/fixed frame pair, and no
spin model. Its gravitational parameter and radius are read from SBDB, while
its spin pole, prime meridian, and body-fixed frame - which SBDB does not
provide - are supplied by the user via `CentralBody.Custom` and
`register_custom_frame`. The same recipe applies to any body brahe doesn't
have built-in constants for: another dwarf planet, an asteroid, or a comet
nucleus.

NASA's Dawn spacecraft orbited Ceres from 2015 to 2018, spending much of its
final year in LAMO: a ~375 km, near-circular polar orbit used for its highest
resolution gravity and neutron/gamma-ray mapping. This example is inspired by
that LAMO phase rather than reproducing its exact mission parameters.

The propagator integrates in a Ceres-centered inertial frame whose axes are
ICRF-aligned: its z-axis is the ICRF pole, which sits ~23 deg from Ceres's
spin pole. An inclination passed straight to state_koe_to_eci would therefore
be measured against the wrong pole. Instead, state_koe_to_inertial_for_body
references the elements to Ceres's mean equator at J2000 -- and because Ceres
is a Custom body, it reads the pole from the user-registered body-fixed frame
-- so the 90 deg polar inclination is referenced to Ceres's equator as intended.
"""

# --8<-- [start:all]
# --8<-- [start:preamble]
import os
import pathlib
import sys

import numpy as np

import brahe as bh

# No `bh.initialize_eop()` call is needed here: this example never converts
# to or from Earth-relative frames, so it has no dependency on Earth
# orientation data. SPICE kernels are loaded below (de440s for Sun/Jupiter
# positions plus a Ceres SPK from Horizons) so that the third-body and solar
# radiation pressure perturbations resolve around Ceres.
# --8<-- [end:preamble]

# Configuration for output files
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# --8<-- [start:body_resolution]
# Resolve Ceres in the JPL Small-Body Database to get its NAIF/SPK ID and SI
# physical parameters, then generate and load a targeted SPK from Horizons so
# third-body and SRP perturbations resolve around Ceres. Both the SBDB query
# and the SPK are cached under the brahe cache directory and reused on repeat
# runs, so this hits the network only once per machine.
ceres_obj = bh.datasets.sbdb.SBDBClient().lookup("Ceres")
CERES_NAIF_ID = ceres_obj.naif_id()  # 20000001 (SBDB SPK-ID scheme)
GM_CERES = ceres_obj.gm  # m^3/s^2
R_CERES = ceres_obj.radius  # m
print(f"Ceres: {ceres_obj.full_name}, NAIF ID {CERES_NAIF_ID}")
print(f"  GM = {GM_CERES:.6e} m^3/s^2, radius = {R_CERES / 1e3:.1f} km")

# Load the common SPICE kernels (includes de440s) so Sun/Jupiter positions are
# available, then fetch and load a Ceres SPK covering the propagation span.
bh.load_common_spice_kernels()
spk_t0 = bh.Epoch.from_datetime(2015, 12, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.TDB)
spk_t1 = bh.Epoch.from_datetime(2016, 3, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.TDB)
spk = bh.datasets.horizons.HorizonsClient().get_spk(
    bh.datasets.horizons.HorizonsSPKRequest.for_spkid(CERES_NAIF_ID, spk_t0, spk_t1)
)
spk.load()
print(f"Loaded Ceres SPK: {spk.path}")
# --8<-- [end:body_resolution]

# --8<-- [start:body_definition]
# Ceres orientation model (IAU WGCCRE 2015 pole/rotation). SBDB does not
# supply spin-pole or prime-meridian constants, so they are set here:
CERES_POLE_RA = 291.418  # deg, ICRF right ascension of the spin pole
CERES_POLE_DEC = 66.764  # deg, ICRF declination of the spin pole
CERES_W0 = 170.650  # deg, prime meridian angle at J2000 TT
CERES_W_RATE = 952.1532635  # deg/day
# --8<-- [end:body_definition]

# --8<-- [start:body_fixed_frame]
# A body-fixed frame from the IAU-style pole/prime-meridian model, registered
# as a custom frame: rotation(epoch) -> ICRF-to-body DCM.
_J2000_TT_MJD = 51544.5


def ceres_rotation(epc):
    d = epc.mjd_as_time_system(bh.TimeSystem.TT) - _J2000_TT_MJD
    alpha = np.radians(CERES_POLE_RA)
    delta = np.radians(CERES_POLE_DEC)
    w = np.radians((CERES_W0 + CERES_W_RATE * d) % 360.0)
    return (
        bh.Rz(w, bh.AngleFormat.RADIANS)
        @ bh.Rx(np.pi / 2 - delta, bh.AngleFormat.RADIANS)
        @ bh.Rz(np.pi / 2 + alpha, bh.AngleFormat.RADIANS)
    )


def ceres_omega(epc=None):
    return np.array([0.0, 0.0, np.radians(CERES_W_RATE) / 86400.0])


# The `1` is an arbitrarily chosen registry key for this custom frame; it
# just needs to be unique among registered custom frames.
bh.register_custom_frame(1, ceres_rotation, ceres_omega)
ceres_fixed = bh.ReferenceFrame.BodyFixedCustom(CERES_NAIF_ID, 1)
# --8<-- [end:body_fixed_frame]

# --8<-- [start:force_model]
ceres = bh.CentralBody.Custom(
    "Ceres",
    CERES_NAIF_ID,
    GM_CERES,
    radius=R_CERES,
    omega=ceres_omega(),
    fixed_frame=ceres_fixed,
)

# With the Ceres SPK loaded, enable solar and Jovian third-body perturbations
# and solar radiation pressure. The Sun dominates the third-body signal at
# Ceres; Jupiter is added via the built-in `ThirdBody.JUPITER_BARYCENTER`. The
# occulting body for eclipse geometry is Ceres itself (an SRP shadow cast by
# Earth is meaningless 2.8 AU away), supplied as a Custom occulting body.
SPACECRAFT_MASS = 750.0  # kg (Dawn dry mass, approximate)
SRP_AREA = 20.0  # m^2 (solar-array-dominated cross section, approximate)
CR = 1.3  # reflectivity coefficient

srp = bh.SolarRadiationPressureConfiguration(
    area=bh.ParameterSource.value(SRP_AREA),
    cr=bh.ParameterSource.value(CR),
    eclipse_model=bh.EclipseModel.CONICAL,
    occulting_bodies=[
        bh.OccultingBody.Custom(name="Ceres", naif_id=CERES_NAIF_ID, radius=R_CERES)
    ],
)

force_config = bh.ForceModelConfig.for_body(
    ceres,
    bh.GravityConfiguration.point_mass(),
    srp=srp,
    third_body=[
        bh.ThirdBody.SUN,
        bh.ThirdBody.JUPITER_BARYCENTER,
    ],
    mass=bh.ParameterSource.value(SPACECRAFT_MASS),
)
# --8<-- [end:force_model]

# --8<-- [start:orbit_setup]
# Dawn LAMO (Low Altitude Mapping Orbit): ~375 km circular polar orbit.
epoch = bh.Epoch.from_datetime(2016, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)

oe = np.array(
    [R_CERES + 375e3, 0.001, 90.0, 0.0, 0.0, 0.0]
)  # [a [m], e [-], i [deg], RAAN [deg], argp [deg], M [deg]]

state0 = bh.state_koe_to_inertial_for_body(oe, ceres, bh.AngleFormat.DEGREES)

# Ceres spin pole (ICRF) from the IAU pole constants, used below to confirm the
# orbit geometry (declination / right ascension -> unit pole vector). This is
# the same pole the registered frame carries, evaluated directly here.
_pole_ra = np.radians(CERES_POLE_RA)
_pole_dec = np.radians(CERES_POLE_DEC)
ceres_pole = np.array(
    [
        np.cos(_pole_dec) * np.cos(_pole_ra),
        np.cos(_pole_dec) * np.sin(_pole_ra),
        np.sin(_pole_dec),
    ]
)

print(f"LAMO altitude: {(oe[0] - R_CERES) / 1e3:.1f} km, inclination: {oe[2]:.1f} deg")
print(f"Ceres spin pole (ICRF): {np.array2string(ceres_pole, precision=4)}")
# --8<-- [end:orbit_setup]

# --8<-- [start:propagation]
prop = bh.NumericalOrbitPropagator.builder(epoch, state0, force_config).build()
duration = 2 * 86400.0
print(f"\nPropagating {duration / 86400.0:.0f} days...")
prop.propagate_to(epoch + duration)
print("  Complete!")

# state_bci returns the propagator's native state in the central body's
# body-centered inertial frame (here, Ceres-centered) -- the frame the orbit
# was actually integrated in. state_eci would instead re-center the state onto
# Earth via SPK ephemeris (now possible since the Ceres SPK is loaded), which
# is not the frame we want here.
dt = 120.0
epochs = [epoch + t for t in np.arange(0.0, duration, dt)]
radii_km = np.array([np.linalg.norm(prop.state_bci(epc)[:3]) for epc in epochs]) / 1e3
print(f"\nMin radius: {radii_km.min():.2f} km, max radius: {radii_km.max():.2f} km")
print(f"(Ceres radius: {R_CERES / 1e3:.1f} km)")

# Body-fixed position through the registered frame:
x_fixed = prop.state_in_frame(ceres_fixed, epoch + duration)
print(
    f"\nBody-fixed state at t+{duration / 86400.0:.0f} d: {np.array2string(x_fixed, precision=1)}"
)
# --8<-- [end:propagation]

# --8<-- [start:plot_3d]
fig_3d = bh.plot_trajectory_3d(
    [{"trajectory": prop.trajectory, "color": "cyan", "label": "Dawn (LAMO)"}],
    central_body="ceres",
    backend="plotly",
)
# --8<-- [end:plot_3d]

# --8<-- [start:baseline_comparison]
# Quantify the perturbations by propagating a two-body (point-mass, no
# third-body, no SRP) baseline from the same initial state and comparing. The
# solar/Jovian third-body and SRP accelerations are small at a ~375 km, ~5.4 h
# LAMO orbit, so over 2 days (~9 revolutions) they perturb the trajectory by
# tens of meters rather than reshaping it -- but the divergence is measurable
# and grows with time, which a pure two-body run cannot reproduce.
baseline_config = bh.ForceModelConfig.for_body(
    ceres, bh.GravityConfiguration.point_mass()
)
baseline = bh.NumericalOrbitPropagator.builder(epoch, state0, baseline_config).build()
baseline.propagate_to(epoch + duration)

pos_divergence_m = np.array(
    [
        np.linalg.norm(prop.state_bci(epc)[:3] - baseline.state_bci(epc)[:3])
        for epc in epochs
    ]
)
vel_divergence_mps = np.array(
    [
        np.linalg.norm(prop.state_bci(epc)[3:] - baseline.state_bci(epc)[3:])
        for epc in epochs
    ]
)
max_divergence_m = pos_divergence_m.max()
print(
    f"\nMax perturbed-vs-two-body position divergence: {max_divergence_m:.2f} m "
    f"(0 for a two-body-only run)"
)
# --8<-- [end:baseline_comparison]

# --8<-- [start:plot_divergence]
# Perturbation signature: the perturbed run's position and velocity divergence
# from the two-body baseline, growing over the propagation. A pure two-body run
# would sit at zero; the growth is the solar/Jovian third-body and SRP signal.
import plotly.graph_objects as go

hours = np.arange(0.0, duration, dt) / 3600.0
fig_div = go.Figure()
fig_div.add_trace(
    go.Scatter(x=hours, y=pos_divergence_m, name="Position (m)", mode="lines")
)
fig_div.add_trace(
    go.Scatter(
        x=hours,
        y=vel_divergence_mps * 1e3,
        name="Velocity (mm/s)",
        mode="lines",
        yaxis="y2",
    )
)
fig_div.update_layout(
    title="Perturbed vs two-body divergence",
    xaxis_title="Time since epoch (hours)",
    yaxis={"title": "Position divergence (m)"},
    yaxis2={"title": "Velocity divergence (mm/s)", "overlaying": "y", "side": "right"},
    legend={"x": 0.02, "y": 0.98},
)
# --8<-- [end:plot_divergence]

# Validation
# Inclination relative to the Ceres spin pole confirms the orbit plane was
# built about the Ceres equator, not the ICRF pole. The perturbations barely
# tilt the plane over 2 days (a few 1e-5 deg), so the orbit stays polar; the
# measurable signature of the perturbations is the position divergence above.
incs_deg = []
for epc in epochs:
    x = prop.state_bci(epc)
    h = np.cross(x[:3], x[3:])
    h /= np.linalg.norm(h)
    incs_deg.append(np.degrees(np.arccos(np.clip(np.dot(h, ceres_pole), -1.0, 1.0))))
incs_deg = np.array(incs_deg)
max_excursion = np.max(np.abs(incs_deg - 90.0))
print(f"Inclination rel. Ceres pole: {incs_deg.min():.6f} to {incs_deg.max():.6f} deg")
print(f"Max excursion from 90 deg polar design: {max_excursion:.6f} deg")

# The perturbations move the trajectory measurably off the two-body baseline
# (they are active) while staying small over 2 days: the orbit remains polar to
# well under a hundredth of a degree and inside the LAMO altitude band, and the
# body-fixed state is finite.
print(
    f"\nPerturbations active: {max_divergence_m:.1f} m divergence from the "
    f"two-body baseline; orbit stays polar (excursion {max_excursion:.1e} deg) "
    f"and bounded ({radii_km.min():.1f}-{radii_km.max():.1f} km radius)."
)
# --8<-- [end:all]

# ============================================================================
# Plot Output Section (for documentation generation)
# ============================================================================

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "plots"))
from brahe_theme import save_themed_html

# Save themed figures
light_path, dark_path = save_themed_html(fig_3d, OUTDIR / f"{SCRIPT_NAME}_3d")
print(f"\n✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")

light_path_div, dark_path_div = save_themed_html(
    fig_div, OUTDIR / f"{SCRIPT_NAME}_divergence"
)
print(f"✓ Generated {light_path_div}")
print(f"✓ Generated {dark_path_div}")

print("\nDawn at Ceres Example Complete!")
```

```python
#!/usr/bin/env python
# /// script
# dependencies = ["brahe", "plotly", "numpy"]
# ///
"""
Dawn at Ceres: a user-defined rotating central body

This example demonstrates how to:
1. Resolve a small body (Ceres) in the JPL Small-Body Database (SBDB) to get
   its NAIF/SPK ID and SI physical parameters (GM, radius)
2. Fetch and load a targeted Ceres SPK from JPL Horizons so third-body and
   solar radiation pressure perturbations resolve around the body
3. Define a user-supplied central body (GM, radius, spin pole, prime meridian)
   and register a custom body-fixed frame from an IAU-style pole/prime-meridian
   rotation model
4. Propagate the Dawn spacecraft's LAMO (Low Altitude Mapping Orbit) around
   Ceres with point-mass gravity plus solar/Jovian third-body and solar
   radiation pressure perturbations
5. Report the body-fixed state through the custom frame and visualize the
   trajectory in 3D around a textured Ceres

Unlike Earth, the Moon, and Mars, Ceres has no built-in constants in brahe:
no built-in `CentralBody` variant, no named inertial/fixed frame pair, and no
spin model. Its gravitational parameter and radius are read from SBDB, while
its spin pole, prime meridian, and body-fixed frame - which SBDB does not
provide - are supplied by the user via `CentralBody.Custom` and
`register_custom_frame`. The same recipe applies to any body brahe doesn't
have built-in constants for: another dwarf planet, an asteroid, or a comet
nucleus.

NASA's Dawn spacecraft orbited Ceres from 2015 to 2018, spending much of its
final year in LAMO: a ~375 km, near-circular polar orbit used for its highest
resolution gravity and neutron/gamma-ray mapping. This example is inspired by
that LAMO phase rather than reproducing its exact mission parameters.

The propagator integrates in a Ceres-centered inertial frame whose axes are
ICRF-aligned: its z-axis is the ICRF pole, which sits ~23 deg from Ceres's
spin pole. An inclination passed straight to state_koe_to_eci would therefore
be measured against the wrong pole. Instead, state_koe_to_inertial_for_body
references the elements to Ceres's mean equator at J2000 -- and because Ceres
is a Custom body, it reads the pole from the user-registered body-fixed frame
-- so the 90 deg polar inclination is referenced to Ceres's equator as intended.
"""

# --8<-- [start:all]
# --8<-- [start:preamble]
import os
import pathlib
import sys

import numpy as np

import brahe as bh

# No `bh.initialize_eop()` call is needed here: this example never converts
# to or from Earth-relative frames, so it has no dependency on Earth
# orientation data. SPICE kernels are loaded below (de440s for Sun/Jupiter
# positions plus a Ceres SPK from Horizons) so that the third-body and solar
# radiation pressure perturbations resolve around Ceres.
# --8<-- [end:preamble]

# Configuration for output files
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# --8<-- [start:body_resolution]
# Resolve Ceres in the JPL Small-Body Database to get its NAIF/SPK ID and SI
# physical parameters, then generate and load a targeted SPK from Horizons so
# third-body and SRP perturbations resolve around Ceres. Both the SBDB query
# and the SPK are cached under the brahe cache directory and reused on repeat
# runs, so this hits the network only once per machine.
ceres_obj = bh.datasets.sbdb.SBDBClient().lookup("Ceres")
CERES_NAIF_ID = ceres_obj.naif_id()  # 20000001 (SBDB SPK-ID scheme)
GM_CERES = ceres_obj.gm  # m^3/s^2
R_CERES = ceres_obj.radius  # m
print(f"Ceres: {ceres_obj.full_name}, NAIF ID {CERES_NAIF_ID}")
print(f"  GM = {GM_CERES:.6e} m^3/s^2, radius = {R_CERES / 1e3:.1f} km")

# Load the common SPICE kernels (includes de440s) so Sun/Jupiter positions are
# available, then fetch and load a Ceres SPK covering the propagation span.
bh.load_common_spice_kernels()
spk_t0 = bh.Epoch.from_datetime(2015, 12, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.TDB)
spk_t1 = bh.Epoch.from_datetime(2016, 3, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.TDB)
spk = bh.datasets.horizons.HorizonsClient().get_spk(
    bh.datasets.horizons.HorizonsSPKRequest.for_spkid(CERES_NAIF_ID, spk_t0, spk_t1)
)
spk.load()
print(f"Loaded Ceres SPK: {spk.path}")
# --8<-- [end:body_resolution]

# --8<-- [start:body_definition]
# Ceres orientation model (IAU WGCCRE 2015 pole/rotation). SBDB does not
# supply spin-pole or prime-meridian constants, so they are set here:
CERES_POLE_RA = 291.418  # deg, ICRF right ascension of the spin pole
CERES_POLE_DEC = 66.764  # deg, ICRF declination of the spin pole
CERES_W0 = 170.650  # deg, prime meridian angle at J2000 TT
CERES_W_RATE = 952.1532635  # deg/day
# --8<-- [end:body_definition]

# --8<-- [start:body_fixed_frame]
# A body-fixed frame from the IAU-style pole/prime-meridian model, registered
# as a custom frame: rotation(epoch) -> ICRF-to-body DCM.
_J2000_TT_MJD = 51544.5


def ceres_rotation(epc):
    d = epc.mjd_as_time_system(bh.TimeSystem.TT) - _J2000_TT_MJD
    alpha = np.radians(CERES_POLE_RA)
    delta = np.radians(CERES_POLE_DEC)
    w = np.radians((CERES_W0 + CERES_W_RATE * d) % 360.0)
    return (
        bh.Rz(w, bh.AngleFormat.RADIANS)
        @ bh.Rx(np.pi / 2 - delta, bh.AngleFormat.RADIANS)
        @ bh.Rz(np.pi / 2 + alpha, bh.AngleFormat.RADIANS)
    )


def ceres_omega(epc=None):
    return np.array([0.0, 0.0, np.radians(CERES_W_RATE) / 86400.0])


# The `1` is an arbitrarily chosen registry key for this custom frame; it
# just needs to be unique among registered custom frames.
bh.register_custom_frame(1, ceres_rotation, ceres_omega)
ceres_fixed = bh.ReferenceFrame.BodyFixedCustom(CERES_NAIF_ID, 1)
# --8<-- [end:body_fixed_frame]

# --8<-- [start:force_model]
ceres = bh.CentralBody.Custom(
    "Ceres",
    CERES_NAIF_ID,
    GM_CERES,
    radius=R_CERES,
    omega=ceres_omega(),
    fixed_frame=ceres_fixed,
)

# With the Ceres SPK loaded, enable solar and Jovian third-body perturbations
# and solar radiation pressure. The Sun dominates the third-body signal at
# Ceres; Jupiter is added via the built-in `ThirdBody.JUPITER_BARYCENTER`. The
# occulting body for eclipse geometry is Ceres itself (an SRP shadow cast by
# Earth is meaningless 2.8 AU away), supplied as a Custom occulting body.
SPACECRAFT_MASS = 750.0  # kg (Dawn dry mass, approximate)
SRP_AREA = 20.0  # m^2 (solar-array-dominated cross section, approximate)
CR = 1.3  # reflectivity coefficient

srp = bh.SolarRadiationPressureConfiguration(
    area=bh.ParameterSource.value(SRP_AREA),
    cr=bh.ParameterSource.value(CR),
    eclipse_model=bh.EclipseModel.CONICAL,
    occulting_bodies=[
        bh.OccultingBody.Custom(name="Ceres", naif_id=CERES_NAIF_ID, radius=R_CERES)
    ],
)

force_config = bh.ForceModelConfig.for_body(
    ceres,
    bh.GravityConfiguration.point_mass(),
    srp=srp,
    third_body=[
        bh.ThirdBody.SUN,
        bh.ThirdBody.JUPITER_BARYCENTER,
    ],
    mass=bh.ParameterSource.value(SPACECRAFT_MASS),
)
# --8<-- [end:force_model]

# --8<-- [start:orbit_setup]
# Dawn LAMO (Low Altitude Mapping Orbit): ~375 km circular polar orbit.
epoch = bh.Epoch.from_datetime(2016, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)

oe = np.array(
    [R_CERES + 375e3, 0.001, 90.0, 0.0, 0.0, 0.0]
)  # [a [m], e [-], i [deg], RAAN [deg], argp [deg], M [deg]]

state0 = bh.state_koe_to_inertial_for_body(oe, ceres, bh.AngleFormat.DEGREES)

# Ceres spin pole (ICRF) from the IAU pole constants, used below to confirm the
# orbit geometry (declination / right ascension -> unit pole vector). This is
# the same pole the registered frame carries, evaluated directly here.
_pole_ra = np.radians(CERES_POLE_RA)
_pole_dec = np.radians(CERES_POLE_DEC)
ceres_pole = np.array(
    [
        np.cos(_pole_dec) * np.cos(_pole_ra),
        np.cos(_pole_dec) * np.sin(_pole_ra),
        np.sin(_pole_dec),
    ]
)

print(f"LAMO altitude: {(oe[0] - R_CERES) / 1e3:.1f} km, inclination: {oe[2]:.1f} deg")
print(f"Ceres spin pole (ICRF): {np.array2string(ceres_pole, precision=4)}")
# --8<-- [end:orbit_setup]

# --8<-- [start:propagation]
prop = bh.NumericalOrbitPropagator.builder(epoch, state0, force_config).build()
duration = 2 * 86400.0
print(f"\nPropagating {duration / 86400.0:.0f} days...")
prop.propagate_to(epoch + duration)
print("  Complete!")

# state_bci returns the propagator's native state in the central body's
# body-centered inertial frame (here, Ceres-centered) -- the frame the orbit
# was actually integrated in. state_eci would instead re-center the state onto
# Earth via SPK ephemeris (now possible since the Ceres SPK is loaded), which
# is not the frame we want here.
dt = 120.0
epochs = [epoch + t for t in np.arange(0.0, duration, dt)]
radii_km = np.array([np.linalg.norm(prop.state_bci(epc)[:3]) for epc in epochs]) / 1e3
print(f"\nMin radius: {radii_km.min():.2f} km, max radius: {radii_km.max():.2f} km")
print(f"(Ceres radius: {R_CERES / 1e3:.1f} km)")

# Body-fixed position through the registered frame:
x_fixed = prop.state_in_frame(ceres_fixed, epoch + duration)
print(
    f"\nBody-fixed state at t+{duration / 86400.0:.0f} d: {np.array2string(x_fixed, precision=1)}"
)
# --8<-- [end:propagation]

# --8<-- [start:plot_3d]
fig_3d = bh.plot_trajectory_3d(
    [{"trajectory": prop.trajectory, "color": "cyan", "label": "Dawn (LAMO)"}],
    central_body="ceres",
    backend="plotly",
)
# --8<-- [end:plot_3d]

# --8<-- [start:baseline_comparison]
# Quantify the perturbations by propagating a two-body (point-mass, no
# third-body, no SRP) baseline from the same initial state and comparing. The
# solar/Jovian third-body and SRP accelerations are small at a ~375 km, ~5.4 h
# LAMO orbit, so over 2 days (~9 revolutions) they perturb the trajectory by
# tens of meters rather than reshaping it -- but the divergence is measurable
# and grows with time, which a pure two-body run cannot reproduce.
baseline_config = bh.ForceModelConfig.for_body(
    ceres, bh.GravityConfiguration.point_mass()
)
baseline = bh.NumericalOrbitPropagator.builder(epoch, state0, baseline_config).build()
baseline.propagate_to(epoch + duration)

pos_divergence_m = np.array(
    [
        np.linalg.norm(prop.state_bci(epc)[:3] - baseline.state_bci(epc)[:3])
        for epc in epochs
    ]
)
vel_divergence_mps = np.array(
    [
        np.linalg.norm(prop.state_bci(epc)[3:] - baseline.state_bci(epc)[3:])
        for epc in epochs
    ]
)
max_divergence_m = pos_divergence_m.max()
print(
    f"\nMax perturbed-vs-two-body position divergence: {max_divergence_m:.2f} m "
    f"(0 for a two-body-only run)"
)
# --8<-- [end:baseline_comparison]

# --8<-- [start:plot_divergence]
# Perturbation signature: the perturbed run's position and velocity divergence
# from the two-body baseline, growing over the propagation. A pure two-body run
# would sit at zero; the growth is the solar/Jovian third-body and SRP signal.
import plotly.graph_objects as go

hours = np.arange(0.0, duration, dt) / 3600.0
fig_div = go.Figure()
fig_div.add_trace(
    go.Scatter(x=hours, y=pos_divergence_m, name="Position (m)", mode="lines")
)
fig_div.add_trace(
    go.Scatter(
        x=hours,
        y=vel_divergence_mps * 1e3,
        name="Velocity (mm/s)",
        mode="lines",
        yaxis="y2",
    )
)
fig_div.update_layout(
    title="Perturbed vs two-body divergence",
    xaxis_title="Time since epoch (hours)",
    yaxis={"title": "Position divergence (m)"},
    yaxis2={"title": "Velocity divergence (mm/s)", "overlaying": "y", "side": "right"},
    legend={"x": 0.02, "y": 0.98},
)
# --8<-- [end:plot_divergence]

# Validation
# Inclination relative to the Ceres spin pole confirms the orbit plane was
# built about the Ceres equator, not the ICRF pole. The perturbations barely
# tilt the plane over 2 days (a few 1e-5 deg), so the orbit stays polar; the
# measurable signature of the perturbations is the position divergence above.
incs_deg = []
for epc in epochs:
    x = prop.state_bci(epc)
    h = np.cross(x[:3], x[3:])
    h /= np.linalg.norm(h)
    incs_deg.append(np.degrees(np.arccos(np.clip(np.dot(h, ceres_pole), -1.0, 1.0))))
incs_deg = np.array(incs_deg)
max_excursion = np.max(np.abs(incs_deg - 90.0))
print(f"Inclination rel. Ceres pole: {incs_deg.min():.6f} to {incs_deg.max():.6f} deg")
print(f"Max excursion from 90 deg polar design: {max_excursion:.6f} deg")

# The perturbations move the trajectory measurably off the two-body baseline
# (they are active) while staying small over 2 days: the orbit remains polar to
# well under a hundredth of a degree and inside the LAMO altitude band, and the
# body-fixed state is finite.
print(
    f"\nPerturbations active: {max_divergence_m:.1f} m divergence from the "
    f"two-body baseline; orbit stays polar (excursion {max_excursion:.1e} deg) "
    f"and bounded ({radii_km.min():.1f}-{radii_km.max():.1f} km radius)."
)
# --8<-- [end:all]

# ============================================================================
# Plot Output Section (for documentation generation)
# ============================================================================

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "plots"))
from brahe_theme import save_themed_html

# Save themed figures
light_path, dark_path = save_themed_html(fig_3d, OUTDIR / f"{SCRIPT_NAME}_3d")
print(f"\n✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")

light_path_div, dark_path_div = save_themed_html(
    fig_div, OUTDIR / f"{SCRIPT_NAME}_divergence"
)
print(f"✓ Generated {light_path_div}")
print(f"✓ Generated {dark_path_div}")

print("\nDawn at Ceres Example Complete!")
```

[`state_bci`](../library_api/propagators/numerical_orbit_propagator.md#brahe.NumericalOrbitPropagator.state_bci) returns the propagator's native state in the central
body's body-centered inertial frame - here, Ceres-centered - the frame the
orbit is actually integrated in. Sampling it over the 2-day propagation
confirms the orbit stays in a tight band around the design altitude.
`state_eci` would instead re-center the state onto Earth via SPK ephemeris -
which now resolves, since the Ceres SPK is loaded - but that isn't the frame
wanted here. [`state_in_frame`](../library_api/propagators/numerical_orbit_propagator.md#brahe.NumericalOrbitPropagator.state_in_frame) converts the
final inertial state directly into the registered Ceres-fixed frame - the
same frame-router entry point used for the built-in `ITRF`/`LFPA`/`MCMF`
frames, but backed entirely by the callbacks registered above.

## Two-Body Baseline Comparison

To confirm the third-body and SRP perturbations are actually doing something
- rather than just adding integration noise - a second propagator is built
from the same initial state with a two-body (point-mass, no third-body, no
SRP) force model, and the two trajectories are compared over the same span:

```python
#!/usr/bin/env python
# /// script
# dependencies = ["brahe", "plotly", "numpy"]
# ///
"""
Dawn at Ceres: a user-defined rotating central body

This example demonstrates how to:
1. Resolve a small body (Ceres) in the JPL Small-Body Database (SBDB) to get
   its NAIF/SPK ID and SI physical parameters (GM, radius)
2. Fetch and load a targeted Ceres SPK from JPL Horizons so third-body and
   solar radiation pressure perturbations resolve around the body
3. Define a user-supplied central body (GM, radius, spin pole, prime meridian)
   and register a custom body-fixed frame from an IAU-style pole/prime-meridian
   rotation model
4. Propagate the Dawn spacecraft's LAMO (Low Altitude Mapping Orbit) around
   Ceres with point-mass gravity plus solar/Jovian third-body and solar
   radiation pressure perturbations
5. Report the body-fixed state through the custom frame and visualize the
   trajectory in 3D around a textured Ceres

Unlike Earth, the Moon, and Mars, Ceres has no built-in constants in brahe:
no built-in `CentralBody` variant, no named inertial/fixed frame pair, and no
spin model. Its gravitational parameter and radius are read from SBDB, while
its spin pole, prime meridian, and body-fixed frame - which SBDB does not
provide - are supplied by the user via `CentralBody.Custom` and
`register_custom_frame`. The same recipe applies to any body brahe doesn't
have built-in constants for: another dwarf planet, an asteroid, or a comet
nucleus.

NASA's Dawn spacecraft orbited Ceres from 2015 to 2018, spending much of its
final year in LAMO: a ~375 km, near-circular polar orbit used for its highest
resolution gravity and neutron/gamma-ray mapping. This example is inspired by
that LAMO phase rather than reproducing its exact mission parameters.

The propagator integrates in a Ceres-centered inertial frame whose axes are
ICRF-aligned: its z-axis is the ICRF pole, which sits ~23 deg from Ceres's
spin pole. An inclination passed straight to state_koe_to_eci would therefore
be measured against the wrong pole. Instead, state_koe_to_inertial_for_body
references the elements to Ceres's mean equator at J2000 -- and because Ceres
is a Custom body, it reads the pole from the user-registered body-fixed frame
-- so the 90 deg polar inclination is referenced to Ceres's equator as intended.
"""

# --8<-- [start:all]
# --8<-- [start:preamble]
import os
import pathlib
import sys

import numpy as np

import brahe as bh

# No `bh.initialize_eop()` call is needed here: this example never converts
# to or from Earth-relative frames, so it has no dependency on Earth
# orientation data. SPICE kernels are loaded below (de440s for Sun/Jupiter
# positions plus a Ceres SPK from Horizons) so that the third-body and solar
# radiation pressure perturbations resolve around Ceres.
# --8<-- [end:preamble]

# Configuration for output files
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# --8<-- [start:body_resolution]
# Resolve Ceres in the JPL Small-Body Database to get its NAIF/SPK ID and SI
# physical parameters, then generate and load a targeted SPK from Horizons so
# third-body and SRP perturbations resolve around Ceres. Both the SBDB query
# and the SPK are cached under the brahe cache directory and reused on repeat
# runs, so this hits the network only once per machine.
ceres_obj = bh.datasets.sbdb.SBDBClient().lookup("Ceres")
CERES_NAIF_ID = ceres_obj.naif_id()  # 20000001 (SBDB SPK-ID scheme)
GM_CERES = ceres_obj.gm  # m^3/s^2
R_CERES = ceres_obj.radius  # m
print(f"Ceres: {ceres_obj.full_name}, NAIF ID {CERES_NAIF_ID}")
print(f"  GM = {GM_CERES:.6e} m^3/s^2, radius = {R_CERES / 1e3:.1f} km")

# Load the common SPICE kernels (includes de440s) so Sun/Jupiter positions are
# available, then fetch and load a Ceres SPK covering the propagation span.
bh.load_common_spice_kernels()
spk_t0 = bh.Epoch.from_datetime(2015, 12, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.TDB)
spk_t1 = bh.Epoch.from_datetime(2016, 3, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.TDB)
spk = bh.datasets.horizons.HorizonsClient().get_spk(
    bh.datasets.horizons.HorizonsSPKRequest.for_spkid(CERES_NAIF_ID, spk_t0, spk_t1)
)
spk.load()
print(f"Loaded Ceres SPK: {spk.path}")
# --8<-- [end:body_resolution]

# --8<-- [start:body_definition]
# Ceres orientation model (IAU WGCCRE 2015 pole/rotation). SBDB does not
# supply spin-pole or prime-meridian constants, so they are set here:
CERES_POLE_RA = 291.418  # deg, ICRF right ascension of the spin pole
CERES_POLE_DEC = 66.764  # deg, ICRF declination of the spin pole
CERES_W0 = 170.650  # deg, prime meridian angle at J2000 TT
CERES_W_RATE = 952.1532635  # deg/day
# --8<-- [end:body_definition]

# --8<-- [start:body_fixed_frame]
# A body-fixed frame from the IAU-style pole/prime-meridian model, registered
# as a custom frame: rotation(epoch) -> ICRF-to-body DCM.
_J2000_TT_MJD = 51544.5


def ceres_rotation(epc):
    d = epc.mjd_as_time_system(bh.TimeSystem.TT) - _J2000_TT_MJD
    alpha = np.radians(CERES_POLE_RA)
    delta = np.radians(CERES_POLE_DEC)
    w = np.radians((CERES_W0 + CERES_W_RATE * d) % 360.0)
    return (
        bh.Rz(w, bh.AngleFormat.RADIANS)
        @ bh.Rx(np.pi / 2 - delta, bh.AngleFormat.RADIANS)
        @ bh.Rz(np.pi / 2 + alpha, bh.AngleFormat.RADIANS)
    )


def ceres_omega(epc=None):
    return np.array([0.0, 0.0, np.radians(CERES_W_RATE) / 86400.0])


# The `1` is an arbitrarily chosen registry key for this custom frame; it
# just needs to be unique among registered custom frames.
bh.register_custom_frame(1, ceres_rotation, ceres_omega)
ceres_fixed = bh.ReferenceFrame.BodyFixedCustom(CERES_NAIF_ID, 1)
# --8<-- [end:body_fixed_frame]

# --8<-- [start:force_model]
ceres = bh.CentralBody.Custom(
    "Ceres",
    CERES_NAIF_ID,
    GM_CERES,
    radius=R_CERES,
    omega=ceres_omega(),
    fixed_frame=ceres_fixed,
)

# With the Ceres SPK loaded, enable solar and Jovian third-body perturbations
# and solar radiation pressure. The Sun dominates the third-body signal at
# Ceres; Jupiter is added via the built-in `ThirdBody.JUPITER_BARYCENTER`. The
# occulting body for eclipse geometry is Ceres itself (an SRP shadow cast by
# Earth is meaningless 2.8 AU away), supplied as a Custom occulting body.
SPACECRAFT_MASS = 750.0  # kg (Dawn dry mass, approximate)
SRP_AREA = 20.0  # m^2 (solar-array-dominated cross section, approximate)
CR = 1.3  # reflectivity coefficient

srp = bh.SolarRadiationPressureConfiguration(
    area=bh.ParameterSource.value(SRP_AREA),
    cr=bh.ParameterSource.value(CR),
    eclipse_model=bh.EclipseModel.CONICAL,
    occulting_bodies=[
        bh.OccultingBody.Custom(name="Ceres", naif_id=CERES_NAIF_ID, radius=R_CERES)
    ],
)

force_config = bh.ForceModelConfig.for_body(
    ceres,
    bh.GravityConfiguration.point_mass(),
    srp=srp,
    third_body=[
        bh.ThirdBody.SUN,
        bh.ThirdBody.JUPITER_BARYCENTER,
    ],
    mass=bh.ParameterSource.value(SPACECRAFT_MASS),
)
# --8<-- [end:force_model]

# --8<-- [start:orbit_setup]
# Dawn LAMO (Low Altitude Mapping Orbit): ~375 km circular polar orbit.
epoch = bh.Epoch.from_datetime(2016, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)

oe = np.array(
    [R_CERES + 375e3, 0.001, 90.0, 0.0, 0.0, 0.0]
)  # [a [m], e [-], i [deg], RAAN [deg], argp [deg], M [deg]]

state0 = bh.state_koe_to_inertial_for_body(oe, ceres, bh.AngleFormat.DEGREES)

# Ceres spin pole (ICRF) from the IAU pole constants, used below to confirm the
# orbit geometry (declination / right ascension -> unit pole vector). This is
# the same pole the registered frame carries, evaluated directly here.
_pole_ra = np.radians(CERES_POLE_RA)
_pole_dec = np.radians(CERES_POLE_DEC)
ceres_pole = np.array(
    [
        np.cos(_pole_dec) * np.cos(_pole_ra),
        np.cos(_pole_dec) * np.sin(_pole_ra),
        np.sin(_pole_dec),
    ]
)

print(f"LAMO altitude: {(oe[0] - R_CERES) / 1e3:.1f} km, inclination: {oe[2]:.1f} deg")
print(f"Ceres spin pole (ICRF): {np.array2string(ceres_pole, precision=4)}")
# --8<-- [end:orbit_setup]

# --8<-- [start:propagation]
prop = bh.NumericalOrbitPropagator.builder(epoch, state0, force_config).build()
duration = 2 * 86400.0
print(f"\nPropagating {duration / 86400.0:.0f} days...")
prop.propagate_to(epoch + duration)
print("  Complete!")

# state_bci returns the propagator's native state in the central body's
# body-centered inertial frame (here, Ceres-centered) -- the frame the orbit
# was actually integrated in. state_eci would instead re-center the state onto
# Earth via SPK ephemeris (now possible since the Ceres SPK is loaded), which
# is not the frame we want here.
dt = 120.0
epochs = [epoch + t for t in np.arange(0.0, duration, dt)]
radii_km = np.array([np.linalg.norm(prop.state_bci(epc)[:3]) for epc in epochs]) / 1e3
print(f"\nMin radius: {radii_km.min():.2f} km, max radius: {radii_km.max():.2f} km")
print(f"(Ceres radius: {R_CERES / 1e3:.1f} km)")

# Body-fixed position through the registered frame:
x_fixed = prop.state_in_frame(ceres_fixed, epoch + duration)
print(
    f"\nBody-fixed state at t+{duration / 86400.0:.0f} d: {np.array2string(x_fixed, precision=1)}"
)
# --8<-- [end:propagation]

# --8<-- [start:plot_3d]
fig_3d = bh.plot_trajectory_3d(
    [{"trajectory": prop.trajectory, "color": "cyan", "label": "Dawn (LAMO)"}],
    central_body="ceres",
    backend="plotly",
)
# --8<-- [end:plot_3d]

# --8<-- [start:baseline_comparison]
# Quantify the perturbations by propagating a two-body (point-mass, no
# third-body, no SRP) baseline from the same initial state and comparing. The
# solar/Jovian third-body and SRP accelerations are small at a ~375 km, ~5.4 h
# LAMO orbit, so over 2 days (~9 revolutions) they perturb the trajectory by
# tens of meters rather than reshaping it -- but the divergence is measurable
# and grows with time, which a pure two-body run cannot reproduce.
baseline_config = bh.ForceModelConfig.for_body(
    ceres, bh.GravityConfiguration.point_mass()
)
baseline = bh.NumericalOrbitPropagator.builder(epoch, state0, baseline_config).build()
baseline.propagate_to(epoch + duration)

pos_divergence_m = np.array(
    [
        np.linalg.norm(prop.state_bci(epc)[:3] - baseline.state_bci(epc)[:3])
        for epc in epochs
    ]
)
vel_divergence_mps = np.array(
    [
        np.linalg.norm(prop.state_bci(epc)[3:] - baseline.state_bci(epc)[3:])
        for epc in epochs
    ]
)
max_divergence_m = pos_divergence_m.max()
print(
    f"\nMax perturbed-vs-two-body position divergence: {max_divergence_m:.2f} m "
    f"(0 for a two-body-only run)"
)
# --8<-- [end:baseline_comparison]

# --8<-- [start:plot_divergence]
# Perturbation signature: the perturbed run's position and velocity divergence
# from the two-body baseline, growing over the propagation. A pure two-body run
# would sit at zero; the growth is the solar/Jovian third-body and SRP signal.
import plotly.graph_objects as go

hours = np.arange(0.0, duration, dt) / 3600.0
fig_div = go.Figure()
fig_div.add_trace(
    go.Scatter(x=hours, y=pos_divergence_m, name="Position (m)", mode="lines")
)
fig_div.add_trace(
    go.Scatter(
        x=hours,
        y=vel_divergence_mps * 1e3,
        name="Velocity (mm/s)",
        mode="lines",
        yaxis="y2",
    )
)
fig_div.update_layout(
    title="Perturbed vs two-body divergence",
    xaxis_title="Time since epoch (hours)",
    yaxis={"title": "Position divergence (m)"},
    yaxis2={"title": "Velocity divergence (mm/s)", "overlaying": "y", "side": "right"},
    legend={"x": 0.02, "y": 0.98},
)
# --8<-- [end:plot_divergence]

# Validation
# Inclination relative to the Ceres spin pole confirms the orbit plane was
# built about the Ceres equator, not the ICRF pole. The perturbations barely
# tilt the plane over 2 days (a few 1e-5 deg), so the orbit stays polar; the
# measurable signature of the perturbations is the position divergence above.
incs_deg = []
for epc in epochs:
    x = prop.state_bci(epc)
    h = np.cross(x[:3], x[3:])
    h /= np.linalg.norm(h)
    incs_deg.append(np.degrees(np.arccos(np.clip(np.dot(h, ceres_pole), -1.0, 1.0))))
incs_deg = np.array(incs_deg)
max_excursion = np.max(np.abs(incs_deg - 90.0))
print(f"Inclination rel. Ceres pole: {incs_deg.min():.6f} to {incs_deg.max():.6f} deg")
print(f"Max excursion from 90 deg polar design: {max_excursion:.6f} deg")

# The perturbations move the trajectory measurably off the two-body baseline
# (they are active) while staying small over 2 days: the orbit remains polar to
# well under a hundredth of a degree and inside the LAMO altitude band, and the
# body-fixed state is finite.
print(
    f"\nPerturbations active: {max_divergence_m:.1f} m divergence from the "
    f"two-body baseline; orbit stays polar (excursion {max_excursion:.1e} deg) "
    f"and bounded ({radii_km.min():.1f}-{radii_km.max():.1f} km radius)."
)
# --8<-- [end:all]

# ============================================================================
# Plot Output Section (for documentation generation)
# ============================================================================

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "plots"))
from brahe_theme import save_themed_html

# Save themed figures
light_path, dark_path = save_themed_html(fig_3d, OUTDIR / f"{SCRIPT_NAME}_3d")
print(f"\n✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")

light_path_div, dark_path_div = save_themed_html(
    fig_div, OUTDIR / f"{SCRIPT_NAME}_divergence"
)
print(f"✓ Generated {light_path_div}")
print(f"✓ Generated {dark_path_div}")

print("\nDawn at Ceres Example Complete!")
```

At a ~375 km, ~5.4-hour LAMO orbit, the solar and Jovian third-body
accelerations and SRP are small enough that they perturb the trajectory by
tens of meters over 2 days (~9 revolutions) rather than reshaping it, but the
divergence from the two-body baseline is measurable and grows with time - a
signature a pure two-body run cannot reproduce.

Plotting the position and velocity difference between the two runs over the
propagation shows this divergence accumulating from zero:

```python
#!/usr/bin/env python
# /// script
# dependencies = ["brahe", "plotly", "numpy"]
# ///
"""
Dawn at Ceres: a user-defined rotating central body

This example demonstrates how to:
1. Resolve a small body (Ceres) in the JPL Small-Body Database (SBDB) to get
   its NAIF/SPK ID and SI physical parameters (GM, radius)
2. Fetch and load a targeted Ceres SPK from JPL Horizons so third-body and
   solar radiation pressure perturbations resolve around the body
3. Define a user-supplied central body (GM, radius, spin pole, prime meridian)
   and register a custom body-fixed frame from an IAU-style pole/prime-meridian
   rotation model
4. Propagate the Dawn spacecraft's LAMO (Low Altitude Mapping Orbit) around
   Ceres with point-mass gravity plus solar/Jovian third-body and solar
   radiation pressure perturbations
5. Report the body-fixed state through the custom frame and visualize the
   trajectory in 3D around a textured Ceres

Unlike Earth, the Moon, and Mars, Ceres has no built-in constants in brahe:
no built-in `CentralBody` variant, no named inertial/fixed frame pair, and no
spin model. Its gravitational parameter and radius are read from SBDB, while
its spin pole, prime meridian, and body-fixed frame - which SBDB does not
provide - are supplied by the user via `CentralBody.Custom` and
`register_custom_frame`. The same recipe applies to any body brahe doesn't
have built-in constants for: another dwarf planet, an asteroid, or a comet
nucleus.

NASA's Dawn spacecraft orbited Ceres from 2015 to 2018, spending much of its
final year in LAMO: a ~375 km, near-circular polar orbit used for its highest
resolution gravity and neutron/gamma-ray mapping. This example is inspired by
that LAMO phase rather than reproducing its exact mission parameters.

The propagator integrates in a Ceres-centered inertial frame whose axes are
ICRF-aligned: its z-axis is the ICRF pole, which sits ~23 deg from Ceres's
spin pole. An inclination passed straight to state_koe_to_eci would therefore
be measured against the wrong pole. Instead, state_koe_to_inertial_for_body
references the elements to Ceres's mean equator at J2000 -- and because Ceres
is a Custom body, it reads the pole from the user-registered body-fixed frame
-- so the 90 deg polar inclination is referenced to Ceres's equator as intended.
"""

# --8<-- [start:all]
# --8<-- [start:preamble]
import os
import pathlib
import sys

import numpy as np

import brahe as bh

# No `bh.initialize_eop()` call is needed here: this example never converts
# to or from Earth-relative frames, so it has no dependency on Earth
# orientation data. SPICE kernels are loaded below (de440s for Sun/Jupiter
# positions plus a Ceres SPK from Horizons) so that the third-body and solar
# radiation pressure perturbations resolve around Ceres.
# --8<-- [end:preamble]

# Configuration for output files
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# --8<-- [start:body_resolution]
# Resolve Ceres in the JPL Small-Body Database to get its NAIF/SPK ID and SI
# physical parameters, then generate and load a targeted SPK from Horizons so
# third-body and SRP perturbations resolve around Ceres. Both the SBDB query
# and the SPK are cached under the brahe cache directory and reused on repeat
# runs, so this hits the network only once per machine.
ceres_obj = bh.datasets.sbdb.SBDBClient().lookup("Ceres")
CERES_NAIF_ID = ceres_obj.naif_id()  # 20000001 (SBDB SPK-ID scheme)
GM_CERES = ceres_obj.gm  # m^3/s^2
R_CERES = ceres_obj.radius  # m
print(f"Ceres: {ceres_obj.full_name}, NAIF ID {CERES_NAIF_ID}")
print(f"  GM = {GM_CERES:.6e} m^3/s^2, radius = {R_CERES / 1e3:.1f} km")

# Load the common SPICE kernels (includes de440s) so Sun/Jupiter positions are
# available, then fetch and load a Ceres SPK covering the propagation span.
bh.load_common_spice_kernels()
spk_t0 = bh.Epoch.from_datetime(2015, 12, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.TDB)
spk_t1 = bh.Epoch.from_datetime(2016, 3, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.TDB)
spk = bh.datasets.horizons.HorizonsClient().get_spk(
    bh.datasets.horizons.HorizonsSPKRequest.for_spkid(CERES_NAIF_ID, spk_t0, spk_t1)
)
spk.load()
print(f"Loaded Ceres SPK: {spk.path}")
# --8<-- [end:body_resolution]

# --8<-- [start:body_definition]
# Ceres orientation model (IAU WGCCRE 2015 pole/rotation). SBDB does not
# supply spin-pole or prime-meridian constants, so they are set here:
CERES_POLE_RA = 291.418  # deg, ICRF right ascension of the spin pole
CERES_POLE_DEC = 66.764  # deg, ICRF declination of the spin pole
CERES_W0 = 170.650  # deg, prime meridian angle at J2000 TT
CERES_W_RATE = 952.1532635  # deg/day
# --8<-- [end:body_definition]

# --8<-- [start:body_fixed_frame]
# A body-fixed frame from the IAU-style pole/prime-meridian model, registered
# as a custom frame: rotation(epoch) -> ICRF-to-body DCM.
_J2000_TT_MJD = 51544.5


def ceres_rotation(epc):
    d = epc.mjd_as_time_system(bh.TimeSystem.TT) - _J2000_TT_MJD
    alpha = np.radians(CERES_POLE_RA)
    delta = np.radians(CERES_POLE_DEC)
    w = np.radians((CERES_W0 + CERES_W_RATE * d) % 360.0)
    return (
        bh.Rz(w, bh.AngleFormat.RADIANS)
        @ bh.Rx(np.pi / 2 - delta, bh.AngleFormat.RADIANS)
        @ bh.Rz(np.pi / 2 + alpha, bh.AngleFormat.RADIANS)
    )


def ceres_omega(epc=None):
    return np.array([0.0, 0.0, np.radians(CERES_W_RATE) / 86400.0])


# The `1` is an arbitrarily chosen registry key for this custom frame; it
# just needs to be unique among registered custom frames.
bh.register_custom_frame(1, ceres_rotation, ceres_omega)
ceres_fixed = bh.ReferenceFrame.BodyFixedCustom(CERES_NAIF_ID, 1)
# --8<-- [end:body_fixed_frame]

# --8<-- [start:force_model]
ceres = bh.CentralBody.Custom(
    "Ceres",
    CERES_NAIF_ID,
    GM_CERES,
    radius=R_CERES,
    omega=ceres_omega(),
    fixed_frame=ceres_fixed,
)

# With the Ceres SPK loaded, enable solar and Jovian third-body perturbations
# and solar radiation pressure. The Sun dominates the third-body signal at
# Ceres; Jupiter is added via the built-in `ThirdBody.JUPITER_BARYCENTER`. The
# occulting body for eclipse geometry is Ceres itself (an SRP shadow cast by
# Earth is meaningless 2.8 AU away), supplied as a Custom occulting body.
SPACECRAFT_MASS = 750.0  # kg (Dawn dry mass, approximate)
SRP_AREA = 20.0  # m^2 (solar-array-dominated cross section, approximate)
CR = 1.3  # reflectivity coefficient

srp = bh.SolarRadiationPressureConfiguration(
    area=bh.ParameterSource.value(SRP_AREA),
    cr=bh.ParameterSource.value(CR),
    eclipse_model=bh.EclipseModel.CONICAL,
    occulting_bodies=[
        bh.OccultingBody.Custom(name="Ceres", naif_id=CERES_NAIF_ID, radius=R_CERES)
    ],
)

force_config = bh.ForceModelConfig.for_body(
    ceres,
    bh.GravityConfiguration.point_mass(),
    srp=srp,
    third_body=[
        bh.ThirdBody.SUN,
        bh.ThirdBody.JUPITER_BARYCENTER,
    ],
    mass=bh.ParameterSource.value(SPACECRAFT_MASS),
)
# --8<-- [end:force_model]

# --8<-- [start:orbit_setup]
# Dawn LAMO (Low Altitude Mapping Orbit): ~375 km circular polar orbit.
epoch = bh.Epoch.from_datetime(2016, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)

oe = np.array(
    [R_CERES + 375e3, 0.001, 90.0, 0.0, 0.0, 0.0]
)  # [a [m], e [-], i [deg], RAAN [deg], argp [deg], M [deg]]

state0 = bh.state_koe_to_inertial_for_body(oe, ceres, bh.AngleFormat.DEGREES)

# Ceres spin pole (ICRF) from the IAU pole constants, used below to confirm the
# orbit geometry (declination / right ascension -> unit pole vector). This is
# the same pole the registered frame carries, evaluated directly here.
_pole_ra = np.radians(CERES_POLE_RA)
_pole_dec = np.radians(CERES_POLE_DEC)
ceres_pole = np.array(
    [
        np.cos(_pole_dec) * np.cos(_pole_ra),
        np.cos(_pole_dec) * np.sin(_pole_ra),
        np.sin(_pole_dec),
    ]
)

print(f"LAMO altitude: {(oe[0] - R_CERES) / 1e3:.1f} km, inclination: {oe[2]:.1f} deg")
print(f"Ceres spin pole (ICRF): {np.array2string(ceres_pole, precision=4)}")
# --8<-- [end:orbit_setup]

# --8<-- [start:propagation]
prop = bh.NumericalOrbitPropagator.builder(epoch, state0, force_config).build()
duration = 2 * 86400.0
print(f"\nPropagating {duration / 86400.0:.0f} days...")
prop.propagate_to(epoch + duration)
print("  Complete!")

# state_bci returns the propagator's native state in the central body's
# body-centered inertial frame (here, Ceres-centered) -- the frame the orbit
# was actually integrated in. state_eci would instead re-center the state onto
# Earth via SPK ephemeris (now possible since the Ceres SPK is loaded), which
# is not the frame we want here.
dt = 120.0
epochs = [epoch + t for t in np.arange(0.0, duration, dt)]
radii_km = np.array([np.linalg.norm(prop.state_bci(epc)[:3]) for epc in epochs]) / 1e3
print(f"\nMin radius: {radii_km.min():.2f} km, max radius: {radii_km.max():.2f} km")
print(f"(Ceres radius: {R_CERES / 1e3:.1f} km)")

# Body-fixed position through the registered frame:
x_fixed = prop.state_in_frame(ceres_fixed, epoch + duration)
print(
    f"\nBody-fixed state at t+{duration / 86400.0:.0f} d: {np.array2string(x_fixed, precision=1)}"
)
# --8<-- [end:propagation]

# --8<-- [start:plot_3d]
fig_3d = bh.plot_trajectory_3d(
    [{"trajectory": prop.trajectory, "color": "cyan", "label": "Dawn (LAMO)"}],
    central_body="ceres",
    backend="plotly",
)
# --8<-- [end:plot_3d]

# --8<-- [start:baseline_comparison]
# Quantify the perturbations by propagating a two-body (point-mass, no
# third-body, no SRP) baseline from the same initial state and comparing. The
# solar/Jovian third-body and SRP accelerations are small at a ~375 km, ~5.4 h
# LAMO orbit, so over 2 days (~9 revolutions) they perturb the trajectory by
# tens of meters rather than reshaping it -- but the divergence is measurable
# and grows with time, which a pure two-body run cannot reproduce.
baseline_config = bh.ForceModelConfig.for_body(
    ceres, bh.GravityConfiguration.point_mass()
)
baseline = bh.NumericalOrbitPropagator.builder(epoch, state0, baseline_config).build()
baseline.propagate_to(epoch + duration)

pos_divergence_m = np.array(
    [
        np.linalg.norm(prop.state_bci(epc)[:3] - baseline.state_bci(epc)[:3])
        for epc in epochs
    ]
)
vel_divergence_mps = np.array(
    [
        np.linalg.norm(prop.state_bci(epc)[3:] - baseline.state_bci(epc)[3:])
        for epc in epochs
    ]
)
max_divergence_m = pos_divergence_m.max()
print(
    f"\nMax perturbed-vs-two-body position divergence: {max_divergence_m:.2f} m "
    f"(0 for a two-body-only run)"
)
# --8<-- [end:baseline_comparison]

# --8<-- [start:plot_divergence]
# Perturbation signature: the perturbed run's position and velocity divergence
# from the two-body baseline, growing over the propagation. A pure two-body run
# would sit at zero; the growth is the solar/Jovian third-body and SRP signal.
import plotly.graph_objects as go

hours = np.arange(0.0, duration, dt) / 3600.0
fig_div = go.Figure()
fig_div.add_trace(
    go.Scatter(x=hours, y=pos_divergence_m, name="Position (m)", mode="lines")
)
fig_div.add_trace(
    go.Scatter(
        x=hours,
        y=vel_divergence_mps * 1e3,
        name="Velocity (mm/s)",
        mode="lines",
        yaxis="y2",
    )
)
fig_div.update_layout(
    title="Perturbed vs two-body divergence",
    xaxis_title="Time since epoch (hours)",
    yaxis={"title": "Position divergence (m)"},
    yaxis2={"title": "Velocity divergence (mm/s)", "overlaying": "y", "side": "right"},
    legend={"x": 0.02, "y": 0.98},
)
# --8<-- [end:plot_divergence]

# Validation
# Inclination relative to the Ceres spin pole confirms the orbit plane was
# built about the Ceres equator, not the ICRF pole. The perturbations barely
# tilt the plane over 2 days (a few 1e-5 deg), so the orbit stays polar; the
# measurable signature of the perturbations is the position divergence above.
incs_deg = []
for epc in epochs:
    x = prop.state_bci(epc)
    h = np.cross(x[:3], x[3:])
    h /= np.linalg.norm(h)
    incs_deg.append(np.degrees(np.arccos(np.clip(np.dot(h, ceres_pole), -1.0, 1.0))))
incs_deg = np.array(incs_deg)
max_excursion = np.max(np.abs(incs_deg - 90.0))
print(f"Inclination rel. Ceres pole: {incs_deg.min():.6f} to {incs_deg.max():.6f} deg")
print(f"Max excursion from 90 deg polar design: {max_excursion:.6f} deg")

# The perturbations move the trajectory measurably off the two-body baseline
# (they are active) while staying small over 2 days: the orbit remains polar to
# well under a hundredth of a degree and inside the LAMO altitude band, and the
# body-fixed state is finite.
print(
    f"\nPerturbations active: {max_divergence_m:.1f} m divergence from the "
    f"two-body baseline; orbit stays polar (excursion {max_excursion:.1e} deg) "
    f"and bounded ({radii_km.min():.1f}-{radii_km.max():.1f} km radius)."
)
# --8<-- [end:all]

# ============================================================================
# Plot Output Section (for documentation generation)
# ============================================================================

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "plots"))
from brahe_theme import save_themed_html

# Save themed figures
light_path, dark_path = save_themed_html(fig_3d, OUTDIR / f"{SCRIPT_NAME}_3d")
print(f"\n✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")

light_path_div, dark_path_div = save_themed_html(
    fig_div, OUTDIR / f"{SCRIPT_NAME}_divergence"
)
print(f"✓ Generated {light_path_div}")
print(f"✓ Generated {dark_path_div}")

print("\nDawn at Ceres Example Complete!")
```


## 3D Visualization

[`plot_trajectory_3d`](../library_api/plots/3d_trajectory.md) accepts `central_body="ceres"`: Ceres is already in the
plotting library's body-visuals registry (radius and NAIF ID for frame
validation, plus a default texture), so no custom dict is needed. Non-Earth
central bodies require the plotted trajectory to already be in
[`OrbitFrame.BodyCenteredInertial(naif_id)`](../library_api/orbits/enums.md#brahe.OrbitFrame.BodyCenteredInertial) for that body; a Ceres-centered
[`NumericalOrbitPropagator`](../library_api/propagators/numerical_orbit_propagator.md)'s `.trajectory` is already in that frame:

```python
#!/usr/bin/env python
# /// script
# dependencies = ["brahe", "plotly", "numpy"]
# ///
"""
Dawn at Ceres: a user-defined rotating central body

This example demonstrates how to:
1. Resolve a small body (Ceres) in the JPL Small-Body Database (SBDB) to get
   its NAIF/SPK ID and SI physical parameters (GM, radius)
2. Fetch and load a targeted Ceres SPK from JPL Horizons so third-body and
   solar radiation pressure perturbations resolve around the body
3. Define a user-supplied central body (GM, radius, spin pole, prime meridian)
   and register a custom body-fixed frame from an IAU-style pole/prime-meridian
   rotation model
4. Propagate the Dawn spacecraft's LAMO (Low Altitude Mapping Orbit) around
   Ceres with point-mass gravity plus solar/Jovian third-body and solar
   radiation pressure perturbations
5. Report the body-fixed state through the custom frame and visualize the
   trajectory in 3D around a textured Ceres

Unlike Earth, the Moon, and Mars, Ceres has no built-in constants in brahe:
no built-in `CentralBody` variant, no named inertial/fixed frame pair, and no
spin model. Its gravitational parameter and radius are read from SBDB, while
its spin pole, prime meridian, and body-fixed frame - which SBDB does not
provide - are supplied by the user via `CentralBody.Custom` and
`register_custom_frame`. The same recipe applies to any body brahe doesn't
have built-in constants for: another dwarf planet, an asteroid, or a comet
nucleus.

NASA's Dawn spacecraft orbited Ceres from 2015 to 2018, spending much of its
final year in LAMO: a ~375 km, near-circular polar orbit used for its highest
resolution gravity and neutron/gamma-ray mapping. This example is inspired by
that LAMO phase rather than reproducing its exact mission parameters.

The propagator integrates in a Ceres-centered inertial frame whose axes are
ICRF-aligned: its z-axis is the ICRF pole, which sits ~23 deg from Ceres's
spin pole. An inclination passed straight to state_koe_to_eci would therefore
be measured against the wrong pole. Instead, state_koe_to_inertial_for_body
references the elements to Ceres's mean equator at J2000 -- and because Ceres
is a Custom body, it reads the pole from the user-registered body-fixed frame
-- so the 90 deg polar inclination is referenced to Ceres's equator as intended.
"""

# --8<-- [start:all]
# --8<-- [start:preamble]
import os
import pathlib
import sys

import numpy as np

import brahe as bh

# No `bh.initialize_eop()` call is needed here: this example never converts
# to or from Earth-relative frames, so it has no dependency on Earth
# orientation data. SPICE kernels are loaded below (de440s for Sun/Jupiter
# positions plus a Ceres SPK from Horizons) so that the third-body and solar
# radiation pressure perturbations resolve around Ceres.
# --8<-- [end:preamble]

# Configuration for output files
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# --8<-- [start:body_resolution]
# Resolve Ceres in the JPL Small-Body Database to get its NAIF/SPK ID and SI
# physical parameters, then generate and load a targeted SPK from Horizons so
# third-body and SRP perturbations resolve around Ceres. Both the SBDB query
# and the SPK are cached under the brahe cache directory and reused on repeat
# runs, so this hits the network only once per machine.
ceres_obj = bh.datasets.sbdb.SBDBClient().lookup("Ceres")
CERES_NAIF_ID = ceres_obj.naif_id()  # 20000001 (SBDB SPK-ID scheme)
GM_CERES = ceres_obj.gm  # m^3/s^2
R_CERES = ceres_obj.radius  # m
print(f"Ceres: {ceres_obj.full_name}, NAIF ID {CERES_NAIF_ID}")
print(f"  GM = {GM_CERES:.6e} m^3/s^2, radius = {R_CERES / 1e3:.1f} km")

# Load the common SPICE kernels (includes de440s) so Sun/Jupiter positions are
# available, then fetch and load a Ceres SPK covering the propagation span.
bh.load_common_spice_kernels()
spk_t0 = bh.Epoch.from_datetime(2015, 12, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.TDB)
spk_t1 = bh.Epoch.from_datetime(2016, 3, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.TDB)
spk = bh.datasets.horizons.HorizonsClient().get_spk(
    bh.datasets.horizons.HorizonsSPKRequest.for_spkid(CERES_NAIF_ID, spk_t0, spk_t1)
)
spk.load()
print(f"Loaded Ceres SPK: {spk.path}")
# --8<-- [end:body_resolution]

# --8<-- [start:body_definition]
# Ceres orientation model (IAU WGCCRE 2015 pole/rotation). SBDB does not
# supply spin-pole or prime-meridian constants, so they are set here:
CERES_POLE_RA = 291.418  # deg, ICRF right ascension of the spin pole
CERES_POLE_DEC = 66.764  # deg, ICRF declination of the spin pole
CERES_W0 = 170.650  # deg, prime meridian angle at J2000 TT
CERES_W_RATE = 952.1532635  # deg/day
# --8<-- [end:body_definition]

# --8<-- [start:body_fixed_frame]
# A body-fixed frame from the IAU-style pole/prime-meridian model, registered
# as a custom frame: rotation(epoch) -> ICRF-to-body DCM.
_J2000_TT_MJD = 51544.5


def ceres_rotation(epc):
    d = epc.mjd_as_time_system(bh.TimeSystem.TT) - _J2000_TT_MJD
    alpha = np.radians(CERES_POLE_RA)
    delta = np.radians(CERES_POLE_DEC)
    w = np.radians((CERES_W0 + CERES_W_RATE * d) % 360.0)
    return (
        bh.Rz(w, bh.AngleFormat.RADIANS)
        @ bh.Rx(np.pi / 2 - delta, bh.AngleFormat.RADIANS)
        @ bh.Rz(np.pi / 2 + alpha, bh.AngleFormat.RADIANS)
    )


def ceres_omega(epc=None):
    return np.array([0.0, 0.0, np.radians(CERES_W_RATE) / 86400.0])


# The `1` is an arbitrarily chosen registry key for this custom frame; it
# just needs to be unique among registered custom frames.
bh.register_custom_frame(1, ceres_rotation, ceres_omega)
ceres_fixed = bh.ReferenceFrame.BodyFixedCustom(CERES_NAIF_ID, 1)
# --8<-- [end:body_fixed_frame]

# --8<-- [start:force_model]
ceres = bh.CentralBody.Custom(
    "Ceres",
    CERES_NAIF_ID,
    GM_CERES,
    radius=R_CERES,
    omega=ceres_omega(),
    fixed_frame=ceres_fixed,
)

# With the Ceres SPK loaded, enable solar and Jovian third-body perturbations
# and solar radiation pressure. The Sun dominates the third-body signal at
# Ceres; Jupiter is added via the built-in `ThirdBody.JUPITER_BARYCENTER`. The
# occulting body for eclipse geometry is Ceres itself (an SRP shadow cast by
# Earth is meaningless 2.8 AU away), supplied as a Custom occulting body.
SPACECRAFT_MASS = 750.0  # kg (Dawn dry mass, approximate)
SRP_AREA = 20.0  # m^2 (solar-array-dominated cross section, approximate)
CR = 1.3  # reflectivity coefficient

srp = bh.SolarRadiationPressureConfiguration(
    area=bh.ParameterSource.value(SRP_AREA),
    cr=bh.ParameterSource.value(CR),
    eclipse_model=bh.EclipseModel.CONICAL,
    occulting_bodies=[
        bh.OccultingBody.Custom(name="Ceres", naif_id=CERES_NAIF_ID, radius=R_CERES)
    ],
)

force_config = bh.ForceModelConfig.for_body(
    ceres,
    bh.GravityConfiguration.point_mass(),
    srp=srp,
    third_body=[
        bh.ThirdBody.SUN,
        bh.ThirdBody.JUPITER_BARYCENTER,
    ],
    mass=bh.ParameterSource.value(SPACECRAFT_MASS),
)
# --8<-- [end:force_model]

# --8<-- [start:orbit_setup]
# Dawn LAMO (Low Altitude Mapping Orbit): ~375 km circular polar orbit.
epoch = bh.Epoch.from_datetime(2016, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)

oe = np.array(
    [R_CERES + 375e3, 0.001, 90.0, 0.0, 0.0, 0.0]
)  # [a [m], e [-], i [deg], RAAN [deg], argp [deg], M [deg]]

state0 = bh.state_koe_to_inertial_for_body(oe, ceres, bh.AngleFormat.DEGREES)

# Ceres spin pole (ICRF) from the IAU pole constants, used below to confirm the
# orbit geometry (declination / right ascension -> unit pole vector). This is
# the same pole the registered frame carries, evaluated directly here.
_pole_ra = np.radians(CERES_POLE_RA)
_pole_dec = np.radians(CERES_POLE_DEC)
ceres_pole = np.array(
    [
        np.cos(_pole_dec) * np.cos(_pole_ra),
        np.cos(_pole_dec) * np.sin(_pole_ra),
        np.sin(_pole_dec),
    ]
)

print(f"LAMO altitude: {(oe[0] - R_CERES) / 1e3:.1f} km, inclination: {oe[2]:.1f} deg")
print(f"Ceres spin pole (ICRF): {np.array2string(ceres_pole, precision=4)}")
# --8<-- [end:orbit_setup]

# --8<-- [start:propagation]
prop = bh.NumericalOrbitPropagator.builder(epoch, state0, force_config).build()
duration = 2 * 86400.0
print(f"\nPropagating {duration / 86400.0:.0f} days...")
prop.propagate_to(epoch + duration)
print("  Complete!")

# state_bci returns the propagator's native state in the central body's
# body-centered inertial frame (here, Ceres-centered) -- the frame the orbit
# was actually integrated in. state_eci would instead re-center the state onto
# Earth via SPK ephemeris (now possible since the Ceres SPK is loaded), which
# is not the frame we want here.
dt = 120.0
epochs = [epoch + t for t in np.arange(0.0, duration, dt)]
radii_km = np.array([np.linalg.norm(prop.state_bci(epc)[:3]) for epc in epochs]) / 1e3
print(f"\nMin radius: {radii_km.min():.2f} km, max radius: {radii_km.max():.2f} km")
print(f"(Ceres radius: {R_CERES / 1e3:.1f} km)")

# Body-fixed position through the registered frame:
x_fixed = prop.state_in_frame(ceres_fixed, epoch + duration)
print(
    f"\nBody-fixed state at t+{duration / 86400.0:.0f} d: {np.array2string(x_fixed, precision=1)}"
)
# --8<-- [end:propagation]

# --8<-- [start:plot_3d]
fig_3d = bh.plot_trajectory_3d(
    [{"trajectory": prop.trajectory, "color": "cyan", "label": "Dawn (LAMO)"}],
    central_body="ceres",
    backend="plotly",
)
# --8<-- [end:plot_3d]

# --8<-- [start:baseline_comparison]
# Quantify the perturbations by propagating a two-body (point-mass, no
# third-body, no SRP) baseline from the same initial state and comparing. The
# solar/Jovian third-body and SRP accelerations are small at a ~375 km, ~5.4 h
# LAMO orbit, so over 2 days (~9 revolutions) they perturb the trajectory by
# tens of meters rather than reshaping it -- but the divergence is measurable
# and grows with time, which a pure two-body run cannot reproduce.
baseline_config = bh.ForceModelConfig.for_body(
    ceres, bh.GravityConfiguration.point_mass()
)
baseline = bh.NumericalOrbitPropagator.builder(epoch, state0, baseline_config).build()
baseline.propagate_to(epoch + duration)

pos_divergence_m = np.array(
    [
        np.linalg.norm(prop.state_bci(epc)[:3] - baseline.state_bci(epc)[:3])
        for epc in epochs
    ]
)
vel_divergence_mps = np.array(
    [
        np.linalg.norm(prop.state_bci(epc)[3:] - baseline.state_bci(epc)[3:])
        for epc in epochs
    ]
)
max_divergence_m = pos_divergence_m.max()
print(
    f"\nMax perturbed-vs-two-body position divergence: {max_divergence_m:.2f} m "
    f"(0 for a two-body-only run)"
)
# --8<-- [end:baseline_comparison]

# --8<-- [start:plot_divergence]
# Perturbation signature: the perturbed run's position and velocity divergence
# from the two-body baseline, growing over the propagation. A pure two-body run
# would sit at zero; the growth is the solar/Jovian third-body and SRP signal.
import plotly.graph_objects as go

hours = np.arange(0.0, duration, dt) / 3600.0
fig_div = go.Figure()
fig_div.add_trace(
    go.Scatter(x=hours, y=pos_divergence_m, name="Position (m)", mode="lines")
)
fig_div.add_trace(
    go.Scatter(
        x=hours,
        y=vel_divergence_mps * 1e3,
        name="Velocity (mm/s)",
        mode="lines",
        yaxis="y2",
    )
)
fig_div.update_layout(
    title="Perturbed vs two-body divergence",
    xaxis_title="Time since epoch (hours)",
    yaxis={"title": "Position divergence (m)"},
    yaxis2={"title": "Velocity divergence (mm/s)", "overlaying": "y", "side": "right"},
    legend={"x": 0.02, "y": 0.98},
)
# --8<-- [end:plot_divergence]

# Validation
# Inclination relative to the Ceres spin pole confirms the orbit plane was
# built about the Ceres equator, not the ICRF pole. The perturbations barely
# tilt the plane over 2 days (a few 1e-5 deg), so the orbit stays polar; the
# measurable signature of the perturbations is the position divergence above.
incs_deg = []
for epc in epochs:
    x = prop.state_bci(epc)
    h = np.cross(x[:3], x[3:])
    h /= np.linalg.norm(h)
    incs_deg.append(np.degrees(np.arccos(np.clip(np.dot(h, ceres_pole), -1.0, 1.0))))
incs_deg = np.array(incs_deg)
max_excursion = np.max(np.abs(incs_deg - 90.0))
print(f"Inclination rel. Ceres pole: {incs_deg.min():.6f} to {incs_deg.max():.6f} deg")
print(f"Max excursion from 90 deg polar design: {max_excursion:.6f} deg")

# The perturbations move the trajectory measurably off the two-body baseline
# (they are active) while staying small over 2 days: the orbit remains polar to
# well under a hundredth of a degree and inside the LAMO altitude band, and the
# body-fixed state is finite.
print(
    f"\nPerturbations active: {max_divergence_m:.1f} m divergence from the "
    f"two-body baseline; orbit stays polar (excursion {max_excursion:.1e} deg) "
    f"and bounded ({radii_km.min():.1f}-{radii_km.max():.1f} km radius)."
)
# --8<-- [end:all]

# ============================================================================
# Plot Output Section (for documentation generation)
# ============================================================================

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "plots"))
from brahe_theme import save_themed_html

# Save themed figures
light_path, dark_path = save_themed_html(fig_3d, OUTDIR / f"{SCRIPT_NAME}_3d")
print(f"\n✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")

light_path_div, dark_path_div = save_themed_html(
    fig_div, OUTDIR / f"{SCRIPT_NAME}_divergence"
)
print(f"✓ Generated {light_path_div}")
print(f"✓ Generated {dark_path_div}")

print("\nDawn at Ceres Example Complete!")
```


*Body textures: [Solar System Scope](https://www.solarsystemscope.com/textures/), CC BY 4.0 - the Ceres texture is an artistic impression, not an actual surface map.*

## Full Code Example

**Full Code**

```
#!/usr/bin/env python
# /// script
# dependencies = ["brahe", "plotly", "numpy"]
# ///
"""
Dawn at Ceres: a user-defined rotating central body

This example demonstrates how to:
1. Resolve a small body (Ceres) in the JPL Small-Body Database (SBDB) to get
   its NAIF/SPK ID and SI physical parameters (GM, radius)
2. Fetch and load a targeted Ceres SPK from JPL Horizons so third-body and
   solar radiation pressure perturbations resolve around the body
3. Define a user-supplied central body (GM, radius, spin pole, prime meridian)
   and register a custom body-fixed frame from an IAU-style pole/prime-meridian
   rotation model
4. Propagate the Dawn spacecraft's LAMO (Low Altitude Mapping Orbit) around
   Ceres with point-mass gravity plus solar/Jovian third-body and solar
   radiation pressure perturbations
5. Report the body-fixed state through the custom frame and visualize the
   trajectory in 3D around a textured Ceres

Unlike Earth, the Moon, and Mars, Ceres has no built-in constants in brahe:
no built-in `CentralBody` variant, no named inertial/fixed frame pair, and no
spin model. Its gravitational parameter and radius are read from SBDB, while
its spin pole, prime meridian, and body-fixed frame - which SBDB does not
provide - are supplied by the user via `CentralBody.Custom` and
`register_custom_frame`. The same recipe applies to any body brahe doesn't
have built-in constants for: another dwarf planet, an asteroid, or a comet
nucleus.

NASA's Dawn spacecraft orbited Ceres from 2015 to 2018, spending much of its
final year in LAMO: a ~375 km, near-circular polar orbit used for its highest
resolution gravity and neutron/gamma-ray mapping. This example is inspired by
that LAMO phase rather than reproducing its exact mission parameters.

The propagator integrates in a Ceres-centered inertial frame whose axes are
ICRF-aligned: its z-axis is the ICRF pole, which sits ~23 deg from Ceres's
spin pole. An inclination passed straight to state_koe_to_eci would therefore
be measured against the wrong pole. Instead, state_koe_to_inertial_for_body
references the elements to Ceres's mean equator at J2000 -- and because Ceres
is a Custom body, it reads the pole from the user-registered body-fixed frame
-- so the 90 deg polar inclination is referenced to Ceres's equator as intended.
"""

# --8<-- [start:all]
# --8<-- [start:preamble]
import os
import pathlib
import sys

import numpy as np

import brahe as bh

# No `bh.initialize_eop()` call is needed here: this example never converts
# to or from Earth-relative frames, so it has no dependency on Earth
# orientation data. SPICE kernels are loaded below (de440s for Sun/Jupiter
# positions plus a Ceres SPK from Horizons) so that the third-body and solar
# radiation pressure perturbations resolve around Ceres.
# --8<-- [end:preamble]

# Configuration for output files
SCRIPT_NAME = pathlib.Path(__file__).stem
OUTDIR = pathlib.Path(os.getenv("BRAHE_FIGURE_OUTPUT_DIR", "./docs/figures/"))
os.makedirs(OUTDIR, exist_ok=True)

# --8<-- [start:body_resolution]
# Resolve Ceres in the JPL Small-Body Database to get its NAIF/SPK ID and SI
# physical parameters, then generate and load a targeted SPK from Horizons so
# third-body and SRP perturbations resolve around Ceres. Both the SBDB query
# and the SPK are cached under the brahe cache directory and reused on repeat
# runs, so this hits the network only once per machine.
ceres_obj = bh.datasets.sbdb.SBDBClient().lookup("Ceres")
CERES_NAIF_ID = ceres_obj.naif_id()  # 20000001 (SBDB SPK-ID scheme)
GM_CERES = ceres_obj.gm  # m^3/s^2
R_CERES = ceres_obj.radius  # m
print(f"Ceres: {ceres_obj.full_name}, NAIF ID {CERES_NAIF_ID}")
print(f"  GM = {GM_CERES:.6e} m^3/s^2, radius = {R_CERES / 1e3:.1f} km")

# Load the common SPICE kernels (includes de440s) so Sun/Jupiter positions are
# available, then fetch and load a Ceres SPK covering the propagation span.
bh.load_common_spice_kernels()
spk_t0 = bh.Epoch.from_datetime(2015, 12, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.TDB)
spk_t1 = bh.Epoch.from_datetime(2016, 3, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.TDB)
spk = bh.datasets.horizons.HorizonsClient().get_spk(
    bh.datasets.horizons.HorizonsSPKRequest.for_spkid(CERES_NAIF_ID, spk_t0, spk_t1)
)
spk.load()
print(f"Loaded Ceres SPK: {spk.path}")
# --8<-- [end:body_resolution]

# --8<-- [start:body_definition]
# Ceres orientation model (IAU WGCCRE 2015 pole/rotation). SBDB does not
# supply spin-pole or prime-meridian constants, so they are set here:
CERES_POLE_RA = 291.418  # deg, ICRF right ascension of the spin pole
CERES_POLE_DEC = 66.764  # deg, ICRF declination of the spin pole
CERES_W0 = 170.650  # deg, prime meridian angle at J2000 TT
CERES_W_RATE = 952.1532635  # deg/day
# --8<-- [end:body_definition]

# --8<-- [start:body_fixed_frame]
# A body-fixed frame from the IAU-style pole/prime-meridian model, registered
# as a custom frame: rotation(epoch) -> ICRF-to-body DCM.
_J2000_TT_MJD = 51544.5


def ceres_rotation(epc):
    d = epc.mjd_as_time_system(bh.TimeSystem.TT) - _J2000_TT_MJD
    alpha = np.radians(CERES_POLE_RA)
    delta = np.radians(CERES_POLE_DEC)
    w = np.radians((CERES_W0 + CERES_W_RATE * d) % 360.0)
    return (
        bh.Rz(w, bh.AngleFormat.RADIANS)
        @ bh.Rx(np.pi / 2 - delta, bh.AngleFormat.RADIANS)
        @ bh.Rz(np.pi / 2 + alpha, bh.AngleFormat.RADIANS)
    )


def ceres_omega(epc=None):
    return np.array([0.0, 0.0, np.radians(CERES_W_RATE) / 86400.0])


# The `1` is an arbitrarily chosen registry key for this custom frame; it
# just needs to be unique among registered custom frames.
bh.register_custom_frame(1, ceres_rotation, ceres_omega)
ceres_fixed = bh.ReferenceFrame.BodyFixedCustom(CERES_NAIF_ID, 1)
# --8<-- [end:body_fixed_frame]

# --8<-- [start:force_model]
ceres = bh.CentralBody.Custom(
    "Ceres",
    CERES_NAIF_ID,
    GM_CERES,
    radius=R_CERES,
    omega=ceres_omega(),
    fixed_frame=ceres_fixed,
)

# With the Ceres SPK loaded, enable solar and Jovian third-body perturbations
# and solar radiation pressure. The Sun dominates the third-body signal at
# Ceres; Jupiter is added via the built-in `ThirdBody.JUPITER_BARYCENTER`. The
# occulting body for eclipse geometry is Ceres itself (an SRP shadow cast by
# Earth is meaningless 2.8 AU away), supplied as a Custom occulting body.
SPACECRAFT_MASS = 750.0  # kg (Dawn dry mass, approximate)
SRP_AREA = 20.0  # m^2 (solar-array-dominated cross section, approximate)
CR = 1.3  # reflectivity coefficient

srp = bh.SolarRadiationPressureConfiguration(
    area=bh.ParameterSource.value(SRP_AREA),
    cr=bh.ParameterSource.value(CR),
    eclipse_model=bh.EclipseModel.CONICAL,
    occulting_bodies=[
        bh.OccultingBody.Custom(name="Ceres", naif_id=CERES_NAIF_ID, radius=R_CERES)
    ],
)

force_config = bh.ForceModelConfig.for_body(
    ceres,
    bh.GravityConfiguration.point_mass(),
    srp=srp,
    third_body=[
        bh.ThirdBody.SUN,
        bh.ThirdBody.JUPITER_BARYCENTER,
    ],
    mass=bh.ParameterSource.value(SPACECRAFT_MASS),
)
# --8<-- [end:force_model]

# --8<-- [start:orbit_setup]
# Dawn LAMO (Low Altitude Mapping Orbit): ~375 km circular polar orbit.
epoch = bh.Epoch.from_datetime(2016, 1, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)

oe = np.array(
    [R_CERES + 375e3, 0.001, 90.0, 0.0, 0.0, 0.0]
)  # [a [m], e [-], i [deg], RAAN [deg], argp [deg], M [deg]]

state0 = bh.state_koe_to_inertial_for_body(oe, ceres, bh.AngleFormat.DEGREES)

# Ceres spin pole (ICRF) from the IAU pole constants, used below to confirm the
# orbit geometry (declination / right ascension -> unit pole vector). This is
# the same pole the registered frame carries, evaluated directly here.
_pole_ra = np.radians(CERES_POLE_RA)
_pole_dec = np.radians(CERES_POLE_DEC)
ceres_pole = np.array(
    [
        np.cos(_pole_dec) * np.cos(_pole_ra),
        np.cos(_pole_dec) * np.sin(_pole_ra),
        np.sin(_pole_dec),
    ]
)

print(f"LAMO altitude: {(oe[0] - R_CERES) / 1e3:.1f} km, inclination: {oe[2]:.1f} deg")
print(f"Ceres spin pole (ICRF): {np.array2string(ceres_pole, precision=4)}")
# --8<-- [end:orbit_setup]

# --8<-- [start:propagation]
prop = bh.NumericalOrbitPropagator.builder(epoch, state0, force_config).build()
duration = 2 * 86400.0
print(f"\nPropagating {duration / 86400.0:.0f} days...")
prop.propagate_to(epoch + duration)
print("  Complete!")

# state_bci returns the propagator's native state in the central body's
# body-centered inertial frame (here, Ceres-centered) -- the frame the orbit
# was actually integrated in. state_eci would instead re-center the state onto
# Earth via SPK ephemeris (now possible since the Ceres SPK is loaded), which
# is not the frame we want here.
dt = 120.0
epochs = [epoch + t for t in np.arange(0.0, duration, dt)]
radii_km = np.array([np.linalg.norm(prop.state_bci(epc)[:3]) for epc in epochs]) / 1e3
print(f"\nMin radius: {radii_km.min():.2f} km, max radius: {radii_km.max():.2f} km")
print(f"(Ceres radius: {R_CERES / 1e3:.1f} km)")

# Body-fixed position through the registered frame:
x_fixed = prop.state_in_frame(ceres_fixed, epoch + duration)
print(
    f"\nBody-fixed state at t+{duration / 86400.0:.0f} d: {np.array2string(x_fixed, precision=1)}"
)
# --8<-- [end:propagation]

# --8<-- [start:plot_3d]
fig_3d = bh.plot_trajectory_3d(
    [{"trajectory": prop.trajectory, "color": "cyan", "label": "Dawn (LAMO)"}],
    central_body="ceres",
    backend="plotly",
)
# --8<-- [end:plot_3d]

# --8<-- [start:baseline_comparison]
# Quantify the perturbations by propagating a two-body (point-mass, no
# third-body, no SRP) baseline from the same initial state and comparing. The
# solar/Jovian third-body and SRP accelerations are small at a ~375 km, ~5.4 h
# LAMO orbit, so over 2 days (~9 revolutions) they perturb the trajectory by
# tens of meters rather than reshaping it -- but the divergence is measurable
# and grows with time, which a pure two-body run cannot reproduce.
baseline_config = bh.ForceModelConfig.for_body(
    ceres, bh.GravityConfiguration.point_mass()
)
baseline = bh.NumericalOrbitPropagator.builder(epoch, state0, baseline_config).build()
baseline.propagate_to(epoch + duration)

pos_divergence_m = np.array(
    [
        np.linalg.norm(prop.state_bci(epc)[:3] - baseline.state_bci(epc)[:3])
        for epc in epochs
    ]
)
vel_divergence_mps = np.array(
    [
        np.linalg.norm(prop.state_bci(epc)[3:] - baseline.state_bci(epc)[3:])
        for epc in epochs
    ]
)
max_divergence_m = pos_divergence_m.max()
print(
    f"\nMax perturbed-vs-two-body position divergence: {max_divergence_m:.2f} m "
    f"(0 for a two-body-only run)"
)
# --8<-- [end:baseline_comparison]

# --8<-- [start:plot_divergence]
# Perturbation signature: the perturbed run's position and velocity divergence
# from the two-body baseline, growing over the propagation. A pure two-body run
# would sit at zero; the growth is the solar/Jovian third-body and SRP signal.
import plotly.graph_objects as go

hours = np.arange(0.0, duration, dt) / 3600.0
fig_div = go.Figure()
fig_div.add_trace(
    go.Scatter(x=hours, y=pos_divergence_m, name="Position (m)", mode="lines")
)
fig_div.add_trace(
    go.Scatter(
        x=hours,
        y=vel_divergence_mps * 1e3,
        name="Velocity (mm/s)",
        mode="lines",
        yaxis="y2",
    )
)
fig_div.update_layout(
    title="Perturbed vs two-body divergence",
    xaxis_title="Time since epoch (hours)",
    yaxis={"title": "Position divergence (m)"},
    yaxis2={"title": "Velocity divergence (mm/s)", "overlaying": "y", "side": "right"},
    legend={"x": 0.02, "y": 0.98},
)
# --8<-- [end:plot_divergence]

# Validation
# Inclination relative to the Ceres spin pole confirms the orbit plane was
# built about the Ceres equator, not the ICRF pole. The perturbations barely
# tilt the plane over 2 days (a few 1e-5 deg), so the orbit stays polar; the
# measurable signature of the perturbations is the position divergence above.
incs_deg = []
for epc in epochs:
    x = prop.state_bci(epc)
    h = np.cross(x[:3], x[3:])
    h /= np.linalg.norm(h)
    incs_deg.append(np.degrees(np.arccos(np.clip(np.dot(h, ceres_pole), -1.0, 1.0))))
incs_deg = np.array(incs_deg)
max_excursion = np.max(np.abs(incs_deg - 90.0))
print(f"Inclination rel. Ceres pole: {incs_deg.min():.6f} to {incs_deg.max():.6f} deg")
print(f"Max excursion from 90 deg polar design: {max_excursion:.6f} deg")

# The perturbations move the trajectory measurably off the two-body baseline
# (they are active) while staying small over 2 days: the orbit remains polar to
# well under a hundredth of a degree and inside the LAMO altitude band, and the
# body-fixed state is finite.
print(
    f"\nPerturbations active: {max_divergence_m:.1f} m divergence from the "
    f"two-body baseline; orbit stays polar (excursion {max_excursion:.1e} deg) "
    f"and bounded ({radii_km.min():.1f}-{radii_km.max():.1f} km radius)."
)
# --8<-- [end:all]

# ============================================================================
# Plot Output Section (for documentation generation)
# ============================================================================

# Add plots directory to path for importing brahe_theme
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "plots"))
from brahe_theme import save_themed_html

# Save themed figures
light_path, dark_path = save_themed_html(fig_3d, OUTDIR / f"{SCRIPT_NAME}_3d")
print(f"\n✓ Generated {light_path}")
print(f"✓ Generated {dark_path}")

light_path_div, dark_path_div = save_themed_html(
    fig_div, OUTDIR / f"{SCRIPT_NAME}_divergence"
)
print(f"✓ Generated {light_path_div}")
print(f"✓ Generated {dark_path_div}")

print("\nDawn at Ceres Example Complete!")
```

---

## See Also

- [Numerical Orbit Propagation](../learn/orbit_propagation/numerical_propagation/index.md) - Propagator fundamentals
- [Force Models](../learn/orbit_propagation/numerical_propagation/force_models.md) - Configuring force models, including `CentralBody.Custom`
- [Reference Frames](../learn/frames/index.md) - Frame conventions, including custom body-fixed frames
- [3D Trajectory Plotting](../learn/plots/3d_trajectory.md) - Advanced options for trajectory visualization, including non-Earth central bodies