# Benchmark Contract

本文档定义了本仓库中 benchmark 布局、公共入口点以及 CI 强制执行的契约。

该契约仅对列入 `benchmarks/finished_benchmarks.json` 的 benchmark 强制执行。仍在积极开发中的 benchmark 受仓库惯例约束，但尚未纳入严格 CI 检查范围。

## 已完成 Benchmark 元数据

`benchmarks/finished_benchmarks.json` 是判定 benchmark 是否已完成的唯一事实来源。

每个已完成 benchmark 条目记录：

- benchmark 名称
- 是否应在专用 CI 中运行生成器可复现性检查
- 哪些数据集路径属于生成器拥有的规范输出

将 benchmark 提升为已完成状态，应仅在其公共 README、数据集布局、生成器、验证器和测试均已稳定后进行。

## 必需的 Benchmark 结构

每个已完成 benchmark 必须位于 `benchmarks/<name>/` 下，并包含：

- `README.md`
- `dataset/`
- `splits.yaml`
- 生成器入口点：`generator.py` 或 `generator/run.py`
- 验证器入口点：`verifier.py` 或 `verifier/run.py`

可选：

- `visualizer.py` 或 `visualizer/run.py`
- `dataset/index.json`
- `dataset/README.md`

已完成 benchmark 不允许存在其他被追踪的顶层条目。

## 入口点调用策略

Benchmark 入口点调用遵循文件布局：

- **顶层脚本**（`generator.py`、`verifier.py`、`visualizer.py`）：直接从仓库根目录以 `python benchmarks/<name>/<entrypoint>.py ...` 方式调用。
- **包入口点**（`generator/run.py`、`verifier/run.py`、`visualizer/run.py`）：以模块方式调用：`python -m benchmarks.<name>.<entrypoint_pkg>.run ...`（从仓库根目录执行）。

请勿为同一入口点同时支持两种调用方式。（这属于公共契约的一部分，但当前契约验证器只会选择第一个匹配的入口点，当两者同时存在时不会报错。）不要为了能让嵌套的 `run.py` 作为直接路径脚本运行而添加引导 hack（如 `sys.path` 手术、伪造运行时包等）。

## 数据集契约

已完成 benchmark 的规范数据集布局为：

```text
dataset/
├── example_solution.json  # 必需，一个最小可运行示例（ schema 与真实解决方案相同）
├── cases/
│   └── <split>/
│       └── <case_id>/
├── index.json      # 可选
└── README.md       # 可选
```

规则：

- `dataset/cases/` 是必需的。
- 已完成 benchmark 的规范提交布局为 `dataset/cases/<split>/<case_id>/`。
- 划分（split）名称是 benchmark 拥有的路径段，通过 `splits.yaml` 进行验证。
- 案例标识符是 benchmark 特定的。CI 不要求必须使用 `case_####` 的命名模式。
- 数据集根目录必须包含 `example_solution.json`、`example_solution.yaml` 或 `example_solution.yml`，以便 CI 能自动针对真实 benchmark 案例运行公共验证器。该文件必须包含**单个**解决方案对象，其 schema 与普通按案例解决方案文件相同（不能是从案例 ID 到解决方案的映射）。
- `index.json` 是可选的。如果存在，它是 benchmark 元数据，而非完成状态的第二事实来源。它可以包含可选的 `example_smoke_case`（字符串）：一个相对案例路径，例如 `test/case_0001`，在 `dataset/cases/` 下解析。省略时，CI 使用 `dataset/cases/<split>/` 下字典序第一个案例目录。
- 生成器不得写入 `dataset/README.md`。
- 当附加的追踪数据集文件是 benchmark 拥有的公共产物并在 benchmark README 中有文档说明时，允许存在。
- `dataset/source_data/` 可用作下载/缓存目录，但必须保持 gitignored，且运行生成器前不要求其必须存在。

## 单位约定（推荐，非 CI 强制）

Benchmark 数据集应对物理单位进行一致编码：

- 线性量：米（键后缀 `_m`，或在键无量纲时在 README 中说明）。
- 面积量：平方米。
- 时间跨度：秒（后缀 `_s` 或 `_sec`，以该 benchmark 文档为准）。
- 速度量：米/秒（后缀 `_m_s` 或等效文档化命名）。
- 角度量：度（后缀 `_deg`）或弧度（后缀 `_rad`）。
- 时间戳：ISO 8601 格式，带 `Z` 或显式 UTC 偏移。

在有助于提升清晰度的地方，优先使用 SI 风格的键和值；但当非 SI 时间单位（如小时）是问题的自然术语并在 benchmark README 中有清晰文档时，benchmark 可以使用非 SI 时间单位。

## 生成器契约

已完成 benchmark 的生成器必须满足以下条件：

- 对已完成的 benchmark，提交一份 benchmark 本地的 `splits.yaml` 是强制的。
- **顶层** `generator.py`：可运行方式为 `python benchmarks/<name>/generator.py ...`。
- **嵌套** `generator/run.py`：可运行方式为 `python -m benchmarks.<name>.generator.run ...`。
- 复现规范数据集必须使用显式 YAML 路径：
  - `python benchmarks/<name>/generator.py benchmarks/<name>/splits.yaml`
  - `python -m benchmarks.<name>.generator.run benchmarks/<name>/splits.yaml`
- 不带所需 YAML 路径运行时，必须失败并输出用法信息。已完成的 benchmark 不再保留无参数的规范生成路径。
- 提交的 `splits.yaml` 是 benchmark 拥有的公共配置，不是占位符。它应足够清晰地暴露预期的数据集构建参数，使读者无需从 Python 代码中反向工程生成器默认值。
- 数据集构建参数应放在 YAML 中。纯操作型控制项，如 `--help`，以及在有正当理由时保留的 benchmark 特定运行时开关（如 force-refresh 或 force-download 行为），可以作为可选 CLI 标志保留。
- 如果需要下载源数据，生成器可以将它们缓存到 `dataset/source_data/` 下，但也必须能在该缓存缺失时执行实时下载。

案例规范应从参数中算法推导（种子、缩放规则、采样），而不是从手工维护的每案例元组列表中得来。不鼓励硬编码精心策划的列表（如 `base_specs` 或 `BASE_SPECS`）；有关参考方法，请参见 `stereo_imaging` 生成器模式（例如由种子驱动的采样）。

### `splits.yaml` 模式

已完成的 benchmark 必须提交一份带有顶层 `splits:` 映射的 `splits.yaml`。支持两种共享结构：

**划分参数**：供按划分构建案例的算法生成器使用：

```yaml
splits:
  easy:
    seed: 42
    case_count: 5
    max_satellites: 3
  hard:
    seed: 142
    case_count: 5
    max_satellites: 12
```

**划分分配**：供将现有案例 ID 分配到各划分的固定案例 benchmark 使用：

```yaml
splits:
  test:
    - case_001
    - case_002
  train:
    - case_003
    - case_004
```

规则：

- 单划分 YAML 是有效的。
- 每个 benchmark 的 `splits:` 映射应只使用一种模式，不要混用分配列表和参数字典。
- 非显而易见的 benchmark 自有字段应加文档说明。内联 YAML 注释是首选，有助于解释参数含义或其对数据集构建的影响。

## 验证器契约

已完成 benchmark 的验证器必须满足以下条件：

- **顶层** `verifier.py`：可运行方式为 `python benchmarks/<name>/verifier.py ...`。
- **嵌套** `verifier/run.py`：可运行方式为 `python -m benchmarks.<name>.verifier.run ...`。
- 公共 CLI 接受两个位置参数：
  - `case_dir`
  - `solution_path`
- 任何额外的 CLI 选项必须是可选的。
- 验证器必须按文档所述可运行，并且必须能够在不崩溃的情况下加载规范案例。

数据集级别的 `example_solution.json` 或 `example_solution.yaml` 是已完成 benchmark 验证器冒烟测试的首选约定。它保存一个最小可运行解决方案，其 schema 与真实提交一致。与案例目录配对时，当冒烟案例不是 `dataset/cases/<split>/` 下字典序第一个时，使用 `index.json` 中的 `example_smoke_case`。该字段值是相对路径，例如 `test/case_0001`。这些是可运行示例，不是基线。

### 参考系（建议，非 CI 强制）

坐标系选择是 benchmark 特定的。对于使用地心坐标系的验证器：

- **地固系（ECEF）**：高精度场景下优先使用 ITRF 等明确定义的实现。
- **惯性系（ECI）**：适用时优先使用 GCRF 等标准天球坐标系。
- 在验证器内部一致使用同一个天体力学工具栈，避免混用坐标系导致的不一致。
- 如果地球定向参数（EOP）或类似因素会影响解决方案，请在 benchmark README 中记录策略。

这些是建议，不是严格 CI 要求：某些 benchmark 可能为了清晰而使用简化坐标系。

## 强制执行的 CI 检查

对于已完成 benchmark，CI 强制执行：

- benchmark 已列入 `benchmarks/finished_benchmarks.json`
- 必需的顶层文件和目录存在
- 规范案例布局为 `dataset/cases/<split>/<case_id>/`
- benchmark 本地 `splits.yaml` 存在且 schema 有效
- 数据集根目录存在验证器冒烟测试用的示例解决方案
- 无被追踪的 `dataset/source_data/`
- 无被追踪的编辑器备份产物（如以 `~` 结尾的文件）
- 生成器/验证器/可视化工具代码中无 `sys.path` hack
- 生成器/验证器/可视化工具代码中无 `from benchmarks.` 导入
- 每种入口点形状（直接脚本 vs `python -m`）均能通过生成器 `--help`、生成器无参失败、验证器冒烟测试
- 通过仓库测试
- 对 `"repro_ci": true` 的 benchmark 运行 `scripts/check_finished_benchmark_repro.py` 可复现性检查

GitHub Actions 运行：

- PR/push CI（`ci.yml`）：测试 + 契约验证
- PR/push 可复现性检查（`benchmark-repro.yml`）：针对 `"repro_ci": true` 的 benchmark 的生成器可复现性检查
- Push i18n 同步提醒（`i18n-sync.yml`）：非阻塞检查，当中文译文可能需要更新时自动创建提醒 issue
- Release 数据集同步（`sync-datasets.yml`）：在 release 发布时上传 benchmark 数据集到 Hugging Face

复现工作流仅比较生成器自有的数据集输出，因为已完成 benchmark 也可能保留有文档说明的手写数据集产物，如数据集级注释。

## 已文档化但尚未完全自动化的内容

以下属于公共契约的一部分，即使 CI 尚未完全强制执行：

- benchmark 公共代码和公共产物不得引用仅限内部使用的指导文件，如 `AGENTS.md`、`CLAUDE.md`、`GEMINI.md` 或 `docs/internal/`
- 公共验证器/生成器/可视化工具代码应避免路径 hack 和其他脆弱的引导方式
- 面向公共 benchmark 的数据和注释应避免泄露 benchmark 信息的措辞，明确告诉 space agent 它正位于验证 harness 内部
- 本仓库保持无解决方案状态；示例解决方案仅用于验证器冒烟测试，不是基线
