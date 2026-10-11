flowjAI Inventory Manager - packaged version
============================================

No Python or other software needs to be installed on this PC.

FIRST TIME ON THIS PC
  1. Put this whole folder somewhere local, e.g. C:\flowjAI
     (NOT OneDrive or a synced Desktop - syncing a live database can corrupt it).
  2. Right-click "Start flowjAI.bat" > Run as administrator (only the first time,
     so it can allow the tablet and other PCs through the firewall).
     The browser opens at http://localhost:8000.
  3. Optional but recommended: run install-autorestart.bat
     (runs flowjAI in the background, restarts it daily, and restarts it if it hangs).
  4. Set this PC's sleep to "Never" (Settings > Power).

BRINGING DATA FROM ANOTHER PC OR FOLDER
  Drag the OLD app folder (or its flowjai.db) onto transfer-db.bat.
  Never copy flowjai.db by hand - see the release notes for why.

EVERYDAY
  Open http://localhost:8000 (this PC) or http://<this PC's address>:8000 (others,
  and the bench tablet at /station).
  stop.bat stops it (and pauses the watchdog); "Start flowjAI.bat" starts it again.

UPDATING TO A NEW BUILD
  1. stop.bat
  2. Delete everything in this folder EXCEPT the data folder.
  3. Copy the new build's files in. Start as usual - database upgrades run by themselves.

HELP
  feedback.flowjai@gmail.com  or  https://github.com/ananthvikas/flowjai-inventory/issues
  Never send the database or patient details.

WHERE THINGS ARE
  data\flowjai.db       the database (with flowjai.db-wal / -shm while running)
  data\uploads\         shipment QC evidence files
  data\flowjai.log      the app's log
  data\logs\            watchdog and transfer logs
