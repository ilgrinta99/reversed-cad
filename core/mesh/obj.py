"""Lettura di mesh OBJ. Generico: nessuna conoscenza del pezzo.

Legge vertici, facce e i gruppi `o` dichiarati dal file. I gruppi non sono un
dettaglio: un OBJ esportato da un modellatore porta lì i nomi dei corpi, e usare
quelli è più onesto che ribattezzarli dopo averli ritrovati.

Normali, coordinate texture e materiali vengono ignorati: qui serve la geometria.

`Mesh` sta in `core/mesh/mesh.py` da quando i formati sono quattro; qui resta
importabile perché è da qui che mezzo progetto la importava.
"""

from __future__ import annotations

from pathlib import Path

from core.mesh.mesh import Mesh, costruisci, ventaglio  # noqa: F401  (Mesh: compat)


def load_obj(path: str | Path) -> Mesh:
    """Legge un OBJ triangolando i poligoni a ventaglio."""
    path = Path(path)
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    group_names: list[str] = []
    face_group: list[int] = []
    current = -1

    with path.open("r", errors="replace") as fh:
        for raw in fh:
            if not raw or raw[0] not in "vfog":
                continue
            parts = raw.split()
            if not parts:
                continue
            if parts[0] == "v":
                vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
            elif parts[0] in ("o", "g"):
                name = " ".join(parts[1:]) or f"gruppo_{len(group_names)}"
                group_names.append(name)
                current = len(group_names) - 1
            elif parts[0] == "f":
                idx = [_vertex_index(tok, len(vertices)) for tok in parts[1:]]
                for tri in ventaglio(idx):
                    faces.append(tri)
                    face_group.append(current)

    return costruisci(vertices, faces, source=path, group_names=tuple(group_names),
                      face_group=face_group, format="obj")


def _vertex_index(token: str, n_vertices: int) -> int:
    """`f` accetta `v`, `v/vt`, `v//vn`, `v/vt/vn`, e indici negativi (dal fondo)."""
    raw = int(token.split("/")[0])
    return raw - 1 if raw > 0 else n_vertices + raw
