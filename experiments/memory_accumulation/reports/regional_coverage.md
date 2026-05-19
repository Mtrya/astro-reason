# Regional Coverage

regional_coverage memory-accumulation comparison by memory source and evaluation harness.

Generated from the current `memory_accumulation` aggregate artifacts.

## Source And Harness Summary

| Memory Source | Harness | Expected | Present | Missing | Valid | Mean Score | Overall Statuses |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| codex | codex | 5 | 0 | 5 | 0 | 0.0000 | missing_artifact: 5 |
| codex | opencode_dpsk | 5 | 5 | 0 | 5 | 60.08 | success: 5 |
| codex | opencode_minimax | 5 | 5 | 0 | 5 | 20.94 | success: 5 |
| none | codex | 5 | 5 | 0 | 5 | 72.08 | success: 5 |
| none | opencode_dpsk | 5 | 5 | 0 | 5 | 35.79 | success: 5 |
| none | opencode_minimax | 5 | 5 | 0 | 5 | 17.73 | success: 5 |
| opencode_dpsk | codex | 5 | 0 | 5 | 0 | 0.0000 | missing_artifact: 5 |
| opencode_dpsk | opencode_dpsk | 5 | 2 | 3 | 2 | 24.63 | missing_artifact: 3, success: 2 |
| opencode_dpsk | opencode_minimax | 5 | 0 | 5 | 0 | 0.0000 | missing_artifact: 5 |
| opencode_minimax | codex | 5 | 0 | 5 | 0 | 0.0000 | missing_artifact: 5 |
| opencode_minimax | opencode_dpsk | 5 | 0 | 5 | 0 | 0.0000 | missing_artifact: 5 |
| opencode_minimax | opencode_minimax | 5 | 0 | 5 | 0 | 0.0000 | missing_artifact: 5 |

## Cases

| Memory Source | Harness | Split | Case | Artifact | Overall Status | Verifier Status | Valid | Duration (s) | Score | coverage_ratio | weighted_coverage_ratio | num_actions | min_battery_wh |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| codex | codex | test | case_0001 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| codex | codex | test | case_0002 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| codex | codex | test | case_0003 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| codex | codex | test | case_0004 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| codex | codex | test | case_0005 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| codex | opencode_dpsk | test | case_0001 | present | success | valid | true | 7200.7 | 66.74 | 0.8392 | 0.8302 | 63 | 492.9 |
| codex | opencode_dpsk | test | case_0002 | present | success | valid | true | 6540.8 | 67.53 | 0.8818 | 0.8832 | 64 | 496.7 |
| codex | opencode_dpsk | test | case_0003 | present | success | valid | true | 7200.7 | 20.69 | 0 | 0 | 0 | 493.1 |
| codex | opencode_dpsk | test | case_0004 | present | success | valid | true | 4536.1 | 71.09 | 0.9372 | 0.9323 | 64 | 496.6 |
| codex | opencode_dpsk | test | case_0005 | present | success | valid | true | 5383.8 | 74.33 | 0.9731 | 0.9780 | 63 | 497.3 |
| codex | opencode_minimax | test | case_0001 | present | success | valid | true | 6803.4 | 23.51 | 0.0877 | 0.0786 | 23 | 492.9 |
| codex | opencode_minimax | test | case_0002 | present | success | valid | true | 4040.7 | 35.18 | 0.3055 | 0.3121 | 31 | 496.7 |
| codex | opencode_minimax | test | case_0003 | present | success | valid | true | 7200.4 | 5.6900 | 0 | 0 | 64 | 493.1 |
| codex | opencode_minimax | test | case_0004 | present | success | valid | true | 2745.2 | 19.57 | 0.0850 | 0.0928 | 32 | 496.6 |
| codex | opencode_minimax | test | case_0005 | present | success | valid | true | 4610.6 | 20.74 | 0 | 0 | 0 | 497.3 |
| none | codex | test | case_0001 | present | success | valid | true | 604.3 | 74.53 | 0.9498 | 0.9464 | 64 | 492.9 |
| none | codex | test | case_0002 | present | success | valid | true | 2041.6 | 49.38 | 0.5136 | 0.5082 | 30 | 496.7 |
| none | codex | test | case_0003 | present | success | valid | true | 1011.1 | 74.82 | 0.9535 | 0.9544 | 54 | 493.1 |
| none | codex | test | case_0004 | present | success | valid | true | 1841.1 | 84.16 | 1.0000 | 1.0000 | 28 | 496.6 |
| none | codex | test | case_0005 | present | success | valid | true | 1152.2 | 77.50 | 0.9878 | 0.9896 | 53 | 492.4 |
| none | opencode_dpsk | test | case_0001 | present | success | valid | true | 7200.9 | 49.78 | 0.5974 | 0.5923 | 64 | 492.9 |
| none | opencode_dpsk | test | case_0002 | present | success | valid | true | 7201.4 | 35.94 | 0.2636 | 0.2691 | 15 | 496.7 |
| none | opencode_dpsk | test | case_0003 | present | success | valid | true | 4748.3 | 39.89 | 0.4908 | 0.4890 | 64 | 486.9 |
| none | opencode_dpsk | test | case_0004 | present | success | valid | true | 7200.9 | 14.04 | 0.1067 | 0.1235 | 64 | 496.6 |
| none | opencode_dpsk | test | case_0005 | present | success | valid | true | 3871.7 | 39.33 | 0.4133 | 0.5087 | 64 | 487.6 |
| none | opencode_minimax | test | case_0001 | present | success | valid | true | 5679.6 | 23.21 | 0 | 0 | 0 | 492.9 |
| none | opencode_minimax | test | case_0002 | present | success | valid | true | 2560.0 | 26.96 | 0.1449 | 0.1697 | 22 | 496.7 |
| none | opencode_minimax | test | case_0003 | present | success | valid | true | 6216.6 | 23.47 | 0.0490 | 0.0501 | 3 | 493.1 |
| none | opencode_minimax | test | case_0004 | present | success | valid | true | 5561.5 | 5.7295 | 0 | 0 | 64 | 496.6 |
| none | opencode_minimax | test | case_0005 | present | success | valid | true | 2941.0 | 9.2533 | 0 | 0 | 49 | 497.3 |
| opencode_dpsk | codex | test | case_0001 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| opencode_dpsk | codex | test | case_0002 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| opencode_dpsk | codex | test | case_0003 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| opencode_dpsk | codex | test | case_0004 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| opencode_dpsk | codex | test | case_0005 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| opencode_dpsk | opencode_dpsk | test | case_0001 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| opencode_dpsk | opencode_dpsk | test | case_0002 | present | success | valid | true | 2619.1 | 59.86 | 0.7722 | 0.7738 | 64 | 496.7 |
| opencode_dpsk | opencode_dpsk | test | case_0003 | present | success | valid | true | 7200.7 | 63.28 | 0.8058 | 0.8060 | 59 | 493.1 |
| opencode_dpsk | opencode_dpsk | test | case_0004 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| opencode_dpsk | opencode_dpsk | test | case_0005 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| opencode_dpsk | opencode_minimax | test | case_0001 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| opencode_dpsk | opencode_minimax | test | case_0002 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| opencode_dpsk | opencode_minimax | test | case_0003 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| opencode_dpsk | opencode_minimax | test | case_0004 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| opencode_dpsk | opencode_minimax | test | case_0005 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| opencode_minimax | codex | test | case_0001 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| opencode_minimax | codex | test | case_0002 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| opencode_minimax | codex | test | case_0003 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| opencode_minimax | codex | test | case_0004 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| opencode_minimax | codex | test | case_0005 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| opencode_minimax | opencode_dpsk | test | case_0001 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| opencode_minimax | opencode_dpsk | test | case_0002 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| opencode_minimax | opencode_dpsk | test | case_0003 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| opencode_minimax | opencode_dpsk | test | case_0004 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| opencode_minimax | opencode_dpsk | test | case_0005 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| opencode_minimax | opencode_minimax | test | case_0001 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| opencode_minimax | opencode_minimax | test | case_0002 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| opencode_minimax | opencode_minimax | test | case_0003 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| opencode_minimax | opencode_minimax | test | case_0004 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
| opencode_minimax | opencode_minimax | test | case_0005 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - |
