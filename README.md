# flowjAI Inventory Manager

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23302747.svg)](https://doi.org/10.5281/zenodo.23302747)

A self-hosted reagent inventory and sample-processing system for clinical and research flow cytometry laboratories. Tracks antibodies from the stockroom to the bench, models consumption per panel, forecasts depletion, verifies new shipments, and traces every sample back to the cocktail and antibody lots it was run on — entirely within your laboratory network, with no cloud dependency and no subscription.

Designed and built by **Ananthvikas Jayaram**. Clinical requirements and validation supported by Sriram Sujay Prasad and Sujay Ramaprasad.

Current version: **0.8.3** — see [RELEASE_NOTES.md](RELEASE_NOTES.md) for the full change history.

---

## Features

**Inventory**
- **Store stock** — unopened vials in the stockroom; "open vial" moves one vial to floor inventory
- **Floor stock** — open vials in use, with FIFO lot deduction and physical-verification logging (method, pipette increment, cycle)
- **Standard vial volume** per catalogue number, applied automatically on receipt; deviations require a recorded reason, and a Volume check page lists legacy discrepancies
- **Forecasting** — Holt-Winters depletion projection including store-stock vials
- **Alerts** — shortage, expiry, substitute suggestions and shipment-verification deadlines, with admin-configurable thresholds

**Panels, cocktails and tests**
- **Panels** — per-antibody µl/tube mapping, shared test groups, and marker search across fluorochrome variants
- **Cocktails** — pre-mixed batches with pre-flight stock warnings, printable worksheets (showing lot and shipment per antibody), and a preparation log recording who mixed each batch
- **Test logging** — from a panel, a cocktail, or ad hoc antibody selection; CSV import for LIMS data; shortfalls are recorded, never silently skipped

**Worklist and bench station**
- **Worklist** — sample orders with cocktail reservation and turnaround-time tracking; lab ID search across all dates
- **Bench station** (`/station`) — full-screen touchscreen view for a bench tablet: per-tube processing steps, step timers with alarms for under- and over-incubation, undo, and large glove-friendly buttons
- **Sample flags and comments** — one-tap flags (fibrin threads, low volume, lyse issue) and free-text comments, each attributed to a named staff member

**Quality and traceability**
- **Shipment QC** — an automatic verification task when an antibody arrives under a new shipment ID, with a 48-hour deadline, evidence-gated sign-off (previous and new shipment), and an immutable audit log
- **Cocktail trace** — from any tube, list every sample run on that cocktail, the antibody lots and shipments in it, and other cocktails drawn from the same lots
- **Staff names on shared logins** — cocktail preparation, shipment sign-off, bench steps and sample comments all record the named person, not just the login

**Operations**
- **Antibody import** — load your antibody master list from CSV or Excel (.xlsx), using the [import template](templates/antibody-import-template.csv) or a SAP materials export, including each antibody's standard vial volume
- **Exports** — CSV for antibodies, inventory, panels, cocktails, worklist and audit logs; a stores-facing stock report; validation exports for publication
- **Roles** — Admin / Technologist, JWT authenticated
- **Background running on Windows** — hidden service with daily restart and a health-check watchdog
- **Safe database transfer** between installs, with automatic backup and record-count verification

Runs on Windows (packaged app or Python), and on macOS and Linux (Python).

---

## Security — read before deploying

- **First run creates your administrator account.** A fresh install has no users: the browser opens a setup page where you create the admin account. There are no default passwords.
- **A unique signing key is generated per install** on first run and stored with the database in `data/`. Do not copy one install's `data/` folder to start another lab's install.
- **Never commit or share your `data/` folder.** It contains your laboratory's inventory, worklist, staff names and QC evidence. It is excluded by `.gitignore`.
- **Network access is opt-in for the packaged app.** Double-clicking the `.exe` serves this computer only. `Start flowjAI.bat` (packaged app) and `launch.bat` / `launch.sh` (Python) start it for the local network so other PCs and the bench tablet can connect, and add a firewall rule restricted to the local subnet. Never expose the app to the internet.
- **Reporting a security problem:** please email rather than opening a public issue — see [SECURITY.md](SECURITY.md).
- **HTTPS is not built in.** Acceptable on a trusted hospital LAN; put a TLS reverse proxy in front of it for anything wider.
- **No login rate limiting yet.** Keep the app on the internal network.

---

## Installation

Install to a **local folder** such as `C:\flowjai\`. Do not run the app from a OneDrive, Dropbox or other synced folder: background sync corrupts the SQLite database.

### Option A — Windows packaged app (no Python needed; recommended for most labs)

1. Open the [Releases page](https://github.com/ananthvikas/flowjai-inventory/releases) and download `flowjAI-vX.Y.Z-windows.zip` for the latest version.
2. *(Optional)* Verify the download against the published `.sha256` checksum.
3. Unzip it to a local path, e.g. `C:\flowjAI\`. Keep the **whole folder** together — the `.exe` needs the `_internal` folder beside it.
4. **First time:** right-click `Start flowjAI.bat` → **Run as administrator**. This allows the bench tablet and other PCs through Windows Firewall (local subnet only) and starts the app for network use. The browser opens at `http://localhost:8000`.
   - **"Windows protected your PC"** appears because the app is not code-signed. Click **More info → Run anyway**. Hospital IT may need to approve it.
5. Create your administrator account on the setup page.
6. *Recommended:* run `install-autorestart.bat` (see *Running in the background*) and set the PC's sleep setting to **Never**.

After the first time, start it with `Start flowjAI.bat` or by double-clicking `flowjai-inventory.exe` — the network setting is remembered. To return to this-PC-only, run `flowjai-inventory.exe --local` once.

The app creates a `data\` folder beside itself on first run. This holds your database, logs and uploaded QC evidence. The `README.txt` inside the folder repeats these steps for laboratory staff.

### Option B — Windows with Python

Requires **Python 3.11** (recommended — the release build is made and tested with it) or 3.12. Tick "Add Python to PATH" during install.

1. Download this repository (green **Code** button → **Download ZIP**) or clone it, and extract it to a local folder.
2. Double-click `launch.bat`.
   - First run creates a virtual environment and installs packages (2–3 minutes); later starts take about 10 seconds.
   - It adds a LAN-only firewall rule (needs administrator rights the first time), prints the address other computers should use, creates or upgrades the database, and opens the browser.
3. Create your administrator account on the setup page.

**No internet on the lab PC?** On a PC with internet, run `build-wheels.bat` to download every package into a `wheels\` folder, then copy the app folder including `wheels\` to the lab PC. `launch.bat` installs from it offline.

Keep the window open while using the app, and **do not click inside it** — Windows pauses the app while text in that window is selected. To run without a window, see *Running in the background* below.

### Option C — macOS / Linux with Python

```bash
./launch.sh
# Open http://localhost:8000
```

### Demo data

To explore the app with sample antibodies, panels and stock, start it with `python run.py --demo` on a **separate, throwaway install**. Never load demo data into a live laboratory database.

---

## Running in the background (Windows)

| Script | What it does |
|---|---|
| `install-autorestart.bat` | Sets up Task Scheduler to run the app hidden, restart it daily at a time you choose, and run a watchdog every 2 minutes that restarts it after 3 failed health checks |
| `start-background.bat` | Starts the hidden app |
| `stop.bat` | Stops the app and pauses the watchdog (for maintenance); starting again resumes it |
| `uninstall-autorestart.bat` | Removes the scheduled tasks |

Watchdog activity is logged to `data\logs\watchdog.log`. These scripts work with both the packaged app and the Python install.

---

## Backing up, moving and upgrading

All laboratory data lives in the `data/` folder: the database (`flowjai.db`), uploaded Shipment QC evidence (`uploads/`), the signing key, and logs.

**Back up:** stop the app (`stop.bat` or close the window), then copy the **entire `data/` folder**. Copying only `flowjai.db` misses QC evidence and can miss the newest records.

**Move to a new computer or folder:** set up a fresh copy of the app, then **drag the old app folder onto `transfer-db.bat`** in the new one. It stops the app, copies the database safely, backs up whatever it replaces to `data\backups`, checks record counts match, and starts the app. Do not copy `flowjai.db` by hand: the database runs in write-ahead-log mode, and a manual copy can lose recent records or make the app show stale data.

**Upgrade to a new version:**
1. Download and extract the new version to a **new** folder.
2. Drag your current app folder onto the new folder's `transfer-db.bat`.
3. The app starts and applies any database upgrades automatically. If an upgrade fails, the app refuses to start rather than risk your data; the reason is in `data\logs\migrate.log`.
4. Keep the old folder until you have confirmed everything works.

After upgrading, read the *Upgrade* section of [RELEASE_NOTES.md](RELEASE_NOTES.md) for any one-off steps.

---

## CSV test-log import format

```csv
date,test_code,count,notes
2026-05-01,LSS,12,Morning batch
2026-05-01,BMRD,4,
2026-05-02,TNK,6,Paediatric cohort
```

`test_code` must match a panel's test code exactly.

---

## Development

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
# API docs at http://localhost:8000/docs

# Frontend (separate terminal)
cd frontend
npm ci
npm run dev
# App at http://localhost:5173 (proxies /api to :8000)
```

Run the tests:

```bash
cd backend
pip install pytest httpx
python -m pytest -q
```

The tests also run automatically on GitHub for every push (`.github/workflows/tests.yml`).

After changing frontend code, rebuild the bundle that the Python and packaged modes serve, and commit `frontend/dist/`:

```bash
cd frontend && npm run build
```

The version number is defined in `frontend/src/version.ts` and `backend/app/__init__.py`. Creating a release with a tag such as `v0.8.3` runs the tests, builds the Windows package and attaches the zip and its checksum to the release automatically (`.github/workflows/release.yml`). `build-exe.bat` produces the same package locally in `dist\flowjAI\`.

---

## Project structure

```
flowjai-inventory/
├── backend/
│   ├── app/
│   │   ├── models.py            # SQLModel table definitions
│   │   ├── database.py          # Engine, session dependency
│   │   ├── auth.py              # JWT, roles, first-run setup
│   │   ├── seed.py              # Demo data (only with --demo)
│   │   ├── routers/             # One file per resource
│   │   └── services/            # Consumption (FIFO), forecasting, alerts,
│   │                            #   sample flags, shipment verification, …
│   ├── migrations/              # Alembic migrations (run automatically on start)
│   ├── tests/                   # pytest suite
│   └── requirements.txt
├── frontend/
│   ├── src/                     # React + TypeScript source
│   └── dist/                    # Pre-built app, shipped so Python installs need no Node
├── packaging/                   # Start script and README added to the Windows package
├── .github/workflows/           # Tests on every push; Windows release build
├── run.py                       # Entry point (packaged app and Python launchers)
├── flowjai-inventory.spec       # PyInstaller build definition
├── build-exe.bat                # Local Windows package build
├── launch.bat / launch.sh       # Python launchers
├── install-autorestart.bat      # Background running, daily restart, watchdog
├── start-background.bat / stop.bat / uninstall-autorestart.bat
├── transfer-db.bat              # Safe database transfer between installs
├── update.bat / update.sh       # Update scripts
├── USER_MANUAL.md               # Guide for laboratory staff
├── SECURITY.md                  # How to report a security problem
├── templates/                   # Antibody import template (CSV)
└── data/                        # Created on first run; never committed
```

---

## Getting help and contributing

- **Bugs and feature requests:** open an issue on the [Issues page](https://github.com/ananthvikas/flowjai-inventory/issues), or email **feedback.flowjai@gmail.com** if you don't have a GitHub account. Include the version (shown on the About page), what you did, what you expected, and the relevant lines from `data\flowjai.log`.
- **Never send your database, patient identifiers or lab IDs** — by email or in an issue.
- **Using flowjAI in your laboratory?** Please email feedback.flowjai@gmail.com to say so. The app never reports anything back on its own, so this is the only way the project knows where it is used.
- **Security problems:** see [SECURITY.md](SECURITY.md).
- **Contributions:** pull requests are welcome. For anything beyond a small fix, please open an issue first to discuss the change.

---

## How to cite

If you use flowjAI Inventory Manager in your work, please cite it using the metadata in DOI: [10.5281/zenodo.23302747](https://doi.org/10.5281/zenodo.23302747) — this DOI always resolves to the latest version.

---

## Licence

MIT — see [LICENSE](LICENSE). Free to use, modify and deploy in any laboratory.
