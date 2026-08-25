export interface DetectedType {
  type: 'boolean' | 'datetime' | 'number' | 'text'
  count: number
  examples: string[]
}

export interface ColumnQuality {
  name: string
  pandas_dtype: string
  missing_count: number
  missing_ratio: number
  detected_types: DetectedType[]
  mixed_types: boolean
}

export interface QualityReport {
  missing_cell_count: number
  duplicate_row_count: number
  duplicate_row_numbers: number[]
  columns: ColumnQuality[]
}

export interface FilePreviewResponse {
  filename: string
  row_count: number
  column_count: number
  columns: string[]
  preview: Record<string, unknown>[]
  quality: QualityReport
}
