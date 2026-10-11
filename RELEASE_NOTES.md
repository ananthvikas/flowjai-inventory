# flowjAI Inventory Manager — v0.8.3 (2026-10-11)

## Python launchers fixed for new installs
- **`launch.bat` failed on every fresh install** with "database upgrade failed: no such table: panels":
  it ran the migrations against an empty database, but the migrations assume the base
  schema already exists. Existing installs were unaffected.
- **`launch.sh` (macOS/Linux) hid the same failure** and then ran the demo seeder, so a fresh
  install got demo data and a default `admin` account while listening on the network.
- Both launchers now start through `run.py --lan`, the same start-up path as the packaged
  app: fresh databases get the full schema and first-run admin setup, existing ones are
  upgraded (refusing to start if an upgrade fails), and demo data never loads.
- A database left with only an `alembic_version` table by the old launchers is recognised
  and initialised as a fresh install instead of failing on every start.
- `stop.sh` now stops a server started by the new `launch.sh`.

## Docker removed
- `docker-compose.yml`, both Dockerfiles and `nginx.conf` are gone; the Docker route was no
  longer maintained or tested. Install with the Windows package or the Python launchers.
- Lab Settings network help now gives port 8000 (was the Docker port 80); the About page
  deployment line is updated. The out-of-date `README for staff.txt` is removed (the
  packaged app's `README.txt` and the main README replace it).

## Antibody import (was "SAP Import")
- **Excel uploads fixed.** Uploading an .xlsx file always failed: the Excel reader
  (`openpyxl`) was not installed and was excluded from the packaged build. Only CSV
  worked. It is now included. Old-format .xls files get a clear message asking for
  .xlsx or .csv.
- **Standard vial volume saved.** The importer worked out each antibody's volume but
  discarded it. It is now saved as the antibody's vial volume (0.8.1), and filled in for
  existing antibodies (matched by catalogue number) that have none; a volume already set
  is never changed.
- **Template.** *Download template* on the import page, also in
  `templates/antibody-import-template.csv`: Antibody Name, Fluorochrome Name,
  Catalogue No, Manufacturer, Vial Volume uL, optional Description. SAP exports work as
  before.
- Renamed to **Antibody import**; example rows use made-up codes.

## Help and feedback
- Contact address **feedback.flowjai@gmail.com** on the About page, in the README and in the
  packaged app's README.txt. `SECURITY.md` explains how to report security problems privately.
- The Lab Settings placeholder no longer names a specific laboratory.

## Build and release
- Tests run on GitHub for every push. Creating a release with a `v*` tag runs the tests,
  builds `dist\flowjAI\` with the same helper scripts as `build-exe.bat`, and attaches
  `flowjAI-<version>-windows.zip` with a SHA-256 checksum.

## Upgrade
- No database changes. Schema head remains `012_sample_flags_comment_staff`.

---

# flowjAI Inventory Manager — v0.8.2 (2026-10-03)

## One-tap sample flags (bench tablet)
- Every station ticket has three large toggle buttons: **Fibrin threads**, **Low volume**,
  **Lyse issue**. Tap to set, tap again to clear. Built for gloved use: no typing,
  56 px targets, on-state shown by a filled button with a tick (not colour alone).
- Recorded against the operator chosen at the top of the tablet; buttons stay disabled
  until an operator is chosen. A repeated tap (double tap, network retry) changes nothing.
- The same flags appear as toggles in the worklist comment editor. Flags and the comment
  are shown together in the worklist, on the ticket, in the cocktail trace and in the CSV
  (`sample_flags`). The flag list lives in `backend/app/services/sample_flags.py`.

## Staff name on comments
- Saving a sample comment or flag change from the worklist requires choosing **who is
  entering it** from the staff list (the bench PC uses a shared login). Deliberately
  never pre-filled. The name shows on hover and is exported as `comment_by`. The API
  rejects comment and flag changes without a valid staff id.

## Standard vial volume: prospective only
- Opening a store vial now uses the store record's volume as recorded. The 0.8.1
  behaviour of silently switching legacy records to the standard volume is removed.
  Standard-volume checks apply to receipts made from 0.8.1 on. Older records are not
  changed automatically; Antibodies > Volume check still lists them for optional review.

## Worklist layout
- Flags and comment are shown under the lab ID, against the sample number, and edited
  in a pop-up instead of inline. At 1280 px the order form narrows slightly and table
  padding is tighter, so the worklist fits without side-scrolling.

## Correction to 0.8.1
- **The 0.8.1 package did not contain the Shipment QC upload fix.** The source and
  built frontend in that zip still had the original upload code, which silently drops
  chosen files. The fix is in 0.8.2, verified in a browser against this exact build.

## Upgrade
- Migration `012_sample_flags_comment_staff` runs automatically on start.

---

# flowjAI Inventory Manager — v0.8.1 (2026-10-03)

## Shipment QC evidence upload fixed
- Choosing files in a verification's "Add file" did nothing: the file input was reset
  before the upload started, which empties the browser's live file list, so zero files
  were sent and no error was shown. The files are now copied first.

## Standard vial volume (antibody master)
- New **Vial volume (µl)** field next to Catalog No. Most reagents ship in a fixed fill
  volume per catalogue number; once set, it is used automatically by Receive lot, Bulk
  receive, Store Stock receive/edit, PO order and PO delivery. The field is shown locked;
  entering a different volume requires a reason, saved on the lot / store record as
  `[VOLUME OVERRIDE]`. The backend enforces the same rule.
- Store Stock no longer defaults to **500 µl** per vial (a silent source of wrong volumes).
- Opening a store vial whose recorded volume disagrees with the standard (and wasn't a
  deliberate override) uses the standard volume and notes `[VOLUME CORRECTED]`.
- **Volume check** (Antibodies page) lists open lots and store vials whose starting
  volume differs from the standard. *Correct* sets the start to the standard and shifts the
  remaining volume by the same amount — unless the lot was physically verified, in which
  case the remaining volume is a measurement and is left alone. *Keep* confirms a genuine
  non-standard vial. Antibodies without a standard volume can be filled in inline.
- Antibody search matches catalogue number.

## Worklist sample comment
- Free-text **Sample comment** column per sample (clots, fibrin threads, degeneration,
  low count…), with quick-pick options. Editable at any status, including completed.
  Records who/when. Shown in the cocktail trace (helps separate sample problems from
  reagent problems) and exported in the worklist CSV.

## Fixes
- Inventory CSV export failed (HTTP 500) whenever any lot existed: it read lot fields that
  don't exist (`vendor`, `catalog_no`, `received_date`, `opened`).

## Build
- `frontend/package-lock.json` is now committed. Use `npm ci` for reproducible builds.
- Version is single-sourced: `frontend/src/version.ts` (About page) and
  `backend/app/__init__.py` (API `/health`).

## Upgrade
- Migration `011_vial_volume_sample_comment` runs automatically on start.
- After upgrading: Antibodies → Volume check. Set standard vial volumes, then correct
  the flagged lots. Forecasts only improve once both are done.

---

# flowjAI Inventory Manager — v0.8.0 (2026-09-25: shipment QC + cocktail traceability)

## Shipment-to-shipment verification
- **Shipment ID recorded on every receipt**: Store Stock, Receive lot, Bulk receive
  and PO delivery (required in the UI). Opening a store vial now carries the
  shipment ID onto the open lot (previously lost).
- **Automatic verification task** when an antibody arrives under a shipment ID
  different from its previous stock (including legacy stock with no shipment ID).
  One task per antibody per shipment; the first-ever receipt of an antibody raises none.
  Lot changes are flagged so lot-to-lot criteria are applied.
- **48 h deadline.** A `shipment_verification` alert on trigger, and a single
  `shipment_verification_overdue` alert after the deadline.
- **Evidence-gated sign-off.** Closing requires at least one image/document for the
  previous AND the new shipment (PDF, image, Office, CSV, FCS; 20 MB max; SHA-256
  recorded). "Not acceptable" requires comments. Closed records are immutable, and
  closing acknowledges the linked alerts.
- New **Shipment QC** page (nav badge: amber = open, red = overdue) and CSV audit log.
- Evidence files are stored in `data/uploads/`. Include this folder in backups.

## Cocktail traceability
- Worklist tubes show their cocktail code. Clicking it lists every sample run on
  that cocktail (your sample highlighted), the antibody lots and shipments that went
  into it, and other cocktails drawn from the same lots. Copy lab IDs or export CSV.
- Trace button on the Cocktails page; the cocktail code is now shown there.
- Worklist lab ID search across all dates.
- The cocktail worksheet prints the lot / shipment used for each antibody.
- Tests logged via Cocktails → "Log tests" carry no lab IDs; the trace reports how
  many such untracked tests exist.

## Upgrading June 2026 databases, part 2 (fix)
- Upgrading a real June database failed at migration 008 with "FOREIGN KEY constraint
  failed" on DROP TABLE cocktails. SQLite changes constraints by rebuilding a table
  (copy, drop, rename), and the app enables foreign-key enforcement on every
  connection, so the drop was refused while tubes and logs referenced cocktails.
  Migrations now run with enforcement off for the migration connection only, then run
  SQLite's integrity check: the upgrade fails if it created any broken reference;
  references that were already broken are reported but don't block start-up.
- A table rebuild interrupted part-way no longer blocks the next attempt (its leftover
  temp table is removed; the original is intact at that point).
- The "database upgrade failed" message box now shows the reason.

## Upgrading databases from the June 2026 .exe (fix)
- Databases created by the June .exe could be labelled with an older schema version
  than they really had (it built tables straight from the models, then stamped an older
  revision). Upgrading them failed with "duplicate column name: cocktail_code" and the
  app refused to start. Every migration now checks for each table, column and index
  before adding it (`migrations/_guards.py`), so such databases upgrade cleanly, and
  running an upgrade twice is harmless.

## Timer alarm
- When a step's timer runs out the station now alarms until someone taps **OK** or does
  the step: a flashing screen edge, a banner naming the sample and step, a flashing
  ticket outline, a chime repeated every 30 s, and a vibration on Android tablets.
  Amber instead of green once the step is 10+ minutes overdue.

## Log size cap
- `data\flowjai.log` now rotates **while running** at 10 MB, keeping 3 old copies
  (40 MB maximum). Previously the size was only checked at start-up, so one long run
  with a repeating error could fill the disk (one reached 44 GB).
- Identical lines repeated back-to-back are collapsed into
  "[previous line repeated N more times]", so an error loop costs almost nothing.
- The background service's Python mode now writes to the same capped log (its
  `server.log` redirect had no limit). Cap adjustable with FLOWJAI_LOG_MAX_MB.

## Packaged build (build-exe.bat)
- Builds a **folder** (`dist\flowjAI\`) instead of a single exe: faster start, far less
  likely to be quarantined by antivirus. Copy the whole folder; nothing needs installing
  on the target PC. The folder includes Start/stop/transfer/auto-restart scripts and a README.
- Builds from the app's venv with all backend requirements (previously used the system
  Python, which could silently produce an exe missing packages).
- Bundles the multipart parser (evidence uploads) and every app module.
- The exe: refuses to start if the database upgrade fails (was "non-fatal"); opens the
  browser instead of starting a second copy; `--lan` is remembered so the tablet keeps
  working; `--no-browser` for the watchdog; `--transfer-db SOURCE` for safe data transfer.
- The watchdog, install-autorestart and transfer-db scripts work with both the Python
  install and the packaged exe.

## Safe database transfer (fixes blank worklist after moving a database)
- **`transfer-db.bat`** (drag the old app folder onto it): stops the app, copies the
  database with SQLite's backup API, removes stale `-wal`/`-shm` files at the target,
  backs up the database it replaces to `data\backups`, verifies record counts match,
  then starts the app (which applies upgrades).
- Why: the database runs in WAL mode. Copying only `flowjai.db` can miss the newest
  records (still in the source's `flowjai.db-wal`, always the case after a force-close),
  and copying over a database while the app runs, or next to a leftover `-wal`, makes
  the app keep showing, and then write back, the old contents.
- `launch.bat` and the background service no longer start on a failed database upgrade;
  the error is shown / logged (`data\logs\migrate.log`) instead of screens going blank.
- `launch.bat` resumes the watchdog if `stop.bat` had paused it.
- `update.bat` stops the app first and backs up with the backup API.

## Step timers
- Each processing step can have a **wait time**: the minimum minutes after the
  previous step before it is due (e.g. Incubated = 15). Set per panel or lab-wide
  under Admin > Processing steps (also reachable from a gear on the station for admins).
- The tablet counts down on the step's button, turns it green and chimes when the time
  is up, and turns it amber once it has been ready for 10+ minutes (over-incubation).
  Countdowns use the server clock, so a tablet with the wrong time still counts correctly.
- Tapping a step early asks for confirmation, and the early completion is recorded
  against the step. Worklist "Complete" (fallback) skips timers.
- Migration `010_step_timers`. `/health` now also checks the database.

## Background running, watchdog and daily restart (Windows)
- `install-autorestart.bat` sets up Task Scheduler to run the app **hidden** (no console
  window), **restart it daily** at a time you choose, and run a **watchdog every 2 min**
  that restarts it after 3 failed health checks, or starts it if it isn't running.
  Everything is logged to `data\logs\watchdog.log`.
- `start-background.bat` / `stop.bat` start and stop it. `stop.bat` pauses the watchdog so it
  stays stopped for maintenance; starting again resumes it. `uninstall-autorestart.bat`
  removes the tasks.
- Fixed: `stop.bat` never stopped anything (killed `uvicorn.exe`; the server is `python.exe`).
- `launch.bat` now just opens the browser if the app is already running, and warns not to
  click inside its window (QuickEdit pauses the server).

## Bench processing station (tablet)
- New full-screen **Bench station** page at `/station` for a touchscreen tablet on the
  lab network: every pending worklist sample is a ticket (urgent first, then longest
  waiting), with a waiting timer that turns amber at 30 min and red at 60 min.
- **Steps per tube**, taken from the tube's panel (Admin → Processing steps), the lab
  default, or the built-in list (Cocktail added → Incubated → Lysed & washed → Acquired).
  Each tube keeps the steps it was ordered with; editing a panel's steps only affects
  new orders.
- **Step 1 uses the tube's reserved cocktail test** and starts the sample. Steps must be
  done in order. When every tube is done the sample is completed (TAT recorded) and
  leaves the board; it stays under "Just finished" for 15 minutes.
- **"All N tubes: <step>"** button when several tubes of a sample are at the same step.
- **Undo** the most recent step of a tube within 10 minutes. Undoing step 1 exactly
  reverses the cocktail use (usage is now linked to the tube).
- **Operator** chosen once at the top of the tablet; every step records who did it.
- **30-day station session** when the tablet is signed in with a technologist login
  (refused for admin logins).
- The worklist shows each tube's progress (e.g. 2/4 → Incubated). Worklist Start and
  Complete still work as a fallback and use the same step logic; Complete now asks
  for confirmation because it marks every remaining step done.
- Cancelling a partly processed sample releases its unstarted tubes' reservations.
- Login now returns you to the page you were trying to open.
- Migration `009_processing_steps`.

## Staff names on shared-login actions
- **Cocktail preparation** asks who is mixing (Admin → Staff list); required in the UI.
  Deliberately not pre-filled from the previous prep, so one person's name can't
  carry over onto the next person's cocktail.
- **Shipment verification sign-off** asks who is signing off.
- Older cocktails show the login username, marked "(login)".
- **Preparation log** on the Cocktails page: filter by date, panel and person;
  open the trace from any row; CSV export now includes cocktail code, time and
  preparer name.
- Migration `008_staff_signatures`.

## Fixes
- Two cocktails of the same panel prepared in the same second no longer collide on
  `cocktail_code` (was an HTTP 500).
- The Alerts page no longer hides alert types it has no section for.

## Upgrade
- Migration `007_shipment_verification` runs automatically on start (run.py /
  launch scripts). It back-fills shipment IDs onto open lots where exactly one store
  record matches antibody + lot.
- Docker only: add `client_max_body_size 25m;` to `frontend/nginx.conf`, or uploads
  over 1 MB will fail.

---

# flowjAI Inventory Manager — v0.7.0

## Security hardening (release blockers addressed)

- **Seeded accounts removed.** A fresh install no longer ships with
  `admin` / `technologist` / `service` accounts. First run now forces a setup
  screen where the operator creates their own administrator account.
- **Demo data is opt-in.** Seed data only loads with `python run.py --demo`.
- **Per-install signing key.** `SECRET_KEY` is generated on first run and
  persisted next to the database (no hardcoded fallback).
- **Loopback binding by default.** The server binds to `127.0.0.1`; pass
  `--lan` to expose it on the local network.
- **Dev scripts removed.** `fix_service.py`, `verify_service.py`,
  `check_service.py`, `fix_db.py` and `backend/reset_service.py` are gone.
- **Auth debug logging removed.** Usernames and password-hash prefixes are no
  longer written to the log.
- **SQL echo off.** Statement echo only when `SQL_ECHO=1` is set.

## Correctness fixes

- **Partial consumption fixed.** Recording a test now deducts every panel
  component; shortfalls are reported once, in full, and recorded in the test
  log notes behind a `[STOCK SHORTFALL]` marker (HTTP 207).
- **Verification logging.** Stock verification always writes a verification
  record, requires the verifying user, and captures measurement method, pipette
  increment and verification cycle.
- **Panel designer.** Markers now resolve across all fluorochrome variants
  (CD4-PE / CD4-APC / CD4-BV421 are three options for CD4), and the search
  reports when results are truncated.
- **Duplicate services removed.** One cocktail service and one FIFO deduction
  path. Cocktail preparation now respects worklist reservations.
- **Forecast fallback bug.** The Holt-ETS fallback now passes the supply
  arguments it was previously missing.

## Windows binary

- Single-file PyInstaller build: `dist/flowjai-inventory.exe`.
- SHA-256 checksum: see `dist/flowjai-inventory.exe.sha256`.
- The database lives in `data/flowjai.db` next to the executable. Upgrading
  means replacing the `.exe` and keeping the `data` folder.

## SmartScreen / antivirus note

This executable is not code-signed, so Windows may show "Windows protected your
PC". Click **More info → Run anyway**. Verify the SHA-256 checksum against the
published value before trusting the download.
