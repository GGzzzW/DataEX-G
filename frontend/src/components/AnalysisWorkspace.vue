<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { exportAnalysis, previewFile, runAnalysis } from '@/services/api'
import type {
  AnalysisMethod,
  AnalysisResponse,
  ExportFormat,
  FilePreviewResponse,
} from '@/types/analysis'

const methods: Array<{ value: AnalysisMethod; label: string; description: string }> = [
  { value: 'ols', label: 'OLS', description: '连续因变量的普通最小二乘回归' },
  { value: 'negative_binomial', label: '负二项回归', description: '非负整数计数型因变量' },
  { value: 'pearson', label: 'Pearson', description: '两个数值变量的线性相关' },
  { value: 'spearman', label: 'Spearman', description: '两个数值变量的单调相关' },
  { value: 'logistic', label: 'Logistic', description: '只有两类结果的二元回归' },
]

const selectedFile = ref<File | null>(null)
const dataset = ref<FilePreviewResponse | null>(null)
const selectedMethod = ref<AnalysisMethod>('ols')
const dependentColumn = ref('')
const independentColumns = ref<string[]>([])
const correlationColumn = ref('')
const result = ref<AnalysisResponse | null>(null)
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

const isCorrelation = computed(() => ['pearson', 'spearman'].includes(selectedMethod.value))

const availableIndependentColumns = computed(() =>
  numericColumns.value.filter((column) => column !== dependentColumn.value),
)

const canRun = computed(() => {
  if (!selectedFile.value || !dependentColumn.value) return false
  return isCorrelation.value
    ? Boolean(correlationColumn.value)
    : independentColumns.value.length > 0
})

watch([selectedMethod, dependentColumn], () => {
  result.value = null
  errorMessage.value = ''
  exportMessage.value = ''
  independentColumns.value = independentColumns.value.filter(
    (column) => column !== dependentColumn.value,
  )
  if (correlationColumn.value === dependentColumn.value) correlationColumn.value = ''
})

async function onFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  selectedFile.value = file
  dataset.value = null
  result.value = null
  dependentColumn.value = ''
  independentColumns.value = []
  correlationColumn.value = ''
  errorMessage.value = ''
  isReading.value = true
  try {
    dataset.value = await previewFile(file)
  } catch (error) {
    selectedFile.value = null
    errorMessage.value = error instanceof Error ? error.message : '读取字段失败。'
  } finally {
    isReading.value = false
  }
}

async function executeAnalysis() {
  if (!selectedFile.value || !canRun.value) return

  isRunning.value = true
  result.value = null
  errorMessage.value = ''
  try {
    result.value = await runAnalysis(
      selectedFile.value,
      selectedMethod.value,
      dependentColumn.value,
      isCorrelation.value ? [correlationColumn.value] : independentColumns.value,
    )
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '分析失败。'
  } finally {
    isRunning.value = false
  }
}

async function downloadAnalysisResult(outputFormat: ExportFormat) {
  if (!selectedFile.value || !result.value) return
  exportingFormat.value = outputFormat
  errorMessage.value = ''
  exportMessage.value = ''
  try {
    const filename = await exportAnalysis(
      selectedFile.value,
      selectedMethod.value,
      dependentColumn.value,
      isCorrelation.value ? [correlationColumn.value] : independentColumns.value,
      outputFormat,
    )
    exportMessage.value = `已导出 ${filename}`
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '结果导出失败。'
  } finally {
    exportingFormat.value = ''
  }
}

function formatNumber(value: number | null) {
  if (value === null) return '—'
  if (value !== 0 && Math.abs(value) < 0.0001) return value.toExponential(3)
  return value.toFixed(6)
}

function correlationStrength(value: number | null) {
  if (value === null) return '无法判断'
  const magnitude = Math.abs(value)
  if (magnitude >= 0.7) return '强相关'
  if (magnitude >= 0.4) return '中等相关'
  return '弱相关'
}
</script>

<template>
  <section class="panel analysis-intro">
    <div class="section-heading">
      <div>
        <p class="step-label">ANALYSIS</p>
        <h2>回归分析方法</h2>
      </div>
      <p>OLS、负二项、Logistic 回归，以及 Pearson、Spearman 相关性</p>
    </div>

    <label class="analysis-file-picker">
      <input type="file" accept=".csv,.xlsx" @change="onFileSelected" />
      <span>{{ isReading ? '正在读取字段…' : '选择分析数据' }}</span>
      <small>{{ selectedFile?.name ?? '建议载入清洗后导出的 -dataex 文件' }}</small>
    </label>
    <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>
  </section>

  <template v-if="dataset">
    <section class="panel">
      <div class="analysis-file-summary">
        <span>{{ dataset.filename }}</span>
        <span>{{ dataset.row_count }} 行</span>
        <span>{{ numericColumns.length }} 个可用数值列</span>
      </div>

      <h3 class="analysis-section-title">选择分析方法</h3>
      <div class="method-grid">
        <label v-for="method in methods" :key="method.value" class="method-card">
          <input v-model="selectedMethod" type="radio" :value="method.value" />
          <strong>{{ method.label }}</strong>
          <small>{{ method.description }}</small>
        </label>
      </div>

      <div class="variable-grid">
        <label>
          <span>{{ isCorrelation ? '变量 Y' : '因变量 Y' }}</span>
          <select v-model="dependentColumn">
            <option value="" disabled>请选择数值列</option>
            <option v-for="column in numericColumns" :key="column" :value="column">
              {{ column }}
            </option>
          </select>
        </label>

        <label v-if="isCorrelation">
          <span>变量 X</span>
          <select v-model="correlationColumn">
            <option value="" disabled>请选择另一个数值列</option>
            <option v-for="column in availableIndependentColumns" :key="column" :value="column">
              {{ column }}
            </option>
          </select>
        </label>

        <div v-else class="independent-selector">
          <span>自变量 X（可多选）</span>
          <div>
            <label v-for="column in availableIndependentColumns" :key="column">
              <input v-model="independentColumns" type="checkbox" :value="column" />
              {{ column }}
            </label>
          </div>
        </div>
      </div>

      <p v-if="!numericColumns.length" class="analysis-warning">
        当前文件没有可安全分析的纯数值列，请先清洗或转换数据类型。
      </p>

      <button class="primary-action" :disabled="isRunning || !canRun" @click="executeAnalysis">
        {{ isRunning ? '正在计算…' : '运行分析' }}
      </button>
    </section>

    <section v-if="result" class="panel analysis-result">
      <div class="section-heading">
        <div>
          <p class="step-label">RESULT</p>
          <h2>分析结果</h2>
        </div>
        <p>有效样本 {{ result.observations }}，排除缺失行 {{ result.dropped_rows }}</p>
      </div>

      <div
        v-if="result.diagnostics"
        class="diagnostics-panel"
        :class="{ invalid: !result.diagnostics.valid_inference }"
      >
        <div class="diagnostics-heading">
          <div>
            <strong>
              {{ result.diagnostics.valid_inference ? '模型推断有效' : '模型推断不可靠' }}
            </strong>
            <small>
              {{ result.diagnostics.converged ? '模型已收敛' : '模型未收敛' }}
            </small>
          </div>
          <div class="diagnostic-values">
            <span>标准化条件数 {{ formatNumber(result.diagnostics.condition_number) }}</span>
            <span>原始条件数 {{ formatNumber(result.diagnostics.raw_condition_number) }}</span>
            <span>最大 VIF {{ formatNumber(result.diagnostics.max_vif) }}</span>
            <span>尺度比 {{ formatNumber(result.diagnostics.scale_ratio) }}</span>
          </div>
        </div>
        <ul v-if="result.diagnostics.warnings.length">
          <li v-for="warning in result.diagnostics.warnings" :key="warning">{{ warning }}</li>
        </ul>
        <p v-else>未检测到收敛、非有限数值或明显共线性问题。</p>
        <details v-if="result.diagnostics.vif.length">
          <summary>查看各变量 VIF</summary>
          <div class="vif-list">
            <span v-for="item in result.diagnostics.vif" :key="item.column">
              {{ item.column }}：{{ formatNumber(item.vif) }}
            </span>
          </div>
        </details>
      </div>

      <div v-if="result.correlation" class="correlation-result">
        <article>
          <span>相关系数</span>
          <strong>{{ formatNumber(result.correlation.coefficient) }}</strong>
          <small>{{ correlationStrength(result.correlation.coefficient) }}</small>
        </article>
        <article>
          <span>p 值</span>
          <strong>{{ formatNumber(result.correlation.p_value) }}</strong>
          <small>{{ (result.correlation.p_value ?? 1) < 0.05 ? '统计显著' : '未达到 0.05' }}</small>
        </article>
      </div>

      <template v-if="result.regression">
        <div class="model-metrics">
          <article v-if="result.regression.metrics.r_squared !== null">
            <span>R²</span><strong>{{ formatNumber(result.regression.metrics.r_squared) }}</strong>
          </article>
          <article v-if="result.regression.metrics.adjusted_r_squared !== null">
            <span>调整 R²</span>
            <strong>{{ formatNumber(result.regression.metrics.adjusted_r_squared) }}</strong>
          </article>
          <article v-if="result.regression.metrics.pseudo_r_squared !== null">
            <span>伪 R²</span>
            <strong>{{ formatNumber(result.regression.metrics.pseudo_r_squared) }}</strong>
          </article>
          <article>
            <span>AIC</span><strong>{{ formatNumber(result.regression.metrics.aic) }}</strong>
          </article>
          <article>
            <span>BIC</span><strong>{{ formatNumber(result.regression.metrics.bic) }}</strong>
          </article>
        </div>

        <p v-if="result.regression.binary_mapping" class="binary-mapping">
          Logistic 编码：
          <span v-for="(value, label) in result.regression.binary_mapping" :key="label">
            {{ label }} → {{ value }}
          </span>
        </p>

        <div class="quality-table-wrap">
          <table class="quality-table">
            <thead>
              <tr>
                <th>变量</th>
                <th>系数</th>
                <th>标准误</th>
                <th>统计量</th>
                <th>p 值</th>
                <th>95% 置信区间</th>
                <th v-if="selectedMethod === 'logistic'">优势比</th>
                <th v-if="selectedMethod === 'negative_binomial'">发生率比</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="coefficient in result.regression.coefficients" :key="coefficient.term">
                <td class="column-name">{{ coefficient.term }}</td>
                <td>{{ formatNumber(coefficient.estimate) }}</td>
                <td>{{ formatNumber(coefficient.standard_error) }}</td>
                <td>{{ formatNumber(coefficient.statistic) }}</td>
                <td>{{ formatNumber(coefficient.p_value) }}</td>
                <td>
                  {{ formatNumber(coefficient.confidence_low) }} ～
                  {{ formatNumber(coefficient.confidence_high) }}
                </td>
                <td v-if="['logistic', 'negative_binomial'].includes(selectedMethod)">
                  {{ formatNumber(coefficient.effect_ratio) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <p class="analysis-disclaimer">
        统计显著性和相关性不代表因果关系；正式结论还需检查模型假设、样本设计与业务背景。
      </p>

      <div class="export-panel analysis-export-panel">
        <div>
          <h3>导出分析结果</h3>
          <p>文件名自动添加 -analysis-dataex；XLSX 包含概览和系数工作表。</p>
        </div>
        <div class="export-actions">
          <button :disabled="!!exportingFormat" @click="downloadAnalysisResult('csv')">
            {{ exportingFormat === 'csv' ? '导出中…' : '导出 CSV' }}
          </button>
          <button
            class="xlsx-button"
            :disabled="!!exportingFormat"
            @click="downloadAnalysisResult('xlsx')"
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
.analysis-file-picker {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 18px;
  border: 1px dashed #99ad9f;
  border-radius: 12px;
  background: #f5f9f5;
  cursor: pointer;
}

.analysis-file-picker input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
}

.analysis-file-picker span {
  font-weight: 800;
}

.analysis-file-picker small {
  color: #728078;
}

.analysis-file-summary,
.model-metrics,
.correlation-result {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.analysis-file-summary span,
.binary-mapping span {
  padding: 7px 10px;
  border-radius: 8px;
  background: #eaf1eb;
  font-size: 0.8rem;
  font-weight: 700;
}

.analysis-section-title {
  margin: 26px 0 14px;
}

.method-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 9px;
}

.method-card {
  min-height: 104px;
  padding: 14px;
  border: 1px solid #dce3de;
  border-radius: 12px;
  background: #fafcf9;
  cursor: pointer;
}

.method-card:has(input:checked) {
  border-color: #3f7556;
  background: #edf6ef;
}

.method-card input {
  accent-color: #315e45;
}

.method-card strong,
.method-card small {
  display: block;
  margin-top: 7px;
}

.method-card small {
  color: #718077;
  line-height: 1.35;
}

.variable-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
  margin: 22px 0;
}

.variable-grid > label > span,
.independent-selector > span {
  display: block;
  margin-bottom: 8px;
  font-size: 0.8rem;
  font-weight: 800;
}

.variable-grid select {
  width: 100%;
  padding: 11px;
  border: 1px solid #ccd7d0;
  border-radius: 9px;
  color: #25372d;
  background: white;
}

.independent-selector > div {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}

.independent-selector label {
  padding: 9px 11px;
  border-radius: 8px;
  background: #f1f4f1;
  cursor: pointer;
}

.analysis-warning {
  color: #9a5c12;
}

.correlation-result article,
.model-metrics article {
  min-width: 160px;
  padding: 18px;
  border-radius: 12px;
  background: #f1f6f2;
}

.correlation-result span,
.correlation-result strong,
.correlation-result small,
.model-metrics span,
.model-metrics strong {
  display: block;
}

.correlation-result strong,
.model-metrics strong {
  margin-top: 7px;
  font-size: 1.35rem;
}

.correlation-result small {
  margin-top: 5px;
  color: #627068;
}

.model-metrics {
  margin-bottom: 22px;
}

.binary-mapping {
  margin-bottom: 18px;
}

.analysis-disclaimer {
  margin: 20px 0 0;
  padding: 12px;
  border-radius: 9px;
  color: #6f6756;
  background: #f8f4e8;
  font-size: 0.78rem;
}

.analysis-export-panel {
  margin-top: 18px;
}

.diagnostics-panel {
  margin-bottom: 20px;
  padding: 16px;
  border: 1px solid #b9d8c2;
  border-radius: 11px;
  background: #edf7ef;
}

.diagnostics-panel.invalid {
  border-color: #e1a39b;
  background: #fff0ed;
}

.diagnostics-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.diagnostics-heading strong,
.diagnostics-heading small {
  display: block;
}

.diagnostics-heading small {
  margin-top: 4px;
  color: #617067;
}

.diagnostic-values,
.vif-list {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}

.diagnostic-values span,
.vif-list span {
  padding: 6px 9px;
  border-radius: 7px;
  background: rgb(255 255 255 / 72%);
  font-size: 0.76rem;
  font-weight: 700;
}

.diagnostics-panel ul {
  margin-bottom: 8px;
  padding-left: 20px;
}

.diagnostics-panel li + li {
  margin-top: 6px;
}

.diagnostics-panel details {
  margin-top: 10px;
}

.diagnostics-panel summary {
  cursor: pointer;
  font-weight: 700;
}

.vif-list {
  margin-top: 10px;
}

@media (max-width: 900px) {
  .method-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 640px) {
  .analysis-file-picker,
  .variable-grid {
    align-items: flex-start;
    grid-template-columns: 1fr;
  }

  .analysis-file-picker {
    flex-direction: column;
  }
}
</style>
