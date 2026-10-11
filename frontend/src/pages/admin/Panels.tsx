// pages/admin/Panels.tsx

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, Pencil, Check, X, Plus, Trash2, Download } from 'lucide-react'
import { useState } from 'react'
import { antibodiesApi, exportApi, panelsApi } from '../../api/client'
import { Button, Card, EmptyState, Input, Modal, Select, Spinner } from '../../components/ui'
import type { Panel } from '../../types'

function CreatePanelModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ name: '', test_code: '', test_group: '', department: '' })
  const [error, setError] = useState('')
  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }))

  const mut = useMutation({
    mutationFn: () => panelsApi.create({ name: form.name, test_code: form.test_code.toUpperCase(), test_group: form.test_group.toUpperCase() || undefined, department: form.department || undefined }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['panels'] }); onClose(); setForm({ name: '', test_code: '', test_group: '', department: '' }) },
    onError: (e: any) => setError(e.response?.data?.detail ?? 'Error'),
  })

  return (
    <Modal open={open} onClose={onClose} title="New Panel">
      <div className="space-y-4">
        <Input label="Panel name" value={form.name} onChange={(e) => set('name', e.target.value)} placeholder="B-ALL MRD 12-colour" />
        <Input label="Tube / panel code" value={form.test_code} onChange={(e) => set('test_code', e.target.value)} placeholder="CL1" />
        <Input label="Protocol / test group (optional)" value={form.test_group} onChange={(e) => set('test_group', e.target.value)} placeholder="cLPD" />
        <Input label="Department (optional)" value={form.department} onChange={(e) => set('department', e.target.value)} />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={() => mut.mutate()} disabled={mut.isPending || !form.name || !form.test_code}>
            {mut.isPending ? 'Saving…' : 'Create panel'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function AddComponentModal({ panel, onClose }: { panel: Panel | null; onClose: () => void }) {
  const qc = useQueryClient()
  const { data: antibodies = [] } = useQuery({ queryKey: ['antibodies'], queryFn: () => antibodiesApi.list() })
  const [form, setForm] = useState({ antibody_id: '', volume_per_tube_ul: '5', tubes_per_test: '1' })
  const [error, setError] = useState('')
  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }))

  const existingIds = new Set(panel?.components.map((c) => c.antibody_id) ?? [])
  const available = antibodies.filter((a) => !existingIds.has(a.id))

  const mut = useMutation({
    mutationFn: () => panelsApi.addComponent(panel!.id, {
      antibody_id: Number(form.antibody_id),
      volume_per_tube_ul: Number(form.volume_per_tube_ul),
      tubes_per_test: Number(form.tubes_per_test),
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['panels'] }); onClose() },
    onError: (e: any) => setError(e.response?.data?.detail ?? 'Error'),
  })

  const [abSearch, setAbSearch] = useState('')
  const filtered = available.filter(ab =>
    ab.name.toLowerCase().includes(abSearch.toLowerCase()) ||
    (ab.fluorochrome?.name ?? '').toLowerCase().includes(abSearch.toLowerCase()) ||
    (ab.clone ?? '').toLowerCase().includes(abSearch.toLowerCase())
  )
  const selectedAb = available.find(ab => ab.id === Number(form.antibody_id))

  return (
    <Modal open={!!panel} onClose={onClose} title={`Add antibody to ${panel?.name}`}>
      <div className="space-y-4">
        <div>
          <label className="text-xs font-medium text-slate-600 block mb-1">Antibody</label>
          {selectedAb ? (
            <div className="flex items-center justify-between bg-blue-50 border border-blue-200 rounded-lg px-3 py-2">
              <span className="text-sm font-medium text-slate-800">
                {selectedAb.name}
                {selectedAb.fluorochrome && <span className="text-slate-400 ml-1.5">· {selectedAb.fluorochrome.name}</span>}
              </span>
              <button onClick={() => { set('antibody_id', ''); setAbSearch('') }} className="text-xs text-slate-400 hover:text-red-500">✕ Clear</button>
            </div>
          ) : (
            <div className="space-y-1">
              <input
                type="text"
                value={abSearch}
                onChange={e => setAbSearch(e.target.value)}
                placeholder="Search by name, fluorochrome or clone…"
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                autoFocus
              />
              {abSearch.length > 0 && (
                <div className="border border-slate-200 rounded-lg overflow-hidden max-h-48 overflow-y-auto shadow-sm">
                  {filtered.length === 0 ? (
                    <p className="px-3 py-2 text-sm text-slate-400">No matches</p>
                  ) : (
                    filtered.map(ab => (
                      <button
                        key={ab.id}
                        onClick={() => { set('antibody_id', String(ab.id)); setAbSearch('') }}
                        className="w-full text-left px-3 py-2 text-sm hover:bg-blue-50 flex items-center justify-between border-b border-slate-100 last:border-0"
                      >
                        <span className="font-medium text-slate-800">{ab.name}</span>
                        <span className="text-xs text-slate-400">
                          {ab.fluorochrome?.name ?? ''}{ab.clone ? ` · ${ab.clone}` : ''}
                        </span>
                      </button>
                    ))
                  )}
                </div>
              )}
              {abSearch.length === 0 && (
                <p className="text-xs text-slate-400 px-1">Start typing to search {available.length} available antibodies</p>
              )}
            </div>
          )}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Input label="µl per tube" type="number" step="0.5" value={form.volume_per_tube_ul} onChange={(e) => set('volume_per_tube_ul', e.target.value)} />
          <Input label="Tubes per test" type="number" min="1" value={form.tubes_per_test} onChange={(e) => set('tubes_per_test', e.target.value)} />
        </div>
        <p className="text-xs text-slate-400">
          Total per test: {(Number(form.volume_per_tube_ul) * Number(form.tubes_per_test)).toFixed(1)} µl
        </p>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={() => mut.mutate()} disabled={mut.isPending || !form.antibody_id}>
            {mut.isPending ? 'Adding…' : 'Add'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function PanelRow({ panel }: { panel: Panel }) {
  const qc = useQueryClient()
  const [expanded, setExpanded] = useState(false)
  const [addComp, setAddComp] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deletePreview, setDeletePreview] = useState<{
    components: number; test_logs: number; safe: boolean
  } | null>(null)
  const [deleteLoading, setDeleteLoading] = useState(false)

  const removeComp = useMutation({
    mutationFn: (compId: number) => panelsApi.removeComponent(panel.id, compId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['panels'] }),
  })

  const [editingCompId, setEditingCompId] = useState<number | null>(null)
  const [editVol, setEditVol] = useState('')
  const [editTubes, setEditTubes] = useState('')

  const startEdit = (c: { id: number; volume_per_tube_ul: number; tubes_per_test: number }) => {
    setEditingCompId(c.id)
    setEditVol(String(c.volume_per_tube_ul))
    setEditTubes(String(c.tubes_per_test))
  }

  const updateComp = useMutation({
    mutationFn: ({ compId, vol, tubes }: { compId: number; vol: number; tubes: number }) =>
      panelsApi.updateComponent(panel.id, compId, { volume_per_tube_ul: vol, tubes_per_test: tubes }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['panels'] })
      setEditingCompId(null)
    },
  })

  const toggleActive = useMutation({
    mutationFn: () => panelsApi.update(panel.id, { active: !panel.active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['panels'] }),
  })

  const openDeleteDialog = async () => {
    setDeleteOpen(true)
    setDeleteLoading(true)
    try {
      const preview = await panelsApi.deletePreview(panel.id)
      setDeletePreview(preview)
    } catch {
      setDeletePreview(null)
    } finally {
      setDeleteLoading(false)
    }
  }

  const confirmDelete = useMutation({
    mutationFn: (force: boolean) => panelsApi.remove(panel.id, force),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['panels'] })
      setDeleteOpen(false)
    },
    onError: (err: any) => alert(err?.response?.data?.detail ?? 'Could not delete panel'),
  })

  const Icon = expanded ? ChevronDown : ChevronRight

  return (
    <div className="border border-slate-200 rounded-xl overflow-hidden">
      <div
        className="flex items-center gap-3 px-4 py-3 bg-white cursor-pointer hover:bg-slate-50 transition-colors"
        onClick={() => setExpanded((e) => !e)}
      >
        <Icon className="w-4 h-4 text-slate-400 shrink-0" />
        <div className="flex-1">
          <span className="font-medium text-slate-900 text-sm">{panel.name}</span>
          <span className="text-xs text-slate-400 ml-2">({panel.test_code})</span>
          {panel.department && <span className="text-xs text-slate-400 ml-2">· {panel.department}</span>}
        </div>
        <span className="text-xs text-slate-400">{panel.components.length} antibodies</span>
        {!panel.active && <span className="text-xs text-amber-500 font-medium">Inactive</span>}
        <div className="flex gap-1.5" onClick={(e) => e.stopPropagation()}>
          <Button variant="secondary" size="sm" onClick={() => setAddComp(true)}>
            <Plus className="w-3 h-3" /> Add
          </Button>
          <Button variant="ghost" size="sm" onClick={() => toggleActive.mutate()}>
            {panel.active ? 'Deactivate' : 'Activate'}
          </Button>
          <Button variant="ghost" size="sm" onClick={openDeleteDialog} className="text-red-500 hover:text-red-700" title="Delete panel">
            <Trash2 className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-slate-100 bg-slate-50 px-4 py-3">
          {panel.components.length === 0 ? (
            <EmptyState message="No antibodies in this panel yet" />
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr>
                  {['Antibody', 'Fluorochrome', 'µl/tube', 'Tubes', 'µl/test', ''].map((h) => (
                    <th key={h} className="text-left pb-2 text-slate-400 font-medium pr-4">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {panel.components.map((c) => {
                  const isEditing = editingCompId === c.id
                  const editedUlPerTest = isEditing
                    ? (parseFloat(editVol) || 0) * (parseFloat(editTubes) || 0)
                    : null
                  return (
                  <tr key={c.id} className={isEditing ? 'bg-blue-50' : ''}>
                    <td className="py-1.5 font-medium text-slate-700 pr-4">{c.antibody_name}</td>
                    <td className="py-1.5 text-slate-500 pr-4">{c.fluorochrome ?? '—'}</td>
                    <td className="py-1.5 pr-4">
                      {isEditing ? (
                        <input
                          type="number" min="0" step="0.1"
                          value={editVol}
                          onChange={e => setEditVol(e.target.value)}
                          className="w-16 border border-blue-300 rounded px-1 py-0.5 text-xs tabular-nums focus:outline-none focus:ring-1 focus:ring-blue-400"
                          autoFocus
                        />
                      ) : (
                        <span className="text-slate-600 tabular-nums">{c.volume_per_tube_ul}</span>
                      )}
                    </td>
                    <td className="py-1.5 pr-4">
                      {isEditing ? (
                        <input
                          type="number" min="1" step="1"
                          value={editTubes}
                          onChange={e => setEditTubes(e.target.value)}
                          className="w-14 border border-blue-300 rounded px-1 py-0.5 text-xs tabular-nums focus:outline-none focus:ring-1 focus:ring-blue-400"
                        />
                      ) : (
                        <span className="text-slate-600 tabular-nums">{c.tubes_per_test}</span>
                      )}
                    </td>
                    <td className="py-1.5 font-medium text-slate-700 tabular-nums pr-4">
                      {isEditing
                        ? <span className="text-blue-600">{editedUlPerTest?.toFixed(1) ?? '—'}</span>
                        : c.ul_per_test.toFixed(1)}
                    </td>
                    <td className="py-1.5">
                      <div className="flex gap-1 items-center">
                        {isEditing ? (
                          <>
                            <button
                              onClick={() => updateComp.mutate({
                                compId: c.id,
                                vol: parseFloat(editVol),
                                tubes: parseInt(editTubes),
                              })}
                              disabled={updateComp.isPending || !editVol || !editTubes}
                              className="text-green-500 hover:text-green-700 disabled:opacity-40 transition-colors"
                              title="Save"
                            >
                              <Check className="w-3.5 h-3.5" />
                            </button>
                            <button
                              onClick={() => setEditingCompId(null)}
                              className="text-slate-400 hover:text-slate-600 transition-colors"
                              title="Cancel"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          </>
                        ) : (
                          <button
                            onClick={() => startEdit(c)}
                            className="text-slate-300 hover:text-blue-500 transition-colors"
                            title="Edit volumes"
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                        )}
                        <button
                          onClick={() => removeComp.mutate(c.id)}
                          className="text-slate-300 hover:text-red-500 transition-colors"
                          title="Remove"
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
          )}
        </div>
      )}

      <AddComponentModal panel={addComp ? panel : null} onClose={() => setAddComp(false)} />

      <Modal open={deleteOpen} onClose={() => setDeleteOpen(false)} title="Delete Panel">
        {deleteLoading && <Spinner className="py-8" />}
        {!deleteLoading && deletePreview && (
          <div className="space-y-4">
            <p className="text-slate-700">Delete panel <span className="font-semibold">{panel.name}</span>?</p>
            {deletePreview.safe ? (
              <p className="text-sm text-green-700 bg-green-50 rounded p-3">No test history — safe to delete.</p>
            ) : (
              <div className="text-sm bg-amber-50 border border-amber-200 rounded p-3 space-y-1">
                <p className="font-semibold text-amber-800">This will also permanently delete:</p>
                {deletePreview.components > 0 && <p className="text-amber-700">• {deletePreview.components} antibody component(s)</p>}
                {deletePreview.test_logs > 0 && <p className="text-amber-700">• {deletePreview.test_logs} test log record(s) and their consumption logs</p>}
              </div>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="secondary" onClick={() => setDeleteOpen(false)}>Cancel</Button>
              <Button
                variant="danger"
                onClick={() => confirmDelete.mutate(!deletePreview.safe)}
                disabled={confirmDelete.isPending}
              >
                {deletePreview.safe ? 'Delete' : 'Force Delete'}
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}

export default function PanelsPage() {
  const [createOpen, setCreateOpen] = useState(false)
  const [showInactive, setShowInactive] = useState(false)

  const { data: panels = [], isLoading } = useQuery({
    queryKey: ['panels', showInactive],
    queryFn: () => panelsApi.list(!showInactive),
  })

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Panels</h1>
          <p className="text-sm text-slate-500 mt-0.5">Manage antibody panels and per-tube volumes</p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={() => setShowInactive((v) => !v)}>
            {showInactive ? 'Hide inactive' : 'Show inactive'}
          </Button>
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="w-4 h-4" /> New panel
          </Button>
        </div>
      </div>

      {isLoading ? (
        <Spinner className="py-16" />
      ) : panels.length === 0 ? (
        <Card><EmptyState message="No panels yet" /></Card>
      ) : (
        <div className="space-y-2">
          {panels.map((p) => <PanelRow key={p.id} panel={p} />)}
        </div>
      )}

      <CreatePanelModal open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  )
}
