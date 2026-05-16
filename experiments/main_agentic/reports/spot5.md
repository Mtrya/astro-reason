# SPOT-5

Generated from the current `main_agentic` aggregate summaries.

| Harness | Present | Success | Valid | Invalid | Timeout | Primary Mean | Normalized Mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| claude_code | 3 | 0 | 0 | 0 | 0 | computed_profit=0.0000 | 0.0000 |
| codex | 5 | 5 | 5 | 0 | 0 | computed_profit=115339.4 | 61.92 |
| kimi_cli | 5 | 5 | 5 | 0 | 0 | computed_profit=115339.4 | 61.92 |
| opencode_minimax | 5 | 4 | 4 | 0 | 0 | computed_profit=45456.4 | 37.47 |
| opencode_dpsk | 5 | 5 | 5 | 0 | 0 | computed_profit=112136.4 | 60.91 |

## claude_code

| Case | Valid | Duration (s) | Normalized Score | computed_profit | computed_weight | computed_selected |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1403 | false | 3.4810 | 0.0000 | - | - | - |
| 1506 | false | 3.0580 | 0.0000 | - | - | - |
| 28 | false | 3.1670 | 0.0000 | - | - | - |

## codex

| Case | Valid | Duration (s) | Normalized Score | computed_profit | computed_weight | computed_selected |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1021 | true | 585.1 | 55.43 | 176246 | 200 | 312 |
| 1403 | true | 742.6 | 55.44 | 176141 | 200 | 218 |
| 1506 | true | 319.5 | 64.36 | 168247 | 200 | 307 |
| 28 | true | 124.4 | 34.37 | 56053 | 0 | 47 |
| 8 | true | 81.73 | 100.0 | 10 | 0 | 7 |

## kimi_cli

| Case | Valid | Duration (s) | Normalized Score | computed_profit | computed_weight | computed_selected |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1021 | true | 3925.4 | 55.43 | 176246 | 200 | 312 |
| 1403 | true | 3632.8 | 55.44 | 176141 | 200 | 218 |
| 1506 | true | 388.8 | 64.36 | 168247 | 200 | 306 |
| 28 | true | 147.5 | 34.37 | 56053 | 0 | 46 |
| 8 | true | 55.86 | 100.0 | 10 | 0 | 7 |

## opencode_dpsk

| Case | Valid | Duration (s) | Normalized Score | computed_profit | computed_weight | computed_selected |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1021 | true | 1318.3 | 55.43 | 176246 | 200 | 312 |
| 1403 | true | 7201.1 | 50.40 | 160127 | 200 | 194 |
| 1506 | true | 608.6 | 64.36 | 168247 | 200 | 309 |
| 28 | true | 354.0 | 34.37 | 56053 | 0 | 46 |
| 8 | true | 150.1 | 100.0 | 9 | 0 | 6 |

## opencode_minimax

| Case | Valid | Duration (s) | Normalized Score | computed_profit | computed_weight | computed_selected |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1021 | true | 1287.0 | 53.53 | 170198 | 200 | 244 |
| 1403 | false | 1395.3 | 0.0000 | - | - | - |
| 1506 | true | 3609.3 | 1.9227 | 5026 | 28 | 18 |
| 28 | true | 4889.6 | 31.92 | 52048 | 0 | 43 |
| 8 | true | 1040.7 | 100.0 | 10 | 0 | 7 |
