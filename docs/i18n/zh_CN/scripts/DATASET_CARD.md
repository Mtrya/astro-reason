---
license: mit
language:
  - en
tags:
  - aerospace
  - satellite-scheduling
  - operations-research
  - constraint-optimization
  - astrodynamics
  - benchmark
---

# AstroReason-Bench 数据集

这是 **AstroReason-Bench** 的规范 Hugging Face 数据集仓库，一个用于评估 AI 代理和算法在航天任务设计与规划问题上的 benchmark 套件。

每个 benchmark 在此数据集中作为一个独立的 **config**（子集）暴露。config 内的划分（split）透明映射到 benchmark 自身的数据集划分（例如 `test`、`single_orbit`、`multi_orbit`）。

## 数据集摘要

| Config | 案例数 | 划分 | 领域 |
|---|---|---|---|
| `aeossp_standard` | 5 | `test` | 敏捷地球观测卫星调度 |
| `regional_coverage` | 5 | `test` | 类 SAR 区域条带观测规划 |
| `relay_constellation` | 5 | `test` | 中继卫星星座增强 |
| `revisit_constellation` | 5 | `test` | 星座设计以实现均匀目标重访 |
| `satnet` | 5 | `test` | 深空网络（DSN）天线调度 |
| `spot5` | 21 | `single_orbit`, `multi_orbit`, `test` | SPOT-5 每日拍摄调度（DCKP） |
| `stereo_imaging` | 5 | `test` | 光学立体/三立体成像规划 |

## 数据集结构

每个 config 中的每个示例遵循相同的 schema：

```json
{
  "case_id": "case_0001",
  "split": "test",
  "benchmark": "aeossp_standard",
  "index_metadata": { ... 来自 index.json 的案例特定元数据 ... },
  "files": [
    {"path": "mission.yaml", "content": "..."},
    {"path": "satellites.yaml", "content": "..."},
    {"path": "tasks.yaml", "content": "..."}
  ]
}
```

- **`case_id`**: 该案例在 benchmark 内的唯一标识符。
- **`split`**: 该案例所属的数据集划分。
- **`benchmark`**: benchmark 名称。
- **`index_metadata`**: benchmark 的 `dataset/index.json` 中的案例级条目（例如卫星数量、任务数量、时域、阈值、来源）。
- **`files`**: 案例目录内所有文本文件的列表。每个条目包含一个 `path`（相对于案例目录）和完整的 UTF-8 `content`。

> **注意**：由于不同案例包含不同的文件名，`files` 被存储为统一的对象列表，而不是带有动态键的字典。这确保了跨划分的一致特征。

## 快速开始

### 加载单个 benchmark

```python
from datasets import load_dataset

# 加载 aeossp_standard benchmark
ds = load_dataset("AstroReason-Bench/datasets", "aeossp_standard")
print(ds["test"][0]["case_id"])
```

### 加载特定案例的文件

```python
case = ds["test"][0]
for file in case["files"]:
    print(file["path"])
    # file["content"] 包含文件的完整文本
```

### 遍历所有 configs

```python
from datasets import get_dataset_config_names

configs = get_dataset_config_names("AstroReason-Bench/datasets")
for config in configs:
    ds = load_dataset("AstroReason-Bench/datasets", config)
    for split_name, split_ds in ds.items():
        print(f"{config}/{split_name}: {len(split_ds)} cases")
```

## Benchmark 描述

### `aeossp_standard`
一个面向规划的敏捷地球观测卫星调度 benchmark。每个案例提供由冻结 TLE 定义的固定真实卫星星座、带时间窗口的点成像任务，以及观测几何、电池状态和机动可行性的硬约束。求解器提交一个 `observation` 动作调度表。指标包括完成率（`CR`）、加权完成率（`WCR`）、平均延迟（`TAT`）和功耗（`PC`）。

**案例文件**: `mission.yaml`, `satellites.yaml`, `tasks.yaml`

### `regional_coverage`
一个类 SAR 区域成像 benchmark。求解器必须规划对多边形感兴趣区域的条带观测，以最大化唯一加权覆盖率。案例包含带冻结 TLE 的真实卫星、GeoJSON 区域定义和 benchmark 自有的细网格评分模型。硬约束包括纯滚动条带几何、同一卫星再指向限制、电池可行性以及可选的每区域最小覆盖阈值。

**案例文件**: `manifest.json`, `satellites.yaml`, `regions.geojson`, `coverage_grid.json`

### `relay_constellation`
一个面向中继服务增强的部分星座设计 benchmark。给定不可变的 MEO 中继骨干网和地面端点，求解器添加有限数量的低轨道中继卫星并调度地面链路和星间链路动作。验证器对服务比例、延迟分位数和新增卫星数量进行评分。

**案例文件**: `manifest.json`, `network.json`, `demands.json`

### `revisit_constellation`
一个聚焦于重访性能的星座设计与调度 benchmark。求解器设计一个卫星星座（初始 GCRF 笛卡尔状态，最多到案例上限）并调度 `observation` 动作，以在 48 小时时域内尽可能缩小目标重访间隔。评分由 `mean_revisit_gap_hours`、`max_revisit_gap_hours` 和 `satellite_count` 驱动。

**案例文件**: `assets.json`, `mission.json`

### `satnet`
一个源于 NASA/JPL 深空网络（DSN）操作的强化学习 benchmark。任务是在一周窗口内为行星际航天器调度地面站天线轨道，遵守预计算的可见周期、设置/拆卸时间、维护窗口和非重叠约束。主要指标是总调度通信时长。

**案例文件**: `problem.json`, `maintenance.csv`, `metadata.json`

### `spot5`
一个基于 ROADEF 2003 挑战赛和 CNES SPOT-5 操作的约束优化 benchmark。案例以 DCKP（析取约束背包问题）格式编码。求解器选择照片并分配相机，以在满足二元/三元析取约束和星载存储容量约束（多轨道实例）的同时最大化总利润。

**案例文件**: `<case_id>.spot`

### `stereo_imaging`
一个光学卫星立体成像 benchmark。求解器调度来自真实卫星的定时观测，以获取地面目标的同轨立体或三立体产物。验证器对 `coverage_ratio`（具有有效立体产物的目标比例）和 `normalized_quality`（基于交会角、重叠和像素比例的最佳每目标质量平均值）进行评分。

**案例文件**: `satellites.yaml`, `targets.yaml`, `mission.yaml`

## 数据划分与划分策略

- `aeossp_standard`、`regional_coverage`、`relay_constellation`、`revisit_constellation`、`satnet`、`stereo_imaging`：当前暴露单个提交划分 `test`。
- `spot5`：暴露三个划分：
  - `single_orbit`：14 个无存储约束的案例。
  - `multi_orbit`：7 个存储容量为 200 的案例。
  - `test`：以种子 42 抽取的 5 案例样本（与 `single_orbit` 和 `multi_orbit` 有重叠）。

未来的 benchmark 发布可能会透明地添加额外划分（例如 `train`、`val`），而不会改变 schema。

## 数据集创建

所有规范数据集都由 AstroReason-Bench 仓库生成或整理。在有生成器的地方，它们是确定性的，并与提交的 `splits.yaml` 契约绑定。规范案例被提交到仓库中，是评估的事实来源。

## 源数据

| Config | 主要来源 |
|---|---|
| `aeossp_standard` | CelesTrak TLE 快照；GeoNames 城市；Natural Earth 陆地多边形 |
| `regional_coverage` | CelesTrak TLE 快照；GeoNames；Natural Earth |
| `relay_constellation` | 带有确定性种子的合成案例生成器 |
| `revisit_constellation` | Kaggle world-cities 数据集；CelesTrak TLE 快照 |
| `satnet` | 源于 NASA/JPL 深空网络运筹学研究（Chien 等，2021） |
| `spot5` | Mendeley Data DCKP 抽象（Wei & Hao，2021），来自 CNES SPOT-5 ROADEF 2003 实例 |
| `stereo_imaging` | Kaggle world-cities；CelesTrak TLE 快照 |

## 使用数据的注意事项

- **算法无关**：benchmark 定义问题和验证方式，不偏好特定的求解策略。
- **独立运行**：每个 config 自包含，不依赖其他 config 的运行时。
- **不包含解决方案**：本数据集仅包含问题实例（案例）。解决方案、基线和排行榜属于下游仓库。
- **跳过二进制文件**：上传脚本仅摄取基于文本的案例文件。任何未来的二进制产物将被排除在此 HF 发布之外。

## 许可信息

本数据集仓库聚合了多个具有不同来源的来源：

- **`spot5`**：`.spot` 实例来自 Mendeley Data 发布（DOI: 10.17632/2kbzg9nw3b.1），采用 **CC BY 4.0** 许可。
- **`satnet`**：源于 NASA/JPL 深空网络运筹学研究。用于研究和教育目的。
- **所有其他 benchmark**（`aeossp_standard`、`regional_coverage`、`relay_constellation`、`revisit_constellation`、`stereo_imaging`）：由 AstroReason-Bench 项目创建的原创 benchmark 材料。

使用单个 benchmark 时，请引用适当的参考文献（见引用信息）。

## 引用信息

如果您在研究中使用了本数据集套件，请引用 AstroReason-Bench 论文和原始 benchmark 来源：

### AstroReason-Bench（套件）
```bibtex
@article{wang2026astroreason,
  title={AstroReason-Bench: Evaluating Unified Agentic Planning across Heterogeneous Space Planning Problems},
  author={Wang, Weiyi and Chen, Xinchi and Gong, Jingjing and Huang, Xuanjing and Qiu, Xipeng},
  journal={arXiv preprint arXiv:2601.11354},
  year={2026}
}
```

### SatNet
```bibtex
@inproceedings{goh2021satnet,
  title={SatNet: A benchmark for satellite scheduling optimization},
  author={Goh, Edwin and Venkataram, Hamsa Shwetha and Balaji, Bharathan and Wilson, Brian D and Johnston, Mark D},
  booktitle={AAAI-22 workshop on Machine Learning for Operations Research (ML4OR)},
  year={2021}
}
```

### SPOT-5 / DCKP
```bibtex
@article{wei2023responsive,
  title={Responsive strategic oscillation for solving the disjunctively constrained knapsack problem},
  author={Wei, Zequn and Hao, Jin-Kao and Ren, Jintong and Glover, Fred},
  journal={European Journal of Operational Research},
  volume={309},
  number={3},
  pages={993--1009},
  year={2023},
  publisher={Elsevier}
}
```

## 联系方式与链接

- **仓库**: https://github.com/Mtrya/astro-reason
- **Issue Tracker**: https://github.com/Mtrya/astro-reason/issues
