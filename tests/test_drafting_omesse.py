# -*- coding: utf-8 -*-
"""Quello che il modello non porta deve vedersi sulla tavola, non solo saperlo.

Il difetto che questi test difendono è concreto: una mesh con una cupola e dei
fori produceva un foglio in cui la cupola non c'era e niente diceva che ci fosse
stata. La tavola era corretta rispetto al *solido* e muta rispetto al *pezzo*.

Due vincoli, e sono opposti fra loro:

1. una superficie misurata che il ricostruttore non porta compare sulle viste con
   la sua impronta, e nel registro con il suo nome;
2. una feature che il solido *contiene* non compare fra le omesse — anche quando
   `buildable` dice di no, come per un'asola che una decisione ha promosso a foro.
"""

from __future__ import annotations

from core.drafting import tavola
from core.provenance import Registry
from parts.auto import drawing


def _analysis(features: list[dict]) -> dict:
    return {"bodies": [], "features": features, "measurements": [], "notes": []}


def _omessa(body: str, kind: str, origine, ingombro, area: float = 100.0,
            raggio: float | None = None) -> dict:
    params = {
        "area": area, "spread_deg": 40.0,
        "dx": ingombro[0], "dy": ingombro[1], "dz": ingombro[2],
        "origine_x": origine[0], "origine_y": origine[1], "origine_z": origine[2],
        "centro_x": origine[0] + ingombro[0] / 2.0,
        "centro_y": origine[1] + ingombro[1] / 2.0,
        "centro_z": origine[2] + ingombro[2] / 2.0,
    }
    if raggio is not None:
        params["raggio"] = raggio
    return {"kind": kind, "body": body, "label": f"{body}: superficie",
            "params": params, "note": "prova", "buildable": False}


def _corpo(bores: list[dict] | None = None) -> dict:
    return {"name": "scatola", "key": "c1", "origin": [0.0, 0.0, 0.0],
            "size": [40.0, 25.0, 12.0], "fillet": None, "cavity": None,
            "bores": bores or []}


def _recipe(bores: list[dict] | None = None) -> dict:
    return {"bodies": [_corpo(bores)], "source": "prova.obj"}


# ------------------------------------------------------- impronte sulle viste


def test_una_superficie_omessa_lascia_la_sua_impronta_sulle_tre_viste():
    """Il rettangolo d'ingombro, in tutte le viste in cui si vede."""
    omesse = [_omessa("scatola", "libera", (10.0, 5.0, 0.0), (20.0, 15.0, 3.0))]
    sagome, richiami = drawing._omesse_sulle_viste("c1", _corpo(), omesse, 1.0)

    assert {s.vista for s in sagome} == {"c1_pianta", "c1_prospetto", "c1_laterale"}
    assert all(s.stile == 'omesso' for s in sagome), \
        "l'impronta non deve confondersi con il profilo della mesh né con gli spigoli"
    pianta = next(s for s in sagome if s.vista == "c1_pianta")
    assert set(pianta.punti) == {(10.0, 5.0), (30.0, 5.0), (30.0, 20.0), (10.0, 20.0)}
    assert len(richiami) == 1
    assert "superficie libera" in richiami[0].righe[0]


def test_una_impronta_piu_piccola_del_tratto_resta_fuori_dalle_viste():
    """Sotto la soglia il rettangolo è una macchia, non un'informazione.

    Resta nel registro: la tavola non la nasconde, la mette dove si legge.
    """
    minuscola = [_omessa("scatola", "sfera", (10.0, 5.0, 0.0), (0.4, 0.4, 0.4),
                         area=1.2, raggio=0.2)]
    sagome, richiami = drawing._omesse_sulle_viste("c1", _corpo(), minuscola, 1.0)
    assert sagome == [] and richiami == []
    # A scala 10:1 la stessa impronta si vede, e allora si disegna.
    sagome, _ = drawing._omesse_sulle_viste("c1", _corpo(), minuscola, 10.0)
    assert len(sagome) == 3


def test_i_richiami_si_incolonnano_invece_di_sovrapporsi():
    """Due impronte a due millimetri l'una dall'altra non danno due testi sovrapposti."""
    vicine = [_omessa("scatola", "sfera", (30.0, 20.0, 6.0), (3.0, 3.0, 3.0), raggio=1.5),
              _omessa("scatola", "sfera", (30.0, 16.0, 6.0), (3.0, 3.0, 3.0), raggio=1.5)]
    _, richiami = drawing._omesse_sulle_viste("c1", _corpo(), vicine, 1.0)
    assert len(richiami) == 2
    testo_y = [r.punto[1] + r.scostamento[1] for r in richiami]
    assert abs(testo_y[0] - testo_y[1]) >= drawing.PASSO_RICHIAMO - 1e-9


def test_il_numero_del_richiamo_ritrova_la_riga_del_registro():
    """Il richiamo porta l'indice, e l'indice è l'ordine per area decrescente."""
    features = [_omessa("scatola", "libera", (0.0, 0.0, 0.0), (5.0, 5.0, 5.0), area=10.0),
                _omessa("scatola", "libera", (10.0, 10.0, 0.0), (9.0, 9.0, 5.0), area=90.0)]
    ordinate = drawing.omesse_del_corpo(_analysis(features), "scatola")
    assert [f["params"]["area"] for f in ordinate] == [90.0, 10.0]
    _, richiami = drawing._omesse_sulle_viste("c1", _corpo(), ordinate, 1.0)
    assert richiami[0].righe[0].startswith("1 ")


def test_solo_le_omesse_del_corpo_giusto_finiscono_sul_suo_foglio():
    features = [_omessa("scatola", "libera", (0.0, 0.0, 0.0), (5.0, 5.0, 5.0)),
                _omessa("coperchio", "libera", (0.0, 0.0, 0.0), (5.0, 5.0, 5.0))]
    assert len(drawing.omesse_del_corpo(_analysis(features), "scatola")) == 1


# ------------------------------------------------- elenco del foglio registro


def test_una_asola_promossa_a_foro_non_e_piu_una_feature_omessa():
    """`buildable` dice se il repertorio *saprebbe*; la ricetta dice se l'ha fatto.

    Con la decisione «asole = fori» l'asola entra nel solido pur restando
    `buildable=False`. Elencarla fra le non ricostruite era una bugia simmetrica a
    quella che questo modulo esiste per evitare.
    """
    asola = {"kind": "asola", "body": "scatola", "label": "scatola: asola 1",
             "params": {"diametro": 5.0, "profondita": 2.5, "larghezza": 5.0,
                        "lunghezza": 8.0,
                        "centro_x": 12.0, "centro_y": 6.0, "centro_z": 1.25},
             "note": "asse Z", "buildable": False}
    costruita = _recipe([{"axis": "Z", "diameter": 5.0, "depth": 2.5,
                          "center": [12.0, 6.0, 1.25]}])
    riquadri = drawing._riquadri_finali(_analysis([asola]), None, None, costruita)
    righe = riquadri[0].righe
    assert righe == ("Nessuna: il repertorio del ricostruttore copre tutta la mesh.",)

    # Senza quella decisione l'asola non è nel solido, e allora va detto.
    riquadri = drawing._riquadri_finali(_analysis([asola]), None, None, _recipe())
    assert any("asola" in riga for riga in riquadri[0].righe)


def test_un_corpo_fuori_dalla_ricetta_porta_fuori_tutte_le_sue_feature():
    """Con la decisione «corpi = principale» il secondo corpo non è nel modello."""
    features = [
        {"kind": "prisma", "body": "coperchio", "label": "coperchio: ingombro esterno",
         "params": {}, "note": "", "buildable": True},
        _omessa("coperchio", "libera", (0.0, 0.0, 0.0), (5.0, 5.0, 5.0)),
    ]
    riquadri = drawing._riquadri_finali(_analysis(features), None, None, _recipe())
    assert len(riquadri[0].righe) == 2


def test_l_elenco_censisce_per_tipo_invece_di_troncare():
    """Venti voci non ci stanno sul foglio, e troncarle perderebbe le più piccole."""
    features = [_omessa("scatola", "libera", (float(i), 0.0, 0.0), (5.0, 5.0, 5.0),
                        area=10.0 + i)
                for i in range(12)]
    riquadri = drawing._riquadri_finali(_analysis(features), None, None, _recipe())
    righe = riquadri[0].righe
    assert len(righe) == 1
    assert righe[0].startswith("scatola — 12×  superficie libera")
    assert righe[0].endswith("(la maggiore)")


def test_una_omessa_sola_porta_anche_la_posizione():
    features = [_omessa("scatola", "sfera", (10.0, 5.0, 2.0), (4.0, 4.0, 2.0),
                        raggio=2.0)]
    riquadri = drawing._riquadri_finali(_analysis(features), None, None, _recipe())
    assert riquadri[0].righe[0] == "scatola — calotta sferica  4.00×4.00×2.00 mm  " \
                                   "in (12.00, 7.00, 3.00)"


# ------------------------------------------------------------ foglio completo


def test_il_foglio_del_corpo_dichiara_le_impronte_in_nota():
    features = [_omessa("scatola", "libera", (10.0, 5.0, 0.0), (20.0, 15.0, 3.0))]
    proiezioni = {f"c1_{v}": {"visibili": [], "nascosti": [], "bbox": [0, 0, 40, 25]}
                  for v in ("pianta", "prospetto", "laterale", "iso")}
    fogli = drawing.fogli(_recipe(), _analysis(features), Registry(), proiezioni,
                          sorgente="prova.obj")
    corpo = fogli[1]
    assert any("Linea viola" in riga for riga in corpo.cartiglio.note)
    assert any(s.stile == 'omesso' for s in corpo.sagome)
    # La fascia note del cartiglio ne tiene quattro: oltre, il testo esce dal riquadro.
    assert len(corpo.cartiglio.note) <= 4


def test_senza_omesse_il_foglio_resta_quello_di_prima():
    """Una mesh che il repertorio copre tutta non cambia di una virgola."""
    proiezioni = {f"c1_{v}": {"visibili": [], "nascosti": [], "bbox": [0, 0, 40, 25]}
                  for v in ("pianta", "prospetto", "laterale", "iso")}
    fogli = drawing.fogli(_recipe(), _analysis([]), Registry(), proiezioni,
                          sorgente="prova.obj")
    corpo = fogli[1]
    assert corpo.sagome == []
    assert not any("Linea viola" in riga for riga in corpo.cartiglio.note)


def test_l_impronta_ha_uno_stile_suo_nei_tre_formati():
    """Colore e layer separati: in CAD si spegne con un clic, come il profilo mesh."""
    from core.drafting.sheet import STILI

    assert 'omesso' in STILI
    colore, spessore, tratteggio, layer, _ = STILI['omesso']
    assert tratteggio, "l'impronta non è una linea continua: non è geometria del modello"
    assert layer not in {STILI['contorno'][3], STILI['riferimento'][3]}


def test_la_sagoma_di_default_resta_il_profilo_della_mesh():
    """Chi già usava `Sagoma` non deve accorgersi di niente."""
    assert tavola.Sagoma("v", ((0.0, 0.0), (1.0, 1.0))).stile == 'riferimento'
