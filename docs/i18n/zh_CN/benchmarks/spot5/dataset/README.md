# SPOT-5 数据集布局

规范 SPOT-5 数据集按测试实例存储在 `cases/` 下。

每个测试实例目录恰好包含一个原始实例文件：

```text
dataset/
├── index.json
├── example_solution.json
└── cases/
    └── <split>/
        └── <case_id>/
            └── <case_id>.spot
```

示例：

- `cases/single_orbit/8/8.spot`
- `cases/multi_orbit/1502/1502.spot`
- `cases/test/1021/1021.spot`

`index.json` 记录 benchmark 名称、上游来源、已发布的子集感知测试实例放置列表，以及 `example_smoke_case`，用于在 CI 中将示例解与测试实例配对（参见 `docs/benchmark_contract.md`）。

`example_solution.json` 是一个最小可运行解（与普通提交的 schema 相同），用于验证器冒烟测试。这些不是基线。

提交的子集分配记录在 [splits.yaml](../splits.yaml) 中。它定义了完整的 `single_orbit` 和 `multi_orbit` 测试实例族，以及一个重叠的以种子 `42` 抽取的 5 测试实例 `test` 子集。

要从上游 Mendeley 发布重新生成此布局，请运行：

```bash
uv run python benchmarks/spot5/generator.py benchmarks/spot5/splits.yaml
```

要从本地原始 `.spot` 文件目录重新生成，请运行：

```bash
uv run python benchmarks/spot5/generator.py benchmarks/spot5/splits.yaml --source-dir /path/to/raw-spot-files
```
