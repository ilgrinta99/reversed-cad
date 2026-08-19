"""Coda job in-process, stato su SQLite, log in streaming.

Gli step lunghi (analisi, build, tavola, confronto) non stanno in una richiesta HTTP
sincrona: si inviano qui, e il browser segue i log via SSE.

L'interfaccia pubblica è `submit()` / `get()` / `stream()`. Se un giorno servirà RQ o
Celery, cambia questo modulo e nient'altro: gli endpoint non sanno come i job girano.
"""

from __future__ import annotations

import asyncio
import json
import threading
import traceback
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncIterator, Callable

from webapp.backend.app.storage.db import connect
from webapp.backend.app.storage.runs import new_id


class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    @property
    def is_final(self) -> bool:
        return self in (JobState.SUCCEEDED, JobState.FAILED)


#: Un job riceve un logger e restituisce un dizionario serializzabile.
JobFn = Callable[[Callable[[str], None]], dict[str, Any]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Job:
    id: str
    run_id: str
    kind: str
    state: JobState
    created_at: str
    started_at: str | None = None
    ended_at: str | None = None
    error: str | None = None
    result: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "kind": self.kind,
            "state": self.state.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "error": self.error,
            "result": self.result or {},
        }


class JobQueue:
    def __init__(self, workers: int = 2) -> None:
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="job")
        self._lock = threading.Lock()
        self._seq: dict[str, int] = defaultdict(int)
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Registra l'event loop del server: i worker sono thread, e per svegliare
        i lettori SSE serve `call_soon_threadsafe`."""
        self._loop = loop

    # -- invio -------------------------------------------------------------

    def submit(self, run_id: str, kind: str, fn: JobFn) -> Job:
        job = Job(id=new_id("job"), run_id=run_id, kind=kind,
                  state=JobState.QUEUED, created_at=_now())
        conn = connect()
        with conn:
            conn.execute(
                "INSERT INTO jobs (id, run_id, kind, state, created_at) VALUES (?,?,?,?,?)",
                (job.id, job.run_id, job.kind, job.state.value, job.created_at),
            )
        self._pool.submit(self._run, job, fn)
        return job

    def _run(self, job: Job, fn: JobFn) -> None:
        self._set_state(job.id, JobState.RUNNING, started_at=_now())
        log = self._logger(job.id)
        log(f"[{job.kind}] avviato")
        try:
            result = fn(log) or {}
            self._set_state(job.id, JobState.SUCCEEDED, ended_at=_now(), result=result)
            log(f"[{job.kind}] completato")
        except Exception as exc:  # il traceback finisce nei log del job, non nel vuoto
            detail = "".join(traceback.format_exception(exc)).rstrip()
            for line in detail.splitlines():
                log(line)
            self._set_state(job.id, JobState.FAILED, ended_at=_now(), error=str(exc))
            log(f"[{job.kind}] FALLITO: {exc}")
        finally:
            self._publish(job.id, None)  # sentinella di fine stream

    # -- log ---------------------------------------------------------------

    def _logger(self, job_id: str) -> Callable[[str], None]:
        def log(line: str) -> None:
            with self._lock:
                self._seq[job_id] += 1
                seq = self._seq[job_id]
            conn = connect()
            with conn:
                conn.execute(
                    "INSERT INTO job_logs (job_id, seq, at, line) VALUES (?,?,?,?)",
                    (job_id, seq, _now(), line),
                )
            self._publish(job_id, {"seq": seq, "line": line})
        return log

    def _publish(self, job_id: str, payload: dict[str, Any] | None) -> None:
        loop = self._loop
        with self._lock:
            queues = list(self._subscribers.get(job_id, ()))
        if not queues or loop is None:
            return
        for q in queues:
            loop.call_soon_threadsafe(q.put_nowait, payload)

    def logs(self, job_id: str, after_seq: int = 0) -> list[dict[str, Any]]:
        rows = connect().execute(
            "SELECT seq, at, line FROM job_logs WHERE job_id = ? AND seq > ? ORDER BY seq",
            (job_id, after_seq),
        ).fetchall()
        return [dict(r) for r in rows]

    async def stream(self, job_id: str) -> AsyncIterator[dict[str, Any]]:
        """Riproduce i log già scritti, poi segue quelli nuovi fino alla fine del job.

        La riproduzione viene prima della sottoscrizione ai nuovi eventi: chi si
        collega a job avviato non perde le righe iniziali.
        """
        queue: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._subscribers[job_id].append(queue)
        try:
            seen = 0
            for entry in self.logs(job_id):
                seen = entry["seq"]
                yield {"type": "log", **entry}

            job = self.get(job_id)
            if job is not None and job.state.is_final:
                yield {"type": "state", **job.to_dict()}
                return

            while True:
                payload = await queue.get()
                if payload is None:
                    break
                if payload["seq"] <= seen:
                    continue  # già riprodotta
                seen = payload["seq"]
                yield {"type": "log", **payload}

            job = self.get(job_id)
            if job is not None:
                yield {"type": "state", **job.to_dict()}
        finally:
            with self._lock:
                subs = self._subscribers.get(job_id, [])
                if queue in subs:
                    subs.remove(queue)
                if not subs:
                    self._subscribers.pop(job_id, None)

    # -- stato -------------------------------------------------------------

    def _set_state(self, job_id: str, state: JobState, **fields: Any) -> None:
        sets = ["state = ?"]
        values: list[Any] = [state.value]
        for key in ("started_at", "ended_at", "error"):
            if key in fields:
                sets.append(f"{key} = ?")
                values.append(fields[key])
        if "result" in fields:
            sets.append("result = ?")
            values.append(json.dumps(fields["result"]))
        values.append(job_id)
        conn = connect()
        with conn:
            conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?", values)

    def get(self, job_id: str) -> Job | None:
        row = connect().execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _row_to_job(row) if row else None

    def for_run(self, run_id: str) -> list[Job]:
        rows = connect().execute(
            "SELECT * FROM jobs WHERE run_id = ? ORDER BY created_at", (run_id,)
        ).fetchall()
        return [_row_to_job(r) for r in rows]

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)


def _row_to_job(row) -> Job:
    return Job(
        id=row["id"],
        run_id=row["run_id"],
        kind=row["kind"],
        state=JobState(row["state"]),
        created_at=row["created_at"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        error=row["error"],
        result=json.loads(row["result"] or "{}"),
    )


#: Coda di processo.
queue = JobQueue()
