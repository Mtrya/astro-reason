# Stereo Imaging Kimi Case Study: Valid Observations, Mirrored Footprints

This note diagnoses the `kimi_cli` stereo imaging runs in the `main_agentic` report. Kimi's aggregate failure was not primarily a parser crash or a lack of orbital-mechanics effort. In three of the five cases, it built schedules that the verifier accepted as hard-valid observation schedules, but the commanded boresight footprints were mirrored away from the target AOIs, so the derived stereo products had zero overlap. The other two cases failed for simpler reasons: one used an ignored action type, and one submitted only a single observation.

## Evidence Base

Aggregate outcomes come from `experiments/main_agentic/reports/stereo_imaging.md`. Behavioral evidence comes from the tracked trace exports:

- `experiments/main_agentic/reports/traces/data/events/stereo_imaging__kimi_cli__test__case_0001.js`
- `experiments/main_agentic/reports/traces/data/events/stereo_imaging__kimi_cli__test__case_0002.js`
- `experiments/main_agentic/reports/traces/data/events/stereo_imaging__kimi_cli__test__case_0003.js`
- `experiments/main_agentic/reports/traces/data/events/stereo_imaging__kimi_cli__test__case_0004.js`
- `experiments/main_agentic/reports/traces/data/events/stereo_imaging__kimi_cli__test__case_0005.js`

Contract evidence comes from `experiments/_fragments/prompts/stereo_imaging/README.default.md`, the benchmark config `experiments/main_agentic/benchmarks/stereo_imaging.yaml`, and the verifier implementation under `benchmarks/stereo_imaging/verifier/`. The evaluated space agent saw an opaque verifier helper and the rendered README, not this source code; the source is used here only to explain retrospectively why the verifier produced the observed metrics.

I also replayed the saved local final `solution.json` files against the repository verifier while preparing this report. Those ignored run outputs are useful diagnostics, but the primary causal claims below are anchored to tracked aggregate rows, tracked traces, and the verifier contract.

## Aggregate Outcome

The aggregate report marks all five Kimi submissions as valid, but with almost no objective value:

| Case | Valid | Duration (s) | normalized_quality | coverage_ratio |
| --- | --- | ---: | ---: | ---: |
| `case_0001` | true | 7200.6 | 0.0000 | 0.0000 |
| `case_0002` | true | 7200.8 | 0.0125 | 0.0165 |
| `case_0003` | true | 7200.9 | 0.0000 | 0.0000 |
| `case_0004` | true | 7200.2 | 0.0000 | 0.0000 |
| `case_0005` | true | 4600.2 | 0.0032 | 0.0071 |

The key diagnostic is that `valid=true` does not mean useful stereo was created. The stereo benchmark separates hard action validity from product quality. A schedule can contain observations that satisfy horizon, access, duration, and slew rules while still producing no valid stereo products. Coverage and normalized quality come only from verifier-derived stereo or tri-stereo products.

## Intended Contract

The assembled workspace README tells the space agent to write a single `solution.json` object with an `actions` array. Each interpreted action must include:

```json
{
  "type": "observation",
  "satellite_id": "sat_worldview_1",
  "target_id": "rugged_043",
  "start_time": "2026-04-22T08:14:18Z",
  "end_time": "2026-04-22T08:14:28Z",
  "off_nadir_along_deg": 11.5,
  "off_nadir_across_deg": 17.8
}
```

The verifier implements that contract directly in `benchmarks/stereo_imaging/verifier/io.py`: `load_solution_actions` reads top-level `actions`, then silently skips rows whose `type` is not exactly `"observation"`. It parses only raw observation actions. It does not parse submitted stereo pairs, product claims, footprints, overlap fractions, or quality scores.

After parsing hard-valid observations, the verifier derives stereo products. Same-target observation pairs are allowed when they are same-satellite same-pass or allowed cross-satellite pairs, satisfy the time bound, and pass geometry checks. Product validity depends on overlap, convergence, and pixel scale ratio. The overlap check is not a symbolic "same target" check. It builds a pushbroom strip centerline from each commanded boresight ray, projects those strip centerlines into the target-local plane, and Monte Carlo samples the AOI disk. A pair is overlap-valid only when sampled points fall inside both strips.

## Immediate Symptoms

Kimi usually found the README and the verifier. The issue is that it kept building private geometry code that was almost, but not quite, aligned with the verifier's local-frame convention.

The traces show several recurring signals:

- `case_0001` reads the README and runs the verifier on an empty solution early, but the final raw actions use `type: "stereoscopic"`, which is not parsed as an observation.
- `case_0002` reads the README and verifier help, then spends the run building access-window and stereo-pair code around Brahe and custom geometry.
- `case_0003` begins after context compaction with an explicit focus on why verifier pair evaluations have `overlap_fraction=0.0`.
- `case_0005` reaches a late diagnosis in stdout: the target is within access, but the boresight azimuth is far from the target direction, so the strip is centered elsewhere and overlap is zero. The run then hits a Kimi usage limit before completing a robust repair.

The pattern is therefore not "Kimi did not know there was a verifier." It did use the verifier. The problem is that the verifier feedback was interpreted through a private geometry model that had the across-track sign wrong.

## The Cross-Track Sign Trap

The stereo verifier defines satellite local axes in `benchmarks/stereo_imaging/verifier/engine.py` as:

```python
nadir = -sat_pos_m / np.linalg.norm(sat_pos_m)
along = sat_vel_mps - float(np.dot(sat_vel_mps, nadir)) * nadir
along = along / np.linalg.norm(along)
across = np.cross(along, nadir)
```

The boresight vector is then:

```python
vec = (
    nadir_hat
    + tan(off_nadir_along_deg) * along_hat
    + tan(off_nadir_across_deg) * across_hat
)
```

Many natural implementations instead define the cross-track axis as `np.cross(nadir, along)`. That is the negative of the verifier's `np.cross(along, nadir)`. If a solver computes steering angles in that opposite frame and submits them unchanged, the submitted `off_nadir_across_deg` points the boresight to the wrong side of the satellite ground track.

This bug is easy to miss because it does not necessarily violate hard action constraints. The combined off-nadir magnitude is symmetric under across-track sign reversal. Solar elevation and access interval membership also depend on whether the target is accessible to the satellite, not whether the commanded boresight strip is centered over the AOI. The verifier can therefore report `valid=true` while the footprint overlap is zero.

## Was The Handedness Specified?

The rendered workspace README does not fully specify the handedness of the satellite local frame. It says `off_nadir_along_deg` tilts along the flight direction and `off_nadir_across_deg` tilts cross-track in the satellite local frame, then gives the boresight formula:

```text
nadir_hat
+ tan(off_nadir_along_deg) * along_hat
+ tan(off_nadir_across_deg) * across_hat
```

This defines how to use `along_hat` and `across_hat` once they are known, but it does not say whether `across_hat = along_hat × nadir_hat` or `across_hat = nadir_hat × along_hat`. Those two options are mirror images.

Both choices are defensible as coordinate conventions if stated up front. There is no universal mathematical rule that makes only one of them "correct" for an abstract local satellite frame. Remote-sensing and flight-dynamics systems often choose a right-handed or left-handed local orbital frame depending on axis naming, whether the radial axis points nadir or zenith, and whether cross-track is aligned with orbit normal or its negative. Once a benchmark verifier chooses a convention, that convention is authoritative for submitted signs, but the README did not expose that sign choice with code-level precision.

This makes the Kimi failure more subtle than a simple hallucination. Kimi still had a verifier-feedback obligation: a few two-action tests with boresight-derived footprints would have exposed the sign error. But the public workspace contract left room for the opposite cross-track convention, and Kimi picked the other handedness.

## Why Zero Overlap Follows

The verifier's overlap machinery is explicit. `_strip_polyline_en` samples each observation window every 8 seconds, intersects the commanded boresight ray with the WGS84 ellipsoid, and converts each intercept into a target-local east/north point. `_monte_carlo_overlap_fraction` samples random points in the AOI disk and counts how many are within each strip half-width from both strip polylines.

If the across-track sign is mirrored, the strip centerline can land hundreds of kilometers from the AOI even though the target itself was accessible. In a representative local replay of Kimi `case_0002`, the first evaluated pair targeted `rugged_043` with `sat_worldview_1`. The official pair diagnostics had:

- `stereo_mode = same_satellite_same_pass`
- `time_separation_s = 30.0`
- `gamma_deg = 23.89`
- `pixel_scale_ratio = 1.0006`
- `overlap_fraction = 0.0`

Convergence and pixel scale were fine. The failing term was overlap. Recomputing the strip geometry showed why: as submitted, each strip centerline missed the target center by about 333 km, while the strip half-width was about 5.1 km and the AOI radius was about 2.6 km. Negating only `off_nadir_across_deg` moved the centerline to about 0.5 km from the target center.

The same replay pattern held across the main zero-overlap cases:

| Case | Interpreted observations | Submitted target-near strips | Negated-across target-near strips | Interpretation |
| --- | ---: | ---: | ---: | --- |
| `case_0002` | 242 | 6 | 242 | Across sign mismatch dominates. |
| `case_0003` | 70 | 1 | 70 | Across sign mismatch dominates. |
| `case_0005` | 278 | 3 | 278 | Across sign mismatch dominates. |

Here "target-near" means the target center fell within the strip half-width plus AOI radius buffer in the verifier's target-local plane. This is a diagnostic replay, not an aggregate metric, but it explains the tracked trace symptom: Kimi could build hard-valid actions and good-looking convergence pairs while the overlap sampler still found zero points inside both strips.

## Mirrored-Solution Counterfactual

To test whether the sign mismatch was merely a local explanation or a score-level cause, I generated temporary copies of Kimi's final `solution.json` files and negated every `off_nadir_across_deg`. I then reran the official repository verifier on those mirrored copies. For `case_0001`, I also tested a variant that changed the ignored `type: "stereoscopic"` rows to `type: "observation"`.

The counterfactual results were:

| Case | Original coverage | Original quality | Mirrored coverage | Mirrored quality | Notes |
| --- | ---: | ---: | ---: | ---: | --- |
| `case_0001` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | Mirroring alone still leaves ignored action types; type-fixing makes the file invalid because one action exceeds max off-nadir. |
| `case_0002` | 0.0165 | 0.0125 | 0.8926 | 0.7129 | Sign flip converts 2 valid pairs into 108 valid pairs. |
| `case_0003` | 0.0000 | 0.0000 | 0.1983 | 0.1263 | Sign flip converts 0 valid pairs into 24, but the schedule remains sparse. |
| `case_0004` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | Only one observation; no stereo pair exists. |
| `case_0005` | 0.0071 | 0.0032 | 0.9716 | 0.6596 | Sign flip converts 1 valid pair into 137 valid pairs. |

This is the strongest evidence that the cross-track sign issue was not a cosmetic convention disagreement. In `case_0002` and `case_0005`, Kimi had already produced schedules with enough timing, access, and target coverage structure to score well once the across-track sign was mirrored back into the verifier's convention. `case_0003` also improves, though less dramatically because the submitted schedule has far fewer observations and pairs. `case_0001` and `case_0004` remain separate failure modes.

## Case-By-Case Failure Mode

Not all five cases failed for the same immediate reason.

`case_0001` failed first on action type. Kimi wrote two raw actions, but the action `type` was `"stereoscopic"` rather than `"observation"`. The verifier skipped both rows, resulting in a valid empty interpreted schedule. The across-track sign of those ignored rows was not the decisive cause of the official zero score.

`case_0002` is the clean mirrored-footprint case. Kimi produced many interpreted observations and many pair evaluations. The final score was nonzero only because two pairs happened to survive; almost all candidate pairs failed overlap. Diagnostic replay shows every interpreted observation became target-near when the across-track sign was negated.

`case_0003` is also a mirrored-footprint case. The trace itself begins after compaction with "Debugging why valid stereo pairs get `overlap_fraction=0.0`." It records that access intervals and convergence could be valid while overlap stayed zero. Later in the trace, Kimi disassembles the opaque verifier and discovers that the verifier uses `across = np.cross(along, nadir)`, the opposite of its own convention. That is the right diagnosis, but too late to produce a robust final solution.

`case_0004` did not meaningfully exercise stereo geometry. The final submission contained only one interpreted observation, with zero along and across steering. With one observation, no stereo pair can be formed. This is a schedule-construction failure rather than a cross-track sign failure.

`case_0005` is another mirrored-footprint case with a late self-diagnosis. Kimi's stdout says the target can be within the satellite field of regard while the commanded boresight points somewhere else. It explicitly concludes that the strip is centered on the boresight ground trace rather than the target and that this explains zero overlap. The run then stops under a Kimi quota error, leaving a mostly hard-valid but low-overlap schedule.

## Why Kimi Did Not Recover

The failure persisted because Kimi optimized a private approximation before fully aligning it with the verifier's coordinate convention. It correctly learned several pieces of the benchmark:

- the solution must normally contain raw `observation` actions,
- the local verifier should be used,
- access interval membership and stereo product validity are separate,
- overlap is based on strips, not merely same target and convergence.

But the local-frame convention was a single-sign error in the steering interface. That is a high-leverage error: every observation can be individually valid, every target can look accessible, and convergence can be in range, while the strips all miss the AOI. The official metric then collapses because coverage comes only from valid products.

The traces also show cognitive lock-in. Once Kimi had a private access and steering model, verifier failures were debugged as access-window, slant-range, solar, duration, or strip-width problems. Those are plausible suspects, but they delayed the simpler conclusion: the submitted across angle was expressed in the wrong handedness. In `case_0003`, Kimi eventually finds the sign mismatch by inspecting the verifier bytecode, but that discovery happens deep into the run and is not converted into a complete final repair.

## Comparison To Opencode DPSK

The neighboring `opencode_dpsk` stereo traces make the Kimi diagnosis more credible. DPSK also encountered zero-overlap and access-model problems, but in its successful `case_0003` and high-scoring invalid `case_0004` traces, its todo list and stdout explicitly include "Fix zero overlap: sign of across_hat was wrong" or "Fix across-direction sign convention." Once that convention was fixed, DPSK could create many valid stereo products. It still had other failures, especially hard-validity drift in `case_0004`, but the cross-track repair unlocked product overlap.

Kimi reached the same insight in places, but did not consistently apply it before timeout or failure. The contrast suggests the zero-overlap symptom was not an unavoidable property of the case data. It was a solver-interface convention bug.

## Root Cause

The root cause is an authority-and-frame-binding failure. Kimi read much of the benchmark contract and used the verifier, but it did not bind its internal steering coordinate system to the verifier's exact signed local frame early enough. The benchmark asks for signed `off_nadir_along_deg` and `off_nadir_across_deg`, not just a scalar off-nadir angle. A wrong sign convention in one axis turns target-pointing commands into mirrored ground footprints.

The immediate official failures split into three categories:

- ignored schema in `case_0001`,
- mirrored boresight footprints in `case_0002`, `case_0003`, and `case_0005`,
- insufficient schedule construction in `case_0004`.

The recurring benchmark-specific failure is the mirrored footprint problem. It is why hard-valid observations did not become valid stereo products.

## Implications

For interpreting the aggregate, Kimi should not be described as simply unable to compute access windows. It often computed enough access and timing structure to produce hard-valid schedules. The missing piece was converting target access into verifier-aligned target-pointed strips.

For future prompts or workspace contracts, the important warning is that signed steering conventions matter. The README already defines the boresight vector formula, but a stronger diagnostic hint could say that the verifier's across-track axis follows `along_hat × nadir_hat`, and that a solution with many valid observations but zero overlap likely has boresight/strip centering wrong.

For verifier diagnostics, this benchmark could expose a helpful warning when many derived observations are hard-valid but their boresight strip centerlines never pass near the target AOI. That would preserve the benchmark rule while turning the current silent symptom, `overlap_fraction=0.0`, into a more actionable failure mode.
