// api/client.ts — centralised Axios instance + typed API calls

import axios from 'axios'
import type {
  Alert, AlertRule, Antibody, AntibodyAlternative,
  AuthToken, Cocktail, Fluorochrome, Forecast, Order,
  Panel, PreflightResult, StockLot, StockSummary, TestLog, User,
  VolumeDiscrepancyReport,
} from '../types'

// ── Axios instance ──────────────────────────────────────────────────────────

export const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

// Inject JWT on every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('flowjai_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Redirect to login on 401 — but NOT on the login endpoint itself,
// otherwise a wrong password silently reloads the page instead of showing an error
api.interceptors.response.use(
  (r) => r,
  (err) => {
    const isLoginEndpoint = err.config?.url?.includes('/auth/token')
    if (err.response?.status === 401 && !isLoginEndpoint) {
      localStorage.removeItem('flowjai_token')
      localStorage.removeItem('flowjai_user')
      const here = window.location.pathname
      window.location.href = here && here !== '/' && here !== '/login'
        ? `/login?next=${encodeURIComponent(here)}`
        : '/login'
    }
    return Promise.reject(err)
  },
)

// ── Authenticated file download ──────────────────────────────────────────────
// window.open() bypasses axios and sends no Authorization header, so it 401s.
// This fetches the file as a blob (token attached via interceptor) and saves it.
export async function downloadFile(url: string, fallbackName = 'download') {
  const res = await api.get(url, { responseType: 'blob' })
  const disposition = res.headers['content-disposition'] as string | undefined
  let filename = fallbackName
  if (disposition) {
    const m = disposition.match(/filename="?([^"]+)"?/)
    if (m) filename = m[1]
  }
  const blobUrl = window.URL.createObjectURL(res.data as Blob)
  const a = document.createElement('a')
  a.href = blobUrl
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(blobUrl)
}

// Opens an authenticated HTML response in a new tab (e.g. printable worksheet).
// The worksheet is gated behind auth, and a new tab wouldn't carry the bearer
// token, so we fetch it as a blob and open the blob URL.
export async function openAuthedHtml(url: string) {
  const res = await api.get(url, { responseType: 'blob' })
  const blob = new Blob([res.data as BlobPart], { type: 'text/html' })
  const blobUrl = window.URL.createObjectURL(blob)
  window.open(blobUrl, '_blank')
  // Revoke after a delay so the new tab has time to load
  setTimeout(() => window.URL.revokeObjectURL(blobUrl), 60_000)
}

// ── Auth ────────────────────────────────────────────────────────────────────

export const authApi = {
  login: async (username: string, password: string): Promise<AuthToken> => {
    const form = new URLSearchParams({ username, password })
    const { data } = await api.post<AuthToken>('/auth/token', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    return data
  },
  me: () => api.get<User>('/auth/me').then((r) => r.data),
  setupStatus: () => api.get<{ needs_setup: boolean }>('/auth/setup-status').then((r) => r.data),
  setup: (d: { username: string; email?: string; password: string }) =>
    api.post<AuthToken>('/auth/setup', d).then((r) => r.data),
}

// ── Fluorochromes ────────────────────────────────────────────────────────────

export const fluorochromesApi = {
  list: () => api.get<Fluorochrome[]>('/fluorochromes/').then((r) => r.data),
  create: (d: Omit<Fluorochrome, 'id'>) => api.post<Fluorochrome>('/fluorochromes/', d).then((r) => r.data),
  update: (id: number, d: Partial<Fluorochrome>) => api.patch<Fluorochrome>(`/fluorochromes/${id}`, d).then((r) => r.data),
  remove: (id: number) => api.delete(`/fluorochromes/${id}`),
}

// ── Antibodies ───────────────────────────────────────────────────────────────

export const antibodiesApi = {
  list: (activeOnly = true) =>
    api.get<Antibody[]>('/antibodies/', { params: { active_only: activeOnly } }).then((r) => r.data),
  get: (id: number) => api.get<Antibody>(`/antibodies/${id}`).then((r) => r.data),
  create: (d: Partial<Antibody>) => api.post<Antibody>('/antibodies/', d).then((r) => r.data),
  update: (id: number, d: Partial<Antibody>) => api.patch<Antibody>(`/antibodies/${id}`, d).then((r) => r.data),
  listAlternatives: (id: number) =>
    api.get<AntibodyAlternative[]>(`/antibodies/${id}/alternatives`).then((r) => r.data),
  addAlternative: (id: number, altId: number, note?: string) =>
    api.post<AntibodyAlternative>(`/antibodies/${id}/alternatives`, { alt_antibody_id: altId, note }).then((r) => r.data),
  removeAlternative: (id: number, altId: number) =>
    api.delete(`/antibodies/${id}/alternatives/${altId}`),
  remove: (id: number, force = false) =>
    api.delete(`/antibodies/${id}`, { params: { force } }),
  deletePreview: (id: number) =>
    api.get<{ antibody_name: string; stock_lots: number; panel_assignments: number; consumption_logs: number; verification_logs: number; alternative_mappings: number; safe: boolean }>(`/antibodies/${id}/delete-preview`).then(r => r.data),
}

// ── Panels ───────────────────────────────────────────────────────────────────

export const panelsApi = {
  list: (activeOnly = true) =>
    api.get<Panel[]>('/panels/', { params: { active_only: activeOnly } }).then((r) => r.data),
  get: (id: number) => api.get<Panel>(`/panels/${id}`).then((r) => r.data),
  create: (d: { name: string; test_code: string; test_group?: string; department?: string }) =>
    api.post<Panel>('/panels/', d).then((r) => r.data),
  update: (id: number, d: Partial<Panel>) => api.patch<Panel>(`/panels/${id}`, d).then((r) => r.data),
  addComponent: (panelId: number, d: { antibody_id: number; volume_per_tube_ul: number; tubes_per_test: number }) =>
    api.post(`/panels/${panelId}/components`, d).then((r) => r.data),
  updateComponent: (panelId: number, compId: number, d: { volume_per_tube_ul?: number; tubes_per_test?: number }) =>
    api.patch(`/panels/${panelId}/components/${compId}`, d).then((r) => r.data),
  removeComponent: (panelId: number, compId: number) =>
    api.delete(`/panels/${panelId}/components/${compId}`),
  remove: (panelId: number, force = false) =>
    api.delete(`/panels/${panelId}`, { params: { force } }),
  deletePreview: (panelId: number) =>
    api.get<{ panel_name: string; components: number; test_logs: number; safe: boolean }>(`/panels/${panelId}/delete-preview`).then(r => r.data),
}

// ── Stock ────────────────────────────────────────────────────────────────────

export const stockApi = {
  list: (antibodyId?: number, activeOnly = true) =>
    api.get<StockLot[]>('/stock/', { params: { antibody_id: antibodyId, active_only: activeOnly } }).then((r) => r.data),
  summary: () => api.get<StockSummary[]>('/stock/summary').then((r) => r.data),
  receive: (d: {
    antibody_id: number; lot_no: string; initial_volume_ul?: number; volume_override_reason?: string
    date_received: string; expiry_date?: string; shipment_id?: string
  }) => api.post<StockLot>('/stock/', d).then((r) => r.data),
  volumeDiscrepancies: () =>
    api.get<VolumeDiscrepancyReport>('/stock/volume-discrepancies').then((r) => r.data),
  correctStartVolume: (lotId: number, correct_initial_volume_ul: number, reason: string) =>
    api.post<StockLot>(`/stock/${lotId}/correct-start-volume`, { correct_initial_volume_ul, reason }).then((r) => r.data),
  verify: (lotId: number, payload: {
    verified_volume_ul: number
    measurement_method?: string
    pipette_increment_ul?: number | null
    verification_cycle?: string | null
  }) => api.post<StockLot>(`/stock/${lotId}/verify`, payload).then((r) => r.data),
  markOpened: (lotId: number) =>
    api.patch<StockLot>(`/stock/${lotId}/open`).then((r) => r.data),
  remove: (lotId: number) => api.delete(`/stock/${lotId}`),
  bulkReceive: (lots: object[]) => api.post<object[]>('/stock/bulk', lots).then(r => r.data),
}

// ── Tests ────────────────────────────────────────────────────────────────────

export const testsApi = {
  list: (params?: { panel_id?: number; start_date?: string; end_date?: string; limit?: number }) =>
    api.get<TestLog[]>('/tests/', { params }).then((r) => r.data),
  create: (d: { date: string; panel_id: number; count: number; notes?: string }) =>
    api.post<TestLog>('/tests/', d),  // returns response (not just data) so caller can check status 207
  importCsv: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/tests/import-csv', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data)
  },
  logAdhoc: (d: object) => api.post('/tests/adhoc', d).then(r => r.data),
}

// ── Forecast ─────────────────────────────────────────────────────────────────

export const forecastApi = {
  all: () => api.get<Forecast[]>('/forecast/').then((r) => r.data),
  one: (antibodyId: number, historyDays = 90, horizonDays = 60) =>
    api.get<Forecast>(`/forecast/${antibodyId}`, {
      params: { history_days: historyDays, horizon_days: horizonDays },
    }).then((r) => r.data),
}

// ── Alerts ───────────────────────────────────────────────────────────────────

export const alertsApi = {
  list: (unacknowledgedOnly = true) =>
    api.get<Alert[]>('/alerts/', { params: { unacknowledged_only: unacknowledgedOnly } }).then((r) => r.data),
  run: () => api.post<Alert[]>('/alerts/run').then((r) => r.data),
  acknowledge: (id: number) =>
    api.post<Alert>(`/alerts/${id}/acknowledge`).then((r) => r.data),
}

// ── Alert Rules ───────────────────────────────────────────────────────────────

export const alertRulesApi = {
  list: () => api.get<AlertRule[]>('/alert-rules/').then((r) => r.data),
  upsert: (antibodyId: number, d: { lead_time_days: number; safety_stock_ul: number; alert_threshold_days: number }) =>
    api.put<AlertRule>(`/alert-rules/${antibodyId}`, d).then((r) => r.data),
  remove: (antibodyId: number) => api.delete(`/alert-rules/${antibodyId}`),
}

// ── Orders ────────────────────────────────────────────────────────────────────

export const ordersApi = {
  list: (status?: string) =>
    api.get<Order[]>('/orders/', { params: { status } }).then((r) => r.data),
  create: (d: {
    antibody_id: number; quantity_vials: number; volume_per_vial_ul?: number; volume_override_reason?: string
    order_date: string; expected_delivery_date?: string; po_number?: string; notes?: string
  }) => api.post<Order>('/orders/', d).then((r) => r.data),
  update: (id: number, d: Partial<Order>) =>
    api.patch<Order>(`/orders/${id}`, d).then((r) => r.data),
  deliver: (id: number, d: {
    lot_no: string; expiry_date?: string; delivery_date?: string; shipment_id?: string
    actual_volume_per_vial_ul?: number; volume_override_reason?: string
  }) =>
    api.post<Order>(`/orders/${id}/deliver`, d).then((r) => r.data),
}

// ── Users ─────────────────────────────────────────────────────────────────────

export const usersApi = {
  list: () => api.get<User[]>('/users/').then((r) => r.data),
  create: (d: { username: string; email?: string; password: string; role: string }) =>
    api.post<User>('/users/', d).then((r) => r.data),
  update: (id: number, d: { username?: string; email?: string; role?: string; active?: boolean }) =>
    api.patch<User>(`/users/${id}`, d).then((r) => r.data),
  adminResetPassword: (id: number, new_password: string) =>
    api.post(`/users/${id}/reset-password`, { new_password }),
  changePassword: (currentPassword: string, newPassword: string) =>
    api.post('/users/me/change-password', { current_password: currentPassword, new_password: newPassword }),
}

// ── Cocktails ─────────────────────────────────────────────────────────────────

export const cocktailsApi = {
  preview: (panel_id: number, total_tests: number) =>
    api.post('/cocktails/preview', { panel_id, total_tests }).then(r => r.data),
  list: (panel_id?: number, active_only = true) =>
    api.get('/cocktails/', { params: { panel_id, active_only } }).then(r => r.data),
  log: (params: { start_date?: string; end_date?: string; panel_id?: number; prepared_by_staff_id?: number }) =>
    api.get<Cocktail[]>('/cocktails/', { params: { active_only: false, ...params } }).then(r => r.data),
  prepare: (d: { panel_id: number; total_tests: number; expiry_date?: string; lot_notes?: string; prepared_by_staff_id?: number }) =>
    api.post('/cocktails/', d),
  use: (cocktail_id: number, d: { test_date: string; count: number; notes?: string }) =>
    api.post(`/cocktails/${cocktail_id}/use`, d).then(r => r.data),
  worksheet: (cocktail_id: number) => openAuthedHtml(`/cocktails/${cocktail_id}/worksheet`),
  trace: (cocktail_id: number) =>
    api.get<CocktailTrace>(`/cocktails/${cocktail_id}/trace`).then(r => r.data),
  traceCsv: (cocktail_id: number) =>
    downloadFile(`/cocktails/${cocktail_id}/trace.csv`, `cocktail_${cocktail_id}_trace.csv`),
  exportSummary: (start?: string, end?: string) => {
    const params = new URLSearchParams()
    if (start) params.set('start_date', start)
    if (end) params.set('end_date', end)
    return downloadFile(`/cocktails/export/summary.csv?${params.toString()}`, 'flowjai_cocktails_summary.csv')
  },
}

// ── Lab Settings ──────────────────────────────────────────────────────────────

export const labSettingsApi = {
  get: () => api.get('/lab-settings/').then(r => r.data),
  update: (d: { lab_name?: string; lab_subtitle?: string }) =>
    api.patch('/lab-settings/', d).then(r => r.data),
  getAlertDefaults: () => api.get('/lab-settings/alert-defaults').then(r => r.data),
  updateAlertDefaults: (d: { lead_time_days: number; alert_threshold_days: number; safety_stock_ul: number }) =>
    api.put('/lab-settings/alert-defaults', d).then(r => r.data),
}

// ── Validation ────────────────────────────────────────────────────────────────

export const validationApi = {
  report: () => api.get('/validation/report').then(r => r.data),
  downloadVerification: () => downloadFile('/validation/export/verification-accuracy.csv', 'verification-accuracy.csv'),
  downloadAccuracySummary: () => downloadFile('/validation/export/accuracy-summary.csv', 'accuracy-summary-stats.csv'),
  downloadUsage: () => downloadFile('/validation/export/usage-summary.csv', 'usage-summary.csv'),
  downloadAlerts: () => downloadFile('/validation/export/alert-effectiveness.csv', 'alert-effectiveness.csv'),
}

export const storeStockApi = {
  list: (inStockOnly = true) =>
    api.get<object[]>('/store-stock/', { params: { in_stock_only: inStockOnly } }).then(r => r.data),
  receive: (d: object) => api.post<object>('/store-stock/', d).then(r => r.data),
  update: (id: number, d: object) => api.patch<object>(`/store-stock/${id}`, d).then(r => r.data),
  openVial: (id: number) => api.post<object>(`/store-stock/${id}/open-vial`).then(r => r.data),
  remove: (id: number) => api.delete(`/store-stock/${id}`),
  check: (antibodyId: number) =>
    api.get<{ has_store_stock: boolean }>(`/store-stock/check/${antibodyId}`).then(r => r.data),
}

export const exportApi = {
  antibodies: () => downloadFile('/export/antibodies', 'flowjai_antibodies.csv'),
  inventory:  () => downloadFile('/export/inventory', 'flowjai_inventory.csv'),
  panels:     () => downloadFile('/export/panels', 'flowjai_panels.csv'),
  cocktails:      () => downloadFile('/export/cocktails', 'flowjai_cocktails.csv'),
  stockPosition:  () => downloadFile('/export/stock-position', 'flowjai_stock_position.csv'),
}

// ── Staff (master list) ───────────────────────────────────────────────────────

import type { Staff, SampleOrder } from '../types'

export const staffApi = {
  list: (role?: string, activeOnly = true) =>
    api.get<Staff[]>('/staff/', { params: { role, active_only: activeOnly } }).then(r => r.data),
  create: (d: { name: string; role: string; initials?: string }) =>
    api.post<Staff>('/staff/', d).then(r => r.data),
  update: (id: number, d: Partial<Staff>) =>
    api.patch<Staff>(`/staff/${id}`, d).then(r => r.data),
  remove: (id: number) => api.delete(`/staff/${id}`),
}

// ── Sample Orders (worklist) ──────────────────────────────────────────────────

export const sampleOrdersApi = {
  list: (params?: { status?: string; start_date?: string; end_date?: string; date_field?: string; lab_id?: string }) =>
    api.get<SampleOrder[]>('/sample-orders/', { params }).then(r => r.data),
  availability: () =>
    api.get<Record<string, number>>('/sample-orders/cocktail-availability').then(r => r.data),
  // returns the raw response so callers can detect 207 (cocktail shortfall)
  create: (d: {
    lab_id: string
    requesting_pathologist_id?: number
    processing_technologist_id?: number
    priority?: string
    notes?: string
    ordered_at?: string
    tubes: { panel_id: number }[]
  }) => api.post<SampleOrder>('/sample-orders/', d),
  update: (id: number, d: Partial<SampleOrder>) =>
    api.patch<SampleOrder>(`/sample-orders/${id}`, d).then(r => r.data),
  reserve: (id: number) => api.post<SampleOrder>(`/sample-orders/${id}/reserve`),
  start: (id: number) => api.post<SampleOrder>(`/sample-orders/${id}/start`).then(r => r.data),
  complete: (id: number) => api.post<SampleOrder>(`/sample-orders/${id}/complete`).then(r => r.data),
  cancel: (id: number) => api.post<SampleOrder>(`/sample-orders/${id}/cancel`).then(r => r.data),
  setSampleComment: (id: number, comment: string, staffId: number) =>
    api.put<SampleOrder>(`/sample-orders/${id}/sample-comment`, { comment, staff_id: staffId }).then(r => r.data),
  sampleFlagOptions: () =>
    api.get<{ code: string; label: string }[]>('/sample-orders/sample-flags').then(r => r.data),
  setSampleFlag: (id: number, code: string, on: boolean, staffId: number) =>
    api.put<SampleOrder>(`/sample-orders/${id}/flags/${code}`, { on, staff_id: staffId }).then(r => r.data),
  exportCsv: (start?: string, end?: string) => {
    const p = new URLSearchParams()
    if (start) p.set('start_date', start)
    if (end) p.set('end_date', end)
    return downloadFile(`/sample-orders/export/worklist.csv?${p.toString()}`, 'flowjai_worklist.csv')
  },
}

// ── Shipment-to-shipment verification ─────────────────────────────────────────

import type { CocktailTrace, ShipmentVerification } from '../types'

export const shipmentVerificationsApi = {
  list: (status: 'open' | 'closed' | 'all' = 'open', params?: { antibody_id?: number; shipment_id?: string }) =>
    api.get<ShipmentVerification[]>('/shipment-verifications/', { params: { status, ...params } }).then(r => r.data),
  summary: () =>
    api.get<{ open: number; overdue: number }>('/shipment-verifications/summary').then(r => r.data),
  get: (id: number) =>
    api.get<ShipmentVerification>(`/shipment-verifications/${id}`).then(r => r.data),
  upload: (id: number, role: 'previous' | 'new', file: File) => {
    const form = new FormData()
    form.append('role', role)
    form.append('file', file)
    return api.post<ShipmentVerification>(`/shipment-verifications/${id}/attachments`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data)
  },
  removeAttachment: (attId: number) => api.delete(`/shipment-verifications/attachments/${attId}`),
  downloadAttachment: (attId: number, name: string) =>
    downloadFile(`/shipment-verifications/attachments/${attId}`, name),
  close: (id: number, d: { outcome: 'acceptable' | 'not_acceptable'; comments?: string; closed_by_staff_id?: number }) =>
    api.post<ShipmentVerification>(`/shipment-verifications/${id}/close`, d).then(r => r.data),
  exportLog: () => downloadFile('/shipment-verifications/export/log.csv', 'flowjai_shipment_verifications.csv'),
}

// ── Bench station ─────────────────────────────────────────────────────────────

import type { StationOrder, StepTemplates, TemplateStep } from '../types'

export const stationApi = {
  queue: () =>
    api.get<{ orders: StationOrder[]; recent: StationOrder[]; server_time: string }>('/station/queue').then(r => r.data),
  complete: (tubeId: number, seq: number, staffId?: number, force = false) =>
    api.post<StationOrder>(`/station/tubes/${tubeId}/steps/${seq}/complete`, { staff_id: staffId, force }).then(r => r.data),
  undo: (tubeId: number, seq: number) =>
    api.post<StationOrder>(`/station/tubes/${tubeId}/steps/${seq}/undo`).then(r => r.data),
  advance: (orderId: number, stepName: string, staffId?: number, force = false) =>
    api.post<StationOrder>(`/station/orders/${orderId}/advance`, { step_name: stepName, staff_id: staffId, force }).then(r => r.data),
  templates: () => api.get<StepTemplates>('/station/templates').then(r => r.data),
  saveDefault: (steps: TemplateStep[]) => api.put('/station/templates/default', { steps }).then(r => r.data),
  savePanel: (panelId: number, steps: TemplateStep[]) => api.put(`/station/templates/${panelId}`, { steps }).then(r => r.data),
  stationToken: () =>
    api.post<{ access_token: string; role: string; username: string }>('/auth/station-token').then(r => r.data),
}
