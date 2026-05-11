# SatNet

Generated from the current `main_agentic` aggregate summaries.

| Harness | Present | Success | Valid | Invalid | Timeout | Primary Mean | Normalized Mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| codex | 5 | 5 | 5 | 0 | 0 | u_rms=0.2342 | 69.45 |
| kimi_cli | 4 | 4 | 4 | 0 | 0 | u_rms=0.2321 | 67.07 |
| opencode_minimax | 5 | 4 | 4 | 1 | 0 | u_rms=0.4372 | 37.54 |
| opencode_dpsk | 4 | 4 | 4 | 0 | 0 | u_rms=0.2653 | 59.97 |

## codex

| Case | Valid | Duration (s) | Normalized Score | u_rms | u_max | n_satisfied_requests | score_hours | n_tracks |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| W10_2018 | true | 987.7 | 78.09 | 0.1540 | 0.4143 | 234 | 1028.8 | 244 |
| W20_2018 | true | 4702.2 | 61.17 | 0.2299 | 0.8636 | 252 | 1144.1 | 265 |
| W30_2018 | true | 745.8 | 69.81 | 0.2475 | 0.4649 | 202 | 1054.4 | 297 |
| W40_2018 | true | 982.0 | 58.37 | 0.3646 | 0.5714 | 208 | 1005.2 | 243 |
| W50_2018 | true | 1586.4 | 79.83 | 0.1753 | 0.2811 | 219 | 1062.1 | 273 |

## kimi_cli

| Case | Valid | Duration (s) | Normalized Score | u_rms | u_max | n_satisfied_requests | score_hours | n_tracks |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| W10_2018 | true | 7200.3 | 81.79 | 0.1360 | 0.3204 | 221 | 1012.9 | 245 |
| W20_2018 | true | 7200.3 | 53.87 | 0.2968 | 0.9548 | 204 | 888.7 | 206 |
| W30_2018 | true | 7200.7 | 70.41 | 0.2197 | 0.5245 | 201 | 1174.9 | 279 |
| W40_2018 | true | 6200.8 | 62.21 | 0.2760 | 0.6835 | 223 | 1179.6 | 281 |

## opencode_dpsk

| Case | Valid | Duration (s) | Normalized Score | u_rms | u_max | n_satisfied_requests | score_hours | n_tracks |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| W10_2018 | true | 7200.3 | 73.68 | 0.1367 | 0.6429 | 232 | 1066.5 | 283 |
| W20_2018 | true | 7200.7 | 71.67 | 0.1622 | 0.6466 | 258 | 1213.3 | 270 |
| W30_2018 | true | 7200.8 | 50.61 | 0.3483 | 0.9308 | 190 | 1017.8 | 263 |
| W40_2018 | true | 4152.5 | 43.94 | 0.4142 | 1.0000 | 194 | 1020.9 | 226 |

## opencode_minimax

| Case | Valid | Duration (s) | Normalized Score | u_rms | u_max | n_satisfied_requests | score_hours | n_tracks |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| W10_2018 | true | 2154.1 | 55.81 | 0.3273 | 0.7857 | 200 | 788.7 | 210 |
| W20_2018 | true | 2473.5 | 26.94 | 0.6408 | 1.0000 | 99 | 1037.4 | 116 |
| W30_2018 | true | 2090.7 | 62.67 | 0.2978 | 0.6000 | 250 | 1060.0 | 259 |
| W40_2018 | true | 2340.2 | 42.28 | 0.4830 | 0.8596 | 194 | 805.7 | 203 |
| W50_2018 | false | 2074.1 | 0.0000 | 0.3592 | 0.6395 | 173 | 835.9 | 264 |
