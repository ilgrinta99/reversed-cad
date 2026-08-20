"""Composizione della tavola per il ricostruttore automatico.

Sta in `parts/auto/` e non in `core/` perché conosce la *ricetta*: sa che un corpo
è un prisma con un eventuale raccordo verticale, una cavità e dei fori, e da lì
decide quali viste servono, dove passano i piani di sezione e quali quote hanno un
senso. Il modo in cui una quota viene disegnata, invece, è di `core/drafting/`.

Ogni numero che finisce sulla tavola viene dal registro delle quote — cioè è
misurato sulla mesh o approvato — tranne gli ingombri d'assieme del foglio 1, che
sono misurati sul solido costruito e dichiarati come tali in nota. Le posizioni
(dove passa una parete, dove sta un foro) vengono dalla ricetta, che a sua volta
è fatta di quote del registro.

Il flusso è in due tempi, e non può essere altrimenti: prima si dichiara *quali*
viste servono (`viste_richieste`), FreeCAD le proietta, e solo dopo — conoscendo
l'ingombro reale di ogni proiezione — si sceglie la scala e si impagina (`fogli`).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from core.drafting import layout, tavola
from core.drafting.layout import ISOMETRICA
from core.provenance import Registry

#: Direzioni delle tre viste ortogonali: (u = destra sul foglio, w = alto).
DIREZIONI = {
    "pianta": ((1, 0, 0), (0, 1, 0)),        # osservatore in +Z
    "prospetto": ((1, 0, 0), (0, 0, 1)),     # osservatore in -Y
    "laterale": ((0, 1, 0), (0, 0, 1)),      # osservatore in +X
}

#: Indice dell'asse del modello che finisce sull'asse orizzontale e verticale di
#: ciascuna vista. Serve a portare un punto 3D nelle coordinate della vista senza
#: rifare i conti della proiezione.
ASSI = {"pianta": (0, 1), "prospetto": (0, 2), "laterale": (1, 2)}

#: Zone del foglio A3. Non si sovrappongono, e nessuna invade il cartiglio, che
#: occupa 15..185 × 15..74. La colonna di sinistra sopra il cartiglio è lo spazio
#: dell'assonometria: è l'unico posto di un A3 dove ci sta senza rubarlo alle viste.
#: Le viste hanno tutta la larghezza che la scala normalizzata richiede: quello che
#: avanza a sinistra va all'assonometria (`_zona_iso`). L'ordine conta — un A3 con
#: le viste a 1:1 per far posto a un'assonometria grande è una tavola sbagliata.
ZONA_VISTE = (90.0, 78.0, 408.0, 284.0)
ZONA_ISO = (14.0, 78.0, 126.0, 284.0)
ZONA_SEZIONI = (90.0, 78.0, 408.0, 284.0)
ZONA_TABELLA_X, ZONA_TABELLA_W = 200.0, 205.0

ORIGINE = "ricostruzione parametrica dalla mesh"


def sanitize(nome: str) -> str:
    """Stesso nome file che usa `build_script.py` per i corpi singoli."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in nome)


#: Sotto questo scarto due numeri sono lo stesso numero — è la tolleranza con cui
#: `core/provenance/` decide se misurato e usato divergono. Legare la stampa a
#: quella soglia evita sia di scrivere «46.000» per un 45.9999996 che viene dalla
#: precisione singola di uno STL, sia di nascondere una terza cifra che conta.
TOLLERANZA_STAMPA = 5e-4


def _num(v: float) -> str:
    """Due decimali quando bastano, tre quando servono. Mai arrotondare in silenzio."""
    return "%.2f" % v if abs(v - round(v, 2)) < TOLLERANZA_STAMPA else "%.3f" % v


def _ha_interno(body: dict) -> bool:
    return bool(body.get("cavity")) or bool(body.get("bores"))


def _centro(body: dict) -> list[float]:
    return [float(o) + float(s) / 2.0 for o, s in zip(body["origin"], body["size"])]


# ---------------------------------------------------------------- viste


def viste_richieste(recipe: dict) -> list[dict[str, Any]]:
    """Elenco delle viste da proiettare, nel formato di `core/drafting/project_script.py`.

    Un corpo produce sempre le tre viste ortogonali e l'assonometria; produce le
    tre sezioni solo se ha qualcosa dentro da mostrare.
    """
    viste: list[dict[str, Any]] = []
    for nome, (u, w) in DIREZIONI.items():
        viste.append({"id": f"assieme_{nome}", "shape": "assieme", "u": u, "w": w})
    viste.append({"id": "assieme_iso", "shape": "assieme",
                  "u": ISOMETRICA[0], "w": ISOMETRICA[1]})

    for body in recipe["bodies"]:
        key = body["key"]
        for nome, (u, w) in DIREZIONI.items():
            viste.append({"id": f"{key}_{nome}", "shape": key, "u": u, "w": w})
        viste.append({"id": f"{key}_iso", "shape": key,
                      "u": ISOMETRICA[0], "w": ISOMETRICA[1]})
        if not _ha_interno(body):
            continue
        centro = _centro(body)
        for lettera, nome, punto in (
            ("A", "prospetto", [0.0, centro[1], 0.0]),
            ("B", "laterale", [centro[0], 0.0, 0.0]),
            ("C", "pianta", [0.0, 0.0, _quota_sezione_c(body)]),
        ):
            u, w = DIREZIONI[nome]
            # La normale del piano è la direzione di vista: si asporta la metà
            # davanti all'osservatore, che è ciò che «sezione X-X» significa.
            viste.append({
                "id": f"{key}_sez{lettera}", "shape": key, "u": u, "w": w,
                "hidden": False,
                "section": {"point": punto, "normal": list(_normale(u, w))},
            })
    return viste


def _normale(u, w) -> tuple[float, float, float]:
    return (u[1] * w[2] - u[2] * w[1],
            u[2] * w[0] - u[0] * w[2],
            u[0] * w[1] - u[1] * w[0])


def _quota_sezione_c(body: dict) -> float:
    """Piano orizzontale della sezione C-C: sull'asse dei fori, se ce ne sono.

    Altrimenti a metà della cavità, dove le pareti si vedono tutte e quattro.
    """
    orizzontali = [b for b in body.get("bores", []) if b.get("axis") in ("X", "Y")]
    if orizzontali:
        return float(orizzontali[0]["center"][2])
    cavity = body.get("cavity")
    if cavity:
        base = float(body["origin"][2])
        return base + float(cavity["floor"]) + float(cavity["depth"]) / 2.0
    return float(body["origin"][2]) + float(body["size"][2]) / 2.0


def _punto_vista(nome: str, p) -> tuple[float, float]:
    """Un punto 3D del modello nelle coordinate 2D della vista."""
    i, j = ASSI[nome]
    return (float(p[i]), float(p[j]))


# ---------------------------------------------------------------- fogli


def fogli(recipe: dict, analysis: dict, registry: Registry, proiezioni: dict,
          *, sorgente: str, contorni: dict | None = None,
          decisioni: list[dict] | None = None,
          scostamento: dict | None = None) -> list[tavola.FoglioSpec]:
    """Tutta la tavola: assieme, un foglio per corpo, le sezioni, il registro."""
    valori = registry.values()
    contorni = contorni or {}
    out = [_foglio_assieme(recipe, proiezioni, sorgente)]
    for body in recipe["bodies"]:
        out.append(_foglio_corpo(body, valori, proiezioni, sorgente,
                                 contorni.get(body["key"], {})))
        if _ha_interno(body):
            out.append(_foglio_sezioni(body, valori, proiezioni, sorgente))
    out.extend(_fogli_registro(registry, analysis, sorgente,
                               decisioni=decisioni, scostamento=scostamento))
    return out


def _cartiglio(sottotitolo: str, scala: float, sorgente: str,
               note: tuple[str, ...]) -> layout.Cartiglio:
    """La fascia note del cartiglio tiene quattro righe: l'ultima è sempre la mesh."""
    return layout.Cartiglio(
        titolo="MODELLO RICOSTRUITO DALLA MESH",
        sottotitolo=sottotitolo,
        scala=layout.testo_scala(scala),
        origine=ORIGINE,
        note=tuple(note)[:3] + (f"Mesh di partenza: {sorgente}",),
    )


def _griglia(proiezioni: dict, prefisso: str, suffissi: dict[str, str],
             area=ZONA_VISTE, passo: float = 24.0) -> layout.Griglia:
    """Scala e centri delle tre viste, dalle dimensioni reali delle proiezioni."""
    misure = {
        slot: tavola.dimensioni_2d(proiezioni.get(f"{prefisso}_{suff}", {}))
        for slot, suff in suffissi.items()
    }
    return layout.griglia_primo_diedro(area, misure, passo=passo)


def _zona_iso(griglia: layout.Griglia, minimo: float = 58.0) -> tuple[float, ...]:
    """Colonna di sinistra rimasta libera dopo le viste: è lì che va l'assonometria.

    Ricavarla invece di fissarla è ciò che permette di dare alle viste tutta la
    larghezza che la scala richiede: lo spazio dell'assonometria è il resto, e il
    resto si conosce solo dopo.
    """
    destra = max(ZONA_ISO[0] + minimo, griglia.blocco[0] - 6.0)
    return (ZONA_ISO[0], ZONA_ISO[1], destra, ZONA_ISO[3])


#: Distanza dell'etichetta dal bordo basso della vista. Dove sotto c'è una quota
#: l'etichetta le sta sotto, altrimenti sale: due misure invece di una perché una
#: sola o sovrascrive il testo della quota o lascia un buco.
SOTTO_LIBERO, SOTTO_QUOTATO = 10.0, 30.0


def _vista(id_: str, etichetta: str, centro, scala: float,
           sotto: float = SOTTO_QUOTATO) -> tavola.Vista:
    return tavola.Vista(id=id_, etichetta=etichetta, centro=centro, scala=scala,
                        etichetta_sotto=sotto)


def _iso(proiezioni: dict, id_: str, area=ZONA_ISO,
         etichetta: str = "ASSONOMETRIA ISOMETRICA",
         massimo: float | None = None) -> tavola.Vista:
    """L'assonometria non supera mai la scala delle viste che accompagna.

    Un pittorico più grande delle viste quotate sposta l'occhio sulla vista che
    non porta numeri: si riempie lo spazio disponibile, ma non oltre.
    """
    scala, centro = tavola.ancora_iso(proiezioni.get(id_, {}), area, massimo=massimo)
    return tavola.Vista(id=id_, etichetta=f"{etichetta}  {layout.testo_scala(scala)}",
                        centro=centro, scala=scala, etichetta_sotto=SOTTO_LIBERO)


# -- foglio 1: assieme ------------------------------------------------------


def _foglio_assieme(recipe: dict, proiezioni: dict, sorgente: str) -> tavola.FoglioSpec:
    """Il modello intero: assonometria in evidenza e le tre viste d'ingombro.

    Le quote qui sono gli ingombri dell'assieme misurati sul solido costruito, non
    quote del registro: la nota lo dice, perché una tavola che non distingue le due
    cose è esattamente il problema che questo progetto esiste per non avere.
    """
    # Sul foglio d'assieme l'assonometria è il soggetto, non un corollario: prende
    # metà foglio, e le viste ortogonali si dispongono nell'altra metà.
    g = _griglia(proiezioni, "assieme",
                 {"pianta": "pianta", "prospetto": "prospetto", "laterale": "laterale"},
                 area=(214.0, 16.0, 408.0, 284.0))
    scala, centri = g.scala, g.centri
    viste = [
        _vista("assieme_prospetto", "PROSPETTO FRONTALE", centri["prospetto"], scala,
               sotto=SOTTO_LIBERO),
        _vista("assieme_laterale", "VISTA LATERALE DESTRA", centri["laterale"], scala,
               sotto=SOTTO_LIBERO),
        _vista("assieme_pianta", "PIANTA", centri["pianta"], scala),
        # Sul foglio d'assieme l'assonometria puo' superare la scala delle viste:
        # e' il soggetto del foglio, e le viste sono li' per riferimento.
        _iso(proiezioni, "assieme_iso", area=(14.0, 78.0, 208.0, 284.0),
             etichetta="ASSIEME - ASSONOMETRIA ISOMETRICA"),
    ]
    quote = []
    x0, y0, x1, y1 = tavola.bbox_2d(proiezioni.get("assieme_pianta", {}))
    if x1 > x0:
        quote.append(tavola.Quota("assieme_pianta", (x0, y0), (x1, y0), -22.0, _num(x1 - x0)))
        quote.append(tavola.Quota("assieme_pianta", (x1, y0), (x1, y1), 14.0, _num(y1 - y0),
                                  orizzontale=False))
    px0, pz0, px1, pz1 = tavola.bbox_2d(proiezioni.get("assieme_prospetto", {}))
    if pz1 > pz0:
        quote.append(tavola.Quota("assieme_prospetto", (px1, pz0), (px1, pz1), 14.0,
                                  _num(pz1 - pz0), orizzontale=False))
    return tavola.FoglioSpec(
        cartiglio=_cartiglio(
            "Assieme - viste ortogonali e assonometria", scala, sorgente,
            note=(f"{len(recipe['bodies'])} corpi ricostruiti dalla mesh.",
                  "Le quote di questo foglio sono l'ingombro dell'assieme misurato sul "
                  "solido costruito;",
                  "le quote del registro stanno sui fogli dei singoli corpi.")),
        viste=viste, quote=quote,
    )


# -- un foglio per corpo ----------------------------------------------------


def _foglio_corpo(body: dict, valori: dict[str, float], proiezioni: dict,
                  sorgente: str, contorni: dict) -> tavola.FoglioSpec:
    key = body["key"]
    g = _griglia(proiezioni, key,
                 {"pianta": "pianta", "prospetto": "prospetto", "laterale": "laterale"})
    scala, centri = g.scala, g.centri
    viste = [
        # Il prospetto non porta quote sotto: la sua etichetta può stare più alta,
        # e nello spazio guadagnato ci sta la lettera della traccia di sezione.
        _vista(f"{key}_prospetto", "PROSPETTO FRONTALE", centri["prospetto"], scala,
               sotto=SOTTO_LIBERO),
        _vista(f"{key}_laterale", "VISTA LATERALE DESTRA", centri["laterale"], scala),
        _vista(f"{key}_pianta", "PIANTA", centri["pianta"], scala),
        _iso(proiezioni, f"{key}_iso", area=_zona_iso(g), massimo=scala),
    ]
    ox, oy, oz = (float(v) for v in body["origin"])
    sx, sy, sz = (float(v) for v in body["size"])
    quote: list[tavola.Quota] = []

    def aggiungi(vista_id: str, dim_id: str, p1, p2, offset: float,
                 orizzontale: bool = True) -> None:
        """Una quota compare solo se il suo numero è nel registro. Nessuna eccezione."""
        if dim_id in valori:
            quote.append(tavola.Quota(vista_id, p1, p2, offset, _num(valori[dim_id]),
                                      orizzontale=orizzontale))

    aggiungi(f"{key}_pianta", f"{key}_ingombro_x", (ox, oy), (ox + sx, oy), -22.0)
    aggiungi(f"{key}_pianta", f"{key}_ingombro_y", (ox + sx, oy), (ox + sx, oy + sy), 14.0,
             orizzontale=False)
    aggiungi(f"{key}_prospetto", f"{key}_ingombro_x", (ox, oz + sz), (ox + sx, oz + sz), 10.0)
    aggiungi(f"{key}_prospetto", f"{key}_ingombro_z", (ox + sx, oz), (ox + sx, oz + sz), 14.0,
             orizzontale=False)
    aggiungi(f"{key}_laterale", f"{key}_ingombro_y", (oy, oz), (oy + sy, oz), -22.0)
    aggiungi(f"{key}_laterale", f"{key}_ingombro_z", (oy, oz), (oy, oz + sz), -14.0,
             orizzontale=False)

    richiami = list(_richiami_fori(key, body, valori))
    raggio = body.get("fillet")
    if raggio:
        richiami.append(tavola.Richiamo(
            f"{key}_pianta", (ox + float(raggio) * 0.3, oy + sy - float(raggio) * 0.3),
            (-16.0, 14.0), (f"raccordo verticale R{_num(float(raggio))}",
                            "su tutti e quattro gli spigoli")))

    tracce = []
    if _ha_interno(body):
        cx, cy, _ = _centro(body)
        tracce = [
            tavola.Traccia(f"{key}_pianta", (ox - 2.0, cy), (ox + sx + 2.0, cy), "A"),
            tavola.Traccia(f"{key}_pianta", (cx, oy - 2.0), (cx, oy + sy + 2.0), "B"),
        ]

    # Il profilo vero della mesh, sezionato a metà corpo, sovrapposto alle viste:
    # dove il prisma ricostruito e il pezzo divergono si vede qui, prima del
    # confronto numerico.
    sagome = [tavola.Sagoma(f"{key}_{nome}", tuple(tuple(p) for p in punti))
              for nome, punti in contorni.items() if punti]
    note = ["Ogni quota di questo foglio viene dal registro: misurata sulla mesh "
            "o approvata.",
            "Tratteggio fine = spigoli nascosti.  Linea mista rossa = tracce dei "
            "piani di sezione."]
    if sagome:
        note.append("Linea rossa a tratti = profilo della mesh sezionata a metà del corpo.")
    return tavola.FoglioSpec(
        cartiglio=_cartiglio(f"{body['name']} - viste ortogonali", scala, sorgente,
                             note=tuple(note)),
        viste=viste, quote=quote, richiami=richiami, tracce=tracce, sagome=sagome,
    )


def _richiami_fori(key: str, body: dict, valori: dict[str, float]):
    """Un richiamo per foro, sulla vista perpendicolare al suo asse."""
    vista_di_asse = {"Z": "pianta", "Y": "prospetto", "X": "laterale"}
    for i, bore in enumerate(body.get("bores", []), start=1):
        asse = bore.get("axis", "Z")
        vista = f"{key}_{vista_di_asse.get(asse, 'pianta')}"
        nome = vista_di_asse.get(asse, "pianta")
        punto = _punto_vista(nome, bore["center"])
        d_id, p_id = f"{key}_foro{i}_diametro", f"{key}_foro{i}_profondita"
        etichetta = []
        if d_id in valori:
            etichetta.append(u"foro %d  Ø%s" % (i, _num(valori[d_id])))
        elif f"{key}_asola{i}_larghezza" in valori:
            etichetta.append("asola %d  larghezza %s"
                             % (i, _num(valori[f"{key}_asola{i}_larghezza"])))
        else:
            continue
        if p_id in valori:
            etichetta.append(f"profondità {_num(valori[p_id])}  asse {asse}")
        else:
            etichetta.append(f"asse {asse}")
        yield tavola.Richiamo(vista, punto, (18.0, 16.0), tuple(etichetta))


# -- foglio delle sezioni ---------------------------------------------------


def _foglio_sezioni(body: dict, valori: dict[str, float], proiezioni: dict,
                    sorgente: str) -> tavola.FoglioSpec:
    key = body["key"]
    # Sul foglio delle sezioni non ci sono tracce da quotare fra una vista e
    # l'altra: il passo puo' stringersi, e quel che si guadagna va in scala.
    g = _griglia(proiezioni, key,
                 {"pianta": "sezC", "prospetto": "sezA", "laterale": "sezB"},
                 area=ZONA_SEZIONI, passo=18.0)
    scala, centri = g.scala, g.centri
    viste = [
        _vista(f"{key}_sezA", "SEZIONE A-A", centri["prospetto"], scala,
               sotto=SOTTO_LIBERO),
        _vista(f"{key}_sezB", "SEZIONE B-B", centri["laterale"], scala,
               sotto=SOTTO_LIBERO),
        _vista(f"{key}_sezC", "SEZIONE C-C", centri["pianta"], scala),
    ]
    ox, oy, oz = (float(v) for v in body["origin"])
    sx, sy, sz = (float(v) for v in body["size"])
    cavity = body.get("cavity") or {}
    pareti = cavity.get("walls", {})
    quote: list[tavola.Quota] = []

    def aggiungi(vista_id, dim_id, p1, p2, offset, orizzontale=True, fuori=None):
        if dim_id in valori:
            quote.append(tavola.Quota(vista_id, p1, p2, offset, _num(valori[dim_id]),
                                      orizzontale=orizzontale, fuori=fuori))

    # A-A: piano verticale longitudinale. Si leggono le pareti in X e il fondo.
    if "X-min" in pareti:
        aggiungi(f"{key}_sezA", f"{key}_parete_x_min",
                 (ox, oz + sz), (ox + float(pareti["X-min"]), oz + sz), 9.0, fuori=True)
    if "X-max" in pareti:
        aggiungi(f"{key}_sezA", f"{key}_parete_x_max",
                 (ox + sx - float(pareti["X-max"]), oz + sz), (ox + sx, oz + sz), 18.0,
                 fuori=True)
    if cavity:
        fondo = oz + float(cavity["floor"])
        aggiungi(f"{key}_sezA", f"{key}_fondo_spessore", (ox, oz), (ox, fondo), -14.0,
                 orizzontale=False, fuori=True)
        aggiungi(f"{key}_sezA", f"{key}_cavita_profondita",
                 (ox + sx, fondo), (ox + sx, fondo + float(cavity["depth"])), 14.0,
                 orizzontale=False)

    # B-B: piano verticale trasversale. Si leggono le pareti in Y e l'altezza.
    if "Y-min" in pareti:
        aggiungi(f"{key}_sezB", f"{key}_parete_y_min",
                 (oy, oz + sz), (oy + float(pareti["Y-min"]), oz + sz), 9.0, fuori=True)
    if "Y-max" in pareti:
        aggiungi(f"{key}_sezB", f"{key}_parete_y_max",
                 (oy + sy - float(pareti["Y-max"]), oz + sz), (oy + sy, oz + sz), 18.0,
                 fuori=True)
    aggiungi(f"{key}_sezB", f"{key}_ingombro_z", (oy + sy, oz), (oy + sy, oz + sz), 14.0,
             orizzontale=False)
    aggiungi(f"{key}_sezC", f"{key}_ingombro_x", (ox, oy), (ox + sx, oy), -22.0)

    piano_c = _quota_sezione_c(body)
    note = (
        f"A-A: piano verticale longitudinale Y = {_num(_centro(body)[1])}.",
        f"B-B: piano verticale trasversale X = {_num(_centro(body)[0])}.",
        f"C-C: piano orizzontale Z = {_num(piano_c)}."
        + ("  Passa sull'asse dei fori." if body.get("bores") else ""),
        "Campitura a 45° = materiale tagliato dal piano.",
    )
    return tavola.FoglioSpec(
        cartiglio=_cartiglio(f"{body['name']} - sezioni", scala, sorgente, note=note),
        viste=viste, quote=quote,
    )


# -- registro delle quote ---------------------------------------------------

INTESTAZIONI = (("quota", 3.0, "start"), ("misurato", 120.0, "end"),
                ("usato", 148.0, "end"), ("delta", 172.0, "end"),
                ("origine", 178.0, "start"))
RIGHE_PER_FOGLIO = 30


def _fogli_registro(registry: Registry, analysis: dict, sorgente: str, *,
                    decisioni: list[dict] | None = None,
                    scostamento: dict | None = None) -> list[tavola.FoglioSpec]:
    """La tabella che rende la tavola verificabile: ogni quota con la sua provenienza.

    È l'equivalente generico della «verifica contro la tavola TinkerCAD» del
    pezzo cablato: lì il confronto era con sei ingombri noti, qui con la mesh.
    """
    righe = []
    for dim in sorted(registry, key=lambda d: d.id):
        delta = dim.divergence
        stile = 'asse' if (delta is not None and abs(delta) > dim.tolerance) else 'contorno'
        righe.append((
            (f"{dim.id}", 'contorno'),
            ("—" if dim.measured is None else "%.3f" % dim.measured, 'contorno'),
            ("—" if dim.used is None else "%.3f" % dim.used, 'contorno'),
            ("—" if delta is None else "%+.3f" % delta, stile),
            ((dim.origin.value if dim.origin else "da risolvere"), stile),
        ))

    blocchi = [righe[i:i + RIGHE_PER_FOGLIO] for i in range(0, len(righe), RIGHE_PER_FOGLIO)] \
        or [[]]
    out = []
    for n, blocco in enumerate(blocchi, start=1):
        titolo = "REGISTRO DELLE QUOTE" + (f"  ({n}/{len(blocchi)})" if len(blocchi) > 1 else "")
        foglio = tavola.FoglioSpec(
            cartiglio=layout.Cartiglio(
                titolo="MODELLO RICOSTRUITO DALLA MESH",
                sottotitolo="Registro delle quote e provenienza",
                scala="—", origine=ORIGINE,
                note=("Ogni quota della tavola è qui, con il valore misurato sulla mesh e "
                      "quello usato nel modello.",
                      "Dove i due divergono la riga è in rosso e l'origine dice chi l'ha "
                      "approvato.",
                      f"Mesh di partenza: {sorgente}")),
            tabelle=[tavola.Tabella(x=20.0, y=282.0 - (13.0 + 5.0 * (len(blocco) + 1)),
                                    w=200.0, titolo=titolo,
                                    intestazioni=INTESTAZIONI,
                                    righe=tuple(blocco))],
        )
        if n == len(blocchi):
            foglio = replace(foglio, riquadri=_riquadri_finali(analysis, decisioni,
                                                               scostamento))
        out.append(foglio)
    return out


def _riquadri_finali(analysis: dict, decisioni: list[dict] | None,
                     scostamento: dict | None) -> list[tavola.Riquadro]:
    """Quel che la tavola non disegna, scritto invece di essere taciuto."""
    out = []
    non_ricostruibili = [f for f in analysis.get("features", []) if not f.get("buildable")]
    # Cinque volte «superficie libera» sullo stesso corpo sono una riga con un
    # numero davanti, non cinque righe: la tavola deve dire quante sono, non
    # ripetersi finché lo spazio finisce.
    conteggio: dict[str, int] = {}
    for f in non_ricostruibili:
        corpo = f["label"].split(":")[0]
        conteggio[f"{corpo} — {f['kind']} ({f['note']})"] = \
            conteggio.get(f"{corpo} — {f['kind']} ({f['note']})", 0) + 1
    righe = [(f"{n}×  {testo}" if n > 1 else testo) for testo, n in list(conteggio.items())[:8]]
    if len(conteggio) > 8:
        righe.append(f"... e altre {len(conteggio) - 8} voci.")
    if not righe:
        righe = ["Nessuna: il repertorio del ricostruttore copre tutta la mesh."]
    out.append(tavola.Riquadro(
        x=ZONA_TABELLA_X + 20.0, y=180.0, w=ZONA_TABELLA_W - 25.0, h=17.0 + 4.6 * len(righe),
        titolo="FEATURE NON RICOSTRUITE", righe=tuple(righe)))

    if decisioni:
        righe = [f"{d['id']}: {d.get('chosen') or 'non decisa'}" for d in decisioni[:8]]
        out.append(tavola.Riquadro(
            x=ZONA_TABELLA_X + 20.0, y=110.0, w=ZONA_TABELLA_W - 25.0,
            h=17.0 + 4.6 * len(righe),
            titolo="AMBIGUITÀ E DECISIONI APPLICATE", righe=tuple(righe)))

    if scostamento:
        righe = [f"{k}: {v:.4f} mm" for k, v in scostamento.items()]
        righe.append("Comprende le feature non ricostruite: è il costo dichiarato")
        righe.append("della semplificazione, non un errore nascosto.")
        out.append(tavola.Riquadro(
            x=ZONA_TABELLA_X + 20.0, y=30.0, w=ZONA_TABELLA_W - 25.0,
            h=17.0 + 4.6 * len(righe),
            titolo="SCOSTAMENTO MODELLO ↔ MESH", righe=tuple(righe)))
    return out
