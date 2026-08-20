"""Percorso completo attraverso l'API: upload → analisi → decisioni → build → tavola.

Il test che conta di più è `test_build_bloccata_senza_quote_approvate`: la regola
non negoziabile deve valere anche passando dagli endpoint, non solo nel dominio.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from tests.conftest import needs_freecad


def wait_job(client, job_id: str, timeout: float = 120.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] in ("succeeded", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} non terminato entro {timeout}s")


def job_log(client, job_id: str) -> str:
    stream = client.get(f"/api/jobs/{job_id}/stream").text
    return stream


@pytest.fixture(scope="module")
def run(client, box_obj: Path) -> dict:
    with box_obj.open("rb") as fh:
        resp = client.post(
            "/api/runs",
            data={"part_id": "demo_box", "title": "scatola di prova"},
            files={"mesh": ("box.obj", fh, "text/plain")},
        )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_health_elenca_i_pezzi(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert "demo_box" in body["parts"]


def test_pezzi_collegati(client, box_obj: Path):
    parts = {p["id"]: p for p in client.get("/api/parts").json()}
    assert parts["teiser"]["wired"] is True
    assert parts["demo_box"]["wired"] is True

    # Un pezzo inesistente non crea un run a metà.
    with box_obj.open("rb") as fh:
        resp = client.post(
            "/api/runs",
            data={"part_id": "inesistente"},
            files={"mesh": ("box.obj", fh, "text/plain")},
        )
    assert resp.status_code == 404


def test_solo_i_formati_mesh_sono_accettati(client, box_obj: Path):
    """Quattro formati sì, il resto no — e il rifiuto dice quali sono.

    L'elenco non è scritto nell'endpoint: viene da `core/mesh/loader.py`, che è
    l'unico posto che sa davvero cosa si riesce a leggere.
    """
    from core.mesh.loader import SUFFISSI

    with box_obj.open("rb") as fh:
        resp = client.post(
            "/api/runs",
            data={"part_id": "demo_box"},
            files={"mesh": ("modello.3mf", fh, "text/plain")},
        )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    for suffisso in SUFFISSI:
        assert suffisso in detail


def test_i_formati_letti_sono_dichiarati_da_health(client):
    formati = client.get("/api/health").json()["mesh_formats"]
    assert set(formati) == {".obj", ".stl", ".ply", ".wrl"}


def test_run_nasce_senza_quote_usate(run):
    dims = {d["id"]: d for d in run["provenance"]["dimensions"]}
    assert set(dims) == {"length", "width", "height"}
    for d in dims.values():
        assert d["used"] is None
        assert d["status"] == "missing"
        assert d["blocks_build"] is True


def test_build_bloccata_senza_quote_approvate(client, run):
    """La regola non negoziabile, vista dall'API."""
    readiness = client.get(f"/api/runs/{run['id']}/readiness").json()
    assert readiness["buildable"] is False
    assert len(readiness["blocking"]) == 3

    job = wait_job(client, client.post(f"/api/runs/{run['id']}/jobs/build").json()["id"])
    assert job["state"] == "failed"
    assert "non sono né misurate né approvate" in job["error"]


def test_analisi_misura_la_mesh(client, run):
    job = wait_job(client, client.post(f"/api/runs/{run['id']}/jobs/analyze").json()["id"])
    assert job["state"] == "succeeded", job["error"]
    assert job["result"]["metrics"]["vertices"] == 8
    assert job["result"]["metrics"]["triangles"] == 12

    dims = {d["id"]: d for d in client.get(f"/api/runs/{run['id']}/dimensions").json()["dimensions"]}
    assert dims["length"]["measured"] == pytest.approx(40.0)
    assert dims["width"]["measured"] == pytest.approx(25.0)
    assert dims["height"]["measured"] == pytest.approx(12.0)

    # Misurato non significa ancora usato: la conferma è uno step esplicito.
    assert all(d["used"] is None for d in dims.values())
    assert all(d["blocks_build"] for d in dims.values())
    assert "tools" in dims["length"]["measured_by"] or "plugin" in dims["length"]["measured_by"]


def test_accettazione_e_approvazione_registrano_la_provenienza(client, run):
    run_id = run["id"]
    for dim_id in ("length", "width"):
        d = client.post(f"/api/runs/{run_id}/dimensions/{dim_id}/accept-measured").json()
        assert d["status"] == "measured_ok"
        assert d["origin"] == "measured"

    # La terza viene forzata a un valore diverso: deve restare marcata come divergenza.
    d = client.post(
        f"/api/runs/{run_id}/dimensions/height/approve",
        json={"value": 12.5, "rationale": "A1: altezza nominale di stampa", "by": "utente"},
    ).json()
    assert d["status"] == "approved_override"
    assert d["divergence"] == pytest.approx(0.5)
    assert d["approval"]["rationale"] == "A1: altezza nominale di stampa"

    readiness = client.get(f"/api/runs/{run_id}/readiness").json()
    assert readiness["buildable"] is True
    assert [x["id"] for x in readiness["divergences"]] == ["height"]


def test_approvazione_senza_motivazione_rifiutata(client, run):
    resp = client.post(
        f"/api/runs/{run['id']}/dimensions/height/approve",
        json={"value": 12.5, "rationale": ""},
    )
    assert resp.status_code == 422  # pydantic: min_length=1


def test_decisione_scrive_nel_registro(client, run):
    run_id = run["id"]
    decisions = client.get(f"/api/runs/{run_id}/decisions").json()
    assert decisions["pending"] == ["A1"]

    resp = client.post(
        f"/api/runs/{run_id}/decisions/A1",
        json={"option_id": "misurato", "rationale": "resto fedele alla mesh"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["decision"]["resolved"] is True

    resp = client.post(
        f"/api/runs/{run_id}/decisions/A1",
        json={"option_id": "inesistente", "rationale": "x"},
    )
    assert resp.status_code == 404


@needs_freecad
def test_build_produce_step_e_stl(client, run):
    job = wait_job(client, client.post(f"/api/runs/{run['id']}/jobs/build").json()["id"])
    assert job["state"] == "succeeded", job["error"]
    assert job["result"]["artifacts"]["step"] == "model.step"

    artifacts = {a["path"] for a in client.get(f"/api/runs/{run['id']}/artifacts").json()}
    assert {"model.step", "model.stl", "params.json"} <= artifacts

    step = client.get(f"/api/runs/{run['id']}/artifacts/model.step")
    assert step.status_code == 200
    assert step.text.startswith("ISO-10303-21")

    # I valori usati sono quelli approvati, non quelli misurati.
    params = json.loads(client.get(f"/api/runs/{run['id']}/artifacts/params.json").text)
    assert params["height"] == pytest.approx(12.5)


def test_tavola_svg_senza_freecad(client, run):
    """L'anteprima della tavola non deve dipendere da FreeCAD."""
    job = wait_job(client, client.post(f"/api/runs/{run['id']}/jobs/draw").json()["id"])
    assert job["state"] == "succeeded", job["error"]

    svg = client.get(f"/api/runs/{run['id']}/artifacts/drawing.svg")
    assert svg.status_code == 200
    assert svg.text.startswith("<svg")
    assert "Pianta" in svg.text


def test_confronto_restituisce_lo_scostamento(client, run):
    run_id = run["id"]
    job = wait_job(client, client.post(f"/api/runs/{run_id}/jobs/compare").json()["id"])
    if job["state"] == "failed":
        assert "eseguire prima la build" in job["error"]
        pytest.skip("build non eseguita (FreeCAD assente)")
    # L'altezza è stata approvata a 12.5 contro i 12.0 misurati: lo scostamento
    # massimo deve valere esattamente quella divergenza, non zero.
    assert job["result"]["metrics"]["max_mm"] == pytest.approx(0.5, abs=1e-6)

    report = client.get(f"/api/runs/{run_id}/artifacts/deviation.json").json()
    assert len(report["points"][0]) == 4, "ogni punto porta x, y, z e scostamento"
    assert report["soglie_mm"] == {"piana": 0.10, "curva": 0.50}


def test_log_del_job_in_streaming(client, run):
    job_id = client.post(f"/api/runs/{run['id']}/jobs/analyze").json()["id"]
    wait_job(client, job_id)
    stream = job_log(client, job_id)
    assert "event: log" in stream
    assert "mesh caricata" in stream
    assert "event: state" in stream


def test_fork_crea_un_run_indipendente(client, run):
    forked = client.post(f"/api/runs/{run['id']}/fork").json()
    assert forked["id"] != run["id"]
    assert forked["parent_id"] == run["id"]
    # La provenance viene ereditata: le decisioni prese non si ripetono da capo.
    dims = {d["id"]: d for d in forked["provenance"]["dimensions"]}
    assert dims["height"]["used"] == pytest.approx(12.5)
    assert dims["height"]["status"] == "approved_override"


def test_percorso_artefatto_non_esce_dalla_cartella_del_run(client, run):
    resp = client.get(f"/api/runs/{run['id']}/artifacts/../../../etc/passwd")
    assert resp.status_code == 404
