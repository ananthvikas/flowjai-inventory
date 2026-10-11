"""
main.py — FastAPI application factory.

Startup sequence:
  1. Create all DB tables (idempotent).
  2. Run seed if DB is empty (dev/demo convenience).
  3. Mount all routers.
  4. Configure CORS for local frontend dev (localhost:3000 / 5173).
"""

import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.database import create_db_and_tables
from app.routers import (
    export,
    store_stock,
    alert_rules,
    alerts,
    antibodies,
    auth,
    cocktails,
    fluorochromes,
    forecast,
    lab_settings,
    orders,
    panel_designer,
    panels,
    sample_orders,
    sap_import,
    shipment_verifications,
    station,
    staff,
    stock,
    tests,
    users,
    validation,
)

app = FastAPI(
    title="FlowJAI Inventory Manager",
    description="Flow cytometry antibody inventory management — open source, self-hosted.",
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# CORS — allow the React frontend (dev: Vite port 5173, prod: same origin)
# ---------------------------------------------------------------------------
allowed_origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]
if os.getenv("FRONTEND_ORIGIN"):
    allowed_origins.append(os.getenv("FRONTEND_ORIGIN"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
def on_startup():
    create_db_and_tables()
    # Demo seed runs only when explicitly requested (e.g. `python run.py --demo`).
    # A fresh install starts empty and drives first-run admin setup instead.
    if os.getenv("FLOWJAI_DEMO") == "1":
        try:
            from app.seed import seed
            seed()
        except Exception as e:
            print(f"Seed skipped or failed: {e}")


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(fluorochromes.router)
app.include_router(antibodies.router)
app.include_router(panels.router)
app.include_router(stock.router)
app.include_router(tests.router)
app.include_router(cocktails.router)
app.include_router(orders.router)
app.include_router(alerts.router)
app.include_router(alert_rules.router)
app.include_router(forecast.router)
app.include_router(lab_settings.router)
app.include_router(validation.router)
app.include_router(export.router)
app.include_router(store_stock.router)
app.include_router(sap_import.router)
app.include_router(staff.router)
app.include_router(panel_designer.router)
app.include_router(sample_orders.router)
app.include_router(shipment_verifications.router)
app.include_router(station.router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["system"])
def health():
    """Liveness + database check, used by the watchdog. Declared sync on purpose:
    it runs in the same worker thread pool as the API, so if that pool is
    exhausted or the database is locked, this times out too and the watchdog
    notices — a check that bypassed the pool would report "ok" while the app hung."""
    from sqlalchemy import text
    from app.database import engine
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:  # pragma: no cover - reported to the watchdog
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"status": "db_error", "detail": str(e)[:200]})
    return {"status": "ok", "version": __version__}


# ---------------------------------------------------------------------------
# Frontend static file serving (standalone / PyInstaller)
# FastAPI serves the pre-built React app when frontend/dist/ exists.
# MUST be mounted last — after all API routes.
# ---------------------------------------------------------------------------

def _get_frontend_dist() -> Path:
    """Locate the built React frontend, supporting dev and PyInstaller."""
    # PyInstaller --onefile: frontend is bundled as data, accessible via _MEIPASS
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / "frontend" / "dist"
    # Dev / standalone: frontend/dist/ is a sibling of the project root
    return Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

_FRONTEND_DIST = _get_frontend_dist()

if _FRONTEND_DIST.exists():
    # Mount static assets (JS, CSS, icons) explicitly
    _ASSETS = _FRONTEND_DIST / "assets"
    if _ASSETS.exists():
        app.mount("/assets", StaticFiles(directory=str(_ASSETS)), name="assets")

    # SPA catch-all: any non-API path returns index.html so React Router handles routing
    from fastapi.responses import FileResponse

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        index = _FRONTEND_DIST / "index.html"
        return FileResponse(str(index))
else:
    @app.get("/", tags=["system"])
    def root():
        return {
            "message": "FlowJAI Inventory Manager API",
            "docs": "/docs",
            "redoc": "/redoc",
        }