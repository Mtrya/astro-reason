# Regional Coverage Benchmark（区域覆盖基准）

## 问题描述

规划卫星观测以最大化指定地理区域的覆盖面积。智能体必须安排条带观测（连续地面轨迹）以重叠条带覆盖多边形区域。

## 数据格式

参考 `datasets/case_0001/` 的结构：

- `satellites.yaml` - 包含 TLE 数据和条带宽度的卫星定义
- `targets.yaml` - 目标位置（如适用）
- `stations.yaml` - 地面站位置
- `requirements.yaml` - 多边形区域和覆盖要求
- `manifest.json` - 包含时间范围规划的案例元数据

## 评估指标

- `coverage_percentage` - 每个多边形区域被观测覆盖的比例
- `mean_coverage_ratio` - 所有区域的平均覆盖率

## 约束

- 多边形区域几何约束
- 卫星条带宽度限制
- 观测重叠要求
- 卫星资源约束

## 基线方法

- `baselines/greedy.py` - 贪心启发式基线
- `baselines/simulated_annealing.py` - 模拟退火基线
