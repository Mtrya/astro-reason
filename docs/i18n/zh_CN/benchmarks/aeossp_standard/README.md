# AEOSSP Standard Benchmark

## 状态

本 benchmark 已实现，是仓库中标准的已完成 AEOSSP benchmark。

它替代了此前公开的 `aeosbench` benchmark 表面层。

## 问题摘要

`aeossp_standard` 是一个面向规划的敏捷地球观测卫星调度 benchmark。

对于每个测试实例，太空规划智能体（space agent）接收：

- 固定的 12 小时规划任务时域
- 由冻结 TLE 及 benchmark 自定义子系统参数所定义的固定真实地球观测卫星星座
- 一组带时间窗口的点成像任务
- 硬观测、电池和姿态机动约束

太空规划智能体必须返回：

- 一个基于事件的 `observation` 动作调度表

本 benchmark 侧重于调度，而非星座设计。求解器不可新增卫星、选取轨道或重新设计编队，也不提交低层姿态指令。

不在范围内：

- 星座设计
- 下行链路与数据交付规划
- 星上存储建模
- 云层覆盖与随机天气
- 详细辐射测量或图像质量评分
- 完整刚体姿态传播

## 数据集布局

规范数据集位于：

```text
dataset/
├── example_solution.json
├── index.json
└── cases/
    └── <split>/
        └── <case_id>/
            ├── mission.yaml
            ├── satellites.yaml
            └── tasks.yaml
```

`dataset/example_solution.json` 是一个与普通提交 schema 相同的真实解对象。`dataset/index.json` 记录测试实例元数据以及通过子集相对路径 `example_smoke_case` 配对的冒烟案例，benchmark 自有的构建契约位于 `benchmarks/aeossp_standard/splits.yaml`。

## 测试实例输入

每个测试实例目录恰好包含三个机器可读文件。

### `mission.yaml`

`mission.yaml` 定义规划任务时域、公共时间网格、传播模型和评分元数据。

重要字段：

- `case_id`
- `horizon_start`
- `horizon_end`
- `action_time_step_s`
- `geometry_sample_step_s`
- `resource_sample_step_s`
- `propagation`
  - `model`
  - `frame_inertial`
  - `frame_fixed`
  - `earth_shape`
- `scoring`
  - `ranking_order`
  - `reported_metrics`

所有时间戳均为 UTC 的 ISO 8601 格式。任务时域必须能被动作步长、几何步长和资源步长整除。

### `satellites.yaml`

`satellites.yaml` 包含该测试实例的固定星座。

每颗卫星条目包括：

- `satellite_id`
- `norad_catalog_id`
- `tle_line1`
- `tle_line2`
- `sensor`
  - `sensor_type`
- `attitude_model`
  - `max_slew_velocity_deg_per_s`
  - `max_slew_acceleration_deg_per_s2`
  - `settling_time_s`
  - `max_off_nadir_deg`
- `resource_model`
  - `battery_capacity_wh`
  - `initial_battery_wh`
  - `idle_power_w`
  - `imaging_power_w`
  - `slew_power_w`
  - `sunlit_charge_power_w`

公共数据集使用 benchmark 自有的可见光和红外传感器模板。

### `tasks.yaml`

`tasks.yaml` 包含任务时域内的成像请求。

每个任务包括：

- `task_id`
- `name`
- `latitude_deg`
- `longitude_deg`
- `altitude_m`
- `release_time`
- `due_time`
- `required_duration_s`
- `required_sensor_type`
- `weight`

冻结任务语义：

- `release_time`、`due_time` 和 `required_duration_s` 必须与公共动作网格对齐
- 任务是二元完成的，不能部分计分
- 目标必须在其时间窗口内被连续观测恰好 `required_duration_s`

## 解契约

有效提交是一个 JSON 对象，包含一个顶层数组：

- `actions`

每个动作格式为：

```json
{
  "type": "observation",
  "satellite_id": "sat_001",
  "task_id": "task_0001",
  "start_time": "2025-07-17T04:12:00Z",
  "end_time": "2025-07-17T04:12:20Z"
}
```

支持的动作类型：

- `observation`

求解器不提交：

- 可见性声明
- 功耗声明
- 姿态机动区间
- 姿态轨迹
- 完成声明

这些都由验证器确定。

## 有效性规则

如果任何硬约束被违反，验证器将拒绝该解，包括：

- 测试实例或解结构格式错误
- 测试实例内重复的任务或卫星标识符
- 解中引用了未知的卫星或任务
- 不支持的动作类型
- 零时长、偏离网格或超出任务时域的动作
- 超出任务窗口的动作
- 动作时长与 `required_duration_s` 不匹配
- 传感器类型不匹配
- 几何非法的观测
- 同一卫星的观测重叠
- 姿态机动加稳定间隙不足
- 电池耗尽至零以下

任何硬违规都会使整个解非法。非法解返回：

- `valid = false`
- 归零指标：
  - `CR = 0`
  - `WCR = 0`
  - `TAT = null`
  - `PC = 0`

## 几何、姿态与功耗语义

轨道传播和观测几何由验证器计算。

传播模型：

- 基于测试实例 TLE 的 Brahe `SGPPropagator`
- GCRF 惯性坐标系
- ITRF 地固坐标系
- WGS84 地球模型
- 静态零值 EOP 提供器，用于确定性离线验证

观测几何：

- 在公共几何网格点和动作边界上检查可见性
- 目标必须在动作区间内保持连续可见
- 所需侧摆角必须始终处于 `attitude_model.max_off_nadir_deg` 范围内

姿态机动模型：

- 求解器仅调度观测区间
- 验证器从几何中导出名义指向策略
- 姿态机动窗口在较晚的观测之前立即预留
- 姿态机动可行性使用标量加速-滑行-减速（bang-coast-bang）模型，参数包括：
  - `max_slew_velocity_deg_per_s`
  - `max_slew_acceleration_deg_per_s2`
  - `settling_time_s`
- 公共解可视化工具渲染的示意图侧摆曲线：
  - 在观测期间跟踪瞬时侧摆角
  - 在预留姿态机动窗口期间使用相同的标量 bang-coast-bang 姿态机动形状
  - 在连续观测之间保持前一次观测的终端指向
  - 在第一次预留姿态机动之前保持对地指向

功耗模型：

- 电池在整个任务时域上通过显式积分段进行模拟
- 总电力负载为：
  - `idle_power_w`
  - 观测期间加上 `imaging_power_w`
  - 姿态机动窗口期间加上 `slew_power_w`
- 卫星处于光照区时应用太阳能充电
- `PC` 仅报告总电力消耗；不减去太阳能充电

## 指标与排序

验证器报告：

- `CR`
- `WCR`
- `TAT`
- `PC`

指标含义：

- `CR`：已完成任务的比例
- `WCR`：已完成权重的比例
- `TAT`：已完成任务的平均 `(完成时间 - 释放时间)`，若无任何完成则为 `null`
- `PC`：整个任务时域内的总耗电瓦时数

任务完成语义：

- 如果至少有一次有效观测满足任务，则该任务完成
- 重复的有效观测不会获得额外加分
- 最早的有效完成时间决定 `TAT`

预期排序优先级：

1. 合法解优于非法解
2. 最大化 `WCR`
3. 最大化 `CR`
4. 最小化 `TAT`
5. 最小化 `PC`

## 公共入口点

数据集生成器：

```bash
uv run python -m benchmarks.aeossp_standard.generator.run \
  benchmarks/aeossp_standard/splits.yaml
```

验证器：

```bash
uv run python -m benchmarks.aeossp_standard.verifier.run \
  benchmarks/aeossp_standard/dataset/cases/test/case_0001 \
  benchmarks/aeossp_standard/dataset/example_solution.json
```

测试实例可视化工具：

```bash
uv run python -m benchmarks.aeossp_standard.visualizer.run case \
  --case-dir benchmarks/aeossp_standard/dataset/cases/test/case_0001
```

解可视化工具：

```bash
uv run python -m benchmarks.aeossp_standard.visualizer.run solution \
  --case-dir benchmarks/aeossp_standard/dataset/cases/test/case_0001 \
  --solution-path benchmarks/aeossp_standard/dataset/example_solution.json
```

可视化产物解读：

- 测试实例 `access_off_nadir_curves.png` 仅基于几何：
  - 它展示代表性的访问/侧摆需求曲线
  - 它不是名义姿态策略图
- 解 `attitude_curves.png` 是示意性的，但与验证器一致：
  - 它由验证器支持的观测区间和姿态机动窗口导出
  - 使用 benchmark 的标量 bang-coast-bang 姿态机动轮廓，而非线性角度插值

规范生成器需要提交的 `splits.yaml` 路径，并在 `dataset/cases/test/` 和 `dataset/index.json` 下复现 benchmark 自有的数据集输出。

## 生成器与规范数据集

生成器根据 benchmark 自有规则构建测试实例，而非手写测试实例列表。

当前子集决策：

- 本次契约迁移仅保留一个提交子集：`test`
- 额外的 benchmark 自有子集被有意推迟到后续工作中，以确保本 issue 保持为契约清理而非 benchmark 重新设计
- 目前正在讨论的候选后续名称包括 `test_easy`、`test_medium`、`test_hard`、`test_medium_horizon_20220414` 和 `train`

当前规范测试实例族：

- 5 个规范测试实例
- 每测试实例 20 至 40 颗卫星
- 每测试实例 200 至 800 个任务
- 混合可见光/红外任务需求
- 混合城市/陆地背景目标来源
- 任务窗口来自真实访问机会

公共源数据工作流：

- vendored CelesTrak 地球资源 TLE 快照（`generator/cached_tles.py`）
- GeoNames 城市数据
- Natural Earth 陆地多边形

GeoNames 和 Natural Earth 的运行时源数据可能缓存到 `dataset/source_data/` 下，但该目录不被追踪，且运行生成器前不要求其必须存在。用于规范复现的 CelesTrak TLE 快照追踪在 `generator/cached_tles.py` 中。

`splits.yaml` 携带规范 `test` 子集的 benchmark 自有生成参数，包括任务时间、卫星池过滤、子系统模板和任务采样控制。保留的操作标志 `--download-dir`、`--output-dir` 和 `--force-download` 仅影响源数据的暂存位置或刷新行为，不是替代的规范数据集契约。

## 测试与 Fixtures

验证器由以下聚焦的 fixture 驱动测试锁定：

- `tests/fixtures/aeossp_standard/`
- `tests/benchmarks/test_aeossp_standard_verifier.py`

这些 fixtures 覆盖：

- 精确的合法评分
- 零完成语义
- 重复观测无额外加分语义
- 传感器不匹配
- 可见性失效
- 重叠失效
- 姿态机动间隙失效
- 电池失效

## 谱系

`aeossp_standard` 参考了标准 AEOSSP 公式和此前的 benchmark 工作（如 AEOS-Bench），但它不是任何单一遗留 benchmark 或仿真器栈的复现。
