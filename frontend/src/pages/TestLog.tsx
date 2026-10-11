// pages/TestLog.tsx

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import { FlaskConical, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { antibodiesApi, cocktailsApi, panelsApi, testsApi } from '../api/client'
import { Button, Badge, Card, EmptyState, Input, Modal, Select, Spinner } from '../components/ui'
import type { TestLog as TTestLog } from '../types'

// ── Manual entry form ──────────────────────────────────────────────────────

function LogTestForm() {
  const qc = useQueryClient()
  const { data: panels = [] } = useQuery({ queryKey: ['panels'], queryFn: () => panelsApi.list() })
  const { data: cocktails = [] } = useQuery({ queryKey: ['cocktails'], queryFn: () => cocktailsApi.list() as Promise<any[]> })
  const [source, setSource] = useState<'panel' | 'cocktail'>('panel')
  const [form, setForm] = useState({ date: format(new Date(), 'yyyy-MM-dd'), panel_id: '', cocktail_id: '', count: '1', notes: '' })
  const [warnings, setWarnings] = useState<string[]>([])
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState('')

  const mut = useMutation({
    mutationFn: () => {
      if (source === 'cocktail') {
        return cocktailsApi.use(Number(form.cocktail_id), {
          test_date: form.date,
          count: Number(form.count),
          notes: form.notes || undefined,
        })
      }
      return testsApi.create({
        date: form.date,
        panel_id: Number(form.panel_id),
        count: Number(form.count),
        notes: form.notes || undefined,
      })
    },
    onSuccess: (res: any) => {
      qc.invalidateQueries({ queryKey: ['test-logs'] })
      qc.invalidateQueries({ queryKey: ['stock'] })
      qc.invalidateQueries({ queryKey: ['stock-summary'] })
      qc.invalidateQueries({ queryKey: ['forecast-all'] })
      qc.invalidateQueries({ queryKey: ['alerts'] })
      qc.invalidateQueries({ queryKey: ['cocktails'] })
      const w = source === 'panel' ? ((res.data as TTestLog)?.warnings ?? []) : []
      setWarnings(w)
      setSuccess(true)
      setForm((f) => ({ ...f, count: '1', notes: '' }))
      setTimeout(() => setSuccess(false), 4000)
    },
    onError: (e: any) => setError(e.response?.data?.detail ?? 'Failed to log tests'),
  })

  const set = (k: string, v: string) => { setForm((f) => ({ ...f, [k]: v })); setError(''); setSuccess(false) }

  const panel = panels.find((p) => p.id === Number(form.panel_id))
  const cocktail = cocktails.find((c: any) => c.id === Number(form.cocktail_id))

  const canSubmit = source === 'panel'
    ? !!form.panel_id && !!form.count
    : !!form.cocktail_id && !!form.count && Number(form.count) <= (cocktail?.remaining_tests ?? 0)

  return (
    <Card>
      <h2 className="text-sm font-semibold text-slate-900 mb-4">Log Tests</h2>
      <div className="space-y-4">
        {/* Source toggle */}
        <div className="flex gap-2">
          <button
            onClick={() => { setSource('panel'); setError(''); setSuccess(false) }}
            className={`flex-1 px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${source === 'panel' ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-600 border-slate-200 hover:border-blue-300'}`}
          >
            From Panel
          </button>
          <button
            onClick={() => { setSource('cocktail'); setError(''); setSuccess(false) }}
            className={`flex-1 px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${source === 'cocktail' ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-600 border-slate-200 hover:border-blue-300'}`}
          >
            From Cocktail
          </button>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Input label="Date" type="date" value={form.date} onChange={(e) => set('date', e.target.value)} />
          <Input label="Count" type="number" min="1" value={form.count} onChange={(e) => set('count', e.target.value)} />
        </div>

        {source === 'panel' ? (
          <Select label="Panel" value={form.panel_id} onChange={(e) => set('panel_id', e.target.value)}>
            <option value="">Select panel…</option>
            {panels.map((p) => (
              <option key={p.id} value={p.id}>{p.name} ({p.test_code})</option>
            ))}
          </Select>
        ) : (
          <Select label="Cocktail" value={form.cocktail_id} onChange={(e) => set('cocktail_id', e.target.value)}>
            <option value="">Select prepared cocktail…</option>
            {cocktails.map((c: any) => (
              <option key={c.id} value={c.id}>
                {c.panel_name} — {c.remaining_tests} of {c.total_tests} tests left
                {c.lot_notes ? ` (${c.lot_notes})` : ''}
              </option>
            ))}
          </Select>
        )}

        {source === 'panel' && panel && (
          <div className="bg-blue-50 rounded-lg p-3 text-xs text-blue-800 space-y-1">
            <p className="font-medium">Panel: {panel.test_code} — {panel.components.length} antibodies</p>
            <p>
              Per test: {panel.components.map((c) =>
                `${c.antibody_name} ${c.ul_per_test.toFixed(0)}µl`
              ).join(' · ')}
            </p>
            {Number(form.count) > 0 && (
              <p className="font-medium mt-1">
                Total this run:{' '}
                {panel.components.map((c) =>
                  `${c.antibody_name} ${(c.ul_per_test * Number(form.count)).toFixed(0)}µl`
                ).join(' · ')}
              </p>
            )}
          </div>
        )}

        {source === 'cocktail' && cocktail && (
          <div className="bg-violet-50 rounded-lg p-3 text-xs text-violet-800 space-y-1">
            <p className="font-medium">Cocktail: {cocktail.panel_name}</p>
            <p>{cocktail.remaining_tests} of {cocktail.total_tests} tests remaining</p>
            <p className="text-violet-600">Deducts from the prepared cocktail — raw antibody stock is not touched (it was already deducted when the cocktail was mixed).</p>
            {Number(form.count) > cocktail.remaining_tests && (
              <p className="text-red-600 font-medium">⚠ Only {cocktail.remaining_tests} tests left in this cocktail.</p>
            )}
          </div>
        )}

        <Input
          label="Notes (optional)"
          value={form.notes}
          onChange={(e) => set('notes', e.target.value)}
          placeholder="e.g. Monday batch"
        />

        {warnings.length > 0 && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 space-y-1">
            <p className="text-xs font-semibold text-amber-800">Stock warnings</p>
            {warnings.map((w, i) => (
              <p key={i} className="text-xs text-amber-700">{w}</p>
            ))}
          </div>
        )}

        {success && !warnings.length && (
          <p className="text-sm text-emerald-600 font-medium">✓ Logged and updated</p>
        )}
        {error && <p className="text-sm text-red-600">{error}</p>}

        <div className="flex justify-end">
          <Button
            onClick={() => mut.mutate()}
            disabled={mut.isPending || !canSubmit}
          >
            {mut.isPending ? 'Logging…' : 'Log tests'}
          </Button>
        </div>
      </div>
    </Card>
  )
}

// ── CSV Import ─────────────────────────────────────────────────────────────

function CsvImport() {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [result, setResult] = useState<{ created: number; skipped: number; errors: string[] } | null>(null)

  const mut = useMutation({
    mutationFn: (file: File) => testsApi.importCsv(file),
    onSuccess: (data) => {
      setResult(data)
      qc.invalidateQueries({ queryKey: ['test-logs'] })
      qc.invalidateQueries({ queryKey: ['stock'] })
      qc.invalidateQueries({ queryKey: ['stock-summary'] })
    },
  })

  return (
    <Card>
      <h2 className="text-sm font-semibold text-slate-900 mb-1">Import from LIMS (CSV)</h2>
      <p className="text-xs text-slate-400 mb-4">
        Column order: <code className="bg-slate-100 px-1 rounded">date, test_code, count, notes</code>
      </p>

      <div
        className="border-2 border-dashed border-slate-200 rounded-xl p-8 text-center
          hover:border-brand-400 hover:bg-blue-50/50 transition-colors cursor-pointer"
        onClick={() => fileRef.current?.click()}
      >
        <Upload className="w-7 h-7 mx-auto text-slate-300 mb-2" />
        <p className="text-sm text-slate-500">Click to upload CSV</p>
        <p className="text-xs text-slate-400 mt-1">or drag and drop</p>
        <input
          ref={fileRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0]
            if (f) mut.mutate(f)
            e.target.value = ''
          }}
        />
      </div>

      {mut.isPending && <Spinner className="mt-4" />}

      {result && (
        <div className="mt-4 space-y-2">
          <div className={`rounded-lg p-3 text-sm ${result.errors.length ? 'bg-amber-50' : 'bg-emerald-50'}`}>
            <p className="font-medium text-slate-800">
              ✓ {result.created} rows imported
              {result.skipped > 0 && `, ${result.skipped} skipped`}
            </p>
          </div>
          {result.errors.length > 0 && (
            <div className="bg-red-50 rounded-lg p-3 space-y-1 max-h-32 overflow-y-auto">
              {result.errors.map((e, i) => (
                <p key={i} className="text-xs text-red-700">{e}</p>
              ))}
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

// ── Test log history table ──────────────────────────────────────────────────

function TestLogTable() {
  const { data: logs = [], isLoading } = useQuery({
    queryKey: ['test-logs'],
    queryFn: () => testsApi.list({ limit: 50 }),
  })

  return (
    <Card padding={false}>
      <div className="px-5 py-4 border-b border-slate-100">
        <h2 className="text-sm font-semibold text-slate-900">Recent test logs</h2>
      </div>
      {isLoading ? (
        <Spinner className="py-12" />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50">
                {['Date', 'Panel', 'Count', 'Method', 'Consumption', 'Warnings'].map((h) => (
                  <th key={h} className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {logs.length === 0 && (
                <tr><td colSpan={6}><EmptyState message="No test logs yet" /></td></tr>
              )}
              {logs.map((log) => (
                <tr key={log.id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-4 py-2.5 text-slate-600 whitespace-nowrap">
                    {format(parseISO(log.date), 'd MMM yyyy')}
                  </td>
                  <td className="px-4 py-2.5 font-medium text-slate-800">
                    <div className="flex items-center gap-2">
                      {log.panel_name}
                      {log.source === 'cocktail' && (
                        <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-violet-100 text-violet-700">COCKTAIL</span>
                      )}
                      {log.source === 'adhoc' && (
                        <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-amber-100 text-amber-700">AD HOC</span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-2.5 text-slate-600 tabular-nums">{log.count}</td>
                  <td className="px-4 py-2.5">
                    <span className="text-xs text-slate-400 font-mono">{log.entry_method}</span>
                  </td>
                  <td className="px-4 py-2.5 text-xs text-slate-500">
                    {log.source === 'cocktail'
                      ? 'from cocktail'
                      : `${log.consumption.length} lots deducted`}
                  </td>
                  <td className="px-4 py-2.5">
                    {log.warnings.length > 0 && (
                      <span className="text-xs text-amber-600">⚠ {log.warnings.length} warning{log.warnings.length > 1 ? 's' : ''}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}


// ── Ad hoc test form ─────────────────────────────────────────────────────

function AdhocTestForm() {
  const qc = useQueryClient()
  const today = new Date().toISOString().slice(0, 10)

  const { data: antibodies = [] } = useQuery({
    queryKey: ['antibodies'],
    queryFn: () => antibodiesApi.list(),
  })

  const [label, setLabel] = useState('')
  const [testDate, setTestDate] = useState(today)
  const [count, setCount] = useState('1')
  const [notes, setNotes] = useState('')
  const [selected, setSelected] = useState<{antibody_id: number; name: string; fluor: string; volume_ul: string}[]>([])
  const [pickId, setPickId] = useState('')
  const [result, setResult] = useState<{warnings: string[]} | null>(null)

  const addAntibody = () => {
    const ab = antibodies.find(a => a.id === parseInt(pickId))
    if (!ab || selected.find(s => s.antibody_id === ab.id)) return
    setSelected(prev => [...prev, {
      antibody_id: ab.id,
      name: ab.name,
      fluor: ab.fluorochrome?.name ?? '',
      volume_ul: '',
    }])
    setPickId('')
  }

  const setVol = (id: number, val: string) =>
    setSelected(prev => prev.map(s => s.antibody_id === id ? {...s, volume_ul: val} : s))

  const removeAb = (id: number) =>
    setSelected(prev => prev.filter(s => s.antibody_id !== id))

  const mut = useMutation({
    mutationFn: () => testsApi.logAdhoc({
      date: testDate,
      label: label || 'Ad hoc',
      count: parseInt(count),
      notes: notes || undefined,
      items: selected.map(s => ({ antibody_id: s.antibody_id, volume_ul: parseFloat(s.volume_ul) })),
    }),
    onSuccess: (data: any) => {
      qc.invalidateQueries({ queryKey: ['test-logs'] })
      qc.invalidateQueries({ queryKey: ['stock'] })
      setResult({ warnings: data.warnings ?? [] })
      setLabel(''); setNotes(''); setSelected([]); setCount('1'); setTestDate(today)
    },
  })

  const canSubmit = label.trim() && selected.length > 0 &&
    selected.every(s => s.volume_ul && parseFloat(s.volume_ul) > 0) && parseInt(count) > 0

  return (
    <Card>
      <h2 className="text-sm font-semibold text-slate-900 mb-4 flex items-center gap-2">
        <FlaskConical className="w-4 h-4" /> Ad hoc / Custom Test
      </h2>
      <div className="space-y-3">
        <Input label="Label / test name" value={label} onChange={e => setLabel(e.target.value)} placeholder="e.g. QC run, Custom IEI" />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Date" type="date" value={testDate} onChange={e => setTestDate(e.target.value)} />
          <Input label="No. of patients" type="number" min="1" value={count} onChange={e => setCount(e.target.value)} />
        </div>

        {/* Antibody picker */}
        <div>
          <label className="text-xs font-medium text-slate-600 block mb-1">Add antibodies</label>
          <div className="flex gap-2">
            <select
              value={pickId}
              onChange={e => setPickId(e.target.value)}
              className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">Select antibody…</option>
              {antibodies.filter(ab => ab.active && !selected.find(s => s.antibody_id === ab.id)).map(ab => (
                <option key={ab.id} value={ab.id}>
                  {ab.name}{ab.fluorochrome ? ` (${ab.fluorochrome.name})` : ''}
                </option>
              ))}
            </select>
            <Button variant="secondary" size="sm" onClick={addAntibody} disabled={!pickId}>Add</Button>
          </div>
        </div>

        {/* Selected antibodies table */}
        {selected.length > 0 && (
          <div className="border border-slate-200 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50">
                  <th className="text-left px-3 py-2 text-xs font-medium text-slate-500">Antibody</th>
                  <th className="text-left px-3 py-2 text-xs font-medium text-slate-500">Fluor</th>
                  <th className="text-left px-3 py-2 text-xs font-medium text-slate-500">µl / patient</th>
                  <th className="px-2 py-2"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {selected.map(s => (
                  <tr key={s.antibody_id}>
                    <td className="px-3 py-1.5 font-medium text-slate-700">{s.name}</td>
                    <td className="px-3 py-1.5 text-slate-500 text-xs">{s.fluor}</td>
                    <td className="px-3 py-1.5">
                      <input
                        type="number" min="0" step="0.5"
                        value={s.volume_ul}
                        onChange={e => setVol(s.antibody_id, e.target.value)}
                        placeholder="µl"
                        className="w-20 border border-slate-200 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-400"
                      />
                    </td>
                    <td className="px-2 py-1.5">
                      <button onClick={() => removeAb(s.antibody_id)} className="text-slate-300 hover:text-red-500 text-xs">✕</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <Input label="Notes (optional)" value={notes} onChange={e => setNotes(e.target.value)} placeholder="Reason for ad hoc run…" />

        {result && (
          <div className="text-sm text-green-700 bg-green-50 rounded p-3">
            ✓ Logged.
            {result.warnings.length > 0 && (
              <ul className="mt-1 text-amber-700">
                {result.warnings.map((w, i) => <li key={i}>⚠ {w}</li>)}
              </ul>
            )}
          </div>
        )}

        <Button onClick={() => mut.mutate()} disabled={!canSubmit || mut.isPending} className="w-full">
          {mut.isPending ? 'Logging…' : 'Log ad hoc test'}
        </Button>
      </div>
    </Card>
  )
}

// ── Page ────────────────────────────────────────────────────────────────────

export default function TestLogPage() {
  return (
    <div className="p-6 space-y-5">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Test Log</h1>
        <p className="text-sm text-slate-500 mt-0.5">Log tests to deduct antibody volumes from stock</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <LogTestForm />
        <CsvImport />
      </div>

      <AdhocTestForm />

      <TestLogTable />
    </div>
  )
}
