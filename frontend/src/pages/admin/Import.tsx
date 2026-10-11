// pages/admin/Import.tsx

import { useMutation } from '@tanstack/react-query'
import { CheckCircle, Upload, XCircle, AlertTriangle, FileSpreadsheet, Download } from 'lucide-react'
import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import { Badge, Button, Card, EmptyState, Spinner } from '../../components/ui'

// ── Types ─────────────────────────────────────────────────────────────────

interface SAPRow {
  row_index: number
  material_no: string
  short_text: string
  catalog_no: string | null
  manufacturer: string | null
  alternative_uom: string | null
  kit_size: number | null
  antibody_name: string | null
  fluorochrome_name: string | null
  vendor: string | null
  volume_ul: number | null
  status: 'new' | 'exists' | 'skip' | 'unrecognised'
  skip_reason: string | null
  existing_antibody_id: number | null
  // user overrides
  override_name?: string
  override_fluorochrome?: string
}

interface CommitResult {
  fluorochromes_created: number
  antibodies_created: number
  antibodies_skipped_existing: number
  vial_volumes_set?: number
  errors: string[]
}

// ── Status badge helper ────────────────────────────────────────────────────

function StatusBadge({ status }: { status: SAPRow['status'] }) {
  const map = {
    new:          { label: 'Will import', variant: 'ok' as const,      icon: '✓' },
    exists:       { label: 'Already exists', variant: 'info' as const,   icon: '=' },
    skip:         { label: 'Skipped',      variant: 'unknown' as const, icon: '—' },
    unrecognised: { label: 'Unrecognised', variant: 'warning' as const, icon: '?' },
  }
  const m = map[status]
  return <Badge variant={m.variant}>{m.icon} {m.label}</Badge>
}

// ── Editable cell ─────────────────────────────────────────────────────────

function EditableCell({
  value,
  onChange,
  placeholder,
}: {
  value: string
  onChange: (v: string) => void
  placeholder?: string
}) {
  return (
    <input
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full px-1.5 py-1 text-xs border border-slate-200 rounded focus:outline-none focus:ring-1 focus:ring-brand-500"
    />
  )
}

// ── Main page ─────────────────────────────────────────────────────────────

// ── Import template ───────────────────────────────────────────────────────
// Same content as templates/antibody-import-template.csv in the repository.
const TEMPLATE_CSV =
  'Antibody Name,Fluorochrome Name,Catalogue No,Manufacturer,Vial Volume uL,Description\r\n' +
  'CD3,FITC,EXAMPLE-001,BD,500,Example row - replace or delete\r\n' +
  'CD19,PE,EXAMPLE-002,BioLegend,500,Example row - replace or delete\r\n' +
  'CD45,V500,EXAMPLE-003,BD,250,Example row - replace or delete\r\n'

function downloadTemplate() {
  const url = URL.createObjectURL(new Blob([TEMPLATE_CSV], { type: 'text/csv' }))
  const a = document.createElement('a')
  a.href = url
  a.download = 'antibody-import-template.csv'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export default function ImportPage() {
  const navigate = useNavigate()
  const fileRef = useRef<HTMLInputElement>(null)
  const [rows, setRows] = useState<SAPRow[] | null>(null)
  const [result, setResult] = useState<CommitResult | null>(null)
  const [step, setStep] = useState<'upload' | 'preview' | 'done'>('upload')

  // ── Preview mutation ──────────────────────────────────────────────────

  const previewMut = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData()
      form.append('file', file)
      const res = await api.post<SAPRow[]>('/import/sap/preview', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      return res.data
    },
    onSuccess: data => {
      setRows(data)
      setStep('preview')
    },
  })

  // ── Commit mutation ───────────────────────────────────────────────────

  const commitMut = useMutation({
    mutationFn: async (toImport: SAPRow[]) => {
      const payload = toImport.map(r => ({
        row_index: r.row_index,
        antibody_name: r.override_name || r.antibody_name || '',
        fluorochrome_name: r.override_fluorochrome ?? r.fluorochrome_name ?? null,
        catalog_no: r.catalog_no,
        vendor: r.vendor,
        volume_ul: r.volume_ul,
        material_no: r.material_no,
      }))
      const res = await api.post<CommitResult>('/import/sap/commit', payload)
      return res.data
    },
    onSuccess: data => {
      setResult(data)
      setStep('done')
    },
  })

  // ── Row editing ───────────────────────────────────────────────────────

  const updateRow = (idx: number, field: 'override_name' | 'override_fluorochrome', val: string) => {
    setRows(prev => prev!.map((r, i) =>
      i === idx ? { ...r, [field]: val } : r
    ))
  }

  const toImport = rows?.filter(r => r.status === 'new' || r.status === 'unrecognised') ?? []
  const toImportReady = toImport.filter(r => (r.override_name || r.antibody_name))

  // ── Summary counts ────────────────────────────────────────────────────

  const counts = rows ? {
    new:          rows.filter(r => r.status === 'new').length,
    exists:       rows.filter(r => r.status === 'exists').length,
    skip:         rows.filter(r => r.status === 'skip').length,
    unrecognised: rows.filter(r => r.status === 'unrecognised').length,
  } : null

  // ── Render ────────────────────────────────────────────────────────────

  return (
    <div className="p-6 space-y-5 max-w-6xl">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Antibody import</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Import your antibody master list from a CSV or Excel (.xlsx) file: the flowjAI template, or a SAP materials export
        </p>
      </div>

      {/* ── Step 1: Upload ── */}
      {step === 'upload' && (
        <div className="space-y-4">
          <Card>
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-sm font-semibold text-slate-900 mb-1">Option 1 — flowjAI template</h2>
                <p className="text-xs text-slate-500">
                  Fill in one row per antibody. <span className="font-medium">Vial Volume uL</span> is the standard
                  fill volume of one vial; it becomes the antibody&apos;s vial volume, used automatically when stock is received.
                  Description is optional.
                </p>
              </div>
              <Button variant="secondary" size="sm" className="shrink-0" onClick={downloadTemplate}>
                <Download className="w-4 h-4" /> Download template
              </Button>
            </div>
            <div className="overflow-x-auto rounded-lg border border-slate-100 mt-3">
              <table className="text-xs w-full">
                <thead>
                  <tr className="bg-slate-50">
                    {['Antibody Name', 'Fluorochrome Name', 'Catalogue No', 'Manufacturer', 'Vial Volume uL', 'Description'].map(h => (
                      <th key={h} className="text-left px-3 py-2 font-semibold text-slate-500">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-t border-slate-100">
                    <td className="px-3 py-2">CD3</td>
                    <td className="px-3 py-2">FITC</td>
                    <td className="px-3 py-2">EXAMPLE-001</td>
                    <td className="px-3 py-2">BD</td>
                    <td className="px-3 py-2">500</td>
                    <td className="px-3 py-2 text-slate-400">optional</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </Card>

          <Card>
            <h2 className="text-sm font-semibold text-slate-900 mb-1">Option 2 — SAP materials export</h2>
            <p className="text-xs text-slate-500 mb-3">
              Export your SAP materials list as .xlsx or CSV. Antibody and fluorochrome are read from the Short Text.
              The importer recognises these columns:
            </p>
            <div className="overflow-x-auto rounded-lg border border-slate-100">
              <table className="text-xs w-full">
                <thead>
                  <tr className="bg-slate-50">
                    {['Material', 'Short Text', 'Catalogue No', 'Manufacturer', 'UOM', 'Alternative UOM', 'Kit Size'].map(h => (
                      <th key={h} className="text-left px-3 py-2 font-semibold text-slate-500">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-t border-slate-100">
                    <td className="px-3 py-2 font-mono text-slate-500">MAT-000101</td>
                    <td className="px-3 py-2 text-slate-700">ANTI HU CD123 R718 9F5 50T</td>
                    <td className="px-3 py-2">EXAMPLE-101</td>
                    <td className="px-3 py-2">BD</td>
                    <td className="px-3 py-2">KIT</td>
                    <td className="px-3 py-2">MICRO</td>
                    <td className="px-3 py-2">250</td>
                  </tr>
                  <tr className="border-t border-slate-100 bg-slate-50/50">
                    <td className="px-3 py-2 font-mono text-slate-500">MAT-000102</td>
                    <td className="px-3 py-2 text-slate-700">CD7 PE-CY7 BD</td>
                    <td className="px-3 py-2">EXAMPLE-102</td>
                    <td className="px-3 py-2">BD</td>
                    <td className="px-3 py-2">KIT</td>
                    <td className="px-3 py-2">MICRO</td>
                    <td className="px-3 py-2">500</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="text-xs text-slate-400 mt-2">
              Kit Size with Alternative UOM = MICRO is read as the vial volume in µl. Rows with Alternative UOM = LITRE
              (sheath fluid, shutdown solution) are skipped automatically. Column names are matched case-insensitively.
            </p>
          </Card>

          <Card>
            <h2 className="text-sm font-semibold text-slate-900 mb-3">Upload file</h2>
            <div
              className="border-2 border-dashed border-slate-200 rounded-xl p-10 text-center
                hover:border-brand-400 hover:bg-blue-50/40 transition-colors cursor-pointer"
              onClick={() => fileRef.current?.click()}
            >
              <FileSpreadsheet className="w-10 h-10 mx-auto text-slate-300 mb-3" />
              <p className="text-sm font-medium text-slate-600">Click to upload Excel or CSV</p>
              <p className="text-xs text-slate-400 mt-1">Supports .xlsx and .csv (save older .xls files as .xlsx first)</p>
              <input
                ref={fileRef}
                type="file"
                accept=".xlsx,.csv"
                className="hidden"
                onChange={e => {
                  const f = e.target.files?.[0]
                  if (f) previewMut.mutate(f)
                  e.target.value = ''
                }}
              />
            </div>
            {previewMut.isPending && (
              <div className="mt-4 flex items-center gap-2 text-sm text-slate-500">
                <Spinner className="h-5" />
                Parsing file and checking against existing antibody master...
              </div>
            )}
            {previewMut.isError && (
              <p className="mt-3 text-sm text-red-600">
                {(previewMut.error as any)?.response?.data?.detail ?? 'Error parsing file. Check the format and try again.'}
              </p>
            )}
          </Card>
        </div>
      )}

      {/* ── Step 2: Preview ── */}
      {step === 'preview' && rows && counts && (
        <div className="space-y-4">

          {/* Summary */}
          <div className="grid grid-cols-4 gap-3">
            {[
              { label: 'Will import', count: counts.new, color: 'text-emerald-700 bg-emerald-50 border-emerald-200' },
              { label: 'Already exists', count: counts.exists, color: 'text-blue-700 bg-blue-50 border-blue-200' },
              { label: 'Needs review', count: counts.unrecognised, color: 'text-amber-700 bg-amber-50 border-amber-200' },
              { label: 'Skipped (instruments)', count: counts.skip, color: 'text-slate-500 bg-slate-50 border-slate-200' },
            ].map(s => (
              <div key={s.label} className={`rounded-xl border p-3 text-center ${s.color}`}>
                <p className="text-2xl font-bold">{s.count}</p>
                <p className="text-xs font-medium mt-0.5">{s.label}</p>
              </div>
            ))}
          </div>

          {/* Unrecognised warning */}
          {counts.unrecognised > 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 flex gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
              <div className="text-xs text-amber-800">
                <p className="font-semibold">{counts.unrecognised} rows could not be automatically parsed.</p>
                <p>The antibody name could not be extracted from the Short Text. You can edit the name below before importing, or leave blank to skip these rows.</p>
              </div>
            </div>
          )}

          {/* Preview table */}
          <Card padding={false}>
            <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-900">
                Preview — {rows.length} rows
              </h2>
              <p className="text-xs text-slate-400">
                Edit antibody name or fluorochrome if the parser got it wrong
              </p>
            </div>
            <div className="overflow-x-auto max-h-[480px] overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-slate-50 z-10">
                  <tr className="border-b border-slate-100">
                    {['Status', 'Short Text (SAP)', 'Antibody name', 'Fluorochrome', 'Vendor', 'Vol (µl)', 'Catalog No'].map(h => (
                      <th key={h} className="text-left px-3 py-2 font-semibold text-slate-500 whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {rows.map((row, idx) => (
                    <tr
                      key={row.row_index}
                      className={`${
                        row.status === 'skip' ? 'opacity-40' :
                        row.status === 'exists' ? 'bg-blue-50/30' :
                        row.status === 'unrecognised' ? 'bg-amber-50/40' : ''
                      }`}
                    >
                      <td className="px-3 py-2 whitespace-nowrap">
                        <StatusBadge status={row.status} />
                        {row.skip_reason && (
                          <p className="text-slate-400 mt-0.5 text-xs">{row.skip_reason}</p>
                        )}
                      </td>
                      <td className="px-3 py-2 max-w-[200px]">
                        <p className="text-slate-600 truncate" title={row.short_text}>{row.short_text}</p>
                        <p className="text-slate-400 font-mono mt-0.5">{row.material_no}</p>
                      </td>
                      <td className="px-3 py-2 min-w-[120px]">
                        {row.status === 'skip' || row.status === 'exists' ? (
                          <span className="text-slate-500">{row.antibody_name ?? '—'}</span>
                        ) : (
                          <EditableCell
                            value={row.override_name ?? row.antibody_name ?? ''}
                            onChange={v => updateRow(idx, 'override_name', v)}
                            placeholder="e.g. CD19"
                          />
                        )}
                      </td>
                      <td className="px-3 py-2 min-w-[110px]">
                        {row.status === 'skip' || row.status === 'exists' ? (
                          <span className="text-slate-500">{row.fluorochrome_name ?? '—'}</span>
                        ) : (
                          <EditableCell
                            value={row.override_fluorochrome ?? row.fluorochrome_name ?? ''}
                            onChange={v => updateRow(idx, 'override_fluorochrome', v)}
                            placeholder="e.g. PE-Cy7"
                          />
                        )}
                      </td>
                      <td className="px-3 py-2 text-slate-600">{row.vendor ?? '—'}</td>
                      <td className="px-3 py-2 tabular-nums text-slate-600">
                        {row.volume_ul != null ? `${row.volume_ul} µl` : '—'}
                      </td>
                      <td className="px-3 py-2 font-mono text-slate-400">{row.catalog_no ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          {/* Actions */}
          <div className="flex items-center justify-between">
            <Button variant="secondary" onClick={() => { setStep('upload'); setRows(null) }}>
              Upload different file
            </Button>
            <div className="flex items-center gap-3">
              <p className="text-sm text-slate-500">
                {toImportReady.length} of {toImport.length} rows ready to import
              </p>
              <Button
                onClick={() => commitMut.mutate(toImportReady)}
                disabled={commitMut.isPending || toImportReady.length === 0}
              >
                {commitMut.isPending
                  ? 'Importing...'
                  : `Import ${toImportReady.length} antibod${toImportReady.length === 1 ? 'y' : 'ies'}`}
              </Button>
            </div>
          </div>

          {commitMut.isError && (
            <p className="text-sm text-red-600">
              {(commitMut.error as any)?.response?.data?.detail ?? 'Error during import'}
            </p>
          )}
        </div>
      )}

      {/* ── Step 3: Done ── */}
      {step === 'done' && result && (
        <Card>
          <div className="text-center py-6 space-y-4">
            <CheckCircle className="w-12 h-12 text-emerald-500 mx-auto" />
            <h2 className="text-lg font-semibold text-slate-900">Import complete</h2>

            <div className="grid grid-cols-3 gap-4 max-w-sm mx-auto">
              <div className="bg-emerald-50 rounded-lg p-3">
                <p className="text-2xl font-bold text-emerald-700">{result.antibodies_created}</p>
                <p className="text-xs text-emerald-600 mt-0.5">Antibodies created</p>
              </div>
              <div className="bg-blue-50 rounded-lg p-3">
                <p className="text-2xl font-bold text-blue-700">{result.fluorochromes_created}</p>
                <p className="text-xs text-blue-600 mt-0.5">Fluorochromes added</p>
              </div>
              <div className="bg-slate-50 rounded-lg p-3">
                <p className="text-2xl font-bold text-slate-600">{result.antibodies_skipped_existing}</p>
                <p className="text-xs text-slate-500 mt-0.5">Already existed</p>
              </div>
            </div>

            {(result.vial_volumes_set ?? 0) > 0 && (
              <p className="text-xs text-slate-500">
                Standard vial volume filled in for {result.vial_volumes_set} existing antibod{result.vial_volumes_set === 1 ? 'y' : 'ies'} that had none.
              </p>
            )}

            {result.errors.length > 0 && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-left max-w-lg mx-auto">
                <p className="text-xs font-semibold text-red-700 mb-1">{result.errors.length} rows had errors:</p>
                {result.errors.map((e, i) => (
                  <p key={i} className="text-xs text-red-600">{e}</p>
                ))}
              </div>
            )}

            <p className="text-sm text-slate-500">
              The imported antibodies are now in your master list.<br />
              Go to Admin → Antibodies to review, add clones, or assign alternatives.
            </p>

            <div className="flex gap-3 justify-center">
              <Button variant="secondary" onClick={() => { setStep('upload'); setRows(null); setResult(null) }}>
                Import another file
              </Button>
              <Button onClick={() => navigate('/admin/antibodies')}>
                View antibody master
              </Button>
            </div>
          </div>
        </Card>
      )}
    </div>
  )
}
