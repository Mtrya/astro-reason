# SPOT-5

Generated from the current `main_agentic` aggregate summaries.

| Harness | Present | Success | Valid | Invalid | Timeout | Primary Mean | Normalized Mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| codex | 5 | 5 | 5 | 0 | 0 | computed_profit=115339.4 | 100.0 |
| kimi_cli | 5 | 5 | 5 | 0 | 0 | computed_profit=115339.4 | 100.0 |
| opencode_minimax | 5 | 4 | 4 | 0 | 0 | computed_profit=56820.5 | 59.18 |
| opencode_dpsk | 5 | 5 | 5 | 0 | 0 | computed_profit=112136.4 | 96.60 |

## codex

| Case | Valid | Duration (s) | Normalized Score | computed_profit | computed_weight | computed_selected |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1021 | true | 585.1 | 100.0 | 176246 | 200 | 312 |
| 1403 | true | 742.6 | 100.0 | 176141 | 200 | 218 |
| 1506 | true | 319.5 | 100.0 | 168247 | 200 | 307 |
| 28 | true | 124.4 | 100.0 | 56053 | 0 | 47 |
| 8 | true | 81.73 | 100.0 | 10 | 0 | 7 |

## kimi_cli

| Case | Valid | Duration (s) | Normalized Score | computed_profit | computed_weight | computed_selected |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1021 | true | 3925.4 | 100.0 | 176246 | 200 | 312 |
| 1403 | true | 3632.8 | 100.0 | 176141 | 200 | 218 |
| 1506 | true | 388.8 | 100.0 | 168247 | 200 | 306 |
| 28 | true | 147.5 | 100.0 | 56053 | 0 | 46 |
| 8 | true | 55.86 | 100.0 | 10 | 0 | 7 |

## opencode_dpsk

| Case | Valid | Duration (s) | Normalized Score | computed_profit | computed_weight | computed_selected |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1021 | true | 1318.3 | 100.0 | 176246 | 200 | 312 |
| 1403 | true | 7201.1 | 93.02 | 160127 | 200 | 194 |
| 1506 | true | 608.6 | 100.0 | 168247 | 200 | 309 |
| 28 | true | 354.0 | 100.0 | 56053 | 0 | 46 |
| 8 | true | 150.1 | 90.00 | 9 | 0 | 6 |

## opencode_minimax

| Case | Valid | Duration (s) | Normalized Score | computed_profit | computed_weight | computed_selected |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1021 | true | 1287.0 | 100.0 | 170198 | 200 | 244 |
| 1403 | false | 1395.3 | 0.0000 | - | - | - |
| 1506 | true | 3609.3 | 3.0601 | 5026 | 28 | 18 |
| 28 | true | 4889.6 | 92.85 | 52048 | 0 | 43 |
| 8 | true | 1040.7 | 100.0 | 10 | 0 | 7 |
