import type { FilePreviewResponse } from '@/types/analysis'

export async function previewFile(file: File): Promise<FilePreviewResponse> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch('/api/files/preview', {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(body?.detail ?? `文件分析失败（HTTP ${response.status}）。`)
  }

  return (await response.json()) as FilePreviewResponse
}
