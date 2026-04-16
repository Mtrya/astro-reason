# SPOT-5 卫星拍摄调度 Benchmark

一个源于 ROADEF 2003 挑战赛和法国航天局（CNES）运营的地球观测卫星调度经典约束优化问题。

## 问题概述

SPOT-5 卫星（2002–2015 年运行）搭载三台成像仪器：两台 HRG（高分辨率几何）相机和一台 HRS（高分辨率立体）相机。每日调度问题要求在满足以下约束的同时选择照片以最大化总利润：

- **相机约束**：单幅图像使用一台相机（HRG 前、中或后）；立体图像需要同时使用两台 HRG 相机
- **非重叠约束**：由于镜面机动时间限制，照片不能冲突
- **数据流约束**：瞬时遥测带宽限制禁止某些组合
- **存储约束**：星载记录容量限制所选图像总数（仅多轨道实例）

这映射为一个具有复杂逻辑约束的析取约束背包问题（DCKP）。

## 历史背景与来源

| 年份 | 事件 |
|------|------|
| 2002 | CNES 发射 SPOT-5 卫星 |
| 2003 | ROADEF 2003 挑战赛发布原始遥测数据（多文件格式，含轨道参数） |
| 2001–2003 | Vasquez 与 Hao 将物理约束抽象为冲突图（VCSP 公式） |
| 2021 | Wei 与 Hao 进一步简化并在 Mendeley Data 上以 DCKP 格式发布了 21 个 benchmark 实例 |

当前数据集（`.spot` 文件）是托管在 [Mendeley Data](https://data.mendeley.com/datasets/2kbzg9nw3b/1) 上的 DCKP 抽象，采用 **CC BY 4.0** 许可。该许可是宽松的，因为抽象过程创建了一个与 CNES 专有原始遥测数据相分离的派生数据集。

在本仓库中，每个发布的实例都作为独立的 benchmark 案例存储：

```text
benchmarks/spot5/dataset/cases/<split>/<case_id>/<case_id>.spot
```

## 实例文件格式（.spot）

### 整体结构

```
<总变量数>
<变量规格行...>
<总约束数>
<约束规格行...>
[<容量>]  # 可选，仅用于多轨道实例
```

### 变量规格

每个变量代表一个拍照请求：

```
<var_id> <利润> <域大小> {<value_id> <recorder_consumption>}* <域大小> [extra_fields...]
```

- **var_id**：变量标识符（从 0 开始索引）
- **profit**：若被选中获得的权重/利润（要最大化的目标）
- **domain_size**：可能的相机分配数量（SPOT-5 始终为 3）
- **value_id**、**recorder_consumption**：定义允许值的配对
  - 值 `1`：HRG 前相机
  - 值 `2`：HRG 中相机
  - 值 `3`：HRG 后相机
  - 值 `13`：HRG 前 + 后相机
- **extra_fields**：不确定，忽略

对于 14 个单轨道实例：所有 `recorder_consumption = 0`
对于 7 个多轨道实例：`recorder_consumption` 表示内存使用量

示例：

1. 单轨道，domain_size = 3

```11.spot, 第 3 行
1 1 3 1 0 2 0 3 0
```

1 -> var_id（第二个变量）
1 -> profit（若被选中获得 1 点利润）
3 -> domain_size：3 种可能的相机分配（即 1、2、3）
1 0 -> value_id 1, recorder_consumption 0
2 0 -> value_id 2, recorder_consumption 0
3 0 -> value_id 3, recorder_consumption 0

2. 多轨道，domain_size = 3

```1504.spot, 第 40 行
38 2 3 1 451.1500000000069 2 451.1500000000069 3 451.1500000000069 213302 1
```

38 -> var_id（第 39 个变量）
2 -> profit（若被选中获得 2 点利润）
3 -> domain_size：3 种可能的相机分配（即 1、2、3）
1 451.1500000000069 -> value_id 1, recorder_consumption 451.1500000000069
2 451.1500000000069 -> value_id 2, recorder_consumption 451.1500000000069
3 451.1500000000069 -> value_id 3, recorder_consumption 451.1500000000069
213302 1 -> extra_field, 忽略

3. 多轨道，domain_size = 1

```1506.spot, 第 127 行
125 2000 1 13 1804.5999999999822 136703 1
```

125 -> var_id（第 126 个变量）
2000 -> profit（若被选中获得 2000 点利润）
1 -> domain_size：1 种可能的相机分配（即 13）
13 1804.5999999999822 -> value_id 13, recorder_consumption 1804.5999999999822
136703 1 -> extra_field, 忽略

### 约束规格

```
<arity> <var_id_1> ... <var_id_arity> {<forbidden_tuple>}*
```

- **arity**：变量数量（2 = 二元，3 = 三元）
- **var_id_***：约束涉及的变量
- **forbidden_tuple**：禁止的值组合（空格分隔）

**二元约束**编码析取冲突：两张照片不能同时被选中。禁止元组是值对（例如 `1 1 2 2 3 3` 表示“不能同时使用相机 1，或同时使用相机 2，或同时使用相机 3”）。

**三元约束**编码数据流限制或复杂的干扰模式。禁止元组是值三元组。

示例：

1. 二元

```11.spot, 第 370 行
2 242 240 13 3 13 1
```

2 -> arity（二元）
242 -> var_id_1
240 -> var_id_2
13 3 -> forbidden_tuple 1
13 1 -> forbidden_tuple 2

禁止将值 13 分配给变量 242 **且** 将值 3 分配给变量 240；禁止将值 13 分配给变量 242 **且** 将值 1 分配给变量 240。

2. 三元

```11.spot, 第 369 行
3 124 81 72 13 2 13
```

3 -> arity（三元）
124 -> var_id_1
81 -> var_id_2
72 -> var_id_3
13 2 13 -> forbidden_tuple 1

禁止将值 13 分配给变量 124 **且** 将值 2 分配给变量 81 **且** 将值 13 分配给变量 72。


### 容量行（仅多轨道）

对于实例 `1401, 1403, 1405, 1502, 1504, 1506, 1021`，文件以表示存储容量约束的单个数字结尾。**重要**：文件中的这个数字在验证器中被忽略。真实容量始终为 **200**。

## 解决方案文件格式（.spot_sol.txt）

```
profit = <P>, weight = <W>
number of candidate photographs = <N>
number of selected photographs = <S>
<assignment_0>
<assignment_1>
...
<assignment_n-1>
```

- **P**：总利润（所选照片的权重之和）
- **W**：总内存使用量（多轨道实例，见权重计算）
- **N**：候选照片（变量）总数
- **S**：所选照片数量（assignment ≠ 0）
- **assignments**：每个变量一个，值为 `{0, 1, 2, 3, 13}`

## 约束类型验证

当满足所有约束时，解决方案有效：

### 二元约束
对于每个带禁止元组 `F` 的二元约束 `C(i, j)`：
- 若 `assignment[i] ≠ 0` **且** `assignment[j] ≠ 0`：配对 `(assignment[i], assignment[j])` **不得** 在 `F` 中
- 若任一为 0：约束满足

### 三元约束
对于每个带禁止元组 `F` 的三元约束 `C(i, j, k)`：
- 若三个 assignment 均 ≠ 0：三元组 **不得** 在 `F` 中
- 若任一为 0：约束满足

### 存储容量约束（仅多轨道）
```
total_weight ≤ 200
```

其中 `total_weight` 按下面的权重计算得出。

## 分数计算

### 利润
```python
profit = sum(variables[i].profit for i in range(n) if assignment[i] != 0)
```

### 权重（内存使用）

**单轨道实例**（8, 54, 404, 408, 412, 5, 11, 28, 29, 42, 503, 505, 507, 509）：
- 所有内存消耗均为 0
- `weight = 0`

**多轨道实例**（1401, 1403, 1405, 1502, 1504, 1506, 1021）：

对于每个有域值的变量，原始 `recorder_consumption` 值必须归一化：
```python
# 来自 1021.spot 行的示例：
# 0 1000 1 2 451.1500000000069 42510 1
# 值 1 的 recorder_consumption = 451.1500000000069

# 构建一个将每个 value_id 映射到其归一化权重的字典
weight_per_value = {
    value_id: round(recorder_consumption / 451)
    for value_id, recorder_consumption in variable.domain_items
}

total_weight = sum(
    weight_per_value[assignment[i]]
    for i in range(n) if assignment[i] != 0
)
```

约束：`total_weight ≤ 200`

## 实例分类

### 总计：21 个实例

| 类别 | 实例 | 变量数 | 约束数 | 容量 |
|----------|-----------|-----------|-------------|----------|
| 小型（单轨道） | 8, 54, 404, 408, 412 | 8–78 | 7–52 | 0 |
| 中型（单轨道） | 5, 11, 28, 29, 42 | 306–309 | 4308–6273 | 0 |
| 大型（单轨道） | 503, 505, 507, 509 | 315 | 3983–8122 | 0 |
| 多轨道 | 1401, 1403, 1405, 1502, 1504, 1506 | 163–855 | 可变 | 200 |
| 多轨道（最大） | 1021 | 1,057 | 20,730 | 200 |

**14 个实例无存储约束**（capacity = 0）
**7 个实例有存储约束**（capacity = 200）

## 已提交划分

已完成 benchmark 在 `benchmarks/spot5/splits.yaml` 中保留了三个提交划分：

- `single_orbit`：所有数字 ID `< 1000` 的已发布实例
- `multi_orbit`：所有数字 ID `> 1000` 的已发布实例
- `test`：以种子 `42` 抽取的 5 个案例重叠样本

重叠是故意的。例如，案例 `8` 同时出现在 `single_orbit` 和 `test` 中。数据集级冒烟示例与 `single_orbit/8` 配对。

## 已知解决方案与验证

参考解决方案位于 `tests/fixtures/spot5_val_sol/` 中，来自 [DCKP_RSOA 仓库](https://github.com/Zequn-Wei/DCKP_RSOA)。

验证结果（使用 `verifier.py`）：

- **14 个解决方案**：声称利润/权重与计算利润/权重完全匹配
- **7 个解决方案**：分配有效，但报告头部值存在微小差异

**头部不匹配**（分配本身正确）：

| 实例 | 声称利润 | 计算利润 | 差异 | 权重状态 |
|----------|----------------|-----------------|------|---------------|
| 11       | 22,117         | 22,119          | +2   | ✓ (0) |
| 408      | 3,078          | 3,080           | +2   | ✓ (0) |
| 509      | 19,115         | 19,117          | +2   | ✓ (0) |
| 1403     | 172,141        | 172,143         | +2   | ✓ (0) |
| 1506     | 164,239        | 164,241         | +2   | ✓ (0) |
| 1021     | 169,240        | 169,243         | +3   | 声称 200, 实际 198 |
| 1405     | 170,175        | 170,179         | +4   | 声称 200, 实际 198 |

验证器将这些案例视为**有效解决方案**；差异似乎出现在 DCKP-RSOA 算法的利润/权重报告逻辑中，而非解决方案质量本身。

## 验证器使用

```bash
# 验证 .spot_sol.txt 解决方案
uv run python benchmarks/spot5/verifier.py \
    benchmarks/spot5/dataset/cases/single_orbit/8 \
    tests/fixtures/spot5_val_sol/8.spot_sol.txt

# 验证 JSON 解决方案（与 example_solution.json 使用相同 schema）
uv run python benchmarks/spot5/verifier.py \
    benchmarks/spot5/dataset/cases/single_orbit/8 \
    benchmarks/spot5/dataset/example_solution.json
```

验证器检查：
1. 所有 assignment 都在有效域内
2. 所有二元约束满足
3. 所有三元约束满足
4. 存储容量约束满足（如适用）
5. 利润计算匹配
6. 权重计算匹配
7. 选中数量与头部匹配

## 文件位置

- **案例目录**：`benchmarks/spot5/dataset/cases/<split>/<case_id>/`
- **实例文件**：`benchmarks/spot5/dataset/cases/<split>/<case_id>/<case_id>.spot`
- **数据集清单**：`benchmarks/spot5/dataset/index.json`
- **解决方案文件**：`tests/fixtures/spot5_val_sol/*.spot_sol.txt`
- **验证器**：`benchmarks/spot5/verifier.py`
- **生成器**：`uv run python benchmarks/spot5/generator.py benchmarks/spot5/splits.yaml`

## 许可与归属

**数据许可**：CC BY 4.0（知识共享署名 4.0 国际）
**来源**：Mendeley Data，DOI: 10.17632/2kbzg9nw3b.1
**归属**：
- 原始问题：CNES（法国航天局）与 ONERA
- 问题抽象：Vasquez & Hao（2001），Wei & Hao（2021）
- 参考解决方案：DCKP-RSOA 算法（Wei & Hao，2021）

**商业使用**：CC BY 4.0 允许。数据集不是病毒式许可的；与使用 GPL 的解决方案程序不同，Mendeley Data 发布是宽松的。

## 参考文献

1. Bensana E, Lemaitre M, Verfaillie G. "Earth observation satellite management." Constraints, 1999.
2. Verfaillie G, Lemaitre M, Schiex T. "Russian Doll Search for Solving Constraint Optimization Problems." AAAI-96, 1996.
3. Agnès J-C, Bataille N, Blumstein D, et al. "Exact and Approximate Methods for the Daily Management of an Earth Observation Satellite." ESA Workshop 1995.
4. Vasquez M, Hao JK. "A Logic-Constrained Knapsack Formulation and a Tabu Search Algorithm for the Daily Photograph Scheduling of an Earth Observation Satellite." 2001.
5. Wei Z, Hao JK. "A Threshold Search Based Memetic Algorithm for the Disjunctively Constrained Knapsack Problem." Applied Soft Computing, 2021.
