# Latency Optimization Benchmark（通信延迟优化基准）

## 问题描述

设计卫星中继网络以最小化地面站之间的通信延迟。智能体必须建立星间链路（ISL）和下行链路，以创建低延迟路径，用于地理上分离的地面站之间的数据中继。

## 数据格式

参考 `datasets/case_0001/` 的结构：

- `satellites.yaml` - 包含 TLE 数据的卫星定义
- `targets.yaml` - 目标位置（如适用）
- `stations.yaml` - 地面站位置
- `requirements.yaml` - 站对和延迟要求
- `manifest.json` - 包含时间范围规划的案例元数据

## 评估指标

- `connection_coverage` - 具有连接性的请求时间窗口比例
- `latency_min/max/mean_ms` - 信号传播延迟统计
- `target_coverage` - 观测需求覆盖率（如适用）

## 约束

- 星间链路建立约束
- 卫星仰角约束
- 地面站可见性约束
- 数据传输延迟约束

## 基线方法

- `baselines/greedy.py` - 贪心启发式基线
- `baselines/simulated_annealing.py` - 模拟退火基线
