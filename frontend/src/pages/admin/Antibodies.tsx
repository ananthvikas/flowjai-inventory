// pages/admin/Antibodies.tsx

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Pencil, Trash2, GitMerge, Download, ArrowUpDown, ArrowUp, ArrowDown, Beaker } from 'lucide-react'
import { useState, useEffect } from 'react'
import { antibodiesApi, exportApi, fluorochromesApi } from '../../api/client'
import { Badge, Button, Card, EmptyState, Input, Modal, Select, Spinner } from '../../components/ui'
import type { Antibody, AntibodyAlternative } from '../../types'
import VolumeCheckModal from '../../components/VolumeCheckModal'

const VIAL_HINT = 'Fill volume for this catalogue number. Receipts and vial openings use it automatically; a different volume then needs a reason.'

// ── Create Antibody Modal ──────────────────────────────────────────────────

function CreateAntibodyModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const { data: fluors = [] } = useQuery({ queryKey: ['fluorochromes'], queryFn: fluorochromesApi.list })
  const [form, setForm] = useState({ name: '', clone: '', vendor: '', catalog_no: '', vial_volume_ul: '', fluorochrome_id: '' })
  const [error, setError] = useState('')
  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  const mut = useMutation({
    mutationFn: () => antibodiesApi.create({
      name: form.name,
      clone: form.clone || undefined,
      vendor: form.vendor || undefined,
      catalog_no: form.catalog_no || undefined,
      vial_volume_ul: form.vial_volume_ul ? Number(form.vial_volume_ul) : undefined,
      fluorochrome_id: form.fluorochrome_id ? Number(form.fluorochrome_id) : undefined,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['antibodies'] })
      onClose()
      setForm({ name: '', clone: '', vendor: '', catalog_no: '', vial_volume_ul: '', fluorochrome_id: '' })
    },
    onError: (e: any) => setError(e.response?.data?.detail ?? 'Error creating antibody'),
  })

  return (
    <Modal open={open} onClose={onClose} title="New Antibody">
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <Input label="Name" value={form.name} onChange={e => set('name', e.target.value)} placeholder="CD3" />
          <Input label="Clone" value={form.clone} onChange={e => set('clone', e.target.value)} placeholder="UCHT1" />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Input label="Vendor" value={form.vendor} onChange={e => set('vendor', e.target.value)} placeholder="BD" />
          <Input label="Catalog No" value={form.catalog_no} onChange={e => set('catalog_no', e.target.value)} placeholder="555339" />
        </div>
        <div>
          <Input label="Vial volume (µl)" type="number" min="1" value={form.vial_volume_ul} onChange={e => set('vial_volume_ul', e.target.value)} placeholder="e.g. 100" />
          <p className="text-xs text-slate-500 mt-1">{VIAL_HINT}</p>
        </div>
        <Select label="Fluorochrome" value={form.fluorochrome_id} onChange={e => set('fluorochrome_id', e.target.value)}>
          <option value="">None / unlabelled</option>
          {fluors.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
        </Select>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={() => mut.mutate()} disabled={mut.isPending || !form.name}>
            {mut.isPending ? 'Saving…' : 'Create'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Alternatives Modal ────────────────────────────────────────────────────


function EditAntibodyModal({
  antibody, onClose, onSave, saving
}: {
  antibody: any | null; onClose: () => void
  onSave: (d: any) => void; saving: boolean
}) {
  const { data: fluors = [] } = useQuery({ queryKey: ['fluorochromes'], queryFn: fluorochromesApi.list })
  const [form, setForm] = useState({ name: '', clone: '', vendor: '', catalog_no: '', vial_volume_ul: '', fluorochrome_id: '' })
  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  // Populate form when antibody changes
  useEffect(() => {
    if (antibody) setForm({
      name: antibody.name ?? '',
      clone: antibody.clone ?? '',
      vendor: antibody.vendor ?? '',
      catalog_no: antibody.catalog_no ?? '',
      vial_volume_ul: antibody.vial_volume_ul != null ? String(antibody.vial_volume_ul) : '',
      fluorochrome_id: antibody.fluorochrome_id ? String(antibody.fluorochrome_id) : '',
    })
  }, [antibody?.id])

  return (
    <Modal open={!!antibody} onClose={onClose} title="Edit Antibody">
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <Input label="Name" value={form.name} onChange={e => set('name', e.target.value)} />
          <Input label="Clone" value={form.clone} onChange={e => set('clone', e.target.value)} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Input label="Vendor" value={form.vendor} onChange={e => set('vendor', e.target.value)} />
          <Input label="Catalog No" value={form.catalog_no} onChange={e => set('catalog_no', e.target.value)} />
        </div>
        <div>
          <Input label="Vial volume (µl)" type="number" min="1" value={form.vial_volume_ul} onChange={e => set('vial_volume_ul', e.target.value)} placeholder="not set" />
          <p className="text-xs text-slate-500 mt-1">{VIAL_HINT} Changing it does not alter lots already received — use Volume check for those.</p>
        </div>
        <Select label="Fluorochrome" value={form.fluorochrome_id} onChange={e => set('fluorochrome_id', e.target.value)}>
          <option value="">None / unlabelled</option>
          {fluors.map((f: any) => <option key={f.id} value={f.id}>{f.name}</option>)}
        </Select>
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={() => onSave({ id: antibody!.id, ...form })} disabled={saving || !form.name}>
            {saving ? 'Saving…' : 'Save changes'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function AlternativesModal({ antibody, onClose }: { antibody: Antibody | null; onClose: () => void }) {
  const qc = useQueryClient()
  const { data: allAbs = [] } = useQuery({ queryKey: ['antibodies'], queryFn: () => antibodiesApi.list() })
  const { data: alts = [], isLoading } = useQuery({
    queryKey: ['alternatives', antibody?.id],
    queryFn: () => antibodiesApi.listAlternatives(antibody!.id),
    enabled: !!antibody,
  })

  const [altId, setAltId] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState('')

  const existingAltIds = new Set(alts.map(a => a.alt_antibody_id))
  const available = allAbs.filter(a => a.id !== antibody?.id && !existingAltIds.has(a.id))

  const addAlt = useMutation({
    mutationFn: () => antibodiesApi.addAlternative(antibody!.id, Number(altId), note || undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['alternatives', antibody?.id] })
      setAltId('')
      setNote('')
    },
    onError: (e: any) => setError(e.response?.data?.detail ?? 'Error'),
  })

  const removeAlt = useMutation({
    mutationFn: (altObjId: number) => antibodiesApi.removeAlternative(antibody!.id, altObjId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alternatives', antibody?.id] }),
  })

  return (
    <Modal open={!!antibody} onClose={onClose} title={`Alternatives for ${antibody?.name}`}>
      <div className="space-y-4">
        {isLoading ? <Spinner /> : alts.length === 0 ? (
          <p className="text-sm text-slate-400 text-center py-3">No alternatives defined yet.</p>
        ) : (
          <div className="space-y-2">
            {alts.map((alt: AntibodyAlternative) => (
              <div key={alt.id} className="flex items-center justify-between gap-2 bg-slate-50 rounded-lg px-3 py-2">
                <div>
                  <span className="text-sm font-medium text-slate-800">{alt.alt_antibody_name}</span>
                  {alt.alt_fluorochrome && (
                    <span className="text-xs text-slate-400 ml-1.5">({alt.alt_fluorochrome})</span>
                  )}
                  {alt.note && <p className="text-xs text-slate-400 mt-0.5">{alt.note}</p>}
                </div>
                <button
                  onClick={() => removeAlt.mutate(alt.id)}
                  className="text-slate-300 hover:text-red-500 transition-colors shrink-0"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="border-t border-slate-100 pt-4 space-y-3">
          <p className="text-xs font-medium text-slate-600">Add alternative</p>
          <Select value={altId} onChange={e => setAltId(e.target.value)}>
            <option value="">Select substitute antibody…</option>
            {available.map(a => (
              <option key={a.id} value={a.id}>
                {a.name}{a.fluorochrome ? ` – ${a.fluorochrome.name}` : ''}
              </option>
            ))}
          </Select>
          <Input
            placeholder="Note (e.g. same clone, different fluor)"
            value={note}
            onChange={e => setNote(e.target.value)}
          />
          {error && <p className="text-xs text-red-600">{error}</p>}
          <Button
            size="sm"
            onClick={() => addAlt.mutate()}
            disabled={addAlt.isPending || !altId}
          >
            <Plus className="w-3 h-3" /> Add alternative
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────

export default function AntibodiesPage() {
  const qc = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [volumeCheckOpen, setVolumeCheckOpen] = useState(false)
  const [altFor, setAltFor] = useState<Antibody | null>(null)
  const [search, setSearch] = useState('')
  const [showInactive, setShowInactive] = useState(false)
  const [editTarget, setEditTarget] = useState<Antibody | null>(null)
  const [sortCol, setSortCol] = useState<string>('name')
  const [sortDir, setSortDir] = useState<'asc'|'desc'>('asc')

  const handleSort = (col: string) => {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortCol(col); setSortDir('asc') }
  }

  const { data: antibodies = [], isLoading } = useQuery({
    queryKey: ['antibodies', showInactive],
    queryFn: () => antibodiesApi.list(!showInactive),
  })

  const toggle = useMutation({
    mutationFn: (ab: Antibody) => antibodiesApi.update(ab.id, { active: !ab.active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['antibodies'] }),
  })

  const [deleteTarget, setDeleteTarget] = useState<Antibody | null>(null)
  const [deletePreview, setDeletePreview] = useState<{
    stock_lots: number; panel_assignments: number; consumption_logs: number;
    verification_logs: number; alternative_mappings: number; safe: boolean
  } | null>(null)
  const [deleteLoading, setDeleteLoading] = useState(false)

  const openDeleteDialog = async (ab: Antibody) => {
    setDeleteTarget(ab)
    setDeleteLoading(true)
    try {
      const preview = await antibodiesApi.deletePreview(ab.id)
      setDeletePreview(preview)
    } catch {
      setDeletePreview(null)
    } finally {
      setDeleteLoading(false)
    }
  }

  const closeDeleteDialog = () => { setDeleteTarget(null); setDeletePreview(null) }

  const editMut = useMutation({
    mutationFn: (d: any) => antibodiesApi.update(d.id, {
      name: d.name,
      clone: d.clone || undefined,
      vendor: d.vendor || undefined,
      catalog_no: d.catalog_no || undefined,
      vial_volume_ul: d.vial_volume_ul ? Number(d.vial_volume_ul) : null,   // empty clears it
      fluorochrome_id: d.fluorochrome_id ? parseInt(d.fluorochrome_id) : null,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['antibodies'] }); setEditTarget(null) },
    onError: (e: any) => alert(e.response?.data?.detail ?? 'Update failed'),
  })

  const confirmDelete = useMutation({
    mutationFn: ({ id, force }: { id: number; force: boolean }) =>
      antibodiesApi.remove(id, force),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['antibodies'] })
      closeDeleteDialog()
    },
    onError: (err: any) => {
      alert(err?.response?.data?.detail ?? 'Could not delete antibody')
    },
  })

  const sortedFiltered = [...antibodies]
    .filter(ab =>
    ab.name.toLowerCase().includes(search.toLowerCase()) ||
    (ab.clone ?? '').toLowerCase().includes(search.toLowerCase()) ||
    (ab.vendor ?? '').toLowerCase().includes(search.toLowerCase()) ||
    (ab.catalog_no ?? '').toLowerCase().includes(search.toLowerCase())
  )
  .sort((a, b) => {
    let av = '', bv = ''
    if (sortCol === 'name')        { av = a.name; bv = b.name }
    else if (sortCol === 'clone')  { av = a.clone ?? ''; bv = b.clone ?? '' }
    else if (sortCol === 'vendor') { av = a.vendor ?? ''; bv = b.vendor ?? '' }
    else if (sortCol === 'fluor')  { av = a.fluorochrome?.name ?? ''; bv = b.fluorochrome?.name ?? '' }
    else if (sortCol === 'status') { av = String(a.active); bv = String(b.active) }
    return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av)
  })

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Antibodies</h1>
          <p className="text-sm text-slate-500 mt-0.5">Master antibody list with fluorochrome assignments</p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={() => setShowInactive(v => !v)}>
            {showInactive ? 'Hide inactive' : 'Show inactive'}
          </Button>
          <Button variant="secondary" size="sm" onClick={() => setVolumeCheckOpen(true)} title="Lots whose starting volume differs from the standard vial volume">
            <Beaker className="w-3.5 h-3.5" /> Volume check
          </Button>
          <Button variant="secondary" size="sm" onClick={() => exportApi.antibodies()}>
            <Download className="w-3.5 h-3.5" /> Export CSV
          </Button>
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="w-4 h-4" /> New antibody
          </Button>
        </div>
      </div>

      <Input
        placeholder="Search name, clone, vendor, catalogue no…"
        value={search}
        onChange={e => setSearch(e.target.value)}
        className="max-w-sm"
      />

      <Card padding={false}>
        {isLoading ? (
          <Spinner className="py-16" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-100">
                  {([
                    ['Name', 'name'], ['Clone', 'clone'], ['Vendor', 'vendor'],
                    ['Catalog No', ''], ['Vial µl', ''], ['Fluorochrome', 'fluor'], ['Status', 'status'], ['', '']
                  ] as [string, string][]).map(([label, col]) => (
                    <th
                      key={label}
                      onClick={() => col && handleSort(col)}
                      className={`text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide ${col ? 'cursor-pointer select-none hover:text-slate-700' : ''}`}
                    >
                      <span className="inline-flex items-center gap-1">
                        {label}
                        {col && (sortCol === col
                          ? (sortDir === 'asc' ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />)
                          : <ArrowUpDown className="w-3 h-3 opacity-30" />)}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {sortedFiltered.length === 0 && (
                  <tr><td colSpan={8}><EmptyState message="No antibodies found" /></td></tr>
                )}
                {sortedFiltered.map(ab => (
                  <tr key={ab.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-4 py-3 font-medium text-slate-800">{ab.name}</td>
                    <td className="px-4 py-3 text-slate-500 font-mono text-xs">{ab.clone ?? '—'}</td>
                    <td className="px-4 py-3 text-slate-500">{ab.vendor ?? '—'}</td>
                    <td className="px-4 py-3 text-slate-400 text-xs font-mono">{ab.catalog_no ?? '—'}</td>
                    <td className="px-4 py-3 text-xs tabular-nums">
                      {ab.vial_volume_ul != null
                        ? <span className="text-slate-700">{ab.vial_volume_ul}</span>
                        : <span className="text-amber-600" title="No standard vial volume — receipts accept any typed volume">not set</span>}
                    </td>
                    <td className="px-4 py-3">
                      {ab.fluorochrome ? (
                        <Badge variant="info">{ab.fluorochrome.name}</Badge>
                      ) : <span className="text-slate-300">—</span>}
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant={ab.active ? 'ok' : 'unknown'}>
                        {ab.active ? 'Active' : 'Inactive'}
                      </Badge>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-1.5">
                        <Button
                          variant="ghost" size="sm"
                          onClick={() => setAltFor(ab)}
                          title="Manage alternatives"
                        >
                          <GitMerge className="w-3.5 h-3.5" />
                          Alts
                        </Button>
                        <Button
                          variant="ghost" size="sm"
                          onClick={() => toggle.mutate(ab)}
                        >
                          {ab.active ? 'Deactivate' : 'Activate'}
                        </Button>
                        <Button
                          variant="ghost" size="sm"
                          onClick={() => setEditTarget(ab)}
                          title="Edit antibody"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </Button>
                        <Button
                          variant="ghost" size="sm"
                          onClick={() => openDeleteDialog(ab)}
                          title="Delete antibody"
                          className="text-red-500 hover:text-red-700"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <CreateAntibodyModal open={createOpen} onClose={() => setCreateOpen(false)} />
      <VolumeCheckModal open={volumeCheckOpen} onClose={() => setVolumeCheckOpen(false)} />
      <AlternativesModal antibody={altFor} onClose={() => setAltFor(null)} />
      <EditAntibodyModal
        antibody={editTarget}
        onClose={() => setEditTarget(null)}
        onSave={(d: any) => editMut.mutate(d)}
        saving={editMut.isPending}
      />

      <Modal open={!!deleteTarget} onClose={closeDeleteDialog} title="Delete Antibody">
        {deleteLoading && <Spinner className="py-8" />}
        {!deleteLoading && deleteTarget && deletePreview && (
          <div className="space-y-4">
            <p className="text-slate-700">
              Delete <span className="font-semibold">{deleteTarget.name}</span>
              {deleteTarget.fluorochrome ? ` (${deleteTarget.fluorochrome.name})` : ''}?
            </p>
            {deletePreview.safe ? (
              <p className="text-sm text-green-700 bg-green-50 rounded p-3">
                No dependent records — safe to delete.
              </p>
            ) : (
              <div className="text-sm bg-amber-50 border border-amber-200 rounded p-3 space-y-1">
                <p className="font-semibold text-amber-800">This will also permanently delete:</p>
                {deletePreview.stock_lots > 0 && <p className="text-amber-700">• {deletePreview.stock_lots} stock lot(s)</p>}
                {deletePreview.panel_assignments > 0 && <p className="text-amber-700">• {deletePreview.panel_assignments} panel assignment(s)</p>}
                {deletePreview.consumption_logs > 0 && <p className="text-amber-700">• {deletePreview.consumption_logs} consumption log(s)</p>}
                {deletePreview.verification_logs > 0 && <p className="text-amber-700">• {deletePreview.verification_logs} verification record(s)</p>}
                {deletePreview.alternative_mappings > 0 && <p className="text-amber-700">• {deletePreview.alternative_mappings} alternative mapping(s)</p>}
              </div>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="secondary" onClick={closeDeleteDialog}>Cancel</Button>
              <Button
                variant="danger"
                onClick={() => confirmDelete.mutate({ id: deleteTarget.id, force: !deletePreview.safe })}
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
