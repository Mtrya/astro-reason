# SatNet

Generated from the current `main_agentic` aggregate summaries.

| Harness | Present | Success | Valid | Invalid | Timeout | Primary Mean | Normalized Mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| claude_code_dpsk | 5 | 5 | 5 | 0 | 0 | score_hours=1030.8 | 45.77 |
| codex | 5 | 5 | 5 | 0 | 0 | score_hours=1461.8 | 31.98 |
| kimi_cli | 5 | 5 | 5 | 0 | 0 | score_hours=1207.6 | 45.21 |
| opencode_minimax | 5 | 2 | 2 | 0 | 0 | score_hours=930.5 | 13.52 |
| opencode_dpsk | 5 | 4 | 4 | 0 | 0 | score_hours=1127.6 | 40.41 |

## claude_code_dpsk

| Case | Valid | Duration (s) | Normalized Score | score_hours | n_satisfied_requests | u_rms | u_max | n_tracks |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| W10_2018 | true | 2880.0 | 42.20 | 951.2 | 168 | 0.4374 | 1.0000 | 218 |
| W20_2018 | true | 1518.8 | 61.33 | 1052.2 | 208 | 0.2775 | 0.7143 | 316 |
| W30_2018 | true | 2130.3 | 52.88 | 1218.5 | 226 | 0.3542 | 0.8222 | 270 |
| W40_2018 | true | 4436.7 | 35.76 | 1025.1 | 172 | 0.5232 | 1.0000 | 242 |
| W50_2018 | true | 1172.1 | 36.69 | 906.9 | 163 | 0.5108 | 1.0000 | 179 |

## codex

| Case | Valid | Duration (s) | Normalized Score | score_hours | n_satisfied_requests | u_rms | u_max | n_tracks |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| W10_2018 | true | 2288.2 | 31.70 | 1555.6 | 129 | 0.5774 | 1.0000 | 272 |
| W20_2018 | true | 507.6 | 25.94 | 1667.0 | 108 | 0.6541 | 1.0000 | 185 |
| W30_2018 | true | 769.2 | 21.81 | 1414.4 | 87 | 0.7091 | 1.0000 | 238 |
| W40_2018 | true | 583.9 | 21.79 | 1574.9 | 104 | 0.7094 | 1.0000 | 190 |
| W50_2018 | true | 1111.2 | 58.66 | 1097.0 | 188 | 0.3132 | 0.7143 | 278 |

## kimi_cli

| Case | Valid | Duration (s) | Normalized Score | score_hours | n_satisfied_requests | u_rms | u_max | n_tracks |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| W10_2018 | true | 7200.9 | 72.44 | 1002.4 | 196 | 0.2007 | 0.5000 | 236 |
| W20_2018 | true | 3485.0 | 16.87 | 1660.2 | 67 | 0.7750 | 1.0000 | 176 |
| W30_2018 | true | 5215.9 | 63.56 | 1121.5 | 235 | 0.2598 | 0.6780 | 268 |
| W40_2018 | true | 5756.3 | 44.43 | 1105.7 | 248 | 0.4076 | 1.0000 | 248 |
| W50_2018 | true | 3389.9 | 28.72 | 1148.0 | 116 | 0.6171 | 1.0000 | 126 |

## opencode_dpsk

| Case | Valid | Duration (s) | Normalized Score | score_hours | n_satisfied_requests | u_rms | u_max | n_tracks |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| W10_2018 | true | 3618.2 | 55.74 | 951.6 | 200 | 0.3330 | 0.7714 | 212 |
| W20_2018 | true | 4915.5 | 46.89 | 1211.8 | 212 | 0.3748 | 1.0000 | 283 |
| W30_2018 | true | 7202.5 | 68.33 | 1218.1 | 252 | 0.2270 | 0.5857 | 265 |
| W40_2018 | true | 4063.2 | 31.09 | 1128.9 | 174 | 0.5855 | 1.0000 | 230 |
| W50_2018 | false | 3051.5 | 0.0000 | - | - | - | - | - |

## opencode_minimax

| Case | Valid | Duration (s) | Normalized Score | score_hours | n_satisfied_requests | u_rms | u_max | n_tracks |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| W10_2018 | false | 721.5 | 0.0000 | - | - | - | - | - |
| W20_2018 | true | 1147.5 | 48.85 | 942.9 | 210 | 0.3725 | 0.9286 | 210 |
| W30_2018 | false | 1715.3 | 0.0000 | - | - | - | - | - |
| W40_2018 | false | 450.0 | 0.0000 | - | - | - | - | - |
| W50_2018 | true | 1544.0 | 18.73 | 918.1 | 92 | 0.7502 | 1.0000 | 98 |
