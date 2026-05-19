# SatNet

satnet memory-accumulation comparison by memory source and evaluation harness.

Generated from the current `memory_accumulation` aggregate artifacts.

## Source And Harness Summary

| Memory Source | Harness | Expected | Present | Missing | Valid | Mean Score | Overall Statuses |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| codex | codex | 5 | 0 | 5 | 0 | 0.0000 | missing_artifact: 5 |
| codex | opencode_dpsk | 5 | 3 | 2 | 3 | 38.75 | missing_artifact: 2, success: 3 |
| codex | opencode_minimax | 5 | 5 | 0 | 5 | 32.46 | success: 5 |
| none | codex | 5 | 5 | 0 | 5 | 69.45 | success: 5 |
| none | opencode_dpsk | 5 | 5 | 0 | 5 | 60.23 | success: 5 |
| none | opencode_minimax | 5 | 5 | 0 | 4 | 37.54 | success: 4, verifier_invalid: 1 |
| opencode_dpsk | codex | 5 | 0 | 5 | 0 | 0.0000 | missing_artifact: 5 |
| opencode_dpsk | opencode_dpsk | 5 | 5 | 0 | 5 | 65.97 | success: 5 |
| opencode_dpsk | opencode_minimax | 5 | 5 | 0 | 4 | 36.03 | success: 4, verifier_invalid: 1 |
| opencode_minimax | codex | 5 | 0 | 5 | 0 | 0.0000 | missing_artifact: 5 |
| opencode_minimax | opencode_dpsk | 5 | 0 | 5 | 0 | 0.0000 | missing_artifact: 5 |
| opencode_minimax | opencode_minimax | 5 | 0 | 5 | 0 | 0.0000 | missing_artifact: 5 |

## Cases

| Memory Source | Harness | Split | Case | Artifact | Overall Status | Verifier Status | Valid | Duration (s) | Score | score_hours | n_satisfied_requests | u_rms | u_max | n_tracks |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| codex | codex | test | W10_2018 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| codex | codex | test | W20_2018 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| codex | codex | test | W30_2018 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| codex | codex | test | W40_2018 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| codex | codex | test | W50_2018 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| codex | opencode_dpsk | test | W10_2018 | present | success | valid | true | 2597.8 | 64.49 | 951.5 | 204 | 0.2234 | 0.7500 | 262 |
| codex | opencode_dpsk | test | W20_2018 | present | success | valid | true | 2597.7 | 68.83 | 1118.2 | 216 | 0.2542 | 0.4842 | 251 |
| codex | opencode_dpsk | test | W30_2018 | present | success | valid | true | 2597.7 | 60.42 | 1041.5 | 205 | 0.2983 | 0.6883 | 254 |
| codex | opencode_dpsk | test | W40_2018 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| codex | opencode_dpsk | test | W50_2018 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| codex | opencode_minimax | test | W10_2018 | present | success | valid | true | 145.9 | 41.01 | 627.3 | 135 | 0.4533 | 1 | 205 |
| codex | opencode_minimax | test | W20_2018 | present | success | valid | true | 145.9 | 18.09 | 1078.6 | 110 | 0.7589 | 1 | 122 |
| codex | opencode_minimax | test | W30_2018 | present | success | valid | true | 1523.9 | 37.27 | 734.7 | 180 | 0.5030 | 1 | 180 |
| codex | opencode_minimax | test | W40_2018 | present | success | valid | true | 1038.3 | 28.06 | 966.8 | 110 | 0.6258 | 1 | 119 |
| codex | opencode_minimax | test | W50_2018 | present | success | valid | true | 946.7 | 37.90 | 602.6 | 157 | 0.5060 | 0.9660 | 157 |
| none | codex | test | W10_2018 | present | success | valid | true | 987.7 | 78.09 | 1028.8 | 234 | 0.1540 | 0.4143 | 244 |
| none | codex | test | W20_2018 | present | success | valid | true | 4702.2 | 61.17 | 1144.1 | 252 | 0.2299 | 0.8636 | 265 |
| none | codex | test | W30_2018 | present | success | valid | true | 745.8 | 69.81 | 1054.4 | 202 | 0.2475 | 0.4649 | 297 |
| none | codex | test | W40_2018 | present | success | valid | true | 982.0 | 58.37 | 1005.2 | 208 | 0.3646 | 0.5714 | 243 |
| none | codex | test | W50_2018 | present | success | valid | true | 1586.4 | 79.83 | 1062.1 | 219 | 0.1753 | 0.2811 | 273 |
| none | opencode_dpsk | test | W10_2018 | present | success | valid | true | 7200.3 | 73.68 | 1066.5 | 232 | 0.1367 | 0.6429 | 283 |
| none | opencode_dpsk | test | W20_2018 | present | success | valid | true | 7200.7 | 71.67 | 1213.3 | 258 | 0.1622 | 0.6466 | 270 |
| none | opencode_dpsk | test | W30_2018 | present | success | valid | true | 7200.8 | 50.61 | 1017.8 | 190 | 0.3483 | 0.9308 | 263 |
| none | opencode_dpsk | test | W40_2018 | present | success | valid | true | 4152.5 | 43.94 | 1020.9 | 194 | 0.4142 | 1 | 226 |
| none | opencode_dpsk | test | W50_2018 | present | success | valid | true | 7200.2 | 61.25 | 895.3 | 193 | 0.2786 | 0.7143 | 222 |
| none | opencode_minimax | test | W10_2018 | present | success | valid | true | 2154.1 | 55.81 | 788.7 | 200 | 0.3273 | 0.7857 | 210 |
| none | opencode_minimax | test | W20_2018 | present | success | valid | true | 2473.5 | 26.94 | 1037.4 | 99 | 0.6408 | 1 | 116 |
| none | opencode_minimax | test | W30_2018 | present | success | valid | true | 2090.7 | 62.67 | 1060 | 250 | 0.2978 | 0.6000 | 259 |
| none | opencode_minimax | test | W40_2018 | present | success | valid | true | 2340.2 | 42.28 | 805.7 | 194 | 0.4830 | 0.8596 | 203 |
| none | opencode_minimax | test | W50_2018 | present | verifier_invalid | invalid | false | 2074.1 | 0 | 835.9 | 173 | 0.3592 | 0.6395 | 264 |
| opencode_dpsk | codex | test | W10_2018 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_dpsk | codex | test | W20_2018 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_dpsk | codex | test | W30_2018 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_dpsk | codex | test | W40_2018 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_dpsk | codex | test | W50_2018 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_dpsk | opencode_dpsk | test | W10_2018 | present | success | valid | true | 3113.9 | 71.69 | 913.2 | 211 | 0.2154 | 0.4860 | 220 |
| opencode_dpsk | opencode_dpsk | test | W20_2018 | present | success | valid | true | 3327.8 | 74.04 | 1097.8 | 226 | 0.2143 | 0.3956 | 254 |
| opencode_dpsk | opencode_dpsk | test | W30_2018 | present | success | valid | true | 3246.6 | 61.86 | 1126.4 | 204 | 0.2941 | 0.6433 | 273 |
| opencode_dpsk | opencode_dpsk | test | W40_2018 | present | success | valid | true | 3796.7 | 62.02 | 1094.6 | 186 | 0.3384 | 0.5038 | 241 |
| opencode_dpsk | opencode_dpsk | test | W50_2018 | present | success | valid | true | 2229.7 | 60.23 | 892.8 | 186 | 0.2922 | 0.7143 | 202 |
| opencode_dpsk | opencode_minimax | test | W10_2018 | present | verifier_invalid | invalid | false | 1257.5 | 0 | 662.9 | 177 | 0.3990 | 1 | 177 |
| opencode_dpsk | opencode_minimax | test | W20_2018 | present | success | valid | true | 4805.6 | 52.37 | 875.2 | 222 | 0.3732 | 0.7857 | 222 |
| opencode_dpsk | opencode_minimax | test | W30_2018 | present | success | valid | true | 1442.6 | 30.99 | 1024.9 | 111 | 0.5869 | 1 | 122 |
| opencode_dpsk | opencode_minimax | test | W40_2018 | present | success | valid | true | 4488.7 | 40.49 | 1116.1 | 176 | 0.4602 | 1 | 228 |
| opencode_dpsk | opencode_minimax | test | W50_2018 | present | success | valid | true | 1002.8 | 56.32 | 793.2 | 175 | 0.3824 | 0.6000 | 186 |
| opencode_minimax | codex | test | W10_2018 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_minimax | codex | test | W20_2018 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_minimax | codex | test | W30_2018 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_minimax | codex | test | W40_2018 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_minimax | codex | test | W50_2018 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_minimax | opencode_dpsk | test | W10_2018 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_minimax | opencode_dpsk | test | W20_2018 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_minimax | opencode_dpsk | test | W30_2018 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_minimax | opencode_dpsk | test | W40_2018 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_minimax | opencode_dpsk | test | W50_2018 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_minimax | opencode_minimax | test | W10_2018 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_minimax | opencode_minimax | test | W20_2018 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_minimax | opencode_minimax | test | W30_2018 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_minimax | opencode_minimax | test | W40_2018 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
| opencode_minimax | opencode_minimax | test | W50_2018 | missing_artifact | missing_artifact | missing_artifact | - | - | 0 | - | - | - | - | - |
