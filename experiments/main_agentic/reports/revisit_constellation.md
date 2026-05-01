# Revisit Constellation

Generated from the current `main_agentic` aggregate summaries.

| Harness | Present | Success | Valid | Invalid | Timeout | Primary Mean | Processed Mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| codex | 5 | 5 | 5 | 0 | 0 | capped_max_revisit_gap_hours=9.8668 | revisit_score_pct=98.59 |
| kimi_cli | 5 | 5 | 5 | 0 | 0 | capped_max_revisit_gap_hours=9.9796 | revisit_score_pct=98.16 |
| opencode_minimax | 5 | 1 | 1 | 3 | 1 | capped_max_revisit_gap_hours=48.00 | revisit_score_pct=0.0000 |
| opencode_dpsk | 5 | 5 | 5 | 0 | 0 | capped_max_revisit_gap_hours=9.6347 | revisit_score_pct=99.83 |

## codex

| Case | Overall | Verifier | Valid | Duration (s) | capped_max_revisit_gap_hours | num_satellites | revisit_score_pct |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| case_0001 | success | valid | true | 1471.7 | 8.0000 | 10 | 100.0 |
| case_0002 | success | valid | true | 2720.6 | 8.0000 | 12 | 100.0 |
| case_0003 | success | valid | true | 2673.1 | 8.0000 | 12 | 100.0 |
| case_0004 | success | valid | true | 2822.4 | 13.33 | 12 | 92.94 |
| case_0005 | success | valid | true | 2495.0 | 12.00 | 13 | 100.0 |

## kimi_cli

| Case | Overall | Verifier | Valid | Duration (s) | capped_max_revisit_gap_hours | num_satellites | revisit_score_pct |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| case_0001 | success | valid | true | 7206.9 | 8.6016 | 18 | 97.08 |
| case_0002 | success | valid | true | 6163.0 | 8.0000 | 16 | 100.0 |
| case_0003 | success | valid | true | 7200.5 | 9.2962 | 12 | 93.74 |
| case_0004 | success | valid | true | 7200.9 | 12.00 | 6 | 100.0 |
| case_0005 | success | valid | true | 3798.9 | 12.00 | 8 | 100.0 |

## opencode_dpsk

| Case | Overall | Verifier | Valid | Duration (s) | capped_max_revisit_gap_hours | num_satellites | revisit_score_pct |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| case_0001 | success | valid | true | 7200.6 | 8.0000 | 18 | 100.0 |
| case_0002 | success | valid | true | 7123.3 | 8.0000 | 12 | 100.0 |
| case_0003 | success | valid | true | 7200.5 | 8.1733 | 12 | 99.17 |
| case_0004 | success | valid | true | 4432.1 | 12.00 | 6 | 100.0 |
| case_0005 | success | valid | true | 4009.4 | 12.00 | 12 | 100.0 |

## opencode_minimax

| Case | Overall | Verifier | Valid | Duration (s) | capped_max_revisit_gap_hours | num_satellites | revisit_score_pct |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| case_0001 | verifier_invalid | invalid | false | 3113.1 | - | - | 0.0000 |
| case_0002 | success | valid | true | 3466.4 | 48.00 | 8 | 0.0000 |
| case_0003 | timeout | no_solution | - | 7201.4 | - | - | 0.0000 |
| case_0004 | verifier_invalid | invalid | false | 916.5 | - | - | 0.0000 |
| case_0005 | verifier_invalid | invalid | false | 6896.2 | - | - | 0.0000 |
