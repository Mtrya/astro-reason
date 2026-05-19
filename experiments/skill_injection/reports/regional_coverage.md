# Skill Injection

regional_coverage skill-ablation results across configured conditions and harnesses.

Generated from the current `skill_injection` aggregate artifacts.

## Score Plots

![regional_coverage / opencode_dpsk](regional_coverage_opencode_dpsk_scores.png)

![regional_coverage / opencode_minimax](regional_coverage_opencode_minimax_scores.png)

## Condition Summary

| Condition | Runs | Present | Valid | Valid Rate | Mean Weighted Coverage | Mean Coverage | Mean Actions | Mean Min Battery | Mean Score | Overall Statuses |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compact_domain | 10 | 10 | 10 | 1.0000 | 0.2711 | 0.2753 | 40.90 | 493.0 | 30.67 | success: 10 |
| no_skill | 10 | 10 | 10 | 1.0000 | 0.2203 | 0.2066 | 40.90 | 493.7 | 26.76 | success: 10 |
| skill_pack | 10 | 10 | 10 | 1.0000 | 0.4344 | 0.4377 | 49.70 | 485.4 | 39.93 | success: 10 |

## Condition And Harness Summary

| Condition | Harness | Runs | Present | Valid | Valid Rate | Mean Weighted Coverage | Mean Coverage | Mean Actions | Mean Min Battery | Mean Score | Overall Statuses |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compact_domain | opencode_dpsk | 5 | 5 | 5 | 1.0000 | 0.4149 | 0.4189 | 42.40 | 493.4 | 40.38 | success: 5 |
| compact_domain | opencode_minimax | 5 | 5 | 5 | 1.0000 | 0.1273 | 0.1317 | 39.40 | 492.7 | 20.96 | success: 5 |
| no_skill | opencode_dpsk | 5 | 5 | 5 | 1.0000 | 0.3965 | 0.3744 | 54.20 | 492.1 | 35.79 | success: 5 |
| no_skill | opencode_minimax | 5 | 5 | 5 | 1.0000 | 0.0440 | 0.0388 | 27.60 | 495.3 | 17.73 | success: 5 |
| skill_pack | opencode_dpsk | 5 | 5 | 5 | 1.0000 | 0.6438 | 0.6497 | 47.60 | 495.3 | 55.25 | success: 5 |
| skill_pack | opencode_minimax | 5 | 5 | 5 | 1.0000 | 0.2250 | 0.2258 | 51.80 | 475.5 | 24.62 | success: 5 |

## Cases

| Condition | Harness | Split | Case | Artifact | Overall Status | Verifier Status | Valid | Duration (s) | Skills | Weighted Coverage | Coverage | Actions | Min Battery | Score |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compact_domain | opencode_dpsk | test | case_0001 | present | success | valid | true | 6171 | 1 | 0.4862 | 0.4909 | 64 | 492.9 | 42.34 |
| compact_domain | opencode_dpsk | test | case_0002 | present | success | valid | true | 8202.7 | 1 | 0.0985 | 0.0884 | 9 | 496.7 | 25.31 |
| compact_domain | opencode_dpsk | test | case_0003 | present | success | valid | true | 9755.3 | 1 | 0.1913 | 0.1935 | 11 | 493.1 | 31.54 |
| compact_domain | opencode_dpsk | test | case_0004 | present | success | valid | true | 5063.3 | 1 | 0.6083 | 0.6034 | 64 | 496.6 | 48.21 |
| compact_domain | opencode_dpsk | test | case_0005 | present | success | valid | true | 3597.0 | 1 | 0.6902 | 0.7184 | 64 | 487.6 | 54.51 |
| compact_domain | opencode_minimax | test | case_0001 | present | success | valid | true | 6926.8 | 1 | 0.2848 | 0.2933 | 16 | 492.9 | 39.57 |
| compact_domain | opencode_minimax | test | case_0002 | present | success | valid | true | 5407.5 | 1 | 0.0288 | 0.0254 | 64 | 496.7 | 7.6768 |
| compact_domain | opencode_minimax | test | case_0003 | present | success | valid | true | 8167.7 | 1 | 0 | 0 | 9 | 493.1 | 18.58 |
| compact_domain | opencode_minimax | test | case_0004 | present | success | valid | true | 2669.9 | 1 | 0.2501 | 0.2659 | 44 | 496.6 | 28.24 |
| compact_domain | opencode_minimax | test | case_0005 | present | success | valid | true | 7195.6 | 1 | 0.0732 | 0.0738 | 64 | 484.4 | 10.72 |
| no_skill | opencode_dpsk | test | case_0001 | present | success | valid | true | 7200.9 | 0 | 0.5923 | 0.5974 | 64 | 492.9 | 49.78 |
| no_skill | opencode_dpsk | test | case_0002 | present | success | valid | true | 7201.4 | 0 | 0.2691 | 0.2636 | 15 | 496.7 | 35.94 |
| no_skill | opencode_dpsk | test | case_0003 | present | success | valid | true | 4748.3 | 0 | 0.4890 | 0.4908 | 64 | 486.9 | 39.89 |
| no_skill | opencode_dpsk | test | case_0004 | present | success | valid | true | 7200.9 | 0 | 0.1235 | 0.1067 | 64 | 496.6 | 14.04 |
| no_skill | opencode_dpsk | test | case_0005 | present | success | valid | true | 3871.7 | 0 | 0.5087 | 0.4133 | 64 | 487.6 | 39.33 |
| no_skill | opencode_minimax | test | case_0001 | present | success | valid | true | 5679.6 | 0 | 0 | 0 | 0 | 492.9 | 23.21 |
| no_skill | opencode_minimax | test | case_0002 | present | success | valid | true | 2560.0 | 0 | 0.1697 | 0.1449 | 22 | 496.7 | 26.96 |
| no_skill | opencode_minimax | test | case_0003 | present | success | valid | true | 6216.6 | 0 | 0.0501 | 0.0490 | 3 | 493.1 | 23.47 |
| no_skill | opencode_minimax | test | case_0004 | present | success | valid | true | 5561.5 | 0 | 0 | 0 | 64 | 496.6 | 5.7295 |
| no_skill | opencode_minimax | test | case_0005 | present | success | valid | true | 2941.0 | 0 | 0 | 0 | 49 | 497.3 | 9.2533 |
| skill_pack | opencode_dpsk | test | case_0001 | present | success | valid | true | 9772.7 | 4 | 0.6773 | 0.6892 | 64 | 492.9 | 55.87 |
| skill_pack | opencode_dpsk | test | case_0002 | present | success | valid | true | 7745.3 | 4 | 0.6321 | 0.6389 | 58 | 496.7 | 51.52 |
| skill_pack | opencode_dpsk | test | case_0003 | present | success | valid | true | 8152.9 | 4 | 0.2643 | 0.2660 | 15 | 493.1 | 35.71 |
| skill_pack | opencode_dpsk | test | case_0004 | present | success | valid | true | 8916.5 | 4 | 0.8591 | 0.8646 | 64 | 496.6 | 65.98 |
| skill_pack | opencode_dpsk | test | case_0005 | present | success | valid | true | 7222.8 | 4 | 0.7861 | 0.7897 | 37 | 497.3 | 67.17 |
| skill_pack | opencode_minimax | test | case_0001 | present | success | valid | true | 5244.8 | 4 | 0 | 0 | 64 | 492.9 | 8.2149 |
| skill_pack | opencode_minimax | test | case_0002 | present | success | valid | true | 4470.6 | 4 | 0.0192 | 0.0163 | 64 | 412.3 | 6.0419 |
| skill_pack | opencode_minimax | test | case_0003 | present | success | valid | true | 8448 | 4 | 0.2813 | 0.2812 | 21 | 493.1 | 35.46 |
| skill_pack | opencode_minimax | test | case_0004 | present | success | valid | true | 1163.1 | 4 | 0.4030 | 0.3993 | 46 | 496.6 | 38.08 |
| skill_pack | opencode_minimax | test | case_0005 | present | success | valid | true | 2962.8 | 4 | 0.4216 | 0.4319 | 64 | 482.7 | 35.29 |
