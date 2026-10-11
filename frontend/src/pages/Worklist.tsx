// pages/Worklist.tsx — sample order worklist (replaces the staff Google sheet)

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format, parseISO, subDays } from 'date-fns'
import {
  ClipboardList, Plus, X, Play, CheckCircle2, XCircle,
  RefreshCw, Download, ScanLine, AlertTriangle, Search, FlaskConical, MessageSquarePlus,
} from 'lucide-react'
import { useRef, useState } from 'react'
import { panelsApi, sampleOrdersApi, staffApi } from '../api/client'
import { Badge, Button, Card, EmptyState, Input, Modal, Select, Spinner } from '../components/ui'
import CocktailTraceModal from '../components/CocktailTraceModal'
import type { CocktailShortfall, Panel, SampleOrder, Staff } from '../types'
import { useSampleFlags } from '../hooks/useSampleFlags'

// ── helpers ──────────────────────────────────────────────────────────────────

function fmtTat(min: number | null): string {
  if (min == null) return '—'
  if (min < 60) return `${Math.round(min)}m`
  const h = Math.floor(min / 60)
  const m = Math.round(min % 60)
  return m ? `${h}h ${m}m` : `${h}h`
}

const STATUS_LABEL: Record<string, string> = {
  in_queue: 'In queue',
  in_processing: 'Processing',
  completed: 'Completed',
  cancelled: 'Cancelled',
}

function statusVariant(s: string): 'pending' | 'info' | 'ok' | 'unknown' {
  if (s === 'in_queue') return 'pending'
  if (s === 'in_processing') return 'info'
  if (s === 'completed') return 'ok'
  return 'unknown'
}

// ── Create order form ────────────────────────────────────────────────────────

function CreateOrderForm() {
  const qc = useQueryClient()
  const labIdRef = useRef<HTMLInputElement>(null)

  const { data: panels = [] } = useQuery({ queryKey: ['panels'], queryFn: () => panelsApi.list() })
  const { data: pathologists = [] } = useQuery({ queryKey: ['staff', 'pathologist'], queryFn: () => staffApi.list('pathologist') })
  const { data: technologists = [] } = useQuery({ queryKey: ['staff', 'technologist'], queryFn: () => staffApi.list('technologist') })
  const { data: availability = {} } = useQuery({
    queryKey: ['cocktail-availability'],
    queryFn: () => sampleOrdersApi.availability(),
    refetchInterval: 30_000,
  })

  const [labId, setLabId] = useState('')
  const [pathologistId, setPathologistId] = useState('')
  const [technologistId, setTechnologistId] = useState('')
  const [priority, setPriority] = useState<'routine' | 'urgent'>('routine')
  const [notes, setNotes] = useState('')
  const [pickPanel, setPickPanel] = useState('')
  const [tubes, setTubes] = useState<{ key: number; panel_id: number; test_code: string; name: string }[]>([])
  const [shortfalls, setShortfalls] = useState<CocktailShortfall[] | null>(null)
  const [success, setSuccess] = useState('')
  const [error, setError] = useState('')

  const avail = (panelId: number) => availability[String(panelId)] ?? 0

  const addTube = () => {
    const p = panels.find((x) => x.id === Number(pickPanel))
    if (!p) return
    setTubes((t) => [...t, { key: Date.now() + Math.random(), panel_id: p.id, test_code: p.test_code, name: p.name }])
    setPickPanel('')
    setShortfalls(null)
    setSuccess('')
  }

  const removeTube = (key: number) => setTubes((t) => t.filter((x) => x.key !== key))

  // count how many tubes of each panel are already queued in THIS draft (for live availability hint)
  const draftCountByPanel = tubes.reduce<Record<number, number>>((acc, t) => {
    acc[t.panel_id] = (acc[t.panel_id] ?? 0) + 1
    return acc
  }, {})

  const mut = useMutation({
    mutationFn: () =>
      sampleOrdersApi.create({
        lab_id: labId.trim(),
        requesting_pathologist_id: pathologistId ? Number(pathologistId) : undefined,
        processing_technologist_id: technologistId ? Number(technologistId) : undefined,
        priority,
        notes: notes.trim() || undefined,
        tubes: tubes.map((t) => ({ panel_id: t.panel_id })),
      }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['sample-orders'] })
      qc.invalidateQueries({ queryKey: ['cocktail-availability'] })
      qc.invalidateQueries({ queryKey: ['cocktails'] })
      const sf = (res.data as SampleOrder)?.cocktail_shortfalls
      if (res.status === 207 && sf?.length) {
        setShortfalls(sf)
        setSuccess(`Order ${labId.trim()} created — some tubes are awaiting cocktail.`)
      } else {
        setShortfalls(null)
        setSuccess(`Order ${labId.trim()} added to the queue.`)
      }
      // reset for the next sample; keep pathologist/tech for a faster run of batched samples
      setLabId('')
      setNotes('')
      setTubes([])
      setPriority('routine')
      labIdRef.current?.focus()
    },
    onError: (e: any) => setError(e.response?.data?.detail ?? 'Could not create order'),
  })

  const canSubmit = labId.trim() && tubes.length > 0

  return (
    <Card>
      <h2 className="text-sm font-semibold text-slate-900 mb-4 flex items-center gap-2">
        <Plus className="w-4 h-4" /> New sample order
      </h2>

      <div className="space-y-4">
        {/* Lab ID — barcode target */}
        <div>
          <label className="text-sm font-medium text-slate-700 flex items-center gap-1.5 mb-1">
            <ScanLine className="w-3.5 h-3.5 text-slate-400" /> Lab ID
          </label>
          <input
            ref={labIdRef}
            autoFocus
            value={labId}
            onChange={(e) => { setLabId(e.target.value); setError(''); setSuccess('') }}
            onKeyDown={(e) => { if (e.key === 'Enter') e.preventDefault() }}
            placeholder="Scan or type accession…"
            className="w-full px-3.5 py-2 text-sm border border-slate-300 rounded-lg font-mono tracking-tight focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
          />
          <p className="text-xs text-slate-400 mt-1">A USB scanner types the value automatically — the field is ready as soon as the page loads.</p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Select label="Requesting pathologist" value={pathologistId} onChange={(e) => setPathologistId(e.target.value)}>
            <option value="">Select…</option>
            {pathologists.map((s: Staff) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </Select>
          <Select label="Processing technologist" value={technologistId} onChange={(e) => setTechnologistId(e.target.value)}>
            <option value="">Select…</option>
            {technologists.map((s: Staff) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </Select>
        </div>

        {(pathologists.length === 0 || technologists.length === 0) && (
          <p className="text-xs text-amber-600">
            Add pathologists and technologists under <span className="font-medium">Admin → Staff</span> to populate these lists.
          </p>
        )}

        {/* Priority */}
        <div>
          <label className="text-sm font-medium text-slate-700 block mb-1">Priority</label>
          <div className="flex gap-2">
            {(['routine', 'urgent'] as const).map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setPriority(p)}
                className={`flex-1 px-3 py-1.5 rounded-lg text-sm font-medium border capitalize transition-colors ${
                  priority === p
                    ? p === 'urgent' ? 'bg-red-600 text-white border-red-600' : 'bg-brand-600 text-white border-brand-600'
                    : 'bg-white text-slate-600 border-slate-200 hover:border-brand-300'
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        {/* Tube picker */}
        <div>
          <label className="text-sm font-medium text-slate-700 block mb-1">Tubes</label>
          <div className="flex gap-2">
              <select
                value={pickPanel}
                onChange={(e) => setPickPanel(e.target.value)}
                className="flex-1 min-w-0 border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white truncate focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                <option value="">Add a tube…</option>
                {panels.map((p: Panel) => {
                  const free = avail(p.id) - (draftCountByPanel[p.id] ?? 0)
                  const fullLabel = `${p.test_code} — ${p.name} (${free > 0 ? `${free} cocktail test${free === 1 ? '' : 's'} free` : 'no cocktail'})`
                  const truncatedLabel = fullLabel.length > 50 ? fullLabel.slice(0, 47) + '…' : fullLabel
                  return (
                    <option key={p.id} value={p.id} title={fullLabel}>
                      {truncatedLabel}
                    </option>
                  )
                })}
              </select>
            <Button variant="secondary" size="sm" onClick={addTube} disabled={!pickPanel}>Add</Button>
          </div>

          {tubes.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2.5">
              {tubes.map((t) => {
                const free = avail(t.panel_id)
                const queuedBefore = tubes.filter((x) => x.panel_id === t.panel_id && x.key <= t.key).length
                const willReserve = queuedBefore <= free
                return (
                  <span
                    key={t.key}
                    className={`inline-flex items-center gap-1 pl-2 pr-1 py-1 rounded-md text-xs font-medium border ${
                      willReserve
                        ? 'bg-brand-50 text-brand-700 border-brand-200'
                        : 'bg-amber-50 text-amber-700 border-amber-200'
                    }`}
                    title={willReserve ? 'A cocktail test is available' : 'No cocktail available — will be flagged'}
                  >
                    {t.test_code}
                    {!willReserve && <AlertTriangle className="w-3 h-3" />}
                    <button onClick={() => removeTube(t.key)} className="ml-0.5 text-slate-400 hover:text-red-500">
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                )
              })}
            </div>
          )}
        </div>

        <Input label="Notes (optional)" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. urgent — clinician called" />

        {shortfalls && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 space-y-1">
            <p className="text-xs font-semibold text-amber-800 flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5" /> Cocktails insufficient
            </p>
            {shortfalls.map((s) => (
              <p key={s.panel_id} className="text-xs text-amber-700">
                {s.test_code}: {s.tubes_short} tube{s.tubes_short === 1 ? '' : 's'} could not be reserved. Prepare a cocktail, then use “Reserve” on the order.
              </p>
            ))}
          </div>
        )}
        {success && !shortfalls && <p className="text-sm text-emerald-600 font-medium">✓ {success}</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}

        <div className="flex justify-end">
          <Button onClick={() => mut.mutate()} disabled={mut.isPending || !canSubmit}>
            {mut.isPending ? 'Creating…' : 'Add to queue'}
          </Button>
        </div>
      </div>
    </Card>
  )
}

// ── Sample comment and flags ─────────────────────────────────────────────────

// Free-text quick picks. Fibrin threads / low volume / lyse issue are one-tap
// flags instead (shared with the bench tablet), so they are not repeated here.
const QUICK_COMMENTS = [
  'Clotted', 'Degenerated / poor viability', 'Low cell count', 'Haemolysed', 'Diluted / haemodilute',
]

function FlagPills({ codes, label, size = 'sm' }: { codes: string[]; label: (c: string) => string; size?: 'sm' | 'xs' }) {
  if (!codes.length) return null
  return (
    <span className="inline-flex flex-wrap gap-1">
      {codes.map((c) => (
        <span key={c} className={`inline-flex items-center whitespace-nowrap rounded border border-amber-300 bg-amber-100 text-amber-900 font-medium ${
          size === 'xs' ? 'px-1 text-[10px]' : 'px-1.5 py-0.5 text-[11px]'}`}>
          {label(c)}
        </span>
      ))}
    </span>
  )
}

function SampleComment({ order }: { order: SampleOrder }) {
  const qc = useQueryClient()
  const { options: flagOptions, label } = useSampleFlags()
  // Everyone on the staff list: pathologists add comments too. Never pre-filled,
  // so one person's name can't carry over onto someone else's entry.
  const { data: staff = [] } = useQuery({ queryKey: ['staff', 'all'], queryFn: () => staffApi.list() })
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState('')
  const [flags, setFlags] = useState<string[]>([])
  const [staffId, setStaffId] = useState('')
  const [error, setError] = useState('')

  const commentChanged = text.trim() !== (order.sample_comment ?? '')
  const flagChanges = flagOptions
    .map((o) => o.code)
    .filter((c) => flags.includes(c) !== order.sample_flags.includes(c))
  const dirty = commentChanged || flagChanges.length > 0

  const save = useMutation({
    mutationFn: async () => {
      const sid = Number(staffId)
      for (const code of flagChanges) await sampleOrdersApi.setSampleFlag(order.id, code, flags.includes(code), sid)
      if (commentChanged) await sampleOrdersApi.setSampleComment(order.id, text, sid)
    },
    onSuccess: () => { setEditing(false); setError('') },
    onError: (e: any) => setError(e.response?.data?.detail ?? 'Could not save'),
    onSettled: () => qc.invalidateQueries({ queryKey: ['sample-orders'] }),
  })

  const open = () => {
    setText(order.sample_comment ?? ''); setFlags(order.sample_flags); setStaffId(''); setError(''); setEditing(true)
  }
  const toggleFlag = (c: string) => setFlags((f) => (f.includes(c) ? f.filter((x) => x !== c) : [...f, c]))
  const addQuick = (q: string) =>
    setText((t) => (t.toLowerCase().includes(q.toLowerCase()) ? t : t.trim() ? `${t.trim()}; ${q}` : q))

  const has = order.sample_comment || order.sample_flags.length > 0
  const who = [
      order.sample_flags.length ? `Flags: ${order.sample_flags_staff_name ?? '—'}${order.sample_flags_updated_at ? `, ${format(parseISO(order.sample_flags_updated_at), 'd MMM HH:mm')}` : ''}` : '',
      order.sample_comment ? `Comment: ${order.sample_comment_staff_name ?? order.sample_comment_updated_by ?? '—'}${order.sample_comment_updated_at ? `, ${format(parseISO(order.sample_comment_updated_at), 'd MMM HH:mm')}` : ''}` : '',
    ].filter(Boolean).join('\n')
  const display = has ? (
      <button type="button" onClick={open} title={`${who}\n\nClick to edit`}
        className="block text-left max-w-[11rem] space-y-1 rounded px-1 py-0.5 -mx-1 hover:bg-slate-50">
        <FlagPills codes={order.sample_flags} label={label} />
        {order.sample_comment && (
          <span className="block text-xs text-amber-900 bg-amber-50 border border-amber-200 rounded px-1.5 py-1">
            <span className="line-clamp-2">{order.sample_comment}</span>
          </span>
        )}
      </button>
    ) : (
      <button type="button" onClick={open} className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-brand-700"
        title="Add sample flags or a comment">
        <MessageSquarePlus className="w-3.5 h-3.5" /> Add
      </button>
    )

  // Edited in a modal, not inline: an inline editor widened the table and left
  // its horizontal scroller shifted (hiding the Lab ID column) after closing.
  return (
    <>
    {display}
    <Modal open={editing} onClose={() => setEditing(false)} title={`Sample ${order.lab_id} — flags and comment`}>
    <div className="space-y-3">
      <select
        value={staffId} onChange={(e) => setStaffId(e.target.value)}
        className={`w-full px-3 py-2 text-sm border rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-brand-500 ${
          staffId ? 'border-slate-300' : 'border-amber-400'}`}
      >
        <option value="">Who is entering this? *</option>
        {staff.map((p: Staff) => <option key={p.id} value={p.id}>{p.name}{p.role === 'pathologist' ? ' (pathologist)' : ''}</option>)}
      </select>
      {flagOptions.length > 0 && (
        <div className="flex flex-wrap gap-1" role="group" aria-label="Sample flags">
          {flagOptions.map((o) => {
            const on = flags.includes(o.code)
            return (
              <button key={o.code} type="button" aria-pressed={on} onClick={() => toggleFlag(o.code)}
                className={`inline-flex items-center gap-1 px-3 py-1.5 text-sm font-medium rounded-lg border ${
                  on ? 'bg-amber-500 border-amber-500 text-white' : 'border-slate-300 text-slate-600 hover:border-amber-400'}`}>
                {on && <CheckCircle2 className="w-3 h-3" />}{o.label}
              </button>
            )
          })}
        </div>
      )}
      <textarea
        value={text} onChange={(e) => setText(e.target.value)} rows={3} maxLength={512}
        placeholder="Comment, e.g. small clot, run after filtering"
        className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500"
        onKeyDown={(e) => {
          if (e.key === 'Escape') setEditing(false)
          if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && staffId && dirty) save.mutate()
        }}
      />
      <div className="flex flex-wrap gap-1">
        {QUICK_COMMENTS.map((q) => (
          <button key={q} type="button" onClick={() => addQuick(q)}
            className="px-2 py-1 text-xs rounded border border-slate-200 text-slate-600 hover:border-brand-400 hover:text-brand-700">
            {q}
          </button>
        ))}
      </div>
      {error && <p className="text-xs text-red-600">{error}</p>}
      <div className="flex justify-end gap-1">
        <Button variant="secondary" size="sm" onClick={() => setEditing(false)}>Cancel</Button>
        <Button size="sm" disabled={save.isPending || !staffId || !dirty} onClick={() => save.mutate()}
          title={!staffId ? 'Choose who is entering this first' : undefined}>Save</Button>
      </div>
    </div>
    </Modal>
    </>
  )
}

// ── Worklist table ───────────────────────────────────────────────────────────

function tubeBadge(status: string) {
  if (status === 'reserved') return 'bg-brand-50 text-brand-700 border-brand-200'
  if (status === 'consumed') return 'bg-slate-100 text-slate-500 border-slate-200'
  return 'bg-amber-50 text-amber-700 border-amber-200'  // awaiting_cocktail
}

function OrderRow({ order, onTrace }: { order: SampleOrder; onTrace: (cocktailId: number, labId: string) => void }) {
  const qc = useQueryClient()
  const [error, setError] = useState('')

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['sample-orders'] })
    qc.invalidateQueries({ queryKey: ['cocktail-availability'] })
    qc.invalidateQueries({ queryKey: ['cocktails'] })
  }

  const startMut = useMutation({
    mutationFn: () => sampleOrdersApi.start(order.id),
    onSuccess: invalidate,
    onError: (e: any) => setError(e.response?.data?.detail ?? 'Could not start'),
  })
  const reserveMut = useMutation({
    mutationFn: () => sampleOrdersApi.reserve(order.id),
    onSuccess: invalidate,
    onError: (e: any) => setError(e.response?.data?.detail ?? 'Could not reserve'),
  })
  const completeMut = useMutation({
    mutationFn: () => sampleOrdersApi.complete(order.id),
    onSuccess: invalidate,
    onError: (e: any) => setError(e.response?.data?.detail ?? 'Could not complete'),
  })
  const cancelMut = useMutation({
    mutationFn: () => sampleOrdersApi.cancel(order.id),
    onSuccess: invalidate,
    onError: (e: any) => setError(e.response?.data?.detail ?? 'Could not cancel'),
  })

  const busy = startMut.isPending || reserveMut.isPending || completeMut.isPending || cancelMut.isPending
  const closed = order.status === 'completed' || order.status === 'cancelled'

  return (
    <tr className={closed ? 'opacity-60' : ''}>
      <td className="px-3 py-2.5">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm font-medium text-slate-800 whitespace-nowrap">{order.lab_id}</span>
          {order.priority === 'urgent' && order.status !== 'completed' && order.status !== 'cancelled' && (
            <Badge variant="critical">urgent</Badge>
          )}
        </div>
        {order.ordered_at && (
          <p className="text-xs text-slate-400 mt-0.5 whitespace-nowrap">{format(parseISO(order.ordered_at), 'd MMM, HH:mm')}</p>
        )}
        {/* Flags and comment sit under the lab ID, against the sample number */}
        <div className="mt-1"><SampleComment order={order} /></div>
      </td>

      <td className="px-3 py-2.5">
        <div className="flex flex-wrap gap-1.5">
          {order.tubes.map((t) => (
            <div key={t.id} className="flex flex-col items-start gap-0.5">
              <span
                className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium border ${tubeBadge(t.status)}`}
                title={t.status === 'awaiting_cocktail' ? 'No cocktail reserved' : t.status === 'reserved' ? 'Cocktail test reserved' : 'Cocktail consumed'}
              >
                {t.test_code}
                {t.status === 'awaiting_cocktail' && <AlertTriangle className="w-2.5 h-2.5" />}
                {t.steps_total > 0 && (t.steps_done > 0 || order.status === 'in_processing') && (
                  <span className="font-normal opacity-70 tabular-nums">{t.steps_done}/{t.steps_total}</span>
                )}
              </span>
              {order.status === 'in_processing' && t.current_step && (
                <span className="text-[11px] text-brand-700" title="Next step on the bench station">→ {t.current_step}</span>
              )}
              {t.reserved_cocktail_id != null && (
                <button
                  type="button"
                  onClick={() => onTrace(t.reserved_cocktail_id!, order.lab_id)}
                  className="inline-flex items-center gap-0.5 text-[11px] font-mono text-slate-500 hover:text-brand-700 hover:underline"
                  title="Show every sample run on this cocktail, and its antibody lots"
                >
                  <FlaskConical className="w-2.5 h-2.5" />
                  {t.cocktail_code ?? `#${t.reserved_cocktail_id}`}
                </button>
              )}
            </div>
          ))}
        </div>
      </td>

      <td className="px-3 py-2.5 text-sm text-slate-600">
        <div>{order.requesting_pathologist_name ?? '—'}</div>
        <div className="text-xs text-slate-400">{order.processing_technologist_name ?? 'unassigned'}</div>
      </td>

      <td className="px-3 py-2.5">
        <Badge variant={statusVariant(order.status)}>{STATUS_LABEL[order.status]}</Badge>
        {order.status === 'in_queue' && order.awaiting_count > 0 && (
          <p className="text-xs text-amber-600 mt-1">{order.awaiting_count} awaiting cocktail</p>
        )}
      </td>

      <td className="px-3 py-2.5 text-sm tabular-nums text-slate-600">{fmtTat(order.tat_minutes)}</td>

      <td className="px-3 py-2.5">
        <div className="flex items-center justify-end gap-1.5">
          {error && <span className="text-xs text-red-600 mr-1">{error}</span>}

          {order.status === 'in_queue' && order.awaiting_count > 0 && (
            <Button variant="secondary" size="sm" onClick={() => { setError(''); reserveMut.mutate() }} disabled={busy}>
              <RefreshCw className="w-3.5 h-3.5" /> Reserve
            </Button>
          )}
          {order.status === 'in_queue' && (
            <Button size="sm" onClick={() => { setError(''); startMut.mutate() }} disabled={busy || order.awaiting_count > 0}>
              <Play className="w-3.5 h-3.5" /> Start
            </Button>
          )}
          {order.status === 'in_processing' && (
            <Button size="sm" onClick={() => {
              const left = order.tubes.reduce((n, t) => n + Math.max(0, t.steps_total - t.steps_done), 0)
              if (left > 0 && !confirm(`Mark all ${left} remaining processing step${left === 1 ? '' : 's'} for ${order.lab_id} as done and complete the sample?\n\nUse the bench station if the steps are still being done.`)) return
              setError(''); completeMut.mutate()
            }} disabled={busy}>
              <CheckCircle2 className="w-3.5 h-3.5" /> Complete
            </Button>
          )}
          {!closed && (
            <Button variant="ghost" size="sm" onClick={() => { setError(''); cancelMut.mutate() }} disabled={busy} title="Cancel order">
              <XCircle className="w-3.5 h-3.5" />
            </Button>
          )}
        </div>
      </td>
    </tr>
  )
}

function Worklist() {
  const today = format(new Date(), 'yyyy-MM-dd')
  const weekAgo = format(subDays(new Date(), 7), 'yyyy-MM-dd')

  const [dateField, setDateField] = useState<'ordered_at' | 'completed_at'>('ordered_at')
  const [startDate, setStartDate] = useState(weekAgo)
  const [endDate, setEndDate] = useState(today)
  const [labSearch, setLabSearch] = useState('')
  const [trace, setTrace] = useState<{ cocktailId: number; labId?: string } | null>(null)

  // A lab ID search ignores the date range — the sample you are chasing may be old.
  const searching = labSearch.trim().length > 0
  const params = searching
    ? { lab_id: labSearch.trim() }
    : { start_date: startDate || undefined, end_date: endDate || undefined, date_field: dateField }

  const { data: orders = [], isLoading } = useQuery({
    queryKey: ['sample-orders', searching ? 'search' : dateField, searching ? labSearch.trim() : startDate, endDate],
    queryFn: () => sampleOrdersApi.list(params),
    refetchInterval: 30_000,
  })

  const pending = orders.filter((o) => o.status === 'in_queue' || o.status === 'in_processing')
  const closed = orders.filter((o) => o.status === 'completed' || o.status === 'cancelled')

  return (
    <Card padding={false}>
      <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
        <h2 className="text-sm font-semibold text-slate-900">Worklist</h2>
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <span>{pending.length} pending</span>
          <span className="text-slate-300">·</span>
          <span>{closed.length} closed</span>
          <Button variant="secondary" size="sm" onClick={() => sampleOrdersApi.exportCsv(startDate || undefined, endDate || undefined)}>
            <Download className="w-3.5 h-3.5" /> Export TAT
          </Button>
        </div>
      </div>

      {/* Date filter bar */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-5 py-2.5 border-b border-slate-100 bg-slate-50/50">
        <div className={`flex rounded-lg border border-slate-200 overflow-hidden ${searching ? 'opacity-40 pointer-events-none' : ''}`}>
          {(['ordered_at', 'completed_at'] as const).map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setDateField(f)}
              className={`px-3 py-1.5 text-xs font-medium whitespace-nowrap transition-colors ${
                dateField === f
                  ? 'bg-brand-600 text-white'
                  : 'bg-white text-slate-500 hover:text-slate-700'
              }`}
            >
              {f === 'ordered_at' ? 'Request date' : 'Completion date'}
            </button>
          ))}
        </div>
        <input
          type="date"
          value={startDate}
          onChange={(e) => setStartDate(e.target.value)}
          className="px-2.5 py-1.5 text-xs border border-slate-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
        />
        <span className="text-xs text-slate-400">to</span>
        <input
          type="date"
          value={endDate}
          onChange={(e) => setEndDate(e.target.value)}
          className="px-2.5 py-1.5 text-xs border border-slate-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
        />
        <span className="text-xs text-slate-400 ml-1 whitespace-nowrap">{orders.length} result{orders.length !== 1 ? 's' : ''}</span>
        <div className="relative ml-auto">
          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
          <input
            value={labSearch}
            onChange={(e) => setLabSearch(e.target.value)}
            placeholder="Find lab ID (all dates)…"
            className="pl-8 pr-2.5 py-1.5 w-52 text-xs font-mono border border-slate-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
          />
        </div>
      </div>

      {isLoading ? (
        <Spinner className="py-16" />
      ) : orders.length === 0 ? (
        <EmptyState message={searching ? `No sample orders with a lab ID containing "${labSearch.trim()}".` : 'No sample orders match this date range. Try a wider range or switch the date field.'} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs font-medium text-slate-500 border-b border-slate-100">
                <th className="px-3 py-2.5">Lab ID</th>
                <th className="px-3 py-2.5">Tubes</th>
                <th className="px-3 py-2.5">Pathologist / Tech</th>
                <th className="px-3 py-2.5">Status</th>
                <th className="px-3 py-2.5">TAT</th>
                <th className="px-3 py-2.5"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {pending.map((o) => <OrderRow key={o.id} order={o} onTrace={(id, lab) => setTrace({ cocktailId: id, labId: lab })} />)}
              {closed.length > 0 && pending.length > 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-1.5 bg-slate-50/60 text-xs font-medium text-slate-400 uppercase tracking-wide">
                    Closed
                  </td>
                </tr>
              )}
              {closed.map((o) => <OrderRow key={o.id} order={o} onTrace={(id, lab) => setTrace({ cocktailId: id, labId: lab })} />)}
            </tbody>
          </table>
        </div>
      )}

      <CocktailTraceModal
        cocktailId={trace?.cocktailId ?? null}
        highlightLabId={trace?.labId}
        onClose={() => setTrace(null)}
        onOpenCocktail={(id) => setTrace({ cocktailId: id })}
      />
    </Card>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function WorklistPage() {
  return (
    <div className="p-6 space-y-5">
      <div>
        <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2">
          <ClipboardList className="w-5 h-5 text-brand-600" /> Worklist
        </h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Order tubes per sample, reserve cocktail tests, and track turnaround from request to acquisition.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(300px,360px)_1fr] 2xl:grid-cols-[minmax(340px,420px)_1fr] gap-5 items-start">
        <CreateOrderForm />
        {/* min-w-0 lets the table's own horizontal scroller work instead of the
            table stretching this grid column past the viewport */}
        <div className="min-w-0"><Worklist /></div>
      </div>
    </div>
  )
}
