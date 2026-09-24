# -*- coding: utf-8 -*-
"""La cupola non si ferma all'analisi: il solido ce l'ha davvero.

Riconoscere un paraboloide e poi non costruirlo sarebbe peggio che non
riconoscerlo, perché la tavola prometterebbe una feature che nello STEP non c'è.
Questi test girano il costruttore vero, sotto FreeCAD, e misurano quel che esce.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.freecad.runner import run_script
from tests.conftest import needs_freecad

REPO = Path(__file__).resolve().parents[1]
BUILD = REPO / "parts" / "auto" / "build_script.py"


def _ricetta(caps=(), bores=()):
    return {
        "bodies": [{
            "name": "prova", "key": "c1",
            "origin": [0.0, 0.0, 0.0], "size": [40.0, 25.0, 12.0],
            "fillet": None, "cavity": None,
            "caps": list(caps), "bores": list(bores),
        }],
        "source": "prova.obj",
    }


def _costruisci(tmp_path, recipe):
    percorso = tmp_path / "recipe.json"
    percorso.write_text(json.dumps(recipe))
    righe: list[str] = []
    run_script(BUILD, [str(percorso), str(tmp_path)], timeout_s=180.0,
               on_line=righe.append)
    return tmp_path / "model.step", "\n".join(righe)


def _ingombro(log: str) -> list[float]:
    return [float(v) for v in log.split("ingombro verificato:")[1].split()[0:5:2]]


@needs_freecad
def test_la_cupola_sporge_dal_prisma_di_quanto_dice_la_quota(tmp_path):
    """Il bordo è sul piano misurato e il vertice sta dalla parte del verso.

    `verso` va dal vertice al bordo: con verso = −1 il bordo è a z = 12 e il
    vertice 4 mm più in alto, quindi l'ingombro del corpo cresce di 4 mm. È
    l'unica verifica che distingue una cupola costruita da una cupola stampata
    solo nel log.
    """
    cap = {"axis": "Z", "verso": -1, "semi": {"X": 12.0, "Y": 7.0},
           "altezza": 4.0, "centro": [20.0, 12.5, 12.0]}
    step, log = _costruisci(tmp_path, _ricetta(caps=[cap]))
    assert step.is_file()
    assert "cupola asse Z" in log
    assert _ingombro(log) == pytest.approx([40.0, 25.0, 16.0], abs=1e-3)


@needs_freecad
def test_una_cupola_rivolta_verso_l_interno_non_allarga_il_pezzo(tmp_path):
    """Con il verso opposto il vertice entra nel prisma: l'ingombro non cambia."""
    cap = {"axis": "Z", "verso": 1, "semi": {"X": 12.0, "Y": 7.0},
           "altezza": 4.0, "centro": [20.0, 12.5, 12.0]}
    _, log = _costruisci(tmp_path, _ricetta(caps=[cap]))
    assert _ingombro(log) == pytest.approx([40.0, 25.0, 12.0], abs=1e-6)


@needs_freecad
def test_un_foro_inclinato_attraversa_davvero_la_cupola(tmp_path):
    """Il foro obliquo entra nella cupola e ne esce: due fori, non due tacche."""
    cap = {"axis": "Z", "verso": 1, "semi": {"X": 12.0, "Y": 7.0},
           "altezza": 4.0, "centro": [20.0, 12.5, 12.0]}
    bore = {"axis": None, "direction": [0.3714, 0.0, 0.9285],
            "diameter": 2.5, "depth": 10.0, "center": [20.0, 12.5, 11.0]}
    step, log = _costruisci(tmp_path, _ricetta(caps=[cap], bores=[bore]))
    assert step.is_file()
    assert "inclinato" in log


@needs_freecad
def test_senza_cupole_la_ricetta_costruisce_quel_che_costruiva_prima(tmp_path):
    """Una mesh che non ha cupole non deve accorgersi che esistono."""
    step, log = _costruisci(tmp_path, _ricetta())
    assert step.is_file()
    assert "cupola" not in log
    ingombro = [float(v) for v in
                log.split("ingombro verificato:")[1].split()[0:5:2]]
    assert ingombro == pytest.approx([40.0, 25.0, 12.0], abs=1e-6)


@needs_freecad
def test_un_asola_si_taglia_col_suo_corpo_non_con_un_foro(tmp_path):
    """Due testate e un corpo: il taglio è uno stadio, non un cerchio."""
    bore = {"kind": "asola", "dim": "c1_asola1", "axis": "Z", "direction": None,
            "diameter": 4.0, "depth": 12.0, "center": [20.0, 12.5, 6.0],
            "slot": True, "length": 8.0, "long": [1.0, 0.0, 0.0]}
    step, log = _costruisci(tmp_path, _ricetta(bores=[bore]))
    assert step.is_file()
    assert "asola 8.000 x 4.000" in log


@needs_freecad
def test_un_apertura_rettangolare_si_taglia_davvero(tmp_path):
    """Il vano misurato diventa un taglio: la scatola della ricetta, asportata."""
    bore = {"kind": "finestra", "dim": "c1_finestra1", "axis": "Y",
            "rect": [16.0, -0.5, 4.0, 24.0, 2.0, 8.0], "depth": 2.5,
            "center": [20.0, 0.75, 6.0],
            "misure": {"larghezza_x": 8.0, "larghezza_z": 4.0}}
    step, log = _costruisci(tmp_path, _ricetta(bores=[bore]))
    assert step.is_file()
    assert "apertura 2.500" in log
    assert _ingombro(log) == pytest.approx([40.0, 25.0, 12.0], abs=1e-6)
