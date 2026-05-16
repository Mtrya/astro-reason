# Skill Injection

relay_constellation skill-ablation results across configured conditions and harnesses.

Generated from the current `skill_injection` aggregate artifacts.

## Score Plots

![relay_constellation / opencode_dpsk](relay_constellation_opencode_dpsk_scores.png)

![relay_constellation / opencode_minimax](relay_constellation_opencode_minimax_scores.png)

## Condition Summary

| Condition | Runs | Present | Valid | Valid Rate | Mean Service | Mean Worst Demand | Mean Added Satellites | Mean Latency | Mean P95 Latency | Mean Score | Overall Statuses |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compact_domain | 10 | 6 | 6 | 0.6000 | 0.3034 | 0.1328 | 4.7000 | 147.4 | 189.7 | 18.25 | missing_artifact: 4, success: 6 |
| no_skill | 10 | 10 | 9 | 0.9000 | 0.2797 | 0.1800 | 6.9000 | 143.7 | 269.8 | 17.83 | success: 9, verifier_invalid: 1 |
| skill_pack | 10 | 0 | 0 | 0.0000 | - | - | - | - | - | 0.0000 | missing_artifact: 10 |

## Condition And Harness Summary

| Condition | Harness | Runs | Present | Valid | Valid Rate | Mean Service | Mean Worst Demand | Mean Added Satellites | Mean Latency | Mean P95 Latency | Mean Score | Overall Statuses |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compact_domain | opencode_dpsk | 5 | 4 | 4 | 0.8000 | 0.5846 | 0.2656 | 3.8000 | 116.2 | 173.1 | 35.34 | missing_artifact: 1, success: 4 |
| compact_domain | opencode_minimax | 5 | 2 | 2 | 0.4000 | 0.0222 | 0.0000 | 3.2000 | 171.0 | 177.5 | 1.1667 | missing_artifact: 3, success: 2 |
| no_skill | opencode_dpsk | 5 | 5 | 5 | 1.0000 | 0.5594 | 0.3600 | 8.4000 | 134.5 | 251.1 | 35.67 | success: 5 |
| no_skill | opencode_minimax | 5 | 5 | 4 | 0.8000 | 0.0000 | 0.0000 | 5.0000 | - | - | 0.0000 | success: 4, verifier_invalid: 1 |
| skill_pack | opencode_dpsk | 5 | 0 | 0 | 0.0000 | - | - | - | - | - | 0.0000 | missing_artifact: 5 |
| skill_pack | opencode_minimax | 5 | 0 | 0 | 0.0000 | - | - | - | - | - | 0.0000 | missing_artifact: 5 |

## Cases

| Condition | Harness | Split | Case | Artifact | Overall Status | Verifier Status | Valid | Duration (s) | Skills | Service | Worst Demand | Added Satellites | Latency | P95 Latency | Score |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compact_domain | opencode_dpsk | test | case_0001 | present | success | valid | true | 8006.1 | 1 | 0.7269 | 0.0889 | 0 | 133.0 | 177.1 | 39.72 |
| compact_domain | opencode_dpsk | test | case_0002 | present | success | valid | true | 6368.3 | 1 | 0.8365 | 0.5556 | 3 | 122.0 | 213.5 | 53.64 |
| compact_domain | opencode_dpsk | test | case_0003 | present | success | valid | true | 7161.2 | 1 | 0.5189 | 0.1500 | 0 | 101.3 | 138.7 | 29.87 |
| compact_domain | opencode_dpsk | test | case_0004 | present | success | valid | true | 5063.4 | 1 | 0.8408 | 0.5333 | 8 | 91.79 | 122.7 | 53.48 |
| compact_domain | opencode_dpsk | test | case_0005 | missing_artifact | missing_artifact | missing_artifact | - | - | 1 | - | - | - | - | - | 0 |
| compact_domain | opencode_minimax | test | case_0001 | present | success | valid | true | 3969.3 | 1 | 0.1111 | 0 | 0 | 171.0 | 177.5 | 5.8333 |
| compact_domain | opencode_minimax | test | case_0002 | present | success | valid | true | 3163.1 | 1 | 0 | 0 | 4 | - | - | 0 |
| compact_domain | opencode_minimax | test | case_0003 | missing_artifact | missing_artifact | missing_artifact | - | - | 1 | - | - | - | - | - | 0 |
| compact_domain | opencode_minimax | test | case_0004 | missing_artifact | missing_artifact | missing_artifact | - | - | 1 | - | - | - | - | - | 0 |
| compact_domain | opencode_minimax | test | case_0005 | missing_artifact | missing_artifact | missing_artifact | - | - | 1 | - | - | - | - | - | 0 |
| no_skill | opencode_dpsk | test | case_0001 | present | success | valid | true | 6891.8 | 0 | 0.9222 | 0.5333 | 6 | 152.8 | 288.5 | 57.75 |
| no_skill | opencode_dpsk | test | case_0002 | present | success | valid | true | 4038.9 | 0 | 0.9524 | 0.6667 | 10 | 114.6 | 215.1 | 61.67 |
| no_skill | opencode_dpsk | test | case_0003 | present | success | valid | true | 7200.8 | 0 | 0 | 0 | 8 | - | - | 0 |
| no_skill | opencode_dpsk | test | case_0004 | present | success | valid | true | 4992.2 | 0 | 0.9222 | 0.6000 | 8 | 99.30 | 174.9 | 58.92 |
| no_skill | opencode_dpsk | test | case_0005 | present | success | valid | true | 7200.8 | 0 | 0 | 0 | 10 | - | - | 0 |
| no_skill | opencode_minimax | test | case_0001 | present | success | valid | true | 3344.4 | 0 | 0 | 0 | 6 | - | - | 0 |
| no_skill | opencode_minimax | test | case_0002 | present | success | valid | true | 2326.8 | 0 | 0 | 0 | 2 | - | - | 0 |
| no_skill | opencode_minimax | test | case_0003 | present | success | valid | true | 3290.8 | 0 | 0 | 0 | 8 | - | - | 0 |
| no_skill | opencode_minimax | test | case_0004 | present | verifier_invalid | invalid | false | 3532.6 | 0 | 0 | 0 | 8 | - | - | 0 |
| no_skill | opencode_minimax | test | case_0005 | present | success | valid | true | 2330.2 | 0 | 0 | 0 | 1 | - | - | 0 |
| skill_pack | opencode_dpsk | test | case_0001 | missing_artifact | missing_artifact | missing_artifact | - | - | 3 | - | - | - | - | - | 0 |
| skill_pack | opencode_dpsk | test | case_0002 | missing_artifact | missing_artifact | missing_artifact | - | - | 3 | - | - | - | - | - | 0 |
| skill_pack | opencode_dpsk | test | case_0003 | missing_artifact | missing_artifact | missing_artifact | - | - | 3 | - | - | - | - | - | 0 |
| skill_pack | opencode_dpsk | test | case_0004 | missing_artifact | missing_artifact | missing_artifact | - | - | 3 | - | - | - | - | - | 0 |
| skill_pack | opencode_dpsk | test | case_0005 | missing_artifact | missing_artifact | missing_artifact | - | - | 3 | - | - | - | - | - | 0 |
| skill_pack | opencode_minimax | test | case_0001 | missing_artifact | missing_artifact | missing_artifact | - | - | 3 | - | - | - | - | - | 0 |
| skill_pack | opencode_minimax | test | case_0002 | missing_artifact | missing_artifact | missing_artifact | - | - | 3 | - | - | - | - | - | 0 |
| skill_pack | opencode_minimax | test | case_0003 | missing_artifact | missing_artifact | missing_artifact | - | - | 3 | - | - | - | - | - | 0 |
| skill_pack | opencode_minimax | test | case_0004 | missing_artifact | missing_artifact | missing_artifact | - | - | 3 | - | - | - | - | - | 0 |
| skill_pack | opencode_minimax | test | case_0005 | missing_artifact | missing_artifact | missing_artifact | - | - | 3 | - | - | - | - | - | 0 |
