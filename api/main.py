"""FastAPI app: /api routes first, then static SPA assets, then an index.html catch-all."""
from __future__ import annotations

import logging
import os
import shlex
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routes import core, reports, subscribe, validation
from config import DEMO_MODE, LOG_DIR, ROOT
from db.store import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s",
                    handlers=[logging.StreamHandler(), logging.FileHandler(LOG_DIR / "smellcast.log")])
DIST = ROOT / "web" / "dist"


def start_seed() -> None:
    """SEED=1: seed this database once in the background (scripts/seed.py); SEED=small: same, Replay list capped at 5;
    SEED=always: everything on every start. The API comes up at once; progress goes to logs/seed.log."""
    mode = os.getenv("SEED", "0").strip().lower()
    if DEMO_MODE or mode not in ("1", "true", "yes", "once", "small", "always"):
        return
    cmd = [sys.executable, "-m", "scripts.seed"] + ([] if mode == "always" else ["--once"])
    cmd += ["--small"] if mode == "small" else []
    cmd += shlex.split(os.getenv("SEED_ARGS", ""))
    log = open(LOG_DIR / "seed.log", "a")
    subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    logging.getLogger("seed").info("seeding in the background (%s); progress in logs/seed.log", " ".join(cmd[1:]))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_seed()
    sched = None
    if not DEMO_MODE and os.getenv("SCHEDULER", "1") == "1":
        from api.scheduler import start
        sched = start()
    yield
    if sched:
        sched.shutdown(wait=False)


app = FastAPI(title="Smellcast API", lifespan=lifespan)
app.include_router(core.router)
app.include_router(validation.router)
app.include_router(subscribe.router)
app.include_router(reports.router)


@app.get("/api/health")
def health():
    return {"ok": True, "demo_mode": DEMO_MODE}


if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith("api/"):
        raise HTTPException(404)
    f = (DIST / path).resolve()
    if path and f.is_file() and DIST.resolve() in f.parents:
        return FileResponse(f)
    index = DIST / "index.html"
    if not index.exists():
        raise HTTPException(404, "frontend not built: cd web && npm run build")
    return FileResponse(index)
