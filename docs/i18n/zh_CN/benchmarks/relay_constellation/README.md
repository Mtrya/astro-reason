# Relay Constellation Benchmark

## 状态

本 benchmark 已实现，是仓库中标准的已完成中继网络增强 benchmark。

它替代了此前的 `latency_optimization` benchmark 故事线。

## 问题摘要

`relay_constellation` 是一个面向中继服务的部分星座设计 benchmark。

对于每个案例，space agent 接收：

- 固定的 96 小时规划时域
- 以笛卡尔初始状态表达的不可变 MEO 中继骨干网
- 固定的地面通信端点
- 端点对之间的通信需求窗口
- 案例特定的轨道与通信约束

Space agent 必须返回：

- 一组有数量上限的额外中继卫星
- 激活通信链路的时间受限接触计划

本 benchmark 聚焦于增强，而非从零设计。现有骨干卫星不可变。预期的增强故事是 LEO 优先：求解器添加低轨道中继以改善服务并降低相对于给定 MEO 基线的延迟。

不在范围内：

- 感知或成像
- 星上功耗或存储建模
- 姿态或天线转向动力学
- 排队与缓冲
- 随机链路中断
- 求解器撰写的路由声明

## 数据集布局

规范数据集位于：

```text
dataset/
├── example_solution.json
├── index.json
└── cases/
    └── <split>/
        └── <case_id>/
            ├── manifest.json
            ├── network.json
            └── demands.json
```

`dataset/example_solution.json` 是一个与普通提交 schema 相同的真实解决方案对象。`dataset/index.json` 记录案例元数据以及通过划分相对路径 `example_smoke_case` 配对的冒烟案例，提交的划分构建契约位于 `benchmarks/relay_constellation/splits.yaml`。

## 案例输入

每个案例目录恰好包含三个机器可读文件。

### `manifest.json`

`manifest.json` 定义规划时域、传播模型、路由步长和硬案例约束。

重要字段：

- `case_id`
- `epoch`
- `horizon_start`
- `horizon_end`
- `routing_step_s`
- `constraints`
  - `max_added_satellites`
  - `min_altitude_m`
  - `max_altitude_m`
  - `max_eccentricity`
  - `min_inclination_deg`
  - `max_inclination_deg`
  - `max_isl_range_m`
  - `max_links_per_satellite`
  - `max_links_per_endpoint`
  - 可选的 `max_ground_range_m`

### `network.json`

`network.json` 包含不可变的中继骨干网和地面端点。

- `backbone_satellites[]`
  - `satellite_id`
  - `x_m`
  - `y_m`
  - `z_m`
  - `vx_m_s`
  - `vy_m_s`
  - `vz_m_s`
- `ground_endpoints[]`
  - `endpoint_id`
  - `latitude_deg`
  - `longitude_deg`
  - `altitude_m`
  - `min_elevation_deg`

所有卫星状态都被解释为案例 epoch 时刻的 GCRF 笛卡尔状态。

### `demands.json`

`demands.json` 包含所需的通信窗口。

- `demanded_windows[]`
  - `demand_id`
  - `source_endpoint_id`
  - `destination_endpoint_id`
  - `start_time`
  - `end_time`
  - `weight`

每条记录描述一个端点对的所需窗口。

## 解决方案契约

有效提交是一个 JSON 对象，包含两个顶层数组：

- `added_satellites`
- `actions`

### `added_satellites`

每颗新增卫星使用与骨干网相同的笛卡尔状态约定：

- `satellite_id`
- `x_m`
- `y_m`
- `z_m`
- `vx_m_s`
- `vy_m_s`
- `vz_m_s`

验证器在内部推导轨道属性，并拒绝违反案例约束的添加状态。

### `actions`

求解器仅提交基于区间的链路激活。支持的动作类型有：

- `ground_link`
- `inter_satellite_link`

共享字段：

- `action_type`
- `start_time`
- `end_time`

`ground_link` 还需要：

- `endpoint_id`
- `satellite_id`

`inter_satellite_link` 还需要：

- `satellite_id_1`
- `satellite_id_2`

求解器不提交端到端路由、延迟声明或需求服务声明。

## 有效性规则

如果任何硬约束被违反，验证器将拒绝该解决方案，包括：

- 案例或解决方案结构格式错误
- 新增卫星 ID 重复或冲突
- 新增卫星数量超过案例允许上限
- 新增轨道超出边界或不受约束
- 引用了未知的端点或卫星
- 不支持的动作类型
- 零时长、偏离网格或超出时域的动作
- 同一物理链路上的动作重叠
- 几何上不可行的地面链路
- 几何上不可行的星间链路
- 违反 `max_links_per_satellite` 的每样本限制
- 违反 `max_links_per_endpoint` 的每样本限制

中间地面端点在路由服务中不是合法的转接节点。只有需求的源端点和目的端点可以作为所选路由中的地面端点出现。

## 路由、服务与延迟

在需求窗口内的每个验证器自有采样时刻，如果存在一条从源到目的地的物理可行多跳路径，通过骨干网加求解器添加的卫星，仅使用当前激活的调度链路，则该需求被服务。

验证器拥有路由和分配：

- 它从验证后的动作构建活跃通信图
- 它在单位容量边使用下进行路由分配
- 它以确定性方式选择路由

样本内的排序意图：

1. 最大化被服务需求的总权重
2. 最小化被服务需求的总延迟
3. 以确定性方式打破剩余平局

延迟仅针对被服务的需求样本计算：

```text
latency_ms = 1000 * total_path_length_m / c
```

未服务的时间会降低服务比例，但不贡献合成或无限延迟。

## 指标与排序

验证器报告：

- `service_fraction`
- `worst_demand_service_fraction`
- `mean_latency_ms`
- `latency_p95_ms`
- `num_added_satellites`
- `num_demanded_windows`
- `num_backbone_satellites`
- `per_demand`
  - `requested_sample_count`
  - `served_sample_count`
  - `service_fraction`
  - `mean_latency_ms`
  - `latency_p95_ms`

预期排序优先级：

1. 有效解决方案优于无效解决方案
2. 最大化 `service_fraction`
3. 最大化 `worst_demand_service_fraction`
4. 最小化 `latency_p95_ms`
5. 最小化 `mean_latency_ms`
6. 最小化 `num_added_satellites`

## 传播与链路模型

验证器使用一个固定的天体力学工具栈：

- `brahe.NumericalOrbitPropagator`
- 仅 J2 引力
- GCRF 用于惯性状态
- ITRF/ECEF 用于几何检查
- 零值静态 EOP 提供器，用于确定性离线验证

链路可行性：

- 地面链路：
  - 端点仰角高于 `min_elevation_deg`
  - 通过 `max_ground_range_m` 的可选斜距限制
- 星间链路：
  - 欧几里得距离在 `max_isl_range_m` 内
  - 视线不被地球遮挡

验证器将几何与拓扑分离：

- 首先验证动作几何并存储每样本边距离
- 然后构建时序图并从这些验证后的边中评分服务和延迟

## 公共入口点

生成器：

```bash
uv run python -m benchmarks.relay_constellation.generator.run \
  benchmarks/relay_constellation/splits.yaml
```

可选的数据集输出覆盖：

```bash
uv run python -m benchmarks.relay_constellation.generator.run \
  benchmarks/relay_constellation/splits.yaml \
  --output-dir /tmp/relay_constellation_dataset
```

验证器：

```bash
uv run python -m benchmarks.relay_constellation.verifier.run \
  benchmarks/relay_constellation/dataset/cases/test/case_0005 \
  benchmarks/relay_constellation/dataset/example_solution.json
```

可视化器：

```bash
uv run python -m benchmarks.relay_constellation.visualizer.run overview \
  --case-dir benchmarks/relay_constellation/dataset/cases/test/case_0001
```

```bash
uv run python -m benchmarks.relay_constellation.visualizer.run connectivity \
  --case-dir benchmarks/relay_constellation/dataset/cases/test/case_0001
```

```bash
uv run python -m benchmarks.relay_constellation.visualizer.run solution \
  --case-dir benchmarks/relay_constellation/dataset/cases/test/case_0005 \
  --solution-path benchmarks/relay_constellation/dataset/example_solution.json
```

## 测试

运行聚焦的中继 benchmark 测试：

```bash
uv run pytest tests/benchmarks/test_relay_constellation_generator.py tests/benchmarks/test_relay_constellation_verifier.py
```
