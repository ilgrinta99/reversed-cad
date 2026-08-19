"""Registro delle quote: da dove viene ogni numero che entra nel modello.

Questo modulo è l'incarnazione in codice della regola non negoziabile del progetto:

    Nessuna quota inventata. Ogni numero che entra nel modello è (a) misurato dalla
    mesh da uno script in `tools/`, oppure (b) approvato esplicitamente dall'utente e
    registrato. Se manca un valore e non è approvato: fermarsi e chiedere, non stimare.

La regola non è un commento in cima a un file: è `Registry.assert_buildable()`, che
solleva un'eccezione e blocca la build. Un default silenzioso qui è un bug, non una
comodità.

Il modulo è generico — non sa nulla del contenitore TAISER. Quali quote esistano lo
dichiara il plugin del pezzo (`parts/<nome>/`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Iterator


class Origin(str, Enum):
    """Da dove viene il valore *usato nel modello*."""

    MEASURED = "measured"  # misurato dalla mesh da uno script in tools/
    APPROVED = "approved"  # scelto dall'utente, registrato con nome e timestamp
    DERIVED = "derived"  # calcolato da altre quote tramite una formula esplicita


class Status(str, Enum):
    """Esito del confronto misurato ↔ usato. Due valori bloccano la build."""

    MEASURED_OK = "measured_ok"  # usato == misurato
    APPROVED_OVERRIDE = "approved_override"  # usato != misurato, ma approvato
    DERIVED_OK = "derived_ok"  # derivato da altre quote, formula registrata
    UNAPPROVED_DIVERGENCE = "unapproved_divergence"  # BLOCCA
    MISSING = "missing"  # BLOCCA

    @property
    def blocks_build(self) -> bool:
        return self in (Status.UNAPPROVED_DIVERGENCE, Status.MISSING)


class UnapprovedDimensions(RuntimeError):
    """Sollevata quando una build partirebbe con quote non misurate né approvate."""

    def __init__(self, dimensions: list["Dimension"]) -> None:
        self.dimensions = dimensions
        detail = "\n".join(f"  - {d.id} ({d.label}): {d.explain()}" for d in dimensions)
        super().__init__(
            f"{len(dimensions)} quote non sono né misurate né approvate. "
            f"La build non parte: servono decisioni esplicite.\n{detail}"
        )


@dataclass(frozen=True)
class Approval:
    """Traccia di chi ha approvato cosa, e quando. Senza questo non c'è approvazione."""

    by: str
    at: datetime
    rationale: str
    decision_id: str | None = None  # es. "D3" o "B", se nasce da una decisione

    def to_dict(self) -> dict[str, Any]:
        return {
            "by": self.by,
            "at": self.at.astimezone(timezone.utc).isoformat(),
            "rationale": self.rationale,
            "decision_id": self.decision_id,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Approval":
        return cls(
            by=d["by"],
            at=datetime.fromisoformat(d["at"]),
            rationale=d.get("rationale", ""),
            decision_id=d.get("decision_id"),
        )


@dataclass(frozen=True)
class Dimension:
    """Una quota, con misura, valore usato e provenienza.

    `measured` è ciò che la mesh dice; `used` è ciò che il costruttore riceve. Il
    prodotto esiste per rendere visibile la differenza fra i due, non per nasconderla.
    """

    id: str
    label: str
    used: float | None = None
    measured: float | None = None
    unit: str = "mm"
    #: Script in tools/ che ha prodotto la misura. Obbligatorio se `measured` c'è.
    measured_by: str | None = None
    approval: Approval | None = None
    #: Formula leggibile, per le quote derivate (es. "raggio_esterno - spessore").
    derived_from: str | None = None
    #: Sotto questa soglia misurato e usato sono considerati lo stesso numero.
    tolerance: float = 5e-4
    note: str = ""

    # -- stato -------------------------------------------------------------

    @property
    def divergence(self) -> float | None:
        if self.used is None or self.measured is None:
            return None
        return self.used - self.measured

    @property
    def diverges(self) -> bool:
        d = self.divergence
        return d is not None and abs(d) > self.tolerance

    @property
    def status(self) -> Status:
        if self.used is None:
            return Status.MISSING
        if self.derived_from:
            return Status.DERIVED_OK
        if self.measured is None:
            # Nessuna misura: l'unico modo per essere legittima è l'approvazione.
            return Status.APPROVED_OVERRIDE if self.approval else Status.MISSING
        if not self.diverges:
            return Status.MEASURED_OK
        return Status.APPROVED_OVERRIDE if self.approval else Status.UNAPPROVED_DIVERGENCE

    @property
    def origin(self) -> Origin | None:
        s = self.status
        if s is Status.MEASURED_OK:
            return Origin.MEASURED
        if s is Status.APPROVED_OVERRIDE:
            return Origin.APPROVED
        if s is Status.DERIVED_OK:
            return Origin.DERIVED
        return None

    def explain(self) -> str:
        """Frase leggibile sulla provenienza — è quel che la UI mostra in tabella."""
        s = self.status
        if s is Status.MISSING and self.used is None:
            return "nessun valore, e nessuna approvazione: da risolvere"
        if s is Status.MISSING:
            return f"{self.used}{self.unit} senza misura né approvazione: da risolvere"
        if s is Status.MEASURED_OK:
            return f"misurato da {self.measured_by or 'tools/'}"
        if s is Status.DERIVED_OK:
            return f"derivato: {self.derived_from}"
        if s is Status.UNAPPROVED_DIVERGENCE:
            return (
                f"diverge dalla misura di {self.divergence:+.4g}{self.unit} "
                "senza approvazione: da risolvere"
            )
        assert self.approval is not None
        if self.measured is None:
            return f"approvato da {self.approval.by} (nessuna misura disponibile)"
        return (
            f"approvato da {self.approval.by}: {self.divergence:+.4g}{self.unit} "
            f"rispetto alla misura di {self.measured_by or 'tools/'}"
        )

    # -- modifiche ---------------------------------------------------------

    def with_measurement(self, value: float, by: str) -> "Dimension":
        return replace(self, measured=value, measured_by=by)

    def approve(self, value: float, *, by: str, rationale: str, decision_id: str | None = None,
                at: datetime | None = None) -> "Dimension":
        """Registra un valore approvato dall'utente. È l'unica via legittima per un
        numero che non venga dalla mesh."""
        if not rationale.strip():
            raise ValueError(
                f"approvazione di {self.id} senza motivazione: la traccia del perché "
                "fa parte dell'approvazione"
            )
        stamp = at or datetime.now(timezone.utc)
        return replace(self, used=value,
                       approval=Approval(by=by, at=stamp, rationale=rationale,
                                         decision_id=decision_id))

    def accept_measurement(self) -> "Dimension":
        """Usa nel modello il valore misurato, così com'è."""
        if self.measured is None:
            raise ValueError(f"{self.id} non ha una misura da accettare")
        return replace(self, used=self.measured)

    # -- serializzazione ---------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "unit": self.unit,
            "used": self.used,
            "measured": self.measured,
            "measured_by": self.measured_by,
            "derived_from": self.derived_from,
            "tolerance": self.tolerance,
            "note": self.note,
            "approval": self.approval.to_dict() if self.approval else None,
            # Campi calcolati: la UI non deve ricostruire questa logica.
            "status": self.status.value,
            "origin": self.origin.value if self.origin else None,
            "divergence": self.divergence,
            "diverges": self.diverges,
            "blocks_build": self.status.blocks_build,
            "explanation": self.explain(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Dimension":
        approval = d.get("approval")
        return cls(
            id=d["id"],
            label=d.get("label", d["id"]),
            used=d.get("used"),
            measured=d.get("measured"),
            unit=d.get("unit", "mm"),
            measured_by=d.get("measured_by"),
            approval=Approval.from_dict(approval) if approval else None,
            derived_from=d.get("derived_from"),
            tolerance=d.get("tolerance", 5e-4),
            note=d.get("note", ""),
        )


@dataclass
class Registry:
    """Insieme delle quote di un run. Ordine di inserimento preservato."""

    dimensions: dict[str, Dimension] = field(default_factory=dict)

    def __iter__(self) -> Iterator[Dimension]:
        return iter(self.dimensions.values())

    def __len__(self) -> int:
        return len(self.dimensions)

    def __contains__(self, dim_id: object) -> bool:
        return dim_id in self.dimensions

    def add(self, dim: Dimension) -> None:
        if dim.id in self.dimensions:
            raise ValueError(f"quota duplicata: {dim.id}")
        self.dimensions[dim.id] = dim

    def get(self, dim_id: str) -> Dimension:
        try:
            return self.dimensions[dim_id]
        except KeyError:
            raise KeyError(f"quota sconosciuta: {dim_id}") from None

    def update(self, dim: Dimension) -> None:
        if dim.id not in self.dimensions:
            raise KeyError(f"quota sconosciuta: {dim.id}")
        self.dimensions[dim.id] = dim

    def extend(self, dims: Iterable[Dimension]) -> None:
        for d in dims:
            self.add(d)

    # -- il cancello -------------------------------------------------------

    def blocking(self) -> list[Dimension]:
        """Le quote che impediscono la build. Se non è vuota, si chiede all'utente."""
        return [d for d in self if d.status.blocks_build]

    def divergences(self) -> list[Dimension]:
        """Quote in cui il modello si discosta dalla misura — approvate o no.
        Sono le D1–D8 del progetto: vanno mostrate, non nascoste."""
        return [d for d in self if d.diverges]

    def assert_buildable(self) -> None:
        blocking = self.blocking()
        if blocking:
            raise UnapprovedDimensions(blocking)

    def values(self) -> dict[str, float]:
        """I numeri da passare al costruttore. Chiama prima `assert_buildable()`:
        non esiste un percorso che restituisca valori non verificati."""
        self.assert_buildable()
        out: dict[str, float] = {}
        for d in self:
            assert d.used is not None  # garantito da assert_buildable
            out[d.id] = d.used
        return out

    # -- riepilogo e serializzazione ---------------------------------------

    def summary(self) -> dict[str, int]:
        counts = {s.value: 0 for s in Status}
        for d in self:
            counts[d.status.value] += 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimensions": [d.to_dict() for d in self],
            "summary": self.summary(),
            "blocking": [d.id for d in self.blocking()],
            "divergent": [d.id for d in self.divergences()],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Registry":
        reg = cls()
        reg.extend(Dimension.from_dict(x) for x in d.get("dimensions", []))
        return reg


def close(a: float | None, b: float | None, tol: float = 5e-4) -> bool:
    """Confronto di quote con la tolleranza del progetto (default 0.5 µm)."""
    if a is None or b is None:
        return False
    return math.isclose(a, b, abs_tol=tol)
