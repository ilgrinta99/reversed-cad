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

import math
from dataclasses import replace
from typing import Any

from core.drafting import layout, patterns, tavola
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

#: Le feature che l'analisi riconosce ma che il repertorio del ricostruttore non
#: porta nel solido. Non sono un errore di lettura: sono superfici *misurate* che
#: il modello non rappresenta, e la tavola le disegna come impronta invece di
#: lasciare il foglio muto dove il pezzo ha qualcosa.
KIND_OMESSE = ("libera", "sfera", "cilindro", "arco")

#: Come si nomina, in una nota, ciascuna di quelle superfici.
NOME_OMESSA = {
    "libera": "superficie libera",
    "sfera": "calotta sferica",
    "cilindro": "cilindro obliquo",
    "arco": "arco parziale",
}

#: Sotto questa dimensione sul foglio l'impronta di una superficie omessa è più
#: piccola del tratto che la disegna: resta nell'elenco del registro, ma non sulle
#: viste, dove sarebbe una macchia e non un'informazione.
IMPRONTA_MINIMA_MM = 2.0

#: Quante impronte portano anche il richiamo con il nome. Oltre, il foglio diventa
#: illeggibile: le altre restano disegnate e numerate, e il registro le elenca tutte.
MAX_RICHIAMI_OMESSE = 5

#: Quanti richiami stanno in una colonna prima di ricominciare dall'alto. Sette
#: passi da 7 mm sono 49 mm: quanto basta a stare accanto a una vista di un A3.
MAX_RICHIAMI_IN_COLONNA = 7

#: Due posizioni più vicine di così sono la stessa posizione: serve a riconoscere
#: se un foro dell'analisi è *quel* foro della ricetta.
TOLLERANZA_POSIZIONE = 1e-3


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


def _cupole(body: dict) -> list[dict]:
    return list(body.get("caps", []))


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
    orizzontali = [b for b in body.get("bores", [])
                   if _asse_di_lettura(b)[0] in ("X", "Y")]
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


# ------------------------------------------------------ superfici non costruite


def omesse_del_corpo(analysis: dict, nome_corpo: str) -> list[dict]:
    """Le superfici che l'analisi ha misurato e il ricostruttore non porta.

    Ordinate per area decrescente: la prima è quella che pesa di più sullo
    scostamento, ed è quella che merita il richiamo se i richiami finiscono.
    """
    out = [f for f in analysis.get("features", [])
           if f.get("body") == nome_corpo and f.get("kind") in KIND_OMESSE]
    return sorted(out, key=lambda f: -float(f.get("params", {}).get("area", 0.0)))


def _riquadro_omessa(feature: dict) -> tuple[tuple[float, float, float],
                                             tuple[float, float, float]] | None:
    """Ingombro 3D di una superficie omessa: (origine, estremo opposto)."""
    p = feature.get("params", {})
    try:
        low = tuple(float(p[f"origine_{a}"]) for a in "xyz")
        size = tuple(float(p[f"d{a}"]) for a in "xyz")
    except (KeyError, TypeError, ValueError):
        return None
    return low, tuple(l + s for l, s in zip(low, size))


def _testo_omessa(indice: int, feature: dict) -> tuple[str, ...]:
    """Le righe del richiamo: che cos'è, quanto è grande, e che il modello non ce l'ha."""
    p = feature.get("params", {})
    nome = NOME_OMESSA.get(feature.get("kind"), feature.get("kind", "?"))
    misura = f"R{_num(float(p['raggio']))}" if p.get("raggio") is not None else \
        f"{_num(float(p.get('dx', 0.0)))}×{_num(float(p.get('dy', 0.0)))}×" \
        f"{_num(float(p.get('dz', 0.0)))}"
    return (f"{indice}  {nome}  {misura}", "nella mesh, non nel modello")


#: Quanto il testo di un richiamo sta fuori dal bordo della vista, e quanto due
#: richiami in colonna distano fra loro. Millimetri sul foglio, non sul modello.
MARGINE_RICHIAMO, PASSO_RICHIAMO = 13.0, 7.0


def _scostamento_richiamo(punto, box, scala: float, ordine: int,
                          destra: bool) -> tuple[float, float]:
    """Il testo va in colonna fuori dalla vista, non a distanza fissa dal punto.

    Due feature vicine di due millimetri, con lo stesso scostamento, danno due
    testi sovrapposti: a doversi spaziare è la posizione *sul foglio*, non la
    lunghezza della linea di richiamo. Qui la colonna parte dal bordo alto della
    vista e scende di un passo per ogni richiamo già uscito da quel lato.
    """
    x0, y0, x1, y1 = box
    bordo = (x1 if destra else x0) - punto[0]
    return (bordo * scala + (MARGINE_RICHIAMO if destra else -MARGINE_RICHIAMO),
            (y1 - punto[1]) * scala - PASSO_RICHIAMO * ordine)


def _incolonna(richiami: list[tavola.Richiamo], key: str, body: dict,
               scala: float) -> list[tavola.Richiamo]:
    """Ridispone i richiami di un foglio in colonne fuori dalle viste.

    Ogni richiamo nasce sapendo *cosa* dire e *dove* puntare, non dove scriversi:
    con uno scostamento fisso, due fori vicini producevano due testi uno sopra
    l'altro, e un foglio con sei feature era illeggibile. Qui si guarda il foglio
    intero: per ogni vista e per ogni lato, i testi scendono in colonna a passo
    costante, e la linea di richiamo si allunga fino al suo punto.

    La colonna è alta `PASSO_RICHIAMO` per richiamo: quando finisce lo spazio si
    riparte dall'alto, che è meglio di scrivere sotto il cartiglio.
    """
    origine = [float(v) for v in body["origin"]]
    estremo = [o + float(s) for o, s in zip(origine, body["size"])]
    per_lato: dict[tuple[str, bool], int] = {}
    fuori: list[tavola.Richiamo] = []
    for richiamo in richiami:
        nome = richiamo.vista[len(key) + 1:]
        if nome not in ASSI:
            fuori.append(richiamo)
            continue
        box = _punto_vista(nome, origine) + _punto_vista(nome, estremo)
        destra = richiamo.punto[0] >= (box[0] + box[2]) / 2.0
        ordine = per_lato.get((nome, destra), 0)
        per_lato[(nome, destra)] = ordine + 1
        fuori.append(replace(richiamo, scostamento=_scostamento_richiamo(
            richiamo.punto, box, scala, ordine % MAX_RICHIAMI_IN_COLONNA, destra)))
    return fuori


def _omesse_sulle_viste(key: str, body: dict, omesse: list[dict], scala: float
                        ) -> tuple[list[tavola.Sagoma], list[tavola.Richiamo]]:
    """Impronta di ogni superficie omessa sulle tre viste, e il richiamo che la nomina.

    L'impronta è il rettangolo d'ingombro della patch nella vista, non il suo
    contorno vero: il contorno vero di una superficie libera è la superficie
    stessa, e ridisegnarla equivarrebbe a dire che il modello la contiene. Il
    rettangolo dice l'unica cosa onesta — *qui c'è qualcosa che il solido non
    porta, e occupa tanto così*.
    """
    sagome: list[tavola.Sagoma] = []
    richiami: list[tavola.Richiamo] = []
    centro = _centro(body)
    origine = [float(v) for v in body["origin"]]
    estremo = [o + float(s) for o, s in zip(origine, body["size"])]
    # Quanti richiami sono già usciti da ogni lato di ogni vista: la colonna dei
    # testi si conta lì, o due viste lontane sprecherebbero le stesse altezze.
    per_lato: dict[tuple[str, bool], int] = {}
    quotati = 0
    for indice, feature in enumerate(omesse, start=1):
        riquadro = _riquadro_omessa(feature)
        if riquadro is None:
            continue
        low, high = riquadro
        disegnate = []
        for nome in DIREZIONI:
            (x0, y0), (x1, y1) = _punto_vista(nome, low), _punto_vista(nome, high)
            if max(x1 - x0, y1 - y0) * scala < IMPRONTA_MINIMA_MM:
                continue
            sagome.append(tavola.Sagoma(
                f"{key}_{nome}", ((x0, y0), (x1, y0), (x1, y1), (x0, y1)),
                stile='omesso'))
            # Il richiamo parte dall'angolo dell'impronta rivolto verso l'esterno
            # del corpo: la linea di richiamo non attraversa la feature che indica.
            cx, cy = _punto_vista(nome, centro)
            destra = (x0 + x1) / 2.0 >= cx
            angolo = (x1 if destra else x0, y1 if (y0 + y1) / 2.0 >= cy else y0)
            box = _punto_vista(nome, origine) + _punto_vista(nome, estremo)
            disegnate.append((nome, (x1 - x0) * (y1 - y0), angolo, box, destra))
        if not disegnate or quotati >= MAX_RICHIAMI_OMESSE:
            continue
        # Il richiamo va sulla vista dove l'impronta è più grande: è lì che si
        # capisce di che cosa si sta parlando.
        nome, _, angolo, box, destra = max(disegnate, key=lambda d: d[1])
        ordine = per_lato.get((nome, destra), 0)
        richiami.append(tavola.Richiamo(
            f"{key}_{nome}", angolo,
            _scostamento_richiamo(angolo, box, scala, ordine, destra),
            _testo_omessa(indice, feature)))
        per_lato[(nome, destra)] = ordine + 1
        quotati += 1
    return sagome, richiami


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
                                 contorni.get(body["key"], {}),
                                 omesse_del_corpo(analysis, body["name"])))
        if _ha_interno(body):
            out.append(_foglio_sezioni(body, valori, proiezioni, sorgente))
    out.extend(_fogli_registro(registry, analysis, sorgente,
                               decisioni=decisioni, scostamento=scostamento,
                               recipe=recipe))
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
                  sorgente: str, contorni: dict,
                  omesse: list[dict] | None = None) -> tavola.FoglioSpec:
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

    quote.extend(_quote_cupole(key, body, valori, scala))

    richiami = list(_richiami_fori(key, body, valori))
    for indice, cap in enumerate(_cupole(body), start=1):
        frontale = _VISTA_DI_ASSE[str(cap["axis"])]
        semi = [valori.get(f"{key}_cupola{indice}_semiasse_{a.lower()}")
                for a in "XYZ" if a != cap["axis"]]
        if any(v is None for v in semi):
            continue
        oi, oj = ASSI[frontale]
        centro = [float(v) for v in cap["centro"]]
        angolo = list(centro)
        angolo[oi] += semi[0] * 0.71
        angolo[oj] += semi[1] * 0.71
        richiami.append(tavola.Richiamo(
            f"{key}_{frontale}", _punto_vista(frontale, angolo), (18.0, 16.0),
            (f"cupola {indice}: paraboloide ellittico",
             f"asse {cap['axis']}, sporgenza {_num(float(cap['altezza']))}")))

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

    # Dove la mesh ha una superficie che il repertorio non costruisce, la vista
    # porta la sua impronta invece di restare muta: è l'unico posto in cui chi
    # legge la tavola può accorgersene guardando il pezzo, non una tabella.
    impronte, richiami_omesse = _omesse_sulle_viste(key, body, list(omesse or []), scala)
    sagome.extend(impronte)
    richiami.extend(richiami_omesse)

    # I richiami si dispongono solo adesso, quando il foglio li ha tutti: da soli
    # non sanno di essere in compagnia, e uno scostamento fisso li accatasta.
    richiami = _incolonna(richiami, key, body, scala)

    # La fascia note del cartiglio tiene tre righe più la mesh di partenza: le
    # legende si accorpano invece di spingersi fuori dal riquadro a vicenda.
    pattern = any("PCD" in riga or riga.startswith("passo")
                  for r in richiami for riga in r.righe)
    note = ["Quote dal registro (misurate o approvate); Ø PCD e passo dai centri "
            "dei fori misurati." if pattern else
            "Ogni quota di questo foglio viene dal registro: misurata sulla mesh "
            "o approvata.",
            "Tratteggio fine = spigoli nascosti.  Linea mista rossa = tracce dei "
            "piani di sezione."]
    legenda = []
    if contorni:
        legenda.append("Linea rossa a tratti = profilo della mesh")
    if impronte:
        legenda.append(f"Linea viola = ingombro di {len(omesse or [])} superfici "
                       f"misurate che il modello non porta")
    if legenda:
        note.append(".  ".join(legenda) + ".")
    return tavola.FoglioSpec(
        cartiglio=_cartiglio(f"{body['name']} - viste ortogonali", scala, sorgente,
                             note=tuple(note)),
        viste=viste, quote=quote, richiami=richiami, tracce=tracce, sagome=sagome,
    )


#: Vista su cui si legge un foro, dal suo asse: la perpendicolare all'asse.
_VISTA_DI_ASSE = {"Z": "pianta", "Y": "prospetto", "X": "laterale"}


def _fuori_dalla_vista(body: dict, nome: str, punto, orizzontale: bool,
                       scala: float, margine: float) -> float:
    """Scostamento che porta una linea di quota fuori dall'ingombro del corpo.

    Una quota tracciata *dentro* la vista attraversa gli spigoli che dovrebbe
    misurare. Quanto stia fuori dipende dalla scala, quindi non può essere un
    numero fisso nel codice: si calcola da dove finisce il corpo su quella vista.
    """
    origine = [float(v) for v in body["origin"]]
    estremo = [o + float(s) for o, s in zip(origine, body["size"])]
    x0, y0 = _punto_vista(nome, origine)
    x1, y1 = _punto_vista(nome, estremo)
    if orizzontale:
        return (y0 - punto[1]) * scala - margine
    return (x1 - punto[0]) * scala + margine


def _quote_cupole(key: str, body: dict, valori: dict[str, float], scala: float):
    """Le quote di ogni cupola: i due assi del bordo dove si vede l'ellisse, e
    l'altezza su una vista che la guarda di taglio.

    Una cupola vista lungo il proprio asse è un'ellisse e si quota come tale; vista
    di lato è un profilo alto quanto la sporgenza. Servono tutte e due: dalla sola
    ellisse non si sa quanto sporge, dalla sola sporgenza non si sa quanto è larga.
    """
    for indice, cap in enumerate(_cupole(body), start=1):
        asse = str(cap["axis"])
        k = "XYZ".index(asse)
        i, j = [q for q in range(3) if q != k]
        centro = [float(v) for v in cap["centro"]]
        semi = {a: valori.get(f"{key}_cupola{indice}_semiasse_{a.lower()}")
                for a in "XYZ"}
        altezza = valori.get(f"{key}_cupola{indice}_altezza")

        # Vista in cui l'asse esce dal foglio: lì il bordo è l'ellisse vera.
        frontale = _VISTA_DI_ASSE[asse]
        oi, oj = ASSI[frontale]
        for indice_asse, margine, orizzontale in ((oi, 30.0, True), (oj, 22.0, False)):
            mezzo = semi["XYZ"[indice_asse]]
            if mezzo is None:
                continue
            p1 = list(centro)
            p2 = list(centro)
            p1[indice_asse] = centro[indice_asse] - mezzo
            p2[indice_asse] = centro[indice_asse] + mezzo
            a, b = _punto_vista(frontale, p1), _punto_vista(frontale, p2)
            yield tavola.Quota(
                f"{key}_{frontale}", a, b,
                _fuori_dalla_vista(body, frontale, a, orizzontale, scala, margine),
                _num(2.0 * mezzo), orizzontale=orizzontale)

        # Vista di taglio: una qualsiasi in cui l'asse della cupola giace nel
        # foglio. Lì si quota la sporgenza, che è l'unica cosa che non si vede
        # nell'ellisse.
        if altezza is None:
            continue
        laterale = _VISTA_DI_ASSE["XYZ"[i]]
        verso = 1.0 if float(cap.get("verso", 1)) >= 0 else -1.0
        base = list(centro)
        apice = list(centro)
        apice[k] = centro[k] - verso * altezza
        assi_vista = ASSI[laterale]
        orizzontale = assi_vista[1] != k
        a, b = _punto_vista(laterale, apice), _punto_vista(laterale, base)
        yield tavola.Quota(
            f"{key}_{laterale}", a, b,
            _fuori_dalla_vista(body, laterale, a, orizzontale, scala, 14.0),
            _num(altezza), orizzontale=orizzontale)


def _richiami_fori(key: str, body: dict, valori: dict[str, float]):
    """Richiami dei fori, con i pattern collassati in un richiamo solo.

    Fori uguali che formano un cerchio (bolt circle) o una fila a passo costante
    si quotano una volta — «N× Ød su Ø(pcd) PCD», «N× Ød passo p» — invece di
    ripetere lo stesso richiamo N volte. Diametro e profondità restano quelli del
    registro; PCD e passo sono ricavati dai centri misurati e dichiarati come tali
    nella nota del foglio (`_foglio_corpo`). Quando non c'è pattern, ogni foro
    torna al suo richiamo, identico a prima: una tavola senza pattern non cambia.
    """
    records = _record_fori(key, body, valori)
    consumati: set[int] = set()

    # I pattern si cercano fra fori cilindrici (con diametro) e sulla stessa vista,
    # cioè con lo stesso asse: fori su assi diversi stanno su viste diverse.
    for asse in ("Z", "Y", "X"):
        # Un foro inclinato non entra in un pattern: «4× Ø3» prometterebbe
        # quattro fori uguali, e uno inclinato non è uguale agli altri.
        candidati = [r for r in records
                     if r["asse"] == asse and r["d"] is not None and not r["inclinato"]]
        if len(candidati) < 3:
            continue
        fori2d = [patterns.Foro2D(r["punto"][0], r["punto"][1], r["d"] / 2.0, ref=r)
                  for r in candidati]
        for pat in patterns.raggruppa_fori(fori2d):
            if pat.kind == "sparso":
                continue
            recs = [f.ref for f in pat.fori]
            if not _profondita_uniforme(recs):
                continue  # profondità diverse: non è un foro solo ripetuto
            yield _richiamo_pattern(pat, recs)
            consumati.update(id(r) for r in recs)

    # Tutto il resto, foro per foro, nell'ordine originale.
    for r in records:
        if id(r) in consumati:
            continue
        richiamo = _richiamo_singolo(r)
        if richiamo is not None:
            yield richiamo


def _asse_di_lettura(bore: dict) -> tuple[str, str]:
    """Su quale asse si legge un foro, e come si chiama nel richiamo.

    Un foro inclinato si legge sulla vista dell'asse a cui somiglia di più — è lì
    che il suo contorno si riconosce — ma il richiamo dice l'inclinazione vera,
    altrimenti la tavola prometterebbe un foro perpendicolare che non c'è.
    """
    direzione = bore.get("direction")
    if not direzione:
        asse = bore.get("axis") or "Z"
        return asse, asse
    vicino = max(range(3), key=lambda k: abs(float(direzione[k])))
    gradi = math.degrees(math.acos(min(1.0, abs(float(direzione[vicino])))))
    nome = "XYZ"[vicino]
    return nome, f"{nome} inclinato {gradi:.1f}°"


def _record_fori(key: str, body: dict, valori: dict[str, float]) -> list[dict]:
    """Un dizionario per foro con quel che serve a quotarlo: vista, punto, valori."""
    records = []
    for i, bore in enumerate(body.get("bores", []), start=1):
        asse, etichetta = _asse_di_lettura(bore)
        nome = _VISTA_DI_ASSE.get(asse, "pianta")
        records.append({
            "i": i, "asse": asse, "etichetta_asse": etichetta,
            "inclinato": bool(bore.get("direction")),
            "vista": f"{key}_{nome}",
            "punto": _punto_vista(nome, bore["center"]),
            "d": valori.get(f"{key}_foro{i}_diametro"),
            "w": valori.get(f"{key}_asola{i}_larghezza"),
            "p": valori.get(f"{key}_foro{i}_profondita"),
        })
    return records


def _profondita_uniforme(recs: list[dict]) -> bool:
    """I fori del pattern hanno la stessa profondità (o tutti nessuna misura)."""
    def chiave(r):
        return None if r["p"] is None else round(float(r["p"]), 3)
    return len({chiave(r) for r in recs}) == 1


def _riga_profondita(r: dict) -> str:
    return (f"profondità {_num(r['p'])}  asse {r['etichetta_asse']}"
            if r["p"] is not None else f"asse {r['etichetta_asse']}")


def _richiamo_singolo(r: dict) -> tavola.Richiamo | None:
    """Il richiamo di un singolo foro (o asola). Testo identico alla versione storica."""
    etichetta = []
    if r["d"] is not None:
        etichetta.append(u"foro %d  Ø%s" % (r["i"], _num(r["d"])))
    elif r["w"] is not None:
        etichetta.append("asola %d  larghezza %s" % (r["i"], _num(r["w"])))
    else:
        return None
    etichetta.append(_riga_profondita(r))
    return tavola.Richiamo(r["vista"], r["punto"], (18.0, 16.0), tuple(etichetta))


def _richiamo_pattern(pat: patterns.Pattern, recs: list[dict]) -> tavola.Richiamo:
    """Il richiamo che quota un intero pattern su un foro rappresentativo."""
    r0 = recs[0]
    diametro = _num(r0["d"])
    if pat.kind == "bolt_circle":
        testa = "%d× foro Ø%s" % (pat.conteggio, diametro)
        mezzo = "equidistanti su Ø%s PCD" % _num(pat.pcd)
    else:  # passo
        testa = "%d× foro Ø%s" % (pat.conteggio, diametro)
        mezzo = "passo %s" % _num(pat.passo)
    return tavola.Richiamo(r0["vista"], r0["punto"], (18.0, 16.0),
                           (testa, mezzo, _riga_profondita(r0)))


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
                    scostamento: dict | None = None,
                    recipe: dict | None = None) -> list[tavola.FoglioSpec]:
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
                                                               scostamento, recipe))
        out.append(foglio)
    return out


def _nel_modello(feature: dict, recipe: dict | None) -> bool:
    """Il solido costruito porta davvero questa feature?

    `buildable` dice se il repertorio *saprebbe* costruirla; non dice se è stata
    costruita. Un'asola con la decisione «asole = fori» finisce nella ricetta pur
    restando `buildable=False`, e un corpo escluso dalla decisione «corpi =
    principale» non c'è pur essendo un prisma. Elencare fra le omesse una feature
    che il solido contiene è la stessa bugia di tacerne una che non contiene, al
    contrario: qui si guarda la ricetta.
    """
    if recipe is None:
        return bool(feature.get("buildable"))
    corpo = next((b for b in recipe.get("bodies", [])
                  if b.get("name") == feature.get("body")), None)
    if corpo is None:
        return False                       # il corpo non è nel modello: niente lo è
    kind = feature.get("kind")
    if kind in ("prisma", "cavita"):
        return kind != "cavita" or bool(corpo.get("cavity"))
    if kind not in ("foro", "asola", "cupola"):
        return False                       # libera, sfera, cilindro, arco
    p = feature.get("params", {})
    try:
        centro = [float(p[f"centro_{a}"]) for a in "xyz"]
    except (KeyError, TypeError, ValueError):
        return False
    posti = ([c.get("centro", ()) for c in corpo.get("caps", [])] if kind == "cupola"
             else [b.get("center", ()) for b in corpo.get("bores", [])])
    return any(
        all(abs(c - float(d)) <= TOLLERANZA_POSIZIONE for c, d in zip(centro, posto))
        for posto in posti if len(posto) == 3
    )


def _riga_omessa(feature: dict, con_posizione: bool = True) -> str:
    """Una voce dell'elenco: che cos'è, quanto è grande, e — se è sola — dove sta."""
    p = feature.get("params", {})
    nome = NOME_OMESSA.get(feature.get("kind"), feature.get("kind", "?"))
    if all(f"d{a}" in p for a in "xyz"):
        ingombro = "  " + "×".join(_num(float(p[f"d{a}"])) for a in "xyz") + " mm"
    elif feature.get("kind") == "asola" and "larghezza" in p:
        ingombro = f"  larghezza {_num(float(p['larghezza']))}"
    elif "diametro" in p:
        ingombro = f"  Ø{_num(float(p['diametro']))}"
    else:
        ingombro = ""
    if con_posizione and all(f"centro_{a}" in p for a in "xyz"):
        centro = "  in (" + ", ".join(_num(float(p[f"centro_{a}"])) for a in "xyz") + ")"
    else:
        centro = ""
    return f"{nome}{ingombro}{centro}"


def _riquadri_finali(analysis: dict, decisioni: list[dict] | None,
                     scostamento: dict | None,
                     recipe: dict | None = None) -> list[tavola.Riquadro]:
    """Quel che la tavola non disegna, scritto invece di essere taciuto."""
    out = []
    omesse = [f for f in analysis.get("features", []) if not _nel_modello(f, recipe)]
    # Un censimento, non un elenco: venti voci non ci stanno, e troncarle
    # lascerebbe fuori proprio quelle piccole. Per ogni corpo e per ogni tipo di
    # superficie: quante sono e qual è la maggiore. *Dove* stanno lo dicono le
    # impronte sulle viste, che le portano tutte.
    gruppi: dict[tuple[str, str], list[dict]] = {}
    for f in omesse:
        gruppi.setdefault((f["label"].split(":")[0], f.get("kind", "?")), []).append(f)
    ordinati = sorted(gruppi.items(),
                      key=lambda item: -sum(float(f.get("params", {}).get("area", 0.0))
                                            for f in item[1]))
    righe = []
    for (corpo, _kind), gruppo in ordinati[:8]:
        maggiore = max(gruppo, key=lambda f: float(f.get("params", {}).get("area", 0.0)))
        molte = len(gruppo) > 1
        prefisso = f"{len(gruppo)}×  " if molte else ""
        coda = "  (la maggiore)" if molte else ""
        righe.append(f"{corpo} — {prefisso}{_riga_omessa(maggiore, not molte)}{coda}")
    if len(ordinati) > 8:
        righe.append(f"... e altri {len(ordinati) - 8} gruppi: tutti hanno "
                     f"l'impronta in viola sulle viste del corpo.")
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
