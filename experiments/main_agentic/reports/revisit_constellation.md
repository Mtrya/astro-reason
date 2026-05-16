# Revisit Constellation

Generated from the current `main_agentic` aggregate summaries.

| Harness | Present | Success | Valid | Invalid | Timeout | Primary Mean | Normalized Mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| claude_code | 5 | 5 | 5 | 0 | 0 | capped_max_revisit_gap_hours=6.8000 | 76.50 |
| codex | 5 | 5 | 5 | 0 | 0 | capped_max_revisit_gap_hours=7.6650 | 69.58 |
| kimi_cli | 5 | 5 | 5 | 0 | 0 | capped_max_revisit_gap_hours=6.8357 | 73.36 |
| opencode_minimax | 5 | 0 | 0 | 5 | 0 | capped_max_revisit_gap_hours=- | 0.0000 |
| opencode_dpsk | 5 | 5 | 5 | 0 | 0 | capped_max_revisit_gap_hours=6.8411 | 70.95 |

## claude_code

| Case | Valid | Duration (s) | Normalized Score | capped_max_revisit_gap_hours | num_satellites |
| --- | --- | ---: | ---: | ---: | ---: |
| case_0001 | true | 3058.4 | 78.31 | 6.0000 | 10 |
| case_0002 | true | 2836.3 | 80.06 | 8.0000 | 9 |
| case_0003 | true | 7200.7 | 71.33 | 6.0000 | 16 |
| case_0004 | true | 4465.6 | 77.50 | 8.0000 | 10 |
| case_0005 | true | 7200.7 | 75.32 | 6.0000 | 12 |

## codex

| Case | Valid | Duration (s) | Normalized Score | capped_max_revisit_gap_hours | num_satellites |
| --- | --- | ---: | ---: | ---: | ---: |
| case_0001 | true | 1773.5 | 69.79 | 6.0628 | 18 |
| case_0002 | true | 1521.8 | 80.06 | 8.0000 | 9 |
| case_0003 | true | 2439.7 | 72.08 | 6.0000 | 15 |
| case_0004 | true | 2184.3 | 55.88 | 12.26 | 19 |
| case_0005 | true | 2119.5 | 70.08 | 6.0000 | 19 |

## kimi_cli

| Case | Valid | Duration (s) | Normalized Score | capped_max_revisit_gap_hours | num_satellites |
| --- | --- | ---: | ---: | ---: | ---: |
| case_0001 | true | 4000.9 | 69.41 | 6.1784 | 14 |
| case_0002 | true | 4738.0 | 81.97 | 8.0000 | 8 |
| case_0003 | true | 3814.1 | 70.00 | 6.0000 | 20 |
| case_0004 | true | 5601.1 | 70.09 | 8.0000 | 18 |
| case_0005 | true | 5601.7 | 75.32 | 6.0000 | 12 |

## opencode_dpsk

| Case | Valid | Duration (s) | Normalized Score | capped_max_revisit_gap_hours | num_satellites |
| --- | --- | ---: | ---: | ---: | ---: |
| case_0001 | true | 6434.9 | 72.08 | 6.0000 | 15 |
| case_0002 | true | 5161.0 | 72.08 | 8.0000 | 15 |
| case_0003 | true | 3162.4 | 70.00 | 6.0000 | 20 |
| case_0004 | true | 6754.5 | 69.28 | 8.2053 | 19 |
| case_0005 | true | 4811.5 | 71.33 | 6.0000 | 16 |

## opencode_minimax

| Case | Valid | Duration (s) | Normalized Score | capped_max_revisit_gap_hours | num_satellites |
| --- | --- | ---: | ---: | ---: | ---: |
| case_0001 | false | 3240.2 | 0.0000 | - | - |
| case_0002 | false | 3839.1 | 0.0000 | - | - |
| case_0003 | false | 1441.4 | 0.0000 | - | - |
| case_0004 | false | 3642.4 | 0.0000 | - | - |
| case_0005 | false | 4541.7 | 0.0000 | - | - |
