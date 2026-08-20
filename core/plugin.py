"""Il confine fra ciò che è generico e ciò che è specifico del pezzo.

Il backend web non importa mai `parts.teiser`: chiede al registry un `PartPlugin` e
parla solo con questa interfaccia. È la scelta architetturale che decide se il
progetto scala — quando arriverà un secondo pezzo (o il riconoscimento automatico
delle feature) si aggiunge un plugin, non si riscrive il runner.

Regola di collocazione, per non doverne discutere caso per caso: se un modulo
contiene un numero, un nome di feature o un'assunzione geometrica specifici del
pezzo, sta in `parts/<nome>/`. Tutto il resto è `core/`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

from core.provenance import DecisionSet, Registry


@dataclass
class RunContext:
    """Tutto ciò che uno step ha il diritto di sapere sull'esecuzione corrente.

    Gli step non leggono variabili d'ambiente né scrivono fuori da `run_dir`: quel
    che producono è ispezionabile e cancellabile per run.
    """

    run_id: str
    #: Mesh caricata dall'utente (OBJ), più eventuali file di corredo.
    mesh_path: Path
    #: Cartella di lavoro del run: ogni artefatto nasce qui.
    run_dir: Path
    #: Riferimenti caricati dall'utente (immagine o PDF di una tavola).
    #: NON sono fonte di quote: la tavola TinkerCAD è generata dalla mesh stessa.
    references: list[Path] = field(default_factory=list)
    #: Log in streaming verso il job runner.
    log: Callable[[str], None] = lambda msg: None
    timeout_s: float = 600.0
    #: Le decisioni del run. Servono al costruttore per le scelte che non sono
    #: numeri — «solo il corpo principale», «asole come fori» — e che quindi non
    #: possono viaggiare nel registro delle quote.
    decisions: DecisionSet | None = None

    def chosen(self, decision_id: str) -> str | None:
        """Opzione scelta per una decisione, o None se non è stata presa."""
        if self.decisions is None or decision_id not in self.decisions.decisions:
            return None
        return self.decisions.get(decision_id).chosen

    def artifact(self, name: str) -> Path:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        return self.run_dir / name


@dataclass
class StepResult:
    """Esito di uno step: artefatti prodotti e metriche da mostrare in UI.

    `dimensions` e `decisions` sono il canale con cui un'analisi *ad hoc*
    restituisce quello che ha scoperto: quali quote esistono in questa mesh e
    quali domande solleva. Un plugin che conosce già il pezzo li lascia vuoti e
    riempie il registro che ha ricevuto.
    """

    artifacts: dict[str, Path] = field(default_factory=dict)
    metrics: dict[str, float | str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    #: Quote scoperte misurando: sostituiscono quelle dichiarate a priori.
    dimensions: Registry | None = None
    #: Ambiguità trovate in *questa* mesh, non un catalogo deciso prima.
    decisions: DecisionSet | None = None

    def to_dict(self) -> dict:
        return {
            "artifacts": {k: str(v) for k, v in self.artifacts.items()},
            "metrics": dict(self.metrics),
            "notes": list(self.notes),
        }


@runtime_checkable
class PartPlugin(Protocol):
    """Contratto di un pezzo. Implementarlo è l'unico modo di entrare nella pipeline."""

    id: str
    name: str
    description: str

    def declare_dimensions(self) -> Registry:
        """Le quote che questo pezzo richiede, ancora senza valori.

        Serve a rendere esplicito *cosa manca* prima ancora di misurare: una quota
        dichiarata e non misurata blocca la build, e la UI sa già come chiamarla.
        """
        ...

    def declare_decisions(self) -> DecisionSet:
        """Discrepanze e ambiguità note per questo pezzo (D1–D8, A–G per Teiser)."""
        ...

    def measure(self, ctx: RunContext, registry: Registry) -> StepResult:
        """Esegue gli script di misura sulla mesh e riempie `registry`.

        Ogni quota scritta qui porta `measured_by` con il nome dello script: è la
        prova che il numero viene dalla mesh e non da una stima.

        Un plugin che non conosce il pezzo in anticipo non può riempire un
        registro dichiarato prima di vedere la mesh: restituisce quote e
        decisioni scoperte in `StepResult`, e il runner le recepisce.
        """
        ...

    def build(self, ctx: RunContext, registry: Registry) -> StepResult:
        """Costruisce i solidi (STEP/STL/FCStd) dai valori approvati.

        Deve chiamare `registry.values()`, che solleva `UnapprovedDimensions` se
        una quota non è né misurata né approvata. Non aggirare quel cancello.
        """
        ...

    def draw(self, ctx: RunContext, registry: Registry) -> StepResult:
        """Produce la tavola (SVG per l'anteprima, poi PDF e DXF)."""
        ...

    def compare(self, ctx: RunContext, model_path: Path) -> StepResult:
        """Confronta modello e mesh e restituisce la statistica di scostamento."""
        ...


class PartRegistry:
    """Elenco dei pezzi disponibili. Un dizionario, ma con messaggi utili."""

    def __init__(self) -> None:
        self._parts: dict[str, PartPlugin] = {}

    def register(self, plugin: PartPlugin) -> PartPlugin:
        if plugin.id in self._parts:
            raise ValueError(f"pezzo già registrato: {plugin.id}")
        self._parts[plugin.id] = plugin
        return plugin

    def get(self, part_id: str) -> PartPlugin:
        try:
            return self._parts[part_id]
        except KeyError:
            known = ", ".join(sorted(self._parts)) or "(nessuno)"
            raise KeyError(f"pezzo sconosciuto: {part_id!r}. Registrati: {known}") from None

    def all(self) -> list[PartPlugin]:
        return list(self._parts.values())

    def __contains__(self, part_id: object) -> bool:
        return part_id in self._parts

    def __len__(self) -> int:
        return len(self._parts)


#: Registry di processo. I plugin si registrano all'import del proprio package.
registry = PartRegistry()
