# -*- coding: utf-8 -*-
"""Il run raccontato in italiano comune.

La pipeline è precisa e i suoi nomi sono quelli giusti — «feature non
ricostruibili», «scostamento p90», `c1_cupola1_semiasse_x`. Ma chi apre l'app per
la prima volta ha bisogno di sapere un'altra cosa: è andata bene? cosa manca?
Questi test difendono che quella risposta esista, che sia in italiano e che non
sia una seconda verità accanto ai numeri.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.mesh.ambiguity import read
from core.mesh.analysis import analyze
from parts.auto import summary as riepilogo


def _scrivi(dir_: Path, nome: str, contenuto: dict) -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / nome).write_text(json.dumps(contenuto))


def _analysis(features: list[dict], corpi: int = 1) -> dict:
    return {"bodies": [{"key": f"c{i + 1}", "name": f"corpo {i + 1}"}
                       for i in range(corpi)],
            "features": features, "measurements": [], "notes": []}


def _feature(kind: str, buildable: bool, centro=(0.0, 0.0, 0.0)) -> dict:
    return {"kind": kind, "body": "corpo 1", "label": f"corpo 1: {kind}",
            "params": {"centro_x": centro[0], "centro_y": centro[1],
                       "centro_z": centro[2]},
            "note": "", "buildable": buildable}


# ------------------------------------------------------------- stati del run


def test_prima_dell_analisi_il_riepilogo_non_inventa_uno_stato(tmp_path: Path):
    """Nessun file, nessuna frase: «non lo so» detto come si deve."""
    r = riepilogo.riassumi(tmp_path)
    assert r["stato"] == "da_analizzare"
    assert r["frasi"] == []


def test_dopo_l_analisi_dice_cosa_ha_trovato_e_basta(tmp_path: Path):
    """Senza ricetta non c'è ancora un modello: non si parla di ricostruzione."""
    _scrivi(tmp_path, "analysis.json",
            _analysis([_feature("foro", True), _feature("libera", False)]))
    r = riepilogo.riassumi(tmp_path)
    assert r["stato"] == "analizzato"
    assert len(r["frasi"]) == 1
    assert "1 pezzo" in r["frasi"][0] and "2 dettagli" in r["frasi"][0]


def test_uno_scostamento_minimo_con_poche_feature_non_e_fedele(tmp_path: Path):
    """Le due misure dicono cose diverse, e il riepilogo non le confonde.

    Lo scostamento pesa i *punti* della mesh: una cupola fitta di triangoli lo
    tiene basso anche se dieci smussi sono rimasti fuori. Dire «fedele» sarebbe
    vero e fuorviante insieme.
    """
    features = [_feature("cupola", True)] + [_feature("arco", False) for _ in range(9)]
    _scrivi(tmp_path, "analysis.json", _analysis(features))
    _scrivi(tmp_path, "recipe.json",
            {"bodies": [{"name": "corpo 1", "key": "c1", "caps": [{"centro": [0, 0, 0]}],
                         "bores": []}]})
    _scrivi(tmp_path, "deviation.json", {"stats": {"mediana_mm": 0.02}})
    r = riepilogo.riassumi(tmp_path)
    assert r["stato"] == "parziale"
    assert "9 su 10" not in r["frasi"][1]      # 1 su 10, non il contrario
    assert "1 su 10" in r["frasi"][1]
    assert "9 smussi" in r["frasi"][1]


def test_tutto_ricostruito_e_scostamento_minimo_e_fedele(tmp_path: Path):
    _scrivi(tmp_path, "analysis.json", _analysis([_feature("foro", True)]))
    _scrivi(tmp_path, "recipe.json",
            {"bodies": [{"name": "corpo 1", "key": "c1", "caps": [],
                         "bores": [{"center": [0.0, 0.0, 0.0]}]}]})
    _scrivi(tmp_path, "deviation.json", {"stats": {"mediana_mm": 0.01}})
    r = riepilogo.riassumi(tmp_path)
    assert r["stato"] == "fedele"
    assert r["frasi"][1] == "Li ho ricostruiti tutti."


def test_uno_scostamento_grosso_lo_dice_senza_giri_di_parole(tmp_path: Path):
    _scrivi(tmp_path, "analysis.json", _analysis([_feature("foro", True)]))
    _scrivi(tmp_path, "recipe.json",
            {"bodies": [{"name": "corpo 1", "key": "c1", "caps": [],
                         "bores": [{"center": [0.0, 0.0, 0.0]}]}]})
    _scrivi(tmp_path, "deviation.json", {"stats": {"mediana_mm": 3.4}})
    r = riepilogo.riassumi(tmp_path)
    assert r["stato"] == "grossolano"
    assert "grossolana" in r["frasi"][-1]
    # I millimetri restano: il giudizio accompagna la cifra, non la sostituisce.
    assert "3,400 mm" in r["frasi"][-1]


# ------------------------------------------------------- una sola verità


def test_il_riepilogo_e_il_disegno_contano_le_stesse_feature(tmp_path: Path):
    """Se divergessero, uno dei due mentirebbe — e non si saprebbe quale."""
    from parts.auto import drawing

    features = [_feature("foro", True, (1.0, 2.0, 3.0)),
                _feature("libera", False, (9.0, 9.0, 9.0))]
    recipe = {"bodies": [{"name": "corpo 1", "key": "c1", "caps": [],
                          "bores": [{"center": [1.0, 2.0, 3.0]}]}]}
    _scrivi(tmp_path, "analysis.json", _analysis(features))
    _scrivi(tmp_path, "recipe.json", recipe)
    r = riepilogo.riassumi(tmp_path)

    fuori_dal_riepilogo = sum(v["quanti"] for v in r["mancante"])
    fuori_dal_disegno = sum(1 for f in features if not drawing._nel_modello(f, recipe))
    assert fuori_dal_riepilogo == fuori_dal_disegno == 1


# --------------------------------------------------------- domande in chiaro


def test_ogni_domanda_si_capisce_senza_sapere_cos_e_un_paraboloide():
    """`plain` non è un di più: è la prima riga che l'utente legge."""
    mesh = Path("input/model.obj")
    if not mesh.is_file():
        pytest.skip("input/model.obj non disponibile")
    reading = read(analyze(mesh))
    assert reading.decisions.decisions, "il TAISER solleva domande"
    for decision in reading.decisions.decisions.values():
        assert decision.plain, f"{decision.id} senza formulazione in chiaro"
        assert decision.plain != decision.question
        assert decision.plain.rstrip().endswith("?"), \
            f"{decision.id}: una domanda finisce con un punto interrogativo"
        # La formulazione tecnica resta: `plain` la affianca, non la sostituisce.
        assert decision.question and decision.evidence


def test_la_domanda_in_chiaro_arriva_fino_al_client():
    from core.provenance.decisions import Decision, DecisionKind, Option

    d = Decision(id="x", kind=DecisionKind.AMBIGUITY, title="t", question="q?",
                 plain="Le tengo così o le faccio rotonde?",
                 options=(Option(id="a", label="A"),))
    assert d.to_dict()["plain"] == "Le tengo così o le faccio rotonde?"
