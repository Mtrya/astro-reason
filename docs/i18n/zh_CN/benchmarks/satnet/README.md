# SatNet：行星际卫星调度 Benchmark

一个用于**深空网络（DSN）调度问题**的强化学习 benchmark。该挑战涉及将地面站天线时间最优分配给整个太阳系的航天器进行通信，同时遵守严格的物理与操作约束。

## 问题概述

深空网络是 NASA/JPL 的国际巨型无线电天线阵列，支持行星际航天器任务。调度问题要求在 1 周周期内最大化成功通信轨道的总时长，同时遵守：

- **可见周期（VP）约束**：只有当卫星与地面站有视线时才能通信（由轨道力学决定）
- **设置/拆卸要求**：每次轨道需要校准时间
- **非重叠约束**：天线不能同时处理多个传输
- **维护计划**：天线有计划停机时间用于维修和升级

这映射为一个具有由天体力学导出的物理约束的复杂约束调度问题。

## 历史背景与来源

| 年份 | 事件 |
|------|------|
| 1963 | NASA 建立深空网络 |
| 2000s | 为 DSN 操作开发自动调度系统 |
| 2021 | Chien 等人在 IEEE 航空航天会议上发表卫星调度 RL 基线 |
| 2021 | 发布源于 DSN 操作的 SatNet benchmark 数据集 |

**数据许可**：数据集源于 NASA/JPL 运筹学和学术论文。用于研究与教育目的。

**可用周次**：2018 年的 5 周（W10、W20、W30、W40、W50），共 1,452 个请求

## 问题建模

### 决策变量

对于每个通信请求，决定：
- **是否**调度（可能部分满足或未满足）
- **使用哪个**天线（来自请求的兼容天线）
- **何时**调度（在有效可见周期内）
- **分配多长时间**（在 `duration_min` 和 `duration` 之间）

### 约束

1. **可见周期约束**：每个轨道必须完全包含在一个可见周期内
   ```
   ∀ 轨道: ∃ VP ∈ request.resource_vp_dict[轨道.antenna]:
       VP.trx_on ≤ 轨道.tracking_on ∧ 轨道.tracking_off ≤ VP.trx_off
   ```

2. **无重叠约束**：同一天线上的轨道不能重叠
   ```
   ∀ 轨道_i, 轨道_j on same antenna (i ≠ j):
       轨道_i.end_time ≤ 轨道_j.start_time ∨ 轨道_j.end_time ≤ 轨道_i.start_time
   ```

3. **设置/拆卸约束**：时间一致性
   ```
   轨道.start_time + request.setup_time × 60 = 轨道.tracking_on
   轨道.tracking_off + request.teardown_time × 60 = 轨道.end_time
   ```

4. **维护约束**：不能与天线停机重叠
   ```
   ∀ 轨道, maintenance on same antenna:
       轨道.end_time ≤ maintenance.start ∨ maintenance.end ≤ 轨道.start_time
   ```

5. **最小持续时间约束**：每个轨道必须满足最小持续时间
   ```
   (轨道.tracking_off - 轨道.tracking_on) / 3600 ≥ request.duration_min
   ```

### 目标

最大化总通信时长：
```
maximize: Σ (轨道.tracking_off - 轨道.tracking_on) / 3600
```

## 数据格式规范

### 问题实例格式（`cases/<CASE_ID>/problem.json`）

每个规范 SatNet 案例存储在 `benchmarks/satnet/dataset/cases/test/` 下的独立目录中。验证器对划分无感知，直接接受案例目录路径。案例目录中的 `problem.json` 文件包含恰好一周/一年对的请求 JSON 数组：

```json
[
  {
    "subject": 521,
    "user": "521_0",
    "week": 10,
    "year": 2018,
    "duration": 1.0,
    "duration_min": 1.0,
    "resources": [["DSS-34"], ["DSS-36"]],
    "track_id": "fc9bbb54-3-1",
    "setup_time": 60,
    "teardown_time": 15,
    "time_window_start": 1520286007,
    "time_window_end": 1520471551,
    "resource_vp_dict": {
      "DSS-34": [
        {
          "RISE": 1520286007,
          "SET": 1520318699,
          "TRX ON": 1520286007,
          "TRX OFF": 1520318699
        }
      ],
      "DSS-36": []
    }
  }
]
```

**字段定义：**

- **subject**：任务 ID（例如 521 = Voyager）
- **track_id**：唯一请求标识符（UUID）
- **duration**：请求的通信时间（小时）
- **duration_min**：可接受的最短持续时间（小时）
- **setup_time**：发射前校准（分钟）
- **teardown_time**：发射后清理（分钟）
- **time_window_start/end**：请求有效窗口（Unix 时间戳）
- **resource_vp_dict**：将天线 ID 映射到可见周期数组
  - **TRX ON/OFF**：传输窗口边界（Unix 时间戳）
  - **RISE/SET**：卫星升起/落下时间（Unix 时间戳）

**特殊情况 - 组阵（Arraying）**：某些请求可以同时使用多根天线（例如 `"DSS-34_DSS-35"`）。这可以改善遥远航天器的信号强度。

### 解决方案格式（JSON）

一个已调度轨道的数组：

```json
[
  {
    "RESOURCE": "DSS-34",
    "SC": "521",
    "START_TIME": 1520286007,
    "TRACKING_ON": 1520289607,
    "TRACKING_OFF": 1520293207,
    "END_TIME": 1520294107,
    "TRACK_ID": "fc9bbb54-3-1"
  }
]
```

**字段定义：**

- **RESOURCE**：天线 ID
- **SC**：航天器/任务 ID（验证器会解析该字段，但不会与请求的 `subject` 进行校验）
- **START_TIME**：包含设置的轨道开始时间（Unix 时间戳）
- **TRACKING_ON**：实际传输开始（Unix 时间戳）
- **TRACKING_OFF**：实际传输结束（Unix 时间戳）
- **END_TIME**：包含拆卸的轨道结束时间（Unix 时间戳）
- **TRACK_ID**：必须与请求的 `track_id` 匹配

**时间关系：**
```
START_TIME --[setup_time]--> TRACKING_ON --[actual_comms]--> TRACKING_OFF --[teardown_time]--> END_TIME
```

### 维护计划格式（`cases/<CASE_ID>/maintenance.csv`）

每个案例目录还包含一个过滤到同一周/年实例的维护 CSV：

```csv
week,year,starttime,endtime,antenna
10.0,2018,1520286000,1520300000,DSS-14
```

**字段定义：**

- **week/year**：ISO 周数和年份
- **starttime/endtime**：维护窗口（Unix 时间戳）
- **antenna**：天线 ID（例如 "DSS-14"）

## 验证规则

验证器（`verifier.py`）检查：

### 1. 可见周期验证
每个轨道的 `[TRACKING_ON, TRACKING_OFF]` 区间必须完全包含在该天线-请求对的至少一个可见周期内。

### 2. 重叠检测
同一天线上的任意两个轨道不能存在重叠的 `[START_TIME, END_TIME]` 区间（包括设置/拆卸）。

### 3. 设置/拆卸验证
- `TRACKING_ON = START_TIME + setup_time × 60`
- `END_TIME = TRACKING_OFF + teardown_time × 60`

### 4. 维护违规检查
任意轨道的 `[START_TIME, END_TIME]` 不能与同一天线上的任何维护窗口重叠。

### 5. 最小持续时间检查
- `(TRACKING_OFF - TRACKING_ON) / 3600 ≥ duration_min`
- **特殊上限**：对于 `duration ≥ 8` 小时的请求，验证器会静默地将单轨最小持续时间上限设为 **4 小时**（`per_track_min_sec = min(req_min_sec, 14400)`）。这意味着单个轨道对长请求只需提供 4 小时的实际传输时间，而非完整的 `duration_min`。

### 6. 请求存在性
每个 `TRACK_ID` 必须对应问题实例中的一个有效请求。

### 7. 天线可用性
`RESOURCE` 必须在请求的 `resource_vp_dict` 中。

## 评分方法

**主要指标**：总通信小时数
```python
score = sum((track['TRACKING_OFF'] - track['TRACKING_ON']) / 3600.0 for track in solution)
```

**注意**：设置和拆卸时间消耗天线可用性，但**不计入**分数。

**次要指标**（也由验证器计算并报告）：

- **满足请求数**：总分配时长（同一 `track_id` 的所有轨道之和）至少达到 `duration_min` 的请求数量
- **公平性（U_max）**：所有请求中的最大未满足比例
  ```
  U_i = (requested_duration - allocated_duration) / requested_duration
  U_max = max(U_i for all requests)
  ```
- **公平性（U_rms）**：未满足比例的均方根
  ```
  U_rms = sqrt(mean(U_i² for all requests))
  ```

## 实例分类

### 数据集统计

| 周次 | 请求数 | 总请求时长 | 唯一任务数 |
|------|----------|----------------------|-----------------|
| W10_2018 | 257 | 1191.5h | 30 |
| W20_2018 | 294 | 1406.5h | 33 |
| W30_2018 | 293 | 1464.0h | 32 |
| W40_2018 | 333 | 1736.7h | 34 |
| W50_2018 | 275 | 1292.2h | 29 |

**复杂度因素：**
- **可见周期碎片化**：某些卫星有很多短 VP，而另一些则很少但很长
- **组阵需求**：多天线请求更难调度
- **设置/拆卸开销**：高开销降低了有效天线利用率
- **维护密度**：更多停机时间增加了调度难度

## 验证器使用

### 命令行

```bash
uv run python benchmarks/satnet/verifier.py \
    benchmarks/satnet/dataset/cases/test/W10_2018 \
    solution.json \
    --verbose
```

**输出（verbose）：**
```
Status: VALID
Score: 234.5678 hours
Tracks: 145
Satisfied Requests: 132
U_rms: 0.32
U_max: 0.65
```

**输出（compact）：**
```
VALID: score=234.5678h, tracks=145
```

## 基线性能

来自原始 RL 实现（Chien 等人，2021）：

| 方法 | 平均分配时长 | 平均满足请求数 | U_rms | U_max |
|--------|--------------------|-----------------------|-------|-------|
| Random | ~180h | ~120 | 0.45 | 0.85 |
| Greedy | ~210h | ~140 | 0.38 | 0.72 |
| PPO (RL) | ~235h | ~155 | 0.32 | 0.65 |

**注意**：精确数字取决于具体周次和随机种子。

## 文件位置

- **案例清单**：`benchmarks/satnet/dataset/index.json`
- **规范案例**：`benchmarks/satnet/dataset/cases/test/W##_YYYY/`
- **共享元数据**：`benchmarks/satnet/dataset/mission_color_map.json`
- **验证器**：`benchmarks/satnet/verifier.py`
- **生成器**：`uv run python benchmarks/satnet/generator.py benchmarks/satnet/splits.yaml`
- **测试 fixtures**：`tests/fixtures/satnet_mock_solutions/`

## 关键技术概念

### 可见周期（VPs）

可见周期是卫星与地面站有视线的时间段。它们基于以下因素预计算：
- **轨道力学**：卫星星历（随时间变化的位置/速度）
- **地面站位置**：纬度、经度、海拔
- **仰角**：地平线上最小角度（通常为 10–15°）
- **大气约束**：无线电频率传播限制

VPs 是**硬约束**——无论天线可用性如何，你都不能在这些窗口之外调度通信。

### 组阵（Arraying）

多根天线可以组合接收来自单一航天器的信号，从而改善：
- **信噪比**：对深空任务（Voyager、New Horizons）尤为关键
- **数据速率**：更高的组合带宽

在数据集中，组阵请求以连字符天线 ID 出现（例如 `"DSS-34_DSS-35"`）。组阵中的所有天线必须同时空闲。

### 设置与拆卸

每次传输前：
- **设置**：天线转向、接收机调谐、频率锁定获取
- **拆卸**：系统复位、日志记录、天线重新定位

这些时间是**物理上必需的**，并消耗天线可用性，但**不计入**目标分数（只有实际传输时间才算）。

## 许可与归属

**数据来源**：源于 NASA/JPL 深空网络运筹学研究

**学术参考文献：**
1. Chien, S., et al. "Reinforcement Learning for Scheduling Deep Space Network Communications." IEEE Aerospace Conference, 2021. [DOI: 10.1109/AERO50100.2021.9438519](https://ieeexplore.ieee.org/abstract/document/9438519/)
2. Chien, S., et al. "Learning Satellite Scheduling Policies using Deep Reinforcement Learning." AAAI ML4OR Workshop, 2021. [OpenReview](https://openreview.net/forum?id=buIUxK7F-Bx)

**致谢**：本 benchmark 基于 NASA JPL 和多智能体学习社区提供的开源 SatNet 实现和数据集。

## 参考文献

1. Chien S, Sherwood R, Tran D, et al. "The EO-1 autonomous science agent." Autonomous Agents and Multi-Agent Systems, 2005.
2. Rabideau G, Chien S, Galer D, Nespoli F. "Managing communications for the Deep Space Network." SpaceOps Conference, 2010.
3. Chien S, Johnston M, Policella N, et al. "A Generalized Timeline Representation for Planning and Scheduling." ICAPS, 2013.
4. Beaumet G, Verfaillie G, Charmeau MC. "Feasibility of Autonomous Decision Making on Board an Agile Earth-Observing Satellite." Computational Intelligence, 2011.
