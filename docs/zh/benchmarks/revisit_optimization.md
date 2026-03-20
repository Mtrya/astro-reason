# Revisit Optimization Benchmark（重访优化基准）

## 问题描述

优化卫星观测调度以最小化监测目标的最大重访间隔。智能体必须安排重复观测以保持覆盖频率，同时满足卫星资源约束（电源、存储、转动速率）。

## 数据格式

参考 `datasets/case_0001/` 的结构：

- `satellites.yaml` - 包含 TLE 数据的卫星定义
- `targets.yaml` - 监测和测绘目标位置
- `stations.yaml` - 用于下行链路的地面站位置
- `requirements.yaml` - 目标观测要求
- `manifest.json` - 包含时间范围规划的案例元数据

## 评估指标

- `target_coverage` - 所需观测完成的比例
- `max_gap_hours` - 每个目标连续观测之间的最大间隔
- `avg_gap_hours` - 连续观测之间的平均间隔

## 约束

- 目标重访频率要求
- 卫星资源约束
- 观测几何约束
- 下行链路约束

## 基线方法

- `baselines/greedy.py` - 贪心启发式基线
- `baselines/simulated_annealing.py` - 模拟退火基线
