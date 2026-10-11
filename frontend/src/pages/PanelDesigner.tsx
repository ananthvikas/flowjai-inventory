// pages/PanelDesigner.tsx — 3-step panel designer wizard

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, AlertTriangle, ArrowLeft, ArrowRight, Eye, XCircle, RefreshCw } from 'lucide-react'
import { api, antibodiesApi } from '../api/client'
import { Button, Card, EmptyState, Input, Modal, Spinner } from '../components/ui'
import type { Antibody } from '../types'

// ── Types ────────────────────────────────────────────────────────────────────

interface FluorochromeOption {
  fluorochrome_id: number
  fluorochrome_name: string
  laser: string | null
  emission_nm: number | null
  stock_ul: number
  antibody_id: number | null
  clone: string | null
  vendor: string | null
}

interface AntibodyOption {
  antibody_id: number
  antibody_name: string
  clone: string | null
  vendor: string | null
  fluorochrome_options: FluorochromeOption[]
}

interface Assignment {
  antibody_id: number
  antibody_name: string
  fluorochrome_id: number
  fluorochrome_name: string
  laser: string | null
  emission_nm: number | null
  stock_ul: number
}

interface Combination {
  index: number
  assignments: Assignment[]
  total_stock_ul: number
}

interface Clash {
  fluorochrome_name: string
  conflicting_antibodies: { antibody_id: number; name: string; fluorochrome_name?: string | null; stock_ul: number }[]
}

interface AlternativeEntry {
  antibody_id: number
  antibody_name: string
  fluorochrome_id: number | null
  fluorochrome_name: string | null
  stock_ul: number
}

interface DesignResponse {
  antibody_options: AntibodyOption[]
  combinations: Combination[]
  clashes: Clash[]
  unplaced_antibodies: number[]
  alternatives?: Record<number, AlternativeEntry[]>
  search_truncated: boolean
}

type Step = 'pick' | 'design' | 'finalize'

// ── Component ────────────────────────────────────────────────────────────────

export default function PanelDesignerPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [step, setStep] = useState<Step>('pick')
  const [search, setSearch] = useState('')
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [design, setDesign] = useState<DesignResponse | null>(null)
  const [comboIdx, setComboIdx] = useState(0)
  const [clashResolutions, setClashResolutions] = useState<Record<number, 'keep' | 'exclude'>>({})
  const [panelName, setPanelName] = useState('')
  const [testCode, setTestCode] = useState('')
  const [testGroup, setTestGroup] = useState('')
  const [department, setDepartment] = useState('')
  const [volumePerTube, setVolumePerTube] = useState('0.5')
  const [previewOpen, setPreviewOpen] = useState(false)
  const [error, setError] = useState('')

  // Fetch antibodies — using proven antibodiesApi.list() pattern
  const { data: antibodies = [], isLoading } = useQuery({
    queryKey: ['antibodies', 'panel-designer'],
    queryFn: () => antibodiesApi.list(true),
  })

  // ── Design mutation ───────────────────────────────────────────────────────

  const designMutation = useMutation({
    mutationFn: (ids: number[]) =>
      api.post<DesignResponse>('/panel-designer/design', { antibody_ids: ids }).then(r => r.data),
    onSuccess: (data) => {
      setDesign(data)
      setStep('design')
      setError('')
      // Auto-resolve: keep highest-stock antibody in each clash
      const resolutions: Record<number, 'keep' | 'exclude'> = {}
      for (const clash of data.clashes) {
        const sorted = [...clash.conflicting_antibodies].sort((a, b) => b.stock_ul - a.stock_ul)
        resolutions[sorted[0].antibody_id] = 'keep'
        for (let i = 1; i < sorted.length; i++) {
          resolutions[sorted[i].antibody_id] = 'exclude'
        }
      }
      setClashResolutions(resolutions)
    },
    onError: (err: any) => setError(err.response?.data?.detail ?? 'Design failed'),
  })

  // ── Create mutation ────────────────────────────────────────────────────────

  const createMutation = useMutation({
    mutationFn: () => {
      const combo = design!.combinations[comboIdx]
      const usedIds = new Set<number>()
      const assignments: Assignment[] = []

      // Start with combo assignments, filtering by clash resolutions
      if (combo) {
        for (const a of combo.assignments) {
          if (clashResolutions[a.antibody_id] === 'exclude') continue
          if (usedIds.has(a.antibody_id)) continue
          usedIds.add(a.antibody_id)
          assignments.push(a)
        }
      }

      // Include kept antibodies from clashes that weren't in the combo
      if (design) {
        for (const clash of design.clashes) {
          for (const ca of clash.conflicting_antibodies) {
            if (clashResolutions[ca.antibody_id] === 'keep' && !usedIds.has(ca.antibody_id)) {
              const opt = design.antibody_options.find(o => o.antibody_id === ca.antibody_id)
              if (opt && opt.fluorochrome_options.length > 0) {
                const fc = opt.fluorochrome_options[0]
                assignments.push({
                  antibody_id: fc.antibody_id ?? ca.antibody_id,
                  antibody_name: ca.name,
                  fluorochrome_id: fc.fluorochrome_id,
                  fluorochrome_name: fc.fluorochrome_name,
                  laser: fc.laser,
                  emission_nm: fc.emission_nm,
                  stock_ul: fc.stock_ul,
                })
                usedIds.add(ca.antibody_id)
              }
            }
          }
        }
      }

      return api.post('/panel-designer/create', {
        name: panelName.trim(),
        test_code: testCode.trim(),
        test_group: testGroup.trim() || undefined,
        department: department.trim() || undefined,
        volume_per_tube_ul: parseFloat(volumePerTube) || 0.5,
        tubes_per_test: 1,
        assignments,
      }).then(r => r.data)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['panels'] })
      navigate('/admin/panels')
    },
    onError: (err: any) => setError(err.response?.data?.detail ?? 'Failed to create panel'),
  })

  // ── Helpers ────────────────────────────────────────────────────────────────

  // Deduplicate antibodies by name — show one entry per antibody name,
  // but selecting it sends all fluorochrome variants to the algorithm.
  const nameGroups = new Map<string, number[]>()
  for (const ab of antibodies) {
    const key = ab.name.toLowerCase()
    if (!nameGroups.has(key)) nameGroups.set(key, [])
    nameGroups.get(key)!.push(ab.id)
  }

  const uniqueAntibodies = antibodies.filter(ab => {
    const key = ab.name.toLowerCase()
    const ids = nameGroups.get(key)
    return ids && ids[0] === ab.id
  })

  const filtered = uniqueAntibodies.filter(ab =>
    !search || ab.name.toLowerCase().includes(search.toLowerCase())
  )

  const toggleId = (id: number) => {
    const ab = antibodies.find(a => a.id === id)
    const key = ab ? ab.name.toLowerCase() : ''
    const allIds = nameGroups.get(key) || [id]
    setSelectedIds(prev => {
      const alreadySelected = allIds.some(x => prev.includes(x))
      if (alreadySelected) return prev.filter(x => !allIds.includes(x))
      return [...prev, ...allIds]
    })
  }

  const chosenCombo = design?.combinations[comboIdx]
  const effectiveAbs = chosenCombo
    ? chosenCombo.assignments.filter(a => clashResolutions[a.antibody_id] !== 'exclude')
    : []

  // Resolved antibodies list (for preview)
  const resolvedAntibodies = effectiveAbs

  const stepLabels: Record<Step, string> = { pick: 'Pick Antibodies', design: 'Resolve Design', finalize: 'Finalize' }

  const stepOrder: Step[] = ['pick', 'design', 'finalize']

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="p-6 space-y-5 max-w-4xl mx-auto">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Panel Designer</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Pick antibodies, resolve fluorochrome clashes, and auto-generate a panel.
        </p>
      </div>

      {/* Progress bar */}
      <div className="flex items-center gap-2 text-sm">
        {stepOrder.map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold ${
              step === s ? 'bg-brand-600 text-white' :
              stepOrder.indexOf(step) > i ? 'bg-emerald-500 text-white' :
              'bg-slate-200 text-slate-500'
            }`}>
              {stepOrder.indexOf(step) > i ? '✓' : i + 1}
            </div>
            <span className={step === s ? 'font-medium text-slate-900' : 'text-slate-400'}>
              {stepLabels[s]}
            </span>
            {i < 2 && <div className="w-8 h-px bg-slate-300" />}
          </div>
        ))}
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      {/* ═══ STEP 1: Pick ═══ */}
      {step === 'pick' && (
        <Card>
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <Input
                placeholder="Search antibodies..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="flex-1"
              />
              <Button
                onClick={() => designMutation.mutate(selectedIds)}
                disabled={selectedIds.length === 0 || designMutation.isPending}
              >
                {designMutation.isPending ? 'Designing...' : `Design (${selectedIds.length})`}
              </Button>
            </div>
            {isLoading ? (
              <Spinner className="py-8" />
            ) : filtered.length === 0 ? (
              <EmptyState message={search ? 'No matching antibodies' : 'No antibodies found'} />
            ) : (
              <div className="max-h-[55vh] overflow-y-auto space-y-0.5">
                {filtered.map(ab => {
                  const sel = selectedIds.includes(ab.id)
                  return (
                    <div
                      key={ab.id}
                      onClick={() => toggleId(ab.id)}
                      className={`flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer border ${
                        sel ? 'bg-brand-50 border-brand-300' : 'bg-white border-slate-200 hover:bg-slate-50'
                      }`}
                    >
                      <div className={`w-5 h-5 rounded border-2 flex items-center justify-center shrink-0 ${
                        sel ? 'bg-brand-600 border-brand-600' : 'border-slate-300'
                      }`}>
                        {sel && <Check className="w-3 h-3 text-white" />}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-slate-800 truncate">{ab.name}</p>
                        <p className="text-xs text-slate-400 truncate">
                          {[ab.clone, ab.vendor].filter(Boolean).join(' · ') || 'No details'}
                        </p>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </Card>
      )}

      {/* ═══ STEP 2: Resolve ═══ */}
      {step === 'design' && design && (
        <div className="space-y-5">
          {design.search_truncated && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-800">
              The search space was too large to enumerate exhaustively — the combinations below are the
              top-ranked subset, not a complete list. Refine your selection for an exhaustive search.
            </div>
          )}
          {/* Clashes */}
          {design.clashes.length > 0 && (
            <Card>
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="w-5 h-5 text-amber-500" />
                  <h2 className="text-sm font-semibold text-slate-900">Clashes ({design.clashes.length})</h2>
                  <span className="text-xs text-slate-500">— multiple antibodies share a fluorochrome</span>
                </div>
                {design.clashes.map(clash => (
                  <div key={clash.fluorochrome_name} className="border border-amber-200 bg-amber-50/50 rounded-lg p-3 space-y-2">
                    <p className="text-sm font-semibold text-amber-800">Channel: {clash.fluorochrome_name}</p>
                    {clash.conflicting_antibodies.map(ca => {
                      const res = clashResolutions[ca.antibody_id]
                      return (
                        <div key={ca.antibody_id} className="flex items-center gap-3">
                          <div className="flex gap-1">
                            <button
                              onClick={() => setClashResolutions(prev => ({ ...prev, [ca.antibody_id]: 'keep' }))}
                              className={`px-2 py-0.5 text-xs rounded border font-medium ${
                                res === 'keep' ? 'bg-emerald-500 text-white border-emerald-500' : 'border-slate-300 hover:bg-emerald-50'
                              }`}
                            >Keep</button>
                            <button
                              onClick={() => setClashResolutions(prev => ({ ...prev, [ca.antibody_id]: 'exclude' }))}
                              className={`px-2 py-0.5 text-xs rounded border font-medium ${
                                res === 'exclude' ? 'bg-red-500 text-white border-red-500' : 'border-slate-300 hover:bg-red-50'
                              }`}
                            >Exclude</button>
                          </div>
                          <span className={res === 'exclude' ? 'text-sm text-slate-400 line-through' : 'text-sm font-medium text-slate-800'}>
                            {ca.name}{ca.fluorochrome_name ? ` · ${ca.fluorochrome_name}` : ''}
                          </span>
                          <span className="text-xs text-slate-400">{ca.stock_ul.toFixed(0)} µl</span>
                        </div>
                      )
                    })}
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Combinations */}
          {design.combinations.length > 0 && (
            <Card>
              <div className="space-y-3">
                <h2 className="text-sm font-semibold text-slate-900">
                  Combinations ({design.combinations.length}{design.combinations.length >= 50 ? '+ top 50' : ''})
                </h2>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-slate-200 text-left">
                        <th className="py-1.5 px-2 w-8 text-slate-400 font-medium">#</th>
                        <th className="py-1.5 px-2 text-slate-400 font-medium">Antibodies</th>
                        <th className="py-1.5 px-2 text-slate-400 font-medium">Fluorochromes</th>
                        <th className="py-1.5 px-2 text-slate-400 font-medium text-right">Stock (µl)</th>
                        <th className="py-1.5 px-2 w-10"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {design.combinations.map(c => {
                        const effective = c.assignments.filter(a => clashResolutions[a.antibody_id] !== 'exclude')
                        return (
                          <tr
                            key={c.index}
                            onClick={() => setComboIdx(c.index)}
                            className={`border-b border-slate-50 cursor-pointer transition-colors ${
                              comboIdx === c.index
                                ? 'bg-brand-50 border-l-2 border-l-brand-600'
                                : 'hover:bg-slate-50'
                            }`}
                          >
                            <td className={`py-1.5 px-2 font-medium ${comboIdx === c.index ? 'text-brand-700' : 'text-slate-400'}`}>
                              {c.index + 1}
                            </td>
                            <td className="py-1.5 px-2 text-slate-700">
                              {effective.map(a => a.antibody_name).join(', ')}
                            </td>
                            <td className="py-1.5 px-2 text-slate-500">
                              {effective.map(a => a.fluorochrome_name).join(', ')}
                            </td>
                            <td className="py-1.5 px-2 text-right tabular-nums font-medium text-slate-700">
                              {effective.reduce((s, a) => s + a.stock_ul, 0).toFixed(0)}
                            </td>
                            <td className="py-1.5 px-2 text-center">
                              <div className={`w-4 h-4 rounded-full border-2 mx-auto flex items-center justify-center ${
                                comboIdx === c.index
                                  ? 'border-brand-600'
                                  : 'border-slate-300'
                              }`}>
                                {comboIdx === c.index && <div className="w-2 h-2 rounded-full bg-brand-600" />}
                              </div>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
                {chosenCombo && (
                  <div className="border border-brand-200 bg-brand-50/30 rounded-lg p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-semibold text-brand-800">Combination #{comboIdx + 1}</p>
                      <span className="text-xs text-brand-600 font-medium">
                        {effectiveAbs.reduce((s, a) => s + a.stock_ul, 0).toFixed(0)} µl · {effectiveAbs.length} abs
                      </span>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5">
                      {chosenCombo.assignments
                        .filter(a => clashResolutions[a.antibody_id] !== 'exclude')
                        .map(a => (
                          <div key={a.antibody_id} className="flex items-center gap-2 bg-white rounded px-2.5 py-1.5 border border-slate-100">
                            <div className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium text-slate-800 truncate">{a.antibody_name}</p>
                              <p className="text-xs text-slate-400">{a.fluorochrome_name} · {a.stock_ul.toFixed(0)} µl</p>
                            </div>
                          </div>
                        ))}
                    </div>
                  </div>
                )}
              </div>
            </Card>
          )}

          {design.unplaced_antibodies.length > 0 && (
            <Card>
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <XCircle className="w-5 h-5 text-red-500" />
                  <h2 className="text-sm font-semibold text-slate-900">
                    Out of Stock ({design.unplaced_antibodies.length} antibodies)
                  </h2>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5">
                  {design.antibody_options
                    .filter(o => design.unplaced_antibodies.includes(o.antibody_id))
                    .map(o => (
                      <div key={o.antibody_id} className="flex items-center gap-2 bg-red-50 rounded px-2.5 py-1.5 border border-red-100">
                        <XCircle className="w-3.5 h-3.5 text-red-400 shrink-0" />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-red-700 truncate">{o.antibody_name}</p>
                          <p className="text-xs text-red-400">No stock available</p>
                        </div>
                      </div>
                    ))}
                </div>

                {/* Alternatives for out-of-stock antibodies */}
                {design.alternatives && Object.keys(design.alternatives).length > 0 && (
                  <div className="pt-2 border-t border-slate-100">
                    <h3 className="text-xs font-semibold text-slate-500 mb-2">Available alternatives</h3>
                    <div className="space-y-2">
                      {Object.entries(design.alternatives).map(([abId, alts]) => {
                        const parent = design.antibody_options.find(o => o.antibody_id === Number(abId))
                        return (
                          <div key={abId} className="bg-blue-50 rounded-lg p-2 border border-blue-100">
                            <p className="text-xs font-medium text-blue-800 mb-1">
                              Alternatives for <span className="font-semibold">{parent?.antibody_name || 'Unknown'}</span>:
                            </p>
                            <div className="flex flex-wrap gap-1.5">
                              {alts.map(alt => (
                                <button
                                  key={alt.antibody_id}
                                  onClick={() => {
                                    setSelectedIds(prev => [...prev, alt.antibody_id])
                                    setDesign(null)
                                    const newIds = [...selectedIds.filter(id => !design.unplaced_antibodies.includes(id)), alt.antibody_id]
                                    designMutation.mutate(newIds)
                                  }}
                                  disabled={designMutation.isPending}
                                  className="px-2 py-1 rounded text-xs font-medium border border-blue-300 bg-white hover:bg-blue-50 text-blue-700"
                                >
                                  {alt.antibody_name}{alt.fluorochrome_name ? ` · ${alt.fluorochrome_name}` : ''} ({alt.stock_ul.toFixed(0)} µl)
                                </button>
                              ))}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}

                <div className="pt-2 border-t border-slate-100">
                  <h3 className="text-xs font-semibold text-slate-500 mb-1.5">
                    Valid antibodies ({design.antibody_options.filter(o => !design.unplaced_antibodies.includes(o.antibody_id) && o.fluorochrome_options.length > 0).length})
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-1">
                    {design.antibody_options
                      .filter(o => !design.unplaced_antibodies.includes(o.antibody_id) && o.fluorochrome_options.length > 0)
                      .map(o => (
                        <div key={o.antibody_id} className="flex items-center gap-1.5 text-xs text-slate-600">
                          <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0" />
                          <span className="truncate">{o.antibody_name}</span>
                        </div>
                      ))}
                  </div>
                </div>

                <Button variant="secondary" size="sm" onClick={() => {
                  const cleanedIds = selectedIds.filter(id => !design.unplaced_antibodies.includes(id))
                  setSelectedIds(cleanedIds)
                  if (cleanedIds.length > 0) {
                    setDesign(null)  // reset to force clean re-render
                    designMutation.mutate(cleanedIds)
                  }
                  else setStep('pick')
                }} disabled={designMutation.isPending}>
                  <RefreshCw className={`w-3.5 h-3.5 mr-1 ${designMutation.isPending ? 'animate-spin' : ''}`} />
                  Exclude out-of-stock & re-design
                </Button>
              </div>
            </Card>
          )}

          {design.combinations.length === 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-800">
              No valid combinations found.
            </div>
          )}

          {resolvedAntibodies.length > 0 && (
            <Card>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-semibold text-slate-900">
                    Resolved Panel ({resolvedAntibodies.length} antibodies)
                  </h2>
                  <Button variant="secondary" size="sm" onClick={() => setPreviewOpen(true)}>
                    <Eye className="w-3.5 h-3.5 mr-1" /> Preview
                  </Button>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5">
                  {resolvedAntibodies.slice(0, 6).map(a => (
                    <div key={a.antibody_id} className="flex items-center gap-2 bg-slate-50 rounded px-2.5 py-1.5">
                      <div className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-slate-800 truncate">{a.antibody_name}</p>
                        <p className="text-xs text-slate-400">{a.fluorochrome_name} · {a.stock_ul.toFixed(0)} µl</p>
                      </div>
                    </div>
                  ))}
                  {resolvedAntibodies.length > 6 && (
                    <div className="flex items-center justify-center px-2.5 py-1.5 text-xs text-slate-400">
                      +{resolvedAntibodies.length - 6} more — click Preview
                    </div>
                  )}
                </div>
              </div>
            </Card>
          )}

          <div className="flex justify-between">
            <Button variant="secondary" onClick={() => { setStep('pick'); setDesign(null) }}>
              <ArrowLeft className="w-4 h-4 mr-1" /> Back
            </Button>
            <Button onClick={() => setStep('finalize')}
              disabled={design.combinations.length === 0}>
              Continue <ArrowRight className="w-4 h-4 ml-1" />
            </Button>
          </div>

          {/* ── Preview Modal ─────────────────────────────────────────── */}
          <Modal open={previewOpen} onClose={() => setPreviewOpen(false)} title={`Resolved Panel (${resolvedAntibodies.length} antibodies)`}>
            <div className="space-y-3">
              <div className="bg-slate-50 rounded-lg p-3 grid grid-cols-2 gap-2 text-xs">
                <div>
                  <span className="text-slate-400">Antibodies:</span>{' '}
                  <span className="font-medium text-slate-800">{resolvedAntibodies.length}</span>
                </div>
                <div>
                  <span className="text-slate-400">Total stock:</span>{' '}
                  <span className="font-medium text-slate-800">{resolvedAntibodies.reduce((s, a) => s + a.stock_ul, 0).toFixed(0)} µl</span>
                </div>
                <div>
                  <span className="text-slate-400">Channels:</span>{' '}
                  <span className="font-medium text-slate-800">{new Set(resolvedAntibodies.map(a => a.fluorochrome_name)).size}</span>
                </div>
                <div>
                  <span className="text-slate-400">Clashes resolved:</span>{' '}
                  <span className="font-medium text-emerald-600">{design?.clashes.length ?? 0}</span>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-slate-100">
                      <th className="text-left py-1.5 px-2 font-medium text-slate-400">#</th>
                      <th className="text-left py-1.5 px-2 font-medium text-slate-400">Antibody</th>
                      <th className="text-left py-1.5 px-2 font-medium text-slate-400">Fluorochrome</th>
                      <th className="text-right py-1.5 px-2 font-medium text-slate-400">Stock (µl)</th>
                      <th className="text-center py-1.5 px-2 font-medium text-slate-400">Volume</th>
                    </tr>
                  </thead>
                  <tbody>
                    {resolvedAntibodies.map((a, i) => {
                      const isKept = clashResolutions[a.antibody_id] === 'keep'
                      return (
                        <tr key={a.antibody_id} className={`border-b border-slate-50 ${isKept ? 'bg-emerald-50/30' : ''}`}>
                          <td className="py-1.5 px-2 text-slate-400">{i + 1}</td>
                          <td className="py-1.5 px-2 font-medium text-slate-800 flex items-center gap-1.5">
                            {isKept && <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 inline-block" />}
                            {a.antibody_name}
                          </td>
                          <td className="py-1.5 px-2 text-slate-500">{a.fluorochrome_name}</td>
                          <td className="py-1.5 px-2 text-right tabular-nums">{a.stock_ul.toFixed(0)}</td>
                          <td className="py-1.5 px-2 text-center">
                            {isKept ? 
                              <span className="text-emerald-600 text-xs font-medium">Kept</span> : 
                              <span className="text-slate-400">—</span>
                            }
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              {resolvedAntibodies.length === 0 && (
                <div className="text-center py-4 text-sm text-slate-400">
                  No antibodies selected after resolving clashes.
                </div>
              )}
            </div>
          </Modal>
        </div>
      )}

      {/* ═══ STEP 3: Finalize ═══ */}
      {step === 'finalize' && (
        <div className="space-y-5">
          <Card>
            <div className="space-y-3">
              <h2 className="text-sm font-semibold text-slate-900">Panel Details</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <Input label="Panel Name" value={panelName} onChange={e => setPanelName(e.target.value)} placeholder="e.g. Acute Leukaemia Panel" />
                <Input label="Test Code" value={testCode} onChange={e => setTestCode(e.target.value)} placeholder="e.g. AL1" />
                <Input label="Test Group (optional)" value={testGroup} onChange={e => setTestGroup(e.target.value)} placeholder="e.g. Haematology" />
                <Input label="Department (optional)" value={department} onChange={e => setDepartment(e.target.value)} placeholder="e.g. Clinical Immunology" />
                <Input label="Volume per tube (µl)" type="number" step="0.1" min="0.1" value={volumePerTube} onChange={e => setVolumePerTube(e.target.value)} />
              </div>
            </div>
          </Card>

          <Card>
            <div className="space-y-2">
              <h2 className="text-sm font-semibold text-slate-900">Final Layout</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5">
                {effectiveAbs.map(a => (
                  <div key={a.antibody_id} className="flex items-center gap-2 bg-slate-50 rounded px-2.5 py-1.5">
                    <div className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-slate-800 truncate">{a.antibody_name}</p>
                      <p className="text-xs text-slate-400">{a.fluorochrome_name} · {a.stock_ul.toFixed(0)} µl</p>
                    </div>
                  </div>
                ))}
              </div>
              <div className="flex justify-between pt-2 border-t text-sm text-slate-500">
                <span>{effectiveAbs.length} antibodies</span>
                <span>{(effectiveAbs.length * parseFloat(volumePerTube || '0.5')).toFixed(1)} µl/test</span>
              </div>
            </div>
          </Card>

          <div className="flex justify-between">
            <Button variant="secondary" onClick={() => setStep('design')}>
              <ArrowLeft className="w-4 h-4 mr-1" /> Back
            </Button>
            <Button onClick={() => createMutation.mutate()}
              disabled={!panelName.trim() || !testCode.trim() || effectiveAbs.length === 0 || createMutation.isPending}>
              {createMutation.isPending ? 'Creating...' : `Create Panel "${panelName.trim() || '...'}"`}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}