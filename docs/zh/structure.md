# 项目结构

## 目录结构

```
astro-reason/
├── benchmarks/                 # 基准测试模块
│   ├── aeossp_standard/       # 标准敏捷地球观测调度
│   ├── latency_optimization/  # 通信延迟优化
│   ├── regional_coverage/     # 区域覆盖调度
│   ├── revisit_constellation/  # 星座重访设计与调度
│   ├── satnet/                # 深空网络调度
│   ├── spot5/                 # SPOT-5 卫星拍摄调度
│   └── stereo_imaging/        # 立体成像调度
├── tests/                     # 测试用例
│   ├── benchmarks/            # 基准测试验证器测试
│   └── fixtures/              # 测试数据和参考解决方案
├── docs/                      # 项目文档
├── pyproject.toml             # 项目配置
└── README.md                  # 项目说明
```

## benchmarks/{name}/ 目录结构

每个基准测试子目录遵循统一的结构：

```
benchmarks/{name}/
├── dataset/              # 问题实例数据
│   ├── index.json       # 数据集级元数据（如适用）
│   ├── case_0001/       # 具体案例
│   ├── case_0002/
│   └── ...
├── verifier.py          # 验证和评分逻辑，或 verifier/run.py
├── generator.py         # 可选生成器，或 generator/run.py
├── visualizer.py        # 可选可视化工具，或 visualizer/run.py
└── README.md            # 问题说明和数据格式
```

### dataset/ 目录结构

典型的数据集结构会随基准而不同，但通常采用按案例组织的目录：

```
dataset/
├── case_0001/
│   ├── assets.json          # 资产、平台或约束定义
│   ├── mission.json         # 任务时间范围与目标需求
│   └── ...                  # 基准特定的其他文件（如适用）
└── ...
```

## 测试结构

```
tests/
├── benchmarks/                      # 针对验证器的测试
│   ├── test_aeossp_standard_verifier.py
│   ├── test_satnet_verifier.py
│   └── test_spot5_verify.py
└── fixtures/                      # 测试数据
    ├── aeossp_standard/           # AEOSSP Standard 语义锁定夹具
    ├── case_0001/                 # 测试案例数据
    ├── satnet_mock_solutions/     # SatNet 参考解决方案
    └── spot5_val_sol/             # SPOT-5 参考解决方案
```

## 关键文件说明

### verifier.py / verifier/run.py

每个基准的核心验证入口，定义：
- 解决方案的加载和解析
- 约束验证逻辑
- 评分指标计算

### generator.py / generator/run.py（可选）

数据生成器，用于：
- 创建新的问题实例
- 扩展数据集
- 生成合成数据

### visualizer.py（可选）

结果可视化工具，用于：
- 绘制调度结果
- 可视化约束满足情况
- 生成分析图表
