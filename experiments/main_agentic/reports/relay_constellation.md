# Relay Constellation

Generated from the current `main_agentic` aggregate summaries.

| Harness | Present | Success | Valid | Invalid | Timeout | Primary Mean | Normalized Mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| codex | 5 | 5 | 5 | 0 | 0 | service_fraction=0.9352 | 64.91 |
| kimi_cli | 5 | 5 | 5 | 0 | 0 | service_fraction=0.8681 | 57.77 |
| opencode_minimax | 5 | 4 | 4 | 1 | 0 | service_fraction=0.0000 | 0.0000 |
| opencode_dpsk | 5 | 5 | 5 | 0 | 0 | service_fraction=0.5594 | 35.67 |

## codex

| Case | Valid | Duration (s) | Normalized Score | service_fraction | worst_demand_service_fraction | num_added_satellites | mean_latency_ms | latency_p95_ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| case_0001 | true | 2591.3 | 53.96 | 0.8981 | 0.3889 | 2 | 149.5 | 253.6 |
| case_0002 | true | 1714.5 | 66.88 | 0.9821 | 0.8750 | 2 | 132.8 | 223.0 |
| case_0003 | true | 2814.4 | 89.23 | 1.0000 | 1.0000 | 2 | 96.08 | 163.8 |
| case_0004 | true | 1995.9 | 56.66 | 0.8970 | 0.5467 | 1 | 100.2 | 158.5 |
| case_0005 | true | 2729.5 | 57.83 | 0.8988 | 0.6083 | 5 | 152.2 | 275.5 |

## kimi_cli

| Case | Valid | Duration (s) | Normalized Score | service_fraction | worst_demand_service_fraction | num_added_satellites | mean_latency_ms | latency_p95_ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| case_0001 | true | 5883.7 | 44.92 | 0.8296 | 0.0778 | 2 | 139.5 | 218.2 |
| case_0002 | true | 7200.9 | 61.67 | 0.9524 | 0.6667 | 3 | 136.5 | 254.3 |
| case_0003 | true | 3747.5 | 85.28 | 1.0000 | 1.0000 | 3 | 104.2 | 180.3 |
| case_0004 | true | 6695.9 | 62.42 | 0.9296 | 0.7778 | 4 | 101.6 | 173.4 |
| case_0005 | true | 7207.0 | 34.56 | 0.6287 | 0.0889 | 2 | 143.3 | 275.8 |

## opencode_dpsk

| Case | Valid | Duration (s) | Normalized Score | service_fraction | worst_demand_service_fraction | num_added_satellites | mean_latency_ms | latency_p95_ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| case_0001 | true | 6891.8 | 57.75 | 0.9222 | 0.5333 | 6 | 152.8 | 288.5 |
| case_0002 | true | 4038.9 | 61.67 | 0.9524 | 0.6667 | 10 | 114.6 | 215.1 |
| case_0003 | true | 7200.8 | 0.0000 | 0.0000 | 0.0000 | 8 | - | - |
| case_0004 | true | 4992.2 | 58.92 | 0.9222 | 0.6000 | 8 | 99.30 | 174.9 |
| case_0005 | true | 7200.8 | 0.0000 | 0.0000 | 0.0000 | 10 | - | - |

## opencode_minimax

| Case | Valid | Duration (s) | Normalized Score | service_fraction | worst_demand_service_fraction | num_added_satellites | mean_latency_ms | latency_p95_ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| case_0001 | true | 3344.4 | 0.0000 | 0.0000 | 0.0000 | 6 | - | - |
| case_0002 | true | 2326.8 | 0.0000 | 0.0000 | 0.0000 | 2 | - | - |
| case_0003 | true | 3290.8 | 0.0000 | 0.0000 | 0.0000 | 8 | - | - |
| case_0004 | false | 3532.6 | 0.0000 | 0.0000 | 0.0000 | 8 | - | - |
| case_0005 | true | 2330.2 | 0.0000 | 0.0000 | 0.0000 | 1 | - | - |
