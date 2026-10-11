// pages/admin/Settings.tsx — Per-antibody alert threshold configuration

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { alertRulesApi, antibodiesApi } from '../../api/client'
import { Button, Card, EmptyState, Input, Modal, Select, Spinner } from '../../components/ui'
import type { AlertRule } from '../../types'

const DEFAULTS = { lead_time_days: 35, safety_stock_ul: 0, alert_threshold_days: 42 }

function RuleModal({
  rule,
  onClose,
}: {
  rule: { antibody_id: number; antibody_name: string; existing?: AlertRule } | null
  onClose: () => void
}) {
  const qc = useQueryClient()
  const existing = rule?.existing
  const [form, setForm] = useState({
    lead_time_days: String(existing?.lead_time_days ?? DEFAULTS.lead_time_days),
    safety_stock_ul: String(existing?.safety_stock_ul ?? DEFAULTS.safety_stock_ul),
    alert_threshold_days: String(existing?.alert_threshold_days ?? DEFAULTS.alert_threshold_days),
  })
  const [error, setError] = useState('')
  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  const mut = useMutation({
    mutationFn: () => alertRulesApi.upsert(rule!.antibody_id, {
      lead_time_days: Number(form.lead_time_days),
      safety_stock_ul: Number(form.safety_stock_ul),
      alert_threshold_days: Number(form.alert_threshold_days),
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['alert-rules'] }); onClose() },
    onError: (e: any) => setError(e.response?.data?.detail ?? 'Error saving'),
  })

  const del = useMutation({
    mutationFn: () => alertRulesApi.remove(rule!.antibody_id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['alert-rules'] }); onClose() },
  })

  return (
    <Modal open={!!rule} onClose={onClose} title={`Alert rule — ${rule?.antibody_name}`}>
      <div className="space-y-4">
        <div className="bg-blue-50 rounded-lg p-3 text-xs text-blue-700 space-y-1">
          <p><strong>Lead time:</strong> expected days between order and delivery.</p>
          <p><strong>Alert threshold:</strong> raise alert when days remaining falls below this.</p>
          <p><strong>Safety stock:</strong> minimum µl to keep in reserve at all times.</p>
        </div>

        <Input
          label="Lead time (days)"
          type="number" min="1"
          value={form.lead_time_days}
          onChange={e => set('lead_time_days', e.target.value)}
        />
        <Input
          label="Alert threshold (days remaining)"
          type="number" min="1"
          value={form.alert_threshold_days}
          onChange={e => set('alert_threshold_days', e.target.value)}
        />
        <Input
          label="Safety stock (µl)"
          type="number" min="0" step="10"
          value={form.safety_stock_ul}
          onChange={e => set('safety_stock_ul', e.target.value)}
        />

        {error && <p className="text-sm text-red-600">{error}</p>}

        <div className="flex items-center justify-between pt-1">
          {existing && (
            <Button variant="danger" size="sm" onClick={() => del.mutate()} disabled={del.isPending}>
              Reset to defaults
            </Button>
          )}
          <div className="flex gap-2 ml-auto">
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button onClick={() => mut.mutate()} disabled={mut.isPending}>
              {mut.isPending ? 'Saving…' : 'Save rule'}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  )
}

export default function SettingsPage() {
  const [editing, setEditing] = useState<{ antibody_id: number; antibody_name: string; existing?: AlertRule } | null>(null)

  const { data: antibodies = [], isLoading: abLoading } = useQuery({
    queryKey: ['antibodies'],
    queryFn: () => antibodiesApi.list(),
  })

  const { data: rules = [], isLoading: rulesLoading } = useQuery({
    queryKey: ['alert-rules'],
    queryFn: alertRulesApi.list,
  })

  const rulesMap = new Map(rules.map(r => [r.antibody_id, r]))

  const isLoading = abLoading || rulesLoading

  return (
    <div className="p-6 space-y-5">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Alert Rules</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Per-antibody thresholds. Default: lead time 35 days, alert at 42 days remaining.
        </p>
      </div>

      {/* Global defaults card */}
      <Card>
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">System defaults</h2>
            <p className="text-xs text-slate-500 mt-0.5">Applied to antibodies without a custom rule.</p>
          </div>
          <div className="text-right text-xs text-slate-500 space-y-0.5">
            <p>Lead time: <span className="font-medium text-slate-700">35 days</span></p>
            <p>Alert threshold: <span className="font-medium text-slate-700">42 days</span></p>
            <p>Safety stock: <span className="font-medium text-slate-700">0 µl</span></p>
          </div>
        </div>
      </Card>

      {/* Per-antibody overrides */}
      <Card padding={false}>
        <div className="px-5 py-4 border-b border-slate-100">
          <h2 className="text-sm font-semibold text-slate-900">Custom rules</h2>
        </div>
        {isLoading ? (
          <Spinner className="py-16" />
        ) : antibodies.length === 0 ? (
          <EmptyState message="No antibodies yet" />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50">
                {['Antibody', 'Lead time', 'Alert threshold', 'Safety stock', ''].map(h => (
                  <th key={h} className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {antibodies.map(ab => {
                const rule = rulesMap.get(ab.id)
                const isCustom = !!rule
                return (
                  <tr key={ab.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-4 py-3 font-medium text-slate-800">
                      {ab.name}
                      {ab.fluorochrome && (
                        <span className="text-xs text-slate-400 ml-1.5">{ab.fluorochrome.name}</span>
                      )}
                    </td>
                    <td className="px-4 py-3 tabular-nums">
                      {isCustom
                        ? <span className="text-slate-800 font-medium">{rule.lead_time_days}d</span>
                        : <span className="text-slate-400">35d (default)</span>}
                    </td>
                    <td className="px-4 py-3 tabular-nums">
                      {isCustom
                        ? <span className="text-slate-800 font-medium">{rule.alert_threshold_days}d</span>
                        : <span className="text-slate-400">42d (default)</span>}
                    </td>
                    <td className="px-4 py-3 tabular-nums">
                      {isCustom
                        ? <span className="text-slate-800 font-medium">{rule.safety_stock_ul} µl</span>
                        : <span className="text-slate-400">0 µl (default)</span>}
                    </td>
                    <td className="px-4 py-3">
                      <Button
                        variant={isCustom ? 'secondary' : 'ghost'}
                        size="sm"
                        onClick={() => setEditing({ antibody_id: ab.id, antibody_name: ab.name, existing: rule })}
                      >
                        {isCustom ? 'Edit rule' : 'Customise'}
                      </Button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </Card>

      <RuleModal rule={editing} onClose={() => setEditing(null)} />
    </div>
  )
}
