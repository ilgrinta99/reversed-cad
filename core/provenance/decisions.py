"""Discrepanze e ambiguità come dati, non come `if` sparsi nel costruttore.

Il progetto Teiser ha 8 discrepanze catalogate (D1–D8) e 7 ambiguità (A–G) che
l'utente ha risolto una per una. Quel passaggio è il cuore del prodotto: qui è
modellato come oggetti che la UI può presentare in forma di scheda, e la cui
risoluzione scrive nel registro delle quote — con motivazione e timestamp.

Il modulo è generico: l'elenco concreto delle decisioni vive nel plugin del pezzo.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Iterator


class DecisionKind(str, Enum):
    #: Il modello e la mesh dicono cose diverse, e va deciso a chi credere (D1–D8).
    DISCREPANCY = "discrepancy"
    #: La mesh non è conclusiva: più letture sono compatibili con la misura (A–G).
    AMBIGUITY = "ambiguity"


@dataclass(frozen=True)
class Option:
    """Una risposta possibile, con l'effetto esatto che ha sulle quote.

    `sets` mappa id-quota → valore. Nessuna opzione può avere effetti impliciti:
    se una scelta cambia un numero, quel numero è scritto qui.
    """

    id: str
    label: str
    description: str = ""
    sets: dict[str, float] = field(default_factory=dict)
    #: Quote da portare al loro valore misurato. Serve per le opzioni del tipo
    #: «tieni quel che dice la mesh», il cui numero non è noto prima di misurare
    #: e che quindi non può stare in `sets` senza essere inventato.
    accept_measured: tuple[str, ...] = ()
    #: Conseguenza sul pezzo reale, in parole. È ciò che permette di decidere.
    consequence: str = ""

    @property
    def dimensions(self) -> list[str]:
        out = list(self.sets)
        out += [d for d in self.accept_measured if d not in out]
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "sets": dict(self.sets),
            "accept_measured": list(self.accept_measured),
            "consequence": self.consequence,
        }


@dataclass(frozen=True)
class Decision:
    """Una domanda aperta sul pezzo, con le sue opzioni e la risposta data."""

    id: str  # "D3", "B", ...
    kind: DecisionKind
    title: str
    question: str
    options: tuple[Option, ...]
    #: Perché la domanda esiste: cosa dice la mesh, cosa dice il disegno, dove
    #: sono in disaccordo. Senza questo l'utente non può decidere davvero.
    evidence: str = ""
    #: Riferimento alla documentazione di progetto (es. "docs/lost+found_design.md §4.2").
    reference: str = ""
    chosen: str | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    rationale: str = ""

    @property
    def resolved(self) -> bool:
        return self.chosen is not None

    @property
    def affected_dimensions(self) -> list[str]:
        seen: list[str] = []
        for opt in self.options:
            for dim_id in opt.dimensions:
                if dim_id not in seen:
                    seen.append(dim_id)
        return seen

    def option(self, option_id: str) -> Option:
        for opt in self.options:
            if opt.id == option_id:
                return opt
        valid = ", ".join(o.id for o in self.options)
        raise KeyError(f"opzione sconosciuta per {self.id}: {option_id!r} (valide: {valid})")

    def choose(self, option_id: str, *, by: str, rationale: str,
               at: datetime | None = None) -> "Decision":
        self.option(option_id)  # valida l'id prima di registrare
        if not rationale.strip():
            raise ValueError(
                f"{self.id}: la scelta va motivata — è la motivazione che rende "
                "l'approvazione tracciabile"
            )
        return replace(self, chosen=option_id, resolved_by=by, rationale=rationale,
                       resolved_at=at or datetime.now(timezone.utc))

    def apply_to(self, registry: "Registry") -> None:  # noqa: F821
        """Scrive nel registro i valori dell'opzione scelta, come approvazioni.

        Una decisione risolta non «imposta» silenziosamente un numero: lo approva,
        lasciando nel registro chi, quando e perché.
        """
        if not self.resolved:
            raise ValueError(f"{self.id} non è ancora stata risolta")
        assert self.chosen is not None and self.resolved_by is not None
        opt = self.option(self.chosen)
        motivo = f"{self.id} → {opt.label}: {self.rationale}"
        for dim_id, value in opt.sets.items():
            dim = registry.get(dim_id)
            registry.update(dim.approve(value, by=self.resolved_by, rationale=motivo,
                                        decision_id=self.id, at=self.resolved_at))
        for dim_id in opt.accept_measured:
            dim = registry.get(dim_id)
            if dim.measured is None:
                # Nessuna misura ancora: la decisione resta registrata e verrà
                # riapplicata dopo l'analisi. Meglio di un numero inventato ora.
                continue
            registry.update(dim.accept_measurement())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "title": self.title,
            "question": self.question,
            "evidence": self.evidence,
            "reference": self.reference,
            "options": [o.to_dict() for o in self.options],
            "chosen": self.chosen,
            "resolved": self.resolved,
            "resolved_by": self.resolved_by,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "rationale": self.rationale,
            "affected_dimensions": self.affected_dimensions,
        }


@dataclass
class DecisionSet:
    """Le decisioni di un run, nell'ordine in cui vanno poste."""

    decisions: dict[str, Decision] = field(default_factory=dict)

    def __iter__(self) -> Iterator[Decision]:
        return iter(self.decisions.values())

    def __len__(self) -> int:
        return len(self.decisions)

    def add(self, decision: Decision) -> None:
        if decision.id in self.decisions:
            raise ValueError(f"decisione duplicata: {decision.id}")
        self.decisions[decision.id] = decision

    def extend(self, items: Iterable[Decision]) -> None:
        for d in items:
            self.add(d)

    def get(self, decision_id: str) -> Decision:
        try:
            return self.decisions[decision_id]
        except KeyError:
            raise KeyError(f"decisione sconosciuta: {decision_id}") from None

    def resolve(self, decision_id: str, option_id: str, *, by: str,
                rationale: str) -> Decision:
        decision = self.get(decision_id).choose(option_id, by=by, rationale=rationale)
        self.decisions[decision_id] = decision
        return decision

    def pending(self) -> list[Decision]:
        return [d for d in self if not d.resolved]

    def adopt(self, fresh: "DecisionSet") -> list[str]:
        """Recepisce le domande di una nuova analisi tenendo le risposte già date.

        Una domanda che la nuova lettura ripropone identica non va richiesta:
        se l'utente ha già risposto, la risposta resta, con il suo autore e il suo
        timestamp. Una domanda che non si ripresenta sparisce — non c'è più nulla
        di ambiguo da decidere lì. Restituisce gli id caduti.
        """
        dropped = [d.id for d in self if d.id not in fresh.decisions]
        merged: dict[str, Decision] = {}
        for incoming in fresh:
            previous = self.decisions.get(incoming.id)
            if previous is not None and previous.resolved:
                try:
                    incoming.option(previous.chosen or "")
                except KeyError:
                    # Le opzioni sono cambiate con i numeri della nuova misura:
                    # la vecchia risposta non è più applicabile, e va ridata.
                    merged[incoming.id] = incoming
                    continue
                incoming = replace(incoming, chosen=previous.chosen,
                                   resolved_by=previous.resolved_by,
                                   resolved_at=previous.resolved_at,
                                   rationale=previous.rationale)
            merged[incoming.id] = incoming
        self.decisions = merged
        return dropped

    def apply_all(self, registry: "Registry") -> None:  # noqa: F821
        for d in self:
            if d.resolved:
                d.apply_to(registry)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decisions": [d.to_dict() for d in self],
            "pending": [d.id for d in self.pending()],
        }
