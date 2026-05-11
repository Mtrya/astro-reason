# Verifier Exposure

satnet comparison across verifier exposure tiers.

Generated from the current `verifier_exposure` aggregate artifacts.

## Exposure Summary

| Exposure | Runs | Valid | Valid Rate | Mean Coverage | Mean Quality | Mean Score | Overall Statuses | Verifier Statuses |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| none | 10 | 0 | - | - | - | 0.0000 | missing_artifact: 10 | missing_artifact: 10 |
| opaque | 10 | 1 | 1.0000 | - | - | 7.8095 | missing_artifact: 9, success: 1 | missing_artifact: 9, valid: 1 |
| solver | 10 | 10 | 1.0000 | - | - | 58.77 | verified: 10 | verified: 10 |
| transparent | 10 | 0 | - | - | - | 0.0000 | missing_artifact: 10 | missing_artifact: 10 |

## Exposure And System Summary

| Exposure | Kind | System | Runs | Valid | Valid Rate | Mean Coverage | Mean Quality | Mean Score | Overall Statuses |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| none | agent | codex | 5 | 0 | - | - | - | 0.0000 | missing_artifact: 5 |
| none | agent | opencode_dpsk | 5 | 0 | - | - | - | 0.0000 | missing_artifact: 5 |
| opaque | agent | codex | 5 | 1 | 1.0000 | - | - | 15.62 | missing_artifact: 4, success: 1 |
| opaque | agent | opencode_dpsk | 5 | 0 | - | - | - | 0.0000 | missing_artifact: 5 |
| solver | solver | satnet_milp_claudet2022 | 5 | 5 | 1.0000 | - | - | 60.54 | verified: 5 |
| solver | solver | satnet_rl_ppo_goh2021 | 5 | 5 | 1.0000 | - | - | 57.00 | verified: 5 |
| transparent | agent | codex | 5 | 0 | - | - | - | 0.0000 | missing_artifact: 5 |
| transparent | agent | opencode_dpsk | 5 | 0 | - | - | - | 0.0000 | missing_artifact: 5 |

## Cases

| Exposure | Split | Kind | System | Case | Artifact | Overall Status | Verifier Status | Valid | Duration (s) | Coverage | Quality | Score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| none | test | agent | codex | W10_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| none | test | agent | codex | W20_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| none | test | agent | codex | W30_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| none | test | agent | codex | W40_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| none | test | agent | codex | W50_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| none | test | agent | opencode_dpsk | W10_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| none | test | agent | opencode_dpsk | W20_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| none | test | agent | opencode_dpsk | W30_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| none | test | agent | opencode_dpsk | W40_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| none | test | agent | opencode_dpsk | W50_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| opaque | test | agent | codex | W10_2018 | present | success | valid | true | 987.7 | - | - | 78.09 |
| opaque | test | agent | codex | W20_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| opaque | test | agent | codex | W30_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| opaque | test | agent | codex | W40_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| opaque | test | agent | codex | W50_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| opaque | test | agent | opencode_dpsk | W10_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| opaque | test | agent | opencode_dpsk | W20_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| opaque | test | agent | opencode_dpsk | W30_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| opaque | test | agent | opencode_dpsk | W40_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
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
| transparent | test | agent | codex | W10_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| transparent | test | agent | codex | W20_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| transparent | test | agent | codex | W30_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| transparent | test | agent | codex | W40_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| transparent | test | agent | codex | W50_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| transparent | test | agent | opencode_dpsk | W10_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| transparent | test | agent | opencode_dpsk | W20_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| transparent | test | agent | opencode_dpsk | W30_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| transparent | test | agent | opencode_dpsk | W40_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
| transparent | test | agent | opencode_dpsk | W50_2018 | missing_or_malformed | missing_artifact | missing_artifact | - | - | - | - | 0.0000 |
