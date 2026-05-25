[English](../../../README.md) | 中文

# AstroReason-Bench

AstroReason-Bench 正在演进为一个用于空间任务设计 benchmark 和第一方方法层的 monorepo。

benchmark 核心保持算法无关（algorithm-agnostic）：benchmark 定义问题、数据集和验证器（verifier）；方法消费 benchmark，而非相反。

如需复现历史论文，请使用 `v1` 分支。

## 仓库结构

```text
astro-reason/
├── benchmarks/   # 标准问题、数据集、验证器、生成器
├── experiments/  # 可复现的方法评估运行
├── solvers/      # 传统求解器实现
├── runtimes/     # 可复用的 agent 系统执行基座
├── scripts/      # 仓库自有的编排与验证入口
└── tests/        # 聚焦的 benchmark 与工具测试
```

## 设计原则

- **算法无关的 benchmark 核心（algorithm-agnostic benchmark core）**：`benchmarks/` 不编码偏好的求解策略。
- **单向契约（one-way contracts）**：方法可以依赖 benchmark；benchmark 不得依赖方法代码。
- **独立的 benchmark（standalone benchmarks）**：每个 benchmark 保持自包含。
- **可复现的方法层（reproducible method layers）**：实验、求解器和运行时应该是可运行且可检查的。

## 目录角色

- `benchmarks/` 拥有公开的 benchmark 定义和 benchmark 侧工具。
- `experiments/` 拥有扁平的可运行实验族和共享的提示词/配置片段。
- `solvers/` 拥有传统的非 agent 求解器方法。
- `runtimes/` 拥有可复用的 agent 运行时环境、构建逻辑和共享运行时资源。

## 环境

benchmark 核心开发使用 `uv`。方法所属的目录可以在有正当理由时使用不同的工具，只要 benchmark 契约保持干净。

## 状态

当前工作聚焦于：

- 精炼 benchmark 定义和验证器契约
- 开发传统求解器作为基线
- 实现和运行 agent 实验
