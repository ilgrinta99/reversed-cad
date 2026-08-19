"""Il pezzo TAISER: schema delle quote e decisioni registrate.

Questi test non richiedono FreeCAD: verificano che il registro delle quote combaci
con il `cad/params.json` committato e che le decisioni di
`docs/lost+found_design.md` §6 coprano davvero tutte le divergenze. È il controllo
che impedisce alla tabella di scollarsi dal file che il costruttore legge.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.plugin import registry as part_registry
from parts.teiser import decisions as teiser_decisions
from parts.teiser import schema

ROOT = Path(__file__).resolve().parents[1]
PARAMS = json.loads((ROOT / "cad" / "params.json").read_text())

#: Le quote in cui il valore usato dal costruttore si discosta dalla misura.
#: Sono le stesse elencate in docs/lost+found_design.md §3.1 e §6.
DIVERGENZE_ATTESE = {
    "scatola.corpo.H",          # D7 / S1: 26.999 → 27.0
    "scatola.pareti.t_x",       # B
    "scatola.pareti.t_y",       # B
    "scatola.fondo.t",          # S1
    "scatola.cavita.L",         # S1
    "scatola.cavita.W",         # S1
    "scatola.cupola.cy",        # S1: simmetrizzazione
    "coperchio.piastra.L",      # F: 74.00 → 73.86
}

#: Quote senza una misura scalare: i raccordi, che nella mesh sono ellittici.
SENZA_MISURA_ATTESE = {"scatola.raccordo_base.R", "coperchio.raccordo_base.R"}


class TestSchema:
    def test_ogni_percorso_esiste_nel_params_committato(self):
        for spec in schema.SPECS:
            assert schema.read(PARAMS, spec.path) is not None, spec.id
            if isinstance(spec.measured, str):
                assert schema.read(PARAMS, spec.measured) is not None, spec.id

    def test_le_divergenze_sono_quelle_documentate(self):
        divergenti, senza_misura = set(), set()
        for spec in schema.SPECS:
            misura = schema.measured_value(PARAMS, spec)
            usato = schema.proposed_value(PARAMS, spec)
            if misura is None:
                senza_misura.add(spec.id)
            elif abs(misura - usato) > 5e-4:
                divergenti.add(spec.id)
        assert divergenti == DIVERGENZE_ATTESE
        assert senza_misura == SENZA_MISURA_ATTESE

    def test_write_modifica_solo_il_percorso_indicato(self):
        params = json.loads(json.dumps(PARAMS))
        schema.write(params, "scatola.pareti.t_x", 9.99)
        assert params["scatola"]["pareti"]["t_x"] == 9.99
        assert params["scatola"]["pareti"]["_t_x_misurato"] == 1.293

    def test_gli_id_sono_unici(self):
        ids = [s.id for s in schema.SPECS]
        assert len(ids) == len(set(ids))


class TestDecisioni:
    def test_ambiguita_e_discrepanze_al_completo(self):
        ds = teiser_decisions.build()
        ambiguita = {d.id for d in ds if d.kind.value == "ambiguity"}
        discrepanze = {d.id for d in ds if d.kind.value == "discrepancy"}
        assert ambiguita == {"A", "B", "C", "D", "E", "F", "G", "S1"}
        assert discrepanze == {f"D{i}" for i in range(1, 9)}

    def test_tutte_gia_risolte_con_la_risposta_registrata(self):
        ds = teiser_decisions.build()
        assert ds.pending() == []
        for d in ds:
            assert d.resolved_by == "committente"
            assert "lost+found_design" in d.rationale
            assert d.resolved_at is not None

    def test_ogni_divergenza_e_coperta_da_una_decisione(self):
        ds = teiser_decisions.build()
        coperte = {dim for d in ds for dim in d.affected_dimensions}
        scoperte = (DIVERGENZE_ATTESE | SENZA_MISURA_ATTESE) - coperte
        assert scoperte == set(), (
            "queste quote divergono dalla misura e nessuna decisione le approva: "
            "resterebbero a bloccare la build"
        )

    def test_le_opzioni_puntano_a_quote_esistenti(self):
        ds = teiser_decisions.build()
        noti = set(schema.BY_ID)
        for d in ds:
            for opt in d.options:
                assert set(opt.dimensions) <= noti, f"{d.id}/{opt.id}"


@pytest.fixture(scope="module")
def misurato(tmp_path_factory):
    """Analisi vera della mesh committata: ~1 s, nessun FreeCAD."""
    from core.plugin import RunContext

    run_dir = tmp_path_factory.mktemp("teiser-run")
    plugin = part_registry.get("teiser")
    reg = plugin.declare_dimensions()
    ds = plugin.declare_decisions()
    ctx = RunContext(run_id="test", mesh_path=ROOT / "input" / "model.obj",
                     run_dir=run_dir, log=lambda _: None, timeout_s=300)
    plugin.measure(ctx, reg)
    return reg, ds, run_dir


class TestPipelineOffline:
    """Misura → decisioni → registro, senza FreeCAD.

    Verifica il punto che conta: dopo l'analisi, le decisioni registrate rendono
    il run costruibile senza che nessun numero sia stato inventato.
    """

    def test_la_misura_riempie_tutte_le_quote_misurabili(self, misurato):
        reg, _, _ = misurato
        senza = {d.id for d in reg if d.measured is None}
        assert senza == SENZA_MISURA_ATTESE

    def test_prima_delle_decisioni_il_run_non_e_costruibile(self, misurato):
        reg, _, _ = misurato
        bloccanti = {d.id for d in reg.blocking()}
        assert bloccanti == DIVERGENZE_ATTESE | SENZA_MISURA_ATTESE

    def test_le_decisioni_registrate_sbloccano_la_build(self, misurato):
        reg, ds, _ = misurato
        ds.apply_all(reg)
        reg.assert_buildable()

        # E le divergenze restano visibili: approvare non è nascondere.
        assert {d.id for d in reg.divergences()} == DIVERGENZE_ATTESE
        for dim in reg.divergences():
            assert dim.approval is not None
            assert dim.approval.decision_id in {"A", "B", "F", "S1"}

    def test_i_valori_approvati_sono_quelli_del_params_di_riferimento(self, misurato):
        reg, ds, _ = misurato
        ds.apply_all(reg)
        for dim_id, valore in reg.values().items():
            atteso = schema.proposed_value(PARAMS, schema.BY_ID[dim_id])
            assert valore == pytest.approx(atteso, abs=1e-3), dim_id
