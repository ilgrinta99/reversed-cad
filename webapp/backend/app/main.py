"""Applicazione FastAPI: assembla storage, coda job e plugin dei pezzi."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from webapp.backend.app.api.routes import router
from webapp.backend.app.jobs.queue import queue
from webapp.backend.app.storage.db import init_db


def _load_parts() -> None:
    """Importa i plugin, che si registrano da soli nel registry di `core.plugin`."""
    import parts  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _load_parts()
    # I job girano su thread; per svegliare i lettori SSE serve il loop del server.
    queue.bind_loop(asyncio.get_running_loop())
    yield
    queue.shutdown()


app = FastAPI(
    title="Teiser — runner web della pipeline di reverse engineering CAD",
    version="0.1.0",
    lifespan=lifespan,
)

origins = [o for o in os.environ.get("TEISER_CORS_ORIGINS", "").split(",") if o]
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(router)

# In produzione il build statico del frontend è servito dallo stesso processo;
# in sviluppo il dev server di Vite gira a parte e questa cartella non esiste.
_static = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _static.is_dir():
    app.mount("/", StaticFiles(directory=_static, html=True), name="frontend")
