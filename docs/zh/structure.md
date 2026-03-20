# 项目结构

## 目录结构

```
astro-reason/
├── benchmarks/                 # 基准测试模块
│   ├── aeosbench/             # 敏捷地球观测卫星星座调度
│   ├── latency_optimization/  # 通信延迟优化
│   ├── regional_coverage/     # 区域覆盖调度
│   ├── revisit_optimization/   # 重访优化
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
│   ├── case_0001/       # 具体案例
│   ├── case_0002/
│   └── ...
├── verifier.py           # 验证和评分逻辑
├── run.py               # 可选的运行入口
├── generator.py         # 可选的生成器
├── visualizer.py        # 可选的可视化工具
└── README.md            # 问题说明和数据格式
```

### dataset/ 目录结构

典型的数据集结构：

```
dataset/
├── case_0001/
│   ├── manifest.json         # 案例元数据（时间范围等）
│   ├── satellites.yaml      # 卫星定义（TLE数据）
│   ├── targets.yaml         # 目标位置
│   ├── stations.yaml        # 地面站位置
│   └── requirements.yaml    # 任务需求
└── ...
```

## 测试结构

```
tests/
├── benchmarks/                      # 针对验证器的测试
│   ├── test_aeosbench_verifier.py
│   ├── test_satnet_verifier.py
│   └── test_spot5_verify.py
└── fixtures/                      # 测试数据
    ├── aeosbench_gt_bsk2.9.0/    # AEOSbench 参考数据
    ├── case_0001/                 # 测试案例数据
    ├── satnet_mock_solutions/     # SatNet 参考解决方案
    └── spot5_val_sol/             # SPOT-5 参考解决方案
```

## 关键文件说明

### verifier.py

每个基准的核心验证入口，定义：
- 解决方案的加载和解析
- 约束验证逻辑
- 评分指标计算

### generator.py（可选）

数据生成器，用于：
- 创建新的问题实例
- 扩展数据集
- 生成合成数据

### visualizer.py（可选）

结果可视化工具，用于：
- 绘制调度结果
- 可视化约束满足情况
- 生成分析图表
