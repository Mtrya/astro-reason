# Verifier Exposure

stereo_imaging comparison across verifier exposure tiers.

Generated from the current `verifier_exposure` aggregate artifacts.

## Exposure Summary

| Exposure | Runs | Valid | Valid Rate | Mean Coverage | Mean Quality | Mean Score | Overall Statuses | Verifier Statuses |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| none | 10 | 4 | 0.4000 | 0.2412 | 0.2370 | 18.96 | success: 4, verifier_error: 2, verifier_invalid: 4 | error: 2, invalid: 4, valid: 4 |
| opaque | 10 | 9 | 0.9000 | 0.5360 | 0.4820 | 40.95 | success: 9, verifier_invalid: 1 | invalid: 1, valid: 9 |
| solver | 10 | 10 | 1.0000 | 0.9570 | 0.9402 | 94.02 | verified: 10 | verified: 10 |
| transparent | 10 | 10 | 1.0000 | 0.9037 | 0.8221 | 82.21 | success: 10 | valid: 10 |

## Exposure And System Summary

| Exposure | Kind | System | Runs | Valid | Valid Rate | Mean Coverage | Mean Quality | Mean Score | Overall Statuses |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| none | agent | codex | 5 | 4 | 0.8000 | 0.3859 | 0.3792 | 37.92 | success: 4, verifier_invalid: 1 |
| none | agent | opencode_dpsk | 5 | 0 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | verifier_error: 2, verifier_invalid: 3 |
| opaque | agent | codex | 5 | 5 | 1.0000 | 0.7232 | 0.6891 | 68.91 | success: 5 |
| opaque | agent | opencode_dpsk | 5 | 4 | 0.8000 | 0.3487 | 0.2749 | 13.00 | success: 4, verifier_invalid: 1 |
| solver | solver | stereo_imaging_cp_local_search_stereo_insertion | 5 | 5 | 1.0000 | 0.9705 | 0.9605 | 96.05 | verified: 5 |
| solver | solver | stereo_imaging_time_window_pruned_stereo_milp | 5 | 5 | 1.0000 | 0.9435 | 0.9200 | 92.00 | verified: 5 |
| transparent | agent | codex | 5 | 5 | 1.0000 | 0.9718 | 0.9562 | 95.62 | success: 5 |
| transparent | agent | opencode_dpsk | 5 | 5 | 1.0000 | 0.8356 | 0.6879 | 68.79 | success: 5 |

## Cases

| Exposure | Split | Kind | System | Case | Artifact | Overall Status | Verifier Status | Valid | Duration (s) | Coverage | Quality | Score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| none | test | agent | codex | case_0001 | present | success | valid | true | 805.3 | 0.9577 | 0.9297 | 92.97 |
| none | test | agent | codex | case_0002 | present | success | valid | true | 841.3 | 0 | 0 | 0.0000 |
| none | test | agent | codex | case_0003 | present | success | valid | true | 1240.1 | 0 | 0 | 0.0000 |
| none | test | agent | codex | case_0004 | present | verifier_invalid | invalid | false | 2113.5 | 0 | 0 | 0.0000 |
| none | test | agent | codex | case_0005 | present | success | valid | true | 835.7 | 0.9716 | 0.9663 | 96.63 |
| none | test | agent | opencode_dpsk | case_0001 | present | verifier_invalid | invalid | false | 5235.6 | 0 | 0 | 0.0000 |
| none | test | agent | opencode_dpsk | case_0002 | present | verifier_error | error | false | 5898.6 | - | - | 0.0000 |
| none | test | agent | opencode_dpsk | case_0003 | present | verifier_error | error | false | 4290.0 | - | - | 0.0000 |
| none | test | agent | opencode_dpsk | case_0004 | present | verifier_invalid | invalid | false | 4286.7 | 0 | 0 | 0.0000 |
| none | test | agent | opencode_dpsk | case_0005 | present | verifier_invalid | invalid | false | 4484.5 | 0 | 0 | 0.0000 |
| opaque | test | agent | codex | case_0001 | present | success | valid | true | 1746.6 | 0.9718 | 0.9694 | 96.94 |
| opaque | test | agent | codex | case_0002 | present | success | valid | true | 1829.6 | 0.9917 | 0.9675 | 96.75 |
| opaque | test | agent | codex | case_0003 | present | success | valid | true | 2561.9 | 0.7934 | 0.6906 | 69.06 |
| opaque | test | agent | codex | case_0004 | present | success | valid | true | 5087.2 | 0.0079 | 0.0079 | 0.7931 |
| opaque | test | agent | codex | case_0005 | present | success | valid | true | 1247.9 | 0.8511 | 0.8098 | 80.98 |
| opaque | test | agent | opencode_dpsk | case_0001 | present | success | valid | true | 5879.5 | 0 | 0 | 0.0000 |
| opaque | test | agent | opencode_dpsk | case_0002 | present | success | valid | true | 7200.9 | 0 | 0 | 0.0000 |
| opaque | test | agent | opencode_dpsk | case_0003 | present | success | valid | true | 5456.1 | 0.9421 | 0.6498 | 64.98 |
| opaque | test | agent | opencode_dpsk | case_0004 | present | verifier_invalid | invalid | false | 5591.7 | 0.8016 | 0.7248 | 0.0000 |
| opaque | test | agent | opencode_dpsk | case_0005 | present | success | valid | true | 5857.2 | 0 | 0 | 0.0000 |
| solver | test | solver | stereo_imaging_cp_local_search_stereo_insertion | case_0001 | baseline | verified | verified | true | 67.00 | 0.9789 | 0.9581 | 95.81 |
| solver | test | solver | stereo_imaging_cp_local_search_stereo_insertion | case_0002 | baseline | verified | verified | true | 77.64 | 0.9917 | 0.9887 | 98.87 |
| solver | test | solver | stereo_imaging_cp_local_search_stereo_insertion | case_0003 | baseline | verified | verified | true | 100.7 | 0.9587 | 0.9572 | 95.72 |
| solver | test | solver | stereo_imaging_cp_local_search_stereo_insertion | case_0004 | baseline | verified | verified | true | 63.70 | 0.9444 | 0.9238 | 92.38 |
| solver | test | solver | stereo_imaging_cp_local_search_stereo_insertion | case_0005 | baseline | verified | verified | true | 317.8 | 0.9787 | 0.9747 | 97.47 |
| solver | test | solver | stereo_imaging_time_window_pruned_stereo_milp | case_0001 | baseline | verified | verified | true | 100.8 | 0.9296 | 0.9130 | 91.30 |
| solver | test | solver | stereo_imaging_time_window_pruned_stereo_milp | case_0002 | baseline | verified | verified | true | 83.62 | 0.9917 | 0.9772 | 97.72 |
| solver | test | solver | stereo_imaging_time_window_pruned_stereo_milp | case_0003 | baseline | verified | verified | true | 88.63 | 0.9421 | 0.9176 | 91.76 |
| solver | test | solver | stereo_imaging_time_window_pruned_stereo_milp | case_0004 | baseline | verified | verified | true | 83.31 | 0.8968 | 0.8532 | 85.32 |
| solver | test | solver | stereo_imaging_time_window_pruned_stereo_milp | case_0005 | baseline | verified | verified | true | 88.51 | 0.9574 | 0.9388 | 93.88 |
| transparent | test | agent | codex | case_0001 | present | success | valid | true | 1712.3 | 0.9789 | 0.9732 | 97.32 |
| transparent | test | agent | codex | case_0002 | present | success | valid | true | 1127.9 | 0.9917 | 0.9829 | 98.29 |
| transparent | test | agent | codex | case_0003 | present | success | valid | true | 1897.8 | 0.9421 | 0.9358 | 93.58 |
| transparent | test | agent | codex | case_0004 | present | success | valid | true | 1801.2 | 0.9603 | 0.9062 | 90.62 |
| transparent | test | agent | codex | case_0005 | present | success | valid | true | 945.6 | 0.9858 | 0.9827 | 98.27 |
| transparent | test | agent | opencode_dpsk | case_0001 | present | success | valid | true | 3991.5 | 0.8451 | 0.6051 | 60.51 |
| transparent | test | agent | opencode_dpsk | case_0002 | present | success | valid | true | 7154.7 | 0.8099 | 0.4383 | 43.83 |
| transparent | test | agent | opencode_dpsk | case_0003 | present | success | valid | true | 6152.0 | 0.8347 | 0.7300 | 73.00 |
| transparent | test | agent | opencode_dpsk | case_0004 | present | success | valid | true | 4868.4 | 0.7381 | 0.7258 | 72.58 |
| transparent | test | agent | opencode_dpsk | case_0005 | present | success | valid | true | 4979.4 | 0.9504 | 0.9405 | 94.05 |
