"""Dalle misure alle domande: le ambiguità che *questa* mesh solleva.

Il progetto ha una regola sola, e non è negoziabile: nessuna quota inventata. Da
lì discende tutto quello che c'è qui dentro. Un'analisi che «aggiusta» in silenzio
un raggio incoerente o uno spessore asimmetrico sta inventando; un'analisi che si
limita a misurare e poi tace lascia all'utente un elenco di numeri senza dirgli
dove sono i punti dolenti. La via di mezzo è questa: si misura, e dove la misura
**non è conclusiva** si formula una domanda, con l'evidenza sotto e le opzioni
numeriche già calcolate dalla mesh.

Le famiglie di ambiguità sono quelle che un disegnatore incontra davvero:

* **raccordo non circolare** — lo spigolo è arretrato di due quantità diverse sui
  due lati: non esiste un raggio, ne esistono due;
* **pareti asimmetriche** — lo spessore cambia da un asse all'altro;
* **superfici libere** — la mesh contiene forme che nessuna primitiva descrive;
* **archi parziali** — un quarto di cilindro: raccordo, o testata di un'asola?
* **asole** — feature allungate che un foro circolare non rappresenta;
* **più corpi** — quale è il pezzo, e cosa sono gli altri;
* **datum arbitrario** — l'origine della mesh non significa niente;
* **arrotondamento** — le quote sono a un soffio da valori tondi.

Nessuna di queste è cablata su un pezzo: sono proprietà della mesh caricata, e i
numeri delle opzioni escono dall'analisi di quella mesh.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from core.mesh.analysis import MeshAnalysis
from core.provenance import (
    Decision,
    DecisionKind,
    DecisionSet,
    Dimension,
    Option,
    Registry,
)

MEASURED_BY = "core/mesh/analysis.py"

#: Passi di arrotondamento proposti, dal più fine al più grosso.
ROUNDING_STEPS = (0.1, 0.5, 1.0)

#: Due spessori che differiscono di meno di così sono lo stesso spessore.
WALL_SAME = 0.02

#: Una quota si considera «a un soffio» da un valore tondo entro un quarto di passo.
NEAR_ROUND = 0.25

#: Sotto questa area una superficie libera è un dettaglio di tassellazione.
FREE_AREA_MIN = 5.0


@dataclass
class Reading:
    """Esito della lettura: quote misurate e domande aperte."""

    registry: Registry
    decisions: DecisionSet
    notes: list[str]


def read(analysis: MeshAnalysis) -> Reading:
    """Costruisce registro delle quote e schede di decisione da un'analisi.

    Le quote misurate entrano nel modello con il valore misurato: usare la misura
    non è mai un'invenzione, ed è il motivo per cui una mesh senza ambiguità
    arriva alla build senza chiedere nulla. Le quote per cui una misura scalare
    *non esiste* restano vuote, e bloccano la build finché una decisione non le
    approva.
    """
    registry = Registry()
    for measurement in analysis.measurements:
        registry.add(Dimension(
            id=measurement.id,
            label=measurement.label,
            unit=measurement.unit,
            measured=measurement.value,
            used=measurement.value,  # la misura è già un'origine legittima
            measured_by=measurement.source,
            note=measurement.note,
        ))

    decisions = DecisionSet()
    for decision in _detect(analysis, registry):
        decisions.add(decision)

    notes = list(analysis.notes)
    if len(decisions) == 0:
        notes.append(
            "Nessuna ambiguità: ogni quota in tabella è misurata dalla mesh e "
            "nessuna lettura è in conflitto con un'altra."
        )
    return Reading(registry=registry, decisions=decisions, notes=notes)


def _detect(analysis: MeshAnalysis, registry: Registry) -> list[Decision]:
    found: list[Decision] = []
    found.extend(_non_circular_roundings(analysis, registry))
    found.extend(_asymmetric_walls(analysis, registry))
    found.extend(_slots(analysis))
    found.extend(_unpaired_arcs(analysis))
    found.extend(_free_surfaces(analysis))
    found.extend(_multiple_bodies(analysis))
    found.extend(_datum(analysis, registry))
    # L'arrotondamento va posto per ultimo: è la domanda che resta quando le
    # altre non si presentano, ed è quella che l'utente vede da sola su una mesh
    # pulita.
    found.extend(_rounding(analysis, registry))
    return found


# -- raccordi non circolari -------------------------------------------------


def _non_circular_roundings(analysis: MeshAnalysis, registry: Registry) -> list[Decision]:
    out: list[Decision] = []
    for body in analysis.bodies:
        for rounding in body.roundings:
            if rounding.get("kind") != "spigolo" or rounding.get("circular", True):
                continue
            along, across = rounding["along"], rounding["across"]
            value_along, value_across = rounding["value_along"], rounding["value_across"]
            edge = rounding["edge"].replace("/", "_").replace("-", "").lower()
            base = f"{body.key}_raccordo_{edge}"
            dim_along, dim_across = f"{base}_{along.lower()}", f"{base}_{across.lower()}"
            single = f"{base}_r"
            if single not in registry:
                # Il raggio unico non esiste nella mesh: la quota nasce vuota, e
                # solo una decisione può riempirla.
                registry.add(Dimension(
                    id=single,
                    label=f"{body.name} · raccordo {rounding['edge']} · raggio",
                    note="nessun raggio unico misurabile: i due arretramenti "
                         "differiscono",
                ))
            ratio = max(value_along, value_across) / max(min(value_along, value_across), 1e-9)
            out.append(Decision(
                id=base,
                kind=DecisionKind.AMBIGUITY,
                title=f"Raccordo non circolare · {body.name} {rounding['edge']}",
                question="Ricostruisco lo spigolo come raccordo circolare, e con quale "
                         "raggio, oppure lo lascio ellittico come la mesh lo porta?",
                evidence=(
                    f"La faccia si arretra di {value_along:.4f} mm lungo {along} e di "
                    f"{value_across:.4f} mm lungo {across}: rapporto {ratio:.3f}. Un "
                    f"raccordo circolare avrebbe due arretramenti uguali. Un raggio "
                    f"unico, qui, non è misurabile: va scelto."
                ),
                options=(
                    Option(id=f"circolare_{along.lower()}",
                           label=f"Circolare R{value_along:.3f} (arretramento su {along})",
                           sets={single: value_along},
                           consequence=f"Scostamento fino a "
                                       f"{abs(value_along - value_across):.3f} mm sull'altro lato."),
                    Option(id=f"circolare_{across.lower()}",
                           label=f"Circolare R{value_across:.3f} (arretramento su {across})",
                           sets={single: value_across},
                           consequence=f"Scostamento fino a "
                                       f"{abs(value_along - value_across):.3f} mm sull'altro lato."),
                    Option(id="ellittico",
                           label="Ellittico, fedele alla mesh",
                           consequence="Azzererebbe lo scostamento, ma il costruttore "
                                       "parametrico non fa raccordi ellittici: la quota "
                                       "resta senza valore e la build non parte."),
                ),
                reference="core/mesh/analysis.py · arretramento delle facce piane",
            ))
    return out


# -- pareti asimmetriche ----------------------------------------------------


def _asymmetric_walls(analysis: MeshAnalysis, registry: Registry) -> list[Decision]:
    out: list[Decision] = []
    for body in analysis.bodies:
        walls = {k: v for k, v in body.walls.items() if not k.startswith("Z")}
        if len(walls) < 2:
            continue
        low, high = min(walls.values()), max(walls.values())
        if high - low <= WALL_SAME:
            continue
        ids = {key: f"{body.key}_parete_{key.split('-')[0].lower()}_{key.split('-')[1]}"
               for key in walls}
        detail = ", ".join(f"{k} {v:.4f}" for k, v in sorted(walls.items()))
        out.append(Decision(
            id=f"{body.key}_pareti",
            kind=DecisionKind.AMBIGUITY,
            title=f"Spessore di parete asimmetrico · {body.name}",
            question="Uniformo le pareti a un unico spessore, o mantengo "
                     "l'asimmetria che la mesh misura?",
            evidence=(
                f"Spessori misurati: {detail} mm. Il rapporto fra il massimo e il "
                f"minimo è {high / max(low, 1e-9):.3f}. Un pezzo progettato ha di "
                f"norma una parete sola; una primitiva scalata in modo non uniforme "
                f"ne ha due."
            ),
            options=(
                Option(id="misurato", label="Mantieni l'asimmetria misurata",
                       accept_measured=tuple(ids.values()),
                       consequence="Il modello resta fedele alla mesh."),
                Option(id="minimo", label=f"Uniforma a {low:.3f} mm (il più sottile)",
                       sets={dim: low for dim in ids.values()},
                       consequence=f"Le pareti più spesse calano di "
                                   f"{high - low:.3f} mm."),
                Option(id="massimo", label=f"Uniforma a {high:.3f} mm (il più spesso)",
                       sets={dim: high for dim in ids.values()},
                       consequence=f"Le pareti più sottili crescono di "
                                   f"{high - low:.3f} mm."),
            ),
            reference="core/mesh/analysis.py · faccia esterna → faccia interna",
        ))
    return out


# -- asole e archi ----------------------------------------------------------


def _slots(analysis: MeshAnalysis) -> list[Decision]:
    out: list[Decision] = []
    for body in analysis.bodies:
        slots = [h for h in body.holes if h["slot"]]
        if not slots:
            continue
        widths = ", ".join(f"{s['width']:.3f} × {s['length']:.3f}" for s in slots[:4])
        out.append(Decision(
            id=f"{body.key}_asole",
            kind=DecisionKind.AMBIGUITY,
            title=f"Asole o fori circolari · {body.name}",
            question="Le riproduco come asole fedeli alla mesh, o come fori "
                     "circolari del diametro misurato sulle testate?",
            evidence=(
                f"{len(slots)} feature con due testate cilindriche coassiali dello "
                f"stesso raggio: {widths} mm. Un foro circolare avrebbe una testata "
                f"sola. Possono essere asole volute, oppure fori deformati da una "
                f"scalatura non uniforme."
            ),
            options=(
                Option(id="asole", label="Asole fedeli alla mesh",
                       consequence="Il costruttore parametrico non le realizza ancora: "
                                   "restano fuori dal solido, e il confronto lo mostrerà."),
                Option(id="fori", label="Fori circolari del diametro delle testate",
                       consequence="Il solido perde l'allungamento dell'asola."),
            ),
            reference="core/mesh/analysis.py · testate coassiali di pari raggio",
        ))
    return out


def _unpaired_arcs(analysis: MeshAnalysis) -> list[Decision]:
    """Una scheda sola per tutti gli archi spaiati: la domanda è la stessa.

    Sei corpi con lo stesso dubbio non sono sei dubbi. Le evidenze restano tutte,
    corpo per corpo, dentro un'unica scheda.
    """
    arcs = [(body, arc) for body in analysis.bodies for arc in body.arcs
            if arc["area"] >= FREE_AREA_MIN]
    if not arcs:
        return []
    by_body: dict[str, list[str]] = {}
    for body, arc in arcs:
        by_body.setdefault(body.name, []).append(f"R{arc['radius']:.3f}")
    detail = "; ".join(f"{name}: {', '.join(radii)}" for name, radii in by_body.items())
    return [Decision(
        id="archi_parziali",
        kind=DecisionKind.AMBIGUITY,
        title=f"{len(arcs)} archi cilindrici parziali",
        question="Sono raccordi di spigolo, o testate di feature che la mesh non chiude?",
        evidence=(
            f"{len(arcs)} porzioni di cilindro non arrivano a un giro completo e non "
            f"si appaiano fra loro. Un foro darebbe un cilindro intero; un'asola "
            f"darebbe due archi uguali affacciati. Raggi misurati — {detail}."
        ),
        options=(
            Option(id="raccordi", label="Sono raccordi: li lascio alla superficie",
                   consequence="Nessuna quota nuova; il solido resta senza quei "
                               "raccordi e lo scostamento resta visibile."),
            Option(id="da_verificare", label="Da verificare a mano",
                   consequence="La lettura resta registrata come aperta: nessun "
                               "numero entra nel modello."),
        ),
        reference="core/mesh/analysis.py · cilindri parziali",
    )]


# -- superfici libere -------------------------------------------------------


def _free_surfaces(analysis: MeshAnalysis) -> list[Decision]:
    surfaces = [(body, patch) for body in analysis.bodies for patch in body.free_patches
                if patch.area >= FREE_AREA_MIN]
    if not surfaces:
        return []
    total = sum(p.area for _, p in surfaces)
    biggest = max(surfaces, key=lambda item: item[1].area)[1]
    return [Decision(
        id="superfici_libere",
        kind=DecisionKind.AMBIGUITY,
        title="Superfici non riconducibili a una primitiva",
        question="Costruisco il modello senza queste superfici, o mi fermo qui?",
        evidence=(
            f"{len(surfaces)} superfici per {total:.0f} mm² non sono né piani né "
            f"cilindri né sfere entro la tolleranza di lettura. La più estesa misura "
            f"{biggest.area:.0f} mm² su un ingombro di {biggest.extents[0]:.2f} × "
            f"{biggest.extents[1]:.2f} × {biggest.extents[2]:.2f} mm. Ricostruirle "
            f"richiede una superficie dedicata: approssimarle con una primitiva "
            f"sarebbe una quota inventata."
        ),
        options=(
            Option(id="ignora",
                   label="Costruisci senza: lo scostamento resterà misurato",
                   consequence="Il confronto modello ↔ mesh mostrerà esattamente "
                               "dove e quanto il solido si discosta."),
            Option(id="fermati", label="Fermati: servono superfici dedicate",
                   consequence="Nessuna build finché non si aggiunge il ricostruttore."),
        ),
        reference="core/mesh/patches.py · classificazione delle patch",
    )]


# -- più corpi --------------------------------------------------------------


def _multiple_bodies(analysis: MeshAnalysis) -> list[Decision]:
    if len(analysis.bodies) < 2:
        return []
    detail = "; ".join(
        f"{b.name} {b.extents[0]:.2f} × {b.extents[1]:.2f} × {b.extents[2]:.2f}"
        for b in analysis.bodies[:6]
    )
    return [Decision(
        id="corpi",
        kind=DecisionKind.AMBIGUITY,
        title=f"{len(analysis.bodies)} corpi separati nella mesh",
        question="Sono tutti parte del pezzo, o solo il principale lo è?",
        evidence=(
            f"La mesh contiene {len(analysis.bodies)} gruppi di triangoli connessi, "
            f"senza spigoli in comune: {detail}. Possono essere un assieme, oppure "
            f"un pezzo con feature staccate dall'esportazione."
        ),
        options=(
            Option(id="tutti", label="Tutti: è un assieme",
                   consequence="Ogni corpo viene costruito come solido a sé."),
            Option(id="principale", label=f"Solo {analysis.bodies[0].name}",
                   consequence="Gli altri corpi restano misurati ma fuori dal solido."),
        ),
        reference="core/mesh/patches.py · componenti connesse per spigolo",
    )]


# -- datum ------------------------------------------------------------------


def _datum(analysis: MeshAnalysis, registry: Registry) -> list[Decision]:
    if not analysis.bodies:
        return []
    body = analysis.bodies[0].body
    low, high = body.bbox_min, body.bbox_max
    centre = [(float(low[k]) + float(high[k])) / 2.0 for k in range(3)]
    # Due sistemazioni sono deliberate e non vanno messe in discussione: il pezzo
    # centrato sull'origine, e il pezzo con lo spigolo dell'ingombro sull'origine.
    # Il dubbio nasce quando l'origine non coincide con nessuna delle due.
    on_centre = max(abs(centre[0]), abs(centre[1]), abs(float(low[2])))
    on_corner = max(abs(float(low[k])) for k in range(3))
    if min(on_centre, on_corner) <= 0.5:
        return []
    return [Decision(
        id="datum",
        kind=DecisionKind.AMBIGUITY,
        title="Origine della mesh arbitraria",
        question="Tengo il sistema di riferimento della mesh, o riporto l'origine "
                 "al centro della base?",
        evidence=(
            f"L'ingombro del corpo principale va da "
            f"({low[0]:.3f}, {low[1]:.3f}, {low[2]:.3f}) a "
            f"({high[0]:.3f}, {high[1]:.3f}, {high[2]:.3f}) mm: il centro in pianta "
            f"cade a ({centre[0]:.3f}, {centre[1]:.3f}) e la base a z = {low[2]:.3f}. "
            f"L'origine del file non coincide con nessun riferimento del pezzo."
        ),
        options=(
            Option(id="mesh", label="Tieni il riferimento della mesh",
                   consequence="Le coordinate del modello coincidono con quelle del "
                               "file: il confronto è diretto."),
            Option(id="centro_base", label="Origine al centro della base",
                   consequence="Quote più leggibili in tavola; il confronto con la "
                               "mesh passa per una traslazione registrata."),
        ),
        reference="docs/CONVENTIONS.md · unità e sistema di riferimento",
    )]


# -- arrotondamento ---------------------------------------------------------


def _rounding(analysis: MeshAnalysis, registry: Registry) -> list[Decision]:
    """La domanda che resta quando non ce ne sono altre.

    Una mesh esportata porta quote come 26.999 o 1.634: numeri che *quasi* sono
    valori di progetto. Arrotondarli d'ufficio sarebbe inventare; ignorarli
    lascerebbe un modello parametrico pieno di decimali senza significato. Qui
    diventano una scelta, con lo scostamento che ciascun passo comporta scritto
    accanto.
    """
    candidates = [d for d in registry if d.measured is not None]
    if not candidates:
        return []

    options: list[Option] = [
        Option(id="misura", label="Tieni le misure così come sono",
               accept_measured=tuple(d.id for d in candidates),
               consequence="Il modello resta fedele alla mesh, decimali inclusi."),
    ]
    for step in ROUNDING_STEPS:
        changed = {}
        worst = 0.0
        for dim in candidates:
            assert dim.measured is not None
            snapped = round(dim.measured / step) * step
            delta = abs(snapped - dim.measured)
            if delta <= dim.tolerance or delta > NEAR_ROUND * step:
                continue  # già tondo, oppure troppo lontano perché sia «quasi tondo»
            changed[dim.id] = round(snapped, 6)
            worst = max(worst, delta)
        if not changed:
            continue
        options.append(Option(
            id=f"passo_{step:g}".replace(".", "_"),
            label=f"Arrotonda al passo di {step:g} mm",
            sets=changed,
            consequence=(f"{len(changed)} quote su {len(candidates)} cambiano, "
                         f"scostamento massimo {worst:.4f} mm."),
        ))
    if len(options) == 1:
        return []  # niente da arrotondare: nessuna domanda da porre

    near = sum(len(o.sets) for o in options[1:])
    return [Decision(
        id="arrotondamento",
        kind=DecisionKind.AMBIGUITY,
        title="Arrotondamento congruente delle quote",
        question="Porto le quote a valori tondi, con lo stesso passo per tutte, "
                 "o tengo la misura?",
        evidence=(
            f"Su {len(candidates)} quote misurate, alcune cadono a meno di un quarto "
            f"di passo da un valore tondo (in tutto {near} occorrenze fra i passi "
            f"proposti): è la firma di un modello nato tondo e poi scalato. Un passo "
            f"unico per tutte le quote mantiene congruenti i rapporti fra le parti; "
            f"arrotondarne una sola no."
        ),
        options=tuple(options),
        reference="core/mesh/ambiguity.py · passi 0.1 / 0.5 / 1 mm",
    )]
