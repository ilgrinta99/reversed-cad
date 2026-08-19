"""Endpoint HTTP. Sottili: la logica sta in core/ e parts/."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from core.plugin import registry as part_registry
from core.provenance import UnapprovedDimensions
from webapp.backend.app.jobs.queue import queue
from webapp.backend.app.jobs.steps import SUBMITTERS
from webapp.backend.app.storage import runs as store

router = APIRouter(prefix="/api")

MESH_SUFFIXES = {".obj"}
COMPANION_SUFFIXES = {".mtl", ".png", ".jpg", ".jpeg", ".pdf", ".svg"}


@router.get("/health")
def health() -> dict[str, Any]:
    from core.freecad.runner import FreeCADNotFound, find_freecad

    try:
        freecad = find_freecad()
    except FreeCADNotFound:
        freecad = None
    return {
        "status": "ok",
        # FreeCAD assente non impedisce di aprire l'app: analisi mesh e anteprima
        # della tavola (draft2d, Python puro) funzionano comunque. Va però detto.
        "freecad": freecad,
        "parts": [p.id for p in part_registry.all()],
    }


@router.get("/parts")
def list_parts() -> list[dict[str, Any]]:
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            # Un pezzo non ancora collegato resta visibile ma non accetta upload:
            # meglio dirlo nell'elenco che far fallire l'utente dopo il caricamento.
            "wired": getattr(p, "wired", True),
        }
        for p in part_registry.all()
    ]


# -- run --------------------------------------------------------------------


@router.post("/runs")
async def create_run(
    part_id: str = Form(...),
    title: str = Form(""),
    mesh: UploadFile = File(...),
    references: list[UploadFile] = File(default=[]),
) -> dict[str, Any]:
    try:
        plugin = part_registry.get(part_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from None

    mesh_name = Path(mesh.filename or "model.obj").name
    if Path(mesh_name).suffix.lower() not in MESH_SUFFIXES:
        raise HTTPException(400, f"atteso un file .obj, ricevuto {mesh_name!r}")

    try:
        declared_dimensions = plugin.declare_dimensions()
        declared_decisions = plugin.declare_decisions()
    except NotImplementedError as exc:
        raise HTTPException(503, str(exc)) from None

    run = store.create_run(
        part_id,
        title=title or mesh_name,
        mesh_name=mesh_name,
        registry=declared_dimensions,
        decisions=declared_decisions,
    )

    dest = run.dir / "input" / mesh_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as fh:
        shutil.copyfileobj(mesh.file, fh)

    for ref in references:
        name = Path(ref.filename or "").name
        if not name:
            continue
        suffix = Path(name).suffix.lower()
        if suffix not in COMPANION_SUFFIXES:
            raise HTTPException(400, f"tipo di allegato non ammesso: {name!r}")
        # Il .mtl sta accanto alla mesh; il resto è materiale di riferimento, e
        # come tale non è fonte di quote.
        target = run.dir / "input" if suffix == ".mtl" else run.dir / "input" / "reference"
        target.mkdir(parents=True, exist_ok=True)
        with (target / name).open("wb") as fh:
            shutil.copyfileobj(ref.file, fh)

    return store.get_run(run.id).to_dict()


@router.get("/runs")
def list_runs() -> list[dict[str, Any]]:
    return [
        {"id": r.id, "part_id": r.part_id, "title": r.title,
         "created_at": r.created_at, "parent_id": r.parent_id,
         "summary": r.registry.summary()}
        for r in store.list_runs()
    ]


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    return _run(run_id).to_dict()


@router.post("/runs/{run_id}/fork")
def fork_run(run_id: str) -> dict[str, Any]:
    """Rilancia con parametri modificabili: un nuovo run, non una sovrascrittura.

    I run precedenti restano confrontabili e la loro provenance non viene persa.
    """
    src = _run(run_id)
    dup = store.create_run(
        src.part_id,
        title=f"{src.title} (variante)",
        mesh_name=src.mesh_name,
        registry=src.registry,
        decisions=src.decisions,
        parent_id=src.id,
    )
    shutil.copytree(src.dir / "input", dup.dir / "input", dirs_exist_ok=True)
    return store.get_run(dup.id).to_dict()


# -- quote e decisioni ------------------------------------------------------


class ApproveBody(BaseModel):
    value: float
    rationale: str = Field(min_length=1)
    by: str = "utente"


class DecisionBody(BaseModel):
    option_id: str
    rationale: str = Field(min_length=1)
    by: str = "utente"


@router.get("/runs/{run_id}/dimensions")
def dimensions(run_id: str) -> dict[str, Any]:
    return _run(run_id).registry.to_dict()


@router.post("/runs/{run_id}/dimensions/{dim_id}/approve")
def approve_dimension(run_id: str, dim_id: str, body: ApproveBody) -> dict[str, Any]:
    run = _run(run_id)
    try:
        dim = run.registry.get(dim_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from None
    run.registry.update(dim.approve(body.value, by=body.by, rationale=body.rationale))
    store.save_run(run)
    return run.registry.get(dim_id).to_dict()


@router.post("/runs/{run_id}/dimensions/{dim_id}/accept-measured")
def accept_measured(run_id: str, dim_id: str) -> dict[str, Any]:
    run = _run(run_id)
    try:
        run.registry.update(run.registry.get(dim_id).accept_measurement())
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    store.save_run(run)
    return run.registry.get(dim_id).to_dict()


@router.get("/runs/{run_id}/decisions")
def decisions(run_id: str) -> dict[str, Any]:
    return _run(run_id).decisions.to_dict()


@router.post("/runs/{run_id}/decisions/{decision_id}")
def resolve_decision(run_id: str, decision_id: str, body: DecisionBody) -> dict[str, Any]:
    run = _run(run_id)
    try:
        run.decisions.resolve(decision_id, body.option_id, by=body.by,
                              rationale=body.rationale)
        run.decisions.get(decision_id).apply_to(run.registry)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    store.save_run(run)
    return {
        "decision": run.decisions.get(decision_id).to_dict(),
        "provenance": run.registry.to_dict(),
    }


@router.get("/runs/{run_id}/readiness")
def readiness(run_id: str) -> dict[str, Any]:
    """Il run è pronto per la build? Se no, cosa manca — in chiaro."""
    run = _run(run_id)
    try:
        run.registry.assert_buildable()
    except UnapprovedDimensions as exc:
        return {
            "buildable": False,
            "blocking": [d.to_dict() for d in exc.dimensions],
            "pending_decisions": [d.to_dict() for d in run.decisions.pending()],
        }
    return {
        "buildable": True,
        "blocking": [],
        "pending_decisions": [d.to_dict() for d in run.decisions.pending()],
        "divergences": [d.to_dict() for d in run.registry.divergences()],
    }


# -- job --------------------------------------------------------------------


@router.post("/runs/{run_id}/jobs/{kind}")
def start_job(run_id: str, kind: str) -> dict[str, Any]:
    _run(run_id)  # 404 se il run non esiste
    submit = SUBMITTERS.get(kind)
    if submit is None:
        raise HTTPException(404, f"step sconosciuto: {kind}. "
                                 f"Disponibili: {', '.join(SUBMITTERS)}")
    return submit(run_id).to_dict()


@router.get("/runs/{run_id}/jobs")
def run_jobs(run_id: str) -> list[dict[str, Any]]:
    _run(run_id)
    return [j.to_dict() for j in queue.for_run(run_id)]


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    job = queue.get(job_id)
    if job is None:
        raise HTTPException(404, f"job sconosciuto: {job_id}")
    return job.to_dict()


@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str) -> StreamingResponse:
    if queue.get(job_id) is None:
        raise HTTPException(404, f"job sconosciuto: {job_id}")

    async def events():
        async for event in queue.stream(job_id):
            yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# -- artefatti --------------------------------------------------------------


@router.get("/runs/{run_id}/artifacts")
def list_artifacts(run_id: str) -> list[dict[str, Any]]:
    run = _run(run_id)
    if not run.dir.is_dir():
        return []
    out = []
    for path in sorted(run.dir.rglob("*")):
        if path.is_file():
            out.append({
                "path": str(path.relative_to(run.dir)),
                "size": path.stat().st_size,
            })
    return out


@router.get("/runs/{run_id}/artifacts/{artifact_path:path}")
def get_artifact(run_id: str, artifact_path: str) -> FileResponse:
    run = _run(run_id)
    base = run.dir.resolve()
    target = (base / artifact_path).resolve()
    # Il percorso arriva dal client: fuori dalla cartella del run non si esce.
    if not target.is_relative_to(base) or not target.is_file():
        raise HTTPException(404, f"artefatto inesistente: {artifact_path}")
    return FileResponse(target, filename=target.name)


def _run(run_id: str) -> store.Run:
    try:
        return store.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from None
