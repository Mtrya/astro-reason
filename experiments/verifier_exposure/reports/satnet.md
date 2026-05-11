# Verifier Exposure

satnet comparison across verifier exposure tiers.

Generated from the current `verifier_exposure` aggregate artifacts.

## Exposure Summary

| Exposure | Runs | Valid | Valid Rate | Mean Coverage | Mean Quality | Mean Score | Overall Statuses | Verifier Statuses |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| none | 10 | 3 | 1.0000 | - | - | 21.29 | missing_artifact: 7, success: 3 | missing_artifact: 7, valid: 3 |
| opaque | 10 | 9 | 1.0000 | - | - | 58.72 | missing_artifact: 1, success: 9 | missing_artifact: 1, valid: 9 |
| solver | 10 | 10 | 1.0000 | - | - | 58.77 | verified: 10 | verified: 10 |
| transparent | 10 | 9 | 1.0000 | - | - | 59.74 | success: 9, verifier_error: 1 | error: 1, valid: 9 |

## Exposure And System Summary

| Exposure | Kind | System | Runs | Valid | Valid Rate | Mean Coverage | Mean Quality | Mean Score | Overall Statuses |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| none | agent | codex | 5 | 2 | 1.0000 | - | - | 28.67 | missing_artifact: 3, success: 2 |
| none | agent | opencode_dpsk | 5 | 1 | 1.0000 | - | - | 13.91 | missing_artifact: 4, success: 1 |
| opaque | agent | codex | 5 | 5 | 1.0000 | - | - | 69.45 | success: 5 |
| opaque | agent | opencode_dpsk | 5 | 4 | 1.0000 | - | - | 47.98 | missing_artifact: 1, success: 4 |
| solver | solver | satnet_milp_claudet2022 | 5 | 5 | 1.0000 | - | - | 60.54 | verified: 5 |
| solver | solver | satnet_rl_ppo_goh2021 | 5 | 5 | 1.0000 | - | - | 57.00 | verified: 5 |
| transparent | agent | codex | 5 | 5 | 1.0000 | - | - | 69.95 | success: 5 |
| transparent | agent | opencode_dpsk | 5 | 4 | 1.0000 | - | - | 49.53 | success: 4, verifier_error: 1 |

## Cases

| Exposure | Split | Kind | System | Case | Artifact | Overall Status | Verifier Status | Valid | Duration (s) | Coverage | Quality | Score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| none | test | agent | codex | W10_2018 | present | success | valid | true | 1098.5 | - | - | 66.80 |
| none | test | agent | codex | W20_2018 | present | success | valid | true | 1625.2 | - | - | 76.54 |
| none | test | agent | codex | W30_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| none | test | agent | codex | W40_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| none | test | agent | codex | W50_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| none | test | agent | opencode_dpsk | W10_2018 | present | success | valid | true | 3791.0 | - | - | 69.55 |
| none | test | agent | opencode_dpsk | W20_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| none | test | agent | opencode_dpsk | W30_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| none | test | agent | opencode_dpsk | W40_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| none | test | agent | opencode_dpsk | W50_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| opaque | test | agent | codex | W10_2018 | present | success | valid | true | 987.7 | - | - | 78.09 |
| opaque | test | agent | codex | W20_2018 | present | success | valid | true | 4702.2 | - | - | 61.17 |
| opaque | test | agent | codex | W30_2018 | present | success | valid | true | 745.8 | - | - | 69.81 |
| opaque | test | agent | codex | W40_2018 | present | success | valid | true | 982.0 | - | - | 58.37 |
| opaque | test | agent | codex | W50_2018 | present | success | valid | true | 1586.4 | - | - | 79.83 |
| opaque | test | agent | opencode_dpsk | W10_2018 | present | success | valid | true | 7200.3 | - | - | 73.68 |
| opaque | test | agent | opencode_dpsk | W20_2018 | present | success | valid | true | 7200.7 | - | - | 71.67 |
| opaque | test | agent | opencode_dpsk | W30_2018 | present | success | valid | true | 7200.8 | - | - | 50.61 |
| opaque | test | agent | opencode_dpsk | W40_2018 | present | success | valid | true | 4152.5 | - | - | 43.94 |
| opaque | test | agent | opencode_dpsk | W50_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
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
| transparent | test | agent | codex | W10_2018 | present | success | valid | true | 3581.5 | - | - | 81.01 |
| transparent | test | agent | codex | W20_2018 | present | success | valid | true | 956.7 | - | - | 71.89 |
| transparent | test | agent | codex | W30_2018 | present | success | valid | true | 1488.7 | - | - | 62.26 |
| transparent | test | agent | codex | W40_2018 | present | success | valid | true | 1794.7 | - | - | 64.61 |
| transparent | test | agent | codex | W50_2018 | present | success | valid | true | 2893.3 | - | - | 69.95 |
| transparent | test | agent | opencode_dpsk | W10_2018 | present | success | valid | true | 3226.1 | - | - | 69.79 |
| transparent | test | agent | opencode_dpsk | W20_2018 | present | success | valid | true | 4144.6 | - | - | 63.90 |
| transparent | test | agent | opencode_dpsk | W30_2018 | present | verifier_error | error | - | 3101.3 | - | - | 0.0000 |
| transparent | test | agent | opencode_dpsk | W40_2018 | present | success | valid | true | 3675.2 | - | - | 49.85 |
| transparent | test | agent | opencode_dpsk | W50_2018 | present | success | valid | true | 3700.8 | - | - | 64.11 |
