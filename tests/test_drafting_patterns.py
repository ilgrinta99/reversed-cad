# -*- coding: utf-8 -*-
"""Riconoscimento dei pattern di fori e loro resa in richiami sulla tavola.

Due livelli: la geometria pura (`core.drafting.patterns`) e il suo aggancio al
compositore automatico (`parts.auto.drawing`). Il vincolo che i test difendono è
duplice: i pattern *veri* si collassano in un richiamo solo, e una tavola *senza*
pattern non cambia di una virgola rispetto al richiamo-per-foro storico.
"""

from __future__ import annotations

import math

import pytest

from core.drafting import patterns
from parts.auto import drawing


# ---------------------------------------------------------------- geometria pura


def _cerchio(n: int, raggio: float, r_foro: float, centro=(0.0, 0.0)) -> list[patterns.Foro2D]:
    cx, cy = centro
    return [
        patterns.Foro2D(cx + raggio * math.cos(2 * math.pi * k / n),
                        cy + raggio * math.sin(2 * math.pi * k / n),
                        r_foro, ref=k)
        for k in range(n)
    ]


def test_cerchio_di_fori_riconosciuto():
    pats = patterns.raggruppa_fori(_cerchio(6, 10.0, 1.5))
    assert len(pats) == 1
    p = pats[0]
    assert p.kind == "bolt_circle"
    assert p.conteggio == 6
    assert p.pcd == pytest.approx(20.0, abs=1e-6)
    assert p.centro[0] == pytest.approx(0.0, abs=1e-6)


def test_quattro_fori_equispaziati_sono_un_cerchio():
    fori = [patterns.Foro2D(10, 0, 1), patterns.Foro2D(0, 10, 1),
            patterns.Foro2D(-10, 0, 1), patterns.Foro2D(0, -10, 1)]
    p = patterns.raggruppa_fori(fori)[0]
    assert p.kind == "bolt_circle"
    assert p.pcd == pytest.approx(20.0)


def test_cerchio_decentrato_usa_il_baricentro():
    p = patterns.raggruppa_fori(_cerchio(5, 7.0, 1.0, centro=(30.0, -12.0)))[0]
    assert p.kind == "bolt_circle"
    assert p.centro == pytest.approx((30.0, -12.0))


def test_passo_lineare_riconosciuto():
    fori = [patterns.Foro2D(x, 5.0, 1.0) for x in (0.0, 10.0, 20.0, 30.0)]
    p = patterns.raggruppa_fori(fori)[0]
    assert p.kind == "passo"
    assert p.conteggio == 4
    assert p.passo == pytest.approx(10.0)


def test_passo_obliquo_riconosciuto():
    # Tre fori su una diagonale, passo costante: la direzione non è un asse.
    fori = [patterns.Foro2D(t * 3.0, t * 4.0, 1.0) for t in (0, 1, 2)]
    p = patterns.raggruppa_fori(fori)[0]
    assert p.kind == "passo"
    assert p.passo == pytest.approx(5.0)  # ipotenusa 3-4-5


def test_passo_non_uniforme_e_sparso():
    fori = [patterns.Foro2D(x, 0.0, 1.0) for x in (0.0, 10.0, 25.0)]
    p = patterns.raggruppa_fori(fori)[0]
    assert p.kind == "sparso"


def test_raggi_diversi_in_gruppi_separati():
    grandi = _cerchio(4, 10.0, 2.0)
    piccoli = [patterns.Foro2D(x, 20.0, 0.5) for x in (0.0, 5.0, 10.0)]
    pats = patterns.raggruppa_fori(grandi + piccoli)
    tipi = sorted(p.kind for p in pats)
    assert tipi == ["bolt_circle", "passo"]


def test_due_fori_sono_sparsi():
    pats = patterns.raggruppa_fori([patterns.Foro2D(0, 0, 1), patterns.Foro2D(10, 0, 1)])
    assert pats[0].kind == "sparso"
    assert pats[0].conteggio == 2


def test_ref_conservato_e_ordine_stabile_negli_sparsi():
    fori = [patterns.Foro2D(0, 0, 1, ref="a"), patterns.Foro2D(1, 7, 1, ref="b")]
    p = patterns.raggruppa_fori(fori)[0]
    assert [f.ref for f in p.fori] == ["a", "b"]


# ---------------------------------------------------------------- aggancio al disegno


def _body_con_fori(centri, diametro=3.0, profondita=5.0, asse="Z", key="c1"):
    """Un corpo sintetico con N fori uguali, e il registro delle loro quote."""
    bores = [{"axis": asse, "diameter": diametro, "depth": profondita,
              "center": [x, y, z]} for (x, y, z) in centri]
    valori = {}
    for i in range(1, len(centri) + 1):
        valori[f"{key}_foro{i}_diametro"] = diametro
        valori[f"{key}_foro{i}_profondita"] = profondita
    return {"key": key, "origin": [0, 0, 0], "size": [40, 40, 10], "bores": bores}, valori


def test_bolt_circle_collassa_in_un_richiamo():
    centri = [(20 + 10 * math.cos(2 * math.pi * k / 6),
               20 + 10 * math.sin(2 * math.pi * k / 6), 0) for k in range(6)]
    body, valori = _body_con_fori(centri)
    richiami = list(drawing._richiami_fori("c1", body, valori))
    assert len(richiami) == 1
    testo = " / ".join(richiami[0].righe)
    assert "6×" in testo and "PCD" in testo
    assert "Ø3.00" in testo


def test_passo_collassa_in_un_richiamo():
    centri = [(x, 20.0, 0.0) for x in (5.0, 15.0, 25.0, 35.0)]
    body, valori = _body_con_fori(centri)
    richiami = list(drawing._richiami_fori("c1", body, valori))
    assert len(richiami) == 1
    testo = " / ".join(richiami[0].righe)
    assert "4×" in testo and "passo 10.00" in testo


def test_pochi_fori_restano_uno_per_uno():
    body, valori = _body_con_fori([(5, 5, 0), (30, 30, 0)])
    richiami = list(drawing._richiami_fori("c1", body, valori))
    assert len(richiami) == 2
    # Testo identico alla resa storica del singolo foro.
    assert richiami[0].righe == ("foro 1  Ø3.00", "profondità 5.00  asse Z")


def test_profondita_diversa_non_collassa():
    centri = [(20 + 10 * math.cos(2 * math.pi * k / 6),
               20 + 10 * math.sin(2 * math.pi * k / 6), 0) for k in range(6)]
    body, valori = _body_con_fori(centri)
    valori["c1_foro3_profondita"] = 9.0  # un foro più profondo: non è lo stesso foro
    richiami = list(drawing._richiami_fori("c1", body, valori))
    assert len(richiami) == 6  # nessun collasso


def test_asola_resta_richiamo_singolo():
    body = {"key": "c1", "origin": [0, 0, 0], "size": [40, 40, 10],
            "bores": [{"axis": "Z", "diameter": 0, "depth": 4, "center": [10, 10, 0]}]}
    valori = {"c1_asola1_larghezza": 6.0, "c1_foro1_profondita": 4.0}
    richiami = list(drawing._richiami_fori("c1", body, valori))
    assert len(richiami) == 1
    assert richiami[0].righe[0].startswith("asola 1  larghezza 6.00")


def test_un_apertura_ha_il_suo_richiamo():
    """Un'apertura non è un foro senza diametro: si quota con i suoi due lati."""
    body = {"key": "c1", "origin": [0, 0, 0], "size": [40, 25, 10],
            "bores": [{"kind": "finestra", "dim": "c1_finestra1", "axis": "Y",
                       "rect": [10, -0.5, 2, 20, 2.5, 6], "depth": 3.0,
                       "center": [15.0, 1.0, 4.0],
                       "misure": {"larghezza_x": 10.0, "larghezza_z": 4.0}}]}
    valori = {"c1_finestra1_larghezza_x": 10.0, "c1_finestra1_larghezza_z": 4.0,
              "c1_finestra1_profondita": 3.0}
    richiami = list(drawing._richiami_fori("c1", body, valori))
    assert len(richiami) == 1
    assert richiami[0].righe[0] == "apertura 1  10.00 × 4.00"
    assert "profondità 3.00" in richiami[0].righe[1]
    assert richiami[0].vista == "c1_prospetto"
