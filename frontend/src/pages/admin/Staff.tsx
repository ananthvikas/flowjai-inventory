// pages/admin/Staff.tsx — master list of pathologists and technologists

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus, Stethoscope, FlaskConical } from 'lucide-react'
import { useState } from 'react'
import { staffApi } from '../../api/client'
import { Badge, Button, Card, EmptyState, Input, Modal, Select, Spinner } from '../../components/ui'
import type { Staff } from '../../types'

// ── Add / edit modal ─────────────────────────────────────────────────────────

function StaffModal({
  open,
  onClose,
  existing,
  defaultRole,
}: {
  open: boolean
  onClose: () => void
  existing?: Staff
  defaultRole?: 'pathologist' | 'technologist'
}) {
  const qc = useQueryClient()
  const isEdit = !!existing

  const [form, setForm] = useState({
    name: existing?.name ?? '',
    role: existing?.role ?? defaultRole ?? 'technologist',
    initials: existing?.initials ?? '',
  })
  const [error, setError] = useState('')
  const set = (k: string, v: string) => { setForm((f) => ({ ...f, [k]: v })); setError('') }

  const mut = useMutation({
    mutationFn: () => {
      const payload = { name: form.name.trim(), role: form.role, initials: form.initials.trim() || undefined }
      return isEdit ? staffApi.update(existing!.id, payload) : staffApi.create(payload)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['staff'] })
      onClose()
    },
    onError: (e: any) => setError(e.response?.data?.detail ?? 'Could not save'),
  })

  return (
    <Modal open={open} onClose={onClose} title={isEdit ? `Edit — ${existing!.name}` : 'Add staff member'}>
      <div className="space-y-4">
        <Input label="Full name" value={form.name} onChange={(e) => set('name', e.target.value)} placeholder="e.g. Dr A. Sharma" autoFocus />
        <div className="grid grid-cols-2 gap-3">
          <Select label="Role" value={form.role} onChange={(e) => set('role', e.target.value)}>
            <option value="pathologist">Pathologist</option>
            <option value="technologist">Technologist</option>
          </Select>
          <Input label="Initials (optional)" value={form.initials} onChange={(e) => set('initials', e.target.value)} placeholder="AS" maxLength={16} />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={() => mut.mutate()} disabled={mut.isPending || !form.name.trim()}>
            {mut.isPending ? 'Saving…' : isEdit ? 'Save changes' : 'Add'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Role group table ─────────────────────────────────────────────────────────

function RoleGroup({
  title,
  icon,
  members,
  onEdit,
  onToggle,
}: {
  title: string
  icon: React.ReactNode
  members: Staff[]
  onEdit: (s: Staff) => void
  onToggle: (s: Staff) => void
}) {
  return (
    <div>
      <div className="flex items-center gap-3 mb-2">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
          {icon} {title}
        </p>
        <div className="flex-1 h-px bg-slate-100" />
        <span className="text-xs text-slate-400">{members.length}</span>
      </div>
      <Card padding={false}>
        {members.length === 0 ? (
          <div className="px-4 py-6 text-sm text-slate-400 text-center">None yet</div>
        ) : (
          <table className="w-full text-sm">
            <tbody className="divide-y divide-slate-100">
              {members.map((s) => (
                <tr key={s.id} className={`hover:bg-slate-50 transition-colors ${s.active ? '' : 'opacity-50'}`}>
                  <td className="px-4 py-3">
                    <span className="font-medium text-slate-800">{s.name}</span>
                    {s.initials && <span className="ml-2 text-xs text-slate-400">({s.initials})</span>}
                    {!s.active && <Badge variant="unknown" className="ml-2">inactive</Badge>}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex justify-end gap-1.5">
                      <Button variant="ghost" size="sm" onClick={() => onEdit(s)}>
                        <Pencil className="w-3.5 h-3.5" /> Edit
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onToggle(s)}
                        className={s.active ? 'text-red-400 hover:text-red-600 hover:bg-red-50' : 'text-emerald-500 hover:text-emerald-700 hover:bg-emerald-50'}
                      >
                        {s.active ? 'Deactivate' : 'Reactivate'}
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function StaffPage() {
  const qc = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [editing, setEditing] = useState<Staff | null>(null)

  const { data: staff = [], isLoading } = useQuery({
    queryKey: ['staff', 'all'],
    queryFn: () => staffApi.list(undefined, false),
  })

  const toggle = useMutation({
    mutationFn: (s: Staff) => staffApi.update(s.id, { active: !s.active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['staff'] }),
    onError: (e: any) => alert(e.response?.data?.detail ?? 'Could not update'),
  })

  const pathologists = staff.filter((s) => s.role === 'pathologist')
  const technologists = staff.filter((s) => s.role === 'technologist')

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Staff</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Pathologists and technologists selectable on the worklist. Separate from login accounts.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="w-4 h-4" /> Add staff member
        </Button>
      </div>

      {isLoading ? (
        <Spinner className="py-16" />
      ) : staff.length === 0 ? (
        <Card><EmptyState message="No staff yet — add pathologists and technologists to populate the worklist dropdowns." /></Card>
      ) : (
        <div className="space-y-5">
          <RoleGroup
            title="Pathologists"
            icon={<Stethoscope className="w-3.5 h-3.5" />}
            members={pathologists}
            onEdit={setEditing}
            onToggle={(s) => toggle.mutate(s)}
          />
          <RoleGroup
            title="Technologists"
            icon={<FlaskConical className="w-3.5 h-3.5" />}
            members={technologists}
            onEdit={setEditing}
            onToggle={(s) => toggle.mutate(s)}
          />
        </div>
      )}

      <StaffModal open={createOpen} onClose={() => setCreateOpen(false)} />
      {editing && <StaffModal open={!!editing} onClose={() => setEditing(null)} existing={editing} />}
    </div>
  )
}
