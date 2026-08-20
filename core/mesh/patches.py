"""Segmentazione di una mesh in patch di superficie, e loro riconoscimento.

Generico per costruzione: qui non c'è un solo numero del pezzo. Il modulo prende
un triangolato qualsiasi e risponde a due domande che valgono per ogni mesh:

* **di quanti corpi separati è fatta?** (componenti connesse per spigolo);
* **di quali superfici è fatto ogni corpo?** (patch a normale coerente, ciascuna
  riconosciuta come piano, cilindro, sfera o superficie libera).

È il livello su cui poggia l'analisi ad hoc: senza questo, «misurare la mesh»
significherebbe conoscere già il pezzo. L'algoritmo è quello di
`tools/segment_features.py`, che sul contenitore TAISER è stato verificato,
riscritto in forma vettoriale e con l'asse dei cilindri stimato dalle normali
invece che provato fra i tre assi coordinati.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterator

import numpy as np

from core.mesh.mesh import Mesh

#: Due vertici più vicini di così sono lo stesso vertice. Gli export triangolati
#: duplicano i vertici per faccia: senza saldatura non esistono spigoli condivisi
#: e ogni triangolo sarebbe un corpo a sé.
WELD_TOL = 1e-4

#: Oltre questo angolo fra normali adiacenti la superficie è considerata spezzata.
#: 12° è il valore verificato sulla mesh di riferimento: separa la fascia dei
#: raccordi dalle facce piane a cui è tangente, senza spezzare in mille pezzi una
#: superficie curva tassellata fine. A 20° i raccordi si fondono con le pareti e
#: le facce esterne spariscono dall'elenco.
BREAK_ANGLE_DEG = 12.0

#: Sotto questa dispersione di normali la patch è un piano.
PLANE_SPREAD_DEG = 1.0

#: Errore di fit relativo al raggio, oltre il quale la primitiva è rifiutata.
FIT_RMS_RATIO = 0.02

#: Errore di fit assoluto, in mm. Il solo criterio relativo non basta: una fascia
#: di raccordo che gira intorno al pezzo si lascia interpolare da un cilindro di
#: raggio enorme con errore relativo minuscolo, e il numero che ne esce non
#: significa niente. La soglia è quella del progetto sulle feature piane
#: (docs/CONVENTIONS.md): oltre 0.10 mm il fit non descrive la superficie.
FIT_RMS_ABS = 0.10


@dataclass(frozen=True)
class Patch:
    """Una porzione di superficie a normale coerente, con la primitiva che la spiega.

    `kind` vale `plane`, `cylinder`, `sphere` o `free`. `free` non è un fallimento
    dell'algoritmo: è un'informazione: significa che quella superficie non è
    ricostruibile con una primitiva elementare, ed è esattamente il caso che va
    portato all'utente invece che approssimato di nascosto.
    """

    faces: np.ndarray
    kind: str
    area: float
    bbox_min: np.ndarray
    bbox_max: np.ndarray
    spread_deg: float
    normal: np.ndarray | None = None       # piano: normale media
    offset: float | None = None            # piano: n · p
    axis: np.ndarray | None = None         # cilindro: direzione dell'asse
    center: np.ndarray | None = None       # cilindro/sfera: punto sull'asse / centro
    radius: float | None = None
    length: float | None = None            # cilindro: estensione lungo l'asse
    rms: float = 0.0

    @property
    def extents(self) -> np.ndarray:
        return self.bbox_max - self.bbox_min

    @property
    def axis_name(self) -> str | None:
        """`X`, `Y` o `Z` se l'asse del cilindro è coordinato entro 1°, altrimenti None."""
        if self.axis is None:
            return None
        for k, name in enumerate("XYZ"):
            if abs(abs(float(self.axis[k])) - 1.0) < 1.5e-4:  # cos(1°) ≈ 0.99985
                return name
        return None

    @property
    def normal_axis(self) -> str | None:
        """`X`, `Y` o `Z` se il piano è perpendicolare a un asse coordinato."""
        if self.normal is None:
            return None
        for k, name in enumerate("XYZ"):
            if abs(abs(float(self.normal[k])) - 1.0) < 1.5e-4:
                return name
        return None

    def describe(self) -> str:
        if self.kind == "plane":
            n = self.normal if self.normal is not None else np.zeros(3)
            return (f"piano A={self.area:.2f} n=({n[0]:+.3f},{n[1]:+.3f},{n[2]:+.3f}) "
                    f"d={self.offset:+.4f}")
        if self.kind == "cylinder":
            return (f"cilindro A={self.area:.2f} asse={self.axis_name or 'obliquo'} "
                    f"R={self.radius:.4f} L={self.length:.3f} rms={self.rms:.4f}")
        if self.kind == "sphere":
            return f"sfera A={self.area:.2f} R={self.radius:.4f} rms={self.rms:.4f}"
        return f"libera A={self.area:.2f} spread={self.spread_deg:.1f}°"


@dataclass(frozen=True)
class Body:
    """Un corpo: insieme di triangoli connessi per spigolo, con le sue patch."""

    name: str
    faces: np.ndarray
    patches: tuple[Patch, ...]
    bbox_min: np.ndarray
    bbox_max: np.ndarray
    volume: float
    area: float
    closed: bool

    @property
    def extents(self) -> np.ndarray:
        return self.bbox_max - self.bbox_min

    def of_kind(self, kind: str) -> list[Patch]:
        return [p for p in self.patches if p.kind == kind]

    def planes_normal_to(self, axis: str) -> list[Patch]:
        return [p for p in self.of_kind("plane") if p.normal_axis == axis]


# -- saldatura e adiacenza --------------------------------------------------


def weld(vertices: np.ndarray, tol: float = WELD_TOL) -> np.ndarray:
    """Indice del vertice saldato per ogni vertice originale."""
    key = np.round(vertices / tol).astype(np.int64)
    _, inverse = np.unique(key, axis=0, return_inverse=True)
    return inverse.reshape(-1)


def face_normals(vertices: np.ndarray, faces: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Normali unitarie e area di ogni triangolo. Area nulla ⇒ normale nulla."""
    if len(faces) == 0:
        return np.zeros((0, 3)), np.zeros(0)
    cross = np.cross(vertices[faces[:, 1]] - vertices[faces[:, 0]],
                     vertices[faces[:, 2]] - vertices[faces[:, 0]])
    norm = np.linalg.norm(cross, axis=1)
    good = norm > 1e-12
    unit = np.zeros_like(cross)
    unit[good] = cross[good] / norm[good, None]
    return unit, norm / 2.0


def _edge_pairs(faces: np.ndarray, welded: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Coppie di facce che condividono uno spigolo, e conteggio facce per spigolo.

    Vettoriale: su una mesh da centomila triangoli il ciclo Python del prototipo
    costava minuti.
    """
    if len(faces) == 0:
        return np.zeros((0, 2), dtype=int), np.zeros(0, dtype=int)
    n = len(faces)
    ends = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    ends = np.sort(welded[ends], axis=1)
    _, edge_id, counts = np.unique(ends, axis=0, return_inverse=True, return_counts=True)
    edge_id = edge_id.reshape(-1)
    owner = np.tile(np.arange(n), 3)

    order = np.argsort(edge_id, kind="stable")
    edge_sorted, owner_sorted = edge_id[order], owner[order]
    # Dentro ogni gruppo di facce con lo stesso spigolo, si collegano a catena:
    # basta per l'unione, e non esplode sugli spigoli non-manifold.
    same = edge_sorted[1:] == edge_sorted[:-1]
    pairs = np.stack([owner_sorted[:-1][same], owner_sorted[1:][same]], axis=1)
    return pairs, counts


class _Union:
    """Union-find con compressione. Poche migliaia di unioni: basta e avanza."""

    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, a: int) -> int:
        root = a
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[a] != root:
            self.parent[a], a = root, self.parent[a]
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra

    def groups(self) -> list[np.ndarray]:
        buckets: dict[int, list[int]] = {}
        for i in range(len(self.parent)):
            buckets.setdefault(self.find(i), []).append(i)
        return [np.asarray(v, dtype=int) for v in buckets.values()]


# -- fit delle primitive ----------------------------------------------------


def fit_plane(points: np.ndarray, normal: np.ndarray) -> tuple[float, float]:
    """Quota del piano lungo la normale, ed errore quadratico medio."""
    d = points @ normal
    return float(d.mean()), float(np.sqrt(np.mean((d - d.mean()) ** 2)))


def fit_cylinder(points: np.ndarray, normals: np.ndarray
                 ) -> tuple[np.ndarray, np.ndarray, float, float] | None:
    """Asse, punto sull'asse, raggio ed rms di un cilindro che spieghi la patch.

    L'asse non si prova fra i tre assi coordinati: si ricava dalle normali. Su un
    cilindro le normali stanno tutte nel piano perpendicolare all'asse, quindi
    l'asse è l'autovettore minore di Σ nnᵀ. Un raccordo obliquo viene trovato
    come uno verticale, e l'inclinazione resta misurabile invece che persa.
    """
    if len(points) < 6:
        return None
    cov = normals.T @ normals
    values, vectors = np.linalg.eigh(cov)
    axis = vectors[:, 0]
    axis = axis / np.linalg.norm(axis)
    # Base del piano perpendicolare all'asse.
    seed = np.array([1.0, 0.0, 0.0]) if abs(axis[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(axis, seed)
    u /= np.linalg.norm(u)
    v = np.cross(axis, u)

    x, y = points @ u, points @ v
    A = np.c_[2 * x, 2 * y, np.ones(len(x))]
    try:
        sol, *_ = np.linalg.lstsq(A, x ** 2 + y ** 2, rcond=None)
    except np.linalg.LinAlgError:
        return None
    cx, cy = float(sol[0]), float(sol[1])
    radius = math.sqrt(max(float(sol[2]) + cx ** 2 + cy ** 2, 0.0))
    if radius <= 1e-9:
        return None
    rms = float(np.sqrt(np.mean((np.hypot(x - cx, y - cy) - radius) ** 2)))
    t = points @ axis
    center = cx * u + cy * v + float(t.mean()) * axis
    return axis, center, radius, rms


def fit_sphere(points: np.ndarray) -> tuple[np.ndarray, float, float] | None:
    if len(points) < 8:
        return None
    A = np.c_[2 * points, np.ones(len(points))]
    try:
        sol, *_ = np.linalg.lstsq(A, (points ** 2).sum(axis=1), rcond=None)
    except np.linalg.LinAlgError:
        return None
    center = sol[:3]
    radius = math.sqrt(max(float(sol[3]) + float(center @ center), 0.0))
    if radius <= 1e-9:
        return None
    rms = float(np.sqrt(np.mean((np.linalg.norm(points - center, axis=1) - radius) ** 2)))
    return center, radius, rms


# -- segmentazione ----------------------------------------------------------


def classify(vertices: np.ndarray, faces: np.ndarray, group: np.ndarray,
             normals: np.ndarray, areas: np.ndarray) -> Patch:
    """Riconosce la primitiva di una patch. Nell'ordine: piano, cilindro, sfera."""
    points = vertices[np.unique(faces[group])]
    mean_normal = normals[group].mean(axis=0)
    norm = np.linalg.norm(mean_normal)
    mean_normal = mean_normal / norm if norm > 1e-12 else np.array([0.0, 0.0, 1.0])
    spread = float(np.degrees(np.arccos(
        np.clip(normals[group] @ mean_normal, -1.0, 1.0))).max())
    common = dict(faces=group, area=float(areas[group].sum()),
                  bbox_min=points.min(axis=0), bbox_max=points.max(axis=0),
                  spread_deg=spread)

    if spread < PLANE_SPREAD_DEG:
        offset, rms = fit_plane(points, mean_normal)
        return Patch(kind="plane", normal=mean_normal, offset=offset, rms=rms, **common)

    cyl = fit_cylinder(points, normals[group])
    if cyl is not None:
        axis, center, radius, rms = cyl
        if rms / radius < FIT_RMS_RATIO and rms < FIT_RMS_ABS:
            t = points @ axis
            return Patch(kind="cylinder", axis=axis, center=center, radius=radius,
                         length=float(t.max() - t.min()), rms=rms, **common)

    sph = fit_sphere(points)
    if sph is not None:
        center, radius, rms = sph
        if rms / radius < FIT_RMS_RATIO and rms < FIT_RMS_ABS:
            return Patch(kind="sphere", center=center, radius=radius, rms=rms, **common)

    return Patch(kind="free", **common)


def segment(mesh: Mesh, *, break_angle_deg: float = BREAK_ANGLE_DEG,
            min_area: float = 0.0) -> list[Body]:
    """Divide la mesh in corpi e ogni corpo in patch riconosciute.

    I nomi dei corpi vengono dai gruppi `o` del file OBJ quando ci sono: è il file
    stesso a dichiararli, e usarli è più onesto che rinominarli `corpo_0`.
    """
    welded = weld(mesh.vertices)
    normals, areas = face_normals(mesh.vertices, mesh.faces)
    pairs, _ = _edge_pairs(mesh.faces, welded)

    bodies_union = _Union(len(mesh.faces))
    for a, b in pairs:
        bodies_union.union(int(a), int(b))

    cos_limit = math.cos(math.radians(break_angle_deg))
    smooth = _Union(len(mesh.faces))
    if len(pairs):
        dot = np.einsum("ij,ij->i", normals[pairs[:, 0]], normals[pairs[:, 1]])
        for a, b in pairs[dot > cos_limit]:
            smooth.union(int(a), int(b))

    patches_by_root: dict[int, list[np.ndarray]] = {}
    for group in smooth.groups():
        patches_by_root.setdefault(bodies_union.find(int(group[0])), []).append(group)

    out: list[Body] = []
    for face_group in sorted(bodies_union.groups(), key=lambda g: -areas[g].sum()):
        faces = mesh.faces[face_group]
        points = mesh.vertices[np.unique(faces)]
        groups = patches_by_root.get(bodies_union.find(int(face_group[0])), [])
        patches = [classify(mesh.vertices, mesh.faces, g, normals, areas) for g in groups]
        patches = [p for p in patches if p.area >= min_area]
        patches.sort(key=lambda p: -p.area)
        out.append(Body(
            name=mesh.group_of(face_group[0]) or f"corpo_{len(out)}",
            faces=face_group,
            patches=tuple(patches),
            bbox_min=points.min(axis=0),
            bbox_max=points.max(axis=0),
            volume=signed_volume(mesh.vertices, faces),
            area=float(areas[face_group].sum()),
            closed=is_closed(faces, welded),
        ))
    return out


def signed_volume(vertices: np.ndarray, faces: np.ndarray) -> float:
    """Volume racchiuso, dal teorema della divergenza. Solo se la mesh è chiusa."""
    if len(faces) == 0:
        return 0.0
    a, b, c = vertices[faces[:, 0]], vertices[faces[:, 1]], vertices[faces[:, 2]]
    return float(abs(np.einsum("ij,ij->i", a, np.cross(b, c)).sum()) / 6.0)


def is_closed(faces: np.ndarray, welded: np.ndarray) -> bool:
    """Ogni spigolo condiviso da esattamente due triangoli: il corpo è chiuso."""
    _, counts = _edge_pairs(faces, welded)
    return bool(len(counts)) and bool((counts == 2).all())


def iter_patches(bodies: list[Body]) -> Iterator[tuple[Body, Patch]]:
    for body in bodies:
        for patch in body.patches:
            yield body, patch
