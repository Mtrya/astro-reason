# SatNet

Generated from the current `main_agentic` aggregate summaries.

| Harness | Present | Success | Valid | Invalid | Timeout | Primary Mean | Processed Mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| claude_code_dpsk | 5 | 5 | 5 | 0 | 0 | score_hours=1030.8 | - |
| codex | 5 | 5 | 5 | 0 | 0 | score_hours=1461.8 | - |
| kimi_cli | 5 | 5 | 5 | 0 | 0 | score_hours=1207.6 | - |
| opencode_minimax | 5 | 2 | 2 | 0 | 0 | score_hours=930.5 | - |
| opencode_dpsk | 5 | 4 | 4 | 0 | 0 | score_hours=1127.6 | - |

## claude_code_dpsk

| Case | Overall | Verifier | Valid | Duration (s) | score_hours | n_satisfied_requests | u_rms | u_max | n_tracks |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| W10_2018 | success | valid | true | 2880.0 | 951.2 | 168 | 0.4374 | 1.0000 | 218 |
| W20_2018 | success | valid | true | 1518.8 | 1052.2 | 208 | 0.2775 | 0.7143 | 316 |
| W30_2018 | success | valid | true | 2130.3 | 1218.5 | 226 | 0.3542 | 0.8222 | 270 |
| W40_2018 | success | valid | true | 4436.7 | 1025.1 | 172 | 0.5232 | 1.0000 | 242 |
| W50_2018 | success | valid | true | 1172.1 | 906.9 | 163 | 0.5108 | 1.0000 | 179 |

## codex

| Case | Overall | Verifier | Valid | Duration (s) | score_hours | n_satisfied_requests | u_rms | u_max | n_tracks |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| W10_2018 | success | valid | true | 2288.2 | 1555.6 | 129 | 0.5774 | 1.0000 | 272 |
| W20_2018 | success | valid | true | 507.6 | 1667.0 | 108 | 0.6541 | 1.0000 | 185 |
| W30_2018 | success | valid | true | 769.2 | 1414.4 | 87 | 0.7091 | 1.0000 | 238 |
| W40_2018 | success | valid | true | 583.9 | 1574.9 | 104 | 0.7094 | 1.0000 | 190 |
| W50_2018 | success | valid | true | 1111.2 | 1097.0 | 188 | 0.3132 | 0.7143 | 278 |

## kimi_cli

| Case | Overall | Verifier | Valid | Duration (s) | score_hours | n_satisfied_requests | u_rms | u_max | n_tracks |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| W10_2018 | success | valid | true | 7200.9 | 1002.4 | 196 | 0.2007 | 0.5000 | 236 |
| W20_2018 | success | valid | true | 3485.0 | 1660.2 | 67 | 0.7750 | 1.0000 | 176 |
| W30_2018 | success | valid | true | 5215.9 | 1121.5 | 235 | 0.2598 | 0.6780 | 268 |
| W40_2018 | success | valid | true | 5756.3 | 1105.7 | 248 | 0.4076 | 1.0000 | 248 |
| W50_2018 | success | valid | true | 3389.9 | 1148.0 | 116 | 0.6171 | 1.0000 | 126 |

## opencode_dpsk

| Case | Overall | Verifier | Valid | Duration (s) | score_hours | n_satisfied_requests | u_rms | u_max | n_tracks |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| W10_2018 | success | valid | true | 3618.2 | 951.6 | 200 | 0.3330 | 0.7714 | 212 |
| W20_2018 | success | valid | true | 4915.5 | 1211.8 | 212 | 0.3748 | 1.0000 | 283 |
| W30_2018 | success | valid | true | 7202.5 | 1218.1 | 252 | 0.2270 | 0.5857 | 265 |
| W40_2018 | success | valid | true | 4063.2 | 1128.9 | 174 | 0.5855 | 1.0000 | 230 |
| W50_2018 | verifier_error | error | - | 3051.5 | - | - | - | - | - |

## opencode_minimax

| Case | Overall | Verifier | Valid | Duration (s) | score_hours | n_satisfied_requests | u_rms | u_max | n_tracks |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| W10_2018 | verifier_error | error | - | 721.5 | - | - | - | - | - |
| W20_2018 | success | valid | true | 1147.5 | 942.9 | 210 | 0.3725 | 0.9286 | 210 |
| W30_2018 | verifier_error | error | - | 1715.3 | - | - | - | - | - |
| W40_2018 | verifier_error | error | - | 450.0 | - | - | - | - | - |
| W50_2018 | success | valid | true | 1544.0 | 918.1 | 92 | 0.7502 | 1.0000 | 98 |
