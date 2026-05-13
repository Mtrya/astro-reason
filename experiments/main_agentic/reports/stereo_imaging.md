# Stereo Imaging

Generated from the current `main_agentic` aggregate summaries.

| Harness | Present | Success | Valid | Invalid | Timeout | Primary Mean | Normalized Mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| codex | 5 | 5 | 5 | 0 | 0 | normalized_quality=0.6891 | 68.91 |
| kimi_cli | 5 | 5 | 5 | 0 | 0 | normalized_quality=0.0032 | 0.3153 |
| opencode_minimax | 5 | 1 | 1 | 1 | 0 | normalized_quality=0.0000 | 0.0000 |
| opencode_dpsk | 5 | 4 | 4 | 1 | 0 | normalized_quality=0.1300 | 13.00 |

## codex

| Case | Valid | Duration (s) | Normalized Score | normalized_quality | coverage_ratio |
| --- | --- | ---: | ---: | ---: | ---: |
| case_0001 | true | 1746.6 | 96.94 | 0.9694 | 0.9718 |
| case_0002 | true | 1829.6 | 96.75 | 0.9675 | 0.9917 |
| case_0003 | true | 2561.9 | 69.06 | 0.6906 | 0.7934 |
| case_0004 | true | 5087.2 | 0.7931 | 0.0079 | 0.0079 |
| case_0005 | true | 1247.9 | 80.98 | 0.8098 | 0.8511 |

## kimi_cli

| Case | Valid | Duration (s) | Normalized Score | normalized_quality | coverage_ratio |
| --- | --- | ---: | ---: | ---: | ---: |
| case_0001 | true | 7200.6 | 0.0000 | 0.0000 | 0.0000 |
| case_0002 | true | 7200.8 | 1.2524 | 0.0125 | 0.0165 |
| case_0003 | true | 7200.9 | 0.0000 | 0.0000 | 0.0000 |
| case_0004 | true | 7200.2 | 0.0000 | 0.0000 | 0.0000 |
| case_0005 | true | 4600.2 | 0.3240 | 0.0032 | 0.0071 |

## opencode_dpsk

| Case | Valid | Duration (s) | Normalized Score | normalized_quality | coverage_ratio |
| --- | --- | ---: | ---: | ---: | ---: |
| case_0001 | true | 5879.5 | 0.0000 | 0.0000 | 0.0000 |
| case_0002 | true | 7200.9 | 0.0000 | 0.0000 | 0.0000 |
| case_0003 | true | 5456.1 | 64.98 | 0.6498 | 0.9421 |
| case_0004 | false | 5591.7 | 0.0000 | 0.7248 | 0.8016 |
| case_0005 | true | 5857.2 | 0.0000 | 0.0000 | 0.0000 |

## opencode_minimax

| Case | Valid | Duration (s) | Normalized Score | normalized_quality | coverage_ratio |
| --- | --- | ---: | ---: | ---: | ---: |
| case_0001 | true | 6512.8 | 0.0000 | 0.0000 | 0.0000 |
| case_0002 | false | 864.1 | 0.0000 | - | - |
| case_0003 | false | 4550.7 | 0.0000 | - | - |
| case_0004 | false | 717.0 | 0.0000 | - | - |
| case_0005 | false | 3852.4 | 0.0000 | 0.0000 | 0.0000 |
