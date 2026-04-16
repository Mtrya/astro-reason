# AEOSSP Standard Benchmark

## 状态

本 benchmark 已实现，是仓库中标准的已完成 AEOSSP benchmark。

它替代了此前公开的 `aeosbench` benchmark 表面层。

## 问题摘要

`aeossp_standard` 是一个面向规划的敏捷地球观测卫星调度 benchmark。

对于每个案例，space agent 接收：

- 固定的 12 小时规划时域
- 由冻结 TLE 和 benchmark 自有子系统参数表达的固定真实地球观测卫星星座
- 一组带时间窗口的点成像任务
- 硬观测、电池和机动约束

Space agent 必须返回：

- 一个基于事件的 `observation` 动作调度表

本 benchmark 侧重于调度，而非星座设计。求解器不添加卫星、选择轨道、重新设计编队，也不提交低层姿态指令。

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

`dataset/example_solution.json` 是一个与普通提交 schema 相同的真实解决方案对象。`dataset/index.json` 记录案例元数据以及通过划分相对路径 `example_smoke_case` 配对的冒烟案例，benchmark 自有的构建契约位于 `benchmarks/aeossp_standard/splits.yaml`。

## 案例输入

每个案例目录恰好包含三个机器可读文件。

### `mission.yaml`

`mission.yaml` 定义规划时域、公共时间网格、传播模型和评分元数据。

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

所有时间戳均为 UTC 的 ISO 8601 格式。时域必须能被动作步长、几何步长和资源步长整除。

### `satellites.yaml`

`satellites.yaml` 包含该案例的固定星座。

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

`tasks.yaml` 包含时域内的成像请求。

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

## 解决方案契约

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
- 机动区间
- 姿态轨迹
- 完成声明

这些都由验证器拥有。

## 有效性规则

如果任何硬规则被违反，验证器将拒绝该解决方案，包括：

- 案例或解决方案结构格式错误
- 案例内重复的任务或卫星标识符
- 解决方案中引用了未知的卫星或任务
- 不支持的动作类型
- 零时长、偏离网格或超出时域的动作
- 超出任务窗口的动作
- 动作时长与 `required_duration_s` 不匹配
- 传感器类型不匹配
- 几何无效的观测
- 同一卫星的观测重叠
- 机动加稳定间隙不足
- 电池耗尽至零以下

任何硬违规都会使整个解决方案无效。无效解决方案返回：

- `valid = false`
- 归零指标：
  - `CR = 0`
  - `WCR = 0`
  - `TAT = null`
  - `PC = 0`

## 几何、姿态与功耗语义

验证器拥有轨道传播和观测几何。

传播模型：

- 基于案例 TLE 的 Brahe `SGPPropagator`
- GCRF 惯性坐标系
- ITRF 地固坐标系
- WGS84 地球模型
- 静态零值 EOP 提供器，用于确定性离线验证

观测几何：

- 在公共几何网格点和动作边界上检查可见性
- 目标必须在动作区间内保持连续可见
- 所需离轴角必须始终处于 `attitude_model.max_off_nadir_deg` 范围内

姿态/机动模型：

- 求解器仅调度观测区间
- 验证器从几何中导出名义指向策略
- 机动窗口在较晚的观测之前立即预留
- 机动可行性使用标量 bang-coast-bang 模型，参数包括：
  - `max_slew_velocity_deg_per_s`
  - `max_slew_acceleration_deg_per_s2`
  - `settling_time_s`
- 公共解决方案可视化器渲染的示意图离轴曲线：
  - 在观测期间跟踪瞬时离轴角
  - 在预留机动窗口期间使用相同的标量 bang-coast-bang 机动形状
  - 在连续观测之间保持前一次观测的终端指向
  - 在第一次预留机动之前保持对地指向

功耗模型：

- 电池在整个时域上通过显式积分段进行模拟
- 总电力负载为：
  - `idle_power_w`
  - 观测期间加上 `imaging_power_w`
  - 机动窗口期间加上 `slew_power_w`
- 卫星受晒时应用太阳能充电
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
- `PC`：整个时域内的总耗电瓦时数

任务完成语义：

- 如果至少有一次有效观测满足任务，则该任务完成
- 重复的有效观测不会获得额外加分
- 最早的有效完成时间决定 `TAT`

预期排序优先级：

1. 有效解决方案优于无效解决方案
2. 最大化 `WCR`
3. 最大化 `CR`
4. 最小化 `TAT`
5. 最小化 `PC`

## 公共入口点

生成器：

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

案例可视化器：

```bash
uv run python -m benchmarks.aeossp_standard.visualizer.run case \
  --case-dir benchmarks/aeossp_standard/dataset/cases/test/case_0001
```

解决方案可视化器：

```bash
uv run python -m benchmarks.aeossp_standard.visualizer.run solution \
  --case-dir benchmarks/aeossp_standard/dataset/cases/test/case_0001 \
  --solution-path benchmarks/aeossp_standard/dataset/example_solution.json
```

可视化产物解读：

- 案例 `access_off_nadir_curves.png` 仅基于几何：
  - 它展示代表性的访问/离轴需求曲线
  - 它不是名义姿态策略图
- 解决方案 `attitude_curves.png` 是示意性的，但与验证器一致：
  - 它由验证器支持的观测区间和机动窗口导出
  - 使用 benchmark 的标量 bang-coast-bang 机动轮廓，而非线性角度插值

规范生成器需要提交的 `splits.yaml` 路径，并在 `dataset/cases/test/` 和 `dataset/index.json` 下复现 benchmark 自有的数据集输出。

## 生成器与规范数据集

生成器根据 benchmark 自有规则构建案例，而非手写案例列表。

当前划分决策：

- 本次契约迁移仅保留一个提交划分：`test`
- 额外的 benchmark 自有划分被有意推迟到后续工作中，以确保本 issue 保持为契约清理而非 benchmark 重新设计
- 目前正在讨论的候选后续名称包括 `test_easy`、`test_medium`、`test_hard`、`test_medium_horizon_20220414` 和 `train`

当前规范案例族：

- 5 个规范案例
- 每案例 20 至 40 颗卫星
- 每案例 200 至 800 个任务
- 混合可见光/红外任务需求
- 混合城市/陆地背景目标来源
- 任务窗口来自真实访问机会

公共源数据工作流：

-  vendored CelesTrak 地球资源 TLE 快照（`generator/cached_tles.py`）
- GeoNames 城市数据
- Natural Earth 陆地多边形

GeoNames 和 Natural Earth 的运行时源数据可能缓存到 `dataset/source_data/` 下，但该目录不被追踪，且运行生成器前不要求其必须存在。用于规范复现的 CelesTrak TLE 快照追踪在 `generator/cached_tles.py` 中。

`splits.yaml` 携带规范 `test` 划分的 benchmark 自有生成参数，包括任务时间、卫星池过滤、子系统模板和任务采样控制。保留的操作标志 `--download-dir`、`--output-dir` 和 `--force-download` 仅影响源数据的暂存位置或刷新行为，不是替代的规范数据集契约。

## 测试与 Fixtures

验证器由以下聚焦的 fixture 驱动测试锁定：

- `tests/fixtures/aeossp_standard/`
- `tests/benchmarks/test_aeossp_standard_verifier.py`

这些 fixtures 覆盖：

- 精确的有效评分
- 零完成语义
- 重复观测无额外加分语义
- 传感器不匹配
- 可见性失效
- 重叠失效
- 机动间隙失效
- 电池失效

## 谱系

`aeossp_standard` 参考了标准 AEOSSP 公式和此前的 benchmark 工作（如 AEOS-Bench），但它不是任何单一遗留 benchmark 或仿真器栈的复现。
