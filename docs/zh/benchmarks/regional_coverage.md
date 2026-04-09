# Regional Coverage Benchmark（区域覆盖基准）

## 问题概述

`regional_coverage` 是一个区域条带成像规划基准。

智能体接收：

- 固定规划时间范围
- 带冻结 TLE 的真实卫星
- 一组 GeoJSON 多边形区域
- 每颗卫星的传感器、机动与电源参数

目标是在满足硬约束的前提下，提交一组定时 `strip_observation`
动作，最大化区域的**唯一覆盖率**。

该基准保留电源约束，但**不建模**存储、下传、地面站、云层与昼夜门控。

## 数据集结构

```text
dataset/
├── index.json
├── example_solution.json
└── cases/
    └── case_0001/
        ├── manifest.json
        ├── satellites.yaml
        ├── regions.geojson
        └── coverage_grid.json
```

## 核心文件

- `manifest.json`：时间范围、采样步长、评分参数
- `satellites.yaml`：TLE、传感器视场、机动约束、电源模型
- `regions.geojson`：公开的人类可读区域定义
- `coverage_grid.json`：基准拥有的细粒度加权覆盖网格

## 解格式

提交内容是一个单一 JSON 对象：

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

## 主要约束

- 时间必须对齐到 `time_step_s`
- `duration_s` 必须满足卫星最小/最大条带时长
- `roll_deg` 与 `cross_track_fov_deg` 推导出的内外边缘离轴角必须落在允许区间
- 同一卫星动作不能重叠
- 同一卫星连续动作之间必须满足 `slew + settling` 时间
- 电池电量不能降到零以下
- 如设置 `imaging_duty_limit_s_per_orbit`，则必须满足单轨成像占空比限制

## 评估指标

- `coverage_ratio`：按区域权重汇总后的全局唯一覆盖率
- `covered_weight_m2_equivalent`：已覆盖样本的唯一加权面积
- `total_imaging_energy_wh`
- `total_slew_angle_deg`
- `num_actions`

## 运行方式

验证器：

```bash
uv run python benchmarks/regional_coverage/verifier.py \
  benchmarks/regional_coverage/dataset/cases/case_0001 \
  benchmarks/regional_coverage/dataset/example_solution.json
```

生成器：

```bash
uv run python -m benchmarks.regional_coverage.generator.run
```

可视化器：

```bash
uv run python -m benchmarks.regional_coverage.visualizer.run overview \
  benchmarks/regional_coverage/dataset/cases/case_0001
```

更完整的公开契约、文件格式、评分与物理抽象，请参见
[`benchmarks/regional_coverage/README.md`](/home/betelgeuse/Developments/AstroReason-Bench/benchmarks/regional_coverage/README.md)。
