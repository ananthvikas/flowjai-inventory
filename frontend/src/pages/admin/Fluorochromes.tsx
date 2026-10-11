// pages/admin/Fluorochromes.tsx

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus } from 'lucide-react'
import { useState } from 'react'
import { fluorochromesApi } from '../../api/client'
import { Badge, Button, Card, EmptyState, Input, Modal, Spinner } from '../../components/ui'
import type { Fluorochrome } from '../../types'

// ── Laser options common in flow cytometry ──────────────────────────────────

const LASER_OPTIONS = [
  'Blue 488nm',
  'Red 638nm',
  'Violet 405nm',
  'Yellow-Green 561nm',
  'UV 355nm',
  'IR 785nm',
]

// ── Form modal (shared for create and edit) ─────────────────────────────────

function FluorochromeModal({
  open,
  onClose,
  existing,
}: {
  open: boolean
  onClose: () => void
  existing?: Fluorochrome
}) {
  const qc = useQueryClient()
  const isEdit = !!existing

  const [form, setForm] = useState({
    name:           existing?.name           ?? '',
    excitation_nm:  existing?.excitation_nm  != null ? String(existing.excitation_nm) : '',
    emission_nm:    existing?.emission_nm    != null ? String(existing.emission_nm)   : '',
    laser:          existing?.laser          ?? '',
  })
  const [error, setError] = useState('')
  const set = (k: string, v: string) => { setForm(f => ({ ...f, [k]: v })); setError('') }

  const mut = useMutation({
    mutationFn: () => {
      const payload = {
        name:          form.name,
        excitation_nm: form.excitation_nm ? Number(form.excitation_nm) : null,
        emission_nm:   form.emission_nm   ? Number(form.emission_nm)   : null,
        laser:         form.laser || null,
      }
      return isEdit
        ? fluorochromesApi.update(existing!.id, payload)
        : fluorochromesApi.create(payload as any)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['fluorochromes'] })
      // Also invalidate antibodies so their fluorochrome labels refresh
      qc.invalidateQueries({ queryKey: ['antibodies'] })
      onClose()
    },
    onError: (e: any) => setError(e.response?.data?.detail ?? 'Error saving fluorochrome'),
  })

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={isEdit ? `Edit — ${existing!.name}` : 'New Fluorochrome'}
    >
      <div className="space-y-4">

        <Input
          label="Name"
          value={form.name}
          onChange={e => set('name', e.target.value)}
          placeholder="e.g. PE-Cy7, BV786, FITC"
          autoFocus
        />

        {/* Laser — free-text with datalist suggestions */}
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-slate-700">Laser</label>
          <input
            list="laser-options"
            value={form.laser}
            onChange={e => set('laser', e.target.value)}
            placeholder="e.g. Blue 488nm"
            className="px-3.5 py-2 text-sm border border-slate-300 rounded-lg
              focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
          />
          <datalist id="laser-options">
            {LASER_OPTIONS.map(l => <option key={l} value={l} />)}
          </datalist>
          <p className="text-xs text-slate-400">
            Type or choose from common options above
          </p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Excitation (nm)"
            type="number"
            value={form.excitation_nm}
            onChange={e => set('excitation_nm', e.target.value)}
            placeholder="488"
          />
          <Input
            label="Emission peak (nm)"
            type="number"
            value={form.emission_nm}
            onChange={e => set('emission_nm', e.target.value)}
            placeholder="578"
          />
        </div>

        {/* Live preview */}
        {form.name && (
          <div className="bg-slate-50 rounded-lg px-4 py-3 text-xs text-slate-600 space-y-0.5">
            <p className="font-medium text-slate-800">{form.name}</p>
            {form.laser && <p>Laser: {form.laser}</p>}
            {form.excitation_nm && form.emission_nm && (
              <p>Ex {form.excitation_nm} nm → Em {form.emission_nm} nm</p>
            )}
          </div>
        )}

        {error && <p className="text-sm text-red-600">{error}</p>}

        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button
            onClick={() => mut.mutate()}
            disabled={mut.isPending || !form.name}
          >
            {mut.isPending ? 'Saving…' : isEdit ? 'Save changes' : 'Add fluorochrome'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function FluorochromesPage() {
  const qc = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [editing, setEditing] = useState<Fluorochrome | null>(null)

  const { data: fluors = [], isLoading } = useQuery({
    queryKey: ['fluorochromes'],
    queryFn: fluorochromesApi.list,
  })

  const del = useMutation({
    mutationFn: (id: number) => fluorochromesApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['fluorochromes'] })
      qc.invalidateQueries({ queryKey: ['antibodies'] })
    },
    onError: (e: any) => alert(e.response?.data?.detail ?? 'Cannot delete — fluorochrome may be in use'),
  })

  // Group by laser for a cleaner display
  const grouped = fluors.reduce<Record<string, Fluorochrome[]>>((acc, f) => {
    const key = f.laser ?? 'No laser assigned'
    acc[key] = acc[key] ?? []
    acc[key].push(f)
    return acc
  }, {})

  const laserOrder = [
    'Violet 405nm',
    'Blue 488nm',
    'Yellow-Green 561nm',
    'Red 638nm',
    'UV 355nm',
    'IR 785nm',
    'No laser assigned',
  ]
  const sortedGroups = [
    ...laserOrder.filter(l => grouped[l]),
    ...Object.keys(grouped).filter(l => !laserOrder.includes(l)),
  ]

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Fluorochromes</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Master list — add new fluorochromes here before assigning them to antibodies
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="w-4 h-4" /> Add fluorochrome
        </Button>
      </div>

      {isLoading ? (
        <Spinner className="py-16" />
      ) : fluors.length === 0 ? (
        <Card>
          <EmptyState message="No fluorochromes yet — add your first one above" />
        </Card>
      ) : (
        <div className="space-y-4">
          {sortedGroups.map(laser => (
            <div key={laser}>
              {/* Laser group header */}
              <div className="flex items-center gap-3 mb-2">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                  {laser}
                </p>
                <div className="flex-1 h-px bg-slate-100" />
              </div>

              <Card padding={false}>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-100">
                      {['Name', 'Excitation (nm)', 'Emission (nm)', 'In use by', ''].map(h => (
                        <th key={h} className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {grouped[laser].map(f => {
                      // Count antibodies using this fluorochrome
                      return (
                        <FluorochromeRow
                          key={f.id}
                          fluorochrome={f}
                          onEdit={() => setEditing(f)}
                          onDelete={() => del.mutate(f.id)}
                        />
                      )
                    })}
                  </tbody>
                </table>
              </Card>
            </div>
          ))}
        </div>
      )}

      {/* Summary stat */}
      {fluors.length > 0 && (
        <p className="text-xs text-slate-400 text-right">
          {fluors.length} fluorochrome{fluors.length !== 1 ? 's' : ''} across {sortedGroups.filter(g => g !== 'No laser assigned' && grouped[g]).length} laser lines
        </p>
      )}

      <FluorochromeModal open={createOpen} onClose={() => setCreateOpen(false)} />
      {editing && (
        <FluorochromeModal
          open={!!editing}
          onClose={() => setEditing(null)}
          existing={editing}
        />
      )}
    </div>
  )
}

// ── Row component — separate so it can query antibody usage count ────────────

function FluorochromeRow({
  fluorochrome: f,
  onEdit,
  onDelete,
}: {
  fluorochrome: Fluorochrome
  onEdit: () => void
  onDelete: () => void
}) {
  const { data: antibodies = [] } = useQuery({
    queryKey: ['antibodies', false],
    queryFn: () => import('../../api/client').then(m => m.antibodiesApi.list(false)),
  })

  const inUseCount = antibodies.filter(ab => ab.fluorochrome_id === f.id).length

  return (
    <tr className="hover:bg-slate-50 transition-colors">
      <td className="px-4 py-3">
        <span className="font-medium text-slate-800">{f.name}</span>
      </td>
      <td className="px-4 py-3 tabular-nums text-slate-500">
        {f.excitation_nm ?? <span className="text-slate-300">—</span>}
      </td>
      <td className="px-4 py-3 tabular-nums text-slate-500">
        {f.emission_nm ?? <span className="text-slate-300">—</span>}
      </td>
      <td className="px-4 py-3">
        {inUseCount > 0 ? (
          <Badge variant="info">{inUseCount} antibod{inUseCount === 1 ? 'y' : 'ies'}</Badge>
        ) : (
          <span className="text-slate-300 text-xs">Not assigned</span>
        )}
      </td>
      <td className="px-4 py-3">
        <div className="flex gap-1.5">
          <Button variant="ghost" size="sm" onClick={onEdit}>
            <Pencil className="w-3.5 h-3.5" /> Edit
          </Button>
          {inUseCount === 0 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onDelete}
              className="text-red-400 hover:text-red-600 hover:bg-red-50"
            >
              Delete
            </Button>
          )}
        </div>
      </td>
    </tr>
  )
}
