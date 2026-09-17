# DataEX-G 数据清洗与空间分析软件 V1.0 源代码文件清单（最新版）

生成日期：2026-08-29

## 交存结构

- 文档总页数：60页。
- 每页源码展示行：60行。
- 第1—30页：当前排序源码第1—1800行。
- 第31—60页：当前排序源码第4851—6650行。
- 文档展示行：3600行，其中真实非空代码3590行、路径标识10行。
- 当前有效自有源码池：6631个非空代码行，另有19个路径标识行。
- 排版：A4纵向、Consolas 6.5磅、固定行距、连续页码。

## 当前源码文件与哈希

|序号|当前源文件|原始行数|非空代码行|文档选入行|SHA-256|
|---:|---|---:|---:|---:|---|
|1|`frontend/src/main.ts`|13|9|10|`6b61098f0f95aeb24b0bba0d3976af60be960fc7d951146a7ef0f0f57221e079`|
|2|`frontend/src/App.vue`|543|502|503|`63e9b25dd09f1dc3da74a916b5d6d5616efcd5e1b337e48b50f8847818f9e4a5`|
|3|`frontend/src/services/api.ts`|294|266|267|`c996ac85dcebd5371f2b82bdd41ff77fafea406333c6c1a0e58826866ae61d35`|
|4|`frontend/src/components/GwrfWorkspace.vue`|1039|1005|1006|`62553d71f8abbfe93c2f5d0dbf72c8b5350e01e4ad159f8391bc5cac60c2ad04`|
|5|`frontend/src/components/AnalysisWorkspace.vue`|617|545|14|`f992cafd06f48f11b6124b2f6153ad64754756d4f579ba7f9d905beecae029ca`|
|6|`frontend/src/components/SpatialWorkspace.vue`|582|540|0|`0e2eeb0316db46533935f0c055830e74e771f30b2a9e42ea37f91b954243b629`|
|7|`frontend/src/types/analysis.ts`|353|320|0|`607e0ff904ef56d4bd83fb09d44daa5244571edda0c398d972cb7415bcc11301`|
|8|`frontend/src/router/index.ts`|8|6|0|`756fccdf1704f381b282456b65af866468ab08cd5ab274e2fd39ed8fc06bd7b7`|
|9|`frontend/src/assets/main.css`|921|780|0|`70ae774b2ec6a418f78c30e6835e4ee067caea1bf4a2888c6eae505ecc7a7a18`|
|10|`backend/src/backend/resources.py`|16|12|0|`15cce01cb6f6e4caf64b7196f72bdab045194c7eae0a4b1b53cb1458b0d2d3ef`|
|11|`backend/src/backend/quality.py`|113|96|0|`3d7099792cbb3757924428676ce8586c0d4a5c7a3e24a513fef2c9f8a6f8cf72`|
|12|`backend/src/backend/cleaning.py`|199|165|0|`df0769960a570ab2b591ce3035040ff9706ac4a555e90ad62655e6b2a8e69874`|
|13|`backend/src/backend/diagnostics.py`|147|131|0|`e99a2ab0f6c8ac4325818ebbbfb00aa607d68a61187a17cee3b46c5ce6f6b83e`|
|14|`backend/src/backend/spatial.py`|587|536|77|`2429f3fe3aea26899928a4ff43ce4da1a3f14e9942dc6d938987ffeacf8d9d09`|
|15|`backend/src/backend/analysis.py`|241|210|211|`6c0cb5ae3121d45e96bb384225cf46a158e983f58b0c8be93334784488826003`|
|16|`backend/src/backend/gwrf.py`|602|554|555|`d7b043b505eef6377d1fe1c5b40f874439816f6a1bdc04e35ad378e5729344a3`|
|17|`backend/src/backend/reporting.py`|293|266|267|`a60017e693412298af876882bfc9085652329d8b425342e74873c448124ce272`|
|18|`backend/src/backend/desktop.py`|158|131|132|`4e3fbd927621d82262b74769666366f807f79f16870de9bfced0f6dde54ff60c`|
|19|`backend/src/backend/main.py`|626|557|558|`3f22d2789a879e93381fac76e6e6849e17f6b866fdc4ffe712b454c9b5f984b0`|

## 实际选入范围

- `frontend/src/main.ts`：源码第1—10行，共10行。
- `frontend/src/App.vue`：源码第11—513行，共503行。
- `frontend/src/services/api.ts`：源码第514—780行，共267行。
- `frontend/src/components/GwrfWorkspace.vue`：源码第781—1786行，共1006行。
- `frontend/src/components/AnalysisWorkspace.vue`：源码第1787—1800行，共14行。
- `backend/src/backend/spatial.py`：源码第4851—4927行，共77行。
- `backend/src/backend/analysis.py`：源码第4928—5138行，共211行。
- `backend/src/backend/gwrf.py`：源码第5139—5693行，共555行。
- `backend/src/backend/reporting.py`：源码第5694—5960行，共267行。
- `backend/src/backend/desktop.py`：源码第5961—6092行，共132行。
- `backend/src/backend/main.py`：源码第6093—6650行，共558行。

## 排除内容

- `node_modules/`、`backend/.venv/`及第三方依赖源码。
- `dist/`、`build/`、`frontend/dist/`等构建产物。
- 缓存、日志、临时文件、二进制、图片、字体和示例数据。
- 依赖锁文件、测试文件及与核心功能无关的配置。
- 已删除的示例计数器文件和空的包初始化文件未作为有效源码计入。

## 当前版本核对重点

- 已包含当前App、GWRF工作区及前端API代码，不含已删除ARIA和冗余前端分支。
- 已包含GWRF自动参数寻优单进程保护、带宽寻优和最终模型流程。
- 已包含`export_id`、完整结果缓存、Blob校验、超时与`finally`状态恢复。
- 已包含当前空间分析、回归分析、结果导出、桌面启动及FastAPI接口代码。
- 后端占位`main()`已删除，空`__init__.py`不计入有效源码。
