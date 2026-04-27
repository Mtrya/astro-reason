# Solver Profiles

These profiles define explicit compute envelopes for the MCLP+TEG relay solver.

## `smoke`

Lightweight contract/smoke profile. This intentionally matches the historical default behavior: 24 candidates, small MILP bounds, and a 300 second informational budget.

Use this for quick local checks and CI-safe solver-contract validation.

## `reproduction`

Meaningful reproduction profile. This increases candidate density and budget settings so public-case runs exercise the MCLP+TEG adaptation beyond smoke defaults. It uses the `route_aware` scheduler so selected links are driven by complete endpoint-to-endpoint demand paths instead of independent edge utility alone.

On the current public cases, this profile generates roughly 300 candidate satellites before MCLP selection.

Use this for intermediate reproduction evidence after candidate and scheduler scaling have been checked.

## `quality`

Strongest intended optimization profile. This is the profile that should become the final canonical metrics profile once Phases 2 and 3 have hardened scaling behavior. It uses the `route_aware` scheduler as the scalable fallback until a larger full-horizon MILP is justified by canonical experiments.

On the current public cases, this profile generates roughly 1000 candidate satellites before MCLP selection.

Use this for final public-case metrics only after the solver records whether larger MCLP and scheduler bounds truly executed or fell back.

## Override Rules

`src.solve` loads `profiles/<name>.json` and then recursively overlays any provided `config.json`. Existing invocations without a profile resolve to `smoke`, so the historical solver contract remains intact while `status.json` names the envelope explicitly.
