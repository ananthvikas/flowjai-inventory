// components/VolumeCheckModal.tsx — find and fix starting volumes that disagree
// with the antibody master's standard vial volume, and fill in missing standards.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import { useState } from 'react'
import { antibodiesApi, stockApi, storeStockApi } from '../api/client'
import { Button, Input, Modal, Spinner } from './ui'

const DEFAULT_REASON = 'Starting volume entered incorrectly — corrected to the standard vial volume'

function Section({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="text-sm font-semibold text-slate-900 mb-2">
        {title} <span className="font-normal text-slate-500">({count})</span>
      </h3>
      {children}
    </section>
  )
}

function MissingVolumeRow({ ab, onSaved }: {
  ab: { antibody_id: number; antibody_name: string; fluorochrome: string | null; catalog_no: string | null }
  onSaved: () => void
}) {
  const [v, setV] = useState('')
  const [err, setErr] = useState('')
  const save = useMutation({
    mutationFn: () => antibodiesApi.update(ab.antibody_id, { vial_volume_ul: Number(v) }),
    onSuccess: () => { setV(''); onSaved() },
    onError: (e: any) => setErr(e.response?.data?.detail ?? 'Could not save'),
  })
  return (
    <tr>
      <td className="px-3 py-1.5 font-medium text-slate-800">{ab.antibody_name}</td>
      <td className="px-3 py-1.5 text-xs text-slate-500">{ab.fluorochrome ?? '—'}</td>
      <td className="px-3 py-1.5 text-xs font-mono text-slate-500">{ab.catalog_no ?? <span className="text-amber-700 font-sans">no cat. no</span>}</td>
      <td className="px-3 py-1.5">
        <div className="flex items-center gap-1.5">
          <input
            type="number" min="1" value={v} onChange={(e) => { setV(e.target.value); setErr('') }}
            placeholder="µl"
            className="w-20 border border-slate-200 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
          <Button size="sm" variant="secondary" disabled={!(Number(v) > 0) || save.isPending} onClick={() => save.mutate()}>Set</Button>
          {err && <span className="text-xs text-red-600">{err}</span>}
        </div>
      </td>
    </tr>
  )
}

export default function VolumeCheckModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const [reason, setReason] = useState(DEFAULT_REASON)
  const [error, setError] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['volume-discrepancies'],
    queryFn: stockApi.volumeDiscrepancies,
    enabled: open,
  })

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['volume-discrepancies'] })
    qc.invalidateQueries({ queryKey: ['antibodies'] })
    qc.invalidateQueries({ queryKey: ['stock'] })
    qc.invalidateQueries({ queryKey: ['store-stock'] })
  }
  const onErr = (e: any) => setError(e.response?.data?.detail ?? 'Update failed')

  const fixLot = useMutation({
    mutationFn: ({ id, volume }: { id: number; volume: number }) => stockApi.correctStartVolume(id, volume, reason.trim()),
    onSuccess: () => { setError(''); refresh() },
    onError: onErr,
  })
  const fixStore = useMutation({
    mutationFn: ({ id, volume, keep }: { id: number; volume: number; keep: boolean }) =>
      storeStockApi.update(id, keep
        ? { volume_per_vial_ul: volume, volume_override_reason: reason.trim() }
        : { volume_per_vial_ul: volume }),
    onSuccess: () => { setError(''); refresh() },
    onError: onErr,
  })
  const busy = fixLot.isPending || fixStore.isPending
  const noReason = !reason.trim()

  return (
    <Modal open={open} onClose={onClose} title="Starting volume check" size="xl">
      {isLoading || !data ? <Spinner className="py-12" /> : (
        <div className="space-y-6">
          <p className="text-sm text-slate-600">
            Lots and store vials whose recorded volume differs from the standard vial volume in the antibody master.
            A wrong starting volume shifts every remaining-volume figure, and so the forecast, for that lot.
          </p>

          <div>
            <Input label="Reason recorded with each correction" value={reason} onChange={(e) => setReason(e.target.value)} />
            <p className="text-xs text-slate-500 mt-1">
              <span className="font-medium">Correct</span> sets the start to the standard volume. Remaining volume shifts by the same amount,
              unless the lot has been physically verified (then only the start changes).
              <span className="font-medium"> Keep</span> confirms the recorded volume is genuinely right, and stops flagging it.
            </p>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}

          <Section title="Open lots" count={data.lots.length}>
            {data.lots.length === 0 ? <p className="text-sm text-slate-400">None.</p> : (
              <div className="border border-slate-200 rounded-lg overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 text-left text-xs font-medium text-slate-500">
                    <tr>
                      <th className="px-3 py-2">Antibody</th><th className="px-3 py-2">Lot</th><th className="px-3 py-2">Received</th>
                      <th className="px-3 py-2 text-right">Recorded</th><th className="px-3 py-2 text-right">Standard</th>
                      <th className="px-3 py-2 text-right">Remaining</th><th className="px-3 py-2"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {data.lots.map((l) => {
                      const after = l.verified ? l.current_volume_ul : Math.max(0, l.current_volume_ul + (l.standard_ul - l.recorded_ul))
                      return (
                        <tr key={l.lot_id}>
                          <td className="px-3 py-1.5">
                            <span className="font-medium text-slate-800">{l.antibody_name}</span>
                            <span className="text-xs text-slate-500"> {l.fluorochrome ?? ''}{l.catalog_no ? ` · ${l.catalog_no}` : ''}</span>
                          </td>
                          <td className="px-3 py-1.5 font-mono text-xs">{l.lot_no}</td>
                          <td className="px-3 py-1.5 text-xs">{format(parseISO(l.date_received), 'd MMM yy')}</td>
                          <td className="px-3 py-1.5 text-right tabular-nums text-amber-700 font-medium">{l.recorded_ul} µl</td>
                          <td className="px-3 py-1.5 text-right tabular-nums">{l.standard_ul} µl</td>
                          <td className="px-3 py-1.5 text-right tabular-nums text-xs" title={l.verified ? 'Verified lot: remaining volume is a measurement and will not change' : 'Remaining after correction'}>
                            {l.current_volume_ul} → {Math.round(after * 10) / 10}{l.verified && ' (verified)'}
                          </td>
                          <td className="px-3 py-1.5">
                            <div className="flex justify-end gap-1">
                              <Button size="sm" disabled={busy || noReason} onClick={() => fixLot.mutate({ id: l.lot_id, volume: l.standard_ul })}>Correct</Button>
                              <Button size="sm" variant="ghost" disabled={busy || noReason} onClick={() => fixLot.mutate({ id: l.lot_id, volume: l.recorded_ul })}>Keep</Button>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Section>

          <Section title="Store vials" count={data.store.length}>
            {data.store.length === 0 ? <p className="text-sm text-slate-400">None.</p> : (
              <div className="border border-slate-200 rounded-lg overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 text-left text-xs font-medium text-slate-500">
                    <tr>
                      <th className="px-3 py-2">Antibody</th><th className="px-3 py-2">Lot</th><th className="px-3 py-2 text-right">Vials</th>
                      <th className="px-3 py-2 text-right">Recorded / vial</th><th className="px-3 py-2 text-right">Standard</th><th className="px-3 py-2"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {data.store.map((r) => (
                      <tr key={r.store_id}>
                        <td className="px-3 py-1.5">
                          <span className="font-medium text-slate-800">{r.antibody_name}</span>
                          <span className="text-xs text-slate-500"> {r.fluorochrome ?? ''}{r.catalog_no ? ` · ${r.catalog_no}` : ''}</span>
                        </td>
                        <td className="px-3 py-1.5 font-mono text-xs">{r.lot_no}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums">{r.quantity}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums text-amber-700 font-medium">{r.recorded_ul} µl</td>
                        <td className="px-3 py-1.5 text-right tabular-nums">{r.standard_ul} µl</td>
                        <td className="px-3 py-1.5">
                          <div className="flex justify-end gap-1">
                            <Button size="sm" disabled={busy} onClick={() => fixStore.mutate({ id: r.store_id, volume: r.standard_ul, keep: false })}>Correct</Button>
                            <Button size="sm" variant="ghost" disabled={busy || noReason} onClick={() => fixStore.mutate({ id: r.store_id, volume: r.recorded_ul, keep: true })}>Keep</Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>

          <Section title="Active antibodies with no standard vial volume" count={data.antibodies_without_volume.length}>
            {data.antibodies_without_volume.length === 0 ? <p className="text-sm text-slate-400">None — every active antibody has a standard volume.</p> : (
              <>
                <p className="text-xs text-slate-500 mb-2">
                  Until a standard is set, receipts for these accept any typed volume, and can't be checked here.
                </p>
                <div className="border border-slate-200 rounded-lg overflow-y-auto max-h-72">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50 text-left text-xs font-medium text-slate-500 sticky top-0">
                      <tr><th className="px-3 py-2">Antibody</th><th className="px-3 py-2">Fluor</th><th className="px-3 py-2">Cat. no</th><th className="px-3 py-2">Vial volume</th></tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {data.antibodies_without_volume.map((ab) => <MissingVolumeRow key={ab.antibody_id} ab={ab} onSaved={refresh} />)}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </Section>
        </div>
      )}
    </Modal>
  )
}
