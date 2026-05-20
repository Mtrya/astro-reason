# Relay Constellation

relay_constellation memory-accumulation comparison by memory source and evaluation harness.

Generated from the current `memory_accumulation` aggregate artifacts.

## Source And Harness Summary

| Memory Source | Harness | Expected | Present | Missing | Valid | Mean Score | Overall Statuses |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| codex | codex | 5 | 0 | 5 | 0 | 0.0000 | missing_artifact: 5 |
| codex | opencode_dpsk | 5 | 5 | 0 | 5 | 45.09 | success: 5 |
| codex | opencode_minimax | 5 | 5 | 0 | 5 | 2.2633 | success: 5 |
| none | codex | 5 | 5 | 0 | 5 | 64.91 | success: 5 |
| none | opencode_dpsk | 5 | 5 | 0 | 5 | 35.67 | success: 5 |
| none | opencode_minimax | 5 | 5 | 0 | 4 | 0.0000 | success: 4, verifier_invalid: 1 |
| opencode_dpsk | codex | 5 | 0 | 5 | 0 | 0.0000 | missing_artifact: 5 |
| opencode_dpsk | opencode_dpsk | 5 | 5 | 0 | 5 | 54.19 | success: 5 |
| opencode_dpsk | opencode_minimax | 5 | 5 | 0 | 3 | 5.7833 | no_solution: 1, success: 3, verifier_invalid: 1 |
| opencode_minimax | codex | 5 | 0 | 5 | 0 | 0.0000 | missing_artifact: 5 |
| opencode_minimax | opencode_dpsk | 5 | 0 | 5 | 0 | 0.0000 | missing_artifact: 5 |
| opencode_minimax | opencode_minimax | 5 | 0 | 5 | 0 | 0.0000 | missing_artifact: 5 |

## Cases

| Memory Source | Harness | Split | Case | Artifact | Overall Status | Verifier Status | Valid | Duration (s) | Score | service_fraction | worst_demand_service_fraction | num_added_satellites | mean_latency_ms | latency_p95_ms |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| codex | codex | test | case_0001 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| codex | codex | test | case_0002 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| codex | codex | test | case_0003 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| codex | codex | test | case_0004 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| codex | codex | test | case_0005 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| codex | opencode_dpsk | test | case_0001 | present | success | valid | true | 7200.5 | 9.7222 | 0.1852 | 0 | 6 | 190.7 | 253.7 |
| codex | opencode_dpsk | test | case_0002 | present | success | valid | true | 7200.3 | 31.56 | 0.5401 | 0.1833 | 10 | 237.2 | 413.9 |
| codex | opencode_dpsk | test | case_0003 | present | success | valid | true | 7200.2 | 77.97 | 1 | 1 | 6 | 99.39 | 163.7 |
| codex | opencode_dpsk | test | case_0004 | present | success | valid | true | 7200.3 | 53.30 | 0.8597 | 0.4667 | 6 | 170.3 | 269.2 |
| codex | opencode_dpsk | test | case_0005 | present | success | valid | true | 7200.9 | 52.87 | 0.8182 | 0.5667 | 6 | 196.7 | 342.9 |
| codex | opencode_minimax | test | case_0001 | present | success | valid | true | 4888.6 | 0 | 0 | 0 | 6 | - | - |
| codex | opencode_minimax | test | case_0002 | present | success | valid | true | 3270.4 | 0 | 0 | 0 | 6 | - | - |
| codex | opencode_minimax | test | case_0003 | present | success | valid | true | 1988.9 | 11.32 | 0.2156 | 0 | 6 | 75.72 | 78.30 |
| codex | opencode_minimax | test | case_0004 | present | success | valid | true | 7200.2 | 0 | 0 | 0 | 6 | - | - |
| codex | opencode_minimax | test | case_0005 | present | success | valid | true | 1777.7 | 0 | 0 | 0 | 6 | - | - |
| none | codex | test | case_0001 | present | success | valid | true | 2591.2 | 53.96 | 0.8981 | 0.3889 | 2 | 149.5 | 253.6 |
| none | codex | test | case_0002 | present | success | valid | true | 1714.5 | 66.88 | 0.9821 | 0.8750 | 2 | 132.8 | 223.0 |
| none | codex | test | case_0003 | present | success | valid | true | 2814.4 | 89.23 | 1 | 1 | 2 | 96.08 | 163.8 |
| none | codex | test | case_0004 | present | success | valid | true | 1995.9 | 56.66 | 0.8970 | 0.5467 | 1 | 100.2 | 158.5 |
| none | codex | test | case_0005 | present | success | valid | true | 2729.5 | 57.83 | 0.8988 | 0.6083 | 5 | 152.2 | 275.5 |
| none | opencode_dpsk | test | case_0001 | present | success | valid | true | 6891.8 | 57.75 | 0.9222 | 0.5333 | 6 | 152.8 | 288.5 |
| none | opencode_dpsk | test | case_0002 | present | success | valid | true | 4038.9 | 61.67 | 0.9524 | 0.6667 | 10 | 114.6 | 215.1 |
| none | opencode_dpsk | test | case_0003 | present | success | valid | true | 7200.8 | 0 | 0 | 0 | 8 | - | - |
| none | opencode_dpsk | test | case_0004 | present | success | valid | true | 4992.2 | 58.92 | 0.9222 | 0.6000 | 8 | 99.30 | 174.9 |
| none | opencode_dpsk | test | case_0005 | present | success | valid | true | 7200.8 | 0 | 0 | 0 | 10 | - | - |
| none | opencode_minimax | test | case_0001 | present | success | valid | true | 3344.4 | 0 | 0 | 0 | 6 | - | - |
| none | opencode_minimax | test | case_0002 | present | success | valid | true | 2326.8 | 0 | 0 | 0 | 2 | - | - |
| none | opencode_minimax | test | case_0003 | present | success | valid | true | 3290.8 | 0 | 0 | 0 | 8 | - | - |
| none | opencode_minimax | test | case_0004 | present | verifier_invalid | invalid | false | 3532.6 | 0 | 0 | 0 | 8 | - | - |
| none | opencode_minimax | test | case_0005 | present | success | valid | true | 2330.2 | 0 | 0 | 0 | 1 | - | - |
| opencode_dpsk | codex | test | case_0001 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_dpsk | codex | test | case_0002 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_dpsk | codex | test | case_0003 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_dpsk | codex | test | case_0004 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_dpsk | codex | test | case_0005 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_dpsk | opencode_dpsk | test | case_0001 | present | success | valid | true | 7200.7 | 52.79 | 0.8611 | 0.4333 | 3 | 158.7 | 275.4 |
| opencode_dpsk | opencode_dpsk | test | case_0002 | present | success | valid | true | 7200.4 | 65.36 | 0.9635 | 0.8444 | 6 | 128.5 | 227.9 |
| opencode_dpsk | opencode_dpsk | test | case_0003 | present | success | valid | true | 7200.5 | 64.98 | 0.9489 | 0.8667 | 7 | 133.6 | 186.0 |
| opencode_dpsk | opencode_dpsk | test | case_0004 | present | success | valid | true | 6594.2 | 42.31 | 0.7037 | 0.3067 | 4 | 147.5 | 193.0 |
| opencode_dpsk | opencode_dpsk | test | case_0005 | present | success | valid | true | 7200.5 | 45.52 | 0.6866 | 0.5417 | 4 | 264.7 | 452.1 |
| opencode_dpsk | opencode_minimax | test | case_0001 | present | success | valid | true | 5902.0 | 0 | 0 | 0 | 3 | - | - |
| opencode_dpsk | opencode_minimax | test | case_0002 | present | success | valid | true | 5906.1 | 28.92 | 0.5508 | 0 | 3 | 114.0 | 150.4 |
| opencode_dpsk | opencode_minimax | test | case_0003 | present | no_solution | no_solution | false | 104.9 | 0 | - | - | - | - | - |
| opencode_dpsk | opencode_minimax | test | case_0004 | present | success | valid | true | 5472.9 | 0 | 0 | 0 | 3 | - | - |
| opencode_dpsk | opencode_minimax | test | case_0005 | present | verifier_invalid | invalid | false | 5773.9 | 0 | 0 | 0 | 3 | - | - |
| opencode_minimax | codex | test | case_0001 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_minimax | codex | test | case_0002 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_minimax | codex | test | case_0003 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_minimax | codex | test | case_0004 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_minimax | codex | test | case_0005 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_minimax | opencode_dpsk | test | case_0001 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_minimax | opencode_dpsk | test | case_0002 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_minimax | opencode_dpsk | test | case_0003 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_minimax | opencode_dpsk | test | case_0004 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_minimax | opencode_dpsk | test | case_0005 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_minimax | opencode_minimax | test | case_0001 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_minimax | opencode_minimax | test | case_0002 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_minimax | opencode_minimax | test | case_0003 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_minimax | opencode_minimax | test | case_0004 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_minimax | opencode_minimax | test | case_0005 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
