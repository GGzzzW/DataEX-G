import type {
  CleaningOptions,
  CleaningPreviewResponse,
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
