# SatNet 数据集布局

规范 SatNet 数据集以按测试实例的周/年实例形式存储。

## 结构

```text
dataset/
├── README.md
├── index.json
├── mission_color_map.json
├── example_solution.json
└── cases/
    └── test/
        └── W10_2018/
            ├── problem.json
            ├── maintenance.csv
            └── metadata.json
```

## 规范测试实例

每个测试实例目录包含验证一个 SatNet 实例所需的全部内容：

- `problem.json`：恰好一个 `(week, year)` 实例的请求列表
- `maintenance.csv`：过滤到同一实例的维护窗口
- `metadata.json`：轻量级每测试实例摘要元数据

共享的、对验证器非关键的 benchmark 元数据保留在数据集范围：

- `index.json`：数据集清单和数据集级来源来源
- `example_solution.json`：数据集范围的一个最小可运行解（与普通提交的 schema 相同），用于验证器冒烟测试；这些不是基线
- `mission_color_map.json`：从上游 SatNet 发布继承的任务显示元数据

## 来源

规范测试实例由聚合的上游 SatNet 数据生成：

- 仓库：`https://github.com/edwinytgoh/satnet`
- 源文件：`data/problems.json`、`data/maintenance.csv`、`data/mission_color_map.json`

提交的子集分配记录在 [splits.yaml](../splits.yaml) 中，当前将所有五个发布的测试实例放入 `test` 子集，并将 `dataset/example_solution.json` 与 `test/W10_2018` 配对。

使用 [generator.py](../generator.py) 从上游源或上游 `data/` 目录的本地副本重新生成此布局：

```bash
uv run python benchmarks/satnet/generator.py benchmarks/satnet/splits.yaml
```
