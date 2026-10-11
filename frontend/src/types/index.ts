// types/index.ts — mirrors backend Pydantic schemas

export interface User {
  id: number
  username: string
  email: string | null
  role: 'admin' | 'technologist' | 'service'
  active: boolean
}

export interface AuthToken {
  access_token: string
  token_type: string
  role: string
  username: string
}

export interface Fluorochrome {
  id: number
  name: string
  excitation_nm: number | null
  emission_nm: number | null
  laser: string | null
}

export interface Antibody {
  id: number
  name: string
  clone: string | null
  vendor: string | null
  catalog_no: string | null
  vial_volume_ul: number | null
  fluorochrome_id: number | null
  fluorochrome: Fluorochrome | null
  active: boolean
}

export interface AntibodyAlternative {
  id: number
  antibody_id: number
  alt_antibody_id: number
  alt_antibody_name: string
  alt_fluorochrome: string | null
  note: string | null
}

export interface PanelComponent {
  id: number
  antibody_id: number
  antibody_name: string
  fluorochrome: string | null
  volume_per_tube_ul: number
  tubes_per_test: number
  ul_per_test: number
}

export interface Panel {
  id: number
  name: string
  test_code: string
  test_group: string | null
  department: string | null
  active: boolean
  components: PanelComponent[]
}

export interface StockLot {
  id: number
  antibody_id: number
  antibody_name: string
  vendor: string | null
  fluorochrome: string | null
  lot_no: string
  initial_volume_ul: number
  current_volume_ul: number
  date_received: string
  date_opened: string | null
  expiry_date: string | null
  last_verified_date: string | null
  last_verified_volume_ul: number | null
  shipment_id: string | null
  notes?: string | null
  active: boolean
  percent_remaining: number
  store_vial_count: number
}

export interface StockSummary {
  antibody_id: number
  antibody_name: string
  fluorochrome: string | null
  vendor: string | null
  total_stock_ul: number
  active_lot_count: number
  oldest_expiry: string | null
}

export interface ConsumptionRead {
  antibody_id: number
  stock_lot_id: number
  volume_consumed_ul: number
}

export interface TestLog {
  id: number
  date: string
  panel_id: number | null
  panel_name: string
  count: number
  entry_method: string
  entered_by: number
  notes: string | null
  source?: string
  consumption: ConsumptionRead[]
  warnings: string[]
}

export interface ForecastPoint {
  date: string
  predicted_ul: number
}

export interface Forecast {
  antibody_id: number
  current_stock_ul: number
  depletion_date: string | null
  days_remaining: number | null
  avg_daily_ul: number
  forecast_daily_ul: number
  history_days: number
  method: string
  forecast_series: ForecastPoint[]
  confidence_low: ForecastPoint[]
  confidence_high: ForecastPoint[]
}

export interface Alert {
  id: number
  antibody_id: number
  antibody_name: string
  alert_type: 'shortage' | 'substitute_suggestion' | 'expiry_warning'
  message: string
  days_remaining: number | null
  triggered_at: string
  acknowledged_by: number | null
  acknowledged_at: string | null
}

export interface AlertRule {
  id: number
  antibody_id: number
  antibody_name: string
  lead_time_days: number
  safety_stock_ul: number
  alert_threshold_days: number
}

export interface Order {
  id: number
  antibody_id: number
  antibody_name: string
  quantity_vials: number
  volume_per_vial_ul: number
  total_volume_ul: number
  order_date: string
  expected_delivery_date: string | null
  status: 'pending' | 'delivered' | 'cancelled'
  po_number: string | null
  notes: string | null
  created_by: number
}

export interface AffectedPanel {
  panel_id: number
  panel_name: string
  test_code: string
  ul_per_test: number
}

export interface CocktailWarning {
  antibody_id: number
  antibody_name: string
  fluorochrome: string | null
  current_stock_ul: number
  deduction_ul: number
  remaining_ul: number
  days_remaining_after: number | null
  will_be_insufficient: boolean
  below_threshold: boolean
  affected_panels: AffectedPanel[]
}

export interface PreflightResult {
  panel_id: number
  panel_name: string
  test_count: number
  total_deductions: Array<{
    antibody_id: number
    antibody_name: string
    fluorochrome: string | null
    deduction_ul: number
    current_stock_ul: number
  }>
  warnings: CocktailWarning[]
  has_warnings: boolean
  has_insufficient: boolean
}

export interface Cocktail {
  id: number
  panel_id: number
  panel_name: string
  prepared_by: number
  prepared_by_username: string
  prepared_date: string
  total_tests: number
  remaining_tests: number
  reserved_tests?: number
  available_tests?: number
  percent_remaining: number
  expiry_date: string | null
  lot_notes: string | null
  active: boolean
}
export interface InventoryRow {
  antibody_id: number
  antibody_name: string
  fluorochrome: string | null
  vendor: string | null
  total_stock_ul: number
  days_remaining: number | null
  depletion_date: string | null
  avg_daily_ul: number
  forecast_method: string
  active_lot_count: number
  oldest_expiry: string | null
  status: 'ok' | 'warning' | 'critical' | 'unknown'
}

export interface AffectedPanel {
  panel_id: number
  panel_name: string
  test_code: string
}

export interface ComponentWarning {
  antibody_id: number
  antibody_name: string
  fluorochrome: string | null
  needed_ul: number
  current_stock_ul: number
  remaining_after_ul: number
  days_remaining_after: number | null
  alert_threshold_days: number
  severity: 'insufficient' | 'warning'
  affected_panels: AffectedPanel[]
}

export interface ComponentPreview {
  antibody_id: number
  antibody_name: string
  fluorochrome: string | null
  vendor: string | null
  volume_per_tube_ul: number
  tubes_per_test: number
  ul_per_test: number
  total_ul_needed: number
  current_stock_ul: number
  remaining_after_ul: number
  has_warning: boolean
}

export interface CocktailPreview {
  panel_id: number
  panel_name: string
  total_tests: number
  components: ComponentPreview[]
  warnings: ComponentWarning[]
  can_proceed: boolean
}

export interface Cocktail {
  id: number
  panel_id: number
  panel_name: string
  prepared_by: number
  prepared_by_username: string
  prepared_date: string
  total_tests: number
  remaining_tests: number
  expiry_date: string | null
  lot_notes: string | null
  active: boolean
  pct_remaining: number
  cocktail_code?: string | null
  prepared_by_staff_id?: number | null
  prepared_by_name?: string | null
  prepared_at?: string | null
  reserved_tests?: number
  available_tests?: number
}

export interface LabSettings {
  lab_name: string | null
  lab_subtitle: string | null
}

export interface GlobalAlertDefaults {
  lead_time_days: number
  alert_threshold_days: number
  safety_stock_ul: number
}

export interface VerificationAccuracyRow {
  verification_date: string
  antibody_name: string
  lot_no: string
  system_estimate_ul: number
  measured_volume_ul: number
  delta_ul: number
  delta_pct: number | null
  verified_by: string
}

export interface AccuracySummary {
  total_verifications: number
  distinct_cycles: number
  distinct_lots: number
  mean_absolute_error_ul: number
  mean_absolute_pct_error: number | null
  mean_signed_bias_ul: number
  sd_of_differences_ul: number
  bland_altman_lower_loa_ul: number
  bland_altman_upper_loa_ul: number
  min_delta_ul: number
  max_delta_ul: number
  median_delta_ul: number
  overestimate_count: number
  underestimate_count: number
  exact_count: number
  interpretation: string
}

export interface ValidationReport {
  generated_date: string
  tracking_period_days: number
  verification_accuracy: VerificationAccuracyRow[]
  accuracy_summary: AccuracySummary
  alert_effectiveness: any[]
  usage_summary: any[]
}

// ── Worklist / Sample Orders ──────────────────────────────────────────────────

export interface Staff {
  id: number
  name: string
  role: 'pathologist' | 'technologist'
  initials: string | null
  active: boolean
}

export interface SampleOrderTube {
  id: number
  panel_id: number
  panel_name: string
  test_code: string
  status: 'awaiting_cocktail' | 'reserved' | 'consumed'
  reserved_cocktail_id: number | null
  cocktail_code: string | null
  cocktail_label: string | null
  steps_done: number
  steps_total: number
  current_step: string | null
}

export interface CocktailShortfall {
  panel_id: number
  panel_name: string
  test_code: string
  tubes_short: number
}

export interface SampleOrder {
  id: number
  lab_id: string
  requesting_pathologist_id: number | null
  requesting_pathologist_name: string | null
  processing_technologist_id: number | null
  processing_technologist_name: string | null
  status: 'in_queue' | 'in_processing' | 'completed' | 'cancelled'
  priority: 'routine' | 'urgent'
  notes: string | null
  sample_comment: string | null
  sample_comment_updated_at: string | null
  sample_comment_updated_by: string | null
  sample_comment_staff_name: string | null
  sample_flags: string[]
  sample_flags_updated_at: string | null
  sample_flags_staff_name: string | null
  ordered_at: string | null
  processing_started_at: string | null
  completed_at: string | null
  created_by: number
  tubes: SampleOrderTube[]
  tube_count: number
  reserved_count: number
  awaiting_count: number
  consumed_count: number
  tat_minutes: number | null
  cocktail_shortfalls?: CocktailShortfall[]
}

// ── Shipment-to-shipment verification ────────────────────────────────────────

export type VerificationStatus = 'pending' | 'overdue' | 'acceptable' | 'not_acceptable'

export interface VerificationAttachment {
  id: number
  role: 'previous' | 'new'
  original_filename: string
  content_type: string | null
  size_bytes: number
  sha256: string
  uploaded_by_username: string
  uploaded_at: string
}

export interface ShipmentVerification {
  id: number
  antibody_id: number
  antibody_name: string
  fluorochrome: string | null
  vendor: string | null
  shipment_id: string
  new_lot_no: string | null
  previous_shipment_id: string | null
  previous_lot_no: string | null
  lot_changed: boolean
  status: 'open' | 'closed'
  display_status: VerificationStatus
  overdue: boolean
  triggered_at: string
  due_at: string
  hours_remaining: number | null
  outcome: 'acceptable' | 'not_acceptable' | null
  comments: string | null
  closed_by_username: string | null
  closed_at: string | null
  closed_late: boolean | null
  attachments: VerificationAttachment[]
  has_previous_evidence: boolean
  has_new_evidence: boolean
}

// ── Cocktail traceability ────────────────────────────────────────────────────

export interface CocktailTrace {
  cocktail: {
    id: number
    cocktail_code: string | null
    panel_id: number
    panel_name: string | null
    test_code: string | null
    prepared_date: string | null
    prepared_by: string | null
    prepared_at: string | null
    expiry_date: string | null
    total_tests: number
    remaining_tests: number
    reserved_tests: number
    active: boolean
    lot_notes: string | null
  }
  components: {
    antibody_id: number
    antibody_name: string
    fluorochrome: string | null
    stock_lot_id: number
    lot_no: string | null
    shipment_id: string | null
    expiry_date: string | null
    volume_ul: number
    shipment_verification_id: number | null
    shipment_verification_status: VerificationStatus | null
  }[]
  samples: {
    sample_order_id: number
    lab_id: string
    tube_id: number
    test_code: string | null
    tube_status: 'reserved' | 'consumed' | 'awaiting_cocktail'
    order_status: string
    priority: string
    ordered_at: string | null
    processing_started_at: string | null
    completed_at: string | null
    pathologist: string | null
    technologist: string | null
    sample_comment: string | null
    sample_flags: string[]
  }[]
  samples_run: number
  samples_reserved: number
  tests_used: number
  untracked_tests: number
  related_cocktails: {
    id: number
    cocktail_code: string | null
    test_code: string | null
    prepared_date: string | null
    active: boolean
    samples_run: number
    shared_lots: string[]
  }[]
}

// ── Bench station ────────────────────────────────────────────────────────────

export interface StationStep {
  seq: number
  name: string
  wait_minutes: number | null
  ready_at: string | null           // server time when the step's timer runs out
  completed_at: string | null
  completed_by: string | null
  completed_early_seconds: number | null
}

export interface TemplateStep {
  name: string
  wait_minutes: number | null
}

export interface StationTube {
  id: number
  test_code: string
  panel_name: string
  status: 'awaiting_cocktail' | 'reserved' | 'consumed'
  cocktail_code: string | null
  steps: StationStep[]
  next_seq: number | null
  next_name: string | null
  undo_seq: number | null
  done: boolean
}

export interface StationOrder {
  id: number
  lab_id: string
  priority: 'routine' | 'urgent'
  status: string
  notes: string | null
  ordered_at: string | null
  waiting_minutes: number | null
  completed_at: string | null
  pathologist: string | null
  technologist: string | null
  sample_flags: string[]
  sample_comment: string | null
  tubes: StationTube[]
}

export interface StepTemplates {
  built_in: string[]
  default: { steps: TemplateStep[]; names: string[]; source: 'lab_default' | 'built_in' }
  panels: { panel_id: number; test_code: string; panel_name: string; steps: TemplateStep[]; names: string[]; source: 'panel' | 'lab_default' | 'built_in' }[]
}

// ── Starting-volume checks ────────────────────────────────────────────────────

export interface VolumeDiscrepancyReport {
  lots: {
    lot_id: number; antibody_id: number; antibody_name: string; fluorochrome: string | null
    catalog_no: string | null; lot_no: string; date_received: string
    recorded_ul: number; standard_ul: number; current_volume_ul: number; verified: boolean
  }[]
  store: {
    store_id: number; antibody_id: number; antibody_name: string; fluorochrome: string | null
    catalog_no: string | null; lot_no: string; quantity: number
    recorded_ul: number; standard_ul: number
  }[]
  antibodies_without_volume: {
    antibody_id: number; antibody_name: string; fluorochrome: string | null; catalog_no: string | null
  }[]
}

export interface SampleFlagOption { code: string; label: string }
