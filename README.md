# DataEX-G

DataEX-G 是一款面向 Windows 的本地数据处理与统计分析桌面应用。它使用 Python 完成数据处理和模型计算，使用 Vue 3 提供图形界面，可在不连接网络的情况下处理 CSV 和 XLSX 文件。

## 主要功能

### 数据检查与清洗

- 预览 CSV、XLSX 文件的字段、数据类型和部分数据。
- 统计空值单元格及包含空值的数据行。
- 检测文本前后空格、回车符和换行符。
- 检查同一列中可能存在的数据格式不一致问题。
- 支持删除包含空值的整行。
- 支持将含空值的数据行摘出为独立数据表。
- 支持使用数值 `0` 替换空值。
- 支持按用户选择清除文本前后空格、回车符和换行符。
- 清洗操作提供结果预览，不会直接覆盖原始文件。

### 数据标准化

- Min-Max 标准化。
- Z-score 标准化。
- 可选择需要标准化的数值列。

### 回归与相关性分析

- OLS 普通最小二乘回归。
- 负二项回归。
- Logistic 二元回归。
- Pearson 相关性分析。
- Spearman 相关性分析。
- 展示系数、标准误、统计量、p 值和 95% 置信区间等结果。
- 检测模型收敛、非有限数值、数值尺度异常和多重共线性风险。

### 空间分析

- 支持经纬度坐标以及投影坐标 `X`、`Y`。
- 使用 K 近邻方法建立空间权重，并进行行标准化。
- 全局 Moran's I 空间自相关检验。
- 空间滞后模型（SLM / SAR）。
- 空间误差模型（SEM）。
- 空间杜宾模型（SDM）。
- 地理加权回归（GWR）。
- 计算 SLM / SDM 的直接效应、间接效应和总效应。
- 提供残差 Moran 检验和基于 LM 检验的空间模型选择提示。
- 检测重复坐标、模型收敛、数值异常和共线性问题。
- GWR 可导出全部局部回归结果。

### 结果导出

- 清洗后的主表可导出为 CSV 或 XLSX。
- 摘出的空值数据表可单独导出。
- 回归与相关性分析结果可导出为 CSV 或 XLSX。
- 空间分析结果可导出为 CSV 或 XLSX。
- 新生成的数据文件名称会添加 `-dataex` 后缀。

## 下载与运行

1. 打开项目的 [GitHub Releases](https://github.com/GGzzzW/data-analysis-desktop/releases)。
2. 下载最新的 `DataEX-G-windows-x64.zip`。
3. 将压缩包完整解压到本地文件夹。
4. 双击 `DataEX-G.exe` 启动程序。

请保留解压后的完整程序目录，不要只复制其中的 EXE 文件。程序在本机运行，不要求安装 Python、Node.js 或开发工具；目标电脑需要具备 Microsoft Edge WebView2 Runtime。

## 使用流程

1. 选择数据清洗、回归分析或空间分析窗口。
2. 导入 CSV 或 XLSX 文件。
3. 查看数据检查结果并选择处理规则或分析方法。
4. 设置所需字段和参数。
5. 运行并检查结果与诊断警告。
6. 将结果导出为 CSV 或 XLSX。

## 使用注意事项

- 建议始终保留原始数据文件，并将导出结果保存为新文件。
- 回归模型的显著性、收敛和诊断信息需要结合研究设计与专业知识解释。
- 空间分析结果依赖坐标系统、邻居数量和空间权重设定。经纬度与投影坐标不应混用，正式分析建议比较不同参数设定。
- 当前版本的 GWR 最多处理 5,000 条坐标和变量均完整的观测记录。
- 软件提供的是数据处理与分析辅助功能，不应将自动提示直接视为最终研究结论。

## 技术架构

- 前端：Vue 3、TypeScript、Vite。
- 后端：Python、FastAPI、pandas、statsmodels、PySAL、MGWR。
- 桌面窗口：pywebview。
- Windows 打包：PyInstaller。

## 项目结构

```text
data-analysis-desktop/
├── backend/       Python 数据处理、统计分析与本地 API
├── frontend/      Vue 3 桌面界面
├── icon/          DataEX-G 程序图标
├── packaging/     Windows 打包配置与说明
├── samples/       示例数据
└── README.md      项目说明
```

## 开发与测试

后端测试：

```powershell
cd backend
uv run pytest
```

前端开发：

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

Windows 打包方法请查看 [packaging/README.md](packaging/README.md)。

