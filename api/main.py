"""PRX Predictor FastAPI app (P6.T2).

Mounts the prediction + reference-data routes and enables CORS for the LAN
dashboard. Heavy model resources load lazily on the first prediction request
(cached per db path); set ``PRX_WARM=1`` to pre-load them at startup per
ARCHITECTURE §5.1 (slower boot, no first-request latency spike).

Run:
    uvicorn api.main:app --host 0.0.0.0 --port 8000
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.deps import db_path
from api.routes import events, home, matches, matchup, model, players, predict, teams

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Opt-in warm of the heavy model resources at startup (ARCHITECTURE §5.1).
    if os.environ.get("PRX_WARM") == "1":
        try:
            from models.predict import _resources
            _resources(db_path())
            logger.info("resources_warmed", db=db_path())
        except Exception as e:  # never block startup on a warm failure
            logger.warning("resource_warm_failed", error=repr(e))
    yield


app = FastAPI(title="PRX Predictor API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # LAN dashboard; tighten if exposed beyond the LAN
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (home, predict, teams, players, events, matches, model, matchup):
    app.include_router(module.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "db": db_path()}


# Serve the built React dashboard (P6.T10), if built. Registered last so /api/*
# and /docs win. Hashed assets are served from /assets; everything else falls back
# to index.html so client-side routes (/match/:id, /player/:id) work on refresh /
# direct load. DASHBOARD_DIST overrides the location (set in Docker).
_DIST = Path(os.environ.get("DASHBOARD_DIST")
             or Path(__file__).resolve().parent.parent / "dashboard" / "dist")
if _DIST.is_dir():
    from fastapi import HTTPException
    from fastapi.responses import FileResponse

    app.mount("/assets", StaticFiles(directory=str(_DIST / "assets")), name="assets")
    _INDEX = _DIST / "index.html"

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="not found")
        candidate = _DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)          # favicon.svg, etc.
        return FileResponse(_INDEX)                  # SPA fallback
else:
    logger.info("dashboard_not_built", expected=str(_DIST))
