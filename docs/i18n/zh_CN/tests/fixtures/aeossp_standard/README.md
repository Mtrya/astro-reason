These fixtures 锁定独立的 `aeossp_standard` 验证器行为。

原则：

- 保持案例微小且易于理解
- 每个 fixture 优先只覆盖一种行为
- 仅断言稳定、定义行为的报告字段
- 使用规范的 benchmark 案例文件：
  - `mission.yaml`
  - `satellites.yaml`
  - `tasks.yaml`
  - `solution.json`
  - `expected.json`

Fixture 集合：

- `full_completion_valid`
  - 一个任务、一次有效观测、精确指标
- `zero_completion_valid`
  - 有效的零观测调度表，`TAT = null`
- `duplicate_observation_no_bonus_valid`
  - 同一任务的两次有效观测只计一次
- `sensor_type_mismatch_invalid`
  - 观测使用了错误的传感器类型
- `visibility_invalid`
  - 观测未能通过连续可见性几何检查
- `observation_overlap_invalid`
  - 同一卫星的观测重叠
- `slew_gap_invalid`
  - 同一卫星的观测间距过近，无法完成机动加稳定
- `battery_depletion_invalid`
  - 电池下溢导致解决方案无效
