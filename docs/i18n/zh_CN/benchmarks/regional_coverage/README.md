# Regional Coverage Benchmark

## 问题

规划对多边形感兴趣区域的条带观测，以在固定规划任务时域内最大化区域的唯一覆盖率。

本 benchmark 建模了一个紧凑的类 SAR 区域成像问题：

- 真实卫星，带有冻结 TLE
- 由验证器计算的条带几何，由定时的仅滚转（roll-only）动作推导
- 同一卫星的再指向限制
- 带光照区充电的电池可行性
- benchmark 自有的细网格覆盖评分

本 benchmark 故意**不**对存储、下行链路、地面站、云层或详细 SAR 处理进行建模。

## 单位约定

所有公共量使用 SI 单位或度：

| 物理量 | 单位 | 后缀 |
|---|---|---|
| 距离、高度 | 米 | `_m` |
| 面积 | 平方米 | `_m2` |
| 时间、持续时间 | 秒 | `_s` |
| 角度 | 度 | `_deg` |
| 角速度 | 度/秒 | `_deg_per_s` |
| 角加速度 | 度/秒² | `_deg_per_s2` |
| 能量 | 瓦时 | `_wh` |
| 功率 | 瓦 | `_w` |
| 时间戳 | ISO 8601，带 `Z` 或显式偏移 | — |

## 数据集结构

```text
dataset/
├── index.json
├── example_solution.json
└── cases/
    └── <split>/
        └── case_0001/
            ├── manifest.json
            ├── satellites.yaml
            ├── regions.geojson
            └── coverage_grid.json
```

当前规范发布包含 5 个测试实例。每个测试实例自包含。验证器读取一个测试实例目录和一个每测试实例解文件。

数据集级 `example_solution.json` 是一个最小可运行示例：

```json
{
  "actions": []
}
```

`dataset/index.json` 包含子集相对路径 `example_smoke_case`，当前指向 `test/case_0001`。benchmark 自有的构建契约位于 `benchmarks/regional_coverage/splits.yaml`。

## 规范测试实例族

生成器当前输出：

- 5 个规范测试实例
- 72 小时任务时域
- 每测试实例 6 至 12 颗卫星
- 当前发布中每测试实例 2 至 3 个区域
- 每测试实例 1 或 2 种卫星类别
- 每测试实例约 5,000 至 20,000 个加权覆盖采样点

当前公共测试实例使用温和的双类别族：

- `sar_narrow`
- `sar_wide`

这些是 benchmark 抽象，不代表 benchmark 复现了某个特定飞行项目。

## 测试实例文件格式

### `manifest.json`

测试实例级元数据和验证器配置：

```json
{
  "case_id": "case_0001",
  "benchmark": "regional_coverage",
  "spec_version": "v1",
  "seed": 20270415,
  "horizon_start": "2025-07-17T00:00:00Z",
  "horizon_end": "2025-07-20T00:00:00Z",
  "time_step_s": 10,
  "coverage_sample_step_s": 5,
  "earth_model": {
    "shape": "wgs84"
  },
  "grid_parameters": {
    "sample_spacing_m": 5000.0
  },
  "scoring": {
    "primary_metric": "coverage_ratio",
    "revisit_bonus_alpha": 0.0,
    "max_actions_total": 64
  }
}
```

`time_step_s` 是公共动作网格。`coverage_sample_step_s` 是验证器用于条带几何和当前功耗积分网格的采样步长。

### `satellites.yaml`

YAML 序列。每个卫星条目定义：

```yaml
- satellite_id: sat_iceye-x2
  tle_line1: str
  tle_line2: str
  tle_epoch: ISO8601

  sensor:
    min_edge_off_nadir_deg: float
    max_edge_off_nadir_deg: float
    cross_track_fov_deg: float
    min_strip_duration_s: float
    max_strip_duration_s: float

  agility:
    max_roll_rate_deg_per_s: float
    max_roll_acceleration_deg_per_s2: float
    settling_time_s: float

  power:
    battery_capacity_wh: float
    initial_battery_wh: float
    idle_power_w: float
    imaging_power_w: float
    slew_power_w: float
    sunlit_charge_power_w: float
    imaging_duty_limit_s_per_orbit: float | null
```

验证器使用：

- TLE + Brahe SGP4 传播
- GCRF 作为惯性坐标系
- ITRF 作为地固坐标系
- WGS84 用于地球交点和大地坐标转换

### `regions.geojson`

RFC 7946 GeoJSON 格式的人类可读区域定义。

**注意：** 验证器仅读取每个 Polygon 的第一个线性环（`coordinates[0]`）。内环（孔洞）当前被忽略。

每个要素包含：

```json
{
  "type": "Feature",
  "properties": {
    "region_id": "region_001",
    "weight": 1.0,
    "min_required_coverage_ratio": 0.25
  },
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[lon, lat], ...]]
  }
}
```

`min_required_coverage_ratio` 是可选的。

### `coverage_grid.json`

benchmark 拥有的机器可读评分支持数据。

当前规范模式为加权采样点：

```json
{
  "grid_version": 1,
  "sample_spacing_m": 5000.0,
  "regions": [
    {
      "region_id": "region_001",
      "total_weight_m2": 123456789.0,
      "samples": [
        {
          "sample_id": "region_001_s000001",
          "longitude_deg": 90.0,
          "latitude_deg": 1.0,
          "weight_m2": 25000000.0
        }
      ]
    }
  ]
}
```

每个采样点恰好属于一个区域，默认情况下只贡献一次唯一覆盖权重。

## 解格式

公共解是一个单一 JSON 对象：

```json
{
  "actions": [
    {
      "type": "strip_observation",
      "satellite_id": "sat_iceye-x2",
      "start_time": "2025-07-17T03:31:00Z",
      "duration_s": 20,
      "roll_deg": 20.0
    }
  ]
}
```

公开定义的动作类型仅有一种：`"strip_observation"`。

验证器会忽略未知的动作类型，但 benchmark 用户应只提交 `strip_observation` 动作。

解不得包含：

- 用户手写的条带多边形
- 用户手写的条带中心线
- 用户手写的覆盖声明
- 预计算的可见窗口标识符

## 条带与姿态模型

本 benchmark 使用通用角条带传感器和仅滚转指向模型。

对于一个动作：

- `roll_deg` 是带中心侧摆角的有符号角度
- `cross_track_fov_deg` 是完整的跨轨角视场

定义：

```text
r = abs(roll_deg)
f = cross_track_fov_deg
theta_inner_deg = r - 0.5 * f
theta_outer_deg = r + 0.5 * f
```

动作仅当以下条件满足时才是传感器有效的：

```text
theta_inner_deg >= min_edge_off_nadir_deg
theta_outer_deg <= max_edge_off_nadir_deg
```

验证器在这些边界附近应用 `1e-6` 度的数值容差。

验证器通过以下步骤推导条带几何：在整个动作区间内传播卫星位置，将中心射线、内边缘射线和外边缘射线与 WGS84 椭球相交，再将这些边缘命中点沿时间扫成条带段。

因此，地面宽度由轨道几何和姿态推导而来。benchmark 不使用固定的存储条带宽度。

## 硬有效性规则

如果以下任何一条成立，验证器将拒绝该解为非法：

- `satellite_id` 未知
- `start_time` 超出测试实例任务时域
- `duration_s <= 0`
- `duration_s` 不是 `time_step_s` 的整数倍
- `start_time` 未对齐到 `time_step_s` 网格
- `duration_s` 超出卫星传感器边界
- `theta_inner_deg` 或 `theta_outer_deg` 违反传感器侧摆带限制
- 条带射线未能与地球相交
- 同一卫星的两个条带观测在时间上重叠
- 同一卫星的间隙小于所需姿态机动时间加稳定时间
- 电池状态降至零以下
- 存在时违反 `imaging_duty_limit_s_per_orbit`
- 存在时未满足区域级 `min_required_coverage_ratio`

本 benchmark **不**暴露公共预计算可见窗口。条带可访问性由验证器确定。

## 机动模型

同一卫星的再指向使用仓库的加速-滑行-减速（bang-coast-bang）/ 梯形最小机动时间模型。

对于同一卫星的两个连续动作：

```text
d = abs(current.roll_deg - previous.roll_deg)
omega = max_roll_rate_deg_per_s
alpha = max_roll_acceleration_deg_per_s2
d_tri = omega^2 / alpha

if d <= d_tri:
    t_slew = 2 * sqrt(d / alpha)
else:
    t_slew = d / omega + omega / alpha

t_required_gap = t_slew + settling_time_s
```

本 benchmark 的机动测量基于指令滚转增量，而非被动地面轨迹漂移。

## 功耗模型

本 benchmark 对每颗卫星使用单一荷电状态电池，采用二元光照区/地影区充电和分段恒定负载。

发电：

- 光照区时为 `sunlit_charge_power_w`
- 地影区时为 `0`

负载：

- 持续 `idle_power_w`
- 成像时加上 `imaging_power_w`
- 所需再指向窗口期间加上 `slew_power_w`

当前实现规则：

- 在验证器自有的 5 秒固定步长网格上进行确定性积分（规范测试实例使用）
- 光照区状态在区间中点评估

离散更新：

```text
E_next = E_curr + (P_charge_w - P_load_w) * delta_t_s / 3600
```

能量上限被截断至 `E_max`，但负值**不会**被钳位到零。如果电池状态在任何时刻变为负值，则解非法。

## 覆盖评分

覆盖在 `coverage_grid.json` 中的 benchmark 自有细网格上评分，而非在精确多边形并集上。

对于每个权重为 `w_i`、覆盖次数为 `c_i` 的采样点 `i`：

```text
u_i = 1 if c_i >= 1 else 0
```

每区域覆盖：

```text
coverage_ratio_r = sum_i(w_i * u_i) / sum_i(w_i)
```

全局覆盖：

```text
coverage_ratio =
    sum_r(region_weight_r * coverage_ratio_r) / sum_r(region_weight_r)
```

默认重访行为：

- 首次覆盖获得全额积分
- 重复覆盖不获得额外积分
- `revisit_bonus_alpha` 存在于 schema 中，但在规范发布中值为 `0.0`

## 验证器输出

验证器返回具有以下顶层结构的 JSON 报告：

```json
{
  "valid": true,
  "metrics": {
    "coverage_ratio": 0.0,
    "covered_weight_m2_equivalent": 0.0,
    "num_actions": 0,
    "total_imaging_time_s": 0.0,
    "total_imaging_energy_wh": 0.0,
    "total_slew_angle_deg": 0.0,
    "min_battery_wh": 0.0,
    "region_coverages": {}
  },
  "violations": [],
  "diagnostics": {}
}
```

重要指标字段：

- `coverage_ratio`
- `covered_weight_m2_equivalent`
- `num_actions` — 统计每个解析出的 `strip_observation` 动作（包括因调度违规而被拒绝的动作）
- `total_imaging_time_s` — 仅对被接受进调度的动作持续时间求和
- `total_imaging_energy_wh`
- `total_slew_angle_deg`
- `min_battery_wh`
- `region_coverages`

主要排序优先级为：

1. `valid = true`
2. 最大化 `coverage_ratio`
3. 最大化 `covered_weight_m2_equivalent`
4. 最小化 `total_imaging_energy_wh`
5. 最小化 `total_slew_angle_deg`
6. 最小化 `num_actions`

## 有意排除在范围外的内容

- 存储
- 下行链路与地面站
- 云层覆盖与昼光门控
- 辐射测量与 SAR 图像生成
- 热子模型
- 反作用轮角动量卸载
- 求解器侧可见窗口

## 运行工具

### 验证器

```bash
uv run python benchmarks/regional_coverage/verifier.py \
    benchmarks/regional_coverage/dataset/cases/test/case_0001 \
    benchmarks/regional_coverage/dataset/example_solution.json
```

验证器在合法时退出码为 `0`，非法时为 `1`。

### 生成器

```bash
# 从提交的划分契约原地重建规范数据集。
uv run python -m benchmarks.regional_coverage.generator.run \
    benchmarks/regional_coverage/splits.yaml

# 将数据集写入另一个目录。
uv run python -m benchmarks.regional_coverage.generator.run \
    benchmarks/regional_coverage/splits.yaml \
    --output-dir /tmp/regional_coverage_dataset
```

提交的 `splits.yaml` 包含一个精确支持的 CelesTrak 快照 epoch 标签，用于 vendored 的真实 TLE 子集。生成器会拒绝任何其他 epoch，因为本 benchmark 不提供替代的缓存 TLE 快照。

运行规范生成器会重写 `benchmarks/regional_coverage/dataset/`，包括：

- `dataset/cases/test/`
- `dataset/index.json`
- `dataset/example_solution.json`

### 可视化器

可视化器用于 benchmark 检查和 fixture 编写。

```bash
# 2D 测试实例概览 PNG。
uv run python -m benchmarks.regional_coverage.visualizer.run overview \
    benchmarks/regional_coverage/dataset/cases/test/case_0001

# 解检查包，包含 3D 条带几何 HTML 和区域级 PNG。
uv run python -m benchmarks.regional_coverage.visualizer.run inspect \
    benchmarks/regional_coverage/dataset/cases/test/case_0001 \
    path/to/solution.json
```

生成的可视化产物写入 `benchmarks/regional_coverage/visualizer/plots/`。
