# CellMem 本地运行工作台

本界面调用冻结的 `FULL_DONOR_PRECISION`（包版本0.1.0），不重写求解器，不提供研究参数搜索。
输入文件、计算和运行记录保留在本机。网页包含运行工具、数据集核验、方法源码导航和运行记录四个页面。

## 启动

要求 Python 3.11、NumPy 1.26.2、SciPy 1.11.4。UI附加依赖为Flask/Werkzeug。

```sh
python -m pip install -r local/requirements-ui.txt
python local/server.py --port 8766
```

在浏览器打开 `http://127.0.0.1:8766`。Windows用户也可运行 `local/Start-CellMem.ps1`；启动脚本优先使用当前目录的`.venv`，其次查找本机已有Python。
建议为其他机器创建独立Python 3.11环境，不在旧研究环境里升级依赖。

界面仅绑定本机回环地址，不能把本地服务直接当作面向互联网的多人计算服务。
静态HTML可浏览方法和核验报告，但运行预测必须启动上述本地Python服务；没有服务器时运行按钮禁用。

## 第一次使用

1. 点击“体验合成示例”，再点击“运行冻结算法”。这只产生5基因、3虚构类型、2样本的合成运行。
2. 查看样本RNA份额、参考供体支持量和数值认证状态；下载结果ZIP，其中包含原CLI输出和运行锁。
3. 用自己的 `reference.npz`、`bulk.npz` 替换示例。预测接口不读取目标真值，两个文件必须具有完全一致的有序基因轴。

参考字段：`F`、`reference_count_sums`、`column_type`、`types`、`genes`，建议提供`donor_labels`。
bulk字段：`Y`、`genes`、`ids`。`F`是按供体×类型聚合后列归一化的RNA谱；`reference_count_sums`是对应的原始计数；`Y`是未变换计数。
本版不直接导入未经构建的H5AD、CSV或Seurat对象，不会通过改扩展名将它们转换为合法输入。

## 限制与状态

- 本地界面每次最多200个bulk样本、两个上传文件合计128 MB、单个NPZ展开不超过1 GiB；更大批次使用原CLI。界面不会静默截断输入。
- 同时运行一个任务。每次使用新目录，不覆盖已有输出。
- `complete`：两阶段数值认证均通过；`uncertified`：有有限输出但未全部通过原数值认证，仍保留结果；`failed`：校验或运行失败。
- 单供体类型的方差不受支持，UI如实提示；未执行VarPool借方差、固定828基因面板或UNKNOWN识别。
- 输出单位为当前完整输入基因轴的RNA份额，不是细胞数量比例或存在概率。界面不会无真值地生成MAE或“准确率”。

## 数据核验

`dist/audit-report.json`和`dist/audit-data.js`为2026-11-17本轮只读审查的汇总。
`dist/audit-detail.json`保留逐卷、逐来源、逐划分与逐输入背景的详细核验，可在界面下载。
完整性（ZIP SHA256和CRC）、注册映射、矩阵/标签/划分的实际检查分层报告。
PASS仅针对明示的检查范围，不能当作“所有原始作者标签、跨来源一致性和独立金标准都已证明”。
Hao的批次不冒充独立人员；细胞划分不冒充人员独立验证；历史抽样标签表与全源角色表分开说明。
本轮未重跑研究模型、未修改原划分、未读取封存测试真值数值。

[原代码与方法说明](https://github.com/zzbyzt/SMSever/tree/master/CellMem)

[数据归档](https://pan.baidu.com/s/1pMzediWV4fjJEDvjRMPa2g?pwd=8vxj)，提取码`8vxj`。

## 发布范围

`method/src`保存与原冻结版字节一致的6个运行源文件；`method/examples`仅含合成生成器。
真实矩阵、逐样本研究结果、用户上传数据、本地任务日志、浏览器测试环境和`.pyc`缓存不包含在UI源码发布中。
附加UI不构成新的算法版本或对既有成功标准的修改。
