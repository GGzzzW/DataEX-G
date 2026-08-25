<script setup lang="ts">
import { computed, ref } from 'vue'

import { previewFile } from '@/services/api'
import type { FilePreviewResponse } from '@/types/analysis'

const selectedFile = ref<File | null>(null)
const result = ref<FilePreviewResponse | null>(null)
const errorMessage = ref('')
const isLoading = ref(false)

const hasIssues = computed(() => {
  if (!result.value) return false
  const quality = result.value.quality
  return (
    quality.missing_cell_count > 0 ||
    quality.duplicate_row_count > 0 ||
    quality.columns.some((column) => column.mixed_types)
  )
})

function setFile(file: File | undefined) {
  errorMessage.value = ''
  result.value = null

  if (!file) {
    selectedFile.value = null
    return
  }

  const extension = file.name.toLowerCase().split('.').pop()
  if (!extension || !['csv', 'xlsx'].includes(extension)) {
    selectedFile.value = null
    errorMessage.value = '请选择 CSV 或 XLSX 文件。'
    return
  }

  selectedFile.value = file
}

function onFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  setFile(input.files?.[0])
}

function onDrop(event: DragEvent) {
  setFile(event.dataTransfer?.files[0])
}

async function analyzeSelectedFile() {
  if (!selectedFile.value) return

  isLoading.value = true
  errorMessage.value = ''
  try {
    result.value = await previewFile(selectedFile.value)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '文件分析失败。'
  } finally {
    isLoading.value = false
  }
}

function formatFileSize(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function formatRatio(ratio: number) {
  return `${(ratio * 100).toFixed(1)}%`
}
</script>

<template>
  <main class="app-shell">
    <header class="hero">
      <div>
        <p class="eyebrow">LOCAL DATA TOOLKIT</p>
        <h1>数据质量工作台</h1>
        <p class="hero-copy">在本机检查 CSV 和 Excel，不上传数据，不依赖互联网。</p>
      </div>
      <div class="local-badge"><span></span> 本地处理</div>
    </header>

    <section class="panel upload-panel">
      <div class="section-heading">
        <div>
          <p class="step-label">步骤 01</p>
          <h2>选择数据文件</h2>
        </div>
        <p>支持 CSV、XLSX，单个文件不超过 20 MB</p>
      </div>

      <label class="drop-zone" @dragover.prevent @drop.prevent="onDrop">
        <input type="file" accept=".csv,.xlsx" @change="onFileSelected" />
        <span class="upload-icon">↑</span>
        <strong>点击选择或拖放文件到这里</strong>
        <small>文件只会发送到你电脑上的 Python 服务</small>
      </label>

      <div v-if="selectedFile" class="selected-file">
        <div>
          <strong>{{ selectedFile.name }}</strong>
          <span>{{ formatFileSize(selectedFile.size) }}</span>
        </div>
        <button :disabled="isLoading" @click="analyzeSelectedFile">
          {{ isLoading ? '分析中…' : '开始分析' }}
        </button>
      </div>

      <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>
    </section>

    <template v-if="result">
      <section class="summary-grid" aria-label="文件摘要">
        <article class="metric-card">
          <span>数据行数</span>
          <strong>{{ result.row_count }}</strong>
        </article>
        <article class="metric-card">
          <span>字段数量</span>
          <strong>{{ result.column_count }}</strong>
        </article>
        <article class="metric-card" :class="{ warning: result.quality.missing_cell_count }">
          <span>空值单元格</span>
          <strong>{{ result.quality.missing_cell_count }}</strong>
        </article>
        <article class="metric-card" :class="{ warning: result.quality.duplicate_row_count }">
          <span>重复数据行</span>
          <strong>{{ result.quality.duplicate_row_count }}</strong>
        </article>
      </section>

      <section class="panel">
        <div class="section-heading">
          <div>
            <p class="step-label">步骤 02</p>
            <h2>质量报告</h2>
          </div>
          <span class="result-badge" :class="{ clean: !hasIssues }">
            {{ hasIssues ? '发现需要关注的问题' : '未发现明显问题' }}
          </span>
        </div>

        <div class="quality-table-wrap">
          <table class="quality-table">
            <thead>
              <tr>
                <th>字段</th>
                <th>pandas 类型</th>
                <th>空值</th>
                <th>检测到的内容类型</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="column in result.quality.columns" :key="column.name">
                <td class="column-name">{{ column.name }}</td>
                <td>
                  <code>{{ column.pandas_dtype }}</code>
                </td>
                <td>{{ column.missing_count }}（{{ formatRatio(column.missing_ratio) }}）</td>
                <td>
                  <span
                    v-for="detected in column.detected_types"
                    :key="detected.type"
                    class="type-chip"
                    :title="detected.examples.join('、')"
                  >
                    {{ detected.type }} · {{ detected.count }}
                  </span>
                  <span v-if="!column.detected_types.length" class="muted">无有效值</span>
                </td>
                <td>
                  <span v-if="column.mixed_types" class="status warning-text">混合类型</span>
                  <span v-else class="status ok-text">正常</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="panel">
        <div class="section-heading">
          <div>
            <p class="step-label">步骤 03</p>
            <h2>数据预览</h2>
          </div>
          <p>显示前 {{ result.preview.length }} 行</p>
        </div>

        <div class="data-table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th class="row-number">#</th>
                <th v-for="column in result.columns" :key="column">{{ column }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, rowIndex) in result.preview" :key="rowIndex">
                <td class="row-number">{{ rowIndex + 1 }}</td>
                <td v-for="column in result.columns" :key="column">
                  <span v-if="row[column] === null" class="missing-value">空值</span>
                  <span v-else>{{ row[column] }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </main>
</template>
