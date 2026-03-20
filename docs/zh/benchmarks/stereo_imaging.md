# Stereo Imaging Benchmark（立体成像基准）

## 问题描述

规划卫星观测以获取用于三维地形重建的立体图像对。智能体必须安排从不同视角（方位角分离）观测目标，以满足立体几何约束。

## 数据格式

参考 `datasets/case_0001/` 的结构：

- `satellites.yaml` - 包含 TLE 数据的卫星定义
- `targets.yaml` - 需要立体成像的目标位置
- `stations.yaml` - 用于下行链路的地面站位置
- `requirements.yaml` - 立体几何要求（最小/最大方位角分离）
- `manifest.json` - 包含时间范围规划的案例元数据

## 评估指标

- `stereo_coverage` - 具有有效立体对的目标比例
- `num_stereo_targets` - 具有立体覆盖的目标数量
- `target_coverage` - 整体观测需求覆盖率

## 约束

- 立体几何约束：目标需要从不同方位角拍摄
- 最小/最大方位角分离要求
- 卫星资源约束（电源、存储、转动速率）

## 基线方法

- `baselines/greedy.py` - 贪心启发式基线
- `baselines/simulated_annealing.py` - 模拟退火基线
