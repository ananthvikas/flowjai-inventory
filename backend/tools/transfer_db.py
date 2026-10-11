"""
tools/transfer_db.py — copy a flowjAI database into this installation, safely.

    python tools/transfer_db.py SOURCE [--target PATH] [--port 8000]

SOURCE is a flowjai.db file, or an app folder (its data/flowjai.db is used).

Why not just copy the file?
  flowjAI runs SQLite in WAL mode, so the live data is flowjai.db PLUS
  flowjai.db-wal / flowjai.db-shm. Copying only flowjai.db can
    * miss the newest records, which may still be in the source's -wal file
      (always the case after a force-close), and
    * corrupt the copy: a leftover -wal next to the TARGET belongs to the old
      database and gets replayed into the new file on next open.
This tool uses SQLite's backup API (a consistent copy that includes any WAL
content), removes stale -wal/-shm at the target, backs up whatever it replaces,
and verifies the result. The server must be stopped first (transfer-db.bat
does that).
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve()
APP_ROOT = HERE.parents[2]
DEFAULT_TARGET = APP_ROOT / "data" / "flowjai.db"

COUNT_TABLES = [
    ("antibodies", "antibodies"),
    ("cocktails", "cocktails"),
    ("sample_orders", "worklist orders"),
    ("stock_lots", "stock lots"),
    ("users", "users"),
]


def fail(msg: str) -> None:
    print(f"\n  ERROR: {msg}\n")
    sys.exit(1)


def resolve_source(arg: str) -> Path:
    p = Path(arg.strip('"')).expanduser().resolve()
    if p.is_dir():
        for cand in (p / "data" / "flowjai.db", p / "flowjai.db"):
            if cand.is_file():
                return cand
        fail(f"No flowjai.db found in {p} or {p / 'data'}")
    if not p.is_file():
        fail(f"{p} does not exist")
    return p


def server_running(port: int) -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3)
        return True
    except Exception:
        return False


def summary(db: Path) -> dict:
    con = sqlite3.connect(str(db))
    try:
        out = {"integrity": con.execute("PRAGMA integrity_check").fetchone()[0]}
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for t, label in COUNT_TABLES:
            out[label] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] if t in tables else "-"
        out["schema version"] = (
            con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            if "alembic_version" in tables else "none"
        )
        out["_is_flowjai"] = {"antibodies", "users"} <= tables
        return out
    finally:
        con.close()


def sqlite_copy(src: Path, dst: Path) -> None:
    """Consistent copy via the backup API (includes committed WAL content)."""
    s = sqlite3.connect(str(src))
    d = sqlite3.connect(str(dst))
    try:
        s.backup(d)
        d.execute("PRAGMA journal_mode=DELETE")   # leave a single self-contained file
    finally:
        d.close()
        s.close()


def remove_sidecars(db: Path) -> None:
    for sfx in ("-wal", "-shm", "-journal"):
        f = db.with_name(db.name + sfx)
        if f.exists():
            f.unlink()


def main(argv=None) -> None:
    """argv lets the packaged .exe call this directly (run.py --transfer-db)."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("--target", default=str(DEFAULT_TARGET))
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args(argv)

    source = resolve_source(args.source)
    target = Path(args.target).resolve()
    if source == target:
        fail("Source and target are the same file.")
    if server_running(args.port):
        fail(f"flowjAI is still running on port {args.port}. Stop it first (stop.bat).")

    print(f"\n  Source: {source}")
    src_info = summary(source)
    if not src_info.pop("_is_flowjai"):
        fail("Source doesn't look like a flowjAI database.")
    if src_info["integrity"] != "ok":
        fail(f"Source database failed its integrity check: {src_info['integrity']}")
    for k, v in src_info.items():
        print(f"    {k:<16} {v}")

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        backups = target.parent / "backups"
        backups.mkdir(exist_ok=True)
        bk = backups / f"before-transfer-{datetime.now():%Y%m%d-%H%M%S}.db"
        try:
            sqlite_copy(target, bk)
            print(f"\n  Current database backed up to {bk}")
        except sqlite3.Error as e:
            # A damaged target can't go through the backup API; keep the raw files instead
            for f in [target] + [target.with_name(target.name + s) for s in ("-wal", "-shm")]:
                if f.exists():
                    shutil.copy2(f, backups / (bk.name + f.name[len(target.name):]))
            print(f"\n  Current database copied as raw files to {backups} ({e})")

    tmp = target.with_name(target.name + ".incoming")
    remove_sidecars(tmp)
    if tmp.exists():
        tmp.unlink()
    sqlite_copy(source, tmp)

    remove_sidecars(target)          # stale -wal/-shm would be replayed into the new file
    if target.exists():
        target.unlink()
    tmp.replace(target)

    new_info = summary(target)
    new_info.pop("_is_flowjai")
    print(f"\n  Target: {target}")
    for k, v in new_info.items():
        print(f"    {k:<16} {v}")
    mismatched = [k for k in new_info if k != "integrity" and new_info[k] != src_info[k]]
    if new_info["integrity"] != "ok" or mismatched:
        fail(f"Copy doesn't match the source ({', '.join(mismatched) or new_info['integrity']}). "
             f"Your previous database is in data\\backups.")
    print("\n  Transfer OK. Start the app - it will apply any database upgrades on start.\n")


if __name__ == "__main__":
    main()
