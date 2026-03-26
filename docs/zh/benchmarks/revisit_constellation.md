# Revisit Constellation Benchmark（星座重访设计与调度基准）

## 问题描述

该基准要求智能体同时完成两类决策：

1. 设计星座架构，即给出每颗卫星在任务起始时刻的初始状态
2. 规划任务动作序列，即安排观测与下行链路操作

目标是在任务时间窗内尽可能减小各目标的重访间隔，并在达到重访阈值后尽量减少所使用的卫星数量。

## 案例输入

每个规范案例目录包含两个机器可读文件：

- `assets.json`
- `mission.json`

其中：

- `assets.json` 定义共享卫星模型、最大卫星数量以及地面站集合
- `mission.json` 定义任务起止时间、目标位置和每个目标的重访要求

## 解决方案格式

求解器提交一个 `solution.json`，包含两个顶层数组：

- `satellites`
- `actions`

`satellites` 给出每颗卫星在任务起始时刻的 GCRF 笛卡尔状态。

`actions` 给出调度动作，当前支持：

- `observation`
- `downlink`

## 评估指标

对有效解，验证器报告：

- `mean_revisit_gap_hours`
- `max_revisit_gap_hours`
- `satellite_count`
- `threshold_satisfied`

若解违反硬约束，例如轨道高度限制、观测几何约束、下行链路约束、电量或存储约束，则立即判为无效。

## 数据集与工具

- 规范数据集位于 `benchmarks/revisit_constellation/dataset/`
- 验证入口位于 `benchmarks/revisit_constellation/verifier/run.py`
- 生成器入口位于 `benchmarks/revisit_constellation/generator/run.py`

生成器会自动下载公开数据源，写入 `dataset/source_data/`，并据此重建规范案例。
