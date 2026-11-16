# CellMem — frozen full-axis donor-precision implementation

本目录发布 `FULL_DONOR_PRECISION` 的可运行代码，软件版本 `cellmem-full-axis 0.1.0`。
方法冻结日期为 2026-11-16，代码交付整理日期为 2026-11-17。源码来自原封存提交
`99c44254ad2aa46ae26349ce3d39a4c0e971e27e`，6 个运行源文件保持原样。
GitHub 发布提交与原研究封存提交分别记录，不能混同。

**精修方法图从 [代码与方法图对应说明](docs/method_figure.md) 和
[实际执行入口 api.py](src/cellmem_full_axis/api.py) 开始。**

## 当前算法

输入为供体×细胞类型参考 RNA 谱、参考原始计数、相同有序基因轴上的 bulk 原始计数。
保留多参考列，在完整输入基因轴上先求一次计数组成解，再由参考供体均值方差、
初始组成和 bulk 深度计算基因精度，固定该精度重新求解一次，最后按类型聚合。
输出为已知类型的 RNA 份额及数值诊断。

本版不运行 VarPool 方差借用、不使用固定 828 基因身份面板、不输出 UNKNOWN、
细胞数量比例或存在概率。单供体类型的方差不受支持，数值上保留 0 并明确标记。
代码封存与后续实验评估是两个不同事项；本仓库不宣称所有数据集或指标均最优。

## 安装及合成示例

在本目录下使用 Python 3.11；原验证环境为 Python 3.11.5 / Windows。
依赖固定为 NumPy 1.26.2、SciPy 1.11.4。

```sh
python -m pip install .
python examples/make_synthetic_inputs.py --out demo_inputs
cellmem-full-axis --reference demo_inputs/reference.npz --bulk demo_inputs/bulk.npz --out demo_predictions
```

输出目录必须不存在。示例仅产生合成矩阵，不读取研究数据。

```sh
python -m unittest discover -s tests -p "test_frozen_method.py" -v
python environments/check_python_environment.py
```

## 目录

| 目录/文件 | 用途 |
|---|---|
| `src/cellmem_full_axis/api.py` | 当前 FULL 路径的输入检查与两阶段推断 |
| `src/cellmem_full_axis/_frozen_core.py` | 原样冻结的计数目标和数值求解器 |
| `src/cellmem_full_axis/io.py`、`cli.py` | 输入合同、运行锁及预测输出 |
| `examples/`、`tests/` | 合成示例和 8 项现有合同/一致性测试 |
| `frozen/FULL_DONOR_PRECISION_20261116/core.py` | 核心字节一致性测试所需原始副本 |
| `docs/` | 方法、绘图对应关系和数据交付状态 |
| `environments/` | 最小环境和原观测环境核验 |
| `SOURCE_PROVENANCE.json` | 与原封存提交、源码哈希的对应 |
| `FILE_MANIFEST.json` | 本次代码交付文件清单与哈希 |

原始矩阵、作者标签、供体/细胞划分、目标真值、逐混合输出、历史方法代码和大型环境包
保存在独立研究归档中。数据分享进度见 [DATA_ACCESS.md](docs/DATA_ACCESS.md)。
此代码快照没有加入新的开源许可授权；第三方软件遵循各自许可。

## 可复现性边界

输入字段隔离和核心字节核验并不替代上游数据来源、划分和开发历史的泄露审查。
两次固定权重凸子问题的数值认证并不证明整个两阶段估计器联合全局最优。
参考均值方差不同于新供体预测方差；当前公式未估计类型间协方差。
科学解释与完整输入合同见 [method_full_donor_precision.md](docs/method_full_donor_precision.md)。
