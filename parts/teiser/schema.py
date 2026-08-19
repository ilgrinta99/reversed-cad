"""Le quote del contenitore TAISER, mappate sullo schema di `cad/params.json`.

Specifico del pezzo, per definizione: qui ci sono nomi di feature e percorsi
dentro un file la cui forma è modellata su questo contenitore.

Ogni riga dichiara dove sta il valore **usato** dal costruttore e dove sta la
**misura** che gli corrisponde. Lo schema di `params.json` porta già questa
distinzione per convenzione: le chiavi con l'underscore iniziale (`_t_x_misurato`,
`_H_misurata`, `_L_mesh`, `_misurato_ellittico`) sono la misura, il valore accanto
è quello che entra nel modello. Questo modulo la rende esplicita e verificabile.

Le quote non elencate qui restano nel params.json come le scrive
`tools/extract_params.py`, cioè misurate dalla mesh: la regola non negoziabile
vale anche per loro. Qui stanno quelle su cui misura e uso *possono* divergere,
più gli ingombri principali: sono quelle che meritano una riga in tabella.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


class NoScalarMeasurement:
    """Marcatore: per questa quota non esiste una misura scalare confrontabile.

    Caso reale: i raccordi della mesh sono **ellittici** (1.514 × 1.422 sulla
    scatola, 1.484 × 1.801 sul coperchio). Un raggio circolare non ha un
    corrispondente misurato — va approvato, non «confrontato». Vedi decisione A.
    """


NO_SCALAR = NoScalarMeasurement()


@dataclass(frozen=True)
class DimensionSpec:
    id: str
    label: str
    #: Percorso puntato del valore usato dentro params.json.
    path: str
    #: Dove sta la misura. `None` = il valore stesso *è* la misura (nessuna
    #: divergenza possibile). Una stringa = percorso della misura. `NO_SCALAR` =
    #: la misura non è un singolo numero.
    measured: str | None | NoScalarMeasurement = None
    unit: str = "mm"
    #: Decisione che governa questa quota, quando ce n'è una (A–G).
    decision: str | None = None
    note: str = ""


#: Le quote in tabella. L'ordine è quello in cui vanno lette: prima gli ingombri,
#: poi il guscio, poi le feature.
SPECS: tuple[DimensionSpec, ...] = (
    # --- scatola, ingombri -------------------------------------------------
    DimensionSpec("scatola.corpo.L", "Scatola · lunghezza corpo", "scatola.corpo.L",
                  note="senza cupola; con cupola 80.00 = tavola T1"),
    DimensionSpec("scatola.corpo.W", "Scatola · larghezza", "scatola.corpo.W"),
    DimensionSpec("scatola.corpo.H", "Scatola · altezza", "scatola.corpo.H",
                  "scatola.corpo._H_misurata",
                  note="D7: la tavola arrotonda 26.999 a 27.00"),

    # --- scatola, guscio ---------------------------------------------------
    DimensionSpec("scatola.pareti.t_x", "Spessore pareti X", "scatola.pareti.t_x",
                  "scatola.pareti._t_x_misurato", decision="B"),
    DimensionSpec("scatola.pareti.t_y", "Spessore pareti Y", "scatola.pareti.t_y",
                  "scatola.pareti._t_y_misurato", decision="B"),
    DimensionSpec("scatola.fondo.t", "Spessore fondo", "scatola.fondo.t",
                  "scatola.fondo._misurato"),
    DimensionSpec("scatola.raccordo_base.R", "Scatola · raccordo di base",
                  "scatola.raccordo_base.R", NO_SCALAR, decision="A",
                  note="nella mesh è ellittico 1.514 (X) × 1.422 (Z)"),
    DimensionSpec("scatola.cavita.L", "Cavità · lunghezza", "scatola.cavita.L",
                  "scatola.cavita._misurata.0"),
    DimensionSpec("scatola.cavita.W", "Cavità · larghezza", "scatola.cavita.W",
                  "scatola.cavita._misurata.1"),

    # --- scatola, cupola (paraboloide ellittico, decisione C) --------------
    DimensionSpec("scatola.cupola.x0", "Cupola · vertice X", "scatola.cupola.x0",
                  decision="C"),
    DimensionSpec("scatola.cupola.a", "Cupola · semiasse a (X)", "scatola.cupola.a",
                  decision="C"),
    DimensionSpec("scatola.cupola.b", "Cupola · semiasse b (Y)", "scatola.cupola.b",
                  decision="C"),
    DimensionSpec("scatola.cupola.c", "Cupola · semiasse c (Z)", "scatola.cupola.c",
                  decision="C"),
    DimensionSpec("scatola.cupola.cy", "Cupola · centro Y", "scatola.cupola.cy",
                  "scatola.cupola._cy_misurato",
                  note="portato a 0 per simmetria: la mesh dà −0.0175"),
    DimensionSpec("scatola.cupola.cz", "Cupola · centro Z", "scatola.cupola.cz"),

    # --- scatola, fori e tasche -------------------------------------------
    DimensionSpec("scatola.foro_parete_dx.D", "Foro parete destra · Ø",
                  "scatola.foro_parete_dx.D", note="fit rms 0.0016: cilindro netto"),
    DimensionSpec("scatola.asola_frontale.L_x", "Asola frontale · lunghezza",
                  "scatola.asola_frontale.L_x"),
    DimensionSpec("scatola.asola_frontale.H_z", "Asola frontale · altezza",
                  "scatola.asola_frontale.H_z"),
    DimensionSpec("scatola.tasca_sx.W_y", "Tasca faccia X− · larghezza",
                  "scatola.tasca_sx.W_y"),
    DimensionSpec("scatola.tasca_sx.H_z", "Tasca faccia X− · altezza",
                  "scatola.tasca_sx.H_z"),
    DimensionSpec("scatola.tasca_sx.prof", "Tasca faccia X− · profondità",
                  "scatola.tasca_sx.prof"),
    DimensionSpec("scatola.tasca_sx.rilievo.W_z", "Rilievo nella tasca · larghezza",
                  "scatola.tasca_sx.rilievo.W_z"),
    DimensionSpec("scatola.tasca_sx.rilievo.L_y", "Rilievo nella tasca · lunghezza",
                  "scatola.tasca_sx.rilievo.L_y"),

    # --- scatola, interni --------------------------------------------------
    DimensionSpec("scatola.colonnine.standard.L_x", "Colonnine · lato X",
                  "scatola.colonnine.standard.L_x"),
    DimensionSpec("scatola.colonnine.standard.W_y", "Colonnine · lato Y",
                  "scatola.colonnine.standard.W_y"),
    DimensionSpec("scatola.colonnine.standard.z_base", "Colonnine · quota di attacco",
                  "scatola.colonnine.standard.z_base"),
    DimensionSpec("scatola.colonnine.standard.smusso_z_top", "Colonnine · fine smusso",
                  "scatola.colonnine.standard.smusso_z_top"),
    DimensionSpec("scatola.colonnine.standard.foro.W", "Asola colonnine · larghezza",
                  "scatola.colonnine.standard.foro.W", decision="E"),
    DimensionSpec("scatola.colonnine.standard.foro.L", "Asola colonnine · lunghezza",
                  "scatola.colonnine.standard.foro.L", decision="E"),
    DimensionSpec("scatola.colonnine.speciale.W_y", "Blocco speciale · lato Y",
                  "scatola.colonnine.speciale.W_y",
                  note="il 4° angolo non è una colonnina: blocco basso, senza smusso"),
    DimensionSpec("scatola.colonnine.speciale.z_base", "Blocco speciale · quota di attacco",
                  "scatola.colonnine.speciale.z_base"),
    DimensionSpec("scatola.colonnine.speciale.foro.L", "Asola blocco speciale · lunghezza",
                  "scatola.colonnine.speciale.foro.L", decision="E"),
    DimensionSpec("scatola.nervature.t_x", "Nervature · spessore",
                  "scatola.nervature.t_x"),

    # --- coperchio ---------------------------------------------------------
    DimensionSpec("coperchio.piastra.L", "Coperchio · lunghezza",
                  "coperchio.piastra.L", "coperchio.piastra._L_mesh", decision="F",
                  note="F: portato a filo esterno del corpo scatola (−0.140)"),
    DimensionSpec("coperchio.piastra.W", "Coperchio · larghezza", "coperchio.piastra.W"),
    DimensionSpec("coperchio.piastra.S", "Coperchio · spessore", "coperchio.piastra.S"),
    DimensionSpec("coperchio.raccordo_base.R", "Coperchio · raccordo di base",
                  "coperchio.raccordo_base.R", NO_SCALAR, decision="A",
                  note="nella mesh è ellittico 1.484 (XY) × 1.801 (Z)"),
    DimensionSpec("coperchio.asole.W", "Asole coperchio · larghezza",
                  "coperchio.asole.W", decision="E"),
    DimensionSpec("coperchio.asole.L", "Asole coperchio · lunghezza",
                  "coperchio.asole.L", decision="E"),
    DimensionSpec("coperchio.tasca_grande.L_x", "Tasca grande · lunghezza",
                  "coperchio.tasca_grande.L_x"),
    DimensionSpec("coperchio.tasca_grande.W_y", "Tasca grande · larghezza",
                  "coperchio.tasca_grande.W_y"),
    DimensionSpec("coperchio.tasca_grande.prof", "Tasca grande · profondità",
                  "coperchio.tasca_grande.prof"),
    DimensionSpec("coperchio.tasca_annidata.L_x", "Tasca annidata · lunghezza",
                  "coperchio.tasca_annidata.L_x"),
    DimensionSpec("coperchio.tasca_annidata.W_y", "Tasca annidata · larghezza",
                  "coperchio.tasca_annidata.W_y"),
    DimensionSpec("coperchio.tasche_piccole.L_x", "Tasche piccole · lunghezza",
                  "coperchio.tasche_piccole.L_x"),
    DimensionSpec("coperchio.tasche_piccole.W_y", "Tasche piccole · larghezza",
                  "coperchio.tasche_piccole.W_y"),
)


BY_ID = {spec.id: spec for spec in SPECS}


def read(params: dict[str, Any], path: str) -> Any:
    """Legge un percorso puntato. Gli indici interi attraversano le liste."""
    node: Any = params
    for key in path.split("."):
        node = node[int(key)] if isinstance(node, list) else node[key]
    return node


def write(params: dict[str, Any], path: str, value: Any) -> None:
    keys = path.split(".")
    node: Any = params
    for key in keys[:-1]:
        node = node[int(key)] if isinstance(node, list) else node[key]
    last = keys[-1]
    if isinstance(node, list):
        node[int(last)] = value
    else:
        node[last] = value


def measured_value(params: dict[str, Any], spec: DimensionSpec) -> float | None:
    """La misura corrispondente a una quota, o None se non esiste come scalare."""
    if isinstance(spec.measured, NoScalarMeasurement):
        return None
    source = spec.measured or spec.path
    try:
        return float(read(params, source))
    except (KeyError, IndexError, TypeError):
        return None


def proposed_value(params: dict[str, Any], spec: DimensionSpec) -> float | None:
    """Il valore che `tools/extract_params.py` propone per il costruttore."""
    try:
        return float(read(params, spec.path))
    except (KeyError, IndexError, TypeError):
        return None


def all_paths() -> Sequence[str]:
    return tuple(spec.path for spec in SPECS)
