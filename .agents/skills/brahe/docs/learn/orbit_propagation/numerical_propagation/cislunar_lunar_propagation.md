# Cislunar and Lunar Propagation

`NumericalOrbitPropagator` integrates relative to a `CentralBody`, which identifies the body an orbit is propagated about and bundles the gravitational parameter (GM, $\mu$), radius, spin rate, and inertial/fixed frame pair needed for body-orientation based force models (gravity, drag). Two central bodies cover cislunar work: `Moon`, for orbits about the Moon, and `EMB`, the Earth-Moon barycenter, whose integration frame is `EMBI`, the inertial (ICRF-aligned) Earth-Moon barycenter frame, for cislunar transfer trajectories. `ForceModelConfig.lunar_default()` and `ForceModelConfig.cislunar_default()` pair each with a physically appropriate force model.

| `CentralBody` | NAIF ID | Inertial frame | Fixed frame |
|---|---|---|---|
| `Moon` | 301 | `LCI` | `LFPA` |
| `EMB` | 3 | `EMBI` | none |

The propagator integrates in the central body's inertial frame (`LCI` for `Moon`, `EMBI` for `EMB`). `state_in_frame(frame, epoch)` converts the integrated state into any [`ReferenceFrame`](../../frames/frame_transformations.md), routing directly from the integration frame: for a Moon-centered propagator, `state_in_frame(ReferenceFrame.LCI, epoch)` is the identity (no SPK round trip), and `state_in_frame(ReferenceFrame.LFPA, epoch)` gives the Moon-fixed state without first converting to Earth-centered `GCRF`. `state_bci(epoch)` returns the raw body-centered inertial state without conversion, and `state_bcbf(epoch)` returns the body-centered body-fixed state (`LFPA` for `Moon`; `EMB` has no body-fixed frame and returns an error).

## Force-Model Defaults

`ForceModelConfig` provides factory methods that pair a `CentralBody` with a force model tuned for it:

| Constructor | Central body | Gravity | Drag | SRP occultation | Third bodies |
|---|---|---|---|---|---|
| `lunar_default()` | `Moon` | 50x50 GRGM660PRIM | none | Moon, Earth | Earth, Sun |
| `cislunar_default()` | `EMB` | None (`Zero`) | none | Earth, Moon | Earth, Moon, Sun |

Both require a spacecraft parameter vector at propagator construction, since mass/area/coefficients are wired up via `ParameterSource::ParameterIndex`. Each expects `[mass, drag_area, Cd, srp_area, Cr]`; because neither model includes drag, the `drag_area` and `Cd` slots (indices 1 and 2) are unused placeholders but must still be present. `.validate()` can be used on the config to check it up front for inconsistent configuration options. For example, with a `Moon` central body it fails on Earth-specific options (e.g. Harris-Priester or NRLMSISE-00 atmospheric drag attributed to the Moon, `EarthZonal` central gravity), and with the `EMB` barycenter it rejects spherical-harmonic central gravity and drag without an attributed body, since a barycenter has no mass or rotation of its own. The same validation also runs automatically when a `NumericalOrbitPropagator` is constructed, so a misconfigured force model fails at construction even without an explicit `.validate()` call.

## Barycenter Third-Body Physics

Third-body acceleration relative to a body-centered frame is normally a *differential* term: the direct attraction of the perturber on the spacecraft, minus its attraction on the (accelerating) central body, whose motion moves the frame origin. The Earth-Moon barycenter is a special case for its two internal bodies. Because internal Earth-Moon gravitational forces are equal and opposite, neither Earth nor the Moon can accelerate their mutual barycenter, so their contributions about `EMB` use the **direct term only** (no indirect subtraction). Other perturbers &mdash; the Sun, planets &mdash; do accelerate the Earth-Moon system as a whole and still use the differential form about `EMB`. (The Solar System barycenter `SSB` uses the direct form for every perturber, since nothing external to the modeled system accelerates it.)

This handling is automatic: selecting `CentralBody::EMB` (via `cislunar_default()` or directly) routes Earth and Moon perturbations through the direct form and all others through the differential form.

## Earth-Attributed Force Models

An EMB-centered trajectory that passes through low Earth altitudes can carry Earth-fidelity forces without switching central bodies. A third-body entry's `gravity` accepts a `SphericalHarmonic` or `EarthZonal` field evaluated at the object's position relative to that body, and `DragConfiguration.body` attributes atmospheric drag to a body other than the central body (density and relative wind are evaluated at the object's body-relative state). See [Force Models: Body Attribution](force_models.md#body-attribution) for the configuration details and a complete EMB-centered example with an 8x8 Earth field and Earth-attributed NRLMSISE-00 drag.

## Example: Propagating an Orbit About the Moon

The example below builds a lunar force model with `ForceModelConfig.lunar_default()`, propagates a low lunar orbit for six hours, and reports the initial and final state in the Moon-fixed LFPA frame via `state_in_frame`.


```python
import numpy as np
import brahe as bh

# Initialize EOP data and the DE440s planetary ephemeris used for third-body
# perturbations and LCI <-> LFPA frame conversions.
bh.initialize_eop()
bh.load_common_spice_kernels()

# Initial epoch
epoch = bh.Epoch.from_datetime(2024, 3, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# Circular low lunar orbit (LLO) at 100 km altitude, expressed directly in
# the Moon-Centered Inertial (LCI) frame the propagator integrates in.
a = bh.R_MOON + 100e3
v = bh.periapsis_velocity(a, 0.0, gm=bh.GM_MOON)
state = np.array([a, 0.0, 0.0, 0.0, v, 0.0])

# Spacecraft parameters, indexed per lunar_default()'s ParameterSource
# assignments: [mass, _, _, srp_area, Cr]. lunar_default() has no drag
# model, so indices 1 and 2 (drag area, Cd) are unused placeholders.
params = np.array([500.0, 0.0, 0.0, 2.0, 1.3])

force_config = bh.ForceModelConfig.lunar_default()
force_config.validate()

prop = bh.NumericalOrbitPropagator(
    epoch,
    state,
    bh.NumericalPropagationConfig.default(),
    force_config,
    params,
)

# Propagate for 6 hours
final_epoch = epoch + 6.0 * 3600.0
prop.propagate_to(final_epoch)

# state_in_frame routes the propagator's native LCI state through the
# reference frame router into any other supported frame. LFPA is the Moon-
# fixed, DE440 principal-axis frame.
x0_lfpa = prop.state_in_frame(bh.ReferenceFrame.LFPA, epoch)
xf_lfpa = prop.state_in_frame(bh.ReferenceFrame.LFPA, final_epoch)

print(f"Initial epoch: {epoch}")
print(f"Final epoch:   {final_epoch}")
print("\nInitial state (LFPA, Moon-fixed):")
print(
    f"  Position (km): [{x0_lfpa[0] / 1e3:.3f}, {x0_lfpa[1] / 1e3:.3f}, {x0_lfpa[2] / 1e3:.3f}]"
)
print(f"  Velocity (m/s): [{x0_lfpa[3]:.3f}, {x0_lfpa[4]:.3f}, {x0_lfpa[5]:.3f}]")
print("\nFinal state (LFPA, Moon-fixed):")
print(
    f"  Position (km): [{xf_lfpa[0] / 1e3:.3f}, {xf_lfpa[1] / 1e3:.3f}, {xf_lfpa[2] / 1e3:.3f}]"
)
print(f"  Velocity (m/s): [{xf_lfpa[3]:.3f}, {xf_lfpa[4]:.3f}, {xf_lfpa[5]:.3f}]")

# Validate propagation completed and the orbit remains bound to the Moon
assert prop.current_epoch() == final_epoch
r_final = np.linalg.norm(xf_lfpa[:3])
assert bh.R_MOON < r_final < bh.R_MOON + 500e3
print("\nExample validated successfully!")
```


## See Also

- [Propagation Around Other Central Bodies](other_central_bodies.md) - Mars, custom bodies, and user-defined body-fixed frames
- [Lunar Reference Frames](../../frames/lunar_frames.md) - LCI/LFPA/LFME frame definitions
- [Reference Frame Router](../../frames/frame_transformations.md) - `state_in_frame` and cross-frame conversion
- [Force Models](force_models.md) - Building a `ForceModelConfig` from individual force terms
- [Third-Body Perturbations](../../orbital_dynamics/third_body.md) - Third-body acceleration model
- [Force Model Configuration API Reference](../../../library_api/propagators/force_model_config.md)