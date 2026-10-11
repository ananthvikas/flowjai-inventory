// pages/Cocktails.tsx

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import { AlertTriangle, FlaskConical, Plus, Printer, XCircle , Download, GitBranch, History } from 'lucide-react'
import { useState } from 'react'
import { format as fmtDate, subDays } from 'date-fns'
import { cocktailsApi, panelsApi , exportApi, staffApi } from '../api/client'
import { Badge, Button, Card, EmptyState, Input, Modal, Select, Spinner } from '../components/ui'
import type { Cocktail, CocktailPreview, ComponentWarning } from '../types'
import CocktailTraceModal from '../components/CocktailTraceModal'

// ── Warning panel ─────────────────────────────────────────────────────────

function WarningPanel({ warnings }: { warnings: ComponentWarning[] }) {
  if (warnings.length === 0) return null
  return (
    <div className="space-y-3">
      {warnings.map(w => (
        <div
          key={w.antibody_id}
          className={`rounded-xl border p-4 space-y-2 ${
            w.severity === 'insufficient' ? 'bg-red-50 border-red-200' : 'bg-amber-50 border-amber-200'
          }`}
        >
          <div className="flex items-center gap-2 flex-wrap">
            {w.severity === 'insufficient'
              ? <XCircle className="w-4 h-4 text-red-600 shrink-0" />
              : <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />}
            <span className="text-sm font-semibold text-slate-900">
              {w.antibody_name}
              {w.fluorochrome && <span className="text-slate-400 font-normal ml-1">· {w.fluorochrome}</span>}
            </span>
            <Badge variant={w.severity === 'insufficient' ? 'critical' : 'warning'}>
              {w.severity === 'insufficient' ? 'Insufficient stock' : 'Low after mixing'}
            </Badge>
          </div>

          <div className="grid grid-cols-3 gap-3 text-xs">
            <div><p className="text-slate-500">Needed</p><p className="font-medium">{w.needed_ul.toFixed(1)} µl</p></div>
            <div><p className="text-slate-500">Available</p><p className="font-medium">{w.current_stock_ul.toFixed(1)} µl</p></div>
            <div>
              <p className="text-slate-500">Remaining after</p>
              <p className={`font-medium ${w.remaining_after_ul < 0 ? 'text-red-600' : 'text-amber-700'}`}>
                {w.remaining_after_ul < 0 ? '0 µl (deficit)' : `${w.remaining_after_ul.toFixed(1)} µl`}
              </p>
            </div>
          </div>

          {w.days_remaining_after !== null && w.days_remaining_after >= 0 && (
            <p className="text-xs text-slate-600">
              At current usage, remaining stock lasts approx.{' '}
              <span className="font-medium">{Math.round(w.days_remaining_after)} days</span>
              {' '}(alert threshold: {w.alert_threshold_days} days).
            </p>
          )}

          {w.affected_panels.length > 0 && (
            <div className="text-xs text-slate-600 bg-white/60 rounded-lg p-2.5">
              <p className="font-medium mb-1">Other panels also using {w.antibody_name}:</p>
              <div className="flex flex-wrap gap-1.5">
                {w.affected_panels.map(p => (
                  <span key={p.panel_id} className="bg-white border border-slate-200 rounded px-2 py-0.5 font-mono">
                    {p.test_code} — {p.panel_name}
                  </span>
                ))}
              </div>
              <p className="mt-1.5 text-slate-500">
                Reducing the number of tests in this batch will preserve stock for these panels.
              </p>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

// ── Prepare modal ─────────────────────────────────────────────────────────

function PrepareCocktailModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const { data: panels = [] } = useQuery({ queryKey: ['panels'], queryFn: () => panelsApi.list() })
  const { data: staff = [] } = useQuery({ queryKey: ['staff', 'all'], queryFn: () => staffApi.list(), enabled: open })

  const [step, setStep] = useState<'form' | 'preview'>('form')
  // prepared_by is deliberately NOT remembered between preps: on a shared PC a
  // pre-filled name would silently attribute the next person's work to the last.
  const [form, setForm] = useState({ panel_id: '', total_tests: '10', expiry_date: '', lot_notes: '', prepared_by_staff_id: '' })
  const [preview, setPreview] = useState<CocktailPreview | null>(null)
  const [error, setError] = useState('')
  const set = (k: string, v: string) => { setForm(f => ({ ...f, [k]: v })); setError('') }

  const previewMut = useMutation({
    mutationFn: () => cocktailsApi.preview(Number(form.panel_id), Number(form.total_tests)),
    onSuccess: (data: any) => { setPreview(data); setStep('preview') },
    onError: (e: any) => setError(e.response?.data?.detail ?? 'Error running preview'),
  })

  const prepareMut = useMutation({
    mutationFn: () => cocktailsApi.prepare({
      panel_id: Number(form.panel_id),
      total_tests: Number(form.total_tests),
      expiry_date: form.expiry_date || undefined,
      lot_notes: form.lot_notes || undefined,
      prepared_by_staff_id: Number(form.prepared_by_staff_id),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cocktails'] })
      qc.invalidateQueries({ queryKey: ['cocktail-log'] })
      qc.invalidateQueries({ queryKey: ['stock'] })
      qc.invalidateQueries({ queryKey: ['stock-summary'] })
      qc.invalidateQueries({ queryKey: ['forecast-all'] })
      qc.invalidateQueries({ queryKey: ['alerts'] })
      handleClose()
    },
    onError: (e: any) => setError(e.response?.data?.detail ?? 'Error preparing cocktail'),
  })

  const handleClose = () => {
    setStep('form'); setPreview(null); setError('')
    setForm({ panel_id: '', total_tests: '10', expiry_date: '', lot_notes: '', prepared_by_staff_id: '' })
    onClose()
  }

  return (
    <Modal open={open} onClose={handleClose} title="Prepare New Cocktail">
      <div className="space-y-4">

        {step === 'form' && (
          <>
            <Select label="Panel" value={form.panel_id} onChange={e => set('panel_id', e.target.value)}>
              <option value="">Select panel...</option>
              {panels.map(p => <option key={p.id} value={p.id}>{p.name} ({p.test_code})</option>)}
            </Select>
            <Input label="Number of tests" type="number" min="1"
              value={form.total_tests} onChange={e => set('total_tests', e.target.value)} />
            <Select label="Prepared by" value={form.prepared_by_staff_id} onChange={e => set('prepared_by_staff_id', e.target.value)}>
              <option value="">Select who is mixing…</option>
              {staff.map((s: any) => <option key={s.id} value={s.id}>{s.name}{s.role === 'pathologist' ? ' (pathologist)' : ''}</option>)}
            </Select>
            {staff.length === 0 && (
              <p className="text-xs text-amber-600 -mt-2">Add staff names under Admin → Staff first.</p>
            )}
            <div className="grid grid-cols-2 gap-3">
              <Input label="Expiry date (optional)" type="date"
                value={form.expiry_date} onChange={e => set('expiry_date', e.target.value)} />
              <Input label="Batch notes (optional)"
                value={form.lot_notes} onChange={e => set('lot_notes', e.target.value)}
                placeholder="e.g. Fridge 2, Batch A" />
            </div>
            {error && <p className="text-sm text-red-600">{error}</p>}
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={handleClose}>Cancel</Button>
              <Button onClick={() => previewMut.mutate()}
                disabled={previewMut.isPending || !form.panel_id || !form.total_tests || !form.prepared_by_staff_id}>
                {previewMut.isPending ? 'Checking...' : 'Preview volumes'}
              </Button>
            </div>
          </>
        )}

        {step === 'preview' && preview && (
          <>
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
                Volumes for {preview.total_tests} tests — {preview.panel_name}
              </p>
              <div className="overflow-x-auto rounded-lg border border-slate-100">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-slate-50">
                      {['Antibody', 'Vendor', 'Fluor', 'µl/test', 'Total needed', 'Stock after'].map(h => (
                        <th key={h} className="text-left px-3 py-2 font-semibold text-slate-500">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {preview.components.map(c => (
                      <tr key={c.antibody_id} className={c.has_warning ? 'bg-amber-50/60' : ''}>
                        <td className="px-3 py-2 font-medium text-slate-800">
                          {c.antibody_name}
                          {c.has_warning && <span className="ml-1 text-amber-500">⚠</span>}
                        </td>
                        <td className="px-3 py-2 text-slate-400">{c.vendor ?? '—'}</td>
                        <td className="px-3 py-2 text-slate-500">{c.fluorochrome ?? '—'}</td>
                        <td className="px-3 py-2 tabular-nums">{c.ul_per_test.toFixed(1)}</td>
                        <td className="px-3 py-2 tabular-nums font-medium">{c.total_ul_needed.toFixed(1)} µl</td>
                        <td className={`px-3 py-2 tabular-nums font-medium ${c.remaining_after_ul < 0 ? 'text-red-600' : c.has_warning ? 'text-amber-600' : 'text-slate-700'}`}>
                          {Math.max(0, c.remaining_after_ul).toFixed(1)} µl
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {preview.warnings.length > 0
              ? <WarningPanel warnings={preview.warnings} />
              : (
                <div className="bg-emerald-50 border border-emerald-200 rounded-lg px-4 py-3 text-sm text-emerald-800">
                  All antibodies have sufficient stock. Safe to proceed.
                </div>
              )}

            {error && <p className="text-sm text-red-600">{error}</p>}

            <div className="flex items-center justify-between pt-1">
              <Button variant="secondary" onClick={() => { setStep('form'); setPreview(null) }}>
                Back - adjust count
              </Button>
              <div className="flex gap-2">
                <Button variant="secondary" onClick={handleClose}>Cancel</Button>
                <Button onClick={() => prepareMut.mutate()}
                  disabled={prepareMut.isPending || !preview.can_proceed}>
                  {prepareMut.isPending ? 'Preparing...' : 'Confirm and deduct stock'}
                </Button>
              </div>
            </div>
            {!preview.can_proceed && (
              <p className="text-xs text-red-600 text-right">
                Insufficient stock - reduce the number of tests to proceed.
              </p>
            )}
          </>
        )}
      </div>
    </Modal>
  )
}

// ── Use cocktail modal ────────────────────────────────────────────────────

function UseCocktailModal({ cocktail, onClose }: { cocktail: Cocktail | null; onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ test_date: format(new Date(), 'yyyy-MM-dd'), count: '1', notes: '' })
  const [error, setError] = useState('')

  const mut = useMutation({
    mutationFn: () => cocktailsApi.use(cocktail!.id, {
      test_date: form.test_date,
      count: Number(form.count),
      notes: form.notes || undefined,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['cocktails'] }); onClose() },
    onError: (e: any) => setError(e.response?.data?.detail ?? 'Error logging usage'),
  })

  if (!cocktail) return null
  return (
    <Modal open={!!cocktail} onClose={onClose} title="Log Tests from Cocktail">
      <div className="space-y-4">
        <div className="bg-slate-50 rounded-lg p-3 text-sm space-y-1">
          <p className="font-medium">{cocktail.panel_name}</p>
          <p className="text-slate-500">
            {cocktail.remaining_tests} of {cocktail.total_tests} tests remaining
            {cocktail.lot_notes && ` · ${cocktail.lot_notes}`}
          </p>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Input label="Date" type="date" value={form.test_date}
            onChange={e => setForm(f => ({ ...f, test_date: e.target.value }))} />
          <Input label="Tests run" type="number" min="1" max={cocktail.remaining_tests}
            value={form.count} onChange={e => setForm(f => ({ ...f, count: e.target.value }))} />
        </div>
        <Input label="Notes (optional)" value={form.notes}
          onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={() => mut.mutate()}
            disabled={mut.isPending || !form.count || Number(form.count) > cocktail.remaining_tests}>
            {mut.isPending ? 'Logging...' : 'Log tests'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────

// ── Export summary modal ──────────────────────────────────────────────────

function ExportSummaryModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  return (
    <Modal open={open} onClose={onClose} title="Export Cocktail Summary">
      <div className="space-y-4">
        <p className="text-sm text-slate-500">
          Download a CSV of cocktails prepared in a date range. Leave both blank for all records.
        </p>
        <div className="grid grid-cols-2 gap-3">
          <Input label="From (optional)" type="date" value={start} onChange={e => setStart(e.target.value)} />
          <Input label="To (optional)" type="date" value={end} onChange={e => setEnd(e.target.value)} />
        </div>
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={() => { cocktailsApi.exportSummary(start || undefined, end || undefined); onClose() }}>
            <Download className="w-3.5 h-3.5" /> Download CSV
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Preparation log ───────────────────────────────────────────────────────

function PrepLogModal({ open, onClose, onTrace }: { open: boolean; onClose: () => void; onTrace: (id: number) => void }) {
  const [start, setStart] = useState(fmtDate(subDays(new Date(), 30), 'yyyy-MM-dd'))
  const [end, setEnd] = useState(fmtDate(new Date(), 'yyyy-MM-dd'))
  const [panelId, setPanelId] = useState('')
  const [staffId, setStaffId] = useState('')

  const { data: panels = [] } = useQuery({ queryKey: ['panels'], queryFn: () => panelsApi.list(), enabled: open })
  const { data: staff = [] } = useQuery({ queryKey: ['staff', 'all'], queryFn: () => staffApi.list(), enabled: open })
  const { data: rows = [], isLoading } = useQuery({
    queryKey: ['cocktail-log', start, end, panelId, staffId],
    queryFn: () => cocktailsApi.log({
      start_date: start || undefined,
      end_date: end || undefined,
      panel_id: panelId ? Number(panelId) : undefined,
      prepared_by_staff_id: staffId ? Number(staffId) : undefined,
    }),
    enabled: open,
  })

  const inputCls = 'px-2.5 py-1.5 text-xs border border-slate-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-brand-500'

  return (
    <Modal open={open} onClose={onClose} title="Cocktail preparation log" size="xl">
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <input type="date" value={start} onChange={e => setStart(e.target.value)} className={inputCls} />
          <span className="text-xs text-slate-400">to</span>
          <input type="date" value={end} onChange={e => setEnd(e.target.value)} className={inputCls} />
          <select value={panelId} onChange={e => setPanelId(e.target.value)} className={inputCls}>
            <option value="">All panels</option>
            {panels.map(p => <option key={p.id} value={p.id}>{p.test_code} — {p.name}</option>)}
          </select>
          <select value={staffId} onChange={e => setStaffId(e.target.value)} className={inputCls}>
            <option value="">Anyone</option>
            {staff.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <span className="text-xs text-slate-400">{rows.length} cocktail{rows.length === 1 ? '' : 's'}</span>
          <Button variant="secondary" size="sm" className="ml-auto"
            onClick={() => cocktailsApi.exportSummary(start || undefined, end || undefined)}>
            <Download className="w-3.5 h-3.5" /> CSV
          </Button>
        </div>

        {isLoading ? <Spinner className="py-10" /> : rows.length === 0 ? (
          <EmptyState message="No cocktails prepared in this range." />
        ) : (
          <div className="border border-slate-200 rounded-lg overflow-auto max-h-[60vh]">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 sticky top-0">
                <tr className="text-left text-xs font-medium text-slate-500">
                  <th className="px-3 py-2">Prepared</th>
                  <th className="px-3 py-2">Cocktail</th>
                  <th className="px-3 py-2">Panel</th>
                  <th className="px-3 py-2">Prepared by</th>
                  <th className="px-3 py-2 text-right">Tests used</th>
                  <th className="px-3 py-2">Expiry</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map(c => (
                  <tr key={c.id}>
                    <td className="px-3 py-1.5 text-xs whitespace-nowrap tabular-nums">
                      {c.prepared_at ? fmtDate(parseISO(c.prepared_at), 'd MMM yy, HH:mm') : format(parseISO(c.prepared_date), 'd MMM yy')}
                    </td>
                    <td className="px-3 py-1.5 font-mono text-xs">{c.cocktail_code ?? `#${c.id}`}</td>
                    <td className="px-3 py-1.5 text-xs">{c.panel_name}</td>
                    <td className="px-3 py-1.5 text-xs">
                      {c.prepared_by_name ?? c.prepared_by_username}
                      {!c.prepared_by_staff_id && <span className="text-slate-400" title="Recorded before staff names were captured — this is the login, not the person"> (login)</span>}
                    </td>
                    <td className="px-3 py-1.5 text-xs text-right tabular-nums">
                      {c.total_tests - c.remaining_tests}/{c.total_tests}
                      {!c.active && <span className="text-slate-400"> · closed</span>}
                    </td>
                    <td className="px-3 py-1.5 text-xs whitespace-nowrap">{c.expiry_date ? format(parseISO(c.expiry_date), 'd MMM yy') : '—'}</td>
                    <td className="px-3 py-1.5 text-right">
                      <Button variant="ghost" size="sm" onClick={() => onTrace(c.id)}>
                        <GitBranch className="w-3.5 h-3.5" /> Trace
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Modal>
  )
}

export default function CocktailsPage() {
  const [prepareOpen, setPrepareOpen] = useState(false)
  const [useCocktail, setUseCocktail] = useState<Cocktail | null>(null)
  const [showAll, setShowAll] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const [traceId, setTraceId] = useState<number | null>(null)
  const [logOpen, setLogOpen] = useState(false)

  const { data: cocktails = [], isLoading } = useQuery({
    queryKey: ['cocktails', showAll],
    queryFn: () => cocktailsApi.list(undefined, !showAll),
    refetchInterval: 60_000,
  })

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Cocktails</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Pre-mixed batches — stock deducted at mixing, tests tracked against batch
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={() => setLogOpen(true)}>
            <History className="w-3.5 h-3.5" /> Preparation log
          </Button>
          <Button variant="secondary" size="sm" onClick={() => setExportOpen(true)}>
            <Download className="w-3.5 h-3.5" /> Export summary
          </Button>
          <Button variant="secondary" size="sm" onClick={() => setShowAll(v => !v)}>
            {showAll ? 'Active only' : 'Show all'}
          </Button>
          <Button onClick={() => setPrepareOpen(true)}>
            <Plus className="w-4 h-4" /> Prepare cocktail
          </Button>
        </div>
      </div>

      {isLoading ? <Spinner className="py-16" /> : cocktails.length === 0 ? (
        <Card><EmptyState message={showAll ? 'No cocktails on record' : 'No active cocktails'} /></Card>
      ) : (
        <Card padding={false}>
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                {['Panel', 'Prepared', 'Expiry', 'Notes', 'Tests remaining', 'Prepared by', ''].map(h => (
                  <th key={h} className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {(cocktails as Cocktail[]).map(c => {
                const isExpired = c.expiry_date && new Date(c.expiry_date) < new Date()
                const pct = c.pct_remaining
                return (
                  <tr key={c.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-4 py-3">
                      <p className="font-medium text-slate-800">{c.panel_name}</p>
                      {c.cocktail_code && <p className="text-xs font-mono text-slate-400">{c.cocktail_code}</p>}
                    </td>
                    <td className="px-4 py-3 text-slate-500 whitespace-nowrap">
                      {format(parseISO(c.prepared_date), 'd MMM yyyy')}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      {c.expiry_date
                        ? <span className={isExpired ? 'text-red-600 font-medium' : 'text-slate-500'}>
                            {format(parseISO(c.expiry_date), 'd MMM yyyy')}{isExpired ? ' (expired)' : ''}
                          </span>
                        : <span className="text-slate-300">—</span>}
                    </td>
                    <td className="px-4 py-3 text-slate-400 text-xs">{c.lot_notes ?? '—'}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-20 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                          <div className={`h-full rounded-full ${pct < 25 ? 'bg-red-400' : pct < 50 ? 'bg-amber-400' : 'bg-emerald-500'}`}
                            style={{ width: `${pct}%` }} />
                        </div>
                        <span className="text-sm font-medium tabular-nums">{c.remaining_tests}/{c.total_tests}</span>
                        {!c.active && <Badge variant="unknown">Exhausted</Badge>}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-slate-500">{c.prepared_by_name ?? c.prepared_by_username}</td>
                    <td className="px-4 py-3">
                      <div className="flex gap-1.5 items-center justify-end whitespace-nowrap">
                        <Button variant="ghost" size="sm" onClick={() => cocktailsApi.worksheet(c.id)} title="Print worksheet">
                          <Printer className="w-3.5 h-3.5" /> Worksheet
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => setTraceId(c.id)} title="Samples run on this cocktail and its antibody lots">
                          <GitBranch className="w-3.5 h-3.5" /> Trace
                        </Button>
                        {c.active && !isExpired && (
                          <Button variant="secondary" size="sm" onClick={() => setUseCocktail(c)}>
                            <FlaskConical className="w-3.5 h-3.5" /> Log tests
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </Card>
      )}

      <PrepareCocktailModal open={prepareOpen} onClose={() => setPrepareOpen(false)} />
      <UseCocktailModal cocktail={useCocktail} onClose={() => setUseCocktail(null)} />
      <ExportSummaryModal open={exportOpen} onClose={() => setExportOpen(false)} />
      <PrepLogModal open={logOpen} onClose={() => setLogOpen(false)} onTrace={(id) => { setLogOpen(false); setTraceId(id) }} />
      <CocktailTraceModal cocktailId={traceId} onClose={() => setTraceId(null)} onOpenCocktail={setTraceId} />
    </div>
  )
}
