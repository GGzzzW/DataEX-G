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
  whitespace_count: number
  whitespace_row_numbers: number[]
  line_break_count: number
  line_break_row_numbers: number[]
}

export interface QualityReport {
  missing_cell_count: number
  whitespace_cell_count: number
  line_break_cell_count: number
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

export type MissingAction = 'none' | 'drop_rows' | 'extract_rows' | 'fill_zero'
export type ExportFormat = 'csv' | 'xlsx'
export type ExportTable = 'cleaned' | 'extracted'
export type StandardizationMethod = 'none' | 'min_max' | 'z_score'

export interface CleaningOptions {
  missingAction: MissingAction
  trimWhitespace: boolean
  removeLineBreaks: boolean
  standardizationMethod: StandardizationMethod
  standardizationColumns: string[]
}

export interface StandardizationStatistic {
  column: string
  minimum: number
  maximum: number
  mean: number
  standard_deviation: number
}

export interface CleaningSummary {
  missing_action: MissingAction
  missing_affected_row_count: number
  text_changed_cell_count: number
  extracted_row_numbers: number[]
  standardization_method: StandardizationMethod
  standardized_columns: string[]
  standardization_statistics: StandardizationStatistic[]
}

export interface CleaningPreviewResponse {
  filename: string
  original_row_count: number
  cleaned_row_count: number
  extracted_row_count: number
  columns: string[]
  cleaned_preview: Record<string, unknown>[]
  extracted_preview: Record<string, unknown>[]
  cleaned_quality: QualityReport
  summary: CleaningSummary
}
