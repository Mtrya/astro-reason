# AEOSbench Benchmark（敏捷卫星星座调度基准）

## 问题描述

使用 Basilisk 仿真进行敏捷地球观测卫星星座调度，分配任务以最大化完成率。

## 数据格式

- `dataset/` - 包含问题实例数据
- `verifier/run.py` - 验证和评分逻辑

## 评估指标

- `completion_rate` - 任务完成率
- 使用 Basilisk 进行轨道和姿态仿真

## 约束

- 卫星星座资源约束
- 观测几何约束
- 数据下传约束
- 仿真物理保真度

## 基线方法

使用 Basilisk 仿真器进行任务规划和调度评估。
