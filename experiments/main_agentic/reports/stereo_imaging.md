# Stereo Imaging

Generated from the current `main_agentic` aggregate summaries.

| Harness | Present | Success | Valid | Invalid | Timeout | Primary Mean | Processed Mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| codex | 5 | 5 | 5 | 0 | 0 | normalized_quality=0.5378 | - |
| kimi_cli | 5 | 4 | 4 | 0 | 0 | normalized_quality=0.0039 | - |
| opencode_minimax | 5 | 1 | 1 | 1 | 0 | normalized_quality=0.0000 | - |
| opencode_dpsk | 5 | 4 | 4 | 1 | 0 | normalized_quality=0.1624 | - |

## codex

| Case | Overall | Verifier | Valid | Duration (s) | normalized_quality | coverage_ratio |
| --- | --- | --- | --- | ---: | ---: | ---: |
| case_0001 | success | valid | true | 1602.6 | 0.2057 | 0.2254 |
| case_0002 | success | valid | true | 1829.6 | 0.9675 | 0.9917 |
| case_0003 | success | valid | true | 2561.9 | 0.6906 | 0.7934 |
| case_0004 | success | valid | true | 5301.2 | 0.0155 | 0.0159 |
| case_0005 | success | valid | true | 1247.9 | 0.8098 | 0.8511 |

## kimi_cli

| Case | Overall | Verifier | Valid | Duration (s) | normalized_quality | coverage_ratio |
| --- | --- | --- | --- | ---: | ---: | ---: |
| case_0001 | success | valid | true | 7200.6 | 0.0000 | 0.0000 |
| case_0002 | success | valid | true | 7200.8 | 0.0125 | 0.0165 |
| case_0003 | success | valid | true | 7200.9 | 0.0000 | 0.0000 |
| case_0004 | agent_failed | no_solution | - | 10.79 | - | - |
| case_0005 | success | valid | true | 4600.2 | 0.0032 | 0.0071 |

## opencode_dpsk

| Case | Overall | Verifier | Valid | Duration (s) | normalized_quality | coverage_ratio |
| --- | --- | --- | --- | ---: | ---: | ---: |
| case_0001 | success | valid | true | 5879.5 | 0.0000 | 0.0000 |
| case_0002 | success | valid | true | 7200.9 | 0.0000 | 0.0000 |
| case_0003 | success | valid | true | 5456.1 | 0.6498 | 0.9421 |
| case_0004 | verifier_invalid | invalid | false | 5591.7 | 0.7248 | 0.8016 |
| case_0005 | success | valid | true | 5857.2 | 0.0000 | 0.0000 |

## opencode_minimax

| Case | Overall | Verifier | Valid | Duration (s) | normalized_quality | coverage_ratio |
| --- | --- | --- | --- | ---: | ---: | ---: |
| case_0001 | success | valid | true | 6512.8 | 0.0000 | 0.0000 |
| case_0002 | verifier_error | error | - | 864.1 | - | - |
| case_0003 | verifier_error | error | - | 4550.7 | - | - |
| case_0004 | verifier_error | error | - | 717.0 | - | - |
| case_0005 | verifier_invalid | invalid | false | 3852.4 | 0.0000 | 0.0000 |
