// pages/Station.tsx — bench processing station (touchscreen tablet).
//
// Kitchen-display style: each pending sample is a ticket. Each tube shows its
// steps in order; the next step is a big button. Step 1 ("cocktail added")
// consumes the tube's reserved cocktail test. When every tube is done the
// ticket leaves the board (kept briefly under "Just finished" for undo).

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import {
  AlertTriangle, Bell, BellOff, Check, ChevronDown, ChevronUp, Maximize, RotateCcw, Settings,
  Timer, User as UserIcon,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { sampleOrdersApi, stationApi, staffApi } from '../api/client'
import { useSampleFlags } from '../hooks/useSampleFlags'
import { useAuth } from '../auth/AuthContext'
import type { Staff, StationOrder, StationTube } from '../types'

const OPERATOR_KEY = 'flowjai_station_operator'
const STATION_FLAG = 'flowjai_station_session'
const SOUND_KEY = 'flowjai_station_sound'
const OVERDUE_GRACE_MIN = 10   // a ready step left this long turns amber (e.g. over-incubation)
const ALARM_REPEAT_SEC = 30    // chime again this often until someone taps OK

// Flash animations for the timer alarm (screen edge, banner, ticket)
const ALARM_CSS = `
@keyframes fj-edge { 0%,100% { opacity: 1 } 50% { opacity: .15 } }
@keyframes fj-banner { 0%,100% { filter: brightness(1) } 50% { filter: brightness(1.35) } }
@keyframes fj-ring { 0%,100% { box-shadow: 0 0 0 4px var(--fj-c) } 50% { box-shadow: 0 0 0 10px transparent } }
`

interface Alarm { key: string; orderId: number; labId: string; test: string; step: string; overMin: number }

function mmss(totalSec: number) {
  const s = Math.max(0, Math.round(totalSec))
  const m = Math.floor(s / 60)
  return `${m}:${String(s % 60).padStart(2, '0')}`
}

// One short two-tone chime. Browsers only allow audio after the user has tapped
// the page, which always happens here (choosing the operator).
let audioCtx: AudioContext | null = null
function chime() {
  try {
    audioCtx = audioCtx ?? new (window.AudioContext || (window as any).webkitAudioContext)()
    const t0 = audioCtx.currentTime
    ;[880, 1320].forEach((f, i) => {
      const o = audioCtx!.createOscillator(), g = audioCtx!.createGain()
      o.frequency.value = f
      g.gain.setValueAtTime(0.0001, t0 + i * 0.18)
      g.gain.exponentialRampToValueAtTime(0.35, t0 + i * 0.18 + 0.02)
      g.gain.exponentialRampToValueAtTime(0.0001, t0 + i * 0.18 + 0.16)
      o.connect(g).connect(audioCtx!.destination)
      o.start(t0 + i * 0.18); o.stop(t0 + i * 0.18 + 0.17)
    })
  } catch { /* no audio available */ }
}

/** Seconds until a step's timer runs out (negative once it has), or null if it has none. */
function secondsLeft(readyAt: string | null, nowMs: number): number | null {
  return readyAt ? (parseISO(readyAt).getTime() - nowMs) / 1000 : null
}

function waitClass(min: number | null) {
  if (min == null) return 'text-slate-500'
  if (min >= 60) return 'text-red-600'
  if (min >= 30) return 'text-amber-600'
  return 'text-slate-500'
}

function fmtWait(min: number | null) {
  if (min == null) return ''
  if (min < 60) return `${min} min`
  return `${Math.floor(min / 60)} h ${min % 60} min`
}

// ── One tube row ─────────────────────────────────────────────────────────────

function TubeRow({
  tube, operatorId, busy, nowMs, onComplete, onUndo,
}: {
  tube: StationTube
  operatorId: number | null
  busy: boolean
  nowMs: number
  onComplete: (tube: StationTube, seq: number, force: boolean) => void
  onUndo: (tube: StationTube, seq: number) => void
}) {
  const [confirmUndo, setConfirmUndo] = useState(false)
  const [confirmEarly, setConfirmEarly] = useState(false)
  const undoStep = tube.steps.find((s) => s.seq === tube.undo_seq)
  const nextStep = tube.steps.find((s) => s.seq === tube.next_seq)
  const left = nextStep ? secondsLeft(nextStep.ready_at, nowMs) : null

  return (
    <div className="py-3 first:pt-0 last:pb-0">
      <div className="flex items-baseline gap-2 mb-2">
        <span className="text-lg font-bold text-slate-900">{tube.test_code}</span>
        {tube.cocktail_code && <span className="text-xs font-mono text-slate-400">{tube.cocktail_code}</span>}
        {tube.status === 'awaiting_cocktail' && (
          <span className="inline-flex items-center gap-1 text-xs font-medium text-amber-700">
            <AlertTriangle className="w-3.5 h-3.5" /> no cocktail reserved
          </span>
        )}
        {tube.done && <span className="ml-auto text-sm font-semibold text-emerald-700">Done</span>}
      </div>

      <div className="flex flex-wrap gap-2">
        {tube.steps.map((s) => {
          const isNext = s.seq === tube.next_seq
          const isDone = !!s.completed_at
          const undoable = s.seq === tube.undo_seq
          if (isNext) {
            const running = left != null && left > 0
            const overMin = left != null && left <= 0 ? Math.floor(-left / 60) : 0
            const cls = running
              ? 'bg-white text-brand-800 border-2 border-brand-300'
              : left != null && overMin >= OVERDUE_GRACE_MIN
                ? 'bg-amber-500 text-white'
                : left != null
                  ? 'bg-emerald-600 text-white animate-[pulse_2s_ease-in-out_infinite]'
                  : 'bg-brand-600 text-white active:bg-brand-700'
            return (
              <button
                key={s.seq}
                disabled={busy || operatorId == null}
                onClick={() => (running ? setConfirmEarly(true) : onComplete(tube, s.seq, false))}
                className={`min-h-[56px] px-5 rounded-xl text-base font-semibold shadow-sm active:scale-[0.98] disabled:opacity-40 transition flex items-center gap-2 ${cls}`}
              >
                {running && <Timer className="w-4 h-4" />}
                <span>{s.name}</span>
                {running && <span className="tabular-nums font-bold">{mmss(left!)}</span>}
                {left != null && !running && (
                  <span className="text-sm font-medium opacity-90">
                    {overMin >= 1 ? `ready +${overMin} min` : 'ready'}
                  </span>
                )}
              </button>
            )
          }
          return (
            <button
              key={s.seq}
              disabled={!undoable || busy}
              onClick={() => undoable && setConfirmUndo(true)}
              title={isDone ? `${s.completed_by ?? ''} ${s.completed_at ? format(parseISO(s.completed_at), 'HH:mm') : ''}` : undefined}
              className={
                isDone
                  ? `min-h-[56px] px-3 rounded-xl text-sm font-medium flex items-center gap-1.5 border ${
                      undoable ? 'bg-emerald-50 text-emerald-800 border-emerald-300' : 'bg-emerald-50/60 text-emerald-700/80 border-emerald-100'}`
                  : 'min-h-[56px] px-3 rounded-xl text-sm text-slate-400 border border-dashed border-slate-200 flex items-center gap-1.5'
              }
            >
              {isDone && <Check className="w-4 h-4" />}
              <span>{s.name}</span>
              {isDone && s.completed_at && <span className="text-xs opacity-70">{format(parseISO(s.completed_at), 'HH:mm')}</span>}
              {isDone && s.completed_early_seconds != null && (
                <span className="text-xs text-amber-700" title="Marked done before its timer ran out">early</span>
              )}
              {!isDone && s.wait_minutes != null && <span className="text-xs opacity-80">{s.wait_minutes}′</span>}
              {undoable && <RotateCcw className="w-3.5 h-3.5 ml-1 opacity-60" aria-label="tap to undo" />}
            </button>
          )
        })}
      </div>

      {confirmEarly && nextStep && left != null && (
        <div className="mt-2 flex items-center gap-2 bg-amber-50 border border-amber-200 rounded-xl px-3 py-2">
          <span className="text-sm text-amber-900 flex-1">
            “{nextStep.name}” has {mmss(left)} left of {nextStep.wait_minutes} min. Mark it done early? This is recorded.
          </span>
          <button onClick={() => { setConfirmEarly(false); onComplete(tube, nextStep.seq, true) }}
            className="min-h-[48px] px-4 rounded-lg bg-amber-600 text-white font-semibold">Done early</button>
          <button onClick={() => setConfirmEarly(false)}
            className="min-h-[48px] px-4 rounded-lg bg-white border border-slate-300 text-slate-700 font-medium">Wait</button>
        </div>
      )}

      {confirmUndo && undoStep && (
        <div className="mt-2 flex items-center gap-2 bg-amber-50 border border-amber-200 rounded-xl px-3 py-2">
          <span className="text-sm text-amber-900 flex-1">
            Undo “{undoStep.name}” on {tube.test_code}?
            {undoStep.seq === 1 && ' The cocktail test goes back to reserved.'}
          </span>
          <button onClick={() => { setConfirmUndo(false); onUndo(tube, undoStep.seq) }}
            className="min-h-[48px] px-4 rounded-lg bg-amber-600 text-white font-semibold">Undo</button>
          <button onClick={() => setConfirmUndo(false)}
            className="min-h-[48px] px-4 rounded-lg bg-white border border-slate-300 text-slate-700 font-medium">Keep</button>
        </div>
      )}
    </div>
  )
}

// ── Ticket ───────────────────────────────────────────────────────────────────

function Ticket({
  order, operatorId, fresh, nowMs, onError, alarming = null,
}: {
  order: StationOrder
  operatorId: number | null
  fresh: boolean
  nowMs: number
  onError: (msg: string) => void
  alarming?: 'ready' | 'over' | null
}) {
  const [confirmBatch, setConfirmBatch] = useState<{ step: string; left: number } | null>(null)
  const qc = useQueryClient()
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['station-queue'] })
    qc.invalidateQueries({ queryKey: ['sample-orders'] })
    qc.invalidateQueries({ queryKey: ['cocktails'] })
    qc.invalidateQueries({ queryKey: ['cocktail-availability'] })
  }
  const err = (e: any) => { onError(e.response?.data?.detail ?? 'Something went wrong'); refresh() }

  const complete = useMutation({
    mutationFn: ({ tube, seq, force }: { tube: StationTube; seq: number; force: boolean }) =>
      stationApi.complete(tube.id, seq, operatorId ?? undefined, force),
    onSuccess: refresh, onError: err,
  })
  const undo = useMutation({
    mutationFn: ({ tube, seq }: { tube: StationTube; seq: number }) => stationApi.undo(tube.id, seq),
    onSuccess: refresh, onError: err,
  })
  const advance = useMutation({
    mutationFn: ({ step, force }: { step: string; force: boolean }) =>
      stationApi.advance(order.id, step, operatorId ?? undefined, force),
    onSuccess: refresh, onError: err,
  })
  // Longest remaining timer among the tubes a batch button would complete
  const batchLeft = (step: string) => Math.max(0, ...order.tubes
    .filter((t) => t.next_name === step)
    .map((t) => secondsLeft(t.steps.find((s) => s.seq === t.next_seq)?.ready_at ?? null, nowMs) ?? 0))
  const busy = complete.isPending || undo.isPending || advance.isPending

  // Batch button when 2+ tubes are waiting on the same step
  const counts: Record<string, number> = {}
  order.tubes.forEach((t) => { if (t.next_name) counts[t.next_name] = (counts[t.next_name] ?? 0) + 1 })
  const batch = Object.entries(counts).filter(([, n]) => n >= 2)

  const urgent = order.priority === 'urgent'
  return (
    <div
      className={`bg-white rounded-2xl border-2 shadow-sm overflow-hidden transition-shadow ${
        urgent ? 'border-red-400' : 'border-slate-200'} ${fresh && !alarming ? 'ring-4 ring-brand-300' : ''}`}
      style={alarming ? ({
        ['--fj-c' as any]: alarming === 'over' ? '#f59e0b' : '#10b981',
        animation: 'fj-ring 1s ease-in-out infinite',
      } as React.CSSProperties) : undefined}
    >
      <div className={`flex items-start justify-between gap-3 px-4 py-3 ${urgent ? 'bg-red-50' : 'bg-slate-50'}`}>
        <div className="min-w-0">
          <p className="font-mono text-2xl font-bold text-slate-900 leading-tight whitespace-nowrap">{order.lab_id}</p>
          <p className="text-sm text-slate-500 truncate">
            {urgent && <span className="font-bold text-red-600 mr-1.5">URGENT</span>}
            {order.pathologist ?? '—'}
            {order.notes && <span className="text-slate-400"> · {order.notes}</span>}
          </p>
        </div>
        <div className="text-right shrink-0">
          {order.completed_at ? (
            <p className="text-sm font-semibold text-emerald-700">Finished {format(parseISO(order.completed_at), 'HH:mm')}</p>
          ) : (
            <p className={`text-lg font-bold tabular-nums ${waitClass(order.waiting_minutes)}`}>{fmtWait(order.waiting_minutes)}</p>
          )}
          <p className="text-xs text-slate-400">{order.status === 'in_queue' ? 'not started' : order.technologist ?? ''}</p>
        </div>
      </div>

      <div className="px-4 py-3">
        <FlagToggles order={order} operatorId={operatorId} onError={onError} />
        {order.sample_comment && (
          <p className="mb-3 text-sm text-amber-900 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
            {order.sample_comment}
          </p>
        )}
        {batch.map(([step, n]) => {
          const left = batchLeft(step)
          return (
            <button
              key={step}
              disabled={busy || operatorId == null}
              onClick={() => (left > 0 ? setConfirmBatch({ step, left }) : advance.mutate({ step, force: false }))}
              className={`w-full mb-3 min-h-[56px] rounded-xl text-base font-semibold active:scale-[0.99] disabled:opacity-40 transition ${
                left > 0 ? 'bg-white text-slate-900 border-2 border-slate-300' : 'bg-slate-900 text-white'}`}
            >
              All {n} tubes: {step}{left > 0 && <span className="ml-2 tabular-nums">{mmss(left)}</span>}
            </button>
          )
        })}
        {confirmBatch && (
          <div className="mb-3 flex items-center gap-2 bg-amber-50 border border-amber-200 rounded-xl px-3 py-2">
            <span className="text-sm text-amber-900 flex-1">
              “{confirmBatch.step}” still has up to {mmss(confirmBatch.left)} to run. Mark all done early? This is recorded.
            </span>
            <button onClick={() => { advance.mutate({ step: confirmBatch.step, force: true }); setConfirmBatch(null) }}
              className="min-h-[48px] px-4 rounded-lg bg-amber-600 text-white font-semibold">Done early</button>
            <button onClick={() => setConfirmBatch(null)}
              className="min-h-[48px] px-4 rounded-lg bg-white border border-slate-300 text-slate-700 font-medium">Wait</button>
          </div>
        )}
        <div className="divide-y divide-slate-100">
          {order.tubes.map((t) => (
            <TubeRow
              key={t.id} tube={t} operatorId={operatorId} busy={busy} nowMs={nowMs}
              onComplete={(tube, seq, force) => complete.mutate({ tube, seq, force })}
              onUndo={(tube, seq) => undo.mutate({ tube, seq })}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Sample flags (gloved one-tap toggles) ────────────────────────────────────

function FlagToggles({ order, operatorId, onError }: {
  order: StationOrder
  operatorId: number | null
  onError: (msg: string) => void
}) {
  const qc = useQueryClient()
  const { options } = useSampleFlags()
  // Desired state while a tap is in flight, so the button flips instantly
  const [pending, setPending] = useState<Record<string, boolean>>({})
  const setFlag = useMutation({
    mutationFn: ({ code, on }: { code: string; on: boolean }) =>
      sampleOrdersApi.setSampleFlag(order.id, code, on, operatorId!),
    onError: (e: any) => onError(e.response?.data?.detail ?? 'Could not update the flag'),
    onSettled: async (_d, _e, v) => {
      await qc.invalidateQueries({ queryKey: ['station-queue'] })
      qc.invalidateQueries({ queryKey: ['sample-orders'] })
      setPending((p) => { const n = { ...p }; delete n[v.code]; return n })
    },
  })
  if (!options.length) return null
  return (
    <div className="grid grid-cols-3 gap-2 mb-3" role="group" aria-label="Sample flags">
      {options.map((o) => {
        const on = pending[o.code] ?? order.sample_flags.includes(o.code)
        return (
          <button
            key={o.code}
            type="button"
            aria-pressed={on}
            disabled={operatorId == null || o.code in pending}
            onClick={() => { setPending((p) => ({ ...p, [o.code]: !on })); setFlag.mutate({ code: o.code, on: !on }) }}
            className={`min-h-[56px] px-2 rounded-xl border-2 text-[15px] font-semibold leading-tight flex items-center justify-center gap-1.5
              active:scale-[0.97] transition disabled:opacity-50 ${
              on ? 'bg-amber-500 border-amber-600 text-white shadow-inner' : 'bg-white border-slate-300 text-slate-700'}`}
          >
            {on && <Check className="w-5 h-5 shrink-0" strokeWidth={3} />}
            <span>{o.label}</span>
          </button>
        )
      })}
    </div>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function StationPage() {
  const { user } = useAuth()
  const [operatorId, setOperatorId] = useState<number | null>(() => {
    const v = localStorage.getItem(OPERATOR_KEY)
    return v ? Number(v) : null
  })
  const [pickOperator, setPickOperator] = useState(false)
  const [error, setError] = useState('')
  const [showRecent, setShowRecent] = useState(false)
  const [now, setNow] = useState(new Date())
  const seen = useRef<Set<number> | null>(null)
  const [fresh, setFresh] = useState<Set<number>>(new Set())

  // Swap the normal 8-hour session for a 30-day station session (technologist logins only)
  const [sessionNote, setSessionNote] = useState('')
  useEffect(() => {
    if (!user) return
    if (user.role !== 'technologist') {
      setSessionNote(`Signed in as ${user.username} (${user.role}). For an unattended tablet, sign in with a technologist login so the session lasts 30 days.`)
      return
    }
    if (localStorage.getItem(STATION_FLAG) === user.username) return
    stationApi.stationToken()
      .then((t) => { localStorage.setItem('flowjai_token', t.access_token); localStorage.setItem(STATION_FLAG, user.username) })
      .catch(() => setSessionNote('Could not start a long station session — it will expire with the normal login.'))
  }, [user])

  useEffect(() => { const i = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(i) }, [])
  const [sound, setSound] = useState(() => localStorage.getItem(SOUND_KEY) !== 'off')
  const toggleSound = () => setSound((v) => { localStorage.setItem(SOUND_KEY, v ? 'off' : 'on'); if (!v) chime(); return !v })
  const chimed = useRef<Set<string>>(new Set())
  useEffect(() => { if (error) { const t = setTimeout(() => setError(''), 6000); return () => clearTimeout(t) } }, [error])

  const { data: staff = [] } = useQuery({ queryKey: ['staff', 'technologist'], queryFn: () => staffApi.list('technologist') })
  const { data, isLoading, isError } = useQuery({
    queryKey: ['station-queue'],
    queryFn: stationApi.queue,
    refetchInterval: 4000,
    refetchIntervalInBackground: true,
  })
  const orders = data?.orders ?? []
  const recent = data?.recent ?? []

  // Timers count down against the SERVER clock, so a tablet whose clock is off
  // still shows the right time left.
  const offsetMs = useRef(0)
  useEffect(() => {
    if (data?.server_time) offsetMs.current = parseISO(data.server_time).getTime() - Date.now()
  }, [data?.server_time])
  const nowMs = now.getTime() + offsetMs.current

  // ── Timer alarm ──────────────────────────────────────────────────────────
  // A step whose timer has run out alarms until someone taps OK or does the step:
  // flashing screen edge + banner + ticket outline, a chime now and every
  // ALARM_REPEAT_SEC seconds, and a vibration on tablets that support it.
  const [acked, setAcked] = useState<Set<string>>(new Set())
  const lastChime = useRef(0)
  const alarms: Alarm[] = []
  for (const o of orders) for (const t of o.tubes) {
    const st = t.steps.find((s) => s.seq === t.next_seq)
    const left = st ? secondsLeft(st.ready_at, nowMs) : null
    const key = `${t.id}:${st?.seq}`
    if (st && left != null && left <= 0 && !acked.has(key)) {
      alarms.push({ key, orderId: o.id, labId: o.lab_id, test: t.test_code, step: st.name, overMin: Math.floor(-left / 60) })
    }
  }
  const alarmKeys = alarms.map((a) => a.key).join(',')
  const anyOver = alarms.some((a) => a.overMin >= OVERDUE_GRACE_MIN)
  useEffect(() => {
    if (!alarms.length) return
    const fresh = alarms.some((a) => !chimed.current.has(a.key))
    alarms.forEach((a) => chimed.current.add(a.key))
    const due = Date.now() - lastChime.current >= ALARM_REPEAT_SEC * 1000
    if (fresh || due) {
      lastChime.current = Date.now()
      if (sound) { chime(); setTimeout(chime, 450) }
      try { navigator.vibrate?.([300, 150, 300]) } catch { /* not supported */ }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [alarmKeys, nowMs, sound])
  const acknowledge = () => setAcked((prev) => new Set([...prev, ...alarms.map((a) => a.key)]))
  const alarmFor = (orderId: number): 'ready' | 'over' | null => {
    const mine = alarms.filter((a) => a.orderId === orderId)
    if (!mine.length) return null
    return mine.some((a) => a.overMin >= OVERDUE_GRACE_MIN) ? 'over' : 'ready'
  }

  // Highlight tickets that arrived since the last refresh
  useEffect(() => {
    if (!data) return
    const ids = new Set(orders.map((o) => o.id))
    if (seen.current) {
      const arrived = orders.filter((o) => !seen.current!.has(o.id)).map((o) => o.id)
      if (arrived.length) {
        setFresh((f) => new Set([...f, ...arrived]))
        setTimeout(() => setFresh((f) => { const n = new Set(f); arrived.forEach((id) => n.delete(id)); return n }), 12_000)
      }
    }
    seen.current = ids
  }, [data])

  const operator = staff.find((s: Staff) => s.id === operatorId) ?? null
  useEffect(() => {  // forget an operator who has been removed from the staff list
    if (staff.length && operatorId != null && !operator) { setOperatorId(null); localStorage.removeItem(OPERATOR_KEY) }
  }, [staff, operatorId, operator])

  const chooseOperator = (id: number) => {
    setOperatorId(id); localStorage.setItem(OPERATOR_KEY, String(id)); setPickOperator(false)
  }

  return (
    <div className="min-h-screen bg-slate-100 select-none">
      {/* Top bar */}
      <header className="sticky top-0 z-20 bg-slate-900 text-white">
        <div className="flex items-center gap-4 px-5 py-3">
          <div>
            <p className="text-lg font-bold leading-tight">Processing station</p>
            <p className="text-xs text-white/50">{orders.length} pending · {format(nowMs, 'HH:mm')}</p>
          </div>
          <button
            onClick={() => setPickOperator((v) => !v)}
            className={`ml-auto min-h-[48px] px-4 rounded-xl flex items-center gap-2 font-semibold ${
              operator ? 'bg-white/10 hover:bg-white/15' : 'bg-amber-500 text-slate-900 animate-pulse'}`}
          >
            <UserIcon className="w-4 h-4" />
            {operator ? operator.name : 'Tap to choose who is processing'}
            {pickOperator ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
          <button onClick={toggleSound} title={sound ? 'Timer chime on' : 'Timer chime off'}
            className="min-h-[48px] min-w-[48px] rounded-xl bg-white/10 flex items-center justify-center">
            {sound ? <Bell className="w-5 h-5" /> : <BellOff className="w-5 h-5 opacity-60" />}
          </button>
          {(user?.role === 'admin' || user?.role === 'service') && (
            <Link to="/admin/process-steps" title="Configure steps and timers"
              className="min-h-[48px] min-w-[48px] rounded-xl bg-white/10 flex items-center justify-center">
              <Settings className="w-5 h-5" />
            </Link>
          )}
          <button onClick={() => document.documentElement.requestFullscreen?.()}
            className="min-h-[48px] min-w-[48px] rounded-xl bg-white/10 flex items-center justify-center" title="Full screen">
            <Maximize className="w-5 h-5" />
          </button>
          <Link to="/worklist" className="text-xs text-white/50 hover:text-white">Exit</Link>
        </div>
        {pickOperator && (
          <div className="flex flex-wrap gap-2 px-5 pb-4">
            {staff.length === 0 && <p className="text-sm text-white/70">No technologists yet — add them under Admin → Staff.</p>}
            {staff.map((s: Staff) => (
              <button key={s.id} onClick={() => chooseOperator(s.id)}
                className={`min-h-[52px] px-5 rounded-xl text-base font-semibold ${
                  s.id === operatorId ? 'bg-brand-500 text-white' : 'bg-white text-slate-900'}`}>
                {s.name}
              </button>
            ))}
          </div>
        )}
        {alarms.length > 0 && (
          <div
            className={`flex items-center gap-4 px-5 py-3 text-white ${anyOver ? 'bg-amber-500' : 'bg-emerald-600'}`}
            style={{ animation: 'fj-banner 1s ease-in-out infinite' }}
            role="alert"
          >
            <Timer className="w-7 h-7 shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-lg font-bold leading-tight">
                {alarms.length === 1 ? 'Timer done' : `${alarms.length} timers done`}
              </p>
              <p className="text-sm font-medium truncate">
                {alarms.slice(0, 3).map((a) =>
                  `${a.labId} · ${a.test}: ${a.step}${a.overMin >= 1 ? ` (+${a.overMin} min)` : ''}`).join('   |   ')}
                {alarms.length > 3 && `   +${alarms.length - 3} more`}
              </p>
            </div>
            <button
              onClick={acknowledge}
              className="min-h-[56px] px-8 rounded-xl bg-white text-slate-900 text-lg font-bold shrink-0 active:scale-95"
            >
              OK
            </button>
          </div>
        )}
      </header>

      <style>{ALARM_CSS}</style>
      {alarms.length > 0 && (
        <>
          {/* flashing screen edge - visible from across the bench */}
          <div
            className="fixed inset-0 z-40 pointer-events-none"
            style={{
              boxShadow: `inset 0 0 0 12px ${anyOver ? '#f59e0b' : '#10b981'}`,
              animation: 'fj-edge 1s ease-in-out infinite',
            }}
          />
        </>
      )}
      {sessionNote && <p className="px-5 py-2 text-xs bg-amber-100 text-amber-900">{sessionNote}</p>}
      {error && (
        <div className="fixed bottom-5 left-1/2 -translate-x-1/2 z-30 bg-red-600 text-white px-5 py-3 rounded-xl shadow-lg text-base font-medium max-w-[90vw]">
          {error}
        </div>
      )}

      <main className="p-4 space-y-4">
        {!operator && staff.length > 0 && (
          <p className="text-center text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-xl py-2">
            Choose who is processing before tapping steps — every step is recorded against that name.
          </p>
        )}

        {isLoading ? (
          <p className="text-center text-slate-500 py-20">Loading…</p>
        ) : isError ? (
          <p className="text-center text-red-600 py-20">Can't reach the flowjAI server. Retrying…</p>
        ) : orders.length === 0 ? (
          <div className="text-center py-24">
            <p className="text-2xl font-semibold text-slate-400">Nothing pending</p>
            <p className="text-sm text-slate-400 mt-1">New worklist orders appear here automatically.</p>
          </div>
        ) : (
          <div className="grid gap-4 grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 items-start">
            {orders.map((o) => (
              <Ticket key={o.id} order={o} operatorId={operatorId} fresh={fresh.has(o.id)} nowMs={nowMs}
                onError={setError} alarming={alarmFor(o.id)} />
            ))}
          </div>
        )}

        {recent.length > 0 && (
          <section className="pt-2">
            <button onClick={() => setShowRecent((v) => !v)}
              className="min-h-[48px] px-4 rounded-xl bg-white border border-slate-200 text-sm font-medium text-slate-600 flex items-center gap-2">
              <RotateCcw className="w-4 h-4" /> Just finished ({recent.length}) — tap to review or undo
              {showRecent ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>
            {showRecent && (
              <div className="grid gap-4 grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 items-start mt-3 opacity-90">
                {recent.map((o) => (
                  <Ticket key={o.id} order={o} operatorId={operatorId} fresh={false} nowMs={nowMs} onError={setError} />
                ))}
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  )
}
