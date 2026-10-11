# flowjAI Inventory Manager — User Manual

A complete guide to day-to-day use and administration.

**Audience:** laboratory technologists (daily use) and lab administrators (setup and configuration).
**Version:** 0.8.3

Installation is covered in the [README](README.md). This manual assumes the app is already running and you know its address.

---

## Contents

1. [Concepts — how the system thinks](#1-concepts)
2. [First-time setup, logging in and roles](#2-first-time-setup-logging-in-and-roles)
3. [The Dashboard](#3-the-dashboard)
4. [Store Stock — unopened vials](#4-store-stock)
5. [Inventory — open vials on the bench](#5-inventory)
6. [Shipment QC — verifying new shipments](#6-shipment-qc)
7. [Panels and the Panel Designer](#7-panels-and-the-panel-designer)
8. [Cocktails](#8-cocktails)
9. [Worklist — sample orders](#9-worklist)
10. [Bench station — the processing tablet](#10-bench-station)
11. [Test Log — recording usage outside the worklist](#11-test-log)
12. [Alerts](#12-alerts)
13. [Orders](#13-orders)
14. [Exports and reports](#14-exports-and-reports)
15. [Administration](#15-administration)
16. [Starting, stopping and looking after the app](#16-starting-stopping-and-looking-after-the-app)
17. [The daily workflow at a glance](#17-the-daily-workflow)
18. [Troubleshooting](#18-troubleshooting)

[Getting help](#getting-help)

---

## 1. Concepts

**Two physical stages of stock.** The system models reagents the way a flow lab actually holds them:

- **Store Stock** — sealed, unopened vials in the stockroom or fridge, counted in **whole vials**. Deliveries are received here.
- **Inventory (floor stock)** — opened vials in use at the bench, tracked in **microlitres (µl) remaining**.

Opening a vial moves it from Store Stock to Inventory. From then on, every test deducts µl from open vials using **FIFO** (first-in, first-out — the oldest open lot is used first).

**Panels and cocktails.** A **panel** is a defined set of antibodies with a fixed volume per tube (e.g. the CL1 tube uses 5 µl CD19, 5 µl CD20 …). A **cocktail** is a pre-mixed batch of a panel's antibodies, prepared in advance for a known number of tests. Mixing deducts the raw antibody stock once, up front; using the cocktail afterwards draws down the batch, not the raw stock.

**Samples and tubes.** The **Worklist** holds sample orders. Each sample has a lab ID and one or more **tubes**, each tube being a panel. When a sample is ordered, each tube reserves a test from a prepared cocktail. The **Bench station** — a tablet at the bench — walks each tube through its processing steps and records who did what and when.

**Shipments.** Every receipt carries the supplier's **shipment ID**. When an antibody arrives under a different shipment from the stock already in use, the system raises a **Shipment QC** task: the new shipment must be checked against the previous one, with evidence, before it is signed off.

**Traceability.** Because tubes, cocktails, antibody lots and shipments are linked, you can start from any tube and see the cocktail it was run on, the lots and shipments that went into that cocktail, and every other sample that shared them.

**Named staff on shared logins.** Bench PCs and tablets often share one login. Wherever it matters — mixing a cocktail, signing off a shipment, doing a processing step, commenting on a sample — the app asks you to pick **your name** from the staff list. It is never pre-filled, so one person's name cannot carry over onto someone else's work.

**Forecasting** projects when each antibody will run out from your recent consumption, counting both open inventory and unopened store vials as available supply.

---

## 2. First-time setup, logging in and roles

### First-time setup (administrator, once per installation)

A new installation has no user accounts. The first time anyone opens the app, it shows **Create your administrator account**. Choose a username and a strong password (email is optional) and save. You are then logged in as the administrator.

There are no default passwords. Keep the administrator credentials safe, and create a second administrator account under **Admin → Users** so you are not locked out if one password is lost.

Then, before staff start using the app:

1. **Admin → Staff** — add every technologist and pathologist by full name (see [Section 15](#15-administration)). These names appear in every "who is doing this?" picker.
2. **Admin → Users** — create login accounts. A shared technologist login for the bench PC and tablet is fine, because individuals are identified through the staff list.
3. **Admin → Antibody import** — load your antibody list from the template or a SAP export (or add antibodies one by one under **Admin → Antibodies**), including each antibody's standard **vial volume**.
4. **Admin → Panels** — define your tubes.
5. **Admin → Processing steps** — set the bench steps and wait times, or keep the built-in defaults.

### Logging in

Open the app in a browser at the address your administrator gives you — `http://localhost:8000` on the computer running the app, or something like `http://192.168.1.50:8000` from other computers on the lab network.

### Roles

| Role | Can do |
|---|---|
| **Technologist** | Receive stock, open vials, verify volumes, prepare and use cocktails, order and process samples, sign off shipment checks, log tests, view everything |
| **Admin** | Everything a technologist can, plus manage antibodies, panels, fluorochromes, users, staff, processing steps, alert rules, lab settings, imports and validation exports |

**Users vs Staff.** *Users* are login accounts. *Staff* are the people whose names are recorded against work. One shared login can be used by many staff members.

---

## 3. The Dashboard

The landing page gives an at-a-glance view of stock health.

- **Stock status table** — by default shows only antibodies running low (critical or warning). Click **Show all** to see every antibody, **Show low stock only** to collapse back. Click any row to see its depletion forecast.
- **Forecast chart** — projected consumption, a depletion date and a confidence band for the selected antibody. Store-stock vials are included.
- **Cocktail status panel** — active cocktail batches sorted by expiry. Rows turn amber when expiring within 3 days and red when expired.

Status colours throughout the app:
- **Green / OK** — comfortably stocked
- **Amber / warning** — approaching the alert threshold
- **Red / critical** — at or below the point where you should already have reordered

---

## 4. Store Stock

**Purpose:** track sealed vials before they are opened.

### Receiving vials

1. Go to **Store Stock** → **Receive vials**
2. Search and select the antibody (you can search by name or catalogue number)
3. Enter:
   - **Shipment ID** — required. The supplier's shipment, delivery or consignment reference. This is what drives Shipment QC, so enter it exactly as it appears on the paperwork.
   - **Lot No** — the manufacturer's lot number
   - **Qty (vials)** — how many sealed vials
   - **Vol per vial (µl)** — filled in automatically from the antibody's standard vial volume, and locked (see below)
   - **Vendor**, **Received date**, **Expiry date** — as applicable
4. Click **Receive to store**

If this antibody's previous stock came from a different shipment, a Shipment QC task is raised automatically (see [Section 6](#6-shipment-qc)).

### Standard vial volume and overrides

Most reagents ship in a fixed fill volume per catalogue number. Once an administrator has set the antibody's **Vial volume (µl)**, it is filled in automatically on every receipt and shown locked. If a delivery genuinely differs (e.g. a different pack size), you can enter a different volume, but you must give a **reason**; it is saved on the record as `[VOLUME OVERRIDE]`.

If no standard volume has been set, enter the volume from the vial label. There is no default — the app no longer assumes 500 µl.

### Opening a vial

When you take a vial to the bench, click **Open vial** on its row and confirm. This decrements the store quantity by one and creates a new open lot in **Inventory**, carrying the vial's volume, lot number and shipment ID across.

> **Why this matters:** if you always receive into Store Stock and open from there, your forecast and reorder alerts reflect everything you hold, and every open vial stays traceable to its shipment.

---

## 5. Inventory

**Purpose:** track open vials and their remaining volume.

The table lists every active open lot: antibody, vendor, fluorochrome, lot number, initial and current volume, percentage left, received and expiry dates, and when it was last physically verified.

### Receiving a lot directly

**Receive lot** adds an open lot without going through Store Stock — for example, legacy stock that was never tracked in the store. A **Shipment ID** is required, and the standard vial volume applies as in Store Stock. If the antibody has no store-stock record, an amber reminder appears; it does not block you.

### Bulk receive

**Bulk receive** shows all active antibodies in one table. Fill in shipment ID, lot number and volume for each one you are adding, optionally set a common received date, and submit. Blank rows are skipped. Useful for initial setup or a large delivery.

### Verifying a vial (important for accuracy)

When you physically measure a vial's remaining volume, click **Verify** and enter:

- **Measured volume (µl)**
- **Measurement method** — how you measured it
- **Pipette increment (µl, optional)** — the resolution of the pipette used
- **Verification cycle (optional)**

Verification corrects the system's estimate to the true value and records the difference, who verified it, and how. This is the basis of the accuracy reporting in the Validation export. **Verify vials whenever you measure them.**

### Deleting a lot

The bin icon deletes a lot. A lot with consumption history cannot be deleted (to preserve the audit trail) — set its volume to zero instead, or ask an administrator.

---

## 6. Shipment QC

**Purpose:** make sure a new shipment of an antibody performs like the one it replaces, and keep the evidence.

### When a task is raised

A verification task is created automatically when an antibody is received under a **shipment ID different from its previous stock** (including older stock that has no shipment ID recorded). There is one task per antibody per shipment. The first-ever receipt of an antibody raises none. If the lot number has also changed, the task is marked as a **lot change**, so your lot-to-lot acceptance criteria apply.

Each task has a **48-hour deadline**. A *shipment verification* alert is raised when the task is created, and a single *overdue* alert if the deadline passes. The **Shipment QC** item in the sidebar shows a badge: **amber** when tasks are open, **red** when any are overdue.

### Completing a verification

1. Open **Shipment QC** and select the task. It shows the antibody, the previous and new shipments, and the deadline.
2. **Attach evidence for both shipments** — at least one file for the **previous** shipment and one for the **new** shipment (e.g. overlay plots, comparison runs, QC reports). Accepted: PDF, images, Office documents, CSV and FCS files, up to 20 MB each. Each file's SHA-256 fingerprint is recorded.
3. Choose the outcome: **Acceptable** or **Not acceptable**. *Not acceptable* requires comments.
4. Choose **who is signing off** from the staff list, and click **Sign off**.

Sign-off stays disabled until evidence for both shipments is attached. **Closed records cannot be edited**, and closing a task acknowledges its alerts.

The Shipment QC page also exports the full audit log as CSV.

> Evidence files are stored in the `data/uploads` folder on the server. Backups must include the whole `data` folder, not just the database.

---

## 7. Panels and the Panel Designer

### Panels

(Admin) **Admin → Panels.** A panel defines which antibodies make up a tube and how much of each is used.

**Creating a panel**
1. **New panel** → enter a **name**, a **tube/panel code** (e.g. `CL1`), optionally a **test group** (e.g. `CLPD`), and a department
2. Save, then expand the panel row
3. **Add antibody** — search by marker, fluorochrome or clone. A marker search lists every fluorochrome variant (CD4-PE, CD4-APC, CD4-BV421 …); the search tells you if results were cut short. Set µl per tube and tubes per test.

**Test groups.** A clinical test often spans several tubes (e.g. CLPD = CL1 + CL2 + HCL). Give them the same test group so they are recognisably one protocol. Each tube remains its own panel for volume tracking.

**Editing volumes.** After a re-titration, expand the panel, click the pencil on the antibody row, edit µl/tube and tubes inline, and save. No need to recreate the panel.

**Processing steps per panel** can be set under **Admin → Processing steps** (see [Section 15](#15-administration)). Changing a panel's steps affects new orders only.

**Deleting.** The bin icon previews what will be removed. Panels with test history require a deliberate **force delete**.

### Panel Designer

**Panel Designer** helps build a new tube from the markers you need and the reagents you actually have in stock.

1. **Pick antibodies** — search and add the markers you want.
2. **Resolve design** — the designer assigns fluorochromes so that no two markers share a channel, using the antibodies available. It shows stock for each option, which clashes it resolved, and available alternatives. You can **Keep** or **Exclude** choices and re-run.
3. **Finalize** — review the final layout, enter the panel details (name, test code, optional test group and department, volume per tube) and create the panel. It then appears under **Admin → Panels** like any other.

---

## 8. Cocktails

**Purpose:** prepare a batch mix in advance and track its use.

### Preparing a cocktail

1. **Cocktails → Prepare cocktail**
2. Choose the panel and the number of tests
3. Choose **who is mixing** from the staff list (required)
4. The pre-flight check shows the µl of each antibody required and warns if any is short, naming the antibodies and the deficit
5. Confirm — the raw antibody stock is deducted once and the batch is created with a unique **cocktail code**

Preparation takes account of tests already **reserved by the worklist**, so a new batch is not counted against stock that is already promised.

### Printing a worksheet

**Worksheet** on a cocktail row opens a print-ready sheet listing each antibody with the **lot and shipment used**, the volume per test and for the batch, checkboxes and sign-off lines. Print or save as PDF for your records.

### Using a cocktail

- **Through the worklist (recommended)** — when a sample is ordered, each tube reserves a test from a prepared cocktail of its panel, and the bench station uses it at the first step. The sample's lab ID is linked to the cocktail.
- **Cocktails → Log tests** — draws tests from the batch without lab IDs. Use only when you cannot use the worklist: these tests cannot be traced to individual samples, and the cocktail trace reports how many such untracked tests exist.

Using a cocktail draws down the batch. It does **not** deduct raw antibody stock again.

### Cocktail trace

Click **Trace** on a cocktail (or the cocktail code on any worklist tube) to see:
- every sample run on that cocktail (the sample you came from is highlighted)
- the antibody **lots and shipments** that went into it
- other cocktails drawn from the same lots

You can copy the list of lab IDs or export it as CSV — useful when a reagent or shipment problem is suspected and you need to know which samples were affected. Sample comments and flags appear in the trace, which helps separate sample problems from reagent problems.

### Preparation log and export

The **Preparation log** on the Cocktails page lists every batch prepared, filterable by date, panel and person, with a trace link on each row. Older batches prepared before staff names were introduced show the login name, marked "(login)".

**Export summary** downloads a CSV of cocktails in a date range: cocktail code, panel, prepared date and time, preparer, total tests, tests used, remaining and expiry.

---

## 9. Worklist

**Purpose:** order samples, reserve their reagents, follow them through processing and record turnaround time (TAT).

### Ordering a sample

1. Go to **Worklist**
2. **Scan or type the accession** (lab ID)
3. Set **Priority** — routine or urgent
4. Choose the **Requesting pathologist** and **Processing technologist** from the staff list
5. **Add a tube…** for each panel the sample needs
6. Add **Notes (optional)**, e.g. "urgent — clinician called"
7. **Add to queue**

For each tube, the app tries to reserve one test from a prepared cocktail of that panel. The tube then shows **Cocktail test reserved**, or **No cocktail available — will be flagged** if none is ready — prepare one, or the tube will be processed without a cocktail link.

### Following a sample

Samples move through **In queue → Processing → Completed** (or **Cancelled**). Each tube shows its progress, e.g. *2/4 → Incubated*. The normal way to move tubes forward is the [Bench station](#10-bench-station).

The worklist **Start** and **Complete** buttons remain as a fallback. **Complete** asks for confirmation, because it marks every remaining step done and skips step timers. Completing a sample records its TAT.

**Cancelling** a sample that is partly processed releases the cocktail reservations of tubes that have not started.

Use **Find lab ID (all dates)…** to find any sample, past or present.

### Sample comments and flags

Click a sample's comment/flags control to open the editor:

- **Sample flags** — one-tap toggles: **Fibrin threads**, **Low volume**, **Lyse issue**
- **Comment** — free text, with quick picks: Clotted, Degenerated / poor viability, Low cell count, Haemolysed, Diluted / haemodilute
- **Who is entering this?** — required, never pre-filled

Comments and flags can be edited at any status, including completed. They appear under the lab ID in the worklist (the name shows on hover), on the bench station ticket, in the cocktail trace, and in the CSV export.

### Export

**Export TAT** downloads the worklist for a date range as CSV, including turnaround times, sample flags (`sample_flags`), comments and who entered them (`comment_by`).

---

## 10. Bench station

**Purpose:** a full-screen view for a touchscreen tablet (or any screen) at the processing bench. Built for gloved hands: large buttons, no typing.

### Setting up the tablet

1. On the tablet's browser, open `http://<server address>:8000/station` (the server must be started for network use — see [Section 16](#16-starting-stopping-and-looking-after-the-app))
2. Sign in with a **technologist** login. The tablet then stays signed in for 30 days. Administrator logins are deliberately not given this long session.
3. Bookmark the page or add it to the home screen

### Choosing the operator

Tap **Tap to choose who is processing** at the top and pick your name. Every step and flag is recorded against the operator shown. Buttons stay disabled until an operator is chosen. **Change the operator when you hand over the bench.** If the list is empty, an administrator needs to add technologists under **Admin → Staff**.

### Tickets

Every pending worklist sample appears as a ticket — urgent samples first, then the longest waiting. New orders appear automatically. Each ticket shows a waiting timer that turns **amber at 30 minutes** and **red at 60 minutes**.

### Doing the steps

Each tube has its own sequence of steps — from its panel's settings, the lab default, or the built-in list: **Cocktail added → Incubated → Lysed & washed → Acquired**.

- Steps must be done **in order**. Tap the next step's button when you have done it.
- **Step 1 uses the tube's reserved cocktail test** and marks the sample as started.
- When several tubes of one sample are at the same step, an **"All N tubes: <step>"** button does them together.
- When every tube is finished, the sample is completed (TAT recorded) and moves to **Just finished** for 15 minutes.

**Undo:** the most recent step of a tube can be undone within 10 minutes. Undoing step 1 exactly reverses the cocktail use.

### Step timers

A step can have a **wait time** — the minimum minutes after the previous step before it is due (e.g. *Incubated = 15*). The step's button then counts down:

- **Green with a chime** when the time is up
- An **alarm** that continues until someone taps **OK** or does the step: a flashing screen edge, a banner naming the sample and step, a flashing ticket outline, a chime every 30 seconds, and vibration on Android tablets
- **Amber** once the step has been ready for 10 minutes or more — a warning of possible over-incubation

Tapping a step before its time is up asks for confirmation, and the early completion is recorded against the step. Countdowns use the server's clock, so a tablet with the wrong time still counts correctly. The chime can be switched on or off with the chime button on the station.

> Most browsers only allow sound after the screen has been touched once. Tap anywhere on the station after opening it so the chime can play.

### Sample flags on the bench

Every ticket has three large toggles: **Fibrin threads**, **Low volume**, **Lyse issue**. Tap to set, tap again to clear. A set flag shows as a filled button with a tick. Flags are recorded against the current operator and appear in the worklist, the cocktail trace and the CSV.

---

## 11. Test Log

**Purpose:** record tests that were **not** ordered through the worklist — for example, historical data, LIMS imports or one-off runs. Tests processed through the worklist and bench station are already recorded; do not log them again here.

The **Log Tests** form has three modes:

### From Panel
Select a panel and a count. The form previews the total µl of each antibody to be deducted. Submitting deducts **every** antibody in the panel (FIFO). If any is short, the shortfall is reported once, in full, and recorded in the test log notes with a `[STOCK SHORTFALL]` marker — nothing is silently skipped.

### From Cocktail
Select a prepared cocktail and a count. Deducts from the cocktail batch (not raw stock). Warns if you request more tests than the batch has left. As with **Cocktails → Log tests**, these tests carry no lab IDs.

### Ad hoc / Custom Test
For one-off combinations not saved as a panel. Add antibodies individually, set µl per patient for each, give the run a label and submit. Deducts raw stock by FIFO. Shows in the history with an **AD HOC** tag.

### CSV import
Bulk-import historical or LIMS-exported runs:
```
date,test_code,count,notes
2026-05-01,CL1,12,Morning batch
```
`test_code` must match a panel's test code exactly.

### History
The table below the form lists recent runs from all sources, with panel/cocktail/label, count, entry method and lots deducted.

---

## 12. Alerts

The bell in the sidebar shows the current alert count. The Alerts page lists:

- **Shortage** — projected to run out within the alert threshold
- **Expiry** — a lot expiring soon
- **Substitute** — when an antibody is short, available alternatives (set in the antibody master) are suggested
- **Cocktail expiry** — a prepared cocktail nearing expiry
- **Shipment verification** — a new shipment needs checking (see [Section 6](#6-shipment-qc))
- **Shipment verification overdue** — the 48-hour deadline has passed

Alerts are de-duplicated within a 24-hour window. Shipment alerts are acknowledged automatically when the verification is signed off.

How shortage is calculated (defaults, all admin-configurable):
- **Lead time** — 35 days (how long reordering takes)
- **Alert threshold** — 42 days (start warning when projected stock-out is within this window)
- **Safety stock** — 0 µl (a buffer kept in reserve)

Set these globally (**Admin → Alert Rules**) or per antibody.

---

## 13. Orders

Track what you have ordered so that reordering prompted by alerts is followed through to receipt. When an order is delivered, record the **shipment ID**; the antibody's standard vial volume applies as with any receipt, and a Shipment QC task is raised if the shipment is new for that antibody.

---

## 14. Exports and reports

| Where | Export | Contents |
|---|---|---|
| Inventory | **Export CSV** | All open lots with volumes and dates |
| Inventory | **Stock report** | Stores-facing summary: per-antibody current stock, oldest expiry, reorder flag (no internal IDs) |
| Antibodies | **Export CSV** | Antibody master list |
| Panels | **Export CSV** | Panels with their antibody components and volumes |
| Cocktails | **Export summary** | Cocktails prepared in a date range, with code and preparer |
| Cocktails | **Worksheet** | Printable preparation sheet, with lot and shipment per antibody |
| Cocktail trace | **Export CSV** | Samples run on a cocktail, with its lots and shipments |
| Worklist | **Export TAT** | Samples, tubes, turnaround times, flags, comments and who entered them |
| Shipment QC | **Audit log CSV** | All verification tasks, outcomes, sign-offs and evidence fingerprints |
| Admin → Validation | Three CSVs | Verification accuracy, alert effectiveness, usage summary |

CSV filenames include the date and time of export, so they double as dated snapshots.

---

## 15. Administration

(Admin only.)

- **Antibody import** — load the antibody master list from a CSV or Excel (.xlsx) file. Older .xls files must be saved as .xlsx first. Two formats are accepted:
  - **The flowjAI template** — click **Download template** on the import page. One row per antibody: Antibody Name, Fluorochrome Name, Catalogue No, Manufacturer, **Vial Volume uL** (the standard fill volume of one vial) and an optional Description. Delete the example rows before importing.
  - **A SAP materials export** — antibody and fluorochrome are read from the Short Text; Kit Size with Alternative UOM = MICRO is read as the vial volume in µl; instrument reagents (Alternative UOM = LITRE) are skipped.

  The import shows a **preview** first: check the recognised antibody and fluorochrome for each row, correct any that were misread, then import. Antibodies whose catalogue number already exists are not duplicated; if such an antibody has no standard vial volume yet, the import fills it in (a volume already set is never changed).
- **Lab Settings** — the lab name and subtitle shown in the sidebar, and a guide to the address other computers and the tablet should use.
- **Fluorochromes** — the fluorochrome list used when defining antibodies.
- **Antibodies** — the master list. Create, edit (pencil), activate/deactivate, set alternatives (for substitute suggestions), sort by any column, and force-delete with a cascade preview.
  - **Vial volume (µl)** — the standard fill volume for this catalogue number, used automatically on every receipt (see [Section 4](#4-store-stock)).
  - **Volume check** — lists open lots and store vials whose starting volume differs from the standard. **Correct** sets the starting volume to the standard and shifts the remaining volume by the same amount — unless the lot has been physically verified, in which case the remaining volume is a measurement and is left alone. **Keep** confirms a genuinely non-standard vial. Antibodies with no standard volume can be filled in directly from this list. Standard volumes apply to new receipts automatically; older records change only when you correct them here.
- **Users** — login accounts (technologist or admin); reset passwords.
- **Staff** — the people whose names are recorded against work. Add each person's **Full name**, optional **Initials**, and **Role** (Technologist or Pathologist). Technologists appear in the mixing, sign-off, bench-operator and comment pickers; pathologists in the worklist's requesting-pathologist picker.
- **Processing steps** — the bench steps for each tube. Set a **Lab default** sequence and, where needed, a different sequence per panel. Each step can have a **wait time** in minutes, which drives the bench station timers. **Reset to built-in** restores *Cocktail added → Incubated → Lysed & washed → Acquired*. Each tube keeps the steps it was ordered with, so changes affect new orders only. Administrators can also reach this from the gear on the bench station.
- **Alert Rules** — global defaults (lead time, threshold, safety stock) and per-antibody overrides.
- **Validation** — accuracy and effectiveness exports for QA or publication.

---

## 16. Starting, stopping and looking after the app

This section is for whoever looks after the computer running flowjAI. Full installation instructions are in the [README](README.md).

### Starting and stopping

| Installation | Start | Stop |
|---|---|---|
| Windows packaged app | `Start flowjAI.bat` (or double-click `flowjai-inventory.exe`) | `stop.bat` |
| Windows with Python | `launch.bat` | Close its window, or `stop.bat` |

If you start the app with `launch.bat`, **do not click inside its window** — Windows pauses the app while text there is selected, which looks as if it has frozen.

`Start flowjAI.bat` and `launch.bat` start the app for network use, so other computers and the bench tablet can connect. Double-clicking the `.exe` keeps whichever setting was used last.

### Running in the background (recommended)

`install-autorestart.bat` makes the app run hidden, restart daily at a time you choose, and restart automatically if it stops responding (a watchdog checks every 2 minutes). Use `start-background.bat` and `stop.bat` to start and stop it; `stop.bat` also pauses the watchdog so the app stays stopped for maintenance. `uninstall-autorestart.bat` removes it.

If `stop.bat` reports "Access is denied", the app was started with administrator rights: right-click `stop.bat` → **Run as administrator**.

Set the server computer's sleep setting to **Never**.

### Backups

Everything lives in the `data` folder next to the app: the database, Shipment QC evidence (`data/uploads`), settings and logs. To back up, stop the app and copy the **whole `data` folder**.

### Moving to another computer, or upgrading

Do **not** copy `flowjai.db` by hand — a manual copy can miss the most recent records. Instead, set up the new copy of the app, then **drag the old app folder onto `transfer-db.bat`** in the new one. It stops the app, copies the database safely, backs up anything it replaces, checks the record counts match, and starts the app. Database upgrades run automatically on start; if one fails, the app refuses to start rather than risk your data.

---

## 17. The daily workflow

A typical day:

1. **Dashboard** — anything red or amber needs attention.
2. **Alerts and Shipment QC** — act on shortages (raise an order), expiries, and any open or overdue shipment checks.
3. **Receive deliveries** into **Store Stock**, with the shipment ID from the paperwork.
4. **Open vials** from Store Stock as you start using them.
5. **Prepare cocktails** for the day's panels, choosing your name; print the worksheet for the file.
6. **Order samples** on the **Worklist** as they arrive, so each tube reserves its cocktail test.
7. **Process at the bench station** — choose yourself as operator, do the steps in order, flag sample problems as you see them.
8. **Verify** any vial you physically measure.

Steps 6–8, done consistently, are what make the forecast, TAT figures and traceability trustworthy.

---

## 18. Troubleshooting

**The setup page appears instead of the login page** — this is a new, empty installation. If you expected existing data, the app is probably running from a different folder from the one that holds your `data` folder. Check which folder you started it from before creating an account.

**Other computers or the tablet can't connect** —
- The app must have been started for network use (`Start flowjAI.bat`, `launch.bat`, or the `.exe` run once with `--lan`).
- Windows Firewall on the server must allow TCP port 8000 from the local network. `Start flowjAI.bat` and `launch.bat` add this rule if run with administrator rights.
- Use the address shown in **Lab Settings**, including `:8000`.
- The server computer must be on and not asleep.

**The bench station says "Can't reach the flowjAI server. Retrying…"** — the tablet has lost contact with the server. Check the server computer is on and the app running; the station reconnects by itself.

**The tablet keeps asking me to log in** — sign in with a technologist login. Administrator logins do not get the 30-day station session.

**The step-timer chime doesn't sound** — tap the screen once after opening the station (browsers block sound until then), and check the chime button is on and the tablet isn't muted.

**"flowjAI — database upgrade failed"** — after an update, a database upgrade could not be applied, so the app did not start. **Your data has not been changed.** The reason is shown in the error message and in `data/flowjai.log` (packaged app or background service), or in the `launch.bat` window (Python install). Keep the old version's folder and report the error.

**Screens are empty after moving the database** — the database was probably copied by hand. Use `transfer-db.bat` from the original folder as described in [Section 16](#16-starting-stopping-and-looking-after-the-app).

**Shipment QC sign-off button is greyed out** — evidence must be attached for **both** the previous and the new shipment, and a name chosen for sign-off.

**A page shows old behaviour after an update** — press **Ctrl + F5** to reload without the browser cache.

**Forecast says "insufficient data"** — the antibody needs some logged consumption history before a projection is possible. It fills in after a couple of weeks of use.

**Antibody import says it cannot read the file** — save the file as .xlsx or .csv (not the older .xls), and check it has either an *Antibody Name* column or a SAP *Short Text* / *Description* column. Starting from the downloaded template avoids most problems.

---

## Getting help

Email **feedback.flowjai@gmail.com** or open an issue at [github.com/ananthvikas/flowjai-inventory/issues](https://github.com/ananthvikas/flowjai-inventory/issues). Say which version you are using (shown on the **About** page) and what you were doing. **Never send the database, patient identifiers or lab IDs.**

---

*flowjAI Inventory Manager — designed and built by Ananthvikas Jayaram. Open source under the MIT licence.*
