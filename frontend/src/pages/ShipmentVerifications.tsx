// pages/ShipmentVerifications.tsx — shipment-to-shipment verification (regulatory QC)

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import {
  CheckCircle2, Circle, Download, FileText, PackageCheck, Paperclip, Trash2, Upload,
} from 'lucide-react'
import { useRef, useState } from 'react'
import { shipmentVerificationsApi, staffApi } from '../api/client'
import { VerificationBadge } from '../components/CocktailTraceModal'
import { Badge, Button, Card, EmptyState, Modal, Spinner } from '../components/ui'
import type { ShipmentVerification, VerificationAttachment } from '../types'

const ACCEPT = '.pdf,.png,.jpg,.jpeg,.tif,.tiff,.webp,.doc,.docx,.xls,.xlsx,.csv,.txt,.fcs'
const fmtDT = (s: string | null) => (s ? format(parseISO(s), 'd MMM yy, HH:mm') : '—')

function timeLeft(v: ShipmentVerification): { text: string; cls: string } {
  if (v.status === 'closed') {
    return v.closed_late
      ? { text: 'closed late', cls: 'text-red-600' }
      : { text: 'closed on time', cls: 'text-slate-400' }
  }
  const h = v.hours_remaining ?? 0
  if (h < 0) return { text: `overdue by ${Math.ceil(-h)} h`, cls: 'text-red-600 font-semibold' }
  if (h < 12) return { text: `${Math.floor(h)} h left`, cls: 'text-amber-600 font-medium' }
  return { text: `${Math.floor(h)} h left`, cls: 'text-slate-500' }
}

function fmtSize(b: number) {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`
  return `${(b / 1024 / 1024).toFixed(1)} MB`
}

// ── Evidence panel (one per shipment) ────────────────────────────────────────

function EvidencePanel({
  v, role, title, subtitle,
}: {
  v: ShipmentVerification
  role: 'previous' | 'new'
  title: string
  subtitle: string
}) {
  const qc = useQueryClient()
  const inputRef = useRef<HTMLInputElement>(null)
  const [error, setError] = useState('')
  const files = v.attachments.filter((a) => a.role === role)
  const editable = v.status === 'open'

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['shipment-verifications'] })
    qc.invalidateQueries({ queryKey: ['shipment-verification', v.id] })
  }

  const upload = useMutation({
    // Takes a plain array: an <input>'s FileList is live and is emptied when the
    // input is reset, which happened before the upload ran (files silently dropped).
    mutationFn: async (list: File[]) => {
      for (const f of list) await shipmentVerificationsApi.upload(v.id, role, f)
    },
    onSuccess: () => { setError(''); refresh() },
    onError: (e: any) => { setError(e.response?.data?.detail ?? 'Upload failed'); refresh() },
  })
  const remove = useMutation({
    mutationFn: (a: VerificationAttachment) => shipmentVerificationsApi.removeAttachment(a.id),
    onSuccess: refresh,
    onError: (e: any) => setError(e.response?.data?.detail ?? 'Could not remove file'),
  })

  return (
    <div className={`border rounded-lg p-3 ${files.length ? 'border-slate-200' : 'border-amber-300 bg-amber-50/40'}`}>
      <div className="flex items-start justify-between gap-2 mb-2">
        <div>
          <p className="text-sm font-semibold text-slate-900 flex items-center gap-1.5">
            {files.length
              ? <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              : <Circle className="w-4 h-4 text-amber-500" />}
            {title}
          </p>
          <p className="text-xs text-slate-500 font-mono mt-0.5">{subtitle}</p>
        </div>
        {editable && (
          <>
            <input
              ref={inputRef} type="file" accept={ACCEPT} multiple className="hidden"
              onChange={(e) => {
                const picked = Array.from(e.target.files ?? [])   // copy BEFORE resetting the input
                e.target.value = ''
                if (picked.length) upload.mutate(picked)
              }}
            />
            <Button variant="secondary" size="sm" className="shrink-0 whitespace-nowrap" onClick={() => inputRef.current?.click()} disabled={upload.isPending}>
              <Upload className="w-3.5 h-3.5" /> {upload.isPending ? 'Uploading…' : 'Add file'}
            </Button>
          </>
        )}
      </div>

      {files.length === 0 ? (
        <p className="text-xs text-amber-700">No evidence yet — image or document required.</p>
      ) : (
        <ul className="space-y-1">
          {files.map((a) => (
            <li key={a.id} className="flex items-center gap-2 text-xs">
              <FileText className="w-3.5 h-3.5 text-slate-400 shrink-0" />
              <button
                onClick={() => shipmentVerificationsApi.downloadAttachment(a.id, a.original_filename)}
                className="truncate text-brand-700 hover:underline text-left"
                title={`SHA-256 ${a.sha256}`}
              >
                {a.original_filename}
              </button>
              <span className="text-slate-400 shrink-0">{fmtSize(a.size_bytes)} · {a.uploaded_by_username}</span>
              {editable && (
                <button
                  onClick={() => { if (confirm(`Remove ${a.original_filename}?`)) remove.mutate(a) }}
                  className="ml-auto text-slate-300 hover:text-red-500"
                  title="Remove"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {error && <p className="text-xs text-red-600 mt-1.5">{error}</p>}
    </div>
  )
}

// ── Detail modal ─────────────────────────────────────────────────────────────

function VerificationModal({ id, onClose }: { id: number | null; onClose: () => void }) {
  const qc = useQueryClient()
  const [outcome, setOutcome] = useState<'acceptable' | 'not_acceptable' | ''>('')
  const [comments, setComments] = useState('')
  const [signerId, setSignerId] = useState('')
  const [error, setError] = useState('')

  const { data: staff = [] } = useQuery({ queryKey: ['staff', 'all'], queryFn: () => staffApi.list(), enabled: id != null })
  const { data: v, isLoading } = useQuery({
    queryKey: ['shipment-verification', id],
    queryFn: () => shipmentVerificationsApi.get(id!),
    enabled: id != null,
  })

  const close = useMutation({
    mutationFn: () => shipmentVerificationsApi.close(id!, {
      outcome: outcome as 'acceptable' | 'not_acceptable',
      comments: comments.trim() || undefined,
      closed_by_staff_id: Number(signerId),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['shipment-verifications'] })
      qc.invalidateQueries({ queryKey: ['shipment-verification', id] })
      qc.invalidateQueries({ queryKey: ['alerts'] })
      qc.invalidateQueries({ queryKey: ['store-stock'] })
      setOutcome(''); setComments(''); setSignerId(''); setError('')
    },
    onError: (e: any) => setError(e.response?.data?.detail ?? 'Could not close'),
  })

  const handleClose = () => { setOutcome(''); setComments(''); setSignerId(''); setError(''); onClose() }
  const evidenceComplete = !!v && v.has_previous_evidence && v.has_new_evidence
  const needsComment = outcome === 'not_acceptable' && !comments.trim()

  return (
    <Modal open={id != null} onClose={handleClose} size="lg"
      title={v ? `${v.antibody_name}${v.fluorochrome ? ` · ${v.fluorochrome}` : ''} — shipment verification` : 'Shipment verification'}>
      {isLoading || !v ? <Spinner className="py-10" /> : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-sm bg-slate-50 border border-slate-200 rounded-lg px-4 py-3">
            <div><span className="text-slate-500">Raised:</span> {fmtDT(v.triggered_at)}</div>
            <div>
              <span className="text-slate-500">Due:</span> {fmtDT(v.due_at)}{' '}
              <span className={`text-xs ${timeLeft(v).cls}`}>({timeLeft(v).text})</span>
            </div>
            <div><span className="text-slate-500">Vendor:</span> {v.vendor ?? '—'}</div>
            <div className="flex items-center gap-1.5">
              <span className="text-slate-500">Status:</span> <VerificationBadge status={v.display_status} />
            </div>
            {v.lot_changed && (
              <div className="col-span-2 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1 mt-1">
                The lot number also changed ({v.previous_lot_no} → {v.new_lot_no}) — apply your lot-to-lot acceptance criteria, not just shipment-to-shipment.
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <EvidencePanel
              v={v} role="previous" title="Previous shipment"
              subtitle={`${v.previous_shipment_id ?? 'untagged stock'} · lot ${v.previous_lot_no ?? '—'}`}
            />
            <EvidencePanel
              v={v} role="new" title="New shipment"
              subtitle={`${v.shipment_id} · lot ${v.new_lot_no ?? '—'}`}
            />
          </div>

          {v.status === 'open' ? (
            <div className="border-t border-slate-100 pt-4 space-y-3">
              <p className="text-sm font-semibold text-slate-900">Sign off</p>
              <div className="flex gap-2">
                {(['acceptable', 'not_acceptable'] as const).map((o) => (
                  <button
                    key={o} type="button" onClick={() => setOutcome(o)}
                    className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${
                      outcome === o
                        ? o === 'acceptable' ? 'bg-emerald-600 text-white border-emerald-600' : 'bg-red-600 text-white border-red-600'
                        : 'bg-white text-slate-600 border-slate-200 hover:border-slate-300'
                    }`}
                  >
                    {o === 'acceptable' ? 'New shipment acceptable' : 'Not acceptable'}
                  </button>
                ))}
              </div>
              <textarea
                value={comments} onChange={(e) => setComments(e.target.value)} rows={3} maxLength={1024}
                placeholder={outcome === 'not_acceptable'
                  ? 'Required: what failed and what action was taken (e.g. quarantined, vendor informed)'
                  : 'Comments (optional) — e.g. % difference in MFI / positive population vs previous shipment'}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
              <select
                value={signerId} onChange={(e) => setSignerId(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                <option value="">Signed off by…</option>
                {staff.map((s: any) => <option key={s.id} value={s.id}>{s.name}{s.role === 'pathologist' ? ' (pathologist)' : ''}</option>)}
              </select>
              {!evidenceComplete && (
                <p className="text-xs text-amber-700">Attach evidence for both shipments to enable sign-off.</p>
              )}
              {error && <p className="text-sm text-red-600">{error}</p>}
              <div className="flex justify-end gap-2">
                <Button variant="secondary" onClick={handleClose}>Later</Button>
                <Button
                  onClick={() => close.mutate()}
                  disabled={!evidenceComplete || !outcome || needsComment || !signerId || close.isPending}
                  variant={outcome === 'not_acceptable' ? 'danger' : 'primary'}
                >
                  {close.isPending ? 'Saving…' : 'Close verification'}
                </Button>
              </div>
            </div>
          ) : (
            <div className="border-t border-slate-100 pt-4 text-sm space-y-1">
              <p>
                <span className="text-slate-500">Closed by</span> {v.closed_by_username ?? '—'}{' '}
                <span className="text-slate-500">on</span> {fmtDT(v.closed_at)}
                {v.closed_late && <Badge variant="critical" className="ml-2">after the 48 h window</Badge>}
              </p>
              {v.comments && <p className="text-slate-700 whitespace-pre-wrap">{v.comments}</p>}
            </div>
          )}
        </div>
      )}
    </Modal>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function ShipmentVerificationsPage() {
  const [tab, setTab] = useState<'open' | 'closed' | 'all'>('open')
  const [openId, setOpenId] = useState<number | null>(null)

  const { data: rows = [], isLoading } = useQuery({
    queryKey: ['shipment-verifications', tab],
    queryFn: () => shipmentVerificationsApi.list(tab),
    refetchInterval: 60_000,
  })

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <PackageCheck className="w-5 h-5 text-brand-600" /> Shipment QC
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Raised automatically when an antibody arrives in a new shipment. Close within 48 h with evidence for both shipments.
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={() => shipmentVerificationsApi.exportLog()}>
          <Download className="w-3.5 h-3.5" /> Export log
        </Button>
      </div>

      <div className="flex rounded-lg border border-slate-200 overflow-hidden w-fit">
        {(['open', 'closed', 'all'] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-1.5 text-xs font-medium capitalize transition-colors ${
              tab === t ? 'bg-brand-600 text-white' : 'bg-white text-slate-500 hover:text-slate-700'}`}>
            {t}
          </button>
        ))}
      </div>

      <Card padding={false}>
        {isLoading ? <Spinner className="py-16" /> : rows.length === 0 ? (
          <EmptyState message={tab === 'open' ? 'No open shipment verifications.' : 'Nothing here yet.'} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs font-medium text-slate-500 border-b border-slate-100">
                  <th className="px-4 py-2.5">Antibody</th>
                  <th className="px-4 py-2.5">Previous → new shipment</th>
                  <th className="px-4 py-2.5">Raised</th>
                  <th className="px-4 py-2.5">Deadline</th>
                  <th className="px-4 py-2.5">Evidence</th>
                  <th className="px-4 py-2.5">Status</th>
                  <th className="px-4 py-2.5"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {rows.map((v) => {
                  const tl = timeLeft(v)
                  return (
                    <tr key={v.id} className={v.overdue ? 'bg-red-50/50' : ''}>
                      <td className="px-4 py-2.5">
                        <p className="font-medium text-slate-800">{v.antibody_name}</p>
                        <p className="text-xs text-slate-400">{[v.fluorochrome, v.vendor].filter(Boolean).join(' · ') || '—'}</p>
                      </td>
                      <td className="px-4 py-2.5 font-mono text-xs">
                        <span className="text-slate-500">{v.previous_shipment_id ?? 'untagged'}</span>
                        <span className="text-slate-300 mx-1.5">→</span>
                        <span className="font-semibold text-slate-800">{v.shipment_id}</span>
                        {v.lot_changed && <Badge variant="warning" className="ml-2 font-sans">lot change</Badge>}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-slate-500 whitespace-nowrap">{fmtDT(v.triggered_at)}</td>
                      <td className={`px-4 py-2.5 text-xs whitespace-nowrap ${tl.cls}`}>{tl.text}</td>
                      <td className="px-4 py-2.5 text-xs whitespace-nowrap">
                        <span className={v.has_previous_evidence ? 'text-emerald-700' : 'text-slate-400'}>
                          {v.has_previous_evidence ? '✓' : '○'} prev
                        </span>
                        <span className="mx-1.5 text-slate-300">·</span>
                        <span className={v.has_new_evidence ? 'text-emerald-700' : 'text-slate-400'}>
                          {v.has_new_evidence ? '✓' : '○'} new
                        </span>
                      </td>
                      <td className="px-4 py-2.5"><VerificationBadge status={v.display_status} /></td>
                      <td className="px-4 py-2.5 text-right">
                        <Button size="sm" variant={v.status === 'open' ? 'primary' : 'secondary'} onClick={() => setOpenId(v.id)}>
                          <Paperclip className="w-3.5 h-3.5" /> {v.status === 'open' ? 'Verify' : 'View'}
                        </Button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <VerificationModal id={openId} onClose={() => setOpenId(null)} />
    </div>
  )
}
