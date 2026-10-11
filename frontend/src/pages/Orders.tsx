// pages/Orders.tsx

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import { Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { antibodiesApi, ordersApi } from '../api/client'
import { Badge, Button, Card, EmptyState, Input, Modal, Select, Spinner } from '../components/ui'
import VialVolumeField, { vialVolumePayload, vialVolumeValid } from '../components/VialVolumeField'
import type { Order } from '../types'
import { useAuth } from '../auth/AuthContext'

// ── Create Order Modal ──────────────────────────────────────────────────────

function CreateOrderModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const { data: antibodies = [] } = useQuery({ queryKey: ['antibodies'], queryFn: () => antibodiesApi.list() })
  const [form, setForm] = useState({
    antibody_id: '', quantity_vials: '1', volume_per_vial_ul: '',
    order_date: format(new Date(), 'yyyy-MM-dd'),
    expected_delivery_date: '', po_number: '', notes: '',
  })
  const [error, setError] = useState('')
  const [volReason, setVolReason] = useState('')
  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }))
  const selectedAb = antibodies.find((a) => a.id === Number(form.antibody_id))
  const vol = vialVolumePayload(selectedAb?.vial_volume_ul, form.volume_per_vial_ul, volReason)

  const mut = useMutation({
    mutationFn: () => ordersApi.create({
      antibody_id: Number(form.antibody_id),
      quantity_vials: Number(form.quantity_vials),
      volume_per_vial_ul: vol.volume,
      volume_override_reason: vol.reason,
      order_date: form.order_date,
      expected_delivery_date: form.expected_delivery_date || undefined,
      po_number: form.po_number || undefined,
      notes: form.notes || undefined,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['orders'] }); onClose() },
    onError: (e: any) => setError(e.response?.data?.detail ?? 'Error creating order'),
  })

  return (
    <Modal open={open} onClose={onClose} title="New Purchase Order">
      <div className="space-y-4">
        <Select label="Antibody" value={form.antibody_id} onChange={(e) => { set('antibody_id', e.target.value); set('volume_per_vial_ul', ''); setVolReason('') }}>
          <option value="">Select antibody…</option>
          {antibodies.map((ab) => (
            <option key={ab.id} value={ab.id}>{ab.name}{ab.fluorochrome ? ` – ${ab.fluorochrome.name}` : ''}</option>
          ))}
        </Select>
        <Input label="Vials" type="number" min="1" value={form.quantity_vials} onChange={(e) => set('quantity_vials', e.target.value)} />
        {selectedAb && (
          <VialVolumeField
            key={selectedAb.id}
            label="µl per vial"
            standard={selectedAb.vial_volume_ul}
            catalogNo={selectedAb.catalog_no}
            value={form.volume_per_vial_ul}
            onChange={(v) => set('volume_per_vial_ul', v)}
            reason={volReason}
            onReasonChange={setVolReason}
          />
        )}
        <div className="grid grid-cols-2 gap-3">
          <Input label="Order date" type="date" value={form.order_date} onChange={(e) => set('order_date', e.target.value)} />
          <Input label="Expected delivery" type="date" value={form.expected_delivery_date} onChange={(e) => set('expected_delivery_date', e.target.value)} />
        </div>
        <Input label="PO number (optional)" value={form.po_number} onChange={(e) => set('po_number', e.target.value)} />
        <Input label="Notes (optional)" value={form.notes} onChange={(e) => set('notes', e.target.value)} />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={() => mut.mutate()} disabled={mut.isPending || !form.antibody_id
            || !vialVolumeValid(selectedAb?.vial_volume_ul, form.volume_per_vial_ul, volReason)}>
            {mut.isPending ? 'Saving…' : 'Place order'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Deliver Modal ───────────────────────────────────────────────────────────

function DeliverModal({ order, onClose }: { order: Order | null; onClose: () => void }) {
  const qc = useQueryClient()
  const { data: antibodies = [] } = useQuery({ queryKey: ['antibodies'], queryFn: () => antibodiesApi.list(), enabled: !!order })
  const [form, setForm] = useState({
    lot_no: '', expiry_date: '', delivery_date: format(new Date(), 'yyyy-MM-dd'), shipment_id: '',
  })
  const [error, setError] = useState('')
  const [volume, setVolume] = useState('')
  const [volReason, setVolReason] = useState('')
  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }))
  const ab = antibodies.find((a) => a.id === order?.antibody_id)
  const standard = ab?.vial_volume_ul ?? null
  // Without a standard volume, start from the ordered volume.
  useEffect(() => {
    setVolume(order && standard == null ? String(order.volume_per_vial_ul) : '')
    setVolReason(''); setError('')
  }, [order?.id, standard])
  const vol = vialVolumePayload(standard, volume, volReason)

  const mut = useMutation({
    mutationFn: () => ordersApi.deliver(order!.id, {
      lot_no: form.lot_no,
      expiry_date: form.expiry_date || undefined,
      delivery_date: form.delivery_date || undefined,
      shipment_id: form.shipment_id.trim(),
      actual_volume_per_vial_ul: vol.volume,
      volume_override_reason: vol.reason,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['orders'] })
      qc.invalidateQueries({ queryKey: ['stock'] })
      qc.invalidateQueries({ queryKey: ['stock-summary'] })
      qc.invalidateQueries({ queryKey: ['shipment-verifications'] })
      qc.invalidateQueries({ queryKey: ['alerts'] })
      onClose()
    },
    onError: (e: any) => setError(e.response?.data?.detail ?? 'Error marking delivered'),
  })

  return (
    <Modal open={!!order} onClose={onClose} title="Mark as Delivered">
      <div className="space-y-4">
        {order && (
          <div className="bg-slate-50 rounded-lg p-3 text-sm">
            <p className="font-medium">{order.antibody_name}</p>
            <p className="text-slate-500">{order.quantity_vials} vial{order.quantity_vials > 1 ? 's' : ''} × {order.volume_per_vial_ul} µl</p>
          </div>
        )}
        <Input label="Lot number" value={form.lot_no} onChange={(e) => set('lot_no', e.target.value)} placeholder="Lot number on vial" autoFocus />
        {order && ab && (
          <VialVolumeField
            key={order.id}
            label="Volume per vial received (µl)"
            standard={standard}
            catalogNo={ab.catalog_no}
            value={volume}
            onChange={setVolume}
            reason={volReason}
            onReasonChange={setVolReason}
          />
        )}
        <Input label="Shipment ID" value={form.shipment_id} onChange={(e) => set('shipment_id', e.target.value)} placeholder="ID assigned to this delivery" />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Delivery date" type="date" value={form.delivery_date} onChange={(e) => set('delivery_date', e.target.value)} />
          <Input label="Expiry date" type="date" value={form.expiry_date} onChange={(e) => set('expiry_date', e.target.value)} />
        </div>
        <p className="text-xs text-slate-400">
          Stock lots will be created automatically in Inventory.
        </p>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={() => mut.mutate()} disabled={mut.isPending || !form.lot_no || !form.shipment_id.trim()
            || !vialVolumeValid(standard, volume, volReason)}>
            {mut.isPending ? 'Saving…' : 'Confirm delivery'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────

export default function OrdersPage() {
  const { isAdmin } = useAuth()
  const [createOpen, setCreateOpen] = useState(false)
  const [deliverOrder, setDeliverOrder] = useState<Order | null>(null)
  const [statusFilter, setStatusFilter] = useState('pending')

  const { data: orders = [], isLoading } = useQuery({
    queryKey: ['orders', statusFilter],
    queryFn: () => ordersApi.list(statusFilter || undefined),
  })

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Orders</h1>
          <p className="text-sm text-slate-500 mt-0.5">Purchase order tracking</p>
        </div>
        {isAdmin && (
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="w-4 h-4" />
            New order
          </Button>
        )}
      </div>

      {/* Filter tabs */}
      <div className="flex gap-1 bg-slate-100 p-1 rounded-lg w-fit">
        {['pending', 'delivered', 'cancelled', ''].map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-1.5 text-sm rounded-md font-medium transition-colors ${
              statusFilter === s ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            {s === '' ? 'All' : s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}
      </div>

      <Card padding={false}>
        {isLoading ? (
          <Spinner className="py-16" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-100">
                  {['Antibody', 'Qty', 'Volume', 'Order date', 'Expected', 'PO', 'Status', ''].map((h) => (
                    <th key={h} className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {orders.length === 0 && (
                  <tr><td colSpan={8}><EmptyState message="No orders found" /></td></tr>
                )}
                {orders.map((o) => (
                  <tr key={o.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-4 py-3 font-medium text-slate-800">{o.antibody_name}</td>
                    <td className="px-4 py-3 text-slate-600">{o.quantity_vials}</td>
                    <td className="px-4 py-3 text-slate-500">{o.total_volume_ul.toFixed(0)} µl</td>
                    <td className="px-4 py-3 text-slate-500 whitespace-nowrap">
                      {format(parseISO(o.order_date), 'd MMM yyyy')}
                    </td>
                    <td className="px-4 py-3 text-slate-500 whitespace-nowrap">
                      {o.expected_delivery_date
                        ? format(parseISO(o.expected_delivery_date), 'd MMM yyyy')
                        : <span className="text-slate-300">—</span>}
                    </td>
                    <td className="px-4 py-3 text-slate-400 text-xs font-mono">{o.po_number ?? '—'}</td>
                    <td className="px-4 py-3">
                      <Badge variant={o.status as any}>{o.status}</Badge>
                    </td>
                    <td className="px-4 py-3">
                      {isAdmin && o.status === 'pending' && (
                        <Button variant="secondary" size="sm" onClick={() => setDeliverOrder(o)}>
                          Mark delivered
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <CreateOrderModal open={createOpen} onClose={() => setCreateOpen(false)} />
      <DeliverModal order={deliverOrder} onClose={() => setDeliverOrder(null)} />
    </div>
  )
}
