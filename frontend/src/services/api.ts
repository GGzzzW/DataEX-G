import type {
  CleaningOptions,
  CleaningPreviewResponse,
  ExportFormat,
  ExportTable,
  FilePreviewResponse,
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
