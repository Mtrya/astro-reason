# SPOT-5

Generated from the current `main_agentic` aggregate summaries.

| Harness | Present | Success | Valid | Invalid | Timeout | Primary Mean | Processed Mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| codex | 5 | 5 | 5 | 0 | 0 | computed_profit=115339.4 | profit_score_pct=101.8 |
| kimi_cli | 5 | 5 | 5 | 0 | 0 | computed_profit=115339.4 | profit_score_pct=101.8 |
| opencode_minimax | 5 | 4 | 4 | 0 | 0 | computed_profit=56820.5 | profit_score_pct=59.30 |
| opencode_dpsk | 5 | 5 | 5 | 0 | 0 | computed_profit=112136.4 | profit_score_pct=97.92 |

## codex

| Case | Overall | Verifier | Valid | Duration (s) | computed_profit | computed_weight | computed_selected | profit_score_pct |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1021 | success | valid | true | 585.1 | 176246 | 200 | 312 | 104.1 |
| 1403 | success | valid | true | 742.6 | 176141 | 200 | 218 | 102.3 |
| 1506 | success | valid | true | 319.5 | 168247 | 200 | 307 | 102.4 |
| 28 | success | valid | true | 124.4 | 56053 | 0 | 47 | 100.0 |
| 8 | success | valid | true | 81.73 | 10 | 0 | 7 | 100.0 |

## kimi_cli

| Case | Overall | Verifier | Valid | Duration (s) | computed_profit | computed_weight | computed_selected | profit_score_pct |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1021 | success | valid | true | 3925.4 | 176246 | 200 | 312 | 104.1 |
| 1403 | success | valid | true | 3632.8 | 176141 | 200 | 218 | 102.3 |
| 1506 | success | valid | true | 388.8 | 168247 | 200 | 306 | 102.4 |
| 28 | success | valid | true | 147.5 | 56053 | 0 | 46 | 100.0 |
| 8 | success | valid | true | 55.86 | 10 | 0 | 7 | 100.0 |

## opencode_dpsk

| Case | Overall | Verifier | Valid | Duration (s) | computed_profit | computed_weight | computed_selected | profit_score_pct |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1021 | success | valid | true | 1318.3 | 176246 | 200 | 312 | 104.1 |
| 1403 | success | valid | true | 7201.1 | 160127 | 200 | 194 | 93.02 |
| 1506 | success | valid | true | 608.6 | 168247 | 200 | 309 | 102.4 |
| 28 | success | valid | true | 354.0 | 56053 | 0 | 46 | 100.0 |
| 8 | success | valid | true | 150.1 | 9 | 0 | 6 | 90.00 |

## opencode_minimax

| Case | Overall | Verifier | Valid | Duration (s) | computed_profit | computed_weight | computed_selected | profit_score_pct |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1021 | success | valid | true | 1287.0 | 170198 | 200 | 244 | 100.6 |
| 1403 | verifier_error | error | - | 1395.3 | - | - | - | 0.0000 |
| 1506 | success | valid | true | 3609.3 | 5026 | 28 | 18 | 3.0601 |
| 28 | success | valid | true | 4889.6 | 52048 | 0 | 43 | 92.85 |
| 8 | success | valid | true | 1040.7 | 10 | 0 | 7 | 100.0 |
