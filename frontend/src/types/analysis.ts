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

export type AnalysisMethod = 'ols' | 'negative_binomial' | 'pearson' | 'spearman' | 'logistic'

export interface CorrelationResult {
  coefficient: number | null
  p_value: number | null
}

export interface RegressionCoefficient {
  term: string
  estimate: number | null
  standard_error: number | null
  statistic: number | null
  p_value: number | null
  confidence_low: number | null
  confidence_high: number | null
  effect_ratio: number | null
}

export interface RegressionMetrics {
  r_squared: number | null
  adjusted_r_squared: number | null
  pseudo_r_squared: number | null
  aic: number | null
  bic: number | null
  log_likelihood: number | null
}

export interface RegressionResult {
  coefficients: RegressionCoefficient[]
  metrics: RegressionMetrics
  binary_mapping: Record<string, number> | null
}

export interface VarianceInflationFactor {
  column: string
  vif: number | null
}

export interface ModelDiagnostics {
  converged: boolean
  valid_inference: boolean
  rank: number | null
  parameter_count: number | null
  condition_number: number | null
  raw_condition_number: number | null
  scale_ratio: number | null
  max_vif: number | null
  vif: VarianceInflationFactor[]
  warnings: string[]
}

export interface AnalysisResponse {
  kind: 'correlation' | 'regression'
  method: AnalysisMethod
  observations: number
  dropped_rows: number
  dependent_column: string
  independent_columns: string[]
  correlation: CorrelationResult | null
  regression: RegressionResult | null
  diagnostics: ModelDiagnostics | null
}

export type SpatialMethod = 'moran' | 'slm' | 'sem' | 'sdm' | 'gwr'
export type CoordinateType = 'geographic' | 'projected'

export interface SpatialCoefficient {
  term: string
  estimate: number | null
  standard_error: number | null
  statistic: number | null
  p_value: number | null
  confidence_low: number | null
  confidence_high: number | null
}

export interface MoranResult {
  i: number | null
  expected_i: number | null
  z_score: number | null
  p_normal: number | null
  p_permutation: number | null
  permutations: number
  random_seed: number
}

export interface SpatialImpact {
  term: string
  direct: number | null
  indirect: number | null
  total: number | null
}

export interface SpatialRegressionResult {
  coefficients: SpatialCoefficient[]
  spatial_impacts: SpatialImpact[]
  impact_method: 'simple'
  metrics: {
    pseudo_r_squared: number | null
    aic: number | null
    bic: number | null
    log_likelihood: number | null
    rho: number | null
    lambda: number | null
  }
}

export interface SpatialDiagnosticTest {
  name: string
  statistic: number | null
  p_value: number | null
}

export interface ModelSelectionDiagnostics {
  available: boolean
  baseline_residual_moran: {
    i: number | null
    z_score: number | null
    p_value: number | null
  } | null
  tests: SpatialDiagnosticTest[]
  recommendation: string
  warnings: string[]
}

export interface GwrCoefficientSummary {
  term: string
  mean: number | null
  standard_deviation: number | null
  minimum: number | null
  median: number | null
  maximum: number | null
}

export interface GwrResult {
  bandwidth: number | null
  metrics: {
    r_squared: number | null
    adjusted_r_squared: number | null
    aic: number | null
    aicc: number | null
  }
  coefficient_summaries: GwrCoefficientSummary[]
  local_result_count: number
  local_preview: Record<string, number | null>[]
}

export interface SpatialAnalysisResponse {
  kind: 'moran' | 'spatial_regression' | 'gwr'
  method: SpatialMethod
  observations: number
  dropped_rows: number
  coordinate_type: CoordinateType
  x_column: string
  y_column: string
  dependent_column: string
  independent_columns: string[]
  weights: {
    type: 'knn'
    neighbors: number
    transformation: 'row_standardized'
    components: number
  }
  moran: MoranResult | null
  regression: SpatialRegressionResult | null
  gwr: GwrResult | null
  diagnostics: ModelDiagnostics
  residual_moran: MoranResult | null
  model_selection: ModelSelectionDiagnostics | null
}
