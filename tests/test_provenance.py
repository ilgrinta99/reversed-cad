"""La regola non negoziabile deve essere verificabile, non solo dichiarata."""

from __future__ import annotations

import pytest

from core.provenance import (
    Decision,
    DecisionKind,
    DecisionSet,
    Dimension,
    Option,
    Origin,
    Registry,
    Status,
    UnapprovedDimensions,
)


def measured(dim_id: str, value: float, **kw) -> Dimension:
    return Dimension(id=dim_id, label=dim_id, measured=value, used=value,
                     measured_by="tools/extract_params.py", **kw)


class TestDimensionStatus:
    def test_valore_misurato_e_usato_coincidono(self):
        d = measured("altezza", 12.5)
        assert d.status is Status.MEASURED_OK
        assert d.origin is Origin.MEASURED
        assert not d.diverges
        assert not d.status.blocks_build

    def test_quota_senza_valore_blocca(self):
        d = Dimension(id="raggio", label="raggio cupola")
        assert d.status is Status.MISSING
        assert d.status.blocks_build
        assert d.origin is None

    def test_divergenza_non_approvata_blocca(self):
        d = measured("spessore", 2.0)
        d = Dimension(**{**d.__dict__, "used": 2.5})
        assert d.diverges
        assert d.status is Status.UNAPPROVED_DIVERGENCE
        assert d.status.blocks_build

    def test_divergenza_approvata_passa_e_resta_visibile(self):
        d = measured("spessore", 2.0).approve(
            2.5, by="utente", rationale="D4: spessore nominale di stampa"
        )
        assert d.status is Status.APPROVED_OVERRIDE
        assert not d.status.blocks_build
        # ma la divergenza NON sparisce: resta mostrabile in tabella
        assert d.diverges
        assert d.divergence == pytest.approx(0.5)
        assert "approvato da utente" in d.explain()

    def test_scostamento_sotto_tolleranza_non_e_divergenza(self):
        d = measured("larghezza", 40.0)
        d = Dimension(**{**d.__dict__, "used": 40.0 + 1e-5})
        assert not d.diverges
        assert d.status is Status.MEASURED_OK

    def test_valore_senza_misura_richiede_approvazione(self):
        d = Dimension(id="raggio_raccordo", label="raggio raccordo", used=1.0)
        assert d.status is Status.MISSING, "un numero dal nulla non è ammesso"

        approved = d.approve(1.0, by="utente", rationale="A2: scelto dall'utente")
        assert approved.status is Status.APPROVED_OVERRIDE
        assert approved.origin is Origin.APPROVED

    def test_approvazione_senza_motivazione_e_rifiutata(self):
        with pytest.raises(ValueError, match="motivazione"):
            measured("spessore", 2.0).approve(2.5, by="utente", rationale="   ")

    def test_quota_derivata_dichiara_la_formula(self):
        d = Dimension(id="raggio_interno", label="raggio interno", used=18.0,
                      derived_from="raggio_esterno - spessore")
        assert d.status is Status.DERIVED_OK
        assert d.origin is Origin.DERIVED
        assert "raggio_esterno - spessore" in d.explain()


class TestRegistryGate:
    def test_build_bloccata_finche_restano_quote_irrisolte(self):
        reg = Registry()
        reg.extend([measured("a", 1.0), Dimension(id="b", label="b")])

        assert [d.id for d in reg.blocking()] == ["b"]
        with pytest.raises(UnapprovedDimensions) as exc:
            reg.assert_buildable()
        assert "b" in str(exc.value)

    def test_values_non_restituisce_mai_numeri_non_verificati(self):
        reg = Registry()
        reg.extend([measured("a", 1.0), Dimension(id="b", label="b")])
        with pytest.raises(UnapprovedDimensions):
            reg.values()

        reg.update(reg.get("b").approve(3.0, by="utente", rationale="G: scelta utente"))
        assert reg.values() == {"a": 1.0, "b": 3.0}

    def test_divergenze_restano_elencabili_dopo_approvazione(self):
        reg = Registry()
        reg.add(measured("spessore", 2.0))
        reg.update(reg.get("spessore").approve(2.5, by="utente", rationale="D4"))

        reg.assert_buildable()  # non blocca
        assert [d.id for d in reg.divergences()] == ["spessore"]  # ma resta in evidenza

    def test_roundtrip_serializzazione(self):
        reg = Registry()
        reg.add(measured("a", 1.0))
        reg.add(measured("b", 2.0).approve(2.5, by="utente", rationale="D1"))

        back = Registry.from_dict(reg.to_dict())
        assert len(back) == 2
        assert back.get("b").status is Status.APPROVED_OVERRIDE
        assert back.get("b").approval is not None
        assert back.get("b").approval.rationale == "D1"

    def test_riepilogo_conta_gli_stati(self):
        reg = Registry()
        reg.extend([measured("a", 1.0), Dimension(id="b", label="b")])
        s = reg.summary()
        assert s[Status.MEASURED_OK.value] == 1
        assert s[Status.MISSING.value] == 1


def _decision() -> Decision:
    return Decision(
        id="D4",
        kind=DecisionKind.DISCREPANCY,
        title="Spessore parete",
        question="La mesh misura 2.0 mm, la tavola TinkerCAD indica 2.5 mm. Quale vale?",
        evidence="La tavola è generata dalla mesh stessa: non è una fonte indipendente.",
        reference="docs/lost+found_design.md §2.1",
        options=(
            Option(id="mesh", label="Tieni la misura della mesh", sets={"spessore": 2.0},
                   consequence="Il modello resta fedele al pezzo scansionato."),
            Option(id="nominale", label="Usa il nominale 2.5", sets={"spessore": 2.5},
                   consequence="Parete più spessa del pezzo reale di 0.5 mm."),
        ),
    )


class TestDecisions:
    def test_una_decisione_risolta_scrive_una_approvazione(self):
        reg = Registry()
        reg.add(measured("spessore", 2.0))

        ds = DecisionSet()
        ds.add(_decision())
        assert [d.id for d in ds.pending()] == ["D4"]

        ds.resolve("D4", "nominale", by="utente", rationale="stampa 3D, tolleranza nota")
        assert ds.pending() == []
        ds.apply_all(reg)

        dim = reg.get("spessore")
        assert dim.used == 2.5
        assert dim.status is Status.APPROVED_OVERRIDE
        assert dim.approval is not None
        assert dim.approval.decision_id == "D4"
        assert "D4 → Usa il nominale 2.5" in dim.approval.rationale

    def test_opzione_inesistente_rifiutata(self):
        ds = DecisionSet()
        ds.add(_decision())
        with pytest.raises(KeyError, match="opzione sconosciuta"):
            ds.resolve("D4", "inventata", by="utente", rationale="x")

    def test_decisione_non_risolta_non_puo_essere_applicata(self):
        reg = Registry()
        reg.add(measured("spessore", 2.0))
        with pytest.raises(ValueError, match="non è ancora stata risolta"):
            _decision().apply_to(reg)

    def test_quote_impattate_dichiarate(self):
        assert _decision().affected_dimensions == ["spessore"]
