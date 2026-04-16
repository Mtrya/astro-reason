# Revisit Constellation Benchmark

## 状态

本 benchmark 已实现，是仓库中标准的已完成重访聚焦星座设计 benchmark。

它替代了此前的 `revisit_optimization` benchmark。

## 问题摘要

设计一个地球观测星座及其运行调度表，使任务时域内的目标重访间隔尽可能小。

对于每个案例，space agent 接收描述以下内容的 problem instance：

- 卫星模型
- 目标位置
- 硬任务与轨道约束
- 任务起止时间
- 预期重访间隔阈值

Space agent 必须返回：

- 星座定义
- 一系列已调度的动作

本 benchmark 将两个决策合并为单一任务：

1. 星座架构设计
2. 任务调度

## 预期的 Benchmark 范围

架构设计部分意味着定义任务起始时刻卫星的初始状态。从高层次看，求解器选择部署多少颗卫星（最多到案例特定的上限），并指定每颗卫星在 GCRF 坐标系中的初始状态。

调度部分意味着为整个任务时域内的该星座生成一个可行的动作序列。

发射设计、发射成本和部署操作不在范围内。本 benchmark 假设所提出的卫星在任务起始时刻已经以它们的初始状态存在。

## 案例输入

每个规范案例恰好包含两个机器可读文件：

- `assets.json`
- `mission.json`

### `assets.json`

`assets.json` 包含该案例的共享卫星模型和卫星数量上限。

- `satellite_model`
  - `model_name`
  - `sensor`
    - `max_off_nadir_angle_deg`
    - `max_range_m`
    - `obs_discharge_rate_w`
  - `resource_model`
    - `battery_capacity_wh`
    - `initial_battery_wh`
    - `idle_discharge_rate_w`
    - `sunlight_charge_rate_w`
  - `attitude_model`
    - `max_slew_velocity_deg_per_sec`
    - `max_slew_acceleration_deg_per_sec2`
    - `settling_time_sec`
    - `maneuver_discharge_rate_w`
  - `min_altitude_m`
  - `max_altitude_m`
- `max_num_satellites`

### `mission.json`

`mission.json` 包含任务时域和针对目标的重访需求：

- `horizon_start`
- `horizon_end`
- `targets[]`
  - `id`
  - `name`
  - `latitude_deg`
  - `longitude_deg`
  - `altitude_m`
  - `expected_revisit_period_hours`（以小时为单位的所需重访周期）
  - `min_elevation_deg`
  - `max_slant_range_m`
  - `min_duration_sec`

本 benchmark 的初始目标为 `48h` 任务时域。

## 解决方案契约

有效解决方案是一个包含两个顶层数组的单一 JSON 文档：

- `satellites`
- `actions`

### `satellites`

每个卫星条目定义任务起始时刻由求解器选择的一颗卫星：

- `satellite_id`
- `x_m`
- `y_m`
- `z_m`
- `vx_m_s`
- `vy_m_s`
- `vz_m_s`

所有状态都被解释为 SI 单位的 GCRF 笛卡尔状态。

### `actions`

动作列表定义了所提出星座的任务调度表。
支持的动作类型有：

- `observation`

每个动作包括：

- `action_type`
- `satellite_id`
- `start`
- `end`

观测动作还包括：

- `target_id`

## 有效性规则

约束违反应立即使解决方案无效。换句话说，指标仅对所有硬约束都满足的解决方案才有意义。

如果以下任何一条发生，验证器应拒绝该解决方案：

- 解决方案结构格式错误
- 卫星数量超过案例允许上限
- 卫星初始状态违反轨道约束
- 观测几何不可行
- 功耗约束违反
- 动作时间不一致
- 动作时间重叠
- 引用了未知的卫星或目标

随着 schema 变得更加具体，可能会添加额外的硬有效性检查。

## 指标与排序

本 benchmark 有意移除了 legacy 的映射覆盖分支。
新 benchmark 纯粹由重访驱动。

验证器为有效解决方案报告以下指标：

- `mean_revisit_gap_hours`
- `max_revisit_gap_hours`
- `satellite_count`
- `threshold_satisfied`
- `target_gap_summary`：每个目标的细分，包含 `expected_revisit_period_hours`、`max_revisit_gap_hours`、`mean_revisit_gap_hours` 和 `observation_count`

预期排序逻辑为：

1. 有效解决方案优于无效解决方案。
2. 如果并非所有目标都达到预期阈值以下的重访间隔，优先选择更低的 `max_revisit_gap_hours`，然后是更低的 `mean_revisit_gap_hours`。
3. 如果所有目标都达到预期阈值以下的重访间隔，优先选择使用卫星更少的解决方案，然后以 `mean_revisit_gap_hours` 作为平局决胜。

## 重访解读

本 benchmark 将差的重访表现视为低分，而不是自动的有效性失败。

成功的观测用其中点时刻表示。重访间隔包含任务开始和任务结束作为边界时间：

- 零次成功观测：重访间隔为整个任务时域
- 一次成功观测：间隔为开始到观测、以及观测到结束
- 多次成功观测：间隔在连续观测中点之间计算，再加上任务边界

## 仿真场景

本节描述验证器使用的物理与资源模型。

### 轨道传播

卫星状态使用 `brahe.NumericalOrbitPropagator` 传播：

- **力学模型**：仅 J2 引力（`brahe` 中的 `spherical_harmonic(2, 0)`）
- **坐标系**：传播用 GCRF/ECI，几何检查用 ECEF
- **时间系统**：UTC
- **EOP**：零值静态 EOP 提供器，用于确定性、离线友好的验证

验证器根据案例特定的海拔边界（最小/最大）验证初始卫星状态。初始状态必须形成闭合椭圆轨道（近地点和远地点在边界内）。

### 可见性计算

观测几何在动作期间以 10 秒间隔验证：

**目标可见性约束**：
- 仰角高于目标最小值（当地 ENU 坐标系）
- 斜距在目标最大范围和传感器最大范围内
- 离轴角在传感器最大离轴指向限制内

当前传感器模型是一个以天底为中心的指向锥，而不是完整的成像足迹模型。只有当目标的视线始终位于天底 `max_off_nadir_angle_deg` 范围内时，目标才是可观测的。

所有几何检查都使用采样时刻传播到的瞬时卫星位置。固定的 10 秒采样在正确性与运行时间之间取得平衡；样本之间的短暂违规可能无法被检测到。

### 星上资源

资源核算模拟离散时间点上的电池状态：

**功耗模型**：
- 通过 `brahe` 食甚计算进行受晒检测
- 受晒时以 `sunlight_charge_rate_w` 充电
- 放电组成部分：
  - 待机：`idle_discharge_rate_w`
  - 观测：+`obs_discharge_rate_w`
  - 机动：在机动/稳定窗口期间 +`maneuver_discharge_rate_w`

资源检查发生在动作边界、机动窗口边界和 30 秒间隔处。电池电量钳位到容量上限，只有耗尽至零以下才会使解决方案无效。

### 姿态与机动窗口

在连续观测之间，验证器使用 bang-coast-bang 机动轮廓计算所需机动时间：

- `attitude_model` 中的最大机动速度和加速度限制
- 机动完成后加上稳定时间
- 机动窗口不得与任何其他动作重叠
- 计算机动角度使用观测中点处的目标向量

验证器不验证观测期间的指向——只验证几何是否允许获取，以及连续目标之间是否有足够的机动时间。

## 验证器输出

验证器返回一个 JSON 对象，包含：

- `is_valid`
- `metrics`
- `errors`
- `warnings`

CLI 入口：

```bash
uv run python -m benchmarks.revisit_constellation.verifier.run <case_dir> <solution.json>
```

## 规范 Benchmark 结构

仓库结构为：

```text
benchmarks/revisit_constellation/
├── dataset/
│   ├── README.md
│   ├── index.json
│   ├── example_solution.json
│   └── cases/
│       └── <split>/<case_id>/{assets.json,mission.json}
├── splits.yaml
├── generator/
│   ├── __init__.py
│   ├── build.py
│   ├── sources.py
│   └── run.py
├── verifier/
│   ├── __init__.py
│   ├── models.py
│   ├── io.py
│   ├── engine.py
│   └── run.py
└── README.md
```

相关测试端产物位于：

```text
tests/fixtures/
tests/benchmarks/
```

## 规范数据集

提交的数据集位于 `dataset/cases/<split>/` 下，数据集级元数据在 `dataset/index.json` 中。当前规范数据集发布了五个 `test` 案例：`case_0001` 到 `case_0005`。

规范生成器入口点为：

```bash
uv run python -m benchmarks.revisit_constellation.generator.run \
  benchmarks/revisit_constellation/splits.yaml
```

下载的原始源 CSV 默认存储在数据集目录下的 `dataset/source_data/` 中。提交的数据集构建参数位于 `benchmarks/revisit_constellation/splits.yaml` 中；运行时源管理控制项（如 `--download-dir` 和 `--force-download`）仍是文档化 Kaggle 下载步骤周围的可选 CLI 覆盖项。
