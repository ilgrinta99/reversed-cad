"""Persistenza di un run: mesh caricata, registro quote, decisioni, artefatti."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.provenance import DecisionSet, Registry
from core.provenance.decisions import Decision, DecisionKind, Option
from webapp.backend.app.storage.db import connect, runs_dir


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass
class Run:
    id: str
    part_id: str
    title: str
    mesh_name: str
    created_at: str
    registry: Registry
    decisions: DecisionSet
    parent_id: str | None = None

    @property
    def dir(self) -> Path:
        return runs_dir() / self.id

    @property
    def mesh_path(self) -> Path:
        return self.dir / "input" / self.mesh_name

    @property
    def references(self) -> list[Path]:
        ref_dir = self.dir / "input" / "reference"
        return sorted(ref_dir.iterdir()) if ref_dir.is_dir() else []

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "part_id": self.part_id,
            "title": self.title,
            "mesh_name": self.mesh_name,
            "created_at": self.created_at,
            "parent_id": self.parent_id,
            "provenance": self.registry.to_dict(),
            "decisions": self.decisions.to_dict(),
            # I riferimenti caricati dall'utente non sono fonte di quote: la tavola
            # TinkerCAD è generata dalla mesh stessa. La UI lo deve dire.
            "references": [
                {"name": p.name, "authoritative": False} for p in self.references
            ],
        }


def create_run(part_id: str, *, title: str, mesh_name: str, registry: Registry,
               decisions: DecisionSet, parent_id: str | None = None) -> Run:
    run = Run(
        id=new_id("run"),
        part_id=part_id,
        title=title,
        mesh_name=mesh_name,
        created_at=_now(),
        registry=registry,
        decisions=decisions,
        parent_id=parent_id,
    )
    (run.dir / "input").mkdir(parents=True, exist_ok=True)
    conn = connect()
    with conn:
        conn.execute(
            "INSERT INTO runs (id, part_id, title, mesh_name, created_at, provenance,"
            " decisions, parent_id) VALUES (?,?,?,?,?,?,?,?)",
            (run.id, run.part_id, run.title, run.mesh_name, run.created_at,
             json.dumps(registry.to_dict()), json.dumps(_decisions_to_json(decisions)),
             parent_id),
        )
    return run


def save_run(run: Run) -> None:
    conn = connect()
    with conn:
        conn.execute(
            "UPDATE runs SET provenance = ?, decisions = ?, title = ? WHERE id = ?",
            (json.dumps(run.registry.to_dict()),
             json.dumps(_decisions_to_json(run.decisions)), run.title, run.id),
        )


def get_run(run_id: str) -> Run:
    row = connect().execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise KeyError(f"run sconosciuto: {run_id}")
    return _row_to_run(row)


def list_runs(limit: int = 50) -> list[Run]:
    rows = connect().execute(
        "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [_row_to_run(r) for r in rows]


def _row_to_run(row) -> Run:
    return Run(
        id=row["id"],
        part_id=row["part_id"],
        title=row["title"],
        mesh_name=row["mesh_name"],
        created_at=row["created_at"],
        registry=Registry.from_dict(json.loads(row["provenance"])),
        decisions=_decisions_from_json(json.loads(row["decisions"])),
        parent_id=row["parent_id"],
    )


# -- serializzazione delle decisioni ---------------------------------------
# Le decisioni sono dati del pezzo, ma la *risposta* è dato del run: si salva
# tutto, così un run resta leggibile anche se il plugin cambia in futuro.


def _decisions_to_json(ds: DecisionSet) -> dict[str, Any]:
    return {"decisions": [d.to_dict() for d in ds]}


def _decisions_from_json(data: dict[str, Any]) -> DecisionSet:
    out = DecisionSet()
    for d in data.get("decisions", []):
        out.add(Decision(
            id=d["id"],
            kind=DecisionKind(d["kind"]),
            title=d["title"],
            question=d["question"],
            evidence=d.get("evidence", ""),
            reference=d.get("reference", ""),
            options=tuple(
                Option(id=o["id"], label=o["label"], description=o.get("description", ""),
                       sets=dict(o.get("sets", {})), consequence=o.get("consequence", ""))
                for o in d.get("options", [])
            ),
            chosen=d.get("chosen"),
            resolved_by=d.get("resolved_by"),
            resolved_at=datetime.fromisoformat(d["resolved_at"]) if d.get("resolved_at") else None,
            rationale=d.get("rationale", ""),
        ))
    return out
