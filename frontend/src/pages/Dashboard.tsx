// pages/Dashboard.tsx

import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { format, parseISO } from 'date-fns'
import { AlertTriangle, Bell, CalendarX2, FlaskConical, Package, TrendingDown } from 'lucide-react'
import { alertsApi, cocktailsApi, forecastApi, stockApi } from '../api/client'
import { Badge, Card, EmptyState, Spinner, StatCard } from '../components/ui'
import type { Forecast, InventoryRow, StockSummary } from '../types'

// Compute status from days_remaining
function statusFromDays(days: number | null): InventoryRow['status'] {
  if (days === null) return 'unknown'
  if (days <= 14)   return 'critical'
  if (days <= 42)   return 'warning'
  return 'ok'
}

function statusLabel(s: InventoryRow['status']) {
  return { ok: 'OK', warning: 'Low', critical: 'Critical', unknown: 'No data' }[s]
}

// ── Forecast sparkline chart for a single antibody ─────────────────────────

function ForecastChart({ forecast }: { forecast: Forecast }) {
  const today = format(new Date(), 'yyyy-MM-dd')

  const historicPoints = [
    { date: today, stock_ul: forecast.current_stock_ul },
  ]

  // Build cumulative-depletion series from forecast
  let remaining = forecast.current_stock_ul
  const depletionSeries = forecast.forecast_series.map((p) => {
    remaining = Math.max(0, remaining - p.predicted_ul)
    return { date: p.date, stock_ul: Math.round(remaining) }
  })

  const series = [...historicPoints, ...depletionSeries]
  const depletionDate = forecast.depletion_date

  return (
    <ResponsiveContainer width="100%" height={180}>
      <AreaChart data={series} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="stockGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#3b82f6" stopOpacity={0.25} />
            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 10, fill: '#94a3b8' }}
          tickFormatter={(d) => format(parseISO(d), 'dd MMM')}
          interval="preserveStartEnd"
        />
        <YAxis
          tick={{ fontSize: 10, fill: '#94a3b8' }}
          tickFormatter={(v) => `${v}µl`}
          width={48}
        />
        <Tooltip
          formatter={(v: number) => [`${v} µl`, 'Remaining stock']}
          labelFormatter={(d) => format(parseISO(d as string), 'dd MMM yyyy')}
          contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e2e8f0' }}
        />
        {depletionDate && (
          <ReferenceLine
            x={depletionDate}
            stroke="#ef4444"
            strokeDasharray="4 2"
            label={{ value: 'Depletion', position: 'insideTopRight', fontSize: 10, fill: '#ef4444' }}
          />
        )}
        <Area
          type="monotone"
          dataKey="stock_ul"
          stroke="#3b82f6"
          strokeWidth={2}
          fill="url(#stockGrad)"
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}

// ── Main dashboard ─────────────────────────────────────────────────────────

export default function Dashboard() {
  const [selectedAntibodyId, setSelectedAntibodyId] = useState<number | null>(null)

  const { data: summaries = [], isLoading: sumLoading } = useQuery({
    queryKey: ['stock-summary'],
    queryFn: stockApi.summary,
    refetchInterval: 120_000,
  })

  const { data: forecasts = [], isLoading: fcLoading } = useQuery({
    queryKey: ['forecast-all'],
    queryFn: forecastApi.all,
    refetchInterval: 120_000,
  })

  const { data: alerts = [] } = useQuery({
    queryKey: ['alerts', 'unread'],
    queryFn: () => alertsApi.list(true),
  })

  const { data: cocktails = [] } = useQuery({
    queryKey: ['cocktails', false],
    queryFn: () => cocktailsApi.list(undefined, true),
    refetchInterval: 120_000,
  })

  // Merge stock summary + forecast into InventoryRow[]
  const rows: InventoryRow[] = useMemo(() => {
    const fcMap = new Map<number, Forecast>(forecasts.map((f) => [f.antibody_id, f]))
    return summaries
      .map((s: StockSummary) => {
        const fc = fcMap.get(s.antibody_id)
        const days = fc?.days_remaining ?? null
        return {
          antibody_id:   s.antibody_id,
          antibody_name: s.antibody_name,
          fluorochrome:  s.fluorochrome,
          vendor:        s.vendor,
          total_stock_ul: s.total_stock_ul,
          days_remaining: days != null ? Math.round(days) : null,
          depletion_date: fc?.depletion_date ?? null,
          avg_daily_ul:   fc?.avg_daily_ul ?? 0,
          forecast_method: fc?.method ?? 'unknown',
          active_lot_count: s.active_lot_count,
          oldest_expiry:  s.oldest_expiry,
          status:         statusFromDays(days),
        }
      })
      .sort((a, b) => (a.days_remaining ?? 9999) - (b.days_remaining ?? 9999))
  }, [summaries, forecasts])

  const critical = rows.filter((r) => r.status === 'critical').length
  const warning  = rows.filter((r) => r.status === 'warning').length
  const [showAllStock, setShowAllStock] = useState(false)
  const visibleRows = showAllStock ? rows : rows.filter(r => r.status !== 'ok')
  const selectedForecast = forecasts.find((f) => f.antibody_id === selectedAntibodyId)
  const selectedRow      = rows.find((r) => r.antibody_id === selectedAntibodyId)

  if (sumLoading || fcLoading) {
    return <Spinner className="h-64" />
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-slate-900">Dashboard</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          {format(new Date(), 'EEEE, d MMMM yyyy')}
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <StatCard
          label="Antibodies tracked"
          value={rows.length}
          icon={<Package className="w-5 h-5" />}
          color="blue"
        />
        <StatCard
          label="Active cocktails"
          value={cocktails.length}
          sub="batches with tests remaining"
          icon={<FlaskConical className="w-5 h-5" />}
          color={cocktails.length > 0 ? 'blue' : 'green'}
        />
        <StatCard
          label="Critical stock"
          value={critical}
          sub="≤14 days remaining"
          icon={<TrendingDown className="w-5 h-5" />}
          color={critical > 0 ? 'red' : 'green'}
        />
        <StatCard
          label="Low stock"
          value={warning}
          sub="15–42 days remaining"
          icon={<AlertTriangle className="w-5 h-5" />}
          color={warning > 0 ? 'amber' : 'green'}
        />
        <StatCard
          label="Active alerts"
          value={alerts.length}
          icon={<Bell className="w-5 h-5" />}
          color={alerts.length > 0 ? 'red' : 'green'}
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* ── Inventory table ── */}
        <Card padding={false} className="xl:col-span-2 overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-slate-900">Stock Status</h2>
              <p className="text-xs text-slate-400">Click a row to see forecast</p>
            </div>
            <button
              onClick={() => setShowAllStock(v => !v)}
              className="text-xs text-blue-600 hover:text-blue-800 font-medium"
            >
              {showAllStock ? `Show low stock only (${critical + warning})` : `Show all (${rows.length})`}
            </button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50">
                  <th className="text-left px-5 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Antibody</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Fluor</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Vendor</th>
                  <th className="text-right px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Stock</th>
                  <th className="text-right px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Days left</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {visibleRows.length === 0 && (
                  <tr>
                    <td colSpan={6}>
                      <EmptyState message={rows.length === 0 ? "No antibody stock data yet" : "All antibodies are well stocked ✓"} />
                    </td>
                  </tr>
                )}
                {visibleRows.map((row) => (
                  <tr
                    key={row.antibody_id}
                    onClick={() => setSelectedAntibodyId(
                      row.antibody_id === selectedAntibodyId ? null : row.antibody_id
                    )}
                    className={`cursor-pointer transition-colors hover:bg-slate-50
                      ${selectedAntibodyId === row.antibody_id ? 'bg-blue-50' : ''}`}
                  >
                    <td className="px-5 py-3 font-medium text-slate-800">{row.antibody_name}</td>
                    <td className="px-4 py-3 text-slate-500">{row.fluorochrome ?? '—'}</td>
                    <td className="px-4 py-3 text-slate-400 text-xs">{row.vendor ?? '—'}</td>
                    <td className="px-4 py-3 text-right text-slate-700 tabular-nums">
                      {row.total_stock_ul.toFixed(0)} µl
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {row.days_remaining !== null ? (
                        <span className={
                          row.status === 'critical' ? 'text-red-600 font-semibold' :
                          row.status === 'warning'  ? 'text-amber-600 font-medium' :
                          'text-slate-700'
                        }>
                          {row.days_remaining}
                        </span>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant={row.status}>{statusLabel(row.status)}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        {/* ── Forecast panel ── */}
        <Card className="xl:col-span-1">
          {selectedForecast && selectedRow ? (
            <div className="space-y-4">
              <div>
                <h2 className="text-sm font-semibold text-slate-900">
                  {selectedRow.antibody_name}
                  {selectedRow.fluorochrome && (
                    <span className="text-slate-400 font-normal ml-1.5">· {selectedRow.fluorochrome}</span>
                  )}
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">Stock depletion forecast</p>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="bg-slate-50 rounded-lg p-3">
                  <p className="text-xs text-slate-500">Current stock</p>
                  <p className="text-lg font-bold text-slate-900">
                    {selectedRow.total_stock_ul.toFixed(0)} µl
                  </p>
                </div>
                <div className={`rounded-lg p-3 ${
                  selectedRow.status === 'critical' ? 'bg-red-50' :
                  selectedRow.status === 'warning'  ? 'bg-amber-50' : 'bg-emerald-50'
                }`}>
                  <p className="text-xs text-slate-500">Days remaining</p>
                  <p className="text-lg font-bold text-slate-900">
                    {selectedRow.days_remaining ?? '∞'}
                  </p>
                </div>
              </div>

              <div className="space-y-1.5 text-xs">
                <div className="flex justify-between">
                  <span className="text-slate-500">Avg daily use</span>
                  <span className="font-medium">{selectedRow.avg_daily_ul.toFixed(1)} µl</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Projected depletion</span>
                  <span className="font-medium">
                    {selectedRow.depletion_date
                      ? format(parseISO(selectedRow.depletion_date), 'd MMM yyyy')
                      : '—'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Forecast model</span>
                  <span className="font-medium capitalize">{selectedRow.forecast_method.replace('_', ' ')}</span>
                </div>
              </div>

              <ForecastChart forecast={selectedForecast} />
            </div>
          ) : (
            <div className="h-full flex flex-col items-center justify-center py-10 text-slate-400">
            <FlaskConical className="w-10 h-10 mb-3 opacity-30" />
              <p className="text-sm text-center">
                Select an antibody from the table<br />to view its depletion forecast
              </p>
            </div>
          )}
        </Card>
      </div>

      {/* ── Cocktail Status ── */}
      {cocktails.length > 0 && (
        <Card padding={false}>
          <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-900">Cocktail Status</h2>
            <p className="text-xs text-slate-400">{cocktails.length} active batch{cocktails.length !== 1 ? 'es' : ''}</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50">
                  <th className="text-left px-5 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Cocktail</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Panel</th>
                  <th className="text-right px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Remaining µl</th>
                  <th className="text-right px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Expiry</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {cocktails
                  .slice()
                  .sort((a: any, b: any) => {
                    if (!a.expiry_date) return 1
                    if (!b.expiry_date) return -1
                    return a.expiry_date.localeCompare(b.expiry_date)
                  })
                  .map((c: any) => {
                    const daysToExpiry = c.expiry_date
                      ? Math.round((new Date(c.expiry_date).getTime() - Date.now()) / 86400000)
                      : null
                    const expired = daysToExpiry !== null && daysToExpiry < 0
                    const expiringSoon = daysToExpiry !== null && daysToExpiry <= 3 && !expired
                    return (
                      <tr key={c.id} className={expired ? 'bg-red-50' : expiringSoon ? 'bg-amber-50' : ''}>
                        <td className="px-5 py-3 font-medium text-slate-800">{c.name}</td>
                        <td className="px-4 py-3 text-slate-500 text-xs">{c.panel_name ?? '—'}</td>
                        <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                          {c.remaining_volume_ul != null ? `${c.remaining_volume_ul.toFixed(0)} µl` : '—'}
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums">
                          {c.expiry_date ? (
                            <span className={expired ? 'text-red-600 font-semibold' : expiringSoon ? 'text-amber-600 font-medium' : 'text-slate-700'}>
                              {expired
                                ? `Expired ${Math.abs(daysToExpiry!)}d ago`
                                : daysToExpiry === 0 ? 'Expires today'
                                : `${daysToExpiry}d`}
                            </span>
                          ) : '—'}
                        </td>
                        <td className="px-4 py-3">
                          {expired
                            ? <Badge variant="critical"><CalendarX2 className="w-3 h-3 inline mr-1" />Expired</Badge>
                            : expiringSoon
                            ? <Badge variant="warning">Expiring soon</Badge>
                            : <Badge variant="ok">Active</Badge>}
                        </td>
                      </tr>
                    )
                  })}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}
