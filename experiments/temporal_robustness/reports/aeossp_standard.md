# Temporal Robustness

AEOSSP comparison across the default `test` split and `test_horizon_2022` split.

`test` agent rows are reused from `main_agentic`; `test_horizon_2022` agent rows come from this experiment.
Solver rows come from `baselines/main_solver.yaml`.
Case identifiers are split-scoped: `test/case_0001` and `test_horizon_2022/case_0001` are different cases.

## Summary

| System | Kind | test Runs | test Valid | test Mean WCR | test Mean CR | test Mean TAT | test Mean PC | test_horizon_2022 Runs | test_horizon_2022 Valid | test_horizon_2022 Mean WCR | test_horizon_2022 Mean CR | test_horizon_2022 Mean TAT | test_horizon_2022 Mean PC |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| codex | agent | 5 | 5 | 0.7075 | 0.7358 | 1025.1 | 19098.7 | 5 | 5 | 0.6949 | 0.7238 | 1003.6 | 18643.8 |
| opencode_dpsk | agent | 5 | 5 | 0.6820 | 0.7101 | 986.9 | 18671.9 | 5 | 5 | 0.6816 | 0.7104 | 953.1 | 18279.2 |
| greedy_lns | solver | 5 | 5 | 0.6816 | 0.7212 | 1128.3 | 18496.6 | 5 | 5 | 0.6874 | 0.7292 | 1120.2 | 18257.2 |
| mwis_conflict_graph | solver | 5 | 5 | 0.7582 | 0.7895 | 1017.8 | 19795.2 | 5 | 5 | 0.7667 | 0.8006 | 1034.1 | 19611.2 |

## test Cases

| Case | Kind | System | Valid | WCR | CR | TAT | PC | Status |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| case_0001 | agent | codex | true | 0.6325 | 0.6651 | 1150.3 | 17644.8 | success |
| case_0001 | agent | opencode_dpsk | true | 0.6201 | 0.6559 | 984.0 | 17523.0 | success |
| case_0001 | solver | greedy_lns | true | 0.6183 | 0.6662 | 1118.2 | 17313.3 | verified |
| case_0001 | solver | mwis_conflict_graph | true | 0.7057 | 0.7432 | 1051.1 | 18773.7 | verified |
| case_0002 | agent | codex | true | 0.7159 | 0.7404 | 948.6 | 19283.0 | success |
| case_0002 | agent | opencode_dpsk | true | 0.1136 | 0.0776 | 1234.9 | 8372.5 | success |
| case_0002 | solver | greedy_lns | true | 0.6978 | 0.7393 | 1120.8 | 18804.4 | verified |
| case_0002 | solver | mwis_conflict_graph | true | 0.7763 | 0.8057 | 1013.3 | 20150.9 | verified |
| case_0003 | agent | codex | true | 0.7202 | 0.7390 | 969.7 | 17853.3 | success |
| case_0003 | agent | opencode_dpsk | true | 0.6675 | 0.6865 | 988.9 | 17036.8 | success |
| case_0003 | solver | greedy_lns | true | 0.6988 | 0.7324 | 1150.9 | 17408.7 | verified |
| case_0003 | solver | mwis_conflict_graph | true | 0.7837 | 0.8063 | 1021.9 | 18710.1 | verified |
| case_0004 | agent | codex | true | 0.6718 | 0.7063 | 1117.7 | 18142.8 | success |
| case_0004 | agent | opencode_dpsk | true | 0.6789 | 0.7126 | 1092.8 | 18052.6 | success |
| case_0004 | solver | greedy_lns | true | 0.6706 | 0.7094 | 1140.3 | 17715.6 | verified |
| case_0004 | solver | mwis_conflict_graph | true | 0.7395 | 0.7757 | 1036.2 | 18966.2 | verified |
| case_0005 | agent | codex | true | 0.7968 | 0.8284 | 939.0 | 22569.9 | success |
| case_0005 | agent | opencode_dpsk | true | 0.7287 | 0.7563 | 934.8 | 21445.9 | success |
| case_0005 | solver | greedy_lns | true | 0.7227 | 0.7589 | 1111.2 | 21240.9 | verified |
| case_0005 | solver | mwis_conflict_graph | true | 0.7858 | 0.8168 | 966.6 | 22374.9 | verified |

## test_horizon_2022 Cases

| Case | Kind | System | Valid | WCR | CR | TAT | PC | Status |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| case_0001 | agent | codex | true | 0.6566 | 0.6903 | 1040.2 | 17544.0 | success |
| case_0001 | agent | opencode_dpsk | true | 0.6056 | 0.6338 | 1052.2 | 16102.3 | success |
| case_0001 | solver | greedy_lns | true | 0.6498 | 0.6918 | 1162.6 | 17001.1 | verified |
| case_0001 | solver | mwis_conflict_graph | true | 0.7210 | 0.7622 | 1076.5 | 18336.5 | verified |
| case_0002 | agent | codex | true | 0.6735 | 0.6979 | 1216.0 | 18733.8 | success |
| case_0002 | agent | opencode_dpsk | true | 0.6996 | 0.7259 | 925.5 | 19038.4 | success |
| case_0002 | solver | greedy_lns | true | 0.6776 | 0.7214 | 1094.8 | 18331.6 | verified |
| case_0002 | solver | mwis_conflict_graph | true | 0.7638 | 0.7962 | 1061.0 | 19975.9 | verified |
| case_0003 | agent | codex | true | 0.7097 | 0.7336 | 960.1 | 17643.5 | success |
| case_0003 | agent | opencode_dpsk | true | 0.6720 | 0.7044 | 954.0 | 17098.9 | success |
| case_0003 | solver | greedy_lns | true | 0.6930 | 0.7288 | 1144.1 | 17243.5 | verified |
| case_0003 | solver | mwis_conflict_graph | true | 0.7750 | 0.8045 | 1024.2 | 18427.1 | verified |
| case_0004 | agent | codex | true | 0.6965 | 0.7275 | 924.4 | 17686.3 | success |
| case_0004 | agent | opencode_dpsk | true | 0.7068 | 0.7312 | 946.1 | 17846.4 | success |
| case_0004 | solver | greedy_lns | true | 0.6974 | 0.7407 | 1099.7 | 17641.9 | verified |
| case_0004 | solver | mwis_conflict_graph | true | 0.7763 | 0.8097 | 1023.2 | 18844.3 | verified |
| case_0005 | agent | codex | true | 0.7382 | 0.7695 | 877.5 | 21611.5 | success |
| case_0005 | agent | opencode_dpsk | true | 0.7239 | 0.7569 | 887.6 | 21309.9 | success |
| case_0005 | solver | greedy_lns | true | 0.7190 | 0.7635 | 1099.9 | 21068.0 | verified |
| case_0005 | solver | mwis_conflict_graph | true | 0.7973 | 0.8305 | 985.8 | 22472.4 | verified |
