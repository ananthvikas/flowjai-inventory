// pages/admin/ProcessSteps.tsx — processing step lists for the bench station

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, Plus, Timer, Trash2, Workflow } from 'lucide-react'
import { useEffect, useState } from 'react'
import { stationApi } from '../../api/client'
import { Badge, Button, Card, Spinner } from '../../components/ui'
import type { TemplateStep } from '../../types'

type Selection = { kind: 'default' } | { kind: 'panel'; panelId: number }

const SOURCE_LABEL: Record<string, string> = {
  panel: 'own steps',
  lab_default: 'lab default',
  built_in: 'built-in default',
}

export default function ProcessStepsPage() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['step-templates'], queryFn: stationApi.templates })
  const [sel, setSel] = useState<Selection>({ kind: 'default' })
  const [draft, setDraft] = useState<TemplateStep[]>([])
  const [error, setError] = useState('')
  const [saved, setSaved] = useState('')

  const current = !data ? null
    : sel.kind === 'default' ? { title: 'Lab default', steps: data.default.steps, source: data.default.source }
    : (() => {
        const p = data.panels.find((x) => x.panel_id === sel.panelId)
        return p ? { title: `${p.test_code} — ${p.panel_name}`, steps: p.steps, source: p.source } : null
      })()

  useEffect(() => { if (current) { setDraft(current.steps.map((s) => ({ ...s }))); setError(''); setSaved('') } },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data, sel.kind, sel.kind === 'panel' ? sel.panelId : 0])

  const save = useMutation({
    mutationFn: (names: TemplateStep[]) =>
      sel.kind === 'default' ? stationApi.saveDefault(names) : stationApi.savePanel(sel.panelId, names),
    onSuccess: (d: any, names) => {
      qc.invalidateQueries({ queryKey: ['step-templates'] })
      qc.invalidateQueries({ queryKey: ['station-queue'] })
      const live = d?.live_tubes_updated ?? 0
      setSaved(
        (names.length ? 'Saved.' : 'This panel now uses the lab default.') +
        (live ? ` Timers updated on ${live} tube${live === 1 ? '' : 's'} already on the bench station.` : '') +
        ' New step names and order apply to tubes ordered from now on.'
      )
      setError('')
    },
    onError: (e: any) => setError(e.response?.data?.detail ?? 'Could not save'),
  })

  const move = (i: number, d: -1 | 1) => setDraft((xs) => {
    const j = i + d
    if (j < 0 || j >= xs.length) return xs
    const n = [...xs]; [n[i], n[j]] = [n[j], n[i]]; return n
  })
  const dirty = current && JSON.stringify(draft) !== JSON.stringify(current.steps)
  const setStep = (i: number, patch: Partial<TemplateStep>) =>
    setDraft((xs) => xs.map((x, k) => (k === i ? { ...x, ...patch } : x)))
  const total = draft.reduce((m, s, i) => m + (i > 0 && s.wait_minutes ? s.wait_minutes : 0), 0)

  return (
    <div className="p-6 space-y-5">
      <div>
        <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2">
          <Workflow className="w-5 h-5 text-brand-600" /> Processing steps
        </h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Steps shown on the bench station for each tube. Panels without their own list use the lab default.
        </p>
      </div>

      {isLoading || !data ? <Spinner className="py-16" /> : (
        <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-5 items-start">
          <Card padding={false}>
            <button
              onClick={() => setSel({ kind: 'default' })}
              className={`w-full text-left px-4 py-3 border-b border-slate-100 ${sel.kind === 'default' ? 'bg-brand-50' : 'hover:bg-slate-50'}`}
            >
              <p className="text-sm font-semibold text-slate-900">Lab default</p>
              <p className="text-xs text-slate-500">{data.default.names.length} steps · {SOURCE_LABEL[data.default.source]}</p>
            </button>
            <div className="max-h-[60vh] overflow-y-auto divide-y divide-slate-50">
              {data.panels.map((p) => (
                <button
                  key={p.panel_id}
                  onClick={() => setSel({ kind: 'panel', panelId: p.panel_id })}
                  className={`w-full text-left px-4 py-2.5 flex items-center justify-between gap-2 ${
                    sel.kind === 'panel' && sel.panelId === p.panel_id ? 'bg-brand-50' : 'hover:bg-slate-50'}`}
                >
                  <span className="min-w-0">
                    <span className="text-sm font-medium text-slate-800">{p.test_code}</span>
                    <span className="text-xs text-slate-500 ml-1.5 truncate">{p.panel_name}</span>
                  </span>
                  <Badge variant={p.source === 'panel' ? 'info' : 'unknown'}>{p.source === 'panel' ? `${p.names.length} steps` : 'default'}</Badge>
                </button>
              ))}
            </div>
          </Card>

          {current && (
            <Card>
              <div className="flex items-center justify-between mb-1">
                <h2 className="text-base font-semibold text-slate-900">{current.title}</h2>
                <span className="text-xs text-slate-400">currently: {SOURCE_LABEL[current.source]}</span>
              </div>
              <p className="text-xs text-slate-500 mb-4">
                Step 1 is always the cocktail step: completing it uses the tube's reserved cocktail test.
                The last step completes the tube. Tubes already ordered keep their step names and order,
                but pick up timer changes straight away.
              </p>
              <p className="text-xs text-slate-500 mb-4 -mt-2 flex items-start gap-1.5">
                <Timer className="w-3.5 h-3.5 mt-px shrink-0 text-brand-600" />
                <span>
                  <b>Wait</b> is the minimum time after the previous step before this one is due — e.g. put 15 on
                  “Incubated” for a 15-minute incubation after the cocktail is added. The tablet counts it down and
                  chimes when it's done. Leave blank for no timer.
                </span>
              </p>

              <ol className="space-y-2">
                {draft.map((st, i) => (
                  <li key={i} className="flex items-center gap-2">
                    <span className="w-6 text-right text-sm tabular-nums text-slate-400">{i + 1}</span>
                    <input
                      value={st.name}
                      maxLength={64}
                      onChange={(e) => setStep(i, { name: e.target.value })}
                      className="flex-1 px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500"
                    />
                    {i === 0 ? (
                      <span className="w-[132px] text-xs text-brand-700 whitespace-nowrap text-center">uses cocktail</span>
                    ) : (
                      <label className="w-[132px] flex items-center gap-1.5 text-xs text-slate-500 whitespace-nowrap">
                        wait
                        <input
                          type="number" min={1} max={1440} inputMode="numeric"
                          value={st.wait_minutes ?? ''}
                          onChange={(e) => setStep(i, { wait_minutes: e.target.value === '' ? null : Math.max(0, parseInt(e.target.value) || 0) })}
                          placeholder="—"
                          className="w-16 px-2 py-2 text-sm text-right tabular-nums border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500"
                        />
                        min
                      </label>
                    )}
                    <button onClick={() => move(i, -1)} disabled={i === 0} className="p-1.5 text-slate-400 hover:text-slate-700 disabled:opacity-30"><ArrowUp className="w-4 h-4" /></button>
                    <button onClick={() => move(i, 1)} disabled={i === draft.length - 1} className="p-1.5 text-slate-400 hover:text-slate-700 disabled:opacity-30"><ArrowDown className="w-4 h-4" /></button>
                    <button onClick={() => setDraft((xs) => xs.filter((_, k) => k !== i))} className="p-1.5 text-slate-300 hover:text-red-500"><Trash2 className="w-4 h-4" /></button>
                  </li>
                ))}
              </ol>
              {total > 0 && (
                <p className="text-xs text-slate-500 mt-3 ml-8">Timed waits add up to {total} min per tube.</p>
              )}

              <div className="flex flex-wrap items-center gap-2 mt-4">
                <Button variant="secondary" size="sm" onClick={() => setDraft((xs) => [...xs, { name: '', wait_minutes: null }])} disabled={draft.length >= 12}>
                  <Plus className="w-3.5 h-3.5" /> Add step
                </Button>
                {sel.kind === 'default' && current.source !== 'built_in' && (
                  <Button variant="ghost" size="sm" onClick={() => setDraft(data.built_in.map((name) => ({ name, wait_minutes: null })))}>Reset to built-in</Button>
                )}
                <div className="ml-auto flex gap-2">
                  {sel.kind === 'panel' && current.source === 'panel' && (
                    <Button variant="secondary" size="sm" onClick={() => save.mutate([])} disabled={save.isPending}>
                      Use lab default instead
                    </Button>
                  )}
                  <Button size="sm" onClick={() => save.mutate(draft)}
                    disabled={save.isPending || (!dirty && !(sel.kind === 'panel' && current.source !== 'panel')) || draft.filter((d) => d.name.trim()).length < 2}>
                    {save.isPending ? 'Saving…' : sel.kind === 'panel' && current.source !== 'panel' ? 'Give this panel its own steps' : 'Save'}
                  </Button>
                </div>
              </div>
              {error && <p className="text-sm text-red-600 mt-3">{error}</p>}
              {saved && <p className="text-sm text-emerald-600 mt-3">{saved}</p>}
            </Card>
          )}
        </div>
      )}
    </div>
  )
}
