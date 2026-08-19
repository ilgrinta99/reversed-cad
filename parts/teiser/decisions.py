"""Le 7 ambiguità (A–G) e le 8 discrepanze (D1–D8) del contenitore TAISER.

**Trascritte** da `docs/lost+found_design.md` §4, §5 e §6. Nessun contenuto è
inventato qui: domande, evidenze e risposte vengono da quel documento, e i valori
delle opzioni dal `cad/params.json` di riferimento, che è il file che il
costruttore legge davvero.

Le A–G risultano già risolte, con la risposta data dal committente il 2026-08-19:
non è un default nascosto, è un fatto registrato. Restano modificabili, e cambiarne
una riscrive le quote che governa — con la nuova motivazione al posto di quella
storica.

Le D1–D8 non sono scelte ma constatazioni: la tavola TinkerCAD tace su quasi tutto.
Compaiono come schede prese d'atto perché il punto che documentano — *quella tavola
non è una fonte* — è la cosa più importante che un utente di questa app debba
sapere.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from core.provenance import Decision, DecisionKind, DecisionSet, Option

#: Il params.json committato: è il valore registrato per il pezzo di riferimento.
_REFERENCE = Path(__file__).resolve().parents[2] / "cad" / "params.json"

#: Data delle decisioni del committente (lost+found_design.md §6).
DECIDED_AT = datetime(2026, 8, 19, tzinfo=timezone.utc)
DECIDED_BY = "committente"
SOURCE = "docs/lost+found_design.md §6"


def _ref() -> dict:
    return json.loads(_REFERENCE.read_text())


def _v(params: dict, path: str) -> float:
    node = params
    for key in path.split("."):
        node = node[int(key)] if isinstance(node, list) else node[key]
    return float(node)


def build() -> DecisionSet:
    p = _ref()
    ds = DecisionSet()

    # ---------------------------------------------------------------- A–G
    ds.add(_resolved(Decision(
        id="A",
        kind=DecisionKind.AMBIGUITY,
        title="Raccordi non circolari",
        question="I raccordi perimetrali della mesh sono ellittici. Li ricostruisco "
                 "come raccordi circolari di raggio nominale, o li replico ellittici "
                 "per fedeltà 1:1?",
        evidence="Coperchio 1.484 in XY contro 1.801 in Z; scatola ≈1.514 in X contro "
                 "≈1.422 in Z. È il comportamento della primitiva «box arrotondato» di "
                 "TinkerCAD scalata in modo non uniforme: non è una scelta di progetto.",
        reference="docs/lost+found_design.md §5-A, §6",
        options=(
            Option(id="circolare", label="Raccordi circolari R1.5",
                   sets={"scatola.raccordo_base.R": _v(p, "scatola.raccordo_base.R"),
                         "coperchio.raccordo_base.R": _v(p, "coperchio.raccordo_base.R")},
                   consequence="Più pulito e tecnicamente corretto. È l'unico scostamento "
                               "residuo oltre 0.5 mm nel confronto finale (max 0.62 mm)."),
            Option(id="ellittico", label="Raccordi ellittici fedeli alla mesh",
                   consequence="Azzererebbe l'ultimo scostamento, ma `makeFillet` non fa "
                               "raccordi ellittici: servirebbe uno sweep dedicato, che "
                               "cad/build_model.py oggi non ha. Scegliendo questa opzione "
                               "le due quote restano da definire e la build non parte."),
        ),
    ), "circolare", "Default proposto nel briefing, non contestato."))

    ds.add(_resolved(Decision(
        id="B",
        kind=DecisionKind.AMBIGUITY,
        title="Spessore pareti asimmetrico",
        question="Uniformo le pareti a un unico spessore di progetto, o mantengo "
                 "l'asimmetria misurata?",
        evidence="1.293 mm sulle pareti X contro 2.188 mm sulle pareti Y, rapporto 1.692. "
                 "Nessuno dei due è un valore di progetto plausibile: è ancora la firma di "
                 "una primitiva scalata in modo non uniforme.",
        reference="docs/lost+found_design.md §5-B, §6",
        options=(
            Option(id="asimmetrico", label="Mantieni l'asimmetria, arrotondata al decimo",
                   sets={"scatola.pareti.t_x": _v(p, "scatola.pareti.t_x"),
                         "scatola.pareti.t_y": _v(p, "scatola.pareti.t_y")},
                   consequence="t_x = 1.3, t_y = 2.2. Fedele al pezzo, scostamento ≤ 0.012 mm."),
            Option(id="misurato", label="Usa i valori misurati, senza arrotondare",
                   accept_measured=("scatola.pareti.t_x", "scatola.pareti.t_y"),
                   consequence="t_x = 1.293, t_y = 2.188. Fedeltà massima, quote non tonde."),
        ),
    ), "asimmetrico", "Mantenere l'asimmetria misurata."))

    ds.add(_resolved(Decision(
        id="C",
        kind=DecisionKind.AMBIGUITY,
        title="Geometria della cupola",
        question="Semi-ellissoide approssimato, o superficie fedele ricostruita dalle "
                 "sezioni della mesh?",
        evidence="Il test di ellissoide dà scarto medio 12.5 % e massimo 25.7 %: non è un "
                 "ellissoide. Il fitting di un superellissoide ha dato p = 1.00, q = 2.00, "
                 "cioè un paraboloide ellittico esatto: scarto max 0.117 mm contro 1.610 mm "
                 "dell'ellissoide, e resta parametrico.",
        reference="docs/lost+found_design.md §5-C, §6, §7-C2",
        options=(
            Option(id="paraboloide", label="Paraboloide ellittico fittato",
                   accept_measured=("scatola.cupola.x0", "scatola.cupola.a",
                                    "scatola.cupola.b", "scatola.cupola.c",
                                    "scatola.cupola.cz"),
                   consequence="Scarto massimo 0.117 mm, con equazione analitica. È anche "
                               "la curva che la tavola usa al posto della silhouette HLR."),
            Option(id="ellissoide", label="Semi-ellissoide approssimato",
                   consequence="Più semplice ma scarto 1.610 mm: oltre ogni soglia di "
                               "docs/CONVENTIONS.md. cad/build_model.py non lo costruisce."),
        ),
    ), "paraboloide", "Il fitting ha dato un paraboloide esatto: meglio della via di mezzo."))

    ds.add(_resolved(Decision(
        id="D",
        kind=DecisionKind.AMBIGUITY,
        title="Aperture nella cupola",
        question="Le due aperture non danno un fit circolare accettabile. Cosa sono?",
        evidence="Risolta dall'analisi in FASE 3, non da una scelta: sono 2 fori a sezione "
                 "ellittica 2.418 × 2.113 con asse inclinato di 21.84° nel piano XY, "
                 "simmetrici. Il fit falliva perché li si assumeva paralleli a X.",
        reference="docs/lost+found_design.md §5-D, §7-C3",
        options=(
            Option(id="misurato", label="Fori ellittici inclinati, come misurati",
                   consequence="Residuo massimo 0.0 mm sulle sezioni di controllo."),
        ),
    ), "misurato", "Chiusa dall'analisi: la geometria è misurata, non scelta."))

    ds.add(_resolved(Decision(
        id="E",
        kind=DecisionKind.AMBIGUITY,
        title="Fori del coperchio",
        question="1.952 × 3.291 mm: sono asole, o fori circolari deformati dallo scaling?",
        evidence="Non sono circolari. Se sono asole servono raggio delle testate e "
                 "interasse; se erano intese come fori Ø2 deformati, va deciso il diametro "
                 "nominale.",
        reference="docs/lost+found_design.md §5-E, §6",
        options=(
            Option(id="asole", label="Asole fedeli alla mesh",
                   accept_measured=("coperchio.asole.W", "coperchio.asole.L",
                                    "scatola.colonnine.standard.foro.W",
                                    "scatola.colonnine.standard.foro.L",
                                    "scatola.colonnine.speciale.foro.L"),
                   consequence="Coperchio 1.948 × 3.291; fori colonnine 1.625 × 2.743, "
                               "e 1.625 × 3.158 sul blocco speciale."),
            Option(id="circolari", label="Fori circolari di diametro nominale",
                   consequence="Richiede un diametro che nessuna misura fornisce: andrebbe "
                               "approvato quota per quota. cad/build_model.py costruisce asole."),
        ),
    ), "asole", "Asole fedeli alla mesh."))

    ds.add(_resolved(Decision(
        id="F",
        kind=DecisionKind.AMBIGUITY,
        title="Accoppiamento scatola / coperchio",
        question="Coperchio a filo esterno, incassato, o appoggiato sulle colonnine?",
        evidence="Il coperchio misura 74.00 ma il corpo esterno della scatola è 73.86 e il "
                 "vano interno 71.27: né entra né combacia. Conferma indipendente: le asole "
                 "del coperchio stanno a ±33.105, i fori delle colonnine a ±33.0425, e il "
                 "fattore 73.86/74.00 = 0.998108 le porta esattamente sui fori. Il coperchio "
                 "era stato scalato per errore in Tinkercad.",
        reference="docs/lost+found_design.md §5-F, §6, §6.1",
        options=(
            Option(id="filo_esterno", label="A filo esterno, avvitato sulle colonnine",
                   sets={"coperchio.piastra.L": _v(p, "coperchio.piastra.L")},
                   consequence="Coperchio da 74.00 a 73.86. Unico scostamento dalla tavola "
                               "TinkerCAD (T4: −0.140 mm), deliberato."),
            Option(id="mesh", label="Lascia la lunghezza della mesh",
                   accept_measured=("coperchio.piastra.L",),
                   consequence="74.00 come la mesh e la tavola, ma le asole non cadono sui "
                               "fori delle colonnine: l'accoppiamento non chiude."),
        ),
    ), "filo_esterno", "Coperchio a filo esterno, avvitato sulle colonnine."))

    ds.add(_resolved(Decision(
        id="G",
        kind=DecisionKind.AMBIGUITY,
        title="Origine e datum",
        question="Dove metto l'origine del modello parametrico?",
        evidence="La mesh ha origine arbitraria: Z = 0 sul fondo, X e Y decentrati. Il "
                 "modello ha bisogno di un riferimento dichiarato.",
        reference="docs/lost+found_design.md §5-G, §6; docs/CONVENTIONS.md",
        options=(
            Option(id="centro_base", label="Origine al centro della base della scatola",
                   consequence="X = lunghezza, Y = larghezza, Z verso l'alto. "
                               "Traslazione mesh → modello: x+6.77, y+27.90."),
        ),
    ), "centro_base", "Default proposto, confermato."))

    ds.add(_resolved(Decision(
        id="S1",
        kind=DecisionKind.AMBIGUITY,
        title="Arrotondamenti proposti nel briefing",
        question="Le quote del guscio vanno arrotondate come proposto, o usate come misurate?",
        evidence="Sono la colonna «proposto» di §3.1, presentata nel briefing insieme alle "
                 "A–G e non contestata. Non hanno una lettera propria in §6, per questo "
                 "compaiono qui: altezza 26.999 → 27.0 (la stessa D7 della tavola), fondo "
                 "1.634 → 1.6, cavità 71.274 → 71.26 e 41.624 → 41.6, e il centro della "
                 "cupola −0.0175 → 0 per simmetria.",
        reference="docs/lost+found_design.md §3.1, §4-D7",
        options=(
            Option(id="proposti", label="Usa i valori proposti nel briefing",
                   sets={"scatola.corpo.H": _v(p, "scatola.corpo.H"),
                         "scatola.fondo.t": _v(p, "scatola.fondo.t"),
                         "scatola.cavita.L": _v(p, "scatola.cavita.L"),
                         "scatola.cavita.W": _v(p, "scatola.cavita.W"),
                         "scatola.cupola.cy": _v(p, "scatola.cupola.cy")},
                   consequence="Quote più leggibili; scostamento massimo 0.034 mm sul fondo, "
                               "ampiamente dentro le soglie di docs/CONVENTIONS.md."),
            Option(id="misurati", label="Usa i valori misurati, senza arrotondare",
                   accept_measured=("scatola.corpo.H", "scatola.fondo.t",
                                    "scatola.cavita.L", "scatola.cavita.W",
                                    "scatola.cupola.cy"),
                   consequence="Fedeltà massima alla mesh; la cupola perde la simmetria "
                               "esatta in Y (centro a −0.0175)."),
        ),
    ), "proposti", "Colonna «proposto» del briefing §3.1, presentata e non contestata."))

    # ------------------------------------------------------------- D1–D8
    for did, gravita, titolo, testo in _DISCREPANCIES:
        ds.add(_resolved(Decision(
            id=did,
            kind=DecisionKind.DISCREPANCY,
            title=f"{titolo} · gravità {gravita}",
            question="Constatazione sulla tavola TinkerCAD: nessuna quota ne dipende.",
            evidence=testo,
            reference="docs/lost+found_design.md §4",
            options=(Option(id="presa_atto", label="Presa d'atto",
                            consequence="La tavola non fornisce questa informazione: "
                                        "il valore viene dalla mesh."),),
        ), "presa_atto", "Catalogata in FASE 1."))

    return ds


def _resolved(decision: Decision, option_id: str, rationale: str) -> Decision:
    return decision.choose(option_id, by=DECIDED_BY,
                           rationale=f"{rationale} ({SOURCE})", at=DECIDED_AT)


_DISCREPANCIES: tuple[tuple[str, str, str, str], ...] = (
    ("D1", "alta", "La tavola disegna solo le sagome esterne",
     "Nessuna linea interna, nessuna linea nascosta, nessuna sezione. Cavità, pareti, "
     "fondo, colonnine, nervature: tutto invisibile."),
    ("D2", "alta", "La cupola non compare nella vista laterale",
     "La vista laterale della scatola è un rettangolo 46 × 27 pulito. La cupola "
     "(≈ 34.9 × 16.4 mm, il dettaglio dominante da quel lato) e le sue 2 aperture non "
     "compaiono affatto. La sagoma esterna è formalmente corretta perché la cupola sta "
     "dentro l'ingombro, ma la vista è priva del contenuto informativo principale."),
    ("D3", "alta", "Foro Ø3 e asola frontale assenti",
     "Il foro Ø3.005 sulla parete destra e l'asola 6.47 × 4.01 sulla parete frontale non "
     "compaiono in nessuna vista, pur essendo passanti e visibili dall'esterno."),
    ("D4", "media", "I 4 fori del coperchio sono disegnati ma non quotati",
     "Quattro piccoli ovali senza nessuna quota: né dimensione, né interasse, né distanza "
     "dai bordi."),
    ("D5", "media", "Le tasche del coperchio non compaiono",
     "Una 12.03 × 12.87, una annidata 4.63 × 4.95, due da 2.78 × 2.97: la vista dall'alto "
     "del coperchio è disegnata come un rettangolo vuoto."),
    ("D6", "bassa", "Nessuna tolleranza, nessun datum",
     "Nessuna indicazione di stato superficiale o materiale. Per un accoppiamento "
     "scatola/coperchio l'accoppiamento resta indefinito."),
    ("D7", "bassa", "Altezza 27.00 contro 26.999 misurati",
     "Scarto trascurabile, ma conferma che la tavola è generata dalla mesh e arrotondata "
     "a due decimali."),
    ("D8", "bassa", "La tavola non indica come i due pezzi si accoppiano",
     "Nel file OBJ sono affiancati, non assemblati. È la domanda a cui risponde la "
     "decisione F."),
)
