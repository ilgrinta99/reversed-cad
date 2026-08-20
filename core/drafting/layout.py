# -*- coding: utf-8 -*-
"""Impaginazione del foglio: cornice, cartiglio, etichette, tracce di sezione.

Tutto quello che sta *intorno* al disegno. Nessun numero di pezzo: i testi
arrivano da chi compone la tavola.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple

from core.drafting.sheet import Foglio

#: Margine della cornice dal bordo del foglio, in mm.
MARGINE = 10.0

#: Assonometria isometrica standard, come coppia (u = destra sul foglio, w = alto):
#: osservatore in (1, -1, 1), Z del modello in alto, X verso destra-basso, Y verso
#: destra-alto. Sta qui e non in `hlr.py` perché serve anche a chi compone la
#: tavola, che non può importare FreeCAD.
ISOMETRICA = ((1.0, 1.0, 0.0), (-1.0, 1.0, 2.0))

#: Cartiglio: larghezza e altezze delle tre fasce (note, dati, titolo).
CARTIGLIO_W = 170.0
H_NOTE, H_DATI, H_TITOLO = 14.0, 33.0, 12.0
CARTIGLIO_H = H_NOTE + H_DATI + H_TITOLO


@dataclass(frozen=True)
class Cartiglio:
    """I campi del riquadro delle iscrizioni (ISO 7200, ridotto all'essenziale)."""

    titolo: str
    sottotitolo: str
    scala: str = "1:1"
    origine: str = "modello parametrico FreeCAD"
    proiezione: str = "europea (1o diedro)"
    formato: str = "A3   420 x 297"
    note: tuple[str, ...] = field(default_factory=tuple)


def cornice_e_cartiglio(f: Foglio, c: Cartiglio, foglio_n: int, foglio_tot: int) -> None:
    """Cornice del foglio e riquadro delle iscrizioni in basso a sinistra."""
    m = MARGINE
    f.polilinea([(m, m), (f.w - m, m), (f.w - m, f.h - m), (m, f.h - m)], 'cornice', chiusa=True)
    x0, y0, cw, ch = m + 5.0, m + 5.0, CARTIGLIO_W, CARTIGLIO_H
    f.polilinea([(x0, y0), (x0 + cw, y0), (x0 + cw, y0 + ch), (x0, y0 + ch)],
                'cornice', chiusa=True)
    f.linea(x0, y0 + H_NOTE, x0 + cw, y0 + H_NOTE, 'sottile')
    f.linea(x0, y0 + H_NOTE + H_DATI, x0 + cw, y0 + H_NOTE + H_DATI, 'sottile')
    for i in (1, 2):
        f.linea(x0, y0 + H_NOTE + 11.0 * i, x0 + cw, y0 + H_NOTE + 11.0 * i, 'sottile')
    f.linea(x0 + 100.0, y0 + H_NOTE, x0 + 100.0, y0 + H_NOTE + H_DATI, 'sottile')

    f.testo(x0 + 3, y0 + ch - 8.0, c.titolo, 4.5, st='contorno', grassetto=True)
    sx = [('OGGETTO', c.sottotitolo), ('SCALA', '%s     UNITA: mm' % c.scala),
          ('PROIEZIONE', c.proiezione)]
    dx = [('FOGLIO', '%d di %d' % (foglio_n, foglio_tot)),
          ('FORMATO', c.formato), ('ORIGINE', c.origine)]
    for col, xx in ((sx, x0 + 3), (dx, x0 + 103)):
        for i, (k, v) in enumerate(col):
            yy = y0 + H_NOTE + H_DATI - 11.0 * i
            f.testo(xx, yy - 4.0, k, 2.0, st='contorno')
            f.testo(xx, yy - 8.5, v, 2.8, st='contorno')
    # Quattro righe e non una di piu': la fascia e' alta H_NOTE e il testo che
    # non ci sta non va scritto sopra il bordo, va tolto da chi compone.
    for i, t in enumerate(c.note[:4]):
        f.testo(x0 + 3, y0 + H_NOTE - 3.8 - 3.0 * i, t, 2.2, st='contorno')

    simbolo_primo_diedro(f, f.w - m - 34.0, m + 8.0)


def simbolo_primo_diedro(f: Foglio, x: float, y: float) -> None:
    """Il tronco di cono con le due circonferenze: proiezione europea."""
    f.cerchio(x, y, 4.0, 'sottile')
    f.cerchio(x, y, 2.4, 'sottile')
    f.polilinea([(x + 9, y - 4), (x + 22, y - 2.4), (x + 22, y + 2.4), (x + 9, y + 4)],
                'sottile', chiusa=True)


def etichetta(f: Foglio, x: float, y: float, testo: str) -> None:
    """Titolo di una vista, centrato sotto la vista stessa."""
    f.testo(x, y, testo, 3.4, anc='middle', st='contorno', grassetto=True)


def linea_di_sezione(f: Foglio, x1: float, y1: float, x2: float, y2: float,
                     lettera: str, verso: int = 1) -> None:
    """Traccia del piano di sezione, con frecce di osservazione e lettere."""
    f.linea(x1, y1, x2, y2, 'asse')
    for (px, py) in ((x1, y1), (x2, y2)):
        if abs(x2 - x1) < 1e-6:                       # traccia verticale
            f._freccia((px + 4.0 * verso, py), (-verso, 0))
            f.testo(px + 4.0 * verso, py + (5 if py == max(y1, y2) else -8), lettera,
                    3.4, anc='middle', st='asse', grassetto=True)
        else:
            f._freccia((px, py + 4.0 * verso), (0, -verso))
            f.testo(px + (5 if px == max(x1, x2) else -5), py + 4.5 * verso, lettera,
                    3.4, anc='middle', st='asse', grassetto=True)


#: Scale normalizzate ISO 5455, dalla piu' grande alla piu' piccola.
SCALE_NORMALIZZATE = (50.0, 20.0, 10.0, 5.0, 2.0, 1.0,
                      0.5, 0.2, 0.1, 0.05, 0.02, 0.01)


def scala_normalizzata(larghezza: float, altezza: float,
                       box_w: float, box_h: float) -> float:
    """La scala ISO piu' grande con cui l'ingombro entra nel riquadro.

    Le scale arbitrarie sono la firma di un disegno generato male: si sceglie fra
    quelle normalizzate, e se nemmeno la piu' piccola basta si restituisce quella
    (il disegno sara' stretto, ma la scala dichiarata resta vera).
    """
    if larghezza <= 0 or altezza <= 0:
        return 1.0
    for s in SCALE_NORMALIZZATE:
        if larghezza * s <= box_w and altezza * s <= box_h:
            return s
    return SCALE_NORMALIZZATE[-1]


def testo_scala(s: float) -> str:
    """'2:1', '1:1', '1:2' — mai '0.5:1'."""
    if s >= 1.0:
        return '%g:1' % s
    inv = 1.0 / s
    return '1:%g' % (round(inv) if abs(inv - round(inv)) < 1e-6 else round(inv, 2))


class Griglia(NamedTuple):
    """Esito della disposizione: scala, centri delle viste, rettangolo occupato.

    Il rettangolo serve a chi impagina il resto del foglio — l'assonometria va
    nello spazio che le viste non hanno usato, e quello spazio si conosce solo
    dopo aver scelto la scala.
    """

    scala: float
    centri: dict[str, tuple[float, float]]
    blocco: tuple[float, float, float, float]


def griglia_primo_diedro(area: tuple[float, float, float, float],
                         bbox: dict[str, tuple[float, float]],
                         passo: float = 24.0,
                         bordo: float = 18.0) -> Griglia:
    """Dispone prospetto, laterale e pianta secondo il primo diedro.

    `bbox` = ingombro 2D (larghezza, altezza) di ciascuna vista in mm di modello;
    `passo` = spazio fra due viste, in mm di carta, dove stanno quote ed etichette;
    `bordo` = fascia interna all'area riservata alle quote esterne.

    Nel primo diedro la vista da destra si disegna a sinistra del prospetto e la
    pianta sotto: prospetto e pianta restano allineati sulla verticale, prospetto
    e laterale sull'orizzontale, perche' ogni vista e' centrata sul proprio
    ingombro e i due ingombri condividono l'asse.

    Ritorna la scala normalizzata scelta e il centro sul foglio di ogni vista.
    """
    x0, y0, x1, y1 = area
    x0 += bordo; y0 += bordo; x1 -= bordo; y1 -= bordo
    lp, hp = bbox.get('prospetto', (0.0, 0.0))
    ll, hl = bbox.get('laterale', (0.0, 0.0))
    lpi, hpi = bbox.get('pianta', (0.0, 0.0))
    h_alto = max(hp, hl)

    # La colonna di destra e' larga quanto la piu' larga fra prospetto e pianta:
    # le due condividono l'asse X del modello e restano incolonnate.
    l_destra = max(lp, lpi)
    scala = scala_normalizzata(ll + l_destra, h_alto + hpi,
                               (x1 - x0) - passo, (y1 - y0) - passo)

    # Il blocco delle tre viste si centra nell'area invece di appoggiarsi a un
    # angolo: appoggiato lascia un vuoto grande quanto lo scarto di scala, ed e'
    # il vuoto che fa sembrare una tavola generata a caso.
    blocco_w = (ll + l_destra) * scala + passo
    blocco_h = (h_alto + hpi) * scala + passo
    sinistra = x0 + ((x1 - x0) - blocco_w) / 2.0
    alto = y1 - ((y1 - y0) - blocco_h) / 2.0

    cx_sinistra = sinistra + ll * scala / 2.0
    cx_destra = sinistra + (ll + l_destra / 2.0) * scala + passo
    cy_alto = alto - h_alto * scala / 2.0
    cy_basso = cy_alto - (h_alto / 2.0 + hpi / 2.0) * scala - passo
    return Griglia(
        scala,
        {'prospetto': (cx_destra, cy_alto),
         'pianta': (cx_destra, cy_basso),
         'laterale': (cx_sinistra, cy_alto)},
        (sinistra, alto - blocco_h, sinistra + blocco_w, alto),
    )
