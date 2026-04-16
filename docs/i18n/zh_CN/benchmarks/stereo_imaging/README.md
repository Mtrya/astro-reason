# Stereo Imaging Benchmark

## 问题

规划光学卫星观测，以在一组地面目标上获取同轨立体或三立体成像影像。

本 benchmark 关注物理上有意义的观测几何和再指向代价。它不建模摄影测量内部过程、云层覆盖、下行链路、存储或星上功耗。

给定一组带有冻结 TLE 的紧凑传感器和敏捷参数的真实地球观测卫星，以及一组地理参考的地面目标，太空规划智能体（space agent）必须在固定规划任务时域内生成一个定时的观测动作调度表，以最大化立体覆盖范围和质量。

## 单位约定

所有公共量使用 SI 单位或度：

| 物理量 | 单位 | 后缀 |
|---|---|---|
| 距离、半径、高度 | 米 | `_m` |
| 面积 | 平方米 | `_m2` |
| 时间、持续时间 | 秒 | `_s` |
| 速度 | 米/秒 | `_mps` |
| 加速度 | 米/秒² | `_mps2` |
| 角度 | 度 | `_deg` |
| 角速度 | 度/秒 | `_deg_per_s` |
| 角加速度 | 度/秒² | `_deg_per_s2` |
| 时间戳 | ISO 8601，带 `Z` 或显式偏移（拒绝无偏移时间戳） | — |

## 数据集结构

```text
dataset/
├── index.json              # 测试实例清单与来源
├── example_solution.json   # 用于验证器冒烟测试的最小动作集
└── cases/
    └── <split>/
        └── case_NNNN/
            ├── satellites.yaml
            ├── targets.yaml
            └── mission.yaml
```

每个测试实例自包含。验证器读取一个测试实例目录和一个解文件。

## 测试实例文件格式

### `satellites.yaml`

YAML 序列。每个条目定义一颗卫星：

```yaml
- id: str
  norad_catalog_id: int
  tle_line1: str
  tle_line2: str

  pixel_ifov_deg: float          # 单像素角 IFOV，跨轨方向
  cross_track_pixels: int        # 跨轨探测器像素数
  max_off_nadir_deg: float       # 从天底最大倾斜角；参见硬动作约束中的组合角度公式

  max_slew_velocity_deg_per_s: float
  max_slew_acceleration_deg_per_s2: float
  settling_time_s: float

  min_obs_duration_s: float
  max_obs_duration_s: float
```

验证器从角传感器模型推导条带几何：

```text
cross_track_fov_deg    = cross_track_pixels * pixel_ifov_deg
half_cross_track_fov_deg = 0.5 * cross_track_fov_deg
strip_half_width_m     ≈ slant_range_m * tan(half_cross_track_fov_deg)
```

### `targets.yaml`

YAML 序列。每个条目定义一个地面目标：

```yaml
- id: str
  latitude_deg: float
  longitude_deg: float
  aoi_radius_m: float       # 目标中心周围感兴趣区域的半径
  elevation_ref_m: float    # 参考地形海拔

  scene_type: urban_structured | vegetated | rugged | open
```

`scene_type` 作为规划抽象捕捉立体匹配难度和遮挡行为。硬合法性不依赖 `scene_type`；立体质量分数依赖。

`scene_type` 的译法映射为：
- `urban_structured` → 都市
- `vegetated` → 林地
- `rugged` → 山地
- `open` → 平原

### `mission.yaml`

```yaml
mission:
  horizon_start: ISO8601
  horizon_end: ISO8601

  allow_cross_satellite_stereo: false
  allow_cross_date_stereo: false

  validity_thresholds:
    min_overlap_fraction: 0.80
    min_convergence_deg: 5.0
    max_convergence_deg: 45.0
    max_pixel_scale_ratio: 1.5
    min_solar_elevation_deg: 10.0
    near_nadir_anchor_max_off_nadir_deg: 10.0

  quality_model:
    pair_weights:
      geometry: 0.50
      overlap: 0.35
      resolution: 0.15
    tri_stereo_bonus_by_scene:
      urban_structured: 0.12
      rugged: 0.10
      vegetated: 0.08
      open: 0.05
```

## 解格式

太空规划智能体提交一个 JSON 文件，其中包含单测试实例对象：

**单测试实例：**
```json
{
  "actions": [
    {
      "type": "observation",
      "satellite_id": "sat_pleiades_1a",
      "target_id": "urban_paris_01",
      "start_time": "2026-06-18T10:00:00Z",
      "end_time": "2026-06-18T10:00:08Z",
      "off_nadir_along_deg": 5.0,
      "off_nadir_across_deg": -2.0
    }
  ]
}
```

每个动作指定卫星、目标、时间窗口以及卫星本体坐标系中的光轴转向角。验证器忽略 `type` 值不为 `"observation"` 的动作。

## 硬动作约束

如果以下任何一条成立，验证器将拒绝该解为非法：

- `end_time` 不严格晚于 `start_time`
- 观测窗口落在任务时域之外
- 观测持续时间在 `[min_obs_duration_s, max_obs_duration_s]` 之外
- 组合光轴侧摆角超过 `max_off_nadir_deg`，其中角度（单位：度）为 $\arctan\sqrt{\tan^2\alpha + \tan^2\beta}$，$\alpha$ = `off_nadir_along_deg`，$\beta$ = `off_nadir_across_deg`（正切使用弧度）。这与验证器用这些转向角形成光轴射线时采用的几何倾斜相同。
- 光轴射线未与地球表面相交
- 同一卫星上的两次观测在时间上重叠
- 同一卫星上连续观测之间的机动加稳定时间不足
- 引用了未知的 `satellite_id` 或 `target_id`
- 观测未完全包含在目标的连续可见区间内（这也间接强制执行了太阳高度角和侧摆角限制）
- 观测中点时刻目标中心的太阳高度角低于 `min_solar_elevation_deg`

## 验证器输出

验证器返回一个 JSON 报告：

```json
{
  "valid": true,
  "metrics": {
    "valid": true,
    "coverage_ratio": 0.0,
    "normalized_quality": 0.0
  },
  "violations": [],
  "derived_observations": [...],
  "diagnostics": {
    "pair_evaluations": [...],
    "per_target_best_score": {...}
  }
}
```

**`valid`**：所有硬约束满足。

**`coverage_ratio`**：至少有一个有效立体或三立体成像产物的目标比例。

**`normalized_quality`**：所有目标上最佳每目标立体质量分数的平均值。

**`derived_observations`**：验证器计算的每动作几何，包括卫星 ECEF 状态、光轴角、太阳角、太阳方位角、斜距、有效像素尺度比和 `access_interval_id`。

**`diagnostics`**：包含 `pair_evaluations`（每个有效产物的详细信息，包括交会角、B/H 代理、重叠率、像素尺度比、平分线高度和不对称性）和 `per_target_best_score`。

## 立体产物定义

### 有效立体对

当以下所有条件满足时，两个观测 `(i, j)` 形成一个有效立体对：

1. 相同的 `target_id`、`satellite_id` 和 `access_interval_id`
2. AOI 重叠率 `>= min_overlap_fraction`（默认 0.80）
3. 交会角 `min_convergence_deg <= gamma <= max_convergence_deg`（默认 5–45 度）
4. 像素尺度比 `max(s_i, s_j) / min(s_i, s_j) <= max_pixel_scale_ratio`（默认 1.5）
5. 所有动作级硬约束满足

### 有效三立体成像集

当以下条件满足时，三个观测形成一个有效三立体成像集：

1. 三个观测共享相同的 `target_id`、`satellite_id` 和 `access_interval_id`
2. 公共 AOI 重叠率 `>= min_overlap_fraction`
3. 三个组成对中至少有两个是有效立体对
4. 一个观测满足 `boresight_off_nadir_deg <= near_nadir_anchor_max_off_nadir_deg`（近天底锚点）

## 质量模型

### 对质量

对于有效立体对：

```
Q_pair = 0.50 * Q_geom + 0.35 * Q_overlap + 0.15 * Q_res
```

其中：

```
Q_overlap = min(1, overlap_fraction / 0.95)
Q_res     = max(0, 1 - (pixel_scale_ratio - 1) / 0.5)
```

`Q_geom` 取决于场景类型偏好的交会带：

| `scene_type` | 偏好带 |
|---|---|
| `urban_structured` | 8–18 deg |
| `vegetated` | 8–14 deg |
| `rugged` | 10–20 deg |
| `open` | 15–25 deg |

在带内和带边缘 `Q_geom = 1.0`，带外线性降至 `0.0`。这些是规划启发式，不是通用的摄影测量真理声明。

### 三立体成像质量

```
Q_tri = min(1, max(valid_pair_qualities) + beta(scene_type) * R)
```

`R` 是一个有界的冗余与锚点奖励。`beta` 值从 `mission.yaml` 的 `tri_stereo_bonus_by_scene` 中读取。

### 每目标分数

每个目标的分数是覆盖该目标的所有有效立体和三立体成像产物中的最大质量。

## 主要排序

解首先按合法性排序，然后按覆盖范围，再按质量排序：

1. `valid = true`
2. 最大化 `coverage_ratio`
3. 最大化 `normalized_quality`

## 观测几何模型

验证器使用冻结 TLE 的 SGP4 风格传播器传播卫星。

**可见区间**：指目标中心处于 `max_off_nadir_deg` 范围内、且目标处太阳高度角不低于 `min_solar_elevation_deg` 时的最大连续时间窗口。当两个观测落在同一连续可见窗口内时，它们共享相同的 `access_interval_id`。

**有效像素尺度**：

```
effective_pixel_scale_m ≈ slant_range_m * pixel_ifov_deg * (pi / 180)
```

应用了离轴投影的局部正割修正。

**成像足迹**：建模为局部切平面近似中的推扫条带。每样本处的条带半宽为 `slant_range_m * tan(radians(half_cross_track_fov_deg))`。

**重叠**：通过在圆形 AOI 内进行蒙特卡洛采样估计。

## 有意排除在范围外的内容

- 云层和天气建模
- 下行链路、地面站、接触窗口
- 星上存储和功耗预算
- 跨卫星立体（默认禁用）
- 跨日期立体（默认禁用）
- 密集图像匹配内部过程
- 光束法平差
- 精细地形遮挡或坡度物理

## 运行工具

### 验证器

```bash
uv run python -m benchmarks.stereo_imaging.verifier.run \
    benchmarks/stereo_imaging/dataset/cases/test/case_0001 \
    path/to/solution.json

# 紧凑输出（仅 valid 标志、指标、违规项）：
uv run python -m benchmarks.stereo_imaging.verifier.run \
    benchmarks/stereo_imaging/dataset/cases/test/case_0001 \
    path/to/solution.json \
    --compact
```

验证器在合法时退出码为 `0`，非法时为 `1`。

### 生成器

```bash
# 从提交的子集契约重新生成规范数据集。
uv run python -m benchmarks.stereo_imaging.generator.run \
    benchmarks/stereo_imaging/splits.yaml

# 将数据集写入另一个目录。
uv run python -m benchmarks.stereo_imaging.generator.run \
    benchmarks/stereo_imaging/splits.yaml \
    --output-dir /tmp/stereo_imaging_dataset

# 仅获取和缓存运行时源（操作模式；跳过数据集输出）：
uv run python -m benchmarks.stereo_imaging.generator.run \
    benchmarks/stereo_imaging/splits.yaml \
    --sources-only

# 即使已缓存也强制从 Kaggle 重新下载世界城市数据：
uv run python -m benchmarks.stereo_imaging.generator.run \
    benchmarks/stereo_imaging/splits.yaml \
    --force-download
```

规范生成器将测试实例写入 `dataset/cases/test/` 下，更新 `dataset/index.json`，并写入 `dataset/example_solution.json`（与 `splits.yaml` 中的 `example_smoke_case: test/case_0001` 对齐）。运行时源暂存到 `dataset/source_data/` 下。

`splits.yaml` 携带 benchmark 自有的构建参数以及 vendored 真实 TLE 子集的确切支持 CelesTrak 快照 epoch 标签。规范任务时域锚定到该缓存快照，生成器会拒绝任何其他 epoch，因为本 benchmark 不提供替代的缓存 TLE 快照。

`--sources-only`、`--download-dir` 和 `--force-download` 是源暂存周围保留的操作模式；它们不是替代的规范数据集构建契约。

### 可视化器

```bash
# 测试实例概览（星下轨迹与目标散点图）：
uv run python -m benchmarks.stereo_imaging.visualizer.run overview \
    benchmarks/stereo_imaging/dataset/cases/test/case_0001

# 解中所有立体候选的批量 ECEF 几何图：
uv run python -m benchmarks.stereo_imaging.visualizer.run batch \
    benchmarks/stereo_imaging/dataset/cases/test/case_0001 \
    path/to/solution.json
```

默认输出到 `benchmarks/stereo_imaging/visualizer/plots/<case_id>/`。

### 测试

```bash
uv run pytest tests/benchmarks/test_stereo_imaging_verifier.py tests/benchmarks/test_stereo_imaging_generator.py
```
