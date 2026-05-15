# Skill Injection

stereo_imaging skill-ablation results across configured conditions and harnesses.

Generated from the current `skill_injection` aggregate artifacts.

## Score Plots

![stereo_imaging / opencode_dpsk](stereo_imaging_opencode_dpsk_scores.png)

![stereo_imaging / opencode_minimax](stereo_imaging_opencode_minimax_scores.png)

## Condition Summary

| Condition | Runs | Present | Valid | Valid Rate | Mean Coverage | Mean Quality | Mean Score | Overall Statuses |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compact_domain | 10 | 10 | 10 | 1.0000 | 0.1663 | 0.1423 | 14.23 | success: 10 |
| no_skill | 10 | 10 | 5 | 0.5000 | 0.0942 | 0.0650 | 6.4975 | success: 5, verifier_error: 3, verifier_invalid: 2 |
| skill_pack | 10 | 10 | 7 | 0.7000 | 0.1544 | 0.1474 | 14.74 | success: 7, verifier_invalid: 3 |

## Condition And Harness Summary

| Condition | Harness | Runs | Present | Valid | Valid Rate | Mean Coverage | Mean Quality | Mean Score | Overall Statuses |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compact_domain | opencode_dpsk | 5 | 5 | 5 | 1.0000 | 0.3327 | 0.2846 | 28.46 | success: 5 |
| compact_domain | opencode_minimax | 5 | 5 | 5 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | success: 5 |
| no_skill | opencode_dpsk | 5 | 5 | 4 | 0.8000 | 0.1884 | 0.1300 | 13.00 | success: 4, verifier_invalid: 1 |
| no_skill | opencode_minimax | 5 | 5 | 1 | 0.2000 | 0.0000 | 0.0000 | 0.0000 | success: 1, verifier_error: 3, verifier_invalid: 1 |
| skill_pack | opencode_dpsk | 5 | 5 | 4 | 0.8000 | 0.3088 | 0.2947 | 29.47 | success: 4, verifier_invalid: 1 |
| skill_pack | opencode_minimax | 5 | 5 | 3 | 0.6000 | 0.0000 | 0.0000 | 0.0000 | success: 3, verifier_invalid: 2 |

## Cases

| Condition | Harness | Split | Case | Artifact | Overall Status | Verifier Status | Valid | Duration (s) | Skills | Coverage | Quality | Score |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| compact_domain | opencode_dpsk | test | case_0001 | present | success | valid | true | 6749.7 | 1 | 0.1338 | 0.0998 | 9.9830 |
| compact_domain | opencode_dpsk | test | case_0002 | present | success | valid | true | 3623.0 | 1 | 0.9835 | 0.9032 | 90.32 |
| compact_domain | opencode_dpsk | test | case_0003 | present | success | valid | true | 6018.3 | 1 | 0 | 0 | 0 |
| compact_domain | opencode_dpsk | test | case_0004 | present | success | valid | true | 6850.1 | 1 | 0 | 0 | 0 |
| compact_domain | opencode_dpsk | test | case_0005 | present | success | valid | true | 6371.9 | 1 | 0.5461 | 0.4201 | 42.01 |
| compact_domain | opencode_minimax | test | case_0001 | present | success | valid | true | 4280.2 | 1 | 0 | 0 | 0 |
| compact_domain | opencode_minimax | test | case_0002 | present | success | valid | true | 5233.1 | 1 | 0 | 0 | 0 |
| compact_domain | opencode_minimax | test | case_0003 | present | success | valid | true | 2431.1 | 1 | 0 | 0 | 0 |
| compact_domain | opencode_minimax | test | case_0004 | present | success | valid | true | 4048.2 | 1 | 0 | 0 | 0 |
| compact_domain | opencode_minimax | test | case_0005 | present | success | valid | true | 703.7 | 1 | 0 | 0 | 0 |
| no_skill | opencode_dpsk | test | case_0001 | present | success | valid | true | 5879.5 | 0 | 0 | 0 | 0 |
| no_skill | opencode_dpsk | test | case_0002 | present | success | valid | true | 7200.9 | 0 | 0 | 0 | 0 |
| no_skill | opencode_dpsk | test | case_0003 | present | success | valid | true | 5456.1 | 0 | 0.9421 | 0.6498 | 64.98 |
| no_skill | opencode_dpsk | test | case_0004 | present | verifier_invalid | invalid | false | 5591.7 | 0 | 0.8016 | 0.7248 | 0 |
| no_skill | opencode_dpsk | test | case_0005 | present | success | valid | true | 5857.2 | 0 | 0 | 0 | 0 |
| no_skill | opencode_minimax | test | case_0001 | present | success | valid | true | 6512.8 | 0 | 0 | 0 | 0 |
| no_skill | opencode_minimax | test | case_0002 | present | verifier_error | error | - | 864.1 | 0 | - | - | - |
| no_skill | opencode_minimax | test | case_0003 | present | verifier_error | error | - | 4550.7 | 0 | - | - | - |
| no_skill | opencode_minimax | test | case_0004 | present | verifier_error | error | - | 717.0 | 0 | - | - | - |
| no_skill | opencode_minimax | test | case_0005 | present | verifier_invalid | invalid | false | 3852.3 | 0 | 0 | 0 | 0 |
| skill_pack | opencode_dpsk | test | case_0001 | present | success | valid | true | 5749.4 | 4 | 0.9155 | 0.9033 | 90.33 |
| skill_pack | opencode_dpsk | test | case_0002 | present | success | valid | true | 6378.1 | 4 | 0.0331 | 0.0186 | 1.8588 |
| skill_pack | opencode_dpsk | test | case_0003 | present | success | valid | true | 8343.4 | 4 | 0 | 0 | 0 |
| skill_pack | opencode_dpsk | test | case_0004 | present | success | valid | true | 9434.4 | 4 | 0.5952 | 0.5516 | 55.16 |
| skill_pack | opencode_dpsk | test | case_0005 | present | verifier_invalid | invalid | false | 6617.9 | 4 | 0 | 0 | 0 |
| skill_pack | opencode_minimax | test | case_0001 | present | success | valid | true | 8479 | 4 | 0 | 0 | 0 |
| skill_pack | opencode_minimax | test | case_0002 | present | success | valid | true | 1110.0 | 4 | 0 | 0 | 0 |
| skill_pack | opencode_minimax | test | case_0003 | present | success | valid | true | 6917.0 | 4 | 0 | 0 | 0 |
| skill_pack | opencode_minimax | test | case_0004 | present | verifier_invalid | invalid | false | 2072.8 | 4 | 0 | 0 | 0 |
| skill_pack | opencode_minimax | test | case_0005 | present | verifier_invalid | invalid | false | 5274.9 | 4 | 0 | 0 | 0 |
