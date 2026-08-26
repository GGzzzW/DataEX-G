import type {
  AnalysisMethod,
  AnalysisResponse,
  CoordinateType,
  CleaningOptions,
  CleaningPreviewResponse,
  ExportFormat,
  ExportTable,
  FilePreviewResponse,
  SpatialAnalysisResponse,
  SpatialMethod,
} from '@/types/analysis'

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(body?.detail ?? `文件处理失败（HTTP ${response.status}）。`)
  }

  return (await response.json()) as T
}

export async function previewFile(file: File): Promise<FilePreviewResponse> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch('/api/files/preview', {
    method: 'POST',
    body: formData,
  })

  return parseResponse<FilePreviewResponse>(response)
}

export async function previewCleaning(
  file: File,
  options: CleaningOptions,
): Promise<CleaningPreviewResponse> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('missing_action', options.missingAction)
  formData.append('trim_whitespace', String(options.trimWhitespace))
  formData.append('remove_line_breaks', String(options.removeLineBreaks))
  formData.append('standardization_method', options.standardizationMethod)
  formData.append('standardization_columns', JSON.stringify(options.standardizationColumns))

  const response = await fetch('/api/files/clean/preview', {
    method: 'POST',
    body: formData,
  })

  return parseResponse<CleaningPreviewResponse>(response)
}

function getDownloadFilename(response: Response, fallback: string): string {
  const disposition = response.headers.get('content-disposition') ?? ''
  const encodedMatch = disposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (encodedMatch?.[1]) return decodeURIComponent(encodedMatch[1])

  const basicMatch = disposition.match(/filename="([^"]+)"/i)
  return basicMatch?.[1] ?? fallback
}

export async function exportCleaning(
  file: File,
  options: CleaningOptions,
  outputFormat: ExportFormat,
  table: ExportTable = 'cleaned',
): Promise<string> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('missing_action', options.missingAction)
  formData.append('trim_whitespace', String(options.trimWhitespace))
  formData.append('remove_line_breaks', String(options.removeLineBreaks))
  formData.append('standardization_method', options.standardizationMethod)
  formData.append('standardization_columns', JSON.stringify(options.standardizationColumns))
  formData.append('output_format', outputFormat)
  formData.append('table', table)

  const response = await fetch('/api/files/clean/export', {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    await parseResponse<never>(response)
  }

  const fallback = `data-dataex.${outputFormat}`
  const filename = getDownloadFilename(response, fallback)
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
  return filename
}

export async function runAnalysis(
  file: File,
  method: AnalysisMethod,
  dependentColumn: string,
  independentColumns: string[],
): Promise<AnalysisResponse> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('method', method)
  formData.append('dependent_column', dependentColumn)
  formData.append('independent_columns', JSON.stringify(independentColumns))

  const response = await fetch('/api/analysis/run', {
    method: 'POST',
    body: formData,
  })
  return parseResponse<AnalysisResponse>(response)
}

async function downloadResponse(response: Response, fallback: string): Promise<string> {
  if (!response.ok) await parseResponse<never>(response)
  const filename = getDownloadFilename(response, fallback)
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
  return filename
}

export async function exportAnalysis(
  file: File,
  method: AnalysisMethod,
  dependentColumn: string,
  independentColumns: string[],
  outputFormat: ExportFormat,
): Promise<string> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('method', method)
  formData.append('dependent_column', dependentColumn)
  formData.append('independent_columns', JSON.stringify(independentColumns))
  formData.append('output_format', outputFormat)

  const response = await fetch('/api/analysis/export', { method: 'POST', body: formData })
  return downloadResponse(response, `analysis-analysis-dataex.${outputFormat}`)
}

interface SpatialRunOptions {
  method: SpatialMethod
  coordinateType: CoordinateType
  xColumn: string
  yColumn: string
  dependentColumn: string
  independentColumns: string[]
  neighbors: number
}

function buildSpatialFormData(file: File, options: SpatialRunOptions): FormData {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('method', options.method)
  formData.append('coordinate_type', options.coordinateType)
  formData.append('x_column', options.xColumn)
  formData.append('y_column', options.yColumn)
  formData.append('dependent_column', options.dependentColumn)
  formData.append('independent_columns', JSON.stringify(options.independentColumns))
  formData.append('neighbors', String(options.neighbors))
  return formData
}

export async function runSpatialAnalysis(
  file: File,
  options: SpatialRunOptions,
): Promise<SpatialAnalysisResponse> {
  const formData = buildSpatialFormData(file, options)
  const response = await fetch('/api/spatial/run', { method: 'POST', body: formData })
  return parseResponse<SpatialAnalysisResponse>(response)
}

export async function exportSpatialAnalysis(
  file: File,
  options: SpatialRunOptions,
  outputFormat: ExportFormat,
): Promise<string> {
  const formData = buildSpatialFormData(file, options)
  formData.append('output_format', outputFormat)
  const response = await fetch('/api/spatial/export', { method: 'POST', body: formData })
  return downloadResponse(response, `spatial-spatial-dataex.${outputFormat}`)
}
