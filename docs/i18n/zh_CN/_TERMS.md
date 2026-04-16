# 中文文档术语表（zh_CN）

> 本文件为 `docs/i18n/zh_CN/` 下所有译文的术语规范。
> 首次出现的术语建议以 **中文译法（英文原词）** 的形式呈现。

---

## 通用架构术语

| 英文 | 中文译法 | 备注 |
|---|---|---|
| benchmark | benchmark | 不译，保留技术术语 |
| verifier | 验证器 | 统一使用，不交替使用“校验器/检查器” |
| generator | 数据集生成器 | 统一 |
| visualizer | 可视化工具 | 或“可视化脚本” |
| dataset | 数据集 | 统一 |
| fixture | fixture / 测试固件 | 测试领域通用，可保留英文 |
| smoke test | 冒烟测试 | 首次出现可加注（smoke test） |
| entrypoint | 入口脚本 | 指 CLI 入口 |
| split | 子集 | 数据集子集 |
| case | 测试实例 | 统一 |

## 角色与实体

| 英文 | 中文译法 | 备注 |
|---|---|---|
| space agent | 太空规划智能体 | 与 coding agent 区分 |
| solver | 求解器 | 指优化/调度求解器 |
| agent | agent | 不译 |
| satellite | 卫星 | 统一 |
| constellation | 星座 | 航天标准术语 |
| fleet | 编队 / 星群 | 根据上下文 |
| ground station | 地面站 | 统一 |
| ground endpoint | 地面端点 | relay_constellation 专用 |
| backbone satellite | 既有的卫星 | 首次出现可保留英文并加注释 |
| target | 目标 / 观测目标 | 根据 benchmark |
| task | 任务 / 成像任务 | aeossp 语境下用“成像任务” |
| request | 请求 / 通信请求 | satnet 专用 |
| region of interest | 目标区域 | 统一 |
| polygonal region | 多边形区域 | 统一 |

## 动作与调度

| 英文 | 中文译法 | 备注 |
|---|---|---|
| action | 动作 / 操作 | 调度表语境下用“动作” |
| observation | 观测 | 统一，避免“观察” |
| schedule | 调度表 / 计划 | 名词用“调度表”，动词用“编排” |
| observation schedule | 观测调度表 | 统一 |
| strip observation | 条带观测 | regional_coverage 专用 |
| ground link | 地面链路 | relay_constellation 专用 |
| inter-satellite link (ISL) | 星间链路 | 统一 |
| track | 跟踪弧段 | satnet 语境下指一次通信跟踪任务 |

## 几何与轨道

| 英文 | 中文译法 | 备注 |
|---|---|---|
| ground track | 星下点轨迹 | 统一 |
| orbit propagation | 轨道传播 / 轨道外推 | 根据语境 |
| TLE (Two-Line Element) | TLE / 两行根数 | 首次出现加注 |
| off-nadir | 侧摆角 | 统一 |
| off-nadir angle | 侧摆角 | 统一 |
| slew | 姿态机动 | 必须明确为姿态机动，而非轨道机动 |
| slew rate | 姿态机动速率 | 统一 |
| slew acceleration | 姿态机动加速度 | 统一 |
| settling time | 稳定时间 | 统一 |
| bang-coast-bang | 加速-滑行-减速（bang-coast-bang） | 首次出现加注，后文可用英文 |
| line of sight | 视线 | 统一 |
| elevation angle | 高度角 | 统一 |
| slant range | 斜距 | 统一 |
| access window / access interval | 可见窗口 / 可见区间 | 统一，不用“访问” |
| footprint | 成像足迹 | 统一 |
| swath / swath width | 条带 / 条带宽度 | 统一 |

## 资源与约束

| 英文 | 中文译法 | 备注 |
|---|---|---|
| battery state of charge | 电池状态 | 统一 |
| power model | 功耗模型 | 统一 |
| capacity constraint | 容量约束 | 统一 |
| memory capacity | 存储容量 | spot5 专用 |
| duty cycle / duty limit | 占空比限制 | 统一 |
| solar charging | 太阳能充电 | 统一 |
| eclipse | 阴影 / 地影区 | 统一 |
| sunlit | 光照区 | 与 eclipse 对应 |

## 评分与指标

| 英文 | 中文译法 | 备注 |
|---|---|---|
| coverage_ratio | coverage_ratio | 代码字段保留英文，解释性文字可用“覆盖率” |
| service fraction | service_fraction | 代码字段保留英文，解释性文字可用“服务比例” |
| completion ratio (CR) | 完成率（CR） | 统一 |
| weighted completion ratio (WCR) | 加权完成率（WCR） | 统一 |
| mean revisit gap | 平均重访间隔 | 统一 |
| max revisit gap | 最大重访间隔 | 统一 |
| latency | 延迟 | 统一用“延迟” |
| objective / score | 目标函数 / 得分 | 优化语境用“目标函数” |
| primary metric | 主要指标 | 统一 |
| secondary metric | 次要指标 | 统一 |
| threshold satisfied | 满足阈值要求 / 达到阈值 | 不用“阈值满足” |
| valid solution | 合法解 | 统一 |
| invalid solution | 非法解 | 统一 |

## 时间与任务相关

| 英文 | 中文译法 | 备注 |
|---|---|---|
| horizon | 任务时域 | 统一，指 planning/mission horizon |
| solution | 解 / 求解结果 | 正文优先用“解”，文件名保留英文 |
| submission | 提交的解 / 提交结果 | 统一 |
| setup (satnet) | 准备 | 指跟踪前的设备准备 |
| teardown (satnet) | 收尾 | 指跟踪结束后的设备复位 |
| resource accounting | 资源预算 / 资源仿真 | 取代“资源核算” |
| sunlight detection | 光照区判定 | 取代“受晒检测” |
| eclipse calculation | 地影计算 / 阴影计算 | 取代错误的“食甚计算” |
| roll-only | 仅滚转 | 姿态控制术语 |
| idle | 待机 | 统一 |

## 立体成像专用术语

| 英文 | 中文译法 | 备注 |
|---|---|---|
| scene type | 场景类型 | urban_structured → 都市；vegetated → 林地；rugged → 山地；open → 平原 |
| tri-stereo | 三立体成像 | 统一 |
| convergence angle | 交会角 | 摄影测量标准术语 |
| B/H proxy | B/H指标 / 基高比指标 | B/H 在摄影测量中为“基高比” |
| pixel scale ratio | 像素尺度比 | 统一 |
| overlap fraction | 重叠率 | 统一 |
| pointing cone | 指向锥 | 保留 |
| bisector elevation | 平分线高度 | 统一 |
| asymmetry | 不对称性 | 统一 |
| anchor | 锚点 | 统一 |
| redundancy | 冗余 | 统一 |
