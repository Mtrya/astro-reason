# Revisit Constellation

Generated from the current `main_agentic` aggregate summaries.

| Harness | Present | Success | Valid | Invalid | Timeout | Primary Mean | Processed Mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| codex | 5 | 5 | 5 | 0 | 0 | capped_max_revisit_gap_hours=7.6650 | revisit_score_pct=95.91 |
| kimi_cli | 5 | 5 | 5 | 0 | 0 | capped_max_revisit_gap_hours=6.8357 | revisit_score_pct=99.84 |
| opencode_minimax | 5 | 0 | 0 | 5 | 0 | capped_max_revisit_gap_hours=- | revisit_score_pct=0.0000 |
| opencode_dpsk | 5 | 5 | 5 | 0 | 0 | capped_max_revisit_gap_hours=6.8411 | revisit_score_pct=99.80 |

## codex

| Case | Overall | Verifier | Valid | Duration (s) | capped_max_revisit_gap_hours | num_satellites | revisit_score_pct |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| case_0001 | success | valid | true | 1773.5 | 6.0628 | 18 | 99.70 |
| case_0002 | success | valid | true | 1521.8 | 8.0000 | 9 | 100.0 |
| case_0003 | success | valid | true | 2439.7 | 6.0000 | 15 | 100.0 |
| case_0004 | success | valid | true | 2184.3 | 12.26 | 19 | 79.83 |
| case_0005 | success | valid | true | 2119.5 | 6.0000 | 19 | 100.0 |

## kimi_cli

| Case | Overall | Verifier | Valid | Duration (s) | capped_max_revisit_gap_hours | num_satellites | revisit_score_pct |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| case_0001 | success | valid | true | 4000.9 | 6.1784 | 14 | 99.18 |
| case_0002 | success | valid | true | 4738.0 | 8.0000 | 8 | 100.0 |
| case_0003 | success | valid | true | 3814.1 | 6.0000 | 20 | 100.0 |
| case_0004 | success | valid | true | 5601.1 | 8.0000 | 18 | 100.0 |
| case_0005 | success | valid | true | 5601.7 | 6.0000 | 12 | 100.0 |

## opencode_dpsk

| Case | Overall | Verifier | Valid | Duration (s) | capped_max_revisit_gap_hours | num_satellites | revisit_score_pct |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| case_0001 | success | valid | true | 6434.9 | 6.0000 | 15 | 100.0 |
| case_0002 | success | valid | true | 5161.0 | 8.0000 | 15 | 100.0 |
| case_0003 | success | valid | true | 3162.4 | 6.0000 | 20 | 100.0 |
| case_0004 | success | valid | true | 6754.5 | 8.2053 | 19 | 99.01 |
| case_0005 | success | valid | true | 4811.5 | 6.0000 | 16 | 100.0 |

## opencode_minimax

| Case | Overall | Verifier | Valid | Duration (s) | capped_max_revisit_gap_hours | num_satellites | revisit_score_pct |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| case_0001 | verifier_invalid | invalid | false | 3240.2 | - | - | 0.0000 |
| case_0002 | verifier_invalid | invalid | false | 3839.1 | - | - | 0.0000 |
| case_0003 | verifier_invalid | invalid | false | 1441.4 | - | - | 0.0000 |
| case_0004 | verifier_invalid | invalid | false | 3642.4 | - | - | 0.0000 |
| case_0005 | verifier_invalid | invalid | false | 4541.7 | - | - | 0.0000 |
