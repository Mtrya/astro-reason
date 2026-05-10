# SPOT-5

Generated from the current `main_agentic` aggregate summaries.

| Harness | Present | Success | Valid | Invalid | Timeout | Primary Mean | Normalized Mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| claude_code | 3 | 0 | 0 | 0 | 0 | computed_profit=- | 0.0000 |
| codex | 5 | 5 | 5 | 0 | 0 | computed_profit=115339.4 | 37.63 |
| kimi_cli | 5 | 5 | 5 | 0 | 0 | computed_profit=115339.4 | 37.63 |
| opencode_minimax | 5 | 4 | 4 | 0 | 0 | computed_profit=56820.5 | 25.40 |
| opencode_dpsk | 5 | 5 | 5 | 0 | 0 | computed_profit=112136.4 | 35.46 |

## claude_code

| Case | Valid | Duration (s) | Normalized Score | computed_profit | computed_weight | computed_selected |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1021 | false | 5.5870 | 0.0000 | - | - | - |
| 1403 | false | 4.8110 | 0.0000 | - | - | - |
| 1506 | false | 0.6000 | 0.0000 | - | - | - |

## codex

| Case | Valid | Duration (s) | Normalized Score | computed_profit | computed_weight | computed_selected |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1021 | true | 585.1 | 27.72 | 176246 | 200 | 312 |
| 1403 | true | 742.6 | 27.72 | 176141 | 200 | 218 |
| 1506 | true | 319.5 | 32.18 | 168247 | 200 | 307 |
| 28 | true | 124.4 | 17.19 | 56053 | 0 | 47 |
| 8 | true | 81.73 | 83.33 | 10 | 0 | 7 |

## kimi_cli

| Case | Valid | Duration (s) | Normalized Score | computed_profit | computed_weight | computed_selected |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1021 | true | 3925.4 | 27.72 | 176246 | 200 | 312 |
| 1403 | true | 3632.8 | 27.72 | 176141 | 200 | 218 |
| 1506 | true | 388.8 | 32.18 | 168247 | 200 | 306 |
| 28 | true | 147.5 | 17.19 | 56053 | 0 | 46 |
| 8 | true | 55.86 | 83.33 | 10 | 0 | 7 |

## opencode_dpsk

| Case | Valid | Duration (s) | Normalized Score | computed_profit | computed_weight | computed_selected |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1021 | true | 1318.3 | 27.72 | 176246 | 200 | 312 |
| 1403 | true | 7201.1 | 25.20 | 160127 | 200 | 194 |
| 1506 | true | 608.6 | 32.18 | 168247 | 200 | 309 |
| 28 | true | 354.0 | 17.19 | 56053 | 0 | 46 |
| 8 | true | 150.1 | 75.00 | 9 | 0 | 6 |

## opencode_minimax

| Case | Valid | Duration (s) | Normalized Score | computed_profit | computed_weight | computed_selected |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1021 | true | 1287.0 | 26.77 | 170198 | 200 | 244 |
| 1403 | false | 1395.3 | 0.0000 | - | - | - |
| 1506 | true | 3609.3 | 0.9613 | 5026 | 28 | 18 |
| 28 | true | 4889.6 | 15.96 | 52048 | 0 | 43 |
| 8 | true | 1040.7 | 83.33 | 10 | 0 | 7 |
