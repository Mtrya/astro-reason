# Rogers MMRT/MART Profiles

`fair_reproduction/config.yaml` is a non-CI profile for broader
benchmark-adapted RGT/APC slot evaluation. It preserves the Rogers common-slot
RAAN/phase relation while clipping the reference semi-major axis to each case's
valid altitude bounds.

The default solver configuration and main-solver profile remain bounded smoke
runs using `slot_library_mode: circular_grid`.

## Latest Evidence

The 2026-04-26 fair-profile public-case run used solver-local PuLP/CBC and
reported exact design and binary-scheduler solves on all five public
`revisit_constellation` cases. It is still `NOT_YET` valid as a fair
reproduction profile: every public case failed official verification because
selected RGT/APC states clipped to the case maximum altitude were reported just
above the benchmark apogee bound.

Observed fair-profile solve times were about 245-272 seconds per case, with
48-75 selected windows before verification failure. The smoke main-solver
profile remains the valid CI/default profile.
