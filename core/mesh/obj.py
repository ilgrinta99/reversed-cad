"""Lettura di mesh OBJ. Generico: nessuna conoscenza del pezzo.

Legge vertici, facce e i gruppi `o` dichiarati dal file. I gruppi non sono un
dettaglio: un OBJ esportato da un modellatore porta lì i nomi dei corpi, e usare
quelli è più onesto che ribattezzarli dopo averli ritrovati.

Normali, coordinate texture e materiali vengono ignorati: qui serve la geometria.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class Mesh:
    #: (N, 3) coordinate dei vertici, nelle unità del file (per il progetto: mm).
    vertices: np.ndarray
    #: (M, 3) indici dei vertici, triangolata.
    faces: np.ndarray
    source: Path | None = None
    #: Nomi dei gruppi `o` incontrati nel file, nell'ordine.
    group_names: tuple[str, ...] = ()
    #: (M,) indice del gruppo di ogni faccia; -1 se il file non ne dichiara.
    face_group: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=int))

    @property
    def bbox(self) -> tuple[np.ndarray, np.ndarray]:
        return self.vertices.min(axis=0), self.vertices.max(axis=0)

    @property
    def extents(self) -> np.ndarray:
        lo, hi = self.bbox
        return hi - lo

    def group_of(self, face_index: int) -> str | None:
        """Nome del gruppo `o` a cui appartiene una faccia, se il file lo dichiara."""
        if len(self.face_group) <= face_index:
            return None
        idx = int(self.face_group[face_index])
        return self.group_names[idx] if 0 <= idx < len(self.group_names) else None

    def __len__(self) -> int:
        return len(self.vertices)


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
                for i in range(1, len(idx) - 1):  # ventaglio
                    faces.append((idx[0], idx[i], idx[i + 1]))
                    face_group.append(current)

    if not vertices:
        raise ValueError(f"nessun vertice in {path}: non sembra un OBJ valido")

    return Mesh(
        vertices=np.asarray(vertices, dtype=float),
        faces=np.asarray(faces, dtype=int) if faces else np.empty((0, 3), dtype=int),
        source=path,
        group_names=tuple(group_names),
        face_group=np.asarray(face_group, dtype=int) if face_group
        else np.empty(0, dtype=int),
    )


def _vertex_index(token: str, n_vertices: int) -> int:
    """`f` accetta `v`, `v/vt`, `v//vn`, `v/vt/vn`, e indici negativi (dal fondo)."""
    raw = int(token.split("/")[0])
    return raw - 1 if raw > 0 else n_vertices + raw
