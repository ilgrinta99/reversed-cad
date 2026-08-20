"""Il tipo `Mesh` e i due servizi che ogni lettore di formato usa.

Sta qui e non dentro un lettore perché i formati sono quattro e il tipo è uno.
Quello che un lettore deve produrre è sempre lo stesso: vertici, triangoli, e —
se il file li dichiara — i nomi dei corpi. Come li dichiara è affare suo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

#: Due vertici più vicini di così sono lo stesso vertice quando si salda una mesh
#: che non porta topologia (STL). È la stessa soglia con cui `core/mesh/patches.py`
#: ricostruisce l'adiacenza: usarne una diversa qui vorrebbe dire che due parti
#: del programma non sono d'accordo su cosa sia un vertice.
SALDATURA_TOL = 1e-4


@dataclass(frozen=True)
class Mesh:
    #: (N, 3) coordinate dei vertici, nelle unità del file (per il progetto: mm).
    vertices: np.ndarray
    #: (M, 3) indici dei vertici, triangolata.
    faces: np.ndarray
    source: Path | None = None
    #: Nomi dei corpi dichiarati dal file, nell'ordine. Ogni formato li chiama a
    #: modo suo — `o` in OBJ, `solid` in STL ASCII, `DEF` in VRML — e in PLY non
    #: esistono affatto.
    group_names: tuple[str, ...] = ()
    #: (M,) indice del gruppo di ogni faccia; -1 se il file non ne dichiara.
    face_group: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=int))
    #: Formato di provenienza, come suffisso senza punto: obj, stl, ply, wrl.
    format: str = ""

    @property
    def bbox(self) -> tuple[np.ndarray, np.ndarray]:
        return self.vertices.min(axis=0), self.vertices.max(axis=0)

    @property
    def extents(self) -> np.ndarray:
        lo, hi = self.bbox
        return hi - lo

    def group_of(self, face_index: int) -> str | None:
        """Nome del gruppo a cui appartiene una faccia, se il file lo dichiara."""
        if len(self.face_group) <= face_index:
            return None
        idx = int(self.face_group[face_index])
        return self.group_names[idx] if 0 <= idx < len(self.group_names) else None

    def __len__(self) -> int:
        return len(self.vertices)


class MeshNonLeggibile(ValueError):
    """Il file non contiene una mesh utilizzabile, e il messaggio dice perché."""


def ventaglio(indici: list[int]) -> list[tuple[int, int, int]]:
    """Triangola un poligono a ventaglio dal primo vertice.

    Vale per i quadrilateri degli esportatori e per i poligoni convessi. Su un
    poligono concavo il ventaglio sbaglia — ma nessuno dei quattro formati qui
    supportati è usato per mandare poligoni concavi da un CAD, e inventare una
    triangolazione robusta significherebbe far finta di sapere di più del file.
    """
    return [(indici[0], indici[i], indici[i + 1]) for i in range(1, len(indici) - 1)]


def salda(vertices: np.ndarray, faces: np.ndarray,
          tol: float = SALDATURA_TOL) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Fonde i vertici coincidenti, rinumera le facce, scarta le degeneri.

    Serve ai formati che non portano topologia: in un STL ogni triangolo ha i
    suoi tre vertici, e senza saldatura la segmentazione in corpi troverebbe
    tanti corpi quanti sono i triangoli.

    La saldatura **non sposta** i vertici: la griglia serve solo a raggruppare, e
    di ogni gruppo si tiene la coordinata del primo incontrato. Una mesh misurata
    su vertici arrotondati sarebbe una mesh diversa da quella caricata.

    Ritorna anche la maschera delle facce sopravvissute, perché chi ha in mano un
    dato per faccia (il gruppo di appartenenza) deve poterlo filtrare allo stesso
    modo. Le degeneri le crea la saldatura stessa: un triangolo più sottile della
    tolleranza collassa su un segmento, e come faccia non esiste più.
    """
    if len(vertices) == 0:
        return vertices, faces, np.ones(len(faces), dtype=bool)
    chiave = np.round(vertices / tol).astype(np.int64)
    _, primo, inverso = np.unique(chiave, axis=0, return_index=True, return_inverse=True)
    # `primo` è, per ogni chiave, l'indice del primo vertice originale che la
    # porta: le coordinate che restano sono quelle del file, non quelle arrotondate.
    v = vertices[primo]
    if not len(faces):
        return v, faces, np.ones(0, dtype=bool)
    f = inverso.reshape(-1)[faces]
    vive = (f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 2] != f[:, 0])
    return v, f[vive], vive


def costruisci(vertices, faces, *, source: Path | None = None,
               group_names: tuple[str, ...] = (), face_group=None,
               format: str = "", salda_vertici: bool = False) -> Mesh:
    """Impacchetta il risultato di un lettore, con i controlli comuni a tutti."""
    v = np.asarray(vertices, dtype=float).reshape(-1, 3) if len(vertices) \
        else np.empty((0, 3), dtype=float)
    f = np.asarray(faces, dtype=int).reshape(-1, 3) if len(faces) \
        else np.empty((0, 3), dtype=int)
    if len(v) == 0:
        raise MeshNonLeggibile(f"nessun vertice in {source}: il file non contiene una mesh")
    if len(f) and (f.min() < 0 or f.max() >= len(v)):
        raise MeshNonLeggibile(
            f"{source}: una faccia rimanda a un vertice inesistente "
            f"(indici {int(f.min())}..{int(f.max())} su {len(v)} vertici)")
    gruppi = np.asarray(face_group, dtype=int) if face_group is not None \
        else np.empty(0, dtype=int)
    if salda_vertici:
        v, f, vive = salda(v, f)
        if len(gruppi) == len(vive):
            gruppi = gruppi[vive]
    return Mesh(vertices=v, faces=f, source=source, group_names=tuple(group_names),
                face_group=gruppi, format=format)
