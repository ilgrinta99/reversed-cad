"""Lettura di mesh OBJ. Generico: nessuna conoscenza del pezzo.

Volutamente minimale — legge vertici e facce e nient'altro. Quando i tool di
analisi del progetto Teiser entreranno in `core/mesh/`, questo modulo resta il
punto d'ingresso comune per il caricamento.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class Mesh:
    #: (N, 3) coordinate dei vertici, nelle unità del file (per il progetto: mm).
    vertices: np.ndarray
    #: (M, 3) indici dei vertici, triangolata.
    faces: np.ndarray
    source: Path | None = None

    @property
    def bbox(self) -> tuple[np.ndarray, np.ndarray]:
        return self.vertices.min(axis=0), self.vertices.max(axis=0)

    @property
    def extents(self) -> np.ndarray:
        lo, hi = self.bbox
        return hi - lo

    def __len__(self) -> int:
        return len(self.vertices)


def load_obj(path: str | Path) -> Mesh:
    """Legge un OBJ triangolando i poligoni a ventaglio.

    Ignora normali, coordinate texture e materiali: qui serve la geometria.
    """
    path = Path(path)
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []

    with path.open("r", errors="replace") as fh:
        for raw in fh:
            if not raw or raw[0] not in "vf":
                continue
            parts = raw.split()
            if not parts:
                continue
            if parts[0] == "v":
                vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
            elif parts[0] == "f":
                idx = [_vertex_index(tok, len(vertices)) for tok in parts[1:]]
                for i in range(1, len(idx) - 1):  # ventaglio
                    faces.append((idx[0], idx[i], idx[i + 1]))

    if not vertices:
        raise ValueError(f"nessun vertice in {path}: non sembra un OBJ valido")

    return Mesh(
        vertices=np.asarray(vertices, dtype=float),
        faces=np.asarray(faces, dtype=int) if faces else np.empty((0, 3), dtype=int),
        source=path,
    )


def _vertex_index(token: str, n_vertices: int) -> int:
    """`f` accetta `v`, `v/vt`, `v//vn`, `v/vt/vn`, e indici negativi (dal fondo)."""
    raw = int(token.split("/")[0])
    return raw - 1 if raw > 0 else n_vertices + raw
