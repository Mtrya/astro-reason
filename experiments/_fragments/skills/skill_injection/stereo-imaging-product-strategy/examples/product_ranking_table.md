# Product Ranking Table

Use a table like this while building or repairing a schedule. The entries are illustrative, not case answers.

| target | scene | mode | obs count | convergence | overlap risk | pixel-scale risk | anchor | timeline cost | decision |
|---|---|---|---:|---|---|---|---|---|---|
| `t_001` | `urban_structured` | cross-satellite pair | 2 | in 8-18 deg band | low | low | n/a | low | seed early |
| `t_002` | `vegetated` | same-satellite same-pass pair | 2 | high for scene | medium | medium | n/a | high | keep as fallback, seek gentler pair |
| `t_003` | `rugged` | tri-stereo | 3 | at least two good pairs | low | low | yes | medium | upgrade after pair coverage |
| `t_004` | `open` | cross-satellite pair | 2 | below 15 deg | low | low | n/a | low | improve baseline if coverage already stable |
| `t_005` | `urban_structured` | same-satellite same-pass pair | 2 | good | high | low | n/a | high | move inward or replace |

## Ranking Rules

Sort candidate products by:

1. New target coverage before duplicate products.
2. Expected validity margin around overlap, convergence, pixel-scale ratio, access, solar, and slew constraints.
3. Scene-appropriate convergence rather than maximum convergence.
4. Lower same-satellite timeline cost.
5. Higher expected best-per-target quality.
6. Stable target/product ID.

## Decisions

- **Seed early:** good first product for an uncovered target.
- **Keep as fallback:** useful coverage but likely not final quality.
- **Upgrade after pair coverage:** tri-stereo candidate that should not replace broad pair coverage work.
- **Improve baseline:** product is probably valid but weak in geometry.
- **Move inward or replace:** product likely fails or barely passes overlap/access margins.

## Product Notes Template

```text
target:
mode:
observations:
expected reason it is valid:
main risk:
if verifier fails, first adjustment:
if verifier passes, next upgrade:
```

The "expected reason it is valid" line is the most important. If you cannot explain why a pair or triple should pass product rules, do not spend many actions on it.
