// pages/admin/LabSettings.tsx

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, useEffect } from 'react'
import { labSettingsApi } from '../../api/client'
import { Button, Card, Input, Spinner } from '../../components/ui'

// ── Lab Identity ──────────────────────────────────────────────────────────

function LabIdentitySection() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['lab-settings'], queryFn: labSettingsApi.get })

  const [labName, setLabName] = useState('')
  const [labSubtitle, setLabSubtitle] = useState('')
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (data) {
      setLabName(data.lab_name ?? '')
      setLabSubtitle(data.lab_subtitle ?? '')
    }
  }, [data])

  const mut = useMutation({
    mutationFn: () => labSettingsApi.update({ lab_name: labName, lab_subtitle: labSubtitle }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['lab-settings'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    },
  })

  if (isLoading) return <Spinner />

  return (
    <Card>
      <h2 className="text-sm font-semibold text-slate-900 mb-1">Lab Identity</h2>
      <p className="text-xs text-slate-400 mb-4">
        Displayed prominently in the sidebar for all users. Helps staff confirm they are
        connected to the correct lab's system.
      </p>

      <div className="space-y-3 max-w-sm">
        <Input
          label="Lab name"
          value={labName}
          onChange={e => { setLabName(e.target.value); setSaved(false) }}
          placeholder="e.g. City Hospital Flow Cytometry Laboratory"
        />
        <Input
          label="Subtitle (optional)"
          value={labSubtitle}
          onChange={e => { setLabSubtitle(e.target.value); setSaved(false) }}
          placeholder="e.g. Haematopathology Unit"
        />

        {/* Live preview */}
        {labName && (
          <div className="mt-2 bg-slate-800 rounded-xl p-3 max-w-[200px]">
            <p className="text-xs font-bold text-white leading-none">FlowJAI</p>
            <p className="text-xs text-white/40 leading-none mt-0.5">Inventory Manager</p>
            <div className="mt-2 bg-white/10 rounded-lg px-2 py-1.5">
              <p className="text-xs font-semibold text-white leading-tight truncate">{labName}</p>
              {labSubtitle && (
                <p className="text-xs text-white/50 leading-tight truncate mt-0.5">{labSubtitle}</p>
              )}
            </div>
          </div>
        )}

        <div className="flex items-center gap-3 pt-1">
          <Button onClick={() => mut.mutate()} disabled={mut.isPending}>
            {mut.isPending ? 'Saving...' : 'Save'}
          </Button>
          {saved && <span className="text-sm text-emerald-600 font-medium">Saved</span>}
        </div>
      </div>
    </Card>
  )
}

// ── Global Alert Defaults ─────────────────────────────────────────────────

function GlobalAlertDefaultsSection() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['global-alert-defaults'],
    queryFn: labSettingsApi.getAlertDefaults,
  })

  const [form, setForm] = useState({ lead_time_days: '35', alert_threshold_days: '42', safety_stock_ul: '0' })
  const [saved, setSaved] = useState(false)
  const set = (k: string, v: string) => { setForm(f => ({ ...f, [k]: v })); setSaved(false) }

  useEffect(() => {
    if (data) {
      setForm({
        lead_time_days: String(data.lead_time_days),
        alert_threshold_days: String(data.alert_threshold_days),
        safety_stock_ul: String(data.safety_stock_ul),
      })
    }
  }, [data])

  const mut = useMutation({
    mutationFn: () => labSettingsApi.updateAlertDefaults({
      lead_time_days: Number(form.lead_time_days),
      alert_threshold_days: Number(form.alert_threshold_days),
      safety_stock_ul: Number(form.safety_stock_ul),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['global-alert-defaults'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    },
  })

  if (isLoading) return <Spinner />

  return (
    <Card>
      <h2 className="text-sm font-semibold text-slate-900 mb-1">System-wide Alert Defaults</h2>
      <p className="text-xs text-slate-400 mb-4">
        Applied to all antibodies that do not have a custom rule set in Alert Rules.
        Changes take effect on the next alert check run.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 max-w-lg">
        <div>
          <Input
            label="Lead time (days)"
            type="number" min="1"
            value={form.lead_time_days}
            onChange={e => set('lead_time_days', e.target.value)}
          />
          <p className="text-xs text-slate-400 mt-1">Expected order-to-delivery time</p>
        </div>
        <div>
          <Input
            label="Alert threshold (days)"
            type="number" min="1"
            value={form.alert_threshold_days}
            onChange={e => set('alert_threshold_days', e.target.value)}
          />
          <p className="text-xs text-slate-400 mt-1">Raise alert when below this</p>
        </div>
        <div>
          <Input
            label="Safety stock (µl)"
            type="number" min="0" step="10"
            value={form.safety_stock_ul}
            onChange={e => set('safety_stock_ul', e.target.value)}
          />
          <p className="text-xs text-slate-400 mt-1">Reserve to keep at all times</p>
        </div>
      </div>

      <div className="flex items-center gap-3 mt-4">
        <Button onClick={() => mut.mutate()} disabled={mut.isPending}>
          {mut.isPending ? 'Saving...' : 'Save defaults'}
        </Button>
        {saved && <span className="text-sm text-emerald-600 font-medium">Saved</span>}
      </div>
    </Card>
  )
}

// ── Network Access ────────────────────────────────────────────────────────

function NetworkAccessSection() {
  const origin = window.location.origin
  const isLocalhost = origin.includes('localhost') || origin.includes('127.0.0.1')

  return (
    <Card>
      <h2 className="text-sm font-semibold text-slate-900 mb-1">Network Access</h2>
      <p className="text-xs text-slate-400 mb-4">
        Allow technologists on the same network to access this app without installing anything.
      </p>

      <div className="space-y-3 text-sm">
        {isLocalhost ? (
          <>
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-amber-800 text-xs">
              You are currently accessing from localhost. To find the network address:
            </div>
            <div className="bg-slate-50 rounded-lg p-3 space-y-2 text-xs font-mono">
              <p className="font-sans font-medium text-slate-700 mb-1">On Windows — run in PowerShell:</p>
              <p className="text-slate-600">{'(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.IPAddress -notlike "127*"}).IPAddress'}</p>
              <p className="font-sans font-medium text-slate-700 mt-3 mb-1">On Mac — run in Terminal:</p>
              <p className="text-slate-600">ipconfig getifaddr en0</p>
            </div>
            <p className="text-xs text-slate-500">
              Share the result as <span className="font-mono bg-slate-100 px-1 rounded">http://[that-ip]:8000</span> with your technologists.
              They can bookmark it in their browser — nothing to install on their machines.
            </p>
          </>
        ) : (
          <>
            <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3">
              <p className="text-xs text-emerald-800 font-medium">Network access is active</p>
              <p className="text-xs text-emerald-700 mt-0.5">Share this URL with technologists on your network:</p>
              <p className="text-sm font-mono font-bold text-emerald-900 mt-1">{origin}</p>
            </div>
            <p className="text-xs text-slate-500">
              Any device on the same network can access the app by visiting this URL.
              No installation required on their end.
            </p>
          </>
        )}

        <div className="bg-blue-50 border border-blue-100 rounded-lg p-3 text-xs text-blue-800 space-y-1">
          <p className="font-medium">If technologists cannot connect:</p>
          <p>· Make sure the app was started for network use (Start flowjAI.bat or launch.bat, or the .exe run once with --lan)</p>
          <p>· Check that Windows Firewall allows port 8000 inbound on the host machine (local subnet)</p>
          <p>· Confirm all devices are on the same Wi-Fi or LAN network</p>
          <p>· The host machine must stay on (and not sleep) while the app is in use</p>
        </div>
      </div>
    </Card>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────

export default function LabSettingsPage() {
  return (
    <div className="p-6 space-y-5 max-w-3xl">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Lab Settings</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          System-wide configuration for this deployment
        </p>
      </div>

      <LabIdentitySection />
      <GlobalAlertDefaultsSection />
      <NetworkAccessSection />
    </div>
  )
}
