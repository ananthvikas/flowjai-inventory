// pages/admin/Validation.tsx

import { useQuery } from '@tanstack/react-query'
import { Download } from 'lucide-react'
import { validationApi } from '../../api/client'
import { Button, Card, EmptyState, Spinner, StatCard } from '../../components/ui'
import { TrendingDown, CheckCircle, AlertTriangle, BarChart2 } from 'lucide-react'

export default function ValidationPage() {
  const { data: report, isLoading } = useQuery({
    queryKey: ['validation-report'],
    queryFn: validationApi.report,
  })

  if (isLoading) return <Spinner className="py-24" />

  const summary = report?.accuracy_summary
  const verRows = report?.verification_accuracy ?? []
  const usageRows = report?.usage_summary ?? []
  const alertRows = report?.alert_effectiveness ?? []

  return (
    <div className="p-6 space-y-6 max-w-5xl">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Validation Report</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Agreement data for publication and audit · {report?.tracking_period_days ?? 0} days tracked
            · Generated {report?.generated_date}
          </p>
        </div>
        <div className="flex gap-2 flex-wrap justify-end">
          <Button variant="secondary" size="sm" onClick={() => validationApi.downloadVerification()}>
            <Download className="w-3.5 h-3.5" /> Verification accuracy
          </Button>
          <Button variant="secondary" size="sm" onClick={() => validationApi.downloadAccuracySummary()}>
            <Download className="w-3.5 h-3.5" /> Agreement stats (publication)
          </Button>
          <Button variant="secondary" size="sm" onClick={() => validationApi.downloadUsage()}>
            <Download className="w-3.5 h-3.5" /> Usage summary
          </Button>
          <Button variant="secondary" size="sm" onClick={() => validationApi.downloadAlerts()}>
            <Download className="w-3.5 h-3.5" /> Alert effectiveness
          </Button>
        </div>
      </div>

      {/* ── Accuracy summary cards ── */}
      <section>
        <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">
          Volume tracking agreement
        </h2>
        <p className="text-xs text-slate-400 mb-3 max-w-3xl">
          Agreement between the system's modelled estimate and the physical measurement.
          Physical measurement (pipette or balance) is itself an estimate with its own
          resolution, so this is a method-agreement analysis (Bland-Altman), not accuracy
          against a gold standard. Report it as such.
        </p>
        {summary && summary.total_verifications > 0 ? (
          <>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <StatCard
                label="Verifications recorded"
                value={summary.total_verifications}
                icon={<BarChart2 className="w-5 h-5" />}
                color="blue"
              />
              <StatCard
                label="Mean absolute error"
                value={`${summary.mean_absolute_error_ul.toFixed(1)} µl`}
                icon={<TrendingDown className="w-5 h-5" />}
                color={summary.mean_absolute_error_ul < 10 ? 'green' : 'amber'}
              />
              <StatCard
                label="Within ±1 µl"
                value={summary.exact_count}
                sub={`of ${summary.total_verifications} events`}
                icon={<CheckCircle className="w-5 h-5" />}
                color="green"
              />
              <StatCard
                label="Mean % error"
                value={summary.mean_absolute_pct_error != null
                  ? `${summary.mean_absolute_pct_error.toFixed(1)}%`
                  : '—'}
                icon={<AlertTriangle className="w-5 h-5" />}
                color={
                  summary.mean_absolute_pct_error == null ? 'blue' :
                  summary.mean_absolute_pct_error < 5 ? 'green' : 'amber'
                }
              />
            </div>

            <div className="mt-3 flex gap-4 text-xs text-slate-500 flex-wrap">
              <span>System overestimated: <strong className="text-slate-700">{summary.overestimate_count}</strong></span>
              <span>System underestimated: <strong className="text-slate-700">{summary.underestimate_count}</strong></span>
              <span>Median delta: <strong className="text-slate-700">{summary.median_delta_ul.toFixed(1)} µl</strong></span>
            </div>

            {/* ── Publication statistics ── */}
            <div className="mt-4 grid grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-2 text-xs bg-slate-50 rounded-lg p-4">
              <div>
                <p className="text-slate-400">Independent cycles</p>
                <p className="text-slate-800 font-semibold tabular-nums">{summary.distinct_cycles}</p>
              </div>
              <div>
                <p className="text-slate-400">Distinct lots</p>
                <p className="text-slate-800 font-semibold tabular-nums">{summary.distinct_lots}</p>
              </div>
              <div>
                <p className="text-slate-400">Mean signed bias</p>
                <p className="text-slate-800 font-semibold tabular-nums">{summary.mean_signed_bias_ul.toFixed(2)} µl</p>
                <p className="text-slate-400 text-[10px]">est − measured; ~0 = random</p>
              </div>
              <div>
                <p className="text-slate-400">SD of differences</p>
                <p className="text-slate-800 font-semibold tabular-nums">{summary.sd_of_differences_ul.toFixed(2)} µl</p>
              </div>
              <div>
                <p className="text-slate-400">Bland-Altman LoA</p>
                <p className="text-slate-800 font-semibold tabular-nums">
                  {summary.bland_altman_lower_loa_ul.toFixed(1)} to {summary.bland_altman_upper_loa_ul.toFixed(1)} µl
                </p>
              </div>
              <div>
                <p className="text-slate-400">Delta range</p>
                <p className="text-slate-800 font-semibold tabular-nums">
                  {summary.min_delta_ul.toFixed(1)} to {summary.max_delta_ul.toFixed(1)} µl
                </p>
              </div>
            </div>

            {summary.interpretation && (
              <div className={`mt-3 rounded-lg p-3 text-xs leading-relaxed ${
                summary.distinct_cycles <= 1 ? 'bg-amber-50 text-amber-800 border border-amber-200'
                : summary.distinct_cycles < 4 ? 'bg-blue-50 text-blue-800 border border-blue-200'
                : 'bg-emerald-50 text-emerald-800 border border-emerald-200'
              }`}>
                <span className="font-semibold">Publication readiness: </span>{summary.interpretation}
              </div>
            )}
          </>
        ) : (
          <Card>
            <EmptyState message="No verification events recorded yet. Use the Verify button on stock lots to start building agreement data." />
          </Card>
        )}
      </section>

      {/* ── Verification events table ── */}
      {verRows.length > 0 && (
        <section>
          <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
            Individual verification events ({verRows.length})
          </h2>
          <Card padding={false}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-100">
                    {['Date', 'Antibody', 'Lot', 'System estimate', 'Measured', 'Delta', '% error', 'Verified by'].map(h => (
                      <th key={h} className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {verRows.map((r: any, i: number) => (
                    <tr key={i} className="hover:bg-slate-50">
                      <td className="px-4 py-2.5 text-slate-500 whitespace-nowrap">{r.verification_date}</td>
                      <td className="px-4 py-2.5 font-medium text-slate-800">{r.antibody_name}</td>
                      <td className="px-4 py-2.5 text-slate-400 font-mono text-xs">{r.lot_no}</td>
                      <td className="px-4 py-2.5 tabular-nums">{r.system_estimate_ul.toFixed(1)} µl</td>
                      <td className="px-4 py-2.5 tabular-nums font-medium">{r.measured_volume_ul.toFixed(1)} µl</td>
                      <td className={`px-4 py-2.5 tabular-nums font-medium ${Math.abs(r.delta_ul) > 20 ? 'text-red-600' : Math.abs(r.delta_ul) > 5 ? 'text-amber-600' : 'text-emerald-600'}`}>
                        {r.delta_ul > 0 ? '+' : ''}{r.delta_ul.toFixed(1)} µl
                      </td>
                      <td className="px-4 py-2.5 tabular-nums text-slate-500">
                        {r.delta_pct != null ? `${r.delta_pct > 0 ? '+' : ''}${r.delta_pct.toFixed(1)}%` : '—'}
                      </td>
                      <td className="px-4 py-2.5 text-slate-400">{r.verified_by}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </section>
      )}

      {/* ── Usage summary ── */}
      {usageRows.length > 0 && (
        <section>
          <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
            Antibody usage summary
          </h2>
          <Card padding={false}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-100">
                    {['Antibody', 'Vendor', 'Fluor', 'Total consumed', 'Avg/day', 'Peak/day', 'Lots exhausted'].map(h => (
                      <th key={h} className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {usageRows.map((r: any, i: number) => (
                    <tr key={i} className="hover:bg-slate-50">
                      <td className="px-4 py-2.5 font-medium text-slate-800">{r.antibody_name}</td>
                      <td className="px-4 py-2.5 text-slate-400 text-xs">{r.vendor ?? '—'}</td>
                      <td className="px-4 py-2.5 text-slate-400 text-xs">{r.fluorochrome ?? '—'}</td>
                      <td className="px-4 py-2.5 tabular-nums">{r.total_consumed_ul.toFixed(0)} µl</td>
                      <td className="px-4 py-2.5 tabular-nums">{r.avg_daily_ul.toFixed(1)} µl</td>
                      <td className="px-4 py-2.5 tabular-nums">{r.peak_daily_ul.toFixed(0)} µl</td>
                      <td className="px-4 py-2.5 tabular-nums">{r.lots_exhausted}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </section>
      )}

      {/* ── Alert effectiveness ── */}
      {alertRows.length > 0 && (
        <section>
          <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
            Alert effectiveness ({alertRows.length} shortage alerts)
          </h2>
          <Card padding={false}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-100">
                    {['Antibody', 'Alert date', 'Days remaining', 'Order within 14 days', 'Acknowledged'].map(h => (
                      <th key={h} className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {alertRows.map((r: any, i: number) => (
                    <tr key={i} className="hover:bg-slate-50">
                      <td className="px-4 py-2.5 font-medium text-slate-800">{r.antibody_name}</td>
                      <td className="px-4 py-2.5 text-slate-500">{r.alert_date}</td>
                      <td className="px-4 py-2.5 tabular-nums">
                        {r.days_remaining_at_alert != null ? `${Math.round(r.days_remaining_at_alert)}d` : '—'}
                      </td>
                      <td className="px-4 py-2.5">
                        <span className={r.order_placed_within_14_days ? 'text-emerald-600 font-medium' : 'text-red-500'}>
                          {r.order_placed_within_14_days ? '✓ Yes' : '✗ No'}
                        </span>
                      </td>
                      <td className="px-4 py-2.5">
                        <span className={r.acknowledged ? 'text-slate-500' : 'text-amber-600'}>
                          {r.acknowledged ? 'Yes' : 'Pending'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </section>
      )}
    </div>
  )
}
