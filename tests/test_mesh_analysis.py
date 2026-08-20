"""L'analisi è ad hoc: due mesh diverse danno due letture diverse.

I test non verificano che l'analizzatore indovini un pezzo: verificano che
misuri quello che la mesh contiene, e che chieda dove la mesh non è conclusiva.
Le mesh sono costruite qui, con quote note per costruzione, così ogni numero
atteso è verificabile leggendo il test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.mesh.ambiguity import read
from core.mesh.analysis import analyze
from core.mesh.obj import load_obj
from core.mesh.patches import segment


def prism_obj(path: Path, profile: list[tuple[float, float]], depth: float) -> Path:
    """Scrive un OBJ: profilo convesso nel piano XZ, estruso lungo Y.

    L'orientamento conta: l'analisi distingue una faccia esterna da una interna
    dal verso della normale, quindi un solido cucito al contrario non avrebbe
    facce esterne. Il profilo va dato in senso antiorario nel piano XZ.
    """
    lines: list[str] = []
    n = len(profile)
    for y in (0.0, depth):
        for x, z in profile:
            lines.append(f"v {x} {y} {z}")
    faces: list[tuple[int, int, int]] = []
    for i in range(1, n - 1):
        faces.append((1, i + 1, i + 2))            # tappo y = 0, normale −Y
        faces.append((n + 1, n + i + 2, n + i + 1))  # tappo y = depth, normale +Y
    for i in range(n):                              # fianchi
        j = (i + 1) % n
        faces.append((i + 1, n + i + 1, n + j + 1))
        faces.append((i + 1, n + j + 1, j + 1))
    lines += [f"f {a} {b} {c}" for a, b, c in faces]
    path.write_text("\n".join(lines) + "\n")
    return path


def open_box_obj(path: Path, outer: tuple[float, float, float],
                 wall_x: float, wall_y: float, floor: float) -> Path:
    """Uno scatolato a cielo aperto: una superficie sola, non due gusci.

    È la forma di un contenitore vero, ed è il motivo per cui le pareti si
    misurano: dall'esterno si passa al bordo e si scende dentro senza mai
    staccare la superficie. Due scatole chiuse una dentro l'altra sarebbero due
    corpi separati, e non avrebbero pareti da misurare.
    """
    length, width, height = outer
    x0, x1 = 0.0, length
    y0, y1 = 0.0, width
    ix0, ix1 = wall_x, length - wall_x
    iy0, iy1 = wall_y, width - wall_y
    points = [
        (x0, y0, 0.0), (x1, y0, 0.0), (x1, y1, 0.0), (x0, y1, 0.0),          # 1-4 fondo
        (x0, y0, height), (x1, y0, height), (x1, y1, height), (x0, y1, height),  # 5-8 bordo
        (ix0, iy0, height), (ix1, iy0, height), (ix1, iy1, height), (ix0, iy1, height),  # 9-12
        (ix0, iy0, floor), (ix1, iy0, floor), (ix1, iy1, floor), (ix0, iy1, floor),  # 13-16
    ]
    quads = [
        (1, 4, 3, 2),        # fondo esterno, normale −Z
        (1, 2, 6, 5), (2, 3, 7, 6), (3, 4, 8, 7), (4, 1, 5, 8),  # pareti esterne
        (5, 6, 10, 9), (6, 7, 11, 10), (7, 8, 12, 11), (8, 5, 9, 12),  # bordo
        (9, 10, 14, 13), (10, 11, 15, 14), (11, 12, 16, 15), (12, 9, 13, 16),  # pareti interne
        (13, 14, 15, 16),    # fondo interno, normale +Z
    ]
    lines = [f"v {x} {y} {z}" for x, y, z in points]
    lines += [f"f {a} {b} {c} {d}" for a, b, c, d in quads]
    path.write_text("\n".join(lines) + "\n")
    return path


@pytest.fixture(scope="module")
def workdir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("analisi")


def test_scatola_semplice_non_solleva_ambiguita(box_obj: Path):
    """Una scatola con quote tonde e spigoli vivi non ha niente da chiedere."""
    reading = read(analyze(box_obj))
    dims = {d.id: d for d in reading.registry}
    assert dims["c1_ingombro_x"].measured == pytest.approx(40.0)
    assert dims["c1_ingombro_y"].measured == pytest.approx(25.0)
    assert dims["c1_ingombro_z"].measured == pytest.approx(12.0)
    # La misura è già un'origine legittima: nessuna quota blocca la build.
    assert all(d.used == d.measured for d in reading.registry)
    assert reading.registry.blocking() == []
    assert len(reading.decisions) == 0
    assert any("Nessuna ambiguità" in n for n in reading.notes)


def test_quote_quasi_tonde_diventano_una_scelta_di_arrotondamento(workdir: Path):
    """40.02 non è 40: arrotondarlo d'ufficio sarebbe inventare, tacerlo sarebbe peggio."""
    mesh = prism_obj(workdir / "quasi.obj",
                     [(0, 0), (40.02, 0), (40.02, 12), (0, 12)], 25.0)
    reading = read(analyze(mesh))
    decision = reading.decisions.get("arrotondamento")
    assert not decision.resolved
    option = decision.option("passo_0_1")
    assert option.sets["c1_ingombro_x"] == pytest.approx(40.0)
    # Finché non si sceglie, nel modello entra la misura, non il valore tondo.
    assert reading.registry.get("c1_ingombro_x").used == pytest.approx(40.02)


def test_raccordo_non_circolare_riconosciuto_dai_due_arretramenti(workdir: Path):
    """La faccia superiore si ferma 1 mm prima, il fianco 2 mm sotto: non è un raggio."""
    mesh = prism_obj(workdir / "raccordo.obj",
                     [(0, 0), (40, 0), (40, 10), (39, 12), (0, 12)], 25.0)
    reading = read(analyze(mesh))
    ambiguities = [d for d in reading.decisions if d.id.endswith("_zmax")]
    assert len(ambiguities) == 1, [d.id for d in reading.decisions]
    decision = ambiguities[0]
    radii = sorted(o.sets[f"{decision.id}_r"] for o in decision.options if o.sets)
    assert radii == pytest.approx([1.0, 2.0])
    # Il raggio unico non esiste nella mesh: nasce vuoto e blocca la build.
    unique = reading.registry.get(f"{decision.id}_r")
    assert unique.used is None
    assert unique.status.blocks_build

    # Scelto un raggio, la quota si riempie con l'approvazione registrata.
    scelta = decision.option("circolare_z")
    reading.decisions.resolve(decision.id, scelta.id, by="collaudo",
                              rationale="raggio nominale dell'arretramento verticale")
    reading.decisions.get(decision.id).apply_to(reading.registry)
    approved = reading.registry.get(f"{decision.id}_r")
    assert approved.used == pytest.approx(2.0)
    assert approved.approval is not None
    assert approved.approval.rationale.startswith(decision.id)
    assert reading.registry.blocking() == []


def test_pareti_asimmetriche_di_una_scatola_cava(workdir: Path):
    """Uno scatolato con pareti diverse sui due assi è un'ambiguità, non un dato."""
    mesh = open_box_obj(workdir / "scatolato.obj", (40.0, 25.0, 12.0),
                        wall_x=1.0, wall_y=3.0, floor=2.0)
    analysis = analyze(mesh)
    body = analysis.bodies[0]
    assert body.walls["X-min"] == pytest.approx(1.0)
    assert body.walls["X-max"] == pytest.approx(1.0)
    assert body.walls["Y-min"] == pytest.approx(3.0)
    assert body.walls["Y-max"] == pytest.approx(3.0)
    assert body.cavity_floor == pytest.approx(2.0)

    reading = read(analysis)
    decision = reading.decisions.get(f"{body.key}_pareti")
    assert {o.id for o in decision.options} == {"misurato", "minimo", "massimo"}
    assert decision.option("minimo").sets[f"{body.key}_parete_y_min"] == pytest.approx(1.0)
    assert decision.option("massimo").sets[f"{body.key}_parete_x_min"] == pytest.approx(3.0)
    # Lo spessore del fondo è una quota misurata, non una parete da uniformare.
    assert reading.registry.get(f"{body.key}_fondo_spessore").used == pytest.approx(2.0)


def test_corpi_separati_sono_una_domanda(workdir: Path, box_obj: Path):
    """Due solidi scollegati: assieme, o pezzo più scarti dell'esportazione?"""
    text = box_obj.read_text().splitlines()
    shift = len([r for r in text if r.startswith("v ")])
    for row in box_obj.read_text().splitlines():
        if row.startswith("v "):
            x, y, z = row.split()[1:]
            text.append(f"v {float(x) + 100.0} {y} {z}")
        elif row.startswith("f "):
            text.append("f " + " ".join(str(int(t) + shift) for t in row.split()[1:]))
    due = workdir / "due_corpi.obj"
    due.write_text("\n".join(text) + "\n")

    analysis = analyze(due)
    assert len(analysis.bodies) == 2
    decision = read(analysis).decisions.get("corpi")
    assert {o.id for o in decision.options} == {"tutti", "principale"}


def test_la_mesh_reale_del_progetto_si_misura_da_sola():
    """Sul contenitore vero l'analisi generica ritrova le quote del briefing.

    Non è un test di regressione su numeri arbitrari: 1.293 e 2.188 sono gli
    spessori catalogati in docs/lost+found_design.md §5-B, 1.634 il fondo di
    §3.1, e qui li ritrova un codice che del TAISER non sa niente.
    """
    mesh = Path("input/model.obj")
    if not mesh.is_file():
        pytest.skip("input/model.obj non disponibile")
    analysis = analyze(mesh)
    scatola = analysis.bodies[0]
    assert list(scatola.extents) == pytest.approx([80.0, 46.0, 26.999], abs=1e-3)
    assert scatola.walls["Y-min"] == pytest.approx(2.188, abs=1e-3)
    assert scatola.walls["Y-max"] == pytest.approx(2.188, abs=1e-3)
    assert scatola.cavity_floor == pytest.approx(1.634, abs=1e-3)
    coperchio = analysis.bodies[1]
    assert list(coperchio.extents) == pytest.approx([74.0, 46.0, 2.5], abs=1e-3)

    reading = read(analysis)
    assert {"superfici_libere", "corpi", "datum", "arrotondamento"} <= {
        d.id for d in reading.decisions
    }
    # La cupola non è ricostruibile con una primitiva, e viene detto invece che
    # approssimato di nascosto.
    assert any(not f.buildable and f.kind == "libera" for f in analysis.features)


def test_segmentazione_riconosce_piani_e_cilindri(box_obj: Path):
    bodies = segment(load_obj(box_obj))
    assert len(bodies) == 1
    body = bodies[0]
    assert body.closed
    assert len(body.of_kind("plane")) == 6
    assert body.volume == pytest.approx(40.0 * 25.0 * 12.0)
