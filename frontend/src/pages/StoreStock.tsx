// pages/StoreStock.tsx — Whole-vial stockroom management

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import { PackagePlus, Trash2, PackageOpen, PackageCheck, AlertTriangle } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { VerificationBadge } from '../components/CocktailTraceModal'
import { antibodiesApi, storeStockApi } from '../api/client'
import { Badge, Button, Card, EmptyState, Input, Modal, Spinner } from '../components/ui'
import VialVolumeField, { vialVolumePayload, vialVolumeValid } from '../components/VialVolumeField'

// ── Receive vials modal ──────────────────────────────────────────────────────

function ReceiveStoreModal({ open, onClose, onTriggered }: {
  open: boolean
  onClose: () => void
  onTriggered: (msg: string) => void
}) {
  const qc = useQueryClient()
  const today = new Date().toISOString().slice(0, 10)
  const { data: antibodies = [] } = useQuery({
    queryKey: ['antibodies'],
    queryFn: () => antibodiesApi.list(),
    enabled: open,
  })

  const [abSearch, setAbSearch] = useState('')
  const [selectedAbId, setSelectedAbId] = useState<number | null>(null)
  const [form, setForm] = useState({
    lot_no: '', quantity: '1', volume_per_vial_ul: '',
    vendor: '', catalog_no: '', received_date: today, expiry_date: '', shipment_id: '', notes: '',
  })
  const [error, setError] = useState('')
  const [volReason, setVolReason] = useState('')

  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))
  const selectedAb = antibodies.find(a => a.id === selectedAbId)
  const vol = vialVolumePayload(selectedAb?.vial_volume_ul, form.volume_per_vial_ul, volReason)
  const pickAntibody = (id: number | null) => {
    const ab = antibodies.find(a => a.id === id)
    setSelectedAbId(id); setAbSearch(''); setVolReason('')
    // Catalogue number and vendor default from the antibody master
    setForm(f => ({ ...f, volume_per_vial_ul: '', catalog_no: ab?.catalog_no ?? '', vendor: ab?.vendor ?? '' }))
  }
  const filteredAbs = antibodies.filter(ab =>
    ab.name.toLowerCase().includes(abSearch.toLowerCase()) ||
    (ab.fluorochrome?.name ?? '').toLowerCase().includes(abSearch.toLowerCase())
  )

  const mut = useMutation({
    mutationFn: () => storeStockApi.receive({
      antibody_id: selectedAbId,
      lot_no: form.lot_no,
      quantity: parseInt(form.quantity),
      volume_per_vial_ul: vol.volume,
      volume_override_reason: vol.reason,
      vendor: form.vendor || undefined,
      catalog_no: form.catalog_no || undefined,
      received_date: form.received_date,
      expiry_date: form.expiry_date || undefined,
      shipment_id: form.shipment_id.trim(),
      notes: form.notes || undefined,
    }),
    onSuccess: (row: any) => {
      qc.invalidateQueries({ queryKey: ['store-stock'] })
      qc.invalidateQueries({ queryKey: ['shipment-verifications'] })
      qc.invalidateQueries({ queryKey: ['alerts'] })
      if (row?.verification_triggered) {
        onTriggered(
          `${row.antibody_name}: shipment ${row.shipment_id} differs from the previous shipment. ` +
          `A shipment-to-shipment verification is due within 48 h.`,
        )
      }
      onClose()
      setSelectedAbId(null); setAbSearch(''); setVolReason('')
      setForm({ lot_no: '', quantity: '1', volume_per_vial_ul: '', vendor: '', catalog_no: '', received_date: today, expiry_date: '', shipment_id: '', notes: '' })
    },
    onError: (e: any) => setError(e.response?.data?.detail ?? 'Error'),
  })

  return (
    <Modal open={open} onClose={onClose} title="Receive vials to store">
      <div className="space-y-3">
        {/* Antibody search */}
        <div>
          <label className="text-xs font-medium text-slate-600 block mb-1">Antibody</label>
          {selectedAb ? (
            <div className="flex items-center justify-between bg-blue-50 border border-blue-200 rounded-lg px-3 py-2">
              <span className="text-sm font-medium text-slate-800">
                {selectedAb.name}
                {selectedAb.fluorochrome && <span className="text-slate-400 ml-1.5">· {selectedAb.fluorochrome.name}</span>}
              </span>
              <button onClick={() => pickAntibody(null)} className="text-xs text-slate-400 hover:text-red-500">✕</button>
            </div>
          ) : (
            <div className="space-y-1">
              <input
                type="text" value={abSearch} onChange={e => setAbSearch(e.target.value)}
                placeholder="Search antibody…"
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                autoFocus
              />
              {abSearch.length > 0 && (
                <div className="border border-slate-200 rounded-lg overflow-hidden max-h-40 overflow-y-auto shadow-sm">
                  {filteredAbs.length === 0
                    ? <p className="px-3 py-2 text-sm text-slate-400">No matches</p>
                    : filteredAbs.map(ab => (
                      <button key={ab.id} onClick={() => pickAntibody(ab.id)}
                        className="w-full text-left px-3 py-2 text-sm hover:bg-blue-50 flex justify-between border-b border-slate-100 last:border-0">
                        <span className="font-medium">{ab.name}</span>
                        <span className="text-xs text-slate-400">{ab.fluorochrome?.name ?? ''}</span>
                      </button>
                    ))}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Input label="Lot No" value={form.lot_no} onChange={e => set('lot_no', e.target.value)} placeholder="Batch/lot number" />
          <Input label="Qty (vials)" type="number" min="1" value={form.quantity} onChange={e => set('quantity', e.target.value)} />
        </div>
        {selectedAb && (
          <VialVolumeField
            key={selectedAb.id}
            label="Vol per vial (µl)"
            standard={selectedAb.vial_volume_ul}
            catalogNo={selectedAb.catalog_no}
            value={form.volume_per_vial_ul}
            onChange={(v) => set('volume_per_vial_ul', v)}
            reason={volReason}
            onReasonChange={setVolReason}
          />
        )}
        <Input label="Vendor" value={form.vendor} onChange={e => set('vendor', e.target.value)} />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Received date" type="date" value={form.received_date} onChange={e => set('received_date', e.target.value)} />
          <Input label="Expiry date" type="date" value={form.expiry_date} onChange={e => set('expiry_date', e.target.value)} />
        </div>
        <Input label="Catalog No (optional)" value={form.catalog_no} onChange={e => set('catalog_no', e.target.value)} />
        <Input label="Shipment ID" value={form.shipment_id} onChange={e => set('shipment_id', e.target.value)} placeholder="ID assigned to this delivery" />
        <Input label="Notes (optional)" value={form.notes} onChange={e => set('notes', e.target.value)} />

        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button
            onClick={() => mut.mutate()}
            disabled={!selectedAbId || !form.lot_no || !form.quantity || !form.shipment_id.trim() || mut.isPending
              || !vialVolumeValid(selectedAb?.vial_volume_ul, form.volume_per_vial_ul, volReason)}
          >
            {mut.isPending ? 'Saving…' : 'Receive to store'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function StoreStockPage() {
  const qc = useQueryClient()
  const [receiveOpen, setReceiveOpen] = useState(false)
  const [showAll, setShowAll] = useState(false)
  const [search, setSearch] = useState('')
  const [triggerMsg, setTriggerMsg] = useState<string | null>(null)

  const { data: rows = [], isLoading } = useQuery({
    queryKey: ['store-stock', showAll],
    queryFn: () => storeStockApi.list(!showAll) as Promise<any[]>,
  })

  const openVial = useMutation({
    mutationFn: (id: number) => storeStockApi.openVial(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['store-stock'] })
      qc.invalidateQueries({ queryKey: ['stock'] })
    },
    onError: (e: any) => alert(e.response?.data?.detail ?? 'Failed to open vial'),
  })

  const remove = useMutation({
    mutationFn: (id: number) => storeStockApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['store-stock'] }),
  })

  const filtered = rows.filter((r: any) =>
    r.antibody_name.toLowerCase().includes(search.toLowerCase()) ||
    r.lot_no.toLowerCase().includes(search.toLowerCase()) ||
    (r.vendor ?? '').toLowerCase().includes(search.toLowerCase()) ||
    (r.shipment_id ?? '').toLowerCase().includes(search.toLowerCase())
  )

  const totalVials = rows.reduce((s: number, r: any) => s + r.quantity, 0)

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Store Stock</h1>
          <p className="text-sm text-slate-500 mt-0.5">Unopened vials in the stockroom — {totalVials} vial{totalVials !== 1 ? 's' : ''} in store</p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={() => setShowAll(v => !v)}>
            {showAll ? 'Show in-stock only' : 'Show all (incl. empty)'}
          </Button>
          <Button onClick={() => setReceiveOpen(true)}>
            <PackagePlus className="w-4 h-4" /> Receive vials
          </Button>
        </div>
      </div>

      {triggerMsg && (
        <div className="flex items-start gap-2.5 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-900">
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <div className="flex-1">
            {triggerMsg}{' '}
            <Link to="/shipment-qc" className="font-medium underline">Open Shipment QC</Link>
          </div>
          <button onClick={() => setTriggerMsg(null)} className="text-amber-500 hover:text-amber-800">✕</button>
        </div>
      )}

      <input
        type="text" value={search} onChange={e => setSearch(e.target.value)}
        placeholder="Search antibody, lot, vendor or shipment…"
        className="w-full max-w-sm border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
      />

      <Card padding={false}>
        {isLoading ? <Spinner className="py-12" /> : filtered.length === 0 ? (
          <EmptyState message="No store stock records. Receive vials to get started." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50">
                  {['Antibody', 'Fluorochrome', 'Lot No', 'Vendor', 'Vials', 'Vol/vial', 'Total µl', 'Shipment ID', 'Received', 'Expiry', ''].map(h => (
                    <th key={h} className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filtered.map((row: any) => {
                  const today = new Date()
                  const expiry = row.expiry_date ? new Date(row.expiry_date) : null
                  const daysToExpiry = expiry ? Math.round((expiry.getTime() - today.getTime()) / 86400000) : null
                  const expired = daysToExpiry !== null && daysToExpiry < 0
                  const expiringSoon = daysToExpiry !== null && daysToExpiry <= 90 && !expired
                  return (
                    <tr key={row.id} className={row.quantity === 0 ? 'opacity-40' : ''}>
                      <td className="px-4 py-3 font-medium text-slate-800">{row.antibody_name}</td>
                      <td className="px-4 py-3 text-slate-500 text-xs">{row.fluorochrome ?? '—'}</td>
                      <td className="px-4 py-3 text-slate-600 font-mono text-xs">{row.lot_no}</td>
                      <td className="px-4 py-3 text-slate-500 text-xs">{row.vendor ?? '—'}</td>
                      <td className="px-4 py-3">
                        <span className={`font-semibold tabular-nums ${row.quantity === 0 ? 'text-slate-400' : row.quantity <= 1 ? 'text-amber-600' : 'text-slate-800'}`}>
                          {row.quantity}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-600 tabular-nums">{row.volume_per_vial_ul} µl</td>
                      <td className="px-4 py-3 text-slate-600 tabular-nums font-medium">{row.total_store_ul} µl</td>
                      <td className="px-4 py-3 text-xs">
                        <div className="font-mono text-slate-500">{row.shipment_id ?? '—'}</div>
                        {row.verification_status && (
                          <Link to="/shipment-qc" className="inline-block mt-0.5">
                            <VerificationBadge status={row.verification_status} />
                          </Link>
                        )}
                      </td>
                      <td className="px-4 py-3 text-slate-500 text-xs">
                        {row.received_date ? format(new Date(row.received_date), 'd MMM yy') : '—'}
                      </td>
                      <td className="px-4 py-3 text-xs">
                        {row.expiry_date ? (
                          <span className={expired ? 'text-red-600 font-medium' : expiringSoon ? 'text-amber-600' : 'text-slate-500'}>
                            {format(new Date(row.expiry_date), 'd MMM yy')}
                            {expired && ' ⚠'}
                          </span>
                        ) : '—'}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex gap-1.5 items-center">
                          <Button
                            variant="ghost" size="sm"
                            onClick={() => {
                              if (confirm(`Open 1 vial of ${row.antibody_name} (lot ${row.lot_no})?\nThis will add it to inventory and deduct 1 from store.`))
                                openVial.mutate(row.id)
                            }}
                            disabled={row.quantity === 0 || openVial.isPending}
                            title="Open vial → move to inventory"
                          >
                            <PackageOpen className="w-3.5 h-3.5" />
                            Open vial
                          </Button>
                          <button
                            onClick={() => { if (confirm('Delete this store record?')) remove.mutate(row.id) }}
                            className="text-slate-300 hover:text-red-500 transition-colors"
                            title="Delete"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <ReceiveStoreModal open={receiveOpen} onClose={() => setReceiveOpen(false)} onTriggered={setTriggerMsg} />
    </div>
  )
}
