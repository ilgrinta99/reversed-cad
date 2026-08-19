"""Stato dei run e dei job su SQLite. Nessun servizio esterno."""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id           TEXT PRIMARY KEY,
    part_id      TEXT NOT NULL,
    title        TEXT NOT NULL DEFAULT '',
    mesh_name    TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    -- Registro quote e decisioni serializzati: è il documento del run.
    provenance   TEXT NOT NULL DEFAULT '{}',
    decisions    TEXT NOT NULL DEFAULT '{}',
    -- Run da cui questo deriva, quando si rilancia con parametri modificati.
    parent_id    TEXT REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS jobs (
    id           TEXT PRIMARY KEY,
    run_id       TEXT NOT NULL REFERENCES runs(id),
    kind         TEXT NOT NULL,
    state        TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    started_at   TEXT,
    ended_at     TEXT,
    error        TEXT,
    result       TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS jobs_run_idx ON jobs(run_id, created_at);

CREATE TABLE IF NOT EXISTS job_logs (
    job_id       TEXT NOT NULL REFERENCES jobs(id),
    seq          INTEGER NOT NULL,
    at           TEXT NOT NULL,
    line         TEXT NOT NULL,
    PRIMARY KEY (job_id, seq)
);
"""


def db_path() -> Path:
    return Path(os.environ.get("TEISER_DB_PATH", "./data/teiser.db")).expanduser()


def runs_dir() -> Path:
    return Path(os.environ.get("TEISER_RUNS_DIR", "./data/runs")).expanduser()


def connect() -> sqlite3.Connection:
    """Connessione per-thread. Il worker pool tocca il db da thread diversi."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        return conn
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # WAL: il lettore SSE non deve bloccare il worker che scrive i log.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    _local.conn = conn
    return conn


def init_db() -> None:
    conn = connect()
    with conn:
        conn.executescript(SCHEMA)
    runs_dir().mkdir(parents=True, exist_ok=True)


def reset_for_tests() -> None:
    """Chiude la connessione del thread corrente (usato dai test fra un db e l'altro)."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None
