
import { Card } from '../components/ui'
import { Microscope } from 'lucide-react'
import { BUILD_DATE, VERSION, VERSION_HISTORY } from '../version'


export default function AboutPage() {
  return (
    <div className="p-6 space-y-5 max-w-2xl">
      <div>
        <h1 className="text-xl font-bold text-slate-900">About</h1>
        <p className="text-sm text-slate-500 mt-0.5">FlowJAI Inventory Manager</p>
      </div>

      <Card>
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 rounded-2xl bg-brand-600 flex items-center justify-center shrink-0 shadow">
            <Microscope className="w-7 h-7 text-white" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-900">FlowJAI Inventory Manager</h2>
            <p className="text-sm text-slate-500">Version {VERSION} &nbsp;·&nbsp; {BUILD_DATE}</p>
          </div>
        </div>
        <div className="mt-5 text-sm text-slate-600 space-y-2 leading-relaxed">
          <p>
            FlowJAI Inventory Manager is a self-hosted reagent management system for clinical
            and research flow cytometry laboratories. It tracks antibodies from the stockroom
            (unopened vials) through to floor stock (open vials in use), with per-panel volume
            mapping, FIFO lot deduction, cocktail batch tracking, and moving-average depletion
            forecasting that accounts for both open and stored stock.
          </p>
          <p>Runs entirely within a laboratory network. No cloud dependency, no subscription,
            no data leaving the institution.</p>
        </div>
      </Card>

      <Card>
        <h3 className="text-sm font-semibold text-slate-900 mb-3">Scope</h3>
        <div className="space-y-2 text-sm text-slate-600">
          {[
            [true,  'Store stock — track unopened vials in the stockroom'],
            [true,  'Floor stock — open vials currently in use, with FIFO lot deduction'],
            [true,  'Per-panel antibody volume mapping; searchable antibody picker'],
            [true,  'Pre-mixed cocktail tracking with pre-flight stock warnings'],
            [true,  'Cocktail preparation worksheets (printable) and dated summary export'],
            [true,  'Log tests from a panel, a prepared cocktail, or ad hoc antibody selection'],
            [true,  'Depletion forecasting (moving average by default; Holt exponential smoothing optional) including store stock'],
            [true,  'Shipment-to-shipment QC verification with evidence files and audit log'],
            [true,  'Worklist with cocktail reservation, traceability, sample comments and TAT; bench station for tablets'],
            [true,  'Standard vial volume per catalogue number, with starting-volume checks'],
            [true,  'Shortage, expiry, and substitute alerts'],
            [true,  'Bulk receive, CSV exports, and a stores-facing stock report'],
            [true,  'Validation export for accuracy reporting and publication'],
            [false, 'Multi-site PostgreSQL — planned'],
          ].map(([done, text]) => (
            <div key={String(text)} className="flex gap-2">
              <span className={done ? 'text-emerald-500 shrink-0' : 'text-slate-300 shrink-0'}>
                {done ? '✓' : '○'}
              </span>
              <span className={done ? '' : 'text-slate-400'}>{String(text)}</span>
            </div>
          ))}
        </div>
      </Card>

      <Card>
        <h3 className="text-sm font-semibold text-slate-900 mb-3">Built with</h3>
        <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-sm text-slate-600">
          {[
            ['Backend', 'Python · FastAPI · SQLModel'],
            ['Database', 'SQLite'],
            ['Forecasting', 'Moving average · optional Holt ETS (pure NumPy)'],
            ['Frontend', 'React · TypeScript · Tailwind CSS'],
            ['Charts', 'Recharts'],
            ['Deployment', 'Windows packaged app · Python (Windows, macOS, Linux)'],
          ].map(([label, value]) => (
            <div key={label} className="flex gap-2">
              <span className="text-slate-400 shrink-0 w-24">{label}</span>
              <span>{value}</span>
            </div>
          ))}
        </div>
      </Card>

      <Card>
        <h3 className="text-sm font-semibold text-slate-900 mb-3">Acknowledgements</h3>
        <div className="text-sm text-slate-600 space-y-2 leading-relaxed">
          <p>
            Designed and developed by <span className="font-medium text-slate-800">Ananthvikas Jayaram</span>.
            Design inputs, clinical requirements and validation supported by{' '}
            <span className="font-medium text-slate-800">Sriram Sujay Prasad</span> and{' '}
            <span className="font-medium text-slate-800">Sujay Ramaprasad</span>.
            Built to solve a real reagent management problem in multi-panel flow cytometry.
          </p>
          <p>Open source under MIT licence. Adaptations for other laboratory settings are welcome.</p>
        </div>
      </Card>

      <Card>
        <h3 className="text-sm font-semibold text-slate-900 mb-3">Help and feedback</h3>
        <div className="text-sm text-slate-600 space-y-2 leading-relaxed">
          <p>
            Questions, problems or suggestions: email{' '}
            <a href="mailto:feedback.flowjai@gmail.com" className="font-medium text-brand-700 hover:underline">feedback.flowjai@gmail.com</a>{' '}
            or open an issue at{' '}
            <a href="https://github.com/ananthvikas/flowjai-inventory/issues" target="_blank" rel="noreferrer"
              className="font-medium text-brand-700 hover:underline">github.com/ananthvikas/flowjai-inventory</a>.
          </p>
          <p>
            <span className="font-medium text-slate-800">Using flowjAI in your laboratory?</span> A short email saying so
            helps the project — the app itself never reports anything back.
          </p>
          <p className="text-xs text-slate-500">
            Never send your database, patient identifiers or lab IDs. Include the version number shown above.
          </p>
        </div>
      </Card>

      <Card>
        <h3 className="text-sm font-semibold text-slate-900 mb-3">Version history</h3>
        <div className="space-y-4">
          {VERSION_HISTORY.map(v => (
            <div key={v.version} className="flex gap-4">
              <div className="shrink-0 text-right w-14">
                <p className="text-sm font-semibold text-slate-800">{v.version}</p>
                <p className="text-xs text-slate-400">{v.date}</p>
              </div>
              <div className="border-l border-slate-100 pl-4 space-y-0.5">
                {v.notes.map(n => (
                  <p key={n} className="text-xs text-slate-600">· {n}</p>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}
