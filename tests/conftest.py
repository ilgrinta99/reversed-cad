"""Ambiente di test: db e cartella run isolati, mesh sintetica di prova."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="teiser-tests-"))
# Impostate prima di importare l'app: il modulo storage le legge all'avvio.
os.environ.setdefault("TEISER_DB_PATH", str(_TMP / "test.db"))
os.environ.setdefault("TEISER_RUNS_DIR", str(_TMP / "runs"))


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from webapp.backend.app.main import app

    with TestClient(app) as c:  # il context manager esegue il lifespan
        yield c


@pytest.fixture(scope="session")
def box_obj() -> Path:
    """Un OBJ di scatola 40 × 25 × 12 mm, scritto a mano.

    Le misure sono note esattamente: servono a verificare che la pipeline
    restituisca ciò che la mesh contiene, non che indovini un pezzo reale.
    """
    lx, ly, lz = 40.0, 25.0, 12.0
    verts = [
        (0, 0, 0), (lx, 0, 0), (lx, ly, 0), (0, ly, 0),
        (0, 0, lz), (lx, 0, lz), (lx, ly, lz), (0, ly, lz),
    ]
    quads = [
        (1, 2, 3, 4), (5, 8, 7, 6), (1, 5, 6, 2),
        (2, 6, 7, 3), (3, 7, 8, 4), (4, 8, 5, 1),
    ]
    lines = [f"v {x} {y} {z}" for x, y, z in verts]
    lines += [f"f {a} {b} {c} {d}" for a, b, c, d in quads]
    path = _TMP / "box.obj"
    path.write_text("\n".join(lines) + "\n")
    return path


def has_freecad() -> bool:
    from core.freecad.runner import FreeCADNotFound, find_freecad

    try:
        find_freecad()
        return True
    except FreeCADNotFound:
        return False


needs_freecad = pytest.mark.skipif(
    not has_freecad(), reason="FreeCAD non disponibile (imposta FREECAD_BIN)"
)
