# SGP4 Skyfield Fixture

## 目的

本 fixture 为以下内容提供 benchmark 无关的、确定性的真实基准：

- 基于 TLE 的轨道状态传播
- 卫星对地可见窗口
- 卫星间可见窗口
- 卫星光照区与地影窗口

该 fixture 有意仅限于轨道传播、可见性和光照区判定。电池曲线、存储曲线和机动动力学被排除在外。这些量是 benchmark 局部的，不应在此冻结。

## 目录布局

```text
tests/fixtures/sgp4_skyfield/
├── README.md          (本文件)
├── generate.py        (fixture 生成器)
├── case_0001/
│   ├── satellites.yaml
│   ├── targets.yaml
│   ├── orbital_states.json
│   ├── visibility_windows.json
│   └── illumination_windows.json
├── case_0002/
│   └── ...
├── case_0003/
│   └── ...
└── case_0004/
    └── ...
```

两个 YAML 文件是手写的输入。三个 JSON 文件由 `generate.py` 生成。每个 JSON 文件自带 `metadata` 块，而不是共享的 manifest 文件。

## 规范规则

### 时间戳

生成的 JSON 文件中的所有时间戳：

- UTC
- ISO 8601 字符串
- 以 `Z` 结尾
- 秒级精度

示例：`2025-07-17T12:00:00Z`

### 区间

所有窗口使用：

- `start_utc` 包含
- `end_utc` 不包含

此规则适用于所有窗口类型：卫星对目标、卫星对卫星、光照区和地影。

### 配对排序

对于卫星间可见性，每个无序对只存储一个方向：

- 字典序上 `satellite_id < other_satellite_id`
- 当 `(A, B)` 已存在时，从不存储 `(B, A)`

### 可空性

仅当字段显式可选且故意缺失时才使用 JSON `null`。不要省略必填字段。

### 数值单位

所有带单位的字段都在字段名中携带单位：

- 位置：`m`
- 速度：`m_per_s`
- 角度：`deg`
- 持续时间：`sec`
- 海拔（星下点）：`m`

---

## 文件模式

### `satellites.yaml`

顶层 YAML 列表。每个条目恰好包含这些字段：

| 字段 | 类型 | 描述 |
|-------|------|-------------|
| `id` | string | 稳定的唯一标识符 |
| `tle_line1` | string | TLE 第 1 行 |
| `tle_line2` | string | TLE 第 2 行 |

---

### `targets.yaml`

顶层 YAML 列表。每个条目恰好包含这些字段：

| 字段 | 类型 | 描述 |
|-------|------|-------------|
| `id` | string | 文件内的唯一标识符 |
| `latitude_deg` | number | WGS-84 纬度，单位：度 |
| `longitude_deg` | number | WGS-84 经度，单位：度 |
| `altitude_m` | number | WGS-84 椭球上方海拔，单位：米 |
| `min_elevation_deg` | number | 可见性最小仰角，单位：度 |
| `max_slant_range_m` | number or null | 最大斜距，单位：米；`null` 表示无限制 |

---

### `orbital_states.json`

JSON 对象，恰好包含这些顶层键：`metadata`、`timestamps_utc`、`offsets_sec`、`satellites`。

#### `metadata`

| 字段 | 类型 | 值 / 备注 |
|-------|------|---------------|
| `case_id` | string | 例如 `case_0001` |
| `generator` | string | `tests/fixtures/sgp4_skyfield/generate.py` |
| `generator_library` | string | `skyfield` |
| `generator_library_version` | string | 已安装包的版本字符串 |
| `time_system` | string | `UTC` |
| `state_frame` | string | `GCRS` |
| `position_unit` | string | `m` |
| `velocity_unit` | string | `m_per_s` |
| `subpoint_altitude_unit` | string | `m` |
| `horizon_start_utc` | string | 带 `Z` 的 ISO 8601 UTC |
| `horizon_end_utc` | string | 带 `Z` 的 ISO 8601 UTC |
| `sample_step_sec` | number | 样本之间的时间间隔，单位：秒 |
| `sample_count` | integer | 共享 10 分钟网格上的总样本数 |
| `timestamp_inclusion` | string | `sample timestamps are exact sample instants` |
| `satellite_ids` | array of strings | `satellites` 中出现的顺序 ID |

#### `timestamps_utc`

UTC ISO 8601 字符串数组。长度等于 `sample_count`。

#### `offsets_sec`

整数数组。长度等于 `sample_count`。第一个值为 `0`。每个值是从 `horizon_start_utc` 起经过的整秒数。

#### `satellites`

对象数组，每颗卫星一个，顺序由 `metadata.satellite_ids` 给出。每个对象：

| 字段 | 类型 | 描述 |
|-------|------|-------------|
| `id` | string | 卫星 ID |
| `position_gcrs_m` | array of `[x, y, z]` arrays | GCRS 位置，单位：米 |
| `velocity_gcrs_m_per_s` | array of `[vx, vy, vz]` arrays | GCRS 速度，单位：米/秒 |
| `subpoint_latitude_deg` | numeric array | 星下点大地纬度 |
| `subpoint_longitude_deg` | numeric array | 星下点大地经度 |
| `subpoint_altitude_m` | numeric array | 星下点海拔，单位：米 |
| `geocentric_distance_m` | numeric array | 距地心距离，单位：米 |

所有每卫星数组长度等于 `sample_count`。

---

### `visibility_windows.json`

JSON 对象，恰好包含这些顶层键：`metadata`、`satellite_to_target`、`satellite_to_satellite`。

#### `metadata`

| 字段 | 类型 | 值 / 备注 |
|-------|------|---------------|
| `case_id` | string | 例如 `case_0001` |
| `generator` | string | `tests/fixtures/sgp4_skyfield/generate.py` |
| `generator_library` | string | `skyfield` |
| `generator_library_version` | string | 版本字符串 |
| `time_system` | string | `UTC` |
| `angle_unit` | string | `deg` |
| `distance_unit` | string | `m` |
| `duration_unit` | string | `sec` |
| `horizon_start_utc` | string | 带 `Z` 的 ISO 8601 UTC |
| `horizon_end_utc` | string | 带 `Z` 的 ISO 8601 UTC |
| `sample_step_sec` | number | 用于采样可见性检测和边界搜索括号的步长 |
| `boundary_tolerance_sec` | number | 窗口边界细化的容差 |
| `timestamp_inclusion` | string | `start inclusive, end exclusive` |
| `ground_visibility_model` | string | `topocentric line of sight with target-defined minimum elevation and optional maximum slant range` |
| `inter_satellite_visibility_model` | string | `geometric line of sight above Earth limb` |
| `inter_satellite_constraints` | object | 见下文 |
| `target_ids` | array of strings | 本测试实例中的所有目标 ID |
| `satellite_ids` | array of strings | 本测试实例中的所有卫星 ID |
| `earth_occlusion_model` | string | `line segment clearance against spherical Earth` |
| `earth_radius_m` | number | 用于遮挡计算的地球半径，单位：米 |

##### `inter_satellite_constraints`

| 字段 | 类型 | 描述 |
|-------|------|-------------|
| `line_of_sight_required` | boolean | 是否要求几何 LOS |
| `max_range_m` | number or null | 最大卫星间距离，或 `null` |

#### `satellite_to_target`

对象数组。每个对象：

| 字段 | 类型 | 描述 |
|-------|------|-------------|
| `satellite_id` | string | 卫星标识符 |
| `target_id` | string | 目标标识符 |
| `constraints` | object | `{min_elevation_deg, max_slant_range_m}` |
| `windows` | array | 见下文窗口模式 |

每个窗口对象：

| 字段 | 类型 | 描述 |
|-------|------|-------------|
| `start_utc` | string | 窗口开始（包含） |
| `end_utc` | string | 窗口结束（不包含） |
| `duration_sec` | number | 窗口持续时间，单位：秒 |
| `time_of_max_elevation_utc` | string | 最大仰角时刻 |
| `max_elevation_deg` | number | 最大仰角，单位：度 |
| `min_slant_range_m` | number | 窗口内最小斜距，单位：米 |
| `max_slant_range_m` | number | 窗口内最大斜距，单位：米 |

#### `satellite_to_satellite`

对象数组。每个对象：

| 字段 | 类型 | 描述 |
|-------|------|-------------|
| `satellite_id` | string | 第一颗卫星（字典序较小） |
| `other_satellite_id` | string | 第二颗卫星 |
| `constraints` | object | `{line_of_sight_required, max_range_m}` |
| `windows` | array | 见下文窗口模式 |

配对排序规则：`satellite_id < other_satellite_id` 字典序。每个无序对恰好出现一次。

每个窗口对象：

| 字段 | 类型 | 描述 |
|-------|------|-------------|
| `start_utc` | string | 窗口开始（包含） |
| `end_utc` | string | 窗口结束（不包含） |
| `duration_sec` | number | 窗口持续时间，单位：秒 |
| `min_range_m` | number | 窗口内最小距离，单位：米 |
| `max_range_m` | number | 窗口内最大距离，单位：米 |

---

### `illumination_windows.json`

JSON 对象，恰好包含这些顶层键：`metadata`、`satellites`。

#### `metadata`

| 字段 | 类型 | 值 / 备注 |
|-------|------|---------------|
| `case_id` | string | 例如 `case_0001` |
| `generator` | string | `tests/fixtures/sgp4_skyfield/generate.py` |
| `generator_library` | string | `skyfield` |
| `generator_library_version` | string | 版本字符串 |
| `time_system` | string | `UTC` |
| `duration_unit` | string | `sec` |
| `distance_unit` | string | `m` |
| `illumination_source` | string | `skyfield` |
| `illumination_model` | string | `skyfield ICRF.is_sunlit with JPL de421.bsp ephemeris` |
| `horizon_start_utc` | string | 带 `Z` 的 ISO 8601 UTC |
| `horizon_end_utc` | string | 带 `Z` 的 ISO 8601 UTC |
| `sample_step_sec` | number | 用于采样光照区检测和过渡搜索括号的步长 |
| `boundary_tolerance_sec` | number | 过渡边界细化的容差 |
| `timestamp_inclusion` | string | `start inclusive, end exclusive` |
| `satellite_ids` | array of strings | 本测试实例中的所有卫星 ID |

#### `satellites`

对象数组，每颗卫星一个。每个对象：

| 字段 | 类型 | 描述 |
|-------|------|-------------|
| `satellite_id` | string | 卫星标识符 |
| `initial_state` | string | 时域起点处的 `sunlit` 或 `eclipse` |
| `final_state` | string | 时域终点处的 `sunlit` 或 `eclipse` |
| `sunlit_windows` | array | 光照区窗口 |
| `eclipse_windows` | array | 地影窗口 |
| `transitions` | array | 状态转换的有序列表 |

光照区和地影窗口对象：

| 字段 | 类型 |
|-------|------|
| `start_utc` | string |
| `end_utc` | string |
| `duration_sec` | number |

转换对象：

| 字段 | 类型 | 允许值 |
|-------|------|----------------|
| `timestamp_utc` | string | — |
| `from_state` | string | `sunlit`, `eclipse` |
| `to_state` | string | `sunlit`, `eclipse` |

不变量：
- `sunlit_windows` 和 `eclipse_windows` 一起划分完整时域
- 同一状态类内无重叠
- `transitions` 按 `timestamp_utc` 排序
- 第一个转换与 `initial_state` 一致
- 最后一个转换与 `final_state` 一致

---

## 测试实例清单

### case_0001 — 混合轨道特征

**目的：** 在一个紧凑 fixture 中覆盖明显不同的轨道体制。

**卫星：**

| ID | 轨道类别 |
|----|-------------|
| sat_skysat-a | 低海拔近圆形太阳同步轨道（SSO） |
| sat_qianfan-1 | 高海拔近极地轨道 |
| sat_yaogan-16_01a | 明显偏心中等海拔倾斜轨道 |
| sat_jilin-1_gaofen | 低倾角低轨道 |

**目标：** city_pontevedra_ph_1、city_lisbon_pt、city_punta_arenas_cl、city_same_tz、city_mositai_cn

所有目标：`min_elevation_deg: 10.0`，`max_slant_range_m: null`

**覆盖目标：** 海拔跨度、周期跨度、倾角跨度、偏心率跨度、普通卫星对地可见性、多轨道类别的光照区状态。

---

### case_0002 — 卫星对地可见性

**目的：** 演练对不同纬度地面端点（类设施和类城市）的混合可见性。

**卫星：** sat_qianfan-1、sat_skysat-a、sat_spot_1

**目标：**

| ID | min_elevation_deg |
|----|-------------------|
| facility_queensland_transmitter | 15.0 |
| facility_greenbelt_test_brt_stdn_bltj | 15.0 |
| facility_sodankyla_eiscat_radar | 15.0 |
| city_taihe_cn | 10.0 |
| city_apia_ws | 10.0 |
| city_surrey_ca | 10.0 |

所有目标：`max_slant_range_m: null`

**覆盖目标：** 混合纬度可见性、不同目标的不同仰角阈值、不同卫星轨道类别的可见性分布。

---

### case_0003 — 卫星间可见性

**目的：** 显式演练卫星对卫星可见窗口。

**卫星：** sat_qianfan-1、sat_qianfan-2、sat_qianfan-3、sat_qianfan-4、sat_qianfan-19

**目标：**

| ID | min_elevation_deg |
|----|-------------------|
| city_pontevedra_ph_1 | 10.0 |
| facility_queensland_transmitter | 15.0 |

所有目标：`max_slant_range_m: null`

**覆盖目标：** 同一壳层卫星间窗口、字典序排序的配对覆盖、卫星间约束（`line_of_sight_required: true`、`max_range_m: null`）、卫星间伴随地面目标可见性。

---

### case_0004 — 约束下的可见性与光照区边界

**目的：** 使用具有不同约束的重复物理位置演练阈值语义——仰角和斜距过滤。

**卫星：** sat_skysat-a、sat_qianfan-1、sat_yaogan-16_01a

**目标：**

| ID | 经纬度基准 | min_elevation_deg | max_slant_range_m |
|----|--------------|-------------------|-------------------|
| city_lisbon_pt_elev10 | Lisbon | 10.0 | null |
| city_lisbon_pt_elev30 | Lisbon | 30.0 | null |
| city_punta_arenas_cl_range_open | Punta Arenas | 10.0 | null |
| city_punta_arenas_cl_range_tight | Punta Arenas | 10.0 | 1500000.0 |
| facility_sodankyla_low_elev | Sodankyla | 5.0 | null |
| facility_sodankyla_high_elev | Sodankyla | 25.0 | null |

**覆盖目标：** 共享相同坐标但约束不同的配对产生明显不同的窗口集，确认约束过滤被正确应用；同一时域内的光照区与地影状态转换验证地影与光照区边界的准确性。

---

## 使用 `generate.py`

`generate.py` 是规范的 fixture 工具。从仓库根目录使用 `uv run python` 运行它。

### 生成所有测试实例

```bash
uv run python tests/fixtures/sgp4_skyfield/generate.py generate-all --overwrite
```

发现所有 `case_####` 目录，为每个测试实例生成三个 JSON 输出文件，验证它们，并打印每测试实例一行摘要。

### 生成单个测试实例

```bash
uv run python tests/fixtures/sgp4_skyfield/generate.py generate-case case_0002 --overwrite
```

### 验证所有测试实例

```bash
uv run python tests/fixtures/sgp4_skyfield/generate.py validate-all
```

检查每个测试实例的 YAML 输入和全部三个 JSON 输出文件。如有测试实例失败则退出码非零。

### 验证单个测试实例

```bash
uv run python tests/fixtures/sgp4_skyfield/generate.py validate-case case_0003
```

### 打印摘要

```bash
uv run python tests/fixtures/sgp4_skyfield/generate.py summary
```

每测试实例打印一行：卫星数量、目标数量、样本数量、卫星对目标窗口数量、卫星间窗口数量、光照/地影转换数量。

### 标志

| 标志 | 命令 | 效果 |
|------|----------|--------|
| `--root PATH` | 所有 | 使用替代的 fixture 根目录 |
| `--overwrite` | `generate-*` | 替换现有 JSON 输出 |
| `--quiet` | `generate-all` | 抑制每测试实例进度日志 |
| `--strict` | `validate-*` | 保留用于未来更严格的检查 |

### 生成参数

所有测试实例共享相同的默认时间网格：

| 参数 | 值 |
|-----------|-------|
| `horizon_start_utc` | `2025-07-17T12:00:00Z` |
| `horizon_end_utc` | `2025-07-18T12:00:00Z` |
| `sample_step_sec` | `600` |
| `sample_count` | `145` |
| `boundary_tolerance_sec` | `1` |

轨道状态使用 **Skyfield** `EarthSatellite`（GCRS 坐标系）。
可见性使用 Skyfield 地面几何（卫星对目标）和球形地球线段清障测试（卫星对卫星，半径 6371000.0 m）。
光照区判定使用 **Skyfield** `ICRF.is_sunlit()` 和 JPL `de421.bsp` 星历。fixture 生成器将该星历缓存到 `tests/fixtures/sgp4_skyfield/.skyfield-data/` 下。
