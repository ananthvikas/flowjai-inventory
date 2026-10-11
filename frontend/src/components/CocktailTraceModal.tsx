// components/CocktailTraceModal.tsx — look-back from a cocktail:
// which samples ran on it, which antibody lots / shipments went into it,
// and which other cocktails drew from the same lots.

import { useQuery } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import { AlertTriangle, Copy, Download, FlaskConical } from 'lucide-react'
import { useState } from 'react'
import { cocktailsApi } from '../api/client'
import type { CocktailTrace, VerificationStatus } from '../types'
import { Badge, Button, Modal, Spinner } from './ui'

const fmtDT = (s: string | null) => (s ? format(parseISO(s), 'd MMM yy, HH:mm') : '—')
const fmtD = (s: string | null) => (s ? format(parseISO(s), 'd MMM yy') : '—')

export function VerificationBadge({ status }: { status: VerificationStatus | null }) {
  if (!status) return <span className="text-xs text-slate-400">—</span>
  const map: Record<VerificationStatus, { v: 'ok' | 'warning' | 'critical' | 'pending'; label: string }> = {
    pending:        { v: 'pending',  label: 'Verification pending' },
    overdue:        { v: 'critical', label: 'Verification overdue' },
    acceptable:     { v: 'ok',       label: 'Verified' },
    not_acceptable: { v: 'critical', label: 'Failed verification' },
  }
  const m = map[status]
  return <Badge variant={m.v}>{m.label}</Badge>
}

export default function CocktailTraceModal({
  cocktailId,
  highlightLabId,
  onClose,
  onOpenCocktail,
}: {
  cocktailId: number | null
  highlightLabId?: string
  onClose: () => void
  onOpenCocktail?: (id: number) => void
}) {
  const [copied, setCopied] = useState(false)
  const { data, isLoading, error } = useQuery<CocktailTrace>({
    queryKey: ['cocktail-trace', cocktailId],
    queryFn: () => cocktailsApi.trace(cocktailId!),
    enabled: cocktailId != null,
  })

  const c = data?.cocktail
  const runIds = data?.samples.filter((s) => s.tube_status === 'consumed').map((s) => s.lab_id) ?? []

  const copyIds = async () => {
    try {
      await navigator.clipboard.writeText(runIds.join('\n'))
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* clipboard blocked — ignore */ }
  }

  return (
    <Modal
      open={cocktailId != null}
      onClose={onClose}
      size="xl"
      title={c ? `Cocktail ${c.cocktail_code ?? `#${c.id}`}` : 'Cocktail trace'}
    >
      {isLoading ? (
        <Spinner className="py-12" />
      ) : error || !data || !c ? (
        <p className="text-sm text-red-600">Could not load the cocktail trace.</p>
      ) : (
        <div className="space-y-5">
          {/* Header */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-2 text-sm bg-slate-50 border border-slate-200 rounded-lg px-4 py-3">
            <div><p className="text-xs text-slate-500">Panel</p><p className="font-medium">{c.test_code} · {c.panel_name}</p></div>
            <div><p className="text-xs text-slate-500">Prepared</p><p className="font-medium">{c.prepared_at ? fmtDT(c.prepared_at) : fmtD(c.prepared_date)} by {c.prepared_by ?? '—'}</p></div>
            <div><p className="text-xs text-slate-500">Expiry</p><p className="font-medium">{fmtD(c.expiry_date)}</p></div>
            <div>
              <p className="text-xs text-slate-500">Tests</p>
              <p className="font-medium tabular-nums">
                {data.tests_used} used / {c.total_tests}
                {!c.active && <span className="ml-1.5 text-xs text-slate-400">(closed)</span>}
              </p>
            </div>
            {c.lot_notes && (
              <div className="col-span-full"><p className="text-xs text-slate-500">Notes</p><p>{c.lot_notes}</p></div>
            )}
          </div>

          {/* Samples */}
          <section>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold text-slate-900">
                Samples on this cocktail · {data.samples_run} run
                {data.samples_reserved > 0 && <span className="font-normal text-slate-500">, {data.samples_reserved} reserved (not yet run)</span>}
              </h3>
              <div className="flex gap-1.5">
                <Button variant="secondary" size="sm" onClick={copyIds} disabled={runIds.length === 0}>
                  <Copy className="w-3.5 h-3.5" /> {copied ? 'Copied' : 'Copy lab IDs'}
                </Button>
                <Button variant="secondary" size="sm" onClick={() => cocktailsApi.traceCsv(c.id)}>
                  <Download className="w-3.5 h-3.5" /> CSV
                </Button>
              </div>
            </div>

            {data.untracked_tests > 0 && (
              <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-2 text-xs text-amber-800">
                <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                <span>
                  {data.untracked_tests} test{data.untracked_tests === 1 ? ' was' : 's were'} logged on this cocktail from
                  the Cocktails page without lab IDs. Those samples can't be listed here — check the bench record.
                </span>
              </div>
            )}

            {data.samples.length === 0 ? (
              <p className="text-sm text-slate-400 py-3">No worklist samples reference this cocktail.</p>
            ) : (
              <div className="border border-slate-200 rounded-lg overflow-hidden max-h-72 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 sticky top-0">
                    <tr className="text-left text-xs font-medium text-slate-500">
                      <th className="px-3 py-2">Lab ID</th>
                      <th className="px-3 py-2">Tube</th>
                      <th className="px-3 py-2">Processed</th>
                      <th className="px-3 py-2">Order</th>
                      <th className="px-3 py-2">Pathologist / Tech</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {data.samples.map((s) => {
                      const mine = highlightLabId && s.lab_id === highlightLabId
                      return (
                        <tr key={s.tube_id} className={mine ? 'bg-brand-50' : s.tube_status !== 'consumed' ? 'text-slate-400' : ''}>
                          <td className="px-3 py-1.5 font-mono font-medium">
                            {s.lab_id}
                            {mine && <span className="ml-1.5 text-xs font-sans text-brand-700">(this sample)</span>}
                            {s.sample_flags?.length > 0 && (
                              <p className="font-sans font-normal text-[11px] text-amber-800 mt-0.5">
                                {s.sample_flags.map((f) => <span key={f} className="inline-block mr-1 px-1 rounded bg-amber-100 border border-amber-300">{f}</span>)}
                              </p>
                            )}
                            {s.sample_comment && (
                              <p className="font-sans font-normal text-[11px] text-amber-800 mt-0.5 max-w-[14rem]" title="Sample comment">
                                {s.sample_comment}
                              </p>
                            )}
                          </td>
                          <td className="px-3 py-1.5 text-xs">{s.test_code}{s.tube_status === 'reserved' && ' · reserved'}</td>
                          <td className="px-3 py-1.5 text-xs tabular-nums">{fmtDT(s.processing_started_at)}</td>
                          <td className="px-3 py-1.5 text-xs capitalize">{s.order_status.replace('_', ' ')}</td>
                          <td className="px-3 py-1.5 text-xs">
                            {s.pathologist ?? '—'}<span className="text-slate-400"> / {s.technologist ?? '—'}</span>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* Components */}
          <section>
            <h3 className="text-sm font-semibold text-slate-900 mb-2">Antibody lots in this cocktail</h3>
            {data.components.length === 0 ? (
              <p className="text-sm text-slate-400">No stock deductions recorded for this cocktail.</p>
            ) : (
              <div className="border border-slate-200 rounded-lg overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50">
                    <tr className="text-left text-xs font-medium text-slate-500">
                      <th className="px-3 py-2">Antibody</th>
                      <th className="px-3 py-2">Lot</th>
                      <th className="px-3 py-2">Shipment</th>
                      <th className="px-3 py-2 text-right">µl drawn</th>
                      <th className="px-3 py-2">Shipment QC</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {data.components.map((r) => (
                      <tr key={`${r.antibody_id}-${r.stock_lot_id}`}>
                        <td className="px-3 py-1.5">{r.antibody_name}{r.fluorochrome && <span className="text-slate-400"> · {r.fluorochrome}</span>}</td>
                        <td className="px-3 py-1.5 font-mono text-xs">{r.lot_no ?? '—'}</td>
                        <td className="px-3 py-1.5 font-mono text-xs">{r.shipment_id ?? <span className="text-slate-400">untagged</span>}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums text-xs">{r.volume_ul}</td>
                        <td className="px-3 py-1.5"><VerificationBadge status={r.shipment_verification_status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* Related cocktails */}
          {data.related_cocktails.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold text-slate-900 mb-1">Other cocktails made from the same lots</h3>
              <p className="text-xs text-slate-500 mb-2">If the problem is a reagent lot rather than this mix, these are affected too.</p>
              <div className="border border-slate-200 rounded-lg divide-y divide-slate-100">
                {data.related_cocktails.map((rc) => (
                  <div key={rc.id} className="flex items-center justify-between gap-3 px-3 py-2">
                    <div className="min-w-0">
                      <p className="text-sm font-medium flex items-center gap-1.5">
                        <FlaskConical className="w-3.5 h-3.5 text-slate-400" />
                        <span className="font-mono">{rc.cocktail_code ?? `#${rc.id}`}</span>
                        <span className="text-xs font-normal text-slate-500">prepared {fmtD(rc.prepared_date)} · {rc.samples_run} sample{rc.samples_run === 1 ? '' : 's'} run</span>
                      </p>
                      <p className="text-xs text-slate-500 truncate">Shares: {rc.shared_lots.join(', ')}</p>
                    </div>
                    {onOpenCocktail && (
                      <Button variant="secondary" size="sm" onClick={() => onOpenCocktail(rc.id)}>Trace</Button>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </Modal>
  )
}
