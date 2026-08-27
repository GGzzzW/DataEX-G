<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

import {
  exportGwrf,
  optimizeGwrfBandwidth,
  optimizeGwrfParameters,
  previewFile,
  runGwrf,
} from '@/services/api'
import type {
  CoordinateType,
  ExportFormat,
  FilePreviewResponse,
  GwrfBandwidthOptimizationResponse,
  GwrfFitMethod,
  GwrfOptions,
  GwrfParameterOptimizationResponse,
  GwrfResponse,
} from '@/types/analysis'

const selectedFile = ref<File | null>(null)
const dataset = ref<FilePreviewResponse | null>(null)
const coordinateType = ref<CoordinateType>('geographic')
const xColumn = ref('')
const yColumn = ref('')
const dependentColumn = ref('')
const independentColumns = ref<string[]>([])
const bandwidth = ref<number | null>(null)
const fitMethod = ref<GwrfFitMethod>('in_sample')
const nEstimators = ref(200)
const maxDepth = ref(10)
const unlimitedDepth = ref(false)
const minSamplesSplit = ref(5)
const parameterMode = ref<'manual' | 'automatic'>('automatic')
const parameterOptimization = ref<GwrfParameterOptimizationResponse | null>(null)
const bandwidthCandidatesText = ref('')
const bandwidthOptimization = ref<GwrfBandwidthOptimizationResponse | null>(null)
const calculateShap = ref(false)
const calculateShapInteractions = ref(false)
const shapInteractionColumns = ref<string[]>([])
const result = ref<GwrfResponse | null>(null)
const errorMessage = ref('')
const exportMessage = ref('')
const isReading = ref(false)
const isOptimizingParameters = ref(false)
const isOptimizingBandwidth = ref(false)
const isRunning = ref(false)
const exportingFormat = ref<ExportFormat | ''>('')

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
const availableIndependentColumns = computed(() =>
  numericColumns.value.filter(
    (column) =>
      column !== dependentColumn.value && column !== xColumn.value && column !== yColumn.value,
  ),
)
const maximumBandwidth = computed(() => {
  const count = dataset.value?.row_count ?? 3
  return fitMethod.value === 'loocv' ? Math.max(3, count - 1) : Math.max(3, count)
})
const bandwidthCandidates = computed(() => {
  const tokens = bandwidthCandidatesText.value
    .trim()
    .split(/[,，\s]+/)
    .filter(Boolean)
  if (!tokens.length) return []
  const values = tokens.map(Number)
  if (values.some((value) => !Number.isInteger(value))) return []
  return [...new Set(values)]
})
const validBandwidthCandidates = computed(
  () =>
    bandwidthCandidates.value.length > 0 &&
    bandwidthCandidates.value.every(
      (candidate) =>
        candidate >= Math.max(3, minSamplesSplit.value) &&
        candidate < (dataset.value?.row_count ?? 1),
    ),
)
const parametersReady = computed(
  () => parameterMode.value === 'manual' || parameterOptimization.value !== null,
)
const validFinalBandwidth = computed(
  () =>
    typeof bandwidth.value === 'number' &&
    bandwidth.value >= 3 &&
    bandwidth.value <= maximumBandwidth.value &&
    minSamplesSplit.value <= bandwidth.value,
)
const canOptimizeParameters = computed(() =>
  Boolean(selectedFile.value && dependentColumn.value && independentColumns.value.length),
)
const canOptimizeBandwidth = computed(
  () =>
    Boolean(
      selectedFile.value &&
        xColumn.value &&
        yColumn.value &&
        xColumn.value !== yColumn.value &&
        dependentColumn.value &&
        independentColumns.value.length,
    ) &&
    parametersReady.value &&
    validBandwidthCandidates.value &&
    !isOptimizingParameters.value,
)
const canRun = computed(
  () =>
    Boolean(
      selectedFile.value &&
      xColumn.value &&
      yColumn.value &&
      xColumn.value !== yColumn.value &&
      dependentColumn.value &&
      independentColumns.value.length,
    ) &&
    parametersReady.value &&
    !isOptimizingParameters.value &&
    validFinalBandwidth.value &&
    nEstimators.value >= 10 &&
    minSamplesSplit.value >= 2 &&
    (!calculateShapInteractions.value || shapInteractionColumns.value.length >= 2),
)
const localColumns = computed(() => Object.keys(result.value?.local_preview[0] ?? {}))
const maximumImportance = computed(() =>
  Math.max(
    ...(result.value?.importance_summary.map((item) => item.relative_importance ?? 0) ?? [0]),
  ),
)

function detectColumn(columns: string[], candidates: string[]) {
  const normalized = new Set(candidates.map((candidate) => candidate.toLowerCase()))
  return columns.find((column) => normalized.has(column.trim().toLowerCase())) ?? ''
}

function detectCoordinates(columns: string[]) {
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

watch(
  [
    coordinateType,
    xColumn,
    yColumn,
    dependentColumn,
    bandwidth,
    fitMethod,
    nEstimators,
    maxDepth,
    unlimitedDepth,
    minSamplesSplit,
    bandwidthCandidatesText,
    calculateShap,
    calculateShapInteractions,
    shapInteractionColumns,
  ],
  () => {
    result.value = null
    exportMessage.value = ''
    const validIndependentColumns = independentColumns.value.filter((column) =>
      availableIndependentColumns.value.includes(column),
    )
    if (
      validIndependentColumns.length !== independentColumns.value.length ||
      validIndependentColumns.some((column, index) => column !== independentColumns.value[index])
    ) {
      independentColumns.value = validIndependentColumns
    }
    if (typeof bandwidth.value === 'number' && bandwidth.value > maximumBandwidth.value) {
      bandwidth.value = maximumBandwidth.value
    }
  },
)

watch(
  independentColumns,
  () => {
    result.value = null
    exportMessage.value = ''
    parameterOptimization.value = null
    bandwidthOptimization.value = null
    shapInteractionColumns.value = shapInteractionColumns.value.filter((column) =>
      independentColumns.value.includes(column),
    )
  },
  { deep: true },
)

watch(dependentColumn, () => {
  parameterOptimization.value = null
  bandwidthOptimization.value = null
})

watch(
  [
    coordinateType,
    xColumn,
    yColumn,
    bandwidthCandidatesText,
    nEstimators,
    maxDepth,
    unlimitedDepth,
    minSamplesSplit,
  ],
  () => {
    bandwidthOptimization.value = null
  },
)

watch(calculateShap, (enabled) => {
  if (!enabled) {
    calculateShapInteractions.value = false
    shapInteractionColumns.value = []
  }
})

watch(calculateShapInteractions, (enabled) => {
  if (!enabled) shapInteractionColumns.value = []
})

async function loadSelectedFile(file: File | undefined) {
  if (!file) return
  selectedFile.value = file
  dataset.value = null
  result.value = null
  independentColumns.value = []
  shapInteractionColumns.value = []
  parameterOptimization.value = null
  bandwidthOptimization.value = null
  dependentColumn.value = ''
  xColumn.value = ''
  yColumn.value = ''
  bandwidth.value = null
  bandwidthCandidatesText.value = ''
  errorMessage.value = ''
  isReading.value = true
  try {
    dataset.value = await previewFile(file)
    detectCoordinates(numericColumns.value)
  } catch (error) {
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

function currentOptions(): GwrfOptions {
  return {
    coordinateType: coordinateType.value,
    xColumn: xColumn.value,
    yColumn: yColumn.value,
    dependentColumn: dependentColumn.value,
    independentColumns: independentColumns.value,
    bandwidth:
      typeof bandwidth.value === 'number' ? bandwidth.value : Math.max(3, minSamplesSplit.value),
    fitMethod: fitMethod.value,
    nEstimators: nEstimators.value,
    maxDepth: unlimitedDepth.value ? null : maxDepth.value,
    minSamplesSplit: minSamplesSplit.value,
    optimizeParameters: false,
    optimizeBandwidth: false,
    bandwidthCandidates: bandwidthCandidates.value,
    calculateShap: calculateShap.value,
    calculateShapInteractions: calculateShapInteractions.value,
    shapInteractionColumns: shapInteractionColumns.value,
  }
}

async function executeBandwidthOptimization() {
  if (!selectedFile.value || !canOptimizeBandwidth.value) return
  isOptimizingBandwidth.value = true
  bandwidthOptimization.value = null
  result.value = null
  errorMessage.value = ''
  try {
    const optimized = await optimizeGwrfBandwidth(selectedFile.value, currentOptions())
    bandwidth.value = optimized.best_bandwidth
    await nextTick()
    bandwidthOptimization.value = optimized
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '带宽寻优失败。'
  } finally {
    isOptimizingBandwidth.value = false
  }
}

async function executeParameterOptimization() {
  if (!selectedFile.value || !canOptimizeParameters.value) return
  isOptimizingParameters.value = true
  parameterOptimization.value = null
  result.value = null
  errorMessage.value = ''
  try {
    const optimized = await optimizeGwrfParameters(
      selectedFile.value,
      dependentColumn.value,
      independentColumns.value,
    )
    parameterOptimization.value = optimized
    nEstimators.value = optimized.best_parameters.n_estimators
    minSamplesSplit.value = optimized.best_parameters.min_samples_split
    unlimitedDepth.value = optimized.best_parameters.max_depth === null
    if (optimized.best_parameters.max_depth !== null) {
      maxDepth.value = optimized.best_parameters.max_depth
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '随机森林参数寻优失败。'
  } finally {
    isOptimizingParameters.value = false
  }
}

async function executeGwrf() {
  if (!selectedFile.value || !canRun.value) return
  isRunning.value = true
  errorMessage.value = ''
  result.value = null
  try {
    result.value = await runGwrf(selectedFile.value, currentOptions())
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'GWRF 拟合失败。'
  } finally {
    isRunning.value = false
  }
}

async function downloadResult(format: ExportFormat) {
  if (!selectedFile.value || !result.value) return
  exportingFormat.value = format
  errorMessage.value = ''
  try {
    const filename = await exportGwrf(selectedFile.value, currentOptions(), format)
    exportMessage.value = `已导出 ${filename}`
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'GWRF 结果导出失败。'
  } finally {
    exportingFormat.value = ''
  }
}

function formatNumber(value: number | null | undefined) {
  if (value === null || value === undefined) return '—'
  if (value !== 0 && Math.abs(value) < 0.0001) return value.toExponential(3)
  return value.toFixed(6)
}

function importanceWidth(value: number | null) {
  if (!value || maximumImportance.value <= 0) return '0%'
  return `${(value / maximumImportance.value) * 100}%`
}
</script>

<template>
  <section class="panel gwrf-intro compact-upload-panel">
    <div class="section-heading">
      <div>
        <h2>地理加权随机森林</h2>
      </div>
      <p>局部随机森林、双平方核权重、SHAP 解释与残差空间检验</p>
    </div>
    <label class="drop-zone compact-drop-zone" @dragover.prevent @drop.prevent="onDrop">
      <input type="file" accept=".csv,.xlsx" @change="onFileSelected" />
      <span class="upload-icon">↑</span>
      <strong>{{ isReading ? '正在读取字段…' : '点击选择或拖放 GWRF 数据' }}</strong>
    </label>
    <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>
  </section>

  <template v-if="dataset">
    <section class="panel gwrf-settings">
      <div class="gwrf-tags">
        <span>{{ dataset.filename }}</span>
        <span>{{ dataset.row_count }} 行</span>
        <span>{{ numericColumns.length }} 个可用数值列</span>
      </div>

      <h3>1. 设置坐标和分析变量</h3>
      <div class="coordinate-type-picker">
        <label><input v-model="coordinateType" type="radio" value="geographic" /> 经纬度</label>
        <label><input v-model="coordinateType" type="radio" value="projected" /> 投影坐标</label>
      </div>
      <div class="gwrf-variable-grid">
        <label>
          <span>{{ coordinateType === 'geographic' ? '经度字段' : 'X 坐标字段' }}</span>
          <select v-model="xColumn">
            <option value="">请选择</option>
            <option v-for="column in numericColumns" :key="column" :value="column">
              {{ column }}
            </option>
          </select>
        </label>
        <label>
          <span>{{ coordinateType === 'geographic' ? '纬度字段' : 'Y 坐标字段' }}</span>
          <select v-model="yColumn">
            <option value="">请选择</option>
            <option v-for="column in numericColumns" :key="column" :value="column">
              {{ column }}
            </option>
          </select>
        </label>
        <label>
          <span>因变量</span>
          <select v-model="dependentColumn">
            <option value="">请选择</option>
            <option v-for="column in numericColumns" :key="column" :value="column">
              {{ column }}
            </option>
          </select>
        </label>
      </div>
      <div class="gwrf-independent-selector">
        <span>自变量（框选一个或多个）</span>
        <div>
          <label v-for="column in availableIndependentColumns" :key="column">
            <input v-model="independentColumns" type="checkbox" :value="column" /> {{ column }}
          </label>
        </div>
      </div>

      <h3>2. 确定随机森林参数</h3>
      <div class="gwrf-method-grid parameter-mode-grid">
        <label :class="{ selected: parameterMode === 'manual' }">
          <input v-model="parameterMode" type="radio" value="manual" />
          <strong>直接填写模型参数</strong>
          <small>直接填写决策树数量、最大树深和最小分裂样本数。</small>
        </label>
        <label :class="{ selected: parameterMode === 'automatic' }">
          <input v-model="parameterMode" type="radio" value="automatic" />
          <strong>自动参数寻优</strong>
          <small>先运行三折 GridSearchCV，确认最优参数后再进入最终模型。</small>
        </label>
      </div>
      <div class="gwrf-parameter-grid rf-parameter-grid">
        <label
          ><span>决策树数量</span
          ><input
            v-model.number="nEstimators"
            type="number"
            min="10"
            max="2000"
            step="10"
            :disabled="parameterMode === 'automatic' && !parameterOptimization"
        /></label>
        <label
          ><span>最大树深</span
          ><input
            v-model.number="maxDepth"
            type="number"
            min="1"
            max="200"
            :disabled="unlimitedDepth || (parameterMode === 'automatic' && !parameterOptimization)"
        /></label>
        <label
          ><span>最小分裂样本数</span
          ><input
            v-model.number="minSamplesSplit"
            type="number"
            min="2"
            :disabled="parameterMode === 'automatic' && !parameterOptimization"
        /></label>
      </div>
      <div class="gwrf-switches">
        <label>
          <input
            v-model="unlimitedDepth"
            type="checkbox"
            :disabled="parameterMode === 'automatic' && !parameterOptimization"
          />
          最大树深不限制
        </label>
      </div>
      <template v-if="parameterMode === 'automatic'">
        <button
          class="parameter-action"
          :disabled="!canOptimizeParameters || isOptimizingParameters"
          @click="executeParameterOptimization"
        >
          {{ isOptimizingParameters ? '正在执行 12 组参数的三折交叉验证…' : '开始参数寻优' }}
        </button>
        <div v-if="parameterOptimization" class="parameter-result">
          <strong>参数寻优完成，可以继续运行最终模型</strong>
          <span>决策树 {{ parameterOptimization.best_parameters.n_estimators }}</span>
          <span>最大树深 {{ parameterOptimization.best_parameters.max_depth ?? '不限制' }}</span>
          <span>最小分裂样本 {{ parameterOptimization.best_parameters.min_samples_split }}</span>
          <details>
            <summary>查看全部参数组合</summary>
            <div class="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>排名</th>
                    <th>决策树</th>
                    <th>最大深度</th>
                    <th>最小分裂</th>
                    <th>CV RMSE</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="item in parameterOptimization.search_results"
                    :key="`${item.n_estimators}-${item.max_depth}-${item.min_samples_split}`"
                  >
                    <td>{{ item.rank }}</td>
                    <td>{{ item.n_estimators }}</td>
                    <td>{{ item.max_depth ?? '不限制' }}</td>
                    <td>{{ item.min_samples_split }}</td>
                    <td>{{ formatNumber(item.cv_rmse) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </details>
        </div>
      </template>

      <h3>3. 选择最终拟合与评估方法</h3>
      <div class="gwrf-method-grid">
        <label :class="{ selected: fitMethod === 'in_sample' }">
          <input v-model="fitMethod" type="radio" value="in_sample" />
          <strong>样本内拟合</strong>
          <small>目标点参与其局部模型训练，R² 表示样本内伪 R²。</small>
        </label>
        <label :class="{ selected: fitMethod === 'loocv' }">
          <input v-model="fitMethod" type="radio" value="loocv" />
          <strong>LOOCV</strong>
          <small>每个局部模型排除目标点，R² 更接近样本外预测能力。</small>
        </label>
      </div>

      <h3>4. 寻找最优带宽</h3>
      <div class="gwrf-parameter-grid">
        <label class="bandwidth-candidates"
          ><span>候选带宽 K（逗号分隔）</span
          ><input
            v-model="bandwidthCandidatesText"
            type="text"
            placeholder="建议根据单元数量等差的设置带宽"
        /></label>
      </div>
      <button
        class="parameter-action"
        :disabled="!canOptimizeBandwidth || isOptimizingBandwidth"
        @click="executeBandwidthOptimization"
      >
        {{ isOptimizingBandwidth ? '正在逐个比较候选带宽…' : '开始带宽寻优' }}
      </button>
      <div v-if="bandwidthOptimization" class="parameter-result bandwidth-optimization-result">
        <strong>带宽寻优完成，最优带宽已回填到下一步</strong>
        <span>最优 K：{{ bandwidthOptimization.best_bandwidth }}</span>
        <span>完整观测：{{ bandwidthOptimization.observations }}</span>
        <div class="table-scroll">
          <table>
            <thead><tr><th>候选 K</th><th>LOOCV RMSE</th><th>耗时（秒）</th><th>结果</th></tr></thead>
            <tbody>
              <tr v-for="item in bandwidthOptimization.search_results" :key="item.bandwidth">
                <td>{{ item.bandwidth }}</td><td>{{ formatNumber(item.loocv_rmse) }}</td><td>{{ item.elapsed_seconds.toFixed(3) }}</td><td>{{ item.bandwidth === bandwidthOptimization.best_bandwidth ? '最优带宽' : '' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <h3>5. 确认唯一带宽并设置最终模型</h3>
      <div class="gwrf-parameter-grid final-bandwidth-grid">
        <label>
          <input
            v-model.number="bandwidth"
            type="number"
            min="3"
            :max="maximumBandwidth"
            placeholder="输入最终带宽"
          />
        </label>
      </div>
      <p class="gwrf-note">
        带宽寻优完成后会自动填入最优 K；你也可以修改该值。最终模型只使用这里确认的唯一带宽，不会重复运行带宽搜索。
      </p>

      <h3>6. 可选 SHAP 解释</h3>
      <div class="gwrf-switches shap-switches">
        <label><input v-model="calculateShap" type="checkbox" /> 计算局部 SHAP 值</label>
        <label :class="{ disabled: !calculateShap }">
          <input v-model="calculateShapInteractions" type="checkbox" :disabled="!calculateShap" />
          计算 SHAP 交互效应
        </label>
      </div>
      <div
        class="shap-interaction-selector"
        :class="{ active: calculateShap && calculateShapInteractions }"
      >
        <span>交互效应变量（至少选择两个，只计算所选变量之间的两两交互）</span>
        <div>
          <label v-for="column in independentColumns" :key="column">
            <input
              v-model="shapInteractionColumns"
              type="checkbox"
              :value="column"
              :disabled="!calculateShap || !calculateShapInteractions"
            />
            {{ column }}
          </label>
        </div>
      </div>
      <p
        v-if="calculateShapInteractions && shapInteractionColumns.length < 2"
        class="interaction-validation"
      >
        请至少选择两个交互变量。
      </p>
      <p class="gwrf-note">
        最终模型将使用上一步确认的唯一带宽，并按上面的选择决定是否计算
        SHAP。SHAP 与交互效应不会参与带宽寻优。
      </p>
      <button class="primary-action" :disabled="!canRun || isRunning" @click="executeGwrf">
        {{
          isRunning
            ? '正在计算最终模型…'
            : parametersReady
              ? '使用确认带宽运行最终 GWRF'
              : '请先完成随机森林参数寻优'
        }}
      </button>
    </section>

    <section v-if="result" class="panel gwrf-result">
      <div class="section-heading">
        <div>
          <p class="step-label">RESULT</p>
          <h2>GWRF 结果</h2>
        </div>
        <p>
          {{ result.fit_method === 'in_sample' ? '样本内拟合' : 'LOOCV' }} · 带宽
          {{ result.bandwidth }}
        </p>
      </div>
      <div class="gwrf-metric-grid">
        <article>
          <span>伪 R²</span><strong>{{ formatNumber(result.metrics.pseudo_r_squared) }}</strong>
        </article>
        <article>
          <span>RMSE</span><strong>{{ formatNumber(result.metrics.rmse) }}</strong>
        </article>
        <article>
          <span>残差 Moran's I</span><strong>{{ formatNumber(result.residual_moran.i) }}</strong
          ><small>模拟 p={{ formatNumber(result.residual_moran.p_permutation) }}</small>
        </article>
        <article>
          <span>完整观测</span><strong>{{ result.observations }}</strong
          ><small>剔除 {{ result.dropped_rows }} 行</small>
        </article>
      </div>
      <div class="gwrf-tags result-capabilities">
        <span>{{ result.shap_calculated ? '已计算 SHAP' : '未计算 SHAP' }}</span>
        <span v-if="result.shap_interactions_calculated">
          已计算 {{ result.shap_interaction_columns.join('、') }} 的交互效应
        </span>
      </div>

      <h3>平均相对重要性</h3>
      <div class="importance-list">
        <div v-for="item in result.importance_summary" :key="item.variable">
          <span>{{ item.variable }}</span>
          <div><i :style="{ width: importanceWidth(item.relative_importance) }"></i></div>
          <strong>{{ formatNumber(item.relative_importance) }}%</strong>
        </div>
      </div>

      <details class="gwrf-local-results">
        <summary>查看局部预测、SHAP 和置换重要性预览（前 100 行）</summary>
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th v-for="column in localColumns" :key="column">{{ column }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, index) in result.local_preview" :key="index">
                <td v-for="column in localColumns" :key="column">
                  {{ typeof row[column] === 'number' ? formatNumber(row[column]) : row[column] }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>

      <div class="export-panel gwrf-export-panel">
        <div>
          <strong>导出完整结果</strong>
          <p>
            XLSX 包含概览、相对重要性、局部结果和残差 Moran；仅在本次启用时包含 SHAP
            与交互效应字段。CSV 导出全部局部结果。
          </p>
        </div>
        <div>
          <button :disabled="Boolean(exportingFormat)" @click="downloadResult('xlsx')">
            {{ exportingFormat === 'xlsx' ? '导出中…' : '导出 XLSX' }}</button
          ><button :disabled="Boolean(exportingFormat)" @click="downloadResult('csv')">
            {{ exportingFormat === 'csv' ? '导出中…' : '导出 CSV' }}
          </button>
        </div>
      </div>
      <p v-if="exportMessage" class="success-message">{{ exportMessage }}</p>
      <p v-if="result.shap_calculated" class="gwrf-note">
        SHAP
        值解释单个目标点的局部模型预测；置换重要性衡量变量打乱后局部加权误差的增加量。两者含义不同，不应直接比较数值大小。
      </p>
    </section>
  </template>
</template>

<style scoped>
.gwrf-tags,
.coordinate-type-picker,
.gwrf-switches {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.gwrf-tags span {
  padding: 7px 10px;
  border-radius: 8px;
  background: #fff1d7;
  font-size: 0.8rem;
  font-weight: 700;
}
.gwrf-settings h3,
.gwrf-result h3 {
  margin: 25px 0 14px;
}
.coordinate-type-picker label,
.gwrf-switches label {
  padding: 9px 12px;
  border-radius: 9px;
  background: #f4f0e8;
}
.gwrf-variable-grid,
.gwrf-parameter-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin: 15px 0;
}
.gwrf-parameter-grid {
  grid-template-columns: repeat(4, 1fr);
}
.rf-parameter-grid {
  grid-template-columns: repeat(3, 1fr);
}
.final-bandwidth-grid {
  grid-template-columns: minmax(240px, 420px);
}
.gwrf-variable-grid span,
.gwrf-parameter-grid span,
.gwrf-independent-selector > span {
  display: block;
  margin-bottom: 7px;
  font-size: 0.8rem;
  font-weight: 800;
}
.gwrf-variable-grid select,
.gwrf-parameter-grid input {
  width: 100%;
  padding: 10px;
  border: 1px solid #d6c7b1;
  border-radius: 9px;
  background: white;
}
.gwrf-independent-selector > div {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}
.gwrf-independent-selector label {
  padding: 9px 11px;
  border-radius: 8px;
  background: #f4f0e8;
  cursor: pointer;
}
.gwrf-method-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.gwrf-method-grid label {
  display: grid;
  grid-template-columns: auto 1fr;
  align-content: start;
  align-items: center;
  column-gap: 8px;
  padding: 16px;
  border: 1px solid #ded4c3;
  border-radius: 12px;
  cursor: pointer;
}
.gwrf-method-grid label.selected {
  border-color: #bd7a26;
  background: #fff4df;
}
.gwrf-method-grid strong,
.gwrf-method-grid small {
  display: block;
}
.gwrf-method-grid strong {
  margin: 0;
}
.gwrf-method-grid small {
  grid-column: 1 / -1;
  margin-top: 8px;
  color: #736b61;
  line-height: 1.45;
}
.gwrf-note {
  margin: 16px 0;
  padding: 12px;
  border-radius: 9px;
  color: #665d50;
  background: #f8f2e7;
  font-size: 0.8rem;
}
.primary-action {
  margin-top: 8px;
  padding: 12px 20px;
  border: 0;
  border-radius: 9px;
  color: white;
  background: #a86418;
  font-weight: 800;
  cursor: pointer;
}
.parameter-action {
  margin-top: 14px;
  padding: 11px 18px;
  border: 0;
  color: white;
  background: #292b2d;
  font-weight: 800;
  cursor: pointer;
}
.parameter-action:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
.parameter-result {
  margin-top: 14px;
  padding: 14px;
  border: 1px solid #bfc3c5;
  background: #f1f2f2;
}
.parameter-result > strong {
  display: block;
  margin-bottom: 10px;
}
.parameter-result > span {
  display: inline-block;
  margin: 0 8px 8px 0;
  padding: 6px 9px;
  border: 1px solid #c9ccce;
  background: white;
  font-size: 0.8rem;
}
.parameter-result details {
  margin-top: 8px;
}
.parameter-result summary {
  cursor: pointer;
  font-weight: 700;
}
.shap-switches label.disabled {
  opacity: 0.45;
}
.shap-interaction-selector {
  margin-top: 12px;
  padding: 14px;
  border: 1px solid #d8dadd;
  color: #8a8d90;
  background: #eceeef;
  opacity: 0.55;
}
.shap-interaction-selector.active {
  border-color: #55595c;
  color: #252729;
  background: #fff;
  opacity: 1;
}
.shap-interaction-selector > span {
  display: block;
  margin-bottom: 10px;
  font-size: 0.8rem;
  font-weight: 800;
}
.shap-interaction-selector > div {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}
.shap-interaction-selector label {
  padding: 8px 10px;
  border: 1px solid #d4d6d8;
  background: #f4f5f5;
}
.interaction-validation {
  margin-top: 8px;
  color: #8d332d;
  font-size: 0.8rem;
  font-weight: 700;
}
.result-capabilities {
  margin-top: 12px;
}
.primary-action:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
.gwrf-metric-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 11px;
}
.gwrf-metric-grid article {
  padding: 17px;
  border-radius: 12px;
  background: #fff4df;
}
.gwrf-metric-grid span,
.gwrf-metric-grid strong,
.gwrf-metric-grid small {
  display: block;
}
.gwrf-metric-grid strong {
  margin: 7px 0;
  font-size: 1.3rem;
}
.importance-list > div {
  display: grid;
  grid-template-columns: 145px 1fr 90px;
  align-items: center;
  gap: 12px;
  margin: 9px 0;
}
.importance-list > div > div {
  height: 10px;
  overflow: hidden;
  border-radius: 999px;
  background: #eee6d8;
}
.importance-list i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: #bd7a26;
}
.importance-list strong {
  text-align: right;
}
.gwrf-local-results {
  margin-top: 24px;
}
.gwrf-local-results summary {
  cursor: pointer;
  font-weight: 800;
}
.table-scroll {
  overflow: auto;
  margin-top: 12px;
}
.table-scroll table {
  min-width: 100%;
  border-collapse: collapse;
  font-size: 0.76rem;
}
.table-scroll th,
.table-scroll td {
  padding: 8px;
  border: 1px solid #e1ddd5;
  white-space: nowrap;
  text-align: right;
}
.table-scroll th {
  background: #f5f1e9;
}
.gwrf-export-panel {
  margin-top: 20px;
}
.gwrf-export-panel > div:last-child {
  display: flex;
  gap: 8px;
}
@media (max-width: 900px) {
  .gwrf-parameter-grid,
  .gwrf-metric-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (max-width: 640px) {
  .gwrf-variable-grid,
  .gwrf-parameter-grid,
  .gwrf-method-grid,
  .gwrf-metric-grid {
    grid-template-columns: 1fr;
  }
  .importance-list > div {
    grid-template-columns: 90px 1fr 75px;
  }
}
</style>
