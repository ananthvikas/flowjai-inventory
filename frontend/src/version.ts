// version.ts — single source of truth for the app version shown in the UI.
// Keep in step with backend/app/__init__.py (__version__) and BUILD_VERSION.txt.

export const VERSION = '0.8.3'
export const BUILD_DATE = '2026-10-11'

export interface VersionEntry { version: string; date: string; notes: string[] }

export const VERSION_HISTORY: VersionEntry[] = [
  {
    version: '0.8.3', date: '2026-10-11',
    notes: [
      'launch.bat / launch.sh: a fresh install now starts correctly. They failed on a new database ("no such table: panels"), and launch.sh could create demo data and a default admin account. Both now start through run.py, exactly like the packaged app',
      'A database left half-created by the old launchers is recognised and set up as a fresh install',
      'Docker deployment removed (no longer maintained). Install with the Windows package or the Python launchers',
      'Network help text corrected to port 8000; About page deployment line updated',
      'GitHub: tests run on every push; the Windows release is built, zipped and checksummed automatically',
      'Antibody import (was SAP Import): Excel .xlsx uploads fixed (they always failed); downloadable template; the standard vial volume is now saved from the import, and filled in for existing antibodies that have none',
      'Help and feedback contact on the About page',
    ],
  },
  {
    version: '0.8.2', date: '2026-10-03',
    notes: [
      'Bench station: one-tap sample flags on every ticket — Fibrin threads, Low volume, Lyse issue. Tap to set, tap again to clear; recorded against the operator chosen on the tablet',
      'Worklist: the same flags as toggles in the comment editor; flags and comment shown together in the worklist, cocktail trace and CSV',
      'Staff name picker on sample comments and flags (shared bench logins). Required; never pre-filled. The name is shown on hover and exported as comment_by',
      'Standard vial volumes now apply prospectively only: opening a store vial uses the store record as recorded (the 0.8.1 automatic correction is removed). Older records can still be reviewed under Antibodies > Volume check',
      'Worklist: flags and comment sit under the lab ID, edited in a pop-up; table fits a 1280 px screen without side-scrolling',
      'Shipment QC upload fix actually included — the 0.8.1 package was built with the old upload code by mistake',
      'Migration 012_sample_flags_comment_staff',
    ],
  },
  {
    version: '0.8.1', date: '2026-10-03',
    notes: [
      'Shipment QC: evidence uploads fixed — chosen files were silently dropped (the file list was cleared before the upload ran)',
      'Antibody master: standard vial volume per catalogue number. Receive lot, bulk receive, store stock, PO order and PO delivery use it automatically; a different volume needs a reason, which is recorded on the lot',
      'Store stock no longer defaults to 500 µl per vial',
      'Opening a store vial whose recorded volume disagrees with the standard uses the standard volume and notes the correction',
      'Volume check (Antibodies page): lists lots and store vials with non-standard starting volumes — correct them (remaining volume follows unless the lot was physically verified) or confirm them as genuine; set missing standard volumes inline',
      'Worklist: sample comment per sample (clots, fibrin threads, degeneration, low count…) with quick-pick options, editable at any status; shown in the cocktail trace and included in the worklist CSV',
      'Antibody search matches catalogue number; vial volume added to the antibody and inventory exports',
      'Fixed: Inventory CSV export failed whenever any lot existed',
      'Frontend dependency lockfile (package-lock.json) for reproducible builds',
      'Migration 011_vial_volume_sample_comment',
    ],
  },
  {
    version: '0.8.0', date: '2026-09-25',
    notes: [
      'Shipment-to-shipment verification: shipment ID on every receipt, automatic 48 h verification task on a shipment change, evidence-gated sign-off with SHA-256 audit hashes, Shipment QC page and CSV audit log',
      'Cocktail traceability: every sample run on a cocktail, the antibody lots and shipments in it, and other cocktails sharing those lots; lab ID search across all dates',
      'Staff names on shared-login actions (cocktail preparation, verification sign-off) and a filterable preparation log',
      'Bench processing station (/station) for a touchscreen tablet: per-panel step lists, batch advance, 10-minute undo, operator selection',
      'Step timers with countdown, chime and over-incubation alarm; early completions recorded',
      'Background running, watchdog and daily restart (Windows); safe database transfer (transfer-db.bat)',
      'Packaged build is now a folder, not a single exe; log file capped at 40 MB',
      'Upgrades from June 2026 databases fixed (idempotent migrations, SQLite table-rebuild fix)',
      'Migrations 007–010',
    ],
  },
  {
    version: '0.7.0', date: '2026',
    notes: [
      'Security hardening: no seeded accounts (first-run admin setup), opt-in demo data, per-install signing key, loopback binding by default',
      'Recording a test deducts every panel component; shortfalls reported in full',
      'Stock verification always writes a verification record with method, pipette increment and cycle',
      'Panel designer resolves markers across all fluorochrome variants',
      'One cocktail service and one FIFO deduction path; cocktail preparation respects worklist reservations',
    ],
  },
  {
    version: '0.6.5', date: '2026-06-25',
    notes: [
      'Panel Designer: fixed fluorochrome names not showing in "Multiple fluorochromes" clashes (now uses direct DB lookup)',
      'Panel Designer: combinations table now shows only maximally-complete assignments — all antibodies included where possible, no partial combos',
    ],
  },
  {
    version: '0.6.4', date: '2026-06-25',
    notes: [
      'Panel Designer: clash entries now show fluorochrome name (e.g. "CD45 · PE") so users can distinguish variants',
      'Panel Designer: alternative antibody suggestions for out-of-stock items — click to swap in an alternative',
      'Panel Designer: integrated AntibodyAlternative system from antibody master into designer flow',
    ],
  },
  {
    version: '0.6.3', date: '2026-06-25',
    notes: [
      'Panel Designer: prevent same antibody from appearing twice in a panel (e.g. CD45-PE and CD45-FITC)',
      'Panel Designer: replace combination selector buttons with a scrollable table for easier comparison',
      'Panel Designer: new clash detection for antibodies available in multiple fluorochromes',
    ],
  },
  {
    version: '0.6.2', date: '2026-06-25',
    notes: [
      'Panel Designer: fixed "No valid combinations found" when antibodies share fluorochromes — algorithm now allows skipping antibodies with unavailable channels instead of dead-ending',
    ],
  },
  {
    version: '0.6.1', date: '2026',
    notes: [
      'Auto-generated human-readable cocktail codes (e.g. CL1_20260624_193015)',
      'Cocktail code tracked against each tube in the worklist for batch-to-batch traceability',
      'Cocktail codes included in worklist CSV export for cocktail-performance verification',
      'All timestamps now use local system time instead of forced UTC',
    ],
  },
  {
    version: '0.6.0', date: '2026',
    notes: [
      'Worklist — order tubes per sample (lab ID, requesting pathologist, processing technologist), replacing the shared tracking sheet',
      'Ordered tubes reserve cocktail tests; an alert flags when cocktails are insufficient',
      'Status flow: in queue → processing (consumes the reserved cocktail) → completed',
      'Manual cocktail logging now respects reservations, so a queued sample\u2019s tests can\u2019t be used by mistake',
      'Turnaround time export — request, processing, and completion timestamps with queue and processing intervals',
      'Staff master list (pathologists and technologists) under Admin',
    ],
  },
  {
    version: '0.5.0', date: '2026',
    notes: [
      'Store Stock module — receive and track unopened vials; "open vial" transfers one vial to floor inventory',
      'Forecasting now includes store stock vials in depletion projections',
      'Receive-lot warning when an antibody has no store stock record',
      'Log tests from a prepared cocktail (deducts the batch, not raw stock) — cocktail usage now appears in the test log',
      'Printable cocktail preparation worksheet with checkboxes and sign-off',
      'Cocktail summary CSV export by date range',
      'Edit antibody details from the antibody master',
      'Authenticated file downloads (fixes export auth errors)',
    ],
  },
  {
    version: '0.4.0', date: '2026',
    notes: [
      'Ad hoc test logging — pick individual antibodies without a saved panel',
      'Column sorting in the antibody master',
      'Dashboard shows low-stock items first, with a cocktail status panel',
      'Stores-facing stock position report and bulk receive',
      'Searchable antibody picker when building panels',
      'Panels can share a test group (e.g. CL1, CL2, HCL under one protocol)',
      'Force-delete with cascade preview for antibodies and panels',
      'Removed statsmodels dependency — runs on any Python 3.9–3.13',
      'SPA routing fix for deep links in standalone mode',
    ],
  },
  {
    version: '0.3.0', date: '2026',
    notes: [
      'Validation export — volume tracking accuracy, alert effectiveness, usage summary',
      'Lab Settings page — lab name/subtitle in sidebar, network access guide',
      'Admin-configurable global alert defaults (replaces hardcoded values)',
      'FlowJAI branding throughout',
      'Updated acknowledgements',
    ],
  },
  {
    version: '0.2.1', date: '2026',
    notes: [
      'Bug fix: verify_stock_volume missing from consumption service after refactor',
    ],
  },
  {
    version: '0.2.0', date: '2026',
    notes: [
      'Cocktail batch tracking with pre-flight stock warnings and affected panel display',
      'Cocktail expiry alerts',
      'Fluorochrome master management page',
      'Vendor and fluorochrome columns in inventory view',
      'Optional email on user accounts; admin edit and password reset',
      'About page with version history',
    ],
  },
  {
    version: '0.1.0', date: '2026',
    notes: [
      'Initial release',
      'Panel and antibody master with per-tube volume mapping',
      'FIFO stock lot management with physical verification',
      'ETS depletion forecasting and shortage/expiry/substitute alerts',
      'CSV test log import and role-based access (Admin / Technologist)',
      'Docker one-command deployment for Windows and Mac',
    ],
  },
]
