"""
run.py — Entry point for the PyInstaller-packaged flowjAI Inventory Manager.

Double-click behaviour (frozen):
  - No terminal window (--windowed)
  - Browser opens automatically at http://localhost:8000
  - Database lives in data/flowjai.db next to the .exe
  - Alembic migrations run automatically on every start; if they FAIL the app
    shows an error and does not start (starting on a half-upgraded database
    gives silently empty screens)
  - If flowjAI is already running, it just opens the browser

Options:
  --lan           Accept connections from other PCs / the bench tablet. The choice
                  is remembered (data/network.txt), so a plain double-click keeps it.
  --local         Back to this-PC-only.
  --no-browser    Don't open a browser tab (used by the watchdog's daily restart).
  --demo          Seed demo data (evaluation only).
  --transfer-db SOURCE
                  Copy a database from another install into this one safely,
                  then exit. Output goes to data/logs/transfer.log.

Dev mode (python run.py):
  - Same behaviour as the original launch sequence
"""

import io
import os
import sys
import threading
import webbrowser
from pathlib import Path


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _is_frozen() -> bool:
    return getattr(sys, 'frozen', False)


def _app_dir() -> Path:
    """Directory containing the .exe (frozen) or this script (dev)."""
    if _is_frozen():
        return Path(sys.executable).parent.resolve()
    return Path(__file__).resolve().parent


def _bundle_dir() -> Path:
    """Root of bundled assets (sys._MEIPASS in frozen, project root in dev)."""
    if _is_frozen():
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Environment setup (must happen before any app imports)
# ---------------------------------------------------------------------------

def setup_environment():
    app_dir = _app_dir()
    data_dir = app_dir / "data"
    data_dir.mkdir(exist_ok=True)

    db_path = data_dir / "flowjai.db"
    db_url = f"sqlite:///{db_path.as_posix()}"

    os.environ["DATABASE_URL"] = db_url
    # Demo seed runs only when --demo is passed (sets FLOWJAI_DEMO=1).
    # A fresh install starts empty and drives first-run admin setup instead.

    print(f"[flowjai] Data directory : {data_dir}")
    print(f"[flowjai] Database URL  : {db_url}")
    return app_dir, data_dir, db_url


# ---------------------------------------------------------------------------
# Small helpers for the windowed .exe (no console to print to)
# ---------------------------------------------------------------------------

def _message_box(title: str, text: str, error: bool = True) -> None:
    """Show a Windows message box when frozen; print otherwise."""
    if _is_frozen() and sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, text, title, 0x10 if error else 0x40)
            return
        except Exception:
            pass
    print(f"[flowjai] {title}: {text}", file=sys.__stderr__ or sys.stderr)


def _already_running(port: int = 8000) -> bool:
    import urllib.request
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3)
        return True
    except Exception:
        return False


class RotatingLogStream(io.TextIOBase):
    """stdout/stderr replacement that can never fill the disk.

    Rotates flowjai.log -> flowjai.log.1 -> .2 -> .3 whenever it passes
    max_bytes, WHILE running (the old code only checked at start-up, so one long
    run with a repeating error could grow without limit - one reached 44 GB).
    Identical lines repeated back-to-back are collapsed into a single
    "[previous line repeated N times]" note, so an error loop costs a few bytes
    per second instead of megabytes.
    """

    def __init__(self, path: Path, max_bytes: int, backups: int = 3):
        super().__init__()
        self.path, self.max_bytes, self.backups = path, max_bytes, backups
        self._lock = threading.Lock()
        self._last = None
        self._repeats = 0
        self._partial = ""
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("a", encoding="utf-8", errors="replace")

    def _rotate(self):
        self._fh.close()
        for i in range(self.backups, 0, -1):
            src = self.path.with_name(f"{self.path.name}.{i - 1}") if i > 1 else self.path
            dst = self.path.with_name(f"{self.path.name}.{i}")
            if src.exists():
                try:
                    src.replace(dst)
                except OSError:
                    pass
        self._fh = self.path.open("a", encoding="utf-8", errors="replace")

    def _emit(self, line: str):
        if line == self._last:
            self._repeats += 1
            return
        if self._repeats:
            self._fh.write(f"[previous line repeated {self._repeats} more times]\n")
            self._repeats = 0
        self._last = line
        self._fh.write(line)
        if self._fh.tell() > self.max_bytes:
            self._rotate()

    def write(self, text: str) -> int:
        with self._lock:
            data = self._partial + text
            lines = data.split("\n")
            self._partial = lines.pop()
            for ln in lines:
                self._emit(ln + "\n")
            if len(self._partial) > 64 * 1024:     # runaway output without newlines
                self._emit(self._partial + "\n")
                self._partial = ""
            self._fh.flush()
        return len(text)

    def flush(self):
        with self._lock:
            self._fh.flush()

    def isatty(self):
        return False

    def writable(self):
        return True


def _log_max_bytes() -> int:
    try:
        return int(float(os.getenv("FLOWJAI_LOG_MAX_MB", "10")) * 1024 * 1024)
    except ValueError:
        return 10 * 1024 * 1024


def _open_log(path: Path, max_bytes: int = 10 * 1024 * 1024):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > max_bytes:
        path.replace(path.with_suffix(path.suffix + ".1"))
    return path.open("a", encoding="utf-8", buffering=1)


def run_transfer(source: str, data_dir: Path) -> int:
    """--transfer-db: bring another install's database into this one."""
    log_path = data_dir / "logs" / "transfer.log"
    if log_path.exists():
        log_path.unlink()
    log = _open_log(log_path)
    sys.stdout = sys.stderr = log
    backend_dir = _bundle_dir() / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    from tools.transfer_db import main as transfer_main
    try:
        transfer_main([source, "--target", str(data_dir / "flowjai.db")])
        return 0
    except SystemExit as e:
        return int(e.code or 0)
    finally:
        log.flush()


# ---------------------------------------------------------------------------
# Database initialisation (schema + Alembic migrations)
# ---------------------------------------------------------------------------

_LAST_DB_ERROR = ""


def initialize_database(bundle_dir: Path) -> bool:
    """Create the schema on a fresh install and apply migrations on upgrades.

    Fresh install (no tables yet): build the full schema from the models and
    stamp Alembic at head, so the first run never attempts migrations against a
    non-existent table (the old "no such table: panels" warning) and future
    upgrades apply cleanly.

    Existing install: apply any pending migrations.

    Returns False if the database could not be brought up to date.
    """
    try:
        from sqlalchemy import inspect

        # Importing app.models registers every table on SQLModel.metadata,
        # which create_db_and_tables() relies on.
        import app.models  # noqa: F401
        from app.database import create_db_and_tables, engine

        from alembic.config import Config
        from alembic import command

        alembic_ini = bundle_dir / "backend" / "alembic.ini"
        migrations_dir = bundle_dir / "backend" / "migrations"

        cfg = None
        if alembic_ini.exists():
            cfg = Config(str(alembic_ini))
            cfg.set_main_option("script_location", str(migrations_dir))
            cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])

        # alembic_version alone means an earlier launcher ran migrations against an
        # empty database and failed part-way - no app tables exist, so treat it as fresh.
        tables = [t for t in inspect(engine).get_table_names() if t != "alembic_version"]

        if not tables:
            # Fresh database — create the schema from the models, then stamp head.
            # force=True: no app tables exist, so creating them cannot clash with a
            # migration (create_db_and_tables otherwise skips once alembic_version exists).
            create_db_and_tables(force=True)
            if cfg is not None:
                command.stamp(cfg, "head")
                print("[flowjai] Fresh database initialised and stamped at head")
            else:
                print("[flowjai] Fresh database initialised (no alembic.ini)")
        elif cfg is not None:
            command.upgrade(cfg, "head")
            print("[flowjai] Migrations applied (or already up to date)")
        else:
            print("[flowjai] alembic.ini not found - cannot check the database version")
            return False
        return True
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[flowjai] DATABASE UPGRADE FAILED: {e}")
        global _LAST_DB_ERROR
        _LAST_DB_ERROR = str(e).splitlines()[0][:300] if str(e) else type(e).__name__
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(description="flowjAI Inventory Manager")
    parser.add_argument("--demo", action="store_true", help="Seed demo data (dev/eval only)")
    parser.add_argument("--lan", action="store_true", help="Listen on 0.0.0.0 (LAN) and remember it")
    parser.add_argument("--local", action="store_true", help="Listen on 127.0.0.1 only and remember it")
    parser.add_argument("--no-browser", action="store_true", help="Don't open a browser tab")
    parser.add_argument("--transfer-db", metavar="SOURCE", help="Copy a database from another install, then exit")
    parser.add_argument("--log-file", action="store_true",
                        help="Write output to data/flowjai.log (size-capped). Always on for the .exe")
    args, _ = parser.parse_known_args()

    # A production install never auto-seeds. Demo data requires an explicit flag.
    if args.demo:
        os.environ["FLOWJAI_DEMO"] = "1"
    os.environ["ENVIRONMENT"] = "production"

    app_dir, data_dir, db_url = setup_environment()
    bundle_dir = _bundle_dir()

    if args.transfer_db:
        sys.exit(run_transfer(args.transfer_db, data_dir))

    # Double-clicked while already running: don't start a second copy (it would
    # fail on port 8000 and, worse, run migrations against a live database).
    if _already_running():
        if not args.no_browser:
            webbrowser.open("http://localhost:8000")
        return

    # Network choice persists so a plain double-click keeps the tablet working.
    net_file = data_dir / "network.txt"
    if args.lan:
        net_file.write_text("lan", encoding="utf-8")
    elif args.local and net_file.exists():
        net_file.unlink()
    lan = net_file.exists() and net_file.read_text(encoding="utf-8").strip() == "lan"

    # When running as --windowed .exe, sys.stdout/stderr are None.
    # uvicorn's logging crashes on None stdout, so redirect to a log file.
    if _is_frozen() or args.log_file:
        log_file = RotatingLogStream(app_dir / "data" / "flowjai.log", _log_max_bytes())
        sys.stdout = log_file
        sys.stderr = log_file
        print(f"[flowjai] Output -> data/flowjai.log (rotates at {_log_max_bytes() / (1024 * 1024):g} MB, 3 old copies kept)")

    # Ensure backend/ is on sys.path so 'from app.xxx' imports resolve
    backend_dir = bundle_dir / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    # Initialise the DB (fresh schema or pending migrations) before the app starts
    if not initialize_database(bundle_dir):
        _message_box(
            "flowjAI - database upgrade failed",
            "The database could not be upgraded, so flowjAI has not started "
            f"(your data has not been changed).\n\nReason: {_LAST_DB_ERROR}\n\n"
            "Full details are in data\\flowjai.log next to flowjai-inventory.exe.",
        )
        sys.exit(1)

    # Open browser after a short delay (gives the server time to bind)
    def _open_browser():
        import time
        time.sleep(1.5)
        webbrowser.open("http://localhost:8000")

    if not args.no_browser:
        threading.Thread(target=_open_browser, daemon=True).start()

    # Start uvicorn (blocking — runs until the user closes the .exe)
    import uvicorn
    from app.main import app  # noqa: E402 — sys.path set above

    host = "0.0.0.0" if lan else "127.0.0.1"
    print(f"[flowjai] Starting server at http://localhost:8000 (bind {host})")
    uvicorn.run(app, host=host, port=8000, log_level="info")


if __name__ == "__main__":
    main()
