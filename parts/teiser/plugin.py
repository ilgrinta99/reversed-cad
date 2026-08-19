"""Contenitore TAISER — scheletro di cablaggio, non ancora collegato.

Il codice della pipeline Teiser (`tools/`, `cad/params.json`, `cad/build_model.py`,
`cad/make_drawing.py`, `cad/draft2d.py`, `cad/compare_model_mesh.py`) non era
presente nel repo quando questo file è stato scritto: viveva solo sul Mac di
sviluppo. Vedi `docs/webapp-architecture.md` §0.

Questo modulo dichiara **dove** ogni pezzo esistente si innesta, e fallisce con un
messaggio esplicito finché non è collegato. Non contiene quote, non contiene le
D1–D8 né le A–G: inventarle qui sarebbe esattamente la violazione che il progetto
vieta. Vanno trascritte dalla documentazione reale.

CABLAGGIO DA COMPLETARE, nell'ordine:

  1. `declare_dimensions()`
     Origine: schema di `cad/params.json`. Ogni chiave diventa un `Dimension`
     con id, etichetta leggibile e unità. Nessun valore di default.

  2. `declare_decisions()`
     Origine: `docs/lost+found_design.md`, discrepanze D1–D8 e ambiguità A–G.
     Per ciascuna: domanda, evidenza (cosa dice la mesh, cosa dice la tavola),
     opzioni con i valori che impostano, e la decisione già presa dall'utente
     come `chosen` di default — così un run riproduce lo stato attuale del
     progetto invece di ripartire da zero.

  3. `measure()`
     Chiama `tools/extract_params.py` e le sonde (`tools/probe_*.py`,
     `tools/fit_superellipsoid.py`) sulla mesh del run. Ogni quota scritta nel
     registro porta `measured_by` con il nome dello script che l'ha prodotta.

  4. `build()`
     `registry.values()` (che applica il cancello sulle quote) → params.json →
     `cad/build_model.py` eseguito con `core.freecad.runner.run_script`, che
     chiude stdin e impone il timeout.

  5. `draw()`
     `cad/make_drawing.py` su `cad/draft2d.py`. L'SVG serve l'anteprima nel
     browser senza passare da FreeCAD; PDF e DXF sono gli stessi artefatti.

  6. `compare()`
     `cad/compare_model_mesh.py`, che è già verificato (mediana 0.015 mm scatola,
     0.013 mm coperchio). Va restituito anche il valore per vertice, per la mappa
     di scostamento in three.js.
"""

from __future__ import annotations

from pathlib import Path

from core.plugin import RunContext, StepResult, registry
from core.provenance import DecisionSet, Registry

_NOT_WIRED = (
    "Il pezzo TAISER non è ancora collegato: il codice della pipeline "
    "(tools/, cad/) non è nel repo. Vedi parts/teiser/plugin.py per l'ordine di "
    "cablaggio e docs/webapp-architecture.md §0 per come portare qui il codice."
)


class TeiserPart:
    id = "teiser"
    name = "Contenitore TAISER"
    description = (
        "Scatola e coperchio con cupola paraboloidica, 4 colonnine (una diversa), "
        "asole e tasche ellittiche. DA COLLEGARE: manca il codice della pipeline."
    )
    #: Falso finché i moduli reali non sono innestati. L'API lo espone, così la UI
    #: può mostrare il pezzo come non disponibile invece di far fallire un upload.
    wired = False

    def declare_dimensions(self) -> Registry:
        raise NotImplementedError(_NOT_WIRED)

    def declare_decisions(self) -> DecisionSet:
        raise NotImplementedError(_NOT_WIRED)

    def measure(self, ctx: RunContext, registry_: Registry) -> StepResult:
        raise NotImplementedError(_NOT_WIRED)

    def build(self, ctx: RunContext, registry_: Registry) -> StepResult:
        raise NotImplementedError(_NOT_WIRED)

    def draw(self, ctx: RunContext, registry_: Registry) -> StepResult:
        raise NotImplementedError(_NOT_WIRED)

    def compare(self, ctx: RunContext, model_path: Path) -> StepResult:
        raise NotImplementedError(_NOT_WIRED)


plugin = registry.register(TeiserPart())
