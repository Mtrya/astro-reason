# Propagation Around Other Central Bodies

Beyond Earth and the cislunar bodies, `NumericalOrbitPropagator` integrates about any body a `CentralBody` can describe. Mars has a dedicated built-in variant with a `mars_default()` force model; every other body is reached through `CentralBody.from_naif_id` (for bodies in an embedded table) or `CentralBody.Custom` (for anything else, including bodies with no catalogued NAIF ID). Bodies without SPICE orientation data can still be given a body-fixed frame through a user-supplied rotation callback.

## Mars

`CentralBody::Mars` integrates in the Mars-Centered Inertial (`MCI`) frame, centered on the Mars body center (NAIF ID 499), and reports body-fixed states in `MCMF`.

| `CentralBody` | NAIF ID | Inertial frame | Fixed frame |
|---|---|---|---|
| `Mars` | 499 | `MCI` | `MCMF` |

`ForceModelConfig.mars_default()` pairs it with a Mars-tuned force model:

| Constructor | Central body | Gravity | Drag | SRP occultation | Third bodies |
|---|---|---|---|---|---|
| `mars_default()` | `Mars` | 50x50 GGM2B (`ggm2bc80`) | Exponential | Mars | Sun |

`mars_default()` requires a spacecraft parameter vector `[mass, drag_area, Cd, srp_area, Cr]` at propagator construction; all five slots are used. Configuration validation runs automatically when the propagator is constructed; `.validate()` can also be called directly to check a configuration earlier.

### Example: Propagating an Orbit About Mars

The example below builds a Mars force model with `ForceModelConfig.mars_default()`, propagates a low Mars orbit for six hours, and reports the initial and final state in the Mars-fixed MCMF frame via `state_in_frame`.


```python
import numpy as np
import brahe as bh

# Initialize EOP data and the DE440s planetary ephemeris used for third-body
# perturbations and ECI <-> MCI frame conversions.
bh.initialize_eop()
bh.load_common_spice_kernels()

# Initial epoch
epoch = bh.Epoch.from_datetime(2024, 3, 1, 0, 0, 0.0, 0.0, bh.TimeSystem.UTC)

# Circular low Mars orbit at 400 km altitude, expressed directly in the
# Mars-Centered Inertial (MCI) frame the propagator integrates in.
a = bh.R_MARS + 400e3
v = bh.periapsis_velocity(a, 0.0, gm=bh.GM_MARS)
state = np.array([a, 0.0, 0.0, 0.0, v, 0.0])

# Spacecraft parameters, indexed per mars_default()'s ParameterSource
# assignments: [mass, drag_area, Cd, srp_area, Cr].
params = np.array([500.0, 2.0, 2.2, 2.0, 1.3])

force_config = bh.ForceModelConfig.mars_default()
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

# state_in_frame routes the propagator's native MCI state through the
# reference frame router into any other supported frame. MCMF is the
# Mars-fixed, IAU/WGCCRE body-fixed frame.
x0_mcmf = prop.state_in_frame(bh.ReferenceFrame.MCMF, epoch)
xf_mcmf = prop.state_in_frame(bh.ReferenceFrame.MCMF, final_epoch)

print(f"Initial epoch: {epoch}")
print(f"Final epoch:   {final_epoch}")
print("\nInitial state (MCMF, Mars-fixed):")
print(
    f"  Position (km): [{x0_mcmf[0] / 1e3:.3f}, {x0_mcmf[1] / 1e3:.3f}, {x0_mcmf[2] / 1e3:.3f}]"
)
print(f"  Velocity (m/s): [{x0_mcmf[3]:.3f}, {x0_mcmf[4]:.3f}, {x0_mcmf[5]:.3f}]")
print("\nFinal state (MCMF, Mars-fixed):")
print(
    f"  Position (km): [{xf_mcmf[0] / 1e3:.3f}, {xf_mcmf[1] / 1e3:.3f}, {xf_mcmf[2] / 1e3:.3f}]"
)
print(f"  Velocity (m/s): [{xf_mcmf[3]:.3f}, {xf_mcmf[4]:.3f}, {xf_mcmf[5]:.3f}]")

# Validate propagation completed and the orbit remains bound to Mars
assert prop.current_epoch() == final_epoch
r_final = np.linalg.norm(xf_mcmf[:3])
assert bh.R_MARS < r_final < bh.R_MARS + 1000e3
print("\nExample validated successfully!")
```


## Selecting a Central Body by NAIF ID

`CentralBody.from_naif_id(naif_id)` constructs one of the five built-in variants for their NAIF IDs (`399` &rarr; `Earth`, `301` &rarr; `Moon`, `4` or `499` &rarr; `Mars`, `3` &rarr; `EMB`, `0` &rarr; `SSB`), or a pre-populated `Custom` body for a fixed table of other commonly used bodies: Mercury, Venus, Jupiter, Saturn, Uranus, Neptune, the Sun, Phobos, Deimos, Enceladus, and Titan. Each table entry carries the body's GM and radius, and its `fixed_frame` is set to `BodyFixedIAU(naif_id)` when the body has a compiled-in IAU/WGCCRE rotation model (true for every body in the table). A NAIF ID outside this set returns an error &mdash; use `CentralBody.Custom` directly for those.

## User-Defined Central Bodies

For a body outside the built-in table, construct `CentralBody.Custom(name, naif_id, gm, radius=None, omega=None, fixed_frame=None)` with the body's physical properties. For a body without a catalogued NAIF ID (e.g. a newly observed asteroid), self-assign a unique **negative** `naif_id`, mirroring NAIF's own convention for non-catalogued objects. The ID is used for frame identity and force-model validation; ephemeris queries against it will surface an SPK lookup error unless a kernel covering that ID is loaded.

Pair a custom body with a force model using `ForceModelConfig.for_body(central_body, gravity, drag=None, srp=None, third_body=None, relativity=False, mass=None)`, which fills in the frame-transformation default so callers specify only the terms that vary per body. Validation runs automatically when the propagator is constructed, rejecting options incompatible with the central body (for example, spherical-harmonic gravity requires the body to have a `fixed_frame`); `.validate()` can also be called directly to check a configuration earlier.

## Body-Fixed Frames Without SPICE Data

A custom body that has no SPICE orientation kernel and no compiled-in IAU model can still be given a rotating body-fixed frame. Register a rotation callback with `register_custom_frame(key, rotation, omega=None)`:

- `rotation` is a callback function: it receives an `Epoch` and returns the 3x3 ICRF&rarr;body-fixed rotation matrix at that instant.
- `omega` is an optional second callback function: it receives an `Epoch` and returns the frame's angular velocity vector (rad/s), used for the exact velocity transport term. When omitted, the angular velocity is derived numerically by central differencing of `rotation`.
- `key` is an arbitrary integer handle that names the registered callback. It does **not** need to match (and is unrelated to) the central body's NAIF ID; the body's NAIF ID appears separately as the `center` of the frame variant.

Reference the registered frame as `ReferenceFrame.BodyFixedCustom(center, key)`, using the same `key`, and set it as the custom body's `fixed_frame`. This enables support for user-defined orientation models, enabling the framework to extend to additional bodies without needing hard-coded support for them in the library. See [Generic NAIF-ID Variants](../../frames/frame_transformations.md#generic-naif-id-variants) for the frame-router side.

### Example: Registering a Custom Body-Fixed Frame

The example below registers a uniform spin state for an uncatalogued body (self-assigned negative NAIF ID), converts a state between the body's inertial and body-fixed frames, and verifies that a co-rotating surface point is stationary in the body-fixed frame. No kernels are required.


```python
import brahe as bh
import numpy as np

# An uncatalogued body (e.g. a newly observed asteroid): self-assign a unique
# negative NAIF ID for its center, mirroring NAIF's convention.
CENTER = -20001

# The frame key is an arbitrary integer handle. It is unrelated to NAIF IDs;
# it only names the callback registered below so BodyFixedCustom can look it
# up at evaluation time.
KEY = 1042

t0 = bh.Epoch.from_date(2024, 3, 1, bh.TimeSystem.TDB)
rate = 2.0e-4  # spin rate (rad/s), ~8.7 h rotation period


# The rotation callback is a proper function: it receives an Epoch and returns
# the 3x3 ICRF -> body-fixed rotation matrix at that instant. Here the body
# spins uniformly about its z-axis.
def rotation(epc):
    theta = rate * (epc - t0)
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])


# The optional omega callback is also a function of the epoch, returning the
# frame's angular velocity vector (rad/s) for the exact velocity transport
# term. Omitting it falls back to numeric differentiation of `rotation`.
def omega(epc):
    return np.array([0.0, 0.0, rate])


bh.register_custom_frame(KEY, rotation, omega)

inertial = bh.ReferenceFrame.BodyCenteredICRF(CENTER)
fixed = bh.ReferenceFrame.BodyFixedCustom(CENTER, KEY)

# Convert an inertial state about the body into its body-fixed frame. Both
# frames share the same center, so no ephemeris kernel is needed.
epc = t0 + 600.0
x_inertial = np.array([7.0e5, -2.0e5, 3.0e5, 10.0, 25.0, -5.0])
x_fixed = bh.state_frame_to_frame(inertial, fixed, epc, x_inertial)

print(f"Epoch: {epc}")
print(f"Inertial state:   {np.array2string(x_inertial, precision=3)}")
print(f"Body-fixed state: {np.array2string(x_fixed, precision=3)}")

# Round trip back to the inertial frame recovers the input.
x_back = bh.state_frame_to_frame(fixed, inertial, epc, x_fixed)
np.testing.assert_allclose(x_back, x_inertial, atol=1e-6)

# A point co-rotating with the body is stationary in the body-fixed frame.
r_surf = rotation(epc).T @ np.array([1.0e3, 0.0, 0.0])
v_surf = np.cross(omega(epc), r_surf)
x_surf_fixed = bh.state_frame_to_frame(
    inertial, fixed, epc, np.concatenate([r_surf, v_surf])
)
np.testing.assert_allclose(x_surf_fixed[3:], 0.0, atol=1e-9)

bh.unregister_custom_frame(KEY)
print("\nExample validated successfully!")
```


## See Also

- [Cislunar and Lunar Propagation](cislunar_lunar_propagation.md) - `Moon`/`EMB` central bodies and barycenter third-body physics
- [Mars Reference Frames](../../frames/mars_frames.md) - MCI/MCMF frame definitions
- [Reference Frame Router](../../frames/frame_transformations.md) - `ReferenceFrame`, `BodyFixedCustom`, and `register_custom_frame`
- [Force Models](force_models.md) - Building a `ForceModelConfig` from individual force terms
- [Force Model Configuration API Reference](../../../library_api/propagators/force_model_config.md)