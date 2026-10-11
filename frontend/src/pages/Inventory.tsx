// pages/Inventory.tsx

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import { CheckCircle, Download, ListPlus, PackagePlus, RefreshCw, Trash2 } from 'lucide-react'
import { useState, useEffect } from 'react'
import { antibodiesApi, exportApi, stockApi, storeStockApi } from '../api/client'
import { Badge, Button, Card, EmptyState, Input, Modal, Select, Spinner } from '../components/ui'
import VialVolumeField, { isNonStandard, vialVolumePayload, vialVolumeValid } from '../components/VialVolumeField'
import type { StockLot } from '../types'

function expiryStatus(lot: StockLot): 'ok' | 'warning' | 'critical' {
  if (!lot.expiry_date) return 'ok'
  const days = Math.ceil((new Date(lot.expiry_date).getTime() - Date.now()) / 86_400_000)
  if (days <= 14)  return 'critical'
  if (days <= 30)  return 'warning'
  return 'ok'
}

// ── Receive Lot Modal ──────────────────────────────────────────────────────

function ReceiveLotModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const { data: antibodies = [] } = useQuery({ queryKey: ['antibodies'], queryFn: () => antibodiesApi.list() })

  const [form, setForm] = useState({
    antibody_id: '',
    lot_no: '',
    initial_volume_ul: '',
    date_received: format(new Date(), 'yyyy-MM-dd'),
    expiry_date: '',
    shipment_id: '',
  })
  const [error, setError] = useState('')
  const [volReason, setVolReason] = useState('')
  const selectedAb = antibodies.find((a) => a.id === Number(form.antibody_id))
  const vol = vialVolumePayload(selectedAb?.vial_volume_ul, form.initial_volume_ul, volReason)

  const mut = useMutation({
    mutationFn: () =>
      stockApi.receive({
        antibody_id: Number(form.antibody_id),
        lot_no: form.lot_no,
        initial_volume_ul: vol.volume,
        volume_override_reason: vol.reason,
        date_received: form.date_received,
        expiry_date: form.expiry_date || undefined,
        shipment_id: form.shipment_id.trim(),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['stock'] })
      qc.invalidateQueries({ queryKey: ['stock-summary'] })
      qc.invalidateQueries({ queryKey: ['shipment-verifications'] })
      qc.invalidateQueries({ queryKey: ['alerts'] })
      setForm((f) => ({ ...f, lot_no: '', initial_volume_ul: '', expiry_date: '', shipment_id: '' }))
      setVolReason('')
      onClose()
    },
    onError: (e: any) => setError(e.response?.data?.detail ?? 'Error receiving lot'),
  })

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }))

  const [storeWarning, setStoreWarning] = useState<string | null>(null)
  const checkStore = async (abId: string) => {
    if (!abId) { setStoreWarning(null); return }
    try {
      const { has_store_stock } = await storeStockApi.check(parseInt(abId))
      setStoreWarning(has_store_stock ? null : 'This antibody has no store stock record. Add vials to Store Stock first.')
    } catch { setStoreWarning(null) }
  }

  return (
    <Modal open={open} onClose={onClose} title="Receive New Lot">
      <div className="space-y-4">
        <Select
          label="Antibody"
          value={form.antibody_id}
          onChange={(e) => { set('antibody_id', e.target.value); set('initial_volume_ul', ''); setVolReason(''); checkStore(e.target.value) }}
        >
          <option value="">Select antibody…</option>
          {antibodies.map((ab) => (
            <option key={ab.id} value={ab.id}>
              {ab.name}{ab.fluorochrome ? ` – ${ab.fluorochrome.name}` : ''}
            </option>
          ))}
        </Select>

        <Input label="Lot number" value={form.lot_no}
          onChange={(e) => set('lot_no', e.target.value)} placeholder="e.g. LOT-12345" />

        {selectedAb && (
          <VialVolumeField
            key={selectedAb.id}
            standard={selectedAb.vial_volume_ul}
            catalogNo={selectedAb.catalog_no}
            value={form.initial_volume_ul}
            onChange={(v) => set('initial_volume_ul', v)}
            reason={volReason}
            onReasonChange={setVolReason}
          />
        )}

        <Input label="Date received" type="date" value={form.date_received}
          onChange={(e) => set('date_received', e.target.value)} />

        <Input label="Shipment ID" value={form.shipment_id}
          onChange={(e) => set('shipment_id', e.target.value)} placeholder="ID assigned to this delivery" />

        <Input label="Expiry date (optional)" type="date" value={form.expiry_date}
          onChange={(e) => set('expiry_date', e.target.value)} />

        {storeWarning && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800">
            ⚠ {storeWarning}
          </div>
        )}
        {error && <p className="text-sm text-red-600">{error}</p>}

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button
            onClick={() => mut.mutate()}
            disabled={mut.isPending || !form.antibody_id || !form.lot_no || !form.shipment_id.trim()
              || !vialVolumeValid(selectedAb?.vial_volume_ul, form.initial_volume_ul, volReason)}
          >
            {mut.isPending ? 'Saving…' : 'Receive lot'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Verify Volume Modal ──────────────────────────────────────────────────────

function VerifyModal({
  lot,
  onClose,
}: {
  lot: StockLot | null
  onClose: () => void
}) {
  const qc = useQueryClient()
  const [vol, setVol] = useState('')
  const [method, setMethod] = useState<'pipette' | 'gravimetric'>('pipette')
  const [increment, setIncrement] = useState('')
  const [cycle, setCycle] = useState('')
  const [error, setError] = useState('')

  const mut = useMutation({
    mutationFn: () => stockApi.verify(lot!.id, {
      verified_volume_ul: Number(vol),
      measurement_method: method,
      pipette_increment_ul: increment ? Number(increment) : null,
      verification_cycle: cycle.trim() || null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['stock'] })
      qc.invalidateQueries({ queryKey: ['stock-summary'] })
      qc.invalidateQueries({ queryKey: ['forecast-all'] })
      onClose()
    },
    onError: (e: any) => setError(e.response?.data?.detail ?? 'Error verifying'),
  })

  return (
    <Modal open={!!lot} onClose={onClose} title="Verify Stock Volume">
      <div className="space-y-4">
        {lot && (
          <div className="bg-slate-50 rounded-lg p-3 text-sm space-y-1">
            <p><span className="text-slate-500">Antibody:</span> <span className="font-medium">{lot.antibody_name}</span></p>
            <p><span className="text-slate-500">Lot:</span> <span className="font-medium">{lot.lot_no}</span></p>
            <p><span className="text-slate-500">System estimate:</span> <span className="font-medium">{lot.current_volume_ul.toFixed(1)} µl</span></p>
          </div>
        )}
        <Input
          label="Measured volume (µl)"
          type="number"
          step="0.1"
          value={vol}
          onChange={(e) => setVol(e.target.value)}
          autoFocus
          placeholder={lot?.current_volume_ul.toFixed(0)}
        />
        <Select label="Measurement method" value={method} onChange={(e) => setMethod(e.target.value as 'pipette' | 'gravimetric')}>
          <option value="pipette">Pipette</option>
          <option value="gravimetric">Gravimetric</option>
        </Select>
        <Input
          label="Pipette increment (µl, optional)"
          type="number"
          step="0.1"
          value={increment}
          onChange={(e) => setIncrement(e.target.value)}
          placeholder="e.g. 5.0"
        />
        <Input
          label="Verification cycle (optional)"
          value={cycle}
          onChange={(e) => setCycle(e.target.value)}
          placeholder="e.g. 2026-09-02 batch A"
        />
        <p className="text-xs text-slate-400">
          This corrects the system estimate. Small differences are expected due to pipetting.
        </p>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={() => mut.mutate()} disabled={mut.isPending || !vol}>
            {mut.isPending ? 'Saving…' : 'Update volume'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}


// ── Bulk Receive Modal ─────────────────────────────────────────────────────

interface BulkRow {
  antibody_id: number
  antibody_name: string
  fluorochrome: string
  vendor: string
  lot_no: string
  initial_volume_ul: string      // '' = standard volume (if set)
  standard_ul: number | null
  volume_reason: string
  expiry_date: string
  date_received: string
}

function BulkReceiveModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const today = new Date().toISOString().slice(0, 10)

  const { data: antibodies = [] } = useQuery({
    queryKey: ['antibodies'],
    queryFn: () => antibodiesApi.list(),
    enabled: open,
  })

  const [rows, setRows] = useState<BulkRow[]>([])
  const [commonDate, setCommonDate] = useState(today)
  const [shipmentId, setShipmentId] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)
  const [createdCount, setCreatedCount] = useState(0)

  // Reset rows whenever modal opens
  useEffect(() => {
    if (open && antibodies.length > 0) {
      setRows(antibodies.map(ab => ({
        antibody_id: ab.id,
        antibody_name: ab.name,
        fluorochrome: ab.fluorochrome?.name ?? '',
        vendor: ab.vendor ?? '',
        lot_no: '',
        initial_volume_ul: '',
        standard_ul: ab.vial_volume_ul ?? null,
        volume_reason: '',
        expiry_date: '',
        date_received: today,
      })))
      setDone(false)
      setCreatedCount(0)
      setCommonDate(today)
    }
  }, [open, antibodies.length])

  const handleOpen = () => {
    setDone(false)
    setCreatedCount(0)
    setCommonDate(today)
    setRows(antibodies.map(ab => ({
      antibody_id: ab.id,
      antibody_name: ab.name,
      fluorochrome: ab.fluorochrome?.name ?? '',
      vendor: ab.vendor ?? '',
      lot_no: '',
      initial_volume_ul: '',
      standard_ul: ab.vial_volume_ul ?? null,
      volume_reason: '',
      expiry_date: '',
      date_received: today,
    })))
  }

  const setField = (idx: number, field: keyof BulkRow, value: string) => {
    setRows(prev => prev.map((r, i) => i === idx ? { ...r, [field]: value } : r))
  }

  const applyCommonDate = () => {
    setRows(prev => prev.map(r => ({ ...r, date_received: commonDate })))
  }

  // A row is ready once it has a lot number and an acceptable volume
  // (blank = the antibody's standard volume; a different volume needs a reason).
  const startedRows = rows.filter(r => r.lot_no.trim() || r.initial_volume_ul.trim())
  const filledRows = startedRows.filter(r => r.lot_no.trim() && vialVolumeValid(r.standard_ul, r.initial_volume_ul, r.volume_reason))
  const incompleteRows = startedRows.length - filledRows.length

  const handleSubmit = async () => {
    const payload = filledRows.map(r => ({
      antibody_id: r.antibody_id,
      lot_no: r.lot_no.trim(),
      initial_volume_ul: vialVolumePayload(r.standard_ul, r.initial_volume_ul, r.volume_reason).volume,
      volume_override_reason: vialVolumePayload(r.standard_ul, r.initial_volume_ul, r.volume_reason).reason,
      date_received: r.date_received || today,
      expiry_date: r.expiry_date || null,
      shipment_id: shipmentId.trim(),
    }))
    setSubmitting(true)
    try {
      const result = await stockApi.bulkReceive(payload) as object[]
      setCreatedCount(result.length)
      qc.invalidateQueries({ queryKey: ['stock'] })
      qc.invalidateQueries({ queryKey: ['shipment-verifications'] })
      qc.invalidateQueries({ queryKey: ['alerts'] })
      setShipmentId('')
      setDone(true)
    } catch (e: any) {
      alert(e?.response?.data?.detail ?? 'Bulk receive failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Bulk Receive Stock"
      
    >
      {done ? (
        <div className="space-y-4 py-4 text-center">
          <p className="text-green-700 font-semibold text-lg">
            ✓ {createdCount} lot{createdCount !== 1 ? 's' : ''} received successfully
          </p>
          <Button onClick={onClose}>Close</Button>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Common date row */}
          <div className="flex items-end gap-3 bg-slate-50 rounded-lg p-3">
            <div className="flex-1">
              <label className="text-xs font-medium text-slate-600">Apply one received date to all rows</label>
              <input
                type="date"
                value={commonDate}
                onChange={e => setCommonDate(e.target.value)}
                className="mt-1 block w-full border border-slate-200 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
              />
            </div>
            <Button variant="secondary" size="sm" onClick={applyCommonDate}>Apply to all</Button>
          </div>

          <div className="bg-slate-50 rounded-lg p-3">
            <label className="text-xs font-medium text-slate-600">Shipment ID for this delivery *</label>
            <input
              value={shipmentId}
              onChange={e => setShipmentId(e.target.value)}
              placeholder="Applies to every row below"
              className="mt-1 block w-full border border-slate-200 rounded px-2 py-1 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-blue-400"
            />
            <p className="text-xs text-slate-400 mt-1">Items from a different shipment need a separate bulk receive.</p>
          </div>

          <p className="text-xs text-slate-500">
            Fill in <span className="font-medium">Lot No</span> for each antibody you are receiving. The volume defaults to the
            antibody's standard vial volume (shown greyed); only type one if the vial label differs, and give a reason. Leave a row blank to skip it.
          </p>

          {/* Table */}
          <div className="overflow-auto max-h-[55vh] border border-slate-200 rounded-lg">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 sticky top-0">
                <tr>
                  <th className="text-left px-3 py-2 font-medium text-slate-600 min-w-[130px]">Antibody</th>
                  <th className="text-left px-3 py-2 font-medium text-slate-600 min-w-[80px]">Fluor</th>
                  <th className="text-left px-3 py-2 font-medium text-slate-600 min-w-[110px]">Lot No *</th>
                  <th className="text-left px-3 py-2 font-medium text-slate-600 min-w-[90px]">Vol µl</th>
                  <th className="text-left px-3 py-2 font-medium text-slate-600 min-w-[120px]">Expiry</th>
                  <th className="text-left px-3 py-2 font-medium text-slate-600 min-w-[120px]">Received</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((row, idx) => {
                  const filled = row.lot_no.trim() || row.initial_volume_ul.trim()
                  return (
                    <tr key={row.antibody_id} className={filled ? 'bg-blue-50' : ''}>
                      <td className="px-3 py-1.5 font-medium text-slate-700">{row.antibody_name}</td>
                      <td className="px-3 py-1.5 text-slate-500 text-xs">{row.fluorochrome}</td>
                      <td className="px-3 py-1.5">
                        <input
                          type="text"
                          value={row.lot_no}
                          onChange={e => setField(idx, 'lot_no', e.target.value)}
                          placeholder="e.g. 1234567"
                          className="w-full border border-slate-200 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-400"
                        />
                      </td>
                      <td className="px-3 py-1.5">
                        <input
                          type="number"
                          min="0"
                          step="0.5"
                          value={row.initial_volume_ul}
                          onChange={e => setField(idx, 'initial_volume_ul', e.target.value)}
                          placeholder={row.standard_ul != null ? String(row.standard_ul) : 'µl *'}
                          title={row.standard_ul != null ? `Standard vial volume ${row.standard_ul} µl — leave blank to use it` : 'No standard volume set in the antibody master'}
                          className={`w-20 border rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-400 ${
                            isNonStandard(row.standard_ul, row.initial_volume_ul) ? 'border-amber-400 bg-amber-50' : 'border-slate-200'
                          }`}
                        />
                        {isNonStandard(row.standard_ul, row.initial_volume_ul) && (
                          <input
                            type="text"
                            value={row.volume_reason}
                            onChange={e => setField(idx, 'volume_reason', e.target.value)}
                            placeholder={`Reason (std ${row.standard_ul} µl)`}
                            className="mt-1 w-36 border border-amber-400 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-amber-400"
                          />
                        )}
                      </td>
                      <td className="px-3 py-1.5">
                        <input
                          type="date"
                          value={row.expiry_date}
                          onChange={e => setField(idx, 'expiry_date', e.target.value)}
                          className="w-full border border-slate-200 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-400"
                        />
                      </td>
                      <td className="px-3 py-1.5">
                        <input
                          type="date"
                          value={row.date_received}
                          onChange={e => setField(idx, 'date_received', e.target.value)}
                          className="w-full border border-slate-200 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-400"
                        />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between pt-1">
            <p className="text-xs text-slate-500">
              {filledRows.length} of {rows.length} rows ready to submit
              {incompleteRows > 0 && <span className="text-amber-700"> · {incompleteRows} incomplete (lot no, volume or reason missing)</span>}
            </p>
            <div className="flex gap-2">
              <Button variant="secondary" onClick={onClose}>Cancel</Button>
              <Button
                onClick={handleSubmit}
                disabled={submitting || filledRows.length === 0 || !shipmentId.trim()}
              >
                {submitting ? 'Receiving…' : `Receive ${filledRows.length} lot${filledRows.length !== 1 ? 's' : ''}`}
              </Button>
            </div>
          </div>
        </div>
      )}
    </Modal>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────

export default function Inventory() {
  const [receiveOpen, setReceiveOpen] = useState(false)
  const [bulkReceiveOpen, setBulkReceiveOpen] = useState(false)
  const [verifyLot, setVerifyLot] = useState<StockLot | null>(null)
  const [search, setSearch] = useState('')

  const { data: lots = [], isLoading } = useQuery({
    queryKey: ['stock'],
    queryFn: () => stockApi.list(undefined, true),
    refetchInterval: 60_000,
  })

  const qc = useQueryClient()

  const deleteLot = useMutation({
    mutationFn: (lot: StockLot) => stockApi.remove(lot.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['stock'] }),
    onError: (err: any) => {
      const detail = err?.response?.data?.detail ?? 'Could not delete lot'
      alert(detail)
    },
  })

  const filtered = lots.filter(
    (l) =>
      l.antibody_name.toLowerCase().includes(search.toLowerCase()) ||
      l.lot_no.toLowerCase().includes(search.toLowerCase()),
  )

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Inventory</h1>
          <p className="text-sm text-slate-500 mt-0.5">Active stock lots</p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={() => exportApi.stockPosition()}>
            <Download className="w-3.5 h-3.5" /> Stock report
          </Button>
          <Button variant="secondary" size="sm" onClick={() => exportApi.inventory()}>
            <Download className="w-3.5 h-3.5" /> Export CSV
          </Button>
          <Button variant="secondary" size="sm" onClick={() => setBulkReceiveOpen(true)}>
            <ListPlus className="w-4 h-4" /> Bulk receive
          </Button>
          <Button onClick={() => setReceiveOpen(true)}>
            <PackagePlus className="w-4 h-4" /> Receive lot
          </Button>
        </div>
      </div>

      {/* Search */}
      <Input
        placeholder="Search antibody or lot number…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="max-w-sm"
      />

      {/* Table */}
      <Card padding={false}>
        {isLoading ? (
          <Spinner className="py-16" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-100">
                  {['Antibody', 'Vendor', 'Fluor', 'Lot No', 'Initial', 'Current', '% Left', 'Store Vials', 'Received', 'Expiry', 'Last verified', ''].map((h) => (
                    <th key={h} className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filtered.length === 0 && (
                  <tr><td colSpan={12}><EmptyState message="No lots found" /></td></tr>
                )}
                {filtered.map((lot) => {
                  const es = expiryStatus(lot)
                  const pct = lot.percent_remaining
                  return (
                    <tr key={lot.id} className="hover:bg-slate-50 transition-colors">
                      <td className="px-4 py-3 font-medium text-slate-800">{lot.antibody_name}</td>
                      <td className="px-4 py-3 text-slate-500 text-xs">{lot.vendor ?? <span className="text-slate-300">—</span>}</td>
                      <td className="px-4 py-3 text-slate-500 text-xs">{lot.fluorochrome ?? <span className="text-slate-300">—</span>}</td>
                      <td className="px-4 py-3 text-slate-500 font-mono text-xs">
                        {lot.lot_no}
                        {lot.shipment_id && <div className="text-[11px] text-slate-400" title="Shipment ID">{lot.shipment_id}</div>}
                      </td>
                      <td className="px-4 py-3 text-slate-600 tabular-nums">{lot.initial_volume_ul.toFixed(0)} µl</td>
                      <td className="px-4 py-3 font-semibold tabular-nums">
                        <span className={pct < 15 ? 'text-red-600' : pct < 30 ? 'text-amber-600' : 'text-slate-800'}>
                          {lot.current_volume_ul.toFixed(1)} µl
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        {/* Progress bar */}
                        <div className="flex items-center gap-2">
                          <div className="w-16 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${pct < 15 ? 'bg-red-500' : pct < 30 ? 'bg-amber-400' : 'bg-emerald-500'}`}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                          <span className="text-xs text-slate-500 tabular-nums">{pct.toFixed(0)}%</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-center tabular-nums">
                        <span className={lot.store_vial_count === 0 ? 'text-slate-300' : lot.store_vial_count <= 1 ? 'text-amber-600 font-medium' : 'text-slate-600 font-medium'}>
                          {lot.store_vial_count}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-500 whitespace-nowrap">
                        {format(parseISO(lot.date_received), 'd MMM yy')}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        {lot.expiry_date ? (
                          <span className={es === 'critical' ? 'text-red-600 font-medium' : es === 'warning' ? 'text-amber-600' : 'text-slate-500'}>
                            {format(parseISO(lot.expiry_date), 'd MMM yy')}
                          </span>
                        ) : <span className="text-slate-300">—</span>}
                      </td>
                      <td className="px-4 py-3 text-slate-400 text-xs whitespace-nowrap">
                        {lot.last_verified_date
                          ? <span>{format(parseISO(lot.last_verified_date), 'd MMM yy')} · {lot.last_verified_volume_ul?.toFixed(0)} µl</span>
                          : <span className="text-slate-300">Never</span>}
                      </td>
                      <td className="px-4 py-3">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setVerifyLot(lot)}
                          title="Verify volume"
                        >
                          <CheckCircle className="w-3.5 h-3.5" />
                          Verify
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            if (confirm(`Delete lot ${lot.lot_no} (${lot.antibody_name})? This cannot be undone.`)) {
                              deleteLot.mutate(lot)
                            }
                          }}
                          title="Delete lot"
                          className="text-red-500 hover:text-red-700"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
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

      <ReceiveLotModal open={receiveOpen} onClose={() => setReceiveOpen(false)} />
      <BulkReceiveModal open={bulkReceiveOpen} onClose={() => setBulkReceiveOpen(false)} />
      <VerifyModal lot={verifyLot} onClose={() => setVerifyLot(null)} />
    </div>
  )
}
