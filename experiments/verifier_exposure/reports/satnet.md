# Verifier Exposure

satnet comparison across verifier exposure tiers.

Generated from the current `verifier_exposure` aggregate artifacts.

## Exposure Summary

| Exposure | Runs | Valid | Valid Rate | Mean Coverage | Mean Quality | Mean Score | Overall Statuses | Verifier Statuses |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| none | 10 | 3 | 1.0000 | - | - | 13.07 | missing_artifact: 7, success: 3 | missing_artifact: 7, valid: 3 |
| opaque | 10 | 9 | 1.0000 | - | - | 36.19 | success: 9, verifier_error: 1 | error: 1, valid: 9 |
| solver | 10 | 10 | 1.0000 | - | - | 58.77 | verified: 10 | verified: 10 |
| transparent | 10 | 10 | 1.0000 | - | - | 51.55 | success: 10 | valid: 10 |

## Exposure And System Summary

| Exposure | Kind | System | Runs | Valid | Valid Rate | Mean Coverage | Mean Quality | Mean Score | Overall Statuses |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| none | agent | codex | 5 | 3 | 1.0000 | - | - | 26.15 | missing_artifact: 2, success: 3 |
| none | agent | opencode_dpsk | 5 | 0 | - | - | - | 0.0000 | missing_artifact: 5 |
| opaque | agent | codex | 5 | 5 | 1.0000 | - | - | 31.98 | success: 5 |
| opaque | agent | opencode_dpsk | 5 | 4 | 1.0000 | - | - | 40.41 | success: 4, verifier_error: 1 |
| solver | solver | satnet_milp_claudet2022 | 5 | 5 | 1.0000 | - | - | 60.54 | verified: 5 |
| solver | solver | satnet_rl_ppo_goh2021 | 5 | 5 | 1.0000 | - | - | 57.00 | verified: 5 |
| transparent | agent | codex | 5 | 5 | 1.0000 | - | - | 61.99 | success: 5 |
| transparent | agent | opencode_dpsk | 5 | 5 | 1.0000 | - | - | 41.10 | success: 5 |

## Cases

| Exposure | Split | Kind | System | Case | Artifact | Overall Status | Verifier Status | Valid | Duration (s) | Coverage | Quality | Score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| none | test | agent | codex | W10_2018 | present | success | valid | true | 352.4 | - | - | 41.31 |
| none | test | agent | codex | W20_2018 | present | success | valid | true | 1764.1 | - | - | 65.14 |
| none | test | agent | codex | W30_2018 | present | success | valid | true | 562.7 | - | - | 24.29 |
| none | test | agent | codex | W40_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| none | test | agent | codex | W50_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| none | test | agent | opencode_dpsk | W10_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| none | test | agent | opencode_dpsk | W20_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| none | test | agent | opencode_dpsk | W30_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| none | test | agent | opencode_dpsk | W40_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| none | test | agent | opencode_dpsk | W50_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| opaque | test | agent | codex | W10_2018 | present | success | valid | true | 2288.2 | - | - | 31.70 |
| opaque | test | agent | codex | W20_2018 | present | success | valid | true | 507.6 | - | - | 25.94 |
| opaque | test | agent | codex | W30_2018 | present | success | valid | true | 769.2 | - | - | 21.81 |
| opaque | test | agent | codex | W40_2018 | present | success | valid | true | 583.9 | - | - | 21.79 |
| opaque | test | agent | codex | W50_2018 | present | success | valid | true | 1111.2 | - | - | 58.66 |
| opaque | test | agent | opencode_dpsk | W10_2018 | present | success | valid | true | 3618.2 | - | - | 55.74 |
| opaque | test | agent | opencode_dpsk | W20_2018 | present | success | valid | true | 4915.5 | - | - | 46.89 |
| opaque | test | agent | opencode_dpsk | W30_2018 | present | success | valid | true | 7202.5 | - | - | 68.33 |
| opaque | test | agent | opencode_dpsk | W40_2018 | present | success | valid | true | 4063.2 | - | - | 31.09 |
| opaque | test | agent | opencode_dpsk | W50_2018 | present | verifier_error | error | - | 3051.5 | - | - | 0.0000 |
| solver | test | solver | satnet_milp_claudet2022 | W10_2018 | baseline | verified | verified | true | - | - | - | 68.53 |
| solver | test | solver | satnet_milp_claudet2022 | W20_2018 | baseline | verified | verified | true | - | - | - | 68.22 |
| solver | test | solver | satnet_milp_claudet2022 | W30_2018 | baseline | verified | verified | true | - | - | - | 62.17 |
| solver | test | solver | satnet_milp_claudet2022 | W40_2018 | baseline | verified | verified | true | - | - | - | 45.00 |
| solver | test | solver | satnet_milp_claudet2022 | W50_2018 | baseline | verified | verified | true | - | - | - | 58.75 |
| solver | test | solver | satnet_rl_ppo_goh2021 | W10_2018 | baseline | verified | verified | true | - | - | - | 61.25 |
| solver | test | solver | satnet_rl_ppo_goh2021 | W20_2018 | baseline | verified | verified | true | - | - | - | 59.50 |
| solver | test | solver | satnet_rl_ppo_goh2021 | W30_2018 | baseline | verified | verified | true | - | - | - | 57.75 |
| solver | test | solver | satnet_rl_ppo_goh2021 | W40_2018 | baseline | verified | verified | true | - | - | - | 50.25 |
| solver | test | solver | satnet_rl_ppo_goh2021 | W50_2018 | baseline | verified | verified | true | - | - | - | 56.25 |
| transparent | test | agent | codex | W10_2018 | present | success | valid | true | 928.6 | - | - | 78.45 |
| transparent | test | agent | codex | W20_2018 | present | success | valid | true | 1534.8 | - | - | 74.70 |
| transparent | test | agent | codex | W30_2018 | present | success | valid | true | 1181.0 | - | - | 74.02 |
| transparent | test | agent | codex | W40_2018 | present | success | valid | true | 663.1 | - | - | 22.78 |
| transparent | test | agent | codex | W50_2018 | present | success | valid | true | 2951.0 | - | - | 59.99 |
| transparent | test | agent | opencode_dpsk | W10_2018 | present | success | valid | true | 3198.9 | - | - | 31.83 |
| transparent | test | agent | opencode_dpsk | W20_2018 | present | success | valid | true | 6544.1 | - | - | 51.05 |
| transparent | test | agent | opencode_dpsk | W30_2018 | present | success | valid | true | 3580.6 | - | - | 40.17 |
| transparent | test | agent | opencode_dpsk | W40_2018 | present | success | valid | true | 3487.9 | - | - | 38.95 |
| transparent | test | agent | opencode_dpsk | W50_2018 | present | success | valid | true | 3221.8 | - | - | 43.51 |
