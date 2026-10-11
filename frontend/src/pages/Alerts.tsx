// pages/Alerts.tsx

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import { AlertTriangle, Bell, CheckCheck, PackageCheck, RefreshCw, Shuffle, Timer } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useState } from 'react'
import { alertsApi } from '../api/client'
import { Badge, Button, Card, EmptyState, Spinner } from '../components/ui'
import type { Alert } from '../types'

const alertMeta: Record<string, { label: string; icon: React.FC<any>; variant: 'warning' | 'critical' | 'info' }> = {
  shortage:              { label: 'Shortage',          icon: AlertTriangle, variant: 'critical' },
  substitute_suggestion: { label: 'Substitute',        icon: Shuffle,       variant: 'warning' },
  expiry_warning:        { label: 'Expiry',            icon: Timer,         variant: 'warning' },
  cocktail_expiry:       { label: 'Cocktail expiry',   icon: Timer,         variant: 'warning' },
  shipment_verification: { label: 'Shipment change',   icon: PackageCheck,  variant: 'warning' },
  shipment_verification_overdue: { label: 'Verification overdue', icon: PackageCheck, variant: 'critical' },
}
const KNOWN_TYPES = new Set(Object.keys(alertMeta))

function AlertCard({ alert }: { alert: Alert }) {
  const qc = useQueryClient()
  const meta = alertMeta[alert.alert_type] ?? { label: alert.alert_type, icon: Bell, variant: 'info' as const }
  const Icon = meta.icon

  const ack = useMutation({
    mutationFn: () => alertsApi.acknowledge(alert.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['alerts'] })
    },
  })

  const isAcknowledged = !!alert.acknowledged_at

  return (
    <div className={`rounded-xl border p-4 space-y-2 transition-opacity ${isAcknowledged ? 'opacity-50' : ''} ${
      meta.variant === 'critical' ? 'border-red-200 bg-red-50' :
      meta.variant === 'warning'  ? 'border-amber-200 bg-amber-50' :
      'border-blue-200 bg-blue-50'
    }`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className={`mt-0.5 p-1.5 rounded-lg ${
            meta.variant === 'critical' ? 'bg-red-100 text-red-600' :
            meta.variant === 'warning'  ? 'bg-amber-100 text-amber-600' :
            'bg-blue-100 text-blue-600'
          }`}>
            <Icon className="w-3.5 h-3.5" />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-semibold text-slate-900">{alert.antibody_name}</span>
              <Badge variant={meta.variant === 'critical' ? 'critical' : 'warning'}>
                {meta.label}
              </Badge>
              {alert.days_remaining != null && (
                <span className="text-xs text-slate-500">{Math.round(alert.days_remaining)} days remaining</span>
              )}
            </div>
            <p className="text-sm text-slate-700 mt-0.5">{alert.message}</p>
          </div>
        </div>

        {!isAcknowledged && (
          <Button variant="secondary" size="sm" onClick={() => ack.mutate()} disabled={ack.isPending}>
            <CheckCheck className="w-3.5 h-3.5" />
            Acknowledge
          </Button>
        )}
      </div>

      <div className="flex items-center gap-3 text-xs text-slate-400 pl-9">
        <span>Raised {format(parseISO(alert.triggered_at), 'd MMM yyyy HH:mm')}</span>
        {isAcknowledged && alert.acknowledged_at && (
          <span>· Acknowledged {format(parseISO(alert.acknowledged_at), 'd MMM HH:mm')}</span>
        )}
      </div>
    </div>
  )
}

export default function AlertsPage() {
  const qc = useQueryClient()
  const [showAll, setShowAll] = useState(false)

  const { data: alerts = [], isLoading } = useQuery({
    queryKey: ['alerts', showAll ? 'all' : 'unread'],
    queryFn: () => alertsApi.list(!showAll),
    refetchInterval: 30_000,
  })

  const runCheck = useMutation({
    mutationFn: alertsApi.run,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  })

  const byType = (type: string) => alerts.filter((a) => a.alert_type === type)
  const shortage  = byType('shortage')
  const substitute = byType('substitute_suggestion')
  const expiry    = byType('expiry_warning')
  const cocktailExpiry = byType('cocktail_expiry')
  const shipmentQc = alerts.filter((a) => a.alert_type.startsWith('shipment_verification'))
  // Anything the page has no section for still has to be visible — the nav
  // badge counts every unacknowledged alert.
  const other = alerts.filter((a) => !KNOWN_TYPES.has(a.alert_type))

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Alerts</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {alerts.filter((a) => !a.acknowledged_at).length} unacknowledged
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={() => setShowAll((v) => !v)}>
            {showAll ? 'Show unread only' : 'Show all'}
          </Button>
          <Button variant="secondary" size="sm" onClick={() => runCheck.mutate()} disabled={runCheck.isPending}>
            <RefreshCw className={`w-3.5 h-3.5 ${runCheck.isPending ? 'animate-spin' : ''}`} />
            Run check
          </Button>
        </div>
      </div>

      {isLoading ? (
        <Spinner className="py-16" />
      ) : alerts.length === 0 ? (
        <Card>
          <EmptyState message={showAll ? "No alerts on record" : "No unacknowledged alerts — all clear"} />
        </Card>
      ) : (
        <div className="space-y-5">
          {shipmentQc.length > 0 && (
            <section>
              <div className="flex items-center justify-between mb-2.5">
                <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                  Shipment verification ({shipmentQc.length})
                </h2>
                <Link to="/shipment-qc" className="text-xs font-medium text-brand-700 hover:underline">
                  Go to Shipment QC →
                </Link>
              </div>
              <p className="text-xs text-slate-400 mb-2">
                Acknowledging only dismisses the notification. The verification stays open until it is signed off with evidence.
              </p>
              <div className="space-y-2">
                {shipmentQc.map((a) => <AlertCard key={a.id} alert={a} />)}
              </div>
            </section>
          )}

          {shortage.length > 0 && (
            <section>
              <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2.5">
                Shortage alerts ({shortage.length})
              </h2>
              <div className="space-y-2">
                {shortage.map((a) => <AlertCard key={a.id} alert={a} />)}
              </div>
            </section>
          )}

          {substitute.length > 0 && (
            <section>
              <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2.5">
                Substitute suggestions ({substitute.length})
              </h2>
              <div className="space-y-2">
                {substitute.map((a) => <AlertCard key={a.id} alert={a} />)}
              </div>
            </section>
          )}

          {expiry.length > 0 && (
            <section>
              <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2.5">
                Expiry warnings ({expiry.length})
              </h2>
              <div className="space-y-2">
                {expiry.map((a) => <AlertCard key={a.id} alert={a} />)}
              </div>
            </section>
          )}

          {cocktailExpiry.length > 0 && (
            <section>
              <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2.5">
                Cocktail expiry ({cocktailExpiry.length})
              </h2>
              <div className="space-y-2">
                {cocktailExpiry.map((a) => <AlertCard key={a.id} alert={a} />)}
              </div>
            </section>
          )}

          {other.length > 0 && (
            <section>
              <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2.5">
                Other ({other.length})
              </h2>
              <div className="space-y-2">
                {other.map((a) => <AlertCard key={a.id} alert={a} />)}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  )
}
