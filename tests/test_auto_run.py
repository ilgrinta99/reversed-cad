"""Il percorso normale del prodotto: si carica un OBJ e basta.

Nessun pezzo da scegliere, nessuna quota nota prima dell'analisi, nessuna
ambiguità decisa in anticipo. Quello che il run contiene dopo l'upload e quello
che contiene dopo l'analisi sono due cose diverse, e questi test verificano
esattamente il passaggio fra le due.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest


def wait_job(client, job_id: str, timeout: float = 180.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] in ("succeeded", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} non terminato entro {timeout}s")


def create(client, mesh_path: Path) -> dict:
    with mesh_path.open("rb") as fh:
        response = client.post("/api/runs",
                               files={"mesh": (mesh_path.name, fh, "text/plain")})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(scope="module")
def run(client, box_obj: Path) -> dict:
    return create(client, box_obj)


def test_upload_senza_scegliere_il_pezzo(run):
    """Il caricamento non chiede altro che il file."""
    assert run["part_id"] == "auto"
    # Prima di misurare non esistono quote: dichiararne sarebbe presumere il pezzo.
    assert run["provenance"]["dimensions"] == []
    assert run["decisions"]["decisions"] == []


def test_le_quote_nascono_dall_analisi(client, run):
    job = wait_job(client, client.post(f"/api/runs/{run['id']}/jobs/analyze").json()["id"])
    assert job["state"] == "succeeded", job["error"]
    assert job["result"]["metrics"]["corpi"] == 1
    assert job["result"]["metrics"]["quote"] > 0

    dims = {d["id"]: d for d in
            client.get(f"/api/runs/{run['id']}/dimensions").json()["dimensions"]}
    assert dims["c1_ingombro_x"]["measured"] == pytest.approx(40.0)
    assert dims["c1_ingombro_z"]["measured"] == pytest.approx(12.0)
    # Il valore misurato è già un'origine legittima: la mesh non è ambigua e la
    # build non ha niente da chiedere.
    assert dims["c1_ingombro_x"]["status"] == "measured_ok"
    assert "core/mesh/analysis.py" in dims["c1_ingombro_x"]["measured_by"]

    readiness = client.get(f"/api/runs/{run['id']}/readiness").json()
    assert readiness["buildable"] is True
    assert readiness["blocking"] == []


def test_nessuna_ambiguita_su_una_mesh_pulita(client, run):
    decisions = client.get(f"/api/runs/{run['id']}/decisions").json()
    assert decisions["decisions"] == []


def test_ambiguita_generate_dalla_mesh_caricata(client, tmp_path_factory):
    """Una mesh con quote quasi tonde solleva la scheda di arrotondamento."""
    from tests.test_mesh_analysis import prism_obj

    mesh = prism_obj(tmp_path_factory.mktemp("quasi") / "quasi.obj",
                     [(0, 0), (40.02, 0), (40.02, 12), (0, 12)], 25.0)
    run = create(client, mesh)
    wait_job(client, client.post(f"/api/runs/{run['id']}/jobs/analyze").json()["id"])

    decisions = client.get(f"/api/runs/{run['id']}/decisions").json()
    assert "arrotondamento" in decisions["pending"]

    resolved = client.post(f"/api/runs/{run['id']}/decisions/arrotondamento",
                           json={"option_id": "passo_0_1",
                                 "rationale": "quote di progetto tonde al decimo"})
    assert resolved.status_code == 200, resolved.text
    dims = {d["id"]: d for d in resolved.json()["provenance"]["dimensions"]}
    assert dims["c1_ingombro_x"]["used"] == pytest.approx(40.0)
    assert dims["c1_ingombro_x"]["measured"] == pytest.approx(40.02)
    assert dims["c1_ingombro_x"]["status"] == "approved_override"
    assert dims["c1_ingombro_x"]["approval"]["rationale"].startswith("arrotondamento")

    # Rimisurare non cancella la decisione presa: è il punto del registro.
    wait_job(client, client.post(f"/api/runs/{run['id']}/jobs/analyze").json()["id"])
    dims = {d["id"]: d for d in
            client.get(f"/api/runs/{run['id']}/dimensions").json()["dimensions"]}
    assert dims["c1_ingombro_x"]["used"] == pytest.approx(40.0)
    assert dims["c1_ingombro_x"]["status"] == "approved_override"


def test_tavola_e_analisi_senza_freecad(client, run):
    """Anteprima della tavola e report di analisi non passano da FreeCAD."""
    job = wait_job(client, client.post(f"/api/runs/{run['id']}/jobs/draw").json()["id"])
    assert job["state"] == "succeeded", job["error"]
    svg = client.get(f"/api/runs/{run['id']}/artifacts/drawing.svg")
    assert svg.status_code == 200
    assert "Pianta" in svg.text
    # In pianta il contorno vero della mesh è ricalcato sopra l'ingombro: è il
    # modo per vedere la differenza fra pezzo e ricostruzione senza la build.
    assert 'class="mesh"' in svg.text

    analysis = client.get(f"/api/runs/{run['id']}/artifacts/analysis.json").json()
    assert analysis["triangles"] == 12
    assert analysis["bodies"][0]["closed"] is True
    assert any(f["kind"] == "prisma" for f in analysis["features"])


def test_la_decisione_fermati_blocca_la_ricetta(client, tmp_path_factory):
    """«Fermati» non è decorativo: senza un ricostruttore adeguato non si costruisce."""
    mesh = Path("input/model.obj")
    if not mesh.is_file():
        pytest.skip("input/model.obj non disponibile")
    run = create(client, mesh)
    wait_job(client, client.post(f"/api/runs/{run['id']}/jobs/analyze").json()["id"])

    decisions = client.get(f"/api/runs/{run['id']}/decisions").json()
    assert "superfici_libere" in decisions["pending"]
    client.post(f"/api/runs/{run['id']}/decisions/superfici_libere",
                json={"option_id": "fermati",
                      "rationale": "la cupola non è approssimabile con un prisma"})

    job = wait_job(client, client.post(f"/api/runs/{run['id']}/jobs/draw").json()["id"])
    assert job["state"] == "failed"
    assert "superfici_libere" in job["error"]
