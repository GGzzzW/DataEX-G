<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { exportSpatialAnalysis, previewFile, runSpatialAnalysis } from '@/services/api'
import type {
  CoordinateType,
  ExportFormat,
  FilePreviewResponse,
  SpatialAnalysisResponse,
  SpatialMethod,
} from '@/types/analysis'

const methods: Array<{ value: SpatialMethod; label: string; description: string }> = [
  { value: 'moran', label: "Moran's I", description: '检验一个变量的全局空间自相关' },
  { value: 'slm', label: 'SLM / SAR', description: '包含因变量空间滞后项 Wy' },
  { value: 'sem', label: 'SEM', description: '误差项存在空间相关结构' },
  { value: 'sdm', label: 'SDM', description: '同时包含 Wy 与自变量空间滞后 WX' },
  { value: 'gwr', label: 'GWR', description: '估计随空间位置变化的局部系数' },
]

const selectedFile = ref<File | null>(null)
const dataset = ref<FilePreviewResponse | null>(null)
const selectedMethod = ref<SpatialMethod>('moran')
const coordinateType = ref<CoordinateType>('geographic')
const xColumn = ref('')
const yColumn = ref('')
const dependentColumn = ref('')
const independentColumns = ref<string[]>([])
const neighbors = ref(8)
const result = ref<SpatialAnalysisResponse | null>(null)
const errorMessage = ref('')
const isReading = ref(false)
const isRunning = ref(false)
const exportingFormat = ref<ExportFormat | ''>('')
const exportMessage = ref('')

const numericColumns = computed(() =>
  (dataset.value?.quality.columns ?? [])
    .filter(
      (column) =>
        !column.mixed_types &&
        column.detected_types.length === 1 &&
        column.detected_types[0]?.type === 'number',
    )
    .map((column) => column.name),
)

const isMoran = computed(() => selectedMethod.value === 'moran')
const availableIndependentColumns = computed(() =>
  numericColumns.value.filter(
    (column) =>
      column !== dependentColumn.value && column !== xColumn.value && column !== yColumn.value,
  ),
)
const canRun = computed(
  () =>
    Boolean(
      selectedFile.value &&
        xColumn.value &&
        yColumn.value &&
        xColumn.value !== yColumn.value &&
        dependentColumn.value &&
        (isMoran.value || independentColumns.value.length),
    ) &&
    neighbors.value >= 1 &&
    neighbors.value < (dataset.value?.row_count ?? 1),
)
const localPreviewColumns = computed(() => Object.keys(result.value?.gwr?.local_preview[0] ?? {}))

function detectColumn(columns: string[], candidates: string[]) {
  const normalizedCandidates = new Set(candidates.map((candidate) => candidate.toLowerCase()))
  return (
    columns.find((column) => normalizedCandidates.has(column.trim().toLowerCase())) ?? ''
  )
}

function detectCoordinateColumns(columns: string[]) {
  const longitude = detectColumn(columns, ['longitude', 'lon', 'lng', '经度'])
  const latitude = detectColumn(columns, ['latitude', 'lat', '纬度'])
  if (longitude && latitude) {
    coordinateType.value = 'geographic'
    xColumn.value = longitude
    yColumn.value = latitude
    return
  }

  const projectedX = detectColumn(columns, ['x', 'x_coord', 'x_coordinate', '投影x', '横坐标'])
  const projectedY = detectColumn(columns, ['y', 'y_coord', 'y_coordinate', '投影y', '纵坐标'])
  if (projectedX && projectedY) {
    coordinateType.value = 'projected'
    xColumn.value = projectedX
    yColumn.value = projectedY
  }
}

watch([selectedMethod, xColumn, yColumn, dependentColumn, coordinateType, neighbors], () => {
  result.value = null
  errorMessage.value = ''
  exportMessage.value = ''
  independentColumns.value = independentColumns.value.filter(
    (column) =>
      column !== dependentColumn.value && column !== xColumn.value && column !== yColumn.value,
  )
})

async function loadSelectedFile(file: File | undefined) {
  if (!file) return

  selectedFile.value = file
  dataset.value = null
  result.value = null
  xColumn.value = ''
  yColumn.value = ''
  dependentColumn.value = ''
  independentColumns.value = []
  errorMessage.value = ''
  isReading.value = true
  try {
    dataset.value = await previewFile(file)
    neighbors.value = Math.min(8, Math.max(1, dataset.value.row_count - 1))
    detectCoordinateColumns(numericColumns.value)
  } catch (error) {
    selectedFile.value = null
    errorMessage.value = error instanceof Error ? error.message : '读取字段失败。'
  } finally {
    isReading.value = false
  }
}

function onFileSelected(event: Event) {
  void loadSelectedFile((event.target as HTMLInputElement).files?.[0])
}

function onDrop(event: DragEvent) {
  void loadSelectedFile(event.dataTransfer?.files[0])
}

async function executeSpatialAnalysis() {
  if (!selectedFile.value || !canRun.value) return
  isRunning.value = true
  result.value = null
  errorMessage.value = ''
  try {
    result.value = await runSpatialAnalysis(selectedFile.value, currentOptions())
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '空间分析失败。'
  } finally {
    isRunning.value = false
  }
}

function currentOptions() {
  return {
    method: selectedMethod.value,
    coordinateType: coordinateType.value,
    xColumn: xColumn.value,
    yColumn: yColumn.value,
    dependentColumn: dependentColumn.value,
    independentColumns: isMoran.value ? [] : independentColumns.value,
    neighbors: neighbors.value,
  }
}

async function downloadSpatialResult(outputFormat: ExportFormat) {
  if (!selectedFile.value || !result.value) return
  exportingFormat.value = outputFormat
  errorMessage.value = ''
  exportMessage.value = ''
  try {
    const filename = await exportSpatialAnalysis(
      selectedFile.value,
      currentOptions(),
      outputFormat,
    )
    exportMessage.value = `已导出 ${filename}`
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '空间结果导出失败。'
  } finally {
    exportingFormat.value = ''
  }
}

function formatNumber(value: number | null | undefined) {
  if (value === null || value === undefined) return '—'
  if (value !== 0 && Math.abs(value) < 0.0001) return value.toExponential(3)
  return value.toFixed(6)
}

function moranInterpretation(value: number | null) {
  if (value === null) return '无法判断'
  if (value > 0) return '正空间自相关（相似值趋于聚集）'
  if (value < 0) return '负空间自相关（相异值趋于相邻）'
  return '接近随机空间分布'
}
</script>

<template>
  <section class="panel spatial-intro compact-upload-panel">
    <div class="section-heading">
      <div>
        <h2>空间分析</h2>
      </div>
      <p>支持经纬度或投影 X/Y 坐标，使用 K 近邻构建空间权重</p>
    </div>

    <label class="drop-zone compact-drop-zone" @dragover.prevent @drop.prevent="onDrop">
      <input type="file" accept=".csv,.xlsx" @change="onFileSelected" />
      <span class="upload-icon">↑</span>
      <strong>{{ isReading ? '正在读取字段…' : '点击选择或拖放空间数据' }}</strong>
    </label>
    <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>
  </section>

  <template v-if="dataset">
    <section class="panel">
      <div class="spatial-summary-tags">
        <span>{{ dataset.filename }}</span>
        <span>{{ dataset.row_count }} 行</span>
        <span>{{ numericColumns.length }} 个可用数值列</span>
      </div>

      <h3 class="spatial-section-title">1. 选择空间分析方法</h3>
      <div class="spatial-method-grid">
        <label v-for="method in methods" :key="method.value" class="spatial-method-card">
          <input v-model="selectedMethod" type="radio" :value="method.value" />
          <strong>{{ method.label }}</strong>
          <small>{{ method.description }}</small>
        </label>
      </div>

      <h3 class="spatial-section-title">2. 设置坐标与空间权重</h3>
      <div class="coordinate-type-picker">
        <label>
          <input v-model="coordinateType" type="radio" value="geographic" />
          经纬度（WGS84）
        </label>
        <label>
          <input v-model="coordinateType" type="radio" value="projected" />
          投影坐标 X / Y
        </label>
      </div>

      <div class="spatial-variable-grid">
        <label>
          <span>{{ coordinateType === 'geographic' ? '经度列' : 'X 坐标列' }}</span>
          <select v-model="xColumn">
            <option value="" disabled>请选择数值列</option>
            <option v-for="column in numericColumns" :key="column" :value="column">{{ column }}</option>
          </select>
        </label>
        <label>
          <span>{{ coordinateType === 'geographic' ? '纬度列' : 'Y 坐标列' }}</span>
          <select v-model="yColumn">
            <option value="" disabled>请选择数值列</option>
            <option v-for="column in numericColumns" :key="column" :value="column">{{ column }}</option>
          </select>
        </label>
        <label>
          <span>K 近邻数</span>
          <input v-model.number="neighbors" type="number" min="1" :max="dataset.row_count - 1" />
          <small>默认 8；每个观测连接最近的 K 个观测</small>
        </label>
      </div>

      <h3 class="spatial-section-title">3. 选择分析变量</h3>
      <div class="spatial-variable-grid">
        <label>
          <span>{{ isMoran ? '空间自相关变量' : '因变量 Y' }}</span>
          <select v-model="dependentColumn">
            <option value="" disabled>请选择数值列</option>
            <option v-for="column in numericColumns" :key="column" :value="column">{{ column }}</option>
          </select>
        </label>

        <div v-if="!isMoran" class="spatial-independent-selector">
          <span>自变量 X（可多选）</span>
          <div>
            <label v-for="column in availableIndependentColumns" :key="column">
              <input v-model="independentColumns" type="checkbox" :value="column" />
              {{ column }}
            </label>
          </div>
        </div>
      </div>

      <p class="spatial-note">
        缺失坐标或模型变量的行会被排除。经纬度按球面邻近关系处理；投影坐标按平面距离处理。
      </p>
      <button class="primary-action" :disabled="isRunning || !canRun" @click="executeSpatialAnalysis">
        {{ isRunning ? (selectedMethod === 'gwr' ? '正在选择带宽并拟合…' : '正在计算…') : '运行空间分析' }}
      </button>
    </section>

    <section v-if="result" class="panel spatial-result">
      <div class="section-heading">
        <div>
          <p class="step-label">SPATIAL RESULT</p>
          <h2>空间分析结果</h2>
        </div>
        <p>有效样本 {{ result.observations }}，排除缺失行 {{ result.dropped_rows }}</p>
      </div>

      <div
        class="spatial-diagnostics"
        :class="{ invalid: !result.diagnostics.valid_inference }"
      >
        <div class="spatial-diagnostics-heading">
          <div>
            <strong>
              {{ result.diagnostics.valid_inference ? '模型推断有效' : '模型推断不可靠' }}
            </strong>
            <small>
              {{ result.diagnostics.converged ? '计算已正常完成' : '模型未收敛' }}
            </small>
          </div>
          <div class="spatial-diagnostic-values">
            <span v-if="result.diagnostics.condition_number !== null">
              标准化条件数 {{ formatNumber(result.diagnostics.condition_number) }}
            </span>
            <span v-if="result.diagnostics.raw_condition_number !== null">
              原始条件数 {{ formatNumber(result.diagnostics.raw_condition_number) }}
            </span>
            <span v-if="result.diagnostics.max_vif !== null">
              最大 VIF {{ formatNumber(result.diagnostics.max_vif) }}
            </span>
            <span v-if="result.diagnostics.scale_ratio !== null">
              尺度比 {{ formatNumber(result.diagnostics.scale_ratio) }}
            </span>
          </div>
        </div>
        <ul v-if="result.diagnostics.warnings.length">
          <li v-for="warning in result.diagnostics.warnings" :key="warning">{{ warning }}</li>
        </ul>
        <p v-else>未检测到收敛、非有限数值、重复坐标或明显共线性问题。</p>
        <details v-if="result.diagnostics.vif.length">
          <summary>查看各变量 VIF</summary>
          <div class="spatial-vif-list">
            <span v-for="item in result.diagnostics.vif" :key="item.column">
              {{ item.column }}：{{ formatNumber(item.vif) }}
            </span>
          </div>
        </details>
      </div>

      <div class="spatial-summary-tags weight-summary">
        <span>KNN：{{ result.weights.neighbors }} 个邻居</span>
        <span>行标准化权重</span>
        <span>连通分量：{{ result.weights.components }}</span>
      </div>

      <div v-if="result.moran" class="spatial-metric-grid">
        <article><span>Moran's I</span><strong>{{ formatNumber(result.moran.i) }}</strong></article>
        <article><span>期望值</span><strong>{{ formatNumber(result.moran.expected_i) }}</strong></article>
        <article><span>Z 值</span><strong>{{ formatNumber(result.moran.z_score) }}</strong></article>
        <article><span>置换检验 p 值</span><strong>{{ formatNumber(result.moran.p_permutation) }}</strong></article>
        <p class="moran-interpretation">{{ moranInterpretation(result.moran.i) }}</p>
      </div>

      <template v-if="result.regression">
        <div class="spatial-metric-grid">
          <article><span>伪 R²</span><strong>{{ formatNumber(result.regression.metrics.pseudo_r_squared) }}</strong></article>
          <article><span>AIC</span><strong>{{ formatNumber(result.regression.metrics.aic) }}</strong></article>
          <article><span>BIC</span><strong>{{ formatNumber(result.regression.metrics.bic) }}</strong></article>
          <article v-if="result.regression.metrics.rho !== null"><span>ρ（空间滞后）</span><strong>{{ formatNumber(result.regression.metrics.rho) }}</strong></article>
          <article v-if="result.regression.metrics.lambda !== null"><span>λ（空间误差）</span><strong>{{ formatNumber(result.regression.metrics.lambda) }}</strong></article>
        </div>
        <div class="quality-table-wrap">
          <table class="quality-table">
            <thead><tr><th>变量</th><th>系数</th><th>标准误</th><th>Z 值</th><th>p 值</th><th>95% 置信区间</th></tr></thead>
            <tbody>
              <tr v-for="coefficient in result.regression.coefficients" :key="coefficient.term">
                <td class="column-name">{{ coefficient.term }}</td>
                <td>{{ formatNumber(coefficient.estimate) }}</td>
                <td>{{ formatNumber(coefficient.standard_error) }}</td>
                <td>{{ formatNumber(coefficient.statistic) }}</td>
                <td>{{ formatNumber(coefficient.p_value) }}</td>
                <td>{{ formatNumber(coefficient.confidence_low) }} ～ {{ formatNumber(coefficient.confidence_high) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <template v-if="result.regression.spatial_impacts.length">
          <h3 class="spatial-subheading">空间效应分解</h3>
          <p class="spatial-result-note">
            直接效应表示本地影响，间接效应表示经空间邻居传播的溢出影响，总效应为两者之和。
          </p>
          <div class="quality-table-wrap">
            <table class="quality-table">
              <thead>
                <tr><th>变量</th><th>直接效应</th><th>间接效应</th><th>总效应</th></tr>
              </thead>
              <tbody>
                <tr v-for="impact in result.regression.spatial_impacts" :key="impact.term">
                  <td class="column-name">{{ impact.term }}</td>
                  <td>{{ formatNumber(impact.direct) }}</td>
                  <td>{{ formatNumber(impact.indirect) }}</td>
                  <td>{{ formatNumber(impact.total) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </template>

      <template v-if="result.gwr">
        <div class="spatial-metric-grid">
          <article><span>自适应带宽</span><strong>{{ formatNumber(result.gwr.bandwidth) }}</strong></article>
          <article><span>R²</span><strong>{{ formatNumber(result.gwr.metrics.r_squared) }}</strong></article>
          <article><span>调整 R²</span><strong>{{ formatNumber(result.gwr.metrics.adjusted_r_squared) }}</strong></article>
          <article><span>AICc</span><strong>{{ formatNumber(result.gwr.metrics.aicc) }}</strong></article>
        </div>
        <h3>局部系数分布</h3>
        <div class="quality-table-wrap">
          <table class="quality-table">
            <thead><tr><th>变量</th><th>均值</th><th>标准差</th><th>最小值</th><th>中位数</th><th>最大值</th></tr></thead>
            <tbody>
              <tr v-for="coefficient in result.gwr.coefficient_summaries" :key="coefficient.term">
                <td class="column-name">{{ coefficient.term }}</td>
                <td>{{ formatNumber(coefficient.mean) }}</td>
                <td>{{ formatNumber(coefficient.standard_deviation) }}</td>
                <td>{{ formatNumber(coefficient.minimum) }}</td>
                <td>{{ formatNumber(coefficient.median) }}</td>
                <td>{{ formatNumber(coefficient.maximum) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <h3 class="local-preview-heading">局部结果预览（前 {{ result.gwr.local_preview.length }} 行）</h3>
        <div class="quality-table-wrap">
          <table class="quality-table">
            <thead><tr><th v-for="column in localPreviewColumns" :key="column">{{ column }}</th></tr></thead>
            <tbody>
              <tr v-for="(row, index) in result.gwr.local_preview" :key="index">
                <td v-for="column in localPreviewColumns" :key="column">{{ formatNumber(row[column]) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <template v-if="result.residual_moran">
        <h3 class="spatial-subheading">当前模型残差 Moran</h3>
        <div class="spatial-metric-grid">
          <article>
            <span>残差 Moran's I</span>
            <strong>{{ formatNumber(result.residual_moran.i) }}</strong>
          </article>
          <article>
            <span>Z 值</span>
            <strong>{{ formatNumber(result.residual_moran.z_score) }}</strong>
          </article>
          <article>
            <span>置换检验 p 值</span>
            <strong>{{ formatNumber(result.residual_moran.p_permutation) }}</strong>
          </article>
        </div>
        <p
          class="residual-interpretation"
          :class="{ warning: (result.residual_moran.p_permutation ?? 1) < 0.05 }"
        >
          {{
            (result.residual_moran.p_permutation ?? 1) < 0.05
              ? '残差仍存在显著空间自相关，当前模型可能尚未充分解释空间结构。'
              : '残差 Moran 未达到 0.05 显著水平，未发现明显的剩余空间自相关。'
          }}
        </p>
      </template>

      <template v-if="result.model_selection">
        <h3 class="spatial-subheading">空间模型选择诊断</h3>
        <p class="model-recommendation">{{ result.model_selection.recommendation }}</p>
        <div class="quality-table-wrap">
          <table class="quality-table">
            <thead><tr><th>检验</th><th>统计量</th><th>p 值</th><th>判断</th></tr></thead>
            <tbody>
              <tr v-for="test in result.model_selection.tests" :key="test.name">
                <td class="column-name">{{ test.name }}</td>
                <td>{{ formatNumber(test.statistic) }}</td>
                <td>{{ formatNumber(test.p_value) }}</td>
                <td>{{ (test.p_value ?? 1) < 0.05 ? '显著' : '不显著' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="spatial-result-note">
          模型选择提示以基础 OLS 的稳健 LM 检验为主；还应结合研究理论、空间权重敏感性和模型拟合指标。
        </p>
        <ul v-if="result.model_selection.warnings.length" class="selection-warnings">
          <li v-for="warning in result.model_selection.warnings" :key="warning">
            诊断运行警告：{{ warning }}
          </li>
        </ul>
      </template>

      <p class="spatial-disclaimer">
        空间模型结果依赖坐标系统、空间权重与邻居数设定。正式结论应比较不同 K 值，并检查残差空间自相关和模型假设。
      </p>

      <div class="export-panel spatial-export-panel">
        <div>
          <h3>导出空间分析结果</h3>
          <p v-if="result.gwr">
            GWR 导出会重新拟合模型，并写入全部 {{ result.gwr.local_result_count }} 行局部结果。
            局部 p_value_unadjusted 为根据 t 值计算、未经多重检验校正的双侧近似 p 值。
          </p>
          <p v-else>XLSX 同时包含模型概览、诊断、VIF 和结果明细。</p>
        </div>
        <div class="export-actions">
          <button :disabled="!!exportingFormat" @click="downloadSpatialResult('csv')">
            {{ exportingFormat === 'csv' ? '导出中…' : '导出 CSV' }}
          </button>
          <button
            class="xlsx-button"
            :disabled="!!exportingFormat"
            @click="downloadSpatialResult('xlsx')"
          >
            {{ exportingFormat === 'xlsx' ? '导出中…' : '导出 XLSX' }}
          </button>
        </div>
        <p v-if="exportMessage" class="export-message">{{ exportMessage }}</p>
      </div>
    </section>
  </template>
</template>

<style scoped>
.spatial-summary-tags, .coordinate-type-picker, .spatial-metric-grid { display: flex; flex-wrap: wrap; gap: 10px; }
.spatial-summary-tags span { padding: 7px 10px; border-radius: 8px; background: #e9f1f4; font-size: .8rem; font-weight: 700; }
.spatial-section-title { margin: 26px 0 14px; }
.spatial-method-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 9px; }
.spatial-method-card { display: grid; grid-template-columns: auto 1fr; align-content: start; align-items: center; column-gap: 8px; min-height: 104px; padding: 14px; border: 1px solid #d8e1e5; border-radius: 12px; background: #fafcfd; cursor: pointer; }
.spatial-method-card:has(input:checked) { border-color: #3d7186; background: #eaf4f8; }
.spatial-method-card input, .coordinate-type-picker input { accent-color: #32677d; }
.spatial-method-card strong, .spatial-method-card small { display: block; }
.spatial-method-card strong { margin: 0; }
.spatial-method-card small { grid-column: 1 / -1; margin-top: 8px; color: #6d7d84; line-height: 1.35; }
.coordinate-type-picker label { padding: 10px 13px; border-radius: 9px; background: #eef3f5; cursor: pointer; }
.spatial-variable-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin: 16px 0 22px; }
.spatial-variable-grid > label > span, .spatial-independent-selector > span { display: block; margin-bottom: 8px; font-size: .8rem; font-weight: 800; }
.spatial-variable-grid select, .spatial-variable-grid input[type='number'] { width: 100%; padding: 11px; border: 1px solid #cad7dc; border-radius: 9px; color: #24363d; background: white; }
.spatial-variable-grid small { display: block; margin-top: 6px; color: #74838a; }
.spatial-independent-selector { grid-column: span 2; }
.spatial-independent-selector > div { display: flex; flex-wrap: wrap; gap: 7px; }
.spatial-independent-selector label { padding: 9px 11px; border-radius: 8px; background: #eef3f5; cursor: pointer; }
.spatial-note, .spatial-disclaimer { margin: 16px 0; padding: 12px; border-radius: 9px; color: #635f55; background: #f7f3e7; font-size: .8rem; }
.weight-summary { margin-bottom: 18px; }
.spatial-metric-grid article { min-width: 155px; padding: 17px; border-radius: 12px; background: #edf4f6; }
.spatial-metric-grid article span, .spatial-metric-grid article strong { display: block; }
.spatial-metric-grid article strong { margin-top: 7px; font-size: 1.3rem; }
.moran-interpretation { width: 100%; font-weight: 700; color: #3d6271; }
.local-preview-heading { margin-top: 24px; }
.spatial-disclaimer { margin-top: 20px; }
.spatial-subheading { margin: 24px 0 10px; }
.spatial-result-note { color: #68777d; font-size: .8rem; }
.residual-interpretation, .model-recommendation { padding: 11px 13px; border-radius: 9px; background: #edf6ef; font-weight: 700; }
.residual-interpretation.warning { color: #8c3e34; background: #fff0ed; }
.model-recommendation { color: #345e70; background: #eaf4f8; }
.selection-warnings { color: #8c5b24; font-size: .78rem; }
.spatial-export-panel { margin-top: 18px; }
.spatial-diagnostics { margin-bottom: 18px; padding: 16px; border: 1px solid #b6d3dc; border-radius: 11px; background: #edf7fa; }
.spatial-diagnostics.invalid { border-color: #e1a39b; background: #fff0ed; }
.spatial-diagnostics-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.spatial-diagnostics-heading strong, .spatial-diagnostics-heading small { display: block; }
.spatial-diagnostics-heading small { margin-top: 4px; color: #64757c; }
.spatial-diagnostic-values, .spatial-vif-list { display: flex; flex-wrap: wrap; gap: 7px; }
.spatial-diagnostic-values span, .spatial-vif-list span { padding: 6px 9px; border-radius: 7px; background: rgb(255 255 255 / 72%); font-size: .76rem; font-weight: 700; }
.spatial-diagnostics ul { margin-bottom: 8px; padding-left: 20px; }
.spatial-diagnostics li + li { margin-top: 6px; }
.spatial-diagnostics details { margin-top: 10px; }
.spatial-diagnostics summary { cursor: pointer; font-weight: 700; }
.spatial-vif-list { margin-top: 10px; }

@media (max-width: 900px) {
  .spatial-method-grid { grid-template-columns: repeat(2, 1fr); }
  .spatial-variable-grid { grid-template-columns: 1fr 1fr; }
}

@media (max-width: 640px) {
  .spatial-variable-grid { grid-template-columns: 1fr; }
  .spatial-independent-selector { grid-column: auto; }
}
</style>
